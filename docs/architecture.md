# Architecture

The provider-neutral core discovers live SQLite metadata and exposes the same schema contract needed by SQLAlchemy/PostgreSQL. Generators return SQL plus a concise plan. The validator enforces one read-only SELECT/WITH statement and checks tables. The bounded executor applies a row cap and structured errors. Self-correction records every attempt; the agent uses explicit schema and execution tools only.

