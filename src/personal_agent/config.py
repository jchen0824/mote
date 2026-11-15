import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    database_url: str
    data_dir: Path
    model: str
    image: str

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        database_url = os.environ.get("DATABASE_URL", "")
        if not database_url.startswith("postgresql+asyncpg://"):
            raise ValueError("Set DATABASE_URL to a postgresql+asyncpg:// URL")
        return cls(
            database_url=database_url,
            data_dir=Path(os.getenv("AGENT_DATA_DIR", ".agent-data")).resolve(),
            model=os.getenv("OPENAI_MODEL", ""),
            image=os.getenv("SANDBOX_IMAGE", "python:3.12-slim"),
        )
