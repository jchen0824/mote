from collections.abc import Awaitable, Callable
from typing import cast

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine

from .models import Job
from .store import jobs

# One persistent personal workspace. A session-level lock serializes all writers.
WORKSPACE_LOCK = 734921012


async def run_once(engine: AsyncEngine, runner: Callable[[Job], Awaitable[str]]) -> bool:
    async with engine.connect() as connection:
        locked = await connection.scalar(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": WORKSPACE_LOCK}
        )
        await connection.commit()
        if not locked:
            return False
        try:
            # Owning the workspace lock proves any earlier running job lost its worker.
            row = (
                (
                    await connection.execute(
                        select(jobs)
                        .where(
                            jobs.c.status.in_(["queued", "running"]),
                            jobs.c.due_at <= func.now(),
                        )
                        .order_by(jobs.c.due_at, jobs.c.id)
                        .limit(1)
                        .with_for_update()
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                await connection.commit()
                return False
            job = cast(Job, dict(row))
            await connection.execute(
                update(jobs)
                .where(jobs.c.id == job["id"])
                .values(status="running", attempts=jobs.c.attempts + 1, error=None)
            )
            await connection.commit()
            try:
                result = await runner(job)
            except Exception as error:
                await connection.execute(
                    update(jobs)
                    .where(jobs.c.id == job["id"])
                    .values(status="failed", error=type(error).__name__)
                )
                await connection.commit()
                raise
            await connection.execute(
                update(jobs).where(jobs.c.id == job["id"]).values(status="completed", result=result)
            )
            await connection.commit()
            return True
        finally:
            await connection.rollback()
            await connection.execute(
                text("SELECT pg_advisory_unlock(:key)"), {"key": WORKSPACE_LOCK}
            )
            await connection.commit()
