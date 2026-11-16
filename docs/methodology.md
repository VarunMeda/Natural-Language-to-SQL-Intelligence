# Methodology

All strategies receive the live schema (tables, typed columns, primary and foreign keys) and must answer with JSON `{"plan": [...], "sql": "..."}`. The model runs at temperature 0 with an 8K context window (`OLLAMA_NUM_CTX`).

| Mode | Prompt | Feedback loop | Tools |
|---|---|---|---|
| Zero-shot | Question + schema | None | None |
| Few-shot | Question + schema + 3 retrieved examples | None | None |
| Structured CoT | Question + schema + 6-step query plan (tables, joins, filters, aggregation, nesting, output) | None | None |
| Self-correction | Zero-shot, then on an execution error the error and failed SQL are sent back for repair (max 3) | Yes | None |
| SQL agent | Structured CoT with sample column values, then the same repair loop (max 3) | Yes | `inspect_schema`, `sample_values`, `execute_sql`, `correct_sql` |

**Few-shot retrieval.** For Spider runs, examples come from the official training split (`train_spider.json`), whose databases are disjoint from `dev.json`, so there is no test leakage. Similarity is computed on structure words and bigrams ("how many", "not in", "each", "most") so the examples teach SQL patterns rather than a specific schema. The demo database uses a small hand-written bank.

**Self-correction vs agent.** Both have the same retry budget, so the comparison isolates what the agent adds: a value-exploration tool that reads real distinct values from text columns (so filters use literals that exist, e.g. `'Dog'` rather than `'dog'`), the structured planning prompt, and LangGraph routing on execution feedback. The agent only reaches the database through read-only tools.

**Safety.** Every query passes the read-only validator (single `SELECT`/`WITH`/set operation, no write nodes anywhere in the sqlglot tree, only known tables) before execution, with a row cap.

**Recorded per question.** Generated SQL, provider, execution success, execution correctness, official exact match, correction iterations, LLM calls, prompt/completion tokens, latency and Spider hardness. A run stops rather than recording keyword-fallback SQL if the model becomes unavailable.
