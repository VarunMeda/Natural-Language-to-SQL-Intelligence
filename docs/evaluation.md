# Spider evaluation protocol

## Data

The official Spider 1.0 archive is downloaded from the [Spider project page](https://yale-lily.github.io/spider) and extracted to `evaluation/datasets/spider_official/spider_data/` (`dev.json`, `train_spider.json`, `tables.json`, `database/`). Spider is distributed under CC BY-SA 4.0. The dataset is git-ignored.

- **Test questions:** 100 questions from `dev.json`, chosen with `random.Random(42).sample` and stored in source-index order. `spider_subset_manifest.json` records each question's source index, text, database ID and reference SQL.
- **Few-shot examples:** retrieved only from `train_spider.json`. Spider's training and dev splits use different databases, so no test database or answer appears in a prompt.
- Each question runs against its own Spider SQLite database, with its schema inspected at run time. The university demo database is never used.

## Modes

| Mode | Prompt | Repair loop | Tools |
|---|---|---|---|
| Zero-shot | Question + schema | No | None |
| Few-shot | + 3 retrieved training examples | No | None |
| CoT | + 6-step query plan | No | None |
| Self-correction | Zero-shot, then error-driven repair | Up to 3 | None |
| Agent | CoT + sample column values, then repair | Up to 3 | `inspect_schema`, `sample_values`, `execute_sql`, `correct_sql` |

Self-correction and the agent share the same retry budget, so their comparison isolates what the agent adds. Model: `qwen2.5-coder:7b` via Ollama, temperature 0, 8,192-token context, 1,024-token reply cap.

## Metrics

| Metric | Definition |
|---|---|
| Execution accuracy | Predicted and reference queries return the same rows on the question's database (order-insensitive). |
| Exact match | Spider's official evaluator (`evaluation/official_spider/`, the authors' `evaluation.py` and `process_sql.py`) compares query structure. |
| Average correction iterations | Mean repair rounds per question (0 for modes without a repair loop). |
| Execution failure rate | Share of final queries that errored. |
| Invalid SQL rate | Share whose final error is a validation failure (empty SQL, unsafe statement, unknown table) or a SQL parse error. |
| Exact-match parse errors | Queries the 2018 Spider parser could not read (see Limitations). |
| Cost | LLM calls, prompt and completion tokens, latency per question. |

Results are also broken down by Spider's difficulty label (easy, medium, hard, extra).

## Running

```powershell
python scripts\run_evaluation.py --count 1 --output-dir evaluation\reports\smoke
python scripts\run_evaluation.py --count 100 --seed 42
python scripts\rescore_exact_match.py
```

- The runner appends to `spider_checkpoint.jsonl` after every question and mode, then writes `spider_experiment.json`, `.jsonl` and `.csv`. Rerunning the same command resumes from the checkpoint.
- Runs are sequential to avoid GPU memory pressure: about 1–2 hours for 500 runs on a GPU.
- If Ollama is unreachable, the run **stops** instead of recording keyword-fallback SQL. A reply that contains no usable SQL is scored as invalid output, not as an outage.
- `rescore_exact_match.py` recomputes exact match from the saved SQL without calling the model.

## Exact-match normalisation

The 2018 Spider parser rejects some valid SQLite. Before scoring, a copy of the predicted SQL is rewritten so it can be parsed: column aliases used in `ORDER BY`, `HAVING` or `GROUP BY` are replaced by the expression they name, then removed; `<>` becomes `!=`; table aliases get an explicit `AS`. The meaning is unchanged, and the SQL that is executed is never modified. The scorer tries the original SQL first, then this rewrite, then a simpler legacy normalisation; if none parses, the question counts as no match and is recorded with `official_error`.

## Results

100 questions × 5 modes = 500 runs, completed 17 November 2026. Report: `evaluation/reports/spider_experiment.json`.

| Mode | Execution acc. | Exact match | Avg. corrections | Errored | Parse errors |
|---|---|---|---|---|---|
| Zero-shot | 61% | 40% | 0 | 16% | 14 |
| Few-shot | 65% | 54% | 0 | 12% | 13 |
| CoT | 40% | 18% | 0 | 21% | 11 |
| Self-correction | 63% | 40% | 0.28 | 8% | 12 |
| Agent | 42% | 18% | 0.36 | 12% | 10 |

## Limitations

- 23 of the 60 parse errors are queries that ran; the other 37 did not run at all and are wrong either way. Of the 23, 8 were correct by execution. Exact match is therefore underestimated by at most about 2 points per mode; execution accuracy is unaffected. Unsupported constructs include `LEFT JOIN`, `INNER JOIN`, `IN (...)` value lists, `NOT EXISTS`, CTEs and `UNION ALL`.
- Execution accuracy compares unordered rows, so a wrong `ORDER BY` is not penalised.
- When a wrong query and the reference both return no rows, execution accuracy counts a match.
- With 100 questions, differences of 2–3 points between modes are within noise.
