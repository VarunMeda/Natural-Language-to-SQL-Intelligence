import sqlite3
from pathlib import Path
from core.config import settings

def sqlite_path() -> Path:
    prefix = "sqlite:///"
    if not settings.database_url.startswith(prefix):
        raise RuntimeError("Offline helper expects sqlite:///; use SQLAlchemy integration for PostgreSQL.")
    path = Path(settings.database_url[len(prefix):])
    if not path.is_absolute(): path = Path.cwd() / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path

def connect():
    con=sqlite3.connect(sqlite_path(), timeout=settings.query_timeout_seconds)
    con.row_factory=sqlite3.Row; con.execute("PRAGMA foreign_keys = ON"); return con

