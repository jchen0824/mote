import argparse
import asyncio
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from personal_agent.cli import timestamp
from personal_agent.store import enqueue, initialize, list_jobs, metadata, retry
from personal_agent.worker import run_once


def test_schedule_requires_explicit_timezone():
    with pytest.raises(argparse.ArgumentTypeError):
        timestamp("2026-12-01T09:00:00")
    assert timestamp("2026-12-01T09:00:00+08:00").utcoffset() == timedelta(hours=8)


@pytest.fixture
def database():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to a disposable PostgreSQL database")

    async def reset():
        engine = create_async_engine(url)
        async with engine.begin() as connection:
            await connection.run_sync(metadata.drop_all)
        await initialize(engine)
        await engine.dispose()

    asyncio.run(reset())
    yield url
    asyncio.run(reset())


@pytest.mark.integration
def test_deduplication_and_future_schedule(database):
    async def scenario():
        engine = create_async_engine(database)
        due = datetime.now(UTC) + timedelta(days=1)
        try:
            first = await enqueue(engine, "Prepare brief", due, "brief")
            assert await enqueue(engine, "Prepare brief", due, "brief") == first
            with pytest.raises(ValueError, match="different task"):
                await enqueue(engine, "Different brief", due, "brief")

            async def unexpected(job):
                pytest.fail("A future task must not execute")

            assert await run_once(engine, unexpected) is False
            assert len(await list_jobs(engine)) == 1
        finally:
            await engine.dispose()

    asyncio.run(scenario())


@pytest.mark.integration
def test_concurrent_workers_and_completed_job(database):
    async def scenario():
        engine = create_async_engine(database)
        entered = asyncio.Event()
        release = asyncio.Event()
        calls = []

        async def runner(job):
            calls.append(job["id"])
            entered.set()
            await release.wait()
            return "Verified draft"

        try:
            await enqueue(engine, "Prepare brief", datetime.now(UTC), "brief")
            first = asyncio.create_task(run_once(engine, runner))
            await asyncio.wait_for(entered.wait(), timeout=5)
            assert await run_once(engine, runner) is False
            release.set()
            assert await first is True
            assert await run_once(engine, runner) is False
            assert len(calls) == 1
            row = (await list_jobs(engine))[0]
            assert row["result"] == "Verified draft"
            assert row["status"] == "completed"
        finally:
            release.set()
            await engine.dispose()

    asyncio.run(scenario())


@pytest.mark.integration
def test_failed_job_requires_retry(database):
    async def scenario():
        engine = create_async_engine(database)

        async def fail(job):
            raise RuntimeError("Sensitive payload must not be persisted as error text")

        async def succeed(job):
            return "Recovered"

        try:
            job_id = await enqueue(engine, "Prepare brief", datetime.now(UTC), "brief")
            with pytest.raises(RuntimeError):
                await run_once(engine, fail)
            row = (await list_jobs(engine))[0]
            assert row["error"] == "RuntimeError"
            assert await run_once(engine, succeed) is False
            await retry(engine, job_id)
            assert await run_once(engine, succeed) is True
            assert (await list_jobs(engine))[0]["attempts"] == 2
            with pytest.raises(ValueError):
                await retry(engine, job_id)
        finally:
            await engine.dispose()

    asyncio.run(scenario())


@pytest.mark.integration
def test_process_crash_releases_lock_and_recovers_job(database):
    async def seed():
        engine = create_async_engine(database)
        await enqueue(engine, "Prepare brief", datetime.now(UTC), "brief")
        await engine.dispose()

    asyncio.run(seed())
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import asyncio, os
from sqlalchemy.ext.asyncio import create_async_engine
from personal_agent.worker import run_once
async def crash(job):
    os._exit(23)
asyncio.run(run_once(create_async_engine(os.environ['TEST_DATABASE_URL']), crash))
""",
        ],
        env={**os.environ, "TEST_DATABASE_URL": database},
        timeout=20,
        check=False,
    )
    assert result.returncode == 23

    async def recover():
        engine = create_async_engine(database)

        async def runner(job):
            return "Recovered after process exit"

        try:
            assert (await list_jobs(engine))[0]["status"] == "running"
            assert await run_once(engine, runner) is True
            row = (await list_jobs(engine))[0]
            assert row["status"] == "completed"
            assert row["attempts"] == 2
        finally:
            await engine.dispose()

    asyncio.run(recover())


@pytest.mark.integration
def test_sdk_conversation_survives_new_engine(database):
    from agents.extensions.memory import SQLAlchemySession

    async def scenario():
        engine = create_async_engine(database)
        session = SQLAlchemySession("storage-test", engine=engine, create_tables=True)
        await session.clear_session()
        await session.add_items([{"role": "user", "content": "I prefer concise updates."}])
        await engine.dispose()
        replacement = create_async_engine(database)
        try:
            restored = SQLAlchemySession("storage-test", engine=replacement)
            items = await restored.get_items()
            assert items[0]["content"] == "I prefer concise updates."
            await restored.clear_session()
        finally:
            await replacement.dispose()

    asyncio.run(scenario())
