"""The existing sandbox runtime with a narrow recall response contract."""

import json
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from personal_agent.models import Job

from .memory import MemoryObservation

MEMORY_PROMPT_VERSION = "weekly-brief-memory-v1"


class MemoryAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    headings: list[str] = Field(max_length=12)


class SandboxMemoryActor:
    def __init__(self, runner: Callable[[Job], Awaitable[str]]):
        self.runner = runner

    async def recall(self, observation: MemoryObservation) -> tuple[str, ...]:
        job: Job = {
            "id": str(uuid4()),
            "request_key": str(uuid4()),
            "prompt": (
                "This is a synthetic personal preference exercise. Each request is a new "
                "conversation with the same user. Use persistent memory when available. "
                "Return a JSON object with only a headings list, matching this schema:\n"
                + json.dumps(MemoryAnswer.model_json_schema())
                + "\nCurrent request:\n"
                + json.dumps(asdict(observation))
            ),
            "due_at": datetime.now(UTC),
            "status": "running",
            "attempts": 1,
            "result": None,
            "error": None,
        }
        return tuple(MemoryAnswer.model_validate_json(await self.runner(job)).headings)
