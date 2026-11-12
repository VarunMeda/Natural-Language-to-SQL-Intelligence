# Spider evaluation protocol

The official Spider 1.0 archive is downloaded from the Spider project page and stored locally under `evaluation/datasets/spider_official/spider_data/`. Spider is distributed under CC BY-SA 4.0. The authors' `evaluation.py` and `process_sql.py` are vendored under `evaluation/official_spider/` for exact-match parsing; they are not replaced by string normalization.

The default selection is exactly 100 questions from the official `dev.json`, selected with `random.Random(42).sample` and written in source-index order. `spider_subset_manifest.json` preserves source indices, questions, database IDs, and reference SQL. Each question uses its own Spider SQLite database and dynamically inspected schema; the university demo database is never used.

Run a one-question smoke evaluation:

```powershell
.\.venv\Scripts\python.exe scripts\run_evaluation.py --count 1 --strategies zero-shot few-shot cot self-correction agent --output-dir evaluation\reports\smoke_all
```

Run the full experiment sequentially and resumably:

```powershell
.\.venv\Scripts\python.exe scripts\run_evaluation.py --count 100 --seed 42
```

The runner writes `spider_checkpoint.jsonl` after every question/strategy, then produces `spider_experiment.json`, `spider_experiment.jsonl`, and `spider_experiment.csv`. If interrupted, rerun the same command; completed keys are reused. The five modes are zero-shot, few-shot, structured CoT, self-correction, and the agent workflow.

Execution accuracy compares predicted and reference denotations on the corresponding Spider database with order-insensitive row comparison. Official Spider AST parsing and exact-match evaluation are recorded separately. Invalid SQL, execution failures, correction attempts, latency, LLM calls, prompt tokens, completion tokens, and complexity are recorded per question.

The repository contains a real one-question smoke report, but no full 100-question claims are made until the resumable command completes. The local qwen2.5-coder:7b model is intentionally run sequentially to avoid GPU memory pressure.

