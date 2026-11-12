from dataclasses import dataclass
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / '.env')
except ImportError:
    pass

ROOT = Path(__file__).resolve().parents[1]

@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{ROOT / 'data' / 'demo.sqlite3'}")
    llm_provider: str = os.getenv("LLM_PROVIDER", "ollama")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
    max_correction_attempts: int = int(os.getenv("MAX_CORRECTION_ATTEMPTS", "3"))
    query_timeout_seconds: int = int(os.getenv("QUERY_TIMEOUT_SECONDS", "15"))
    max_result_rows: int = int(os.getenv("MAX_RESULT_ROWS", "1000"))

settings = Settings()

