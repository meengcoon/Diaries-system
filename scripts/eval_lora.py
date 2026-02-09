#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _require_deps() -> None:
    try:
        import torch  # noqa: F401
        import peft  # noqa: F401
        import transformers  # noqa: F401
    except Exception as e:
        raise RuntimeError("Missing deps. Install: pip install torch transformers peft") from e


def _load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main() -> int:
    _require_deps()

    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    p = argparse.ArgumentParser(description="Quick eval for LoRA diary adapter")
    p.add_argument("--base-model", default="Qwen/Qwen2.5-3B-Instruct")
    p.add_argument("--adapter-dir", default="artifacts/lora-diary/adapter")
    p.add_argument("--val-jsonl", default="training_data/sft_val.jsonl")
    p.add_argument("--num-samples", type=int, default=5)
    p.add_argument("--max-new-tokens", type=int, default=160)
    args = p.parse_args()

    val_rows = _load_jsonl(Path(args.val_jsonl))[: max(1, int(args.num_samples))]

    tokenizer = AutoTokenizer.from_pretrained(args.base_model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    torch_dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32
    base = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        torch_dtype=torch_dtype,
        device_map="auto" if torch.cuda.is_available() else None,
        trust_remote_code=True,
    )
    model = PeftModel.from_pretrained(base, args.adapter_dir)
    model.eval()

    for i, ex in enumerate(val_rows, start=1):
        msgs = ex.get("messages") or []
        if len(msgs) < 2:
            continue
        prompt_msgs = msgs[:-1]
        ref = str(msgs[-1].get("content") or "")

        text = tokenizer.apply_chat_template(prompt_msgs, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(text, return_tensors="pt").to(model.device)
        with torch.no_grad():
            out = model.generate(**inputs, max_new_tokens=int(args.max_new_tokens), do_sample=False)
        gen = tokenizer.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)

        print(f"\\n=== Sample {i} ===")
        print("[Prompt User]", prompt_msgs[-1].get("content", "")[:220])
        print("[Model]", gen[:400])
        print("[Ref]", ref[:400])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
