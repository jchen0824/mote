import argparse
import asyncio
import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.ext.asyncio import create_async_engine

from .config import Settings
from .runtime import SandboxRunner
from .store import enqueue, initialize, list_jobs, retry
from .worker import run_once


def timestamp(value: str) -> datetime:
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise argparse.ArgumentTypeError(
            "Include a timezone, for example 2026-11-20T09:00:00+08:00"
        )
    return result


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Persistent personal agent")
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="Create PostgreSQL tables")
    add = commands.add_parser("enqueue", help="Schedule a task, or make it due now")
    add.add_argument("prompt")
    add.add_argument("--at", type=timestamp)
    add.add_argument("--key", help="Stable request key to deduplicate repeated submissions")
    work = commands.add_parser("work", help="Run due tasks")
    work.add_argument("--once", action="store_true")
    commands.add_parser("jobs", help="Show scheduled tasks and results")
    repeat = commands.add_parser("retry", help="Requeue a failed task")
    repeat.add_argument("job_id")
    return result


async def execute(args: argparse.Namespace) -> None:
    settings = Settings.from_env()
    engine = create_async_engine(settings.database_url)
    try:
        if args.command == "init":
            await initialize(engine)
            print("Database initialized")
        elif args.command == "enqueue":
            due_at = args.at or datetime.now(UTC)
            print(await enqueue(engine, args.prompt, due_at, args.key or str(uuid4())))
        elif args.command == "jobs":
            print(json.dumps(await list_jobs(engine), default=str, indent=2))
        elif args.command == "retry":
            await retry(engine, args.job_id)
            print("Task queued")
        elif args.command == "work":
            runner = SandboxRunner(settings, engine)
            while True:
                worked = await run_once(engine, runner)
                if args.once:
                    print("Task completed" if worked else "No task available")
                    break
                if not worked:
                    await asyncio.sleep(5)
    finally:
        await engine.dispose()


def main() -> None:
    args = parser().parse_args()
    try:
        asyncio.run(execute(args))
    except KeyboardInterrupt:
        print("Worker stopped")
    except ValueError as error:
        raise SystemExit(str(error)) from error
