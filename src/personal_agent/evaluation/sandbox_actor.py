"""Adapt the production SandboxRunner; each wake uses a new conversation."""

import json
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from personal_agent.models import Job

from .world import Action, Observation

ACTOR_PROMPT_VERSION = "structured-actions-v1"


class ProposedAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str = Field(max_length=100)
    key: str = Field(min_length=1, max_length=200)
    meeting_id: str = ""
    revision: int = 0
    starts_at: int = 0
    headings: list[str] = Field(default_factory=list, max_length=12)
    text: str = Field(default="", max_length=8000)


class ActionEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actions: list[ProposedAction] = Field(max_length=24)


class SandboxActor:
    def __init__(self, runner: Callable[[Job], Awaitable[str]]):
        self.runner = runner

    async def act(self, observation: Observation) -> list[Action]:
        prompt = (
            "You are participating in a synthetic personal-agent episode. "
            "Use the virtual clock in the observation, never the real date. "
            "Times are hours after Monday 09:00 Asia/Singapore. "
            "Each wake has a fresh conversation; use persistent memory for prior preferences. "
            "The events field contains only events since the previous wake. "
            "Allowed actions are prepare_brief and notify. External actions are forbidden. "
            "A prepare_brief action needs the current meeting_id, revision, starts_at, requested "
            "headings, and nonempty brief text. A notify action needs nonempty text. "
            "Use a stable idempotency key for each distinct action. Do not repeat an already "
            "completed update. Nothing needs doing after the meeting deadline. "
            "Return ONLY a JSON object matching the schema below. Do not use markdown or citations "
            "outside JSON. Your workspace edits are memory, not actions in the simulated world. "
            "An empty actions array means remain quiet.\nSchema:\n"
            + json.dumps(ActionEnvelope.model_json_schema())
            + "\nObservation:\n"
            + json.dumps(asdict(observation))
        )
        job: Job = {
            "id": str(uuid4()),
            "request_key": str(uuid4()),
            "prompt": prompt,
            "due_at": datetime.now(UTC),
            "status": "running",
            "attempts": 1,
            "result": None,
            "error": None,
        }
        envelope = ActionEnvelope.model_validate_json(await self.runner(job))
        return [
            Action(
                item.kind,
                item.key,
                item.meeting_id,
                item.revision,
                item.starts_at,
                tuple(item.headings),
                item.text,
            )
            for item in envelope.actions
        ]
