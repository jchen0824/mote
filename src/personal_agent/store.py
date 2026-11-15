from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, Text, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from .models import Job

metadata = MetaData()
jobs = Table(
    "agent_jobs",
    metadata,
    Column("id", String, primary_key=True),
    Column("request_key", String, nullable=False, unique=True),
    Column("prompt", Text, nullable=False),
    Column("due_at", DateTime(timezone=True), nullable=False),
    Column("status", String, nullable=False),
    Column("attempts", Integer, nullable=False, default=0),
    Column("result", Text),
    Column("error", Text),
)


async def initialize(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(metadata.create_all)


async def enqueue(engine: AsyncEngine, prompt: str, due_at: datetime, key: str) -> str:
    if not prompt.strip():
        raise ValueError("Task prompt must contain text")
    if due_at.tzinfo is None:
        raise ValueError("The scheduled time must include a timezone")
    async with engine.begin() as connection:
        await connection.execute(
            insert(jobs)
            .values(
                id=str(uuid4()),
                request_key=key,
                prompt=prompt,
                due_at=due_at,
                status="queued",
                attempts=0,
            )
            .on_conflict_do_nothing(index_elements=[jobs.c.request_key])
        )
        row = (
            (await connection.execute(select(jobs).where(jobs.c.request_key == key)))
            .mappings()
            .one()
        )
        if row["prompt"] != prompt or row["due_at"] != due_at:
            raise ValueError("Request key already belongs to a different task or time")
        return row["id"]


async def list_jobs(engine: AsyncEngine) -> list[Job]:
    async with engine.connect() as connection:
        rows = await connection.execute(select(jobs).order_by(jobs.c.due_at))
        return [cast(Job, dict(row)) for row in rows.mappings()]


async def retry(engine: AsyncEngine, job_id: str) -> None:
    async with engine.begin() as connection:
        result = await connection.execute(
            update(jobs)
            .where(jobs.c.id == job_id, jobs.c.status == "failed")
            .values(status="queued", error=None, due_at=datetime.now(UTC))
        )
        if result.rowcount != 1:
            raise ValueError("Retry requires an existing failed job")
