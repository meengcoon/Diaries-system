#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def _require_deps() -> None:
    try:
        import torch  # noqa: F401
        import datasets  # noqa: F401
        import transformers  # noqa: F401
        import peft  # noqa: F401
    except Exception as e:
        raise RuntimeError(
            "Missing deps for training. Install: pip install torch datasets transformers peft trl accelerate"
        ) from e


def _load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _format_chat(example: dict, tokenizer) -> str:
    msgs = example.get("messages") or []
    if not isinstance(msgs, list) or not msgs:
        sys = str(example.get("system") or "")
        instr = str(example.get("instruction") or "")
        inp = str(example.get("input") or "")
        out = str(example.get("output") or "")
        msgs = [
            {"role": "system", "content": sys},
            {"role": "user", "content": f"{instr}\n\n{inp}".strip()},
            {"role": "assistant", "content": out},
        ]
    return tokenizer.apply_chat_template(msgs, tokenize=False, add_generation_prompt=False)


def main() -> int:
    _require_deps()

    import torch
    from datasets import Dataset
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments

    p = argparse.ArgumentParser(description="Train LoRA adapter on exported diary SFT dataset")
    p.add_argument("--base-model", default="Qwen/Qwen2.5-3B-Instruct")
    p.add_argument("--train-jsonl", default="training_data/sft_train.jsonl")
    p.add_argument("--val-jsonl", default="training_data/sft_val.jsonl")
    p.add_argument("--out-dir", default="artifacts/lora-diary")
    p.add_argument("--epochs", type=float, default=2.0)
    p.add_argument("--lr", type=float, default=2e-4)
    p.add_argument("--batch-size", type=int, default=1)
    p.add_argument("--grad-accum", type=int, default=16)
    p.add_argument("--max-length", type=int, default=2048)
    p.add_argument("--logging-steps", type=int, default=1)
    p.add_argument("--lora-r", type=int, default=16)
    p.add_argument("--lora-alpha", type=int, default=32)
    p.add_argument("--lora-dropout", type=float, default=0.05)
    args = p.parse_args()

    train_path = Path(args.train_jsonl)
    val_path = Path(args.val_jsonl)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    train_rows = _load_jsonl(train_path)
    val_rows = _load_jsonl(val_path)

    tokenizer = AutoTokenizer.from_pretrained(args.base_model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    def preprocess(rows: list[dict]) -> Dataset:
        texts = [_format_chat(x, tokenizer) for x in rows]
        ds = Dataset.from_dict({"text": texts})

        def tok(batch):
            out = tokenizer(
                batch["text"],
                truncation=True,
                max_length=int(args.max_length),
                padding="max_length",
            )
            out["labels"] = out["input_ids"].copy()
            return out

        return ds.map(tok, batched=True, remove_columns=["text"])

    train_ds = preprocess(train_rows)
    val_ds = preprocess(val_rows)

    has_cuda = torch.cuda.is_available()
    has_mps = bool(getattr(torch.backends, "mps", None) and torch.backends.mps.is_available())
    # On Apple MPS, float32 for 3B often OOMs. Prefer float16.
    if has_cuda:
        dtype = torch.bfloat16
    elif has_mps:
        dtype = torch.float16
    else:
        dtype = torch.float32
    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        dtype=dtype,
        device_map="auto" if has_cuda else None,
        trust_remote_code=True,
    )

    lora_cfg = LoraConfig(
        r=int(args.lora_r),
        lora_alpha=int(args.lora_alpha),
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_dropout=float(args.lora_dropout),
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_cfg)
    model.gradient_checkpointing_enable()
    model.enable_input_require_grads()
    model.print_trainable_parameters()

    targs = TrainingArguments(
        output_dir=str(out_dir),
        num_train_epochs=float(args.epochs),
        learning_rate=float(args.lr),
        per_device_train_batch_size=int(args.batch_size),
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=int(args.grad_accum),
        eval_strategy="steps",
        eval_steps=100,
        save_steps=100,
        logging_steps=max(1, int(args.logging_steps)),
        bf16=bool(has_cuda),
        fp16=bool(has_mps),
        warmup_ratio=0.03,
        weight_decay=0.0,
        report_to="none",
        load_best_model_at_end=False,
        dataloader_pin_memory=not has_mps,
        dataloader_num_workers=0,
    )

    trainer = Trainer(
        model=model,
        args=targs,
        train_dataset=train_ds,
        eval_dataset=val_ds,
    )

    trainer.train()
    trainer.save_model(str(out_dir / "adapter"))
    tokenizer.save_pretrained(str(out_dir / "adapter"))

    print(json.dumps({"ok": True, "adapter_dir": str((out_dir / 'adapter').resolve())}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
