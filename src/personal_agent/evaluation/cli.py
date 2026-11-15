import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from personal_agent.config import Settings
from personal_agent.runtime import SandboxRunner

from .episode import Actor, Limits, Policy, Wake, run_episode
from .grading import GRADER_VERSION
from .reference import ReferenceActor
from .sandbox_actor import ACTOR_PROMPT_VERSION, ActionEnvelope, SandboxActor
from .world import World, scenario

POLICIES: tuple[Policy, ...] = ("reactive", "scheduled", "event-driven")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Run synthetic personal-agent episodes locally")
    result.add_argument("--actor", choices=("reference", "sandbox"), default="reference")
    result.add_argument("--backend", choices=("local", "hud"), default="local")
    result.add_argument("--policy", choices=("all", *POLICIES), default="all")
    result.add_argument(
        "--scenario", choices=("meeting-moved", "quiet-week"), default="meeting-moved"
    )
    result.add_argument("--seed", type=int, default=0)
    result.add_argument("--max-wakes", type=int, default=8)
    result.add_argument("--max-actions", type=int, default=24)
    result.add_argument("--wake-timeout", type=float, default=180)
    result.add_argument("--output-dir", type=Path, default=Path("eval-results"))
    return result


def provenance() -> dict[str, Any]:
    def git(*args: str) -> str | None:
        result = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
        return result.stdout.strip() if result.returncode == 0 else None

    package = Path(__file__).parents[1]
    source = hashlib.sha256()
    for path in sorted(package.rglob("*.py")):
        source.update(path.relative_to(package).as_posix().encode())
        source.update(path.read_bytes())
    lock = Path("uv.lock")
    return {
        "git_commit": git("rev-parse", "HEAD"),
        "git_status": git("status", "--porcelain"),
        "source_sha256": source.hexdigest(),
        "lockfile_sha256": hashlib.sha256(lock.read_bytes()).hexdigest() if lock.exists() else None,
        "python": sys.version.split()[0],
        "agents_sdk": importlib.metadata.version("openai-agents"),
    }


def save_report(path: Path, report: dict[str, Any]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2) + "\n")
    temporary.chmod(0o600)
    temporary.replace(path)


async def execute(args: argparse.Namespace) -> int:
    limits = Limits(args.max_wakes, args.max_actions, args.wake_timeout)
    definition = scenario(args.seed, args.scenario)
    policies = POLICIES if args.policy == "all" else tuple(p for p in POLICIES if p == args.policy)
    root = args.output_dir.resolve() / str(uuid4())
    root.mkdir(parents=True, mode=0o700)
    settings: Settings | None = None
    if args.actor == "sandbox":
        from agents import set_tracing_disabled

        # Includes the SDK's separate memory extraction/consolidation runs.
        set_tracing_disabled(True)
        settings = Settings.from_env()
        url = os.getenv("EVAL_DATABASE_URL", "")
        if not url.startswith("postgresql+asyncpg://"):
            raise ValueError("Set EVAL_DATABASE_URL to a separate disposable PostgreSQL database")
        if make_url(url).database == make_url(settings.database_url).database:
            raise ValueError("EVAL_DATABASE_URL must use a different database from DATABASE_URL")
        settings = replace(settings, database_url=url)
    meta = provenance()
    exit_code = 0
    for policy in policies:
        directory = root / policy
        directory.mkdir(mode=0o700)
        engine = None
        actor: Actor
        if settings:
            engine = create_async_engine(settings.database_url)
            actor = SandboxActor(
                SandboxRunner(
                    replace(settings, data_dir=directory / "workspace"),
                    engine,
                    output_type=ActionEnvelope,
                )
            )
        else:
            actor = ReferenceActor()
        report: dict[str, Any] = {
            "provenance": meta,
            "scenario": definition.name,
            "scenario_version": definition.version,
            "scenario_sha256": definition.digest,
            "seed": args.seed,
            "grader": GRADER_VERSION,
            "actor_prompt": ACTOR_PROMPT_VERSION,
            "actor": args.actor,
            "model": settings.model if settings else None,
            "backend": args.backend,
            "policy": policy,
            "limits": asdict(limits),
            "model_usage": None,
            "usage_note": "Task and memory model tokens/cost are not yet instrumented.",
        }
        world = World(definition)
        path = directory / "report.json"
        report["status"] = "running"
        report["wakes"] = []
        save_report(path, report)

        def checkpoint(wake: Wake, report: dict[str, Any] = report, path: Path = path) -> None:
            report["wakes"].append(asdict(wake))
            save_report(path, report)
            print(
                f"  hour={wake.observation.now} actions={len(wake.records)} "
                f"elapsed={wake.elapsed_seconds:.1f}s error={wake.error}",
                flush=True,
            )

        print(f"Starting {policy} / {args.actor} / {args.backend}", flush=True)
        try:
            if args.backend == "hud":
                from .hud_adapter import run_with_hud

                result, hud_reward = await run_with_hud(
                    world, actor, policy, limits, directory / "hud", on_wake=checkpoint
                )
                report["hud_reward"] = hud_reward
            else:
                result = await run_episode(world, actor, policy, limits, on_wake=checkpoint)
            report["result"] = asdict(result)
            report["status"] = result.status
            report.pop("wakes")
            exit_code = max(exit_code, int(result.status != "completed"))
            print(
                f"{policy}: {result.status}, reward={result.metrics.reward}, "
                f"wakes={len(result.wakes)}"
            )
        except Exception as exc:
            report["error"] = type(exc).__name__
            report["status"] = "failed"
            exit_code = 1
            print(f"{policy}: failed ({type(exc).__name__})")
        finally:
            report["ledger"] = [asdict(record) for record in world.records]
            save_report(path, report)
            if engine:
                await engine.dispose()
    print(f"Reports: {root}")
    return exit_code


def main() -> None:
    try:
        raise SystemExit(asyncio.run(execute(parser().parse_args())))
    except ValueError as error:
        raise SystemExit(str(error)) from error
