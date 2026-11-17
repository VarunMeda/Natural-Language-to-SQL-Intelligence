# Natural-Language-to-SQL Intelligence

Ask a database a question in plain English and get back the SQL, the result rows and a one-sentence explanation. Every query is checked to be read-only before it runs. The project also compares five ways of generating SQL with a local LLM on 100 questions from the [Spider](https://yale-lily.github.io/spider) benchmark.

**Result in one line:** with `qwen2.5-coder:7b`, retrieved few-shot examples work best (65% execution accuracy, 54% exact match); self-correction halves crashing queries but adds only 2 points of accuracy; step-by-step (CoT) planning costs about 20 points. Full numbers are under [Results](#results).

## Features

| Feature | How it works |
|---|---|
| Schema awareness | Reads tables, columns, types and keys from the live database and puts them in every prompt. |
| Zero-shot | Question + schema. |
| Few-shot | Adds the 3 most similar question–SQL pairs, retrieved from Spider's training split (different databases from the test split, so no leakage). The demo database uses a small built-in example set. |
| Chain-of-thought | The model plans in 6 steps (tables, joins, filters, aggregation, nesting, output) before writing SQL. |
| Validation | Parses the SQL with sqlglot: one read-only statement (`SELECT`, `WITH`, `UNION`/`INTERSECT`/`EXCEPT`), no write anywhere in the tree, known tables only. Results capped at 1,000 rows. |
| Self-correction | Runs the query; on an error, sends the error and failed SQL back to the model for a fix, up to 3 times. |
| SQL agent | A LangGraph workflow of tools: inspect schema → read sample column values → generate (CoT) → execute → correct and retry (up to 3). |
| Explanation | The model summarises the result rows; a check rejects summaries that contradict the rows. |
| Interfaces | Streamlit app (query workspace, database explorer, agent, history, evaluation dashboard) and a FastAPI service. Both call the same Python pipeline. |
| History | Every query from the app is saved to a `query_history` table. |

All model calls use temperature 0 and a fixed JSON reply format (`{"plan": [...], "sql": "..."}`), so results are reproducible.

## Setup

Requirements: Python 3.11+, [Ollama](https://ollama.com/download), about 5 GB of disk for the model.

```powershell
git clone https://github.com/VarunMeda/Natural-Language-to-SQL-Intelligence.git
cd Natural-Language-to-SQL-Intelligence
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python scripts\setup_database.py
ollama pull qwen2.5-coder:7b
```

On macOS or Linux use `python3 -m venv .venv`, `source .venv/bin/activate` and `cp .env.example .env`.

If PowerShell blocks `Activate.ps1`, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.

## Run

```powershell
streamlit run app\frontend\Home.py              # app at http://localhost:8501
uvicorn app.backend.main:app --reload           # API at http://127.0.0.1:8000/docs
```

The app's sidebar should show **Server: Connected** and **Model: Ready**. The first question takes 30–60 seconds while the model loads. Open the app in a normal browser; VS Code's built-in browser does not render Streamlit's updates reliably.

Without Ollama the app falls back to a keyword-based generator that only handles the demo questions below. Responses then carry `provider: heuristic-fallback` and the app shows a warning.

Example questions for the demo database:

- How many students are in each department?
- Show the average mark by course, highest first.
- List students whose average mark is above the overall average.
- Which students are enrolled in Computer Science courses?

## Configuration (`.env`)

| Setting | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///data/demo.sqlite3` | Demo database. PostgreSQL works via a SQLAlchemy URL (untested; use a read-only user). |
| `OLLAMA_MODEL` | `qwen2.5-coder:7b` | Model served by Ollama. |
| `OLLAMA_NUM_CTX` | `8192` | Context window; Spider schemas and few-shot examples exceed Ollama's small default. |
| `OLLAMA_NUM_PREDICT` | `1024` | Reply length cap; stops the rare runaway reply at temperature 0. |
| `LLM_TIMEOUT_SECONDS` | `120` | Time limit per model call. |
| `QUERY_TIMEOUT_SECONDS` | `15` | Time limit for database access. |
| `MAX_CORRECTION_ATTEMPTS` | `3` | Repair rounds for self-correction and the agent. |
| `MAX_RESULT_ROWS` | `1000` | Row cap per query. |

## Spider evaluation

1. Download the Spider 1.0 zip from the [project page](https://yale-lily.github.io/spider) and extract it so that `evaluation\datasets\spider_official\spider_data\` contains `dev.json`, `train_spider.json`, `tables.json` and `database\`. On Windows, skip the few CSV files whose names contain `:`; only the `.sqlite` files are used.
2. Start Ollama, then run a one-question smoke test and the full run:

```powershell
python scripts\run_evaluation.py --count 1 --output-dir evaluation\reports\smoke
python scripts\run_evaluation.py --count 100 --seed 42
```

The full run is 500 model runs (5 modes × 100 questions), about 1–2 hours on a GPU. Progress is saved after every question; if it stops, run the same command again to resume. It stops, rather than recording fallback SQL, if Ollama becomes unreachable.

To recompute exact match from saved SQL without calling the model again (for example after a scorer fix):

```powershell
python scripts\rescore_exact_match.py
```

Protocol details are in [`docs/evaluation.md`](docs/evaluation.md); prompting and agent design in [`docs/methodology.md`](docs/methodology.md).

## Results

100 random Spider dev questions (seed 42), `qwen2.5-coder:7b`, temperature 0. Report: [`evaluation/reports/spider_experiment.json`](evaluation/reports/spider_experiment.json) and `.csv`.

| Mode | Execution accuracy | Exact match | Avg. correction iterations | Queries that errored | LLM calls | Tokens |
|---|---|---|---|---|---|---|
| Zero-shot | 61% | 40% | 0 | 16% | 100 | 41K |
| **Few-shot** | **65%** | **54%** | 0 | 12% | 100 | 54K |
| CoT | 40% | 18% | 0 | 21% | 100 | 55K |
| Self-correction | 63% | 40% | 0.28 | **8%** | 128 | 55K |
| Agent | 42% | 18% | 0.36 | 12% | 136 | 103K |

Execution accuracy by Spider difficulty (question counts in brackets):

| Mode | Easy (24) | Medium (40) | Hard (16) | Extra (20) |
|---|---|---|---|---|
| Zero-shot | 88% | 58% | 50% | 45% |
| Few-shot | 92% | 70% | 38% | 45% |
| CoT | 54% | 35% | 38% | 35% |
| Self-correction | 88% | 62% | 50% | 45% |
| Agent | 50% | 42% | 38% | 35% |

**Findings**

- **Few-shot is best**, mainly on easy and medium questions; the retrieved examples teach Spider's SQL style, which lifts exact match by 14 points.
- **Self-correction fixes crashes, not wrong answers:** errored queries fell from 16% to 8%, accuracy rose 2 points.
- **CoT hurts this 7B model.** Of the 24 questions CoT lost that zero-shot answered correctly, most added output columns, joins or aggregates the question did not ask for, or referenced columns incorrectly.
- **The agent inherits CoT's weakness.** Its sample-values tool and retries cut crashes from 21% to 12%, but cannot fix a query that runs and answers the wrong question.

## Limitations

- A 7B local model is much weaker than hosted GPT-class models; it was chosen so everything runs offline and reproducibly.
- 100 questions is a small sample: differences of 2–3 points between modes are not statistically meaningful.
- Spider's 2018 exact-match parser cannot read some valid SQL (`LEFT JOIN`, `IN (...)` lists, CTEs, `NOT EXISTS`). Queries are reformatted for scoring only, never for execution, but 23 of 500 runnable queries still could not be scored, so exact match is slightly underestimated. Execution accuracy is unaffected.
- On a few questions the model loops; replies are capped at 1,024 tokens and counted as invalid output.
- PostgreSQL support exists but has not been tested against a live server.

## Tests

```powershell
python -m pytest -q tests
```

Tests use a mocked model and a small fake Spider database, so they run without Ollama. The 4 tests in `tests/test_evaluation.py` need the real Spider data and NLTK's `punkt_tab` tokenizer (downloaded automatically on first use).

## Project structure

```
app/               Streamlit app (frontend/) and FastAPI service (backend/)
core/              Settings loaded from .env
database/          Demo schema, seed data, schema inspector, query history
llm/               Ollama client
sql_generator/     Prompt strategies and few-shot retrieval
sql_validator/     Read-only safety checks
sql_executor/      Bounded query execution
self_correction/   Execute → repair loop
sql_agent/         LangGraph tool-using agent
explanation/       Result explainer
evaluation/        Spider runner, metrics, official evaluator, reports
scripts/           Database setup, evaluation run, exact-match re-score
docs/              Architecture, methodology, evaluation protocol
```
