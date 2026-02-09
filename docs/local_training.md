# Local Model Training (LoRA)

This project currently uses retrieval + memory (RAG). It does **not** fine-tune model weights by default.

Use the scripts below to train a LoRA adapter from your local SQLite data.

## 1) Export SFT dataset from DB

```bash
cd "/Users/lincma/Documents/diary system"
python3 scripts/export_sft_dataset.py --limit 10000 --out-dir training_data
```

Outputs:
- `training_data/sft_train.jsonl`
- `training_data/sft_val.jsonl`

## 2) Install training deps (inside your venv)

```bash
pip install torch datasets transformers peft trl accelerate
```

## 3) Train LoRA adapter

```bash
python3 scripts/train_lora.py \
  --base-model Qwen/Qwen2.5-3B-Instruct \
  --train-jsonl training_data/sft_train.jsonl \
  --val-jsonl training_data/sft_val.jsonl \
  --out-dir artifacts/lora-diary \
  --epochs 2 \
  --batch-size 1 \
  --grad-accum 16
```

Adapter output dir:
- `artifacts/lora-diary/adapter`

## 4) Quick evaluation

```bash
python3 scripts/eval_lora.py \
  --base-model Qwen/Qwen2.5-3B-Instruct \
  --adapter-dir artifacts/lora-diary/adapter \
  --val-jsonl training_data/sft_val.jsonl \
  --num-samples 5
```

## Notes

- This is LoRA fine-tuning, not full-parameter training.
- Keep private data local; do not upload dataset unless you intend to.
- You can later merge/deploy this adapter to your own server model endpoint.
