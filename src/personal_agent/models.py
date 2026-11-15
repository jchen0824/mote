from datetime import datetime
from typing import Literal, TypedDict


class Job(TypedDict):
    id: str
    request_key: str
    prompt: str
    due_at: datetime
    status: Literal["queued", "running", "completed", "failed"]
    attempts: int
    result: str | None
    error: str | None
