"""Compare persistent workspace memory with a fresh workspace at every wake."""

import argparse
import asyncio
import hashlib
import os
import tarfile
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from personal_agent.config import Settings
from personal_agent.runtime import SandboxRunner

from .cli import provenance, save_report
from .episode import Limits
from .memory import (
    MEMORY_GRADER_VERSION,
    MemoryActor,
    MemoryMode,
    MemoryWake,
    ReferenceMemoryActor,
    memory_scenario,
    run_memory_trial,
)
from .memory_actor import MEMORY_PROMPT_VERSION, MemoryAnswer, SandboxMemoryActor

MODES: tuple[MemoryMode, ...] = ("persistent", "reset")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Evaluate preference retention and revision")
    result.add_argument("--actor", choices=("reference", "sandbox"), default="reference")
    result.add_argument("--backend", choices=("local", "hud"), default="local")
    result.add_argument("--memory", choices=("both", *MODES), default="both")
    result.add_argument("--seed", type=int, default=0)
    result.add_argument("--max-wakes", type=int, default=4)
    result.add_argument("--wake-timeout", type=float, default=180)
    result.add_argument("--output-dir", type=Path, default=Path("eval-results"))
    return result


def workspace_for(directory: Path, mode: MemoryMode, index: int) -> Path:
    if mode == "persistent":
        return directory / "workspace"
    return directory / f"wake-{index}" / "workspace"


def workspace_evidence(directory: Path) -> dict[str, Any]:
    """Inventory persisted artifacts without extracting or publishing their contents."""
    evidence: dict[str, Any] = {
        "saved_state": (directory / "sandbox.json").exists(),
        "memory_files": [],
        "snapshot_sha256": None,
    }
    snapshots = list((directory / "snapshots").rglob("*.tar"))
    if not snapshots:
        return evidence
    latest = max(snapshots, key=lambda path: path.stat().st_mtime_ns)
    evidence["snapshot_sha256"] = hashlib.sha256(latest.read_bytes()).hexdigest()
    with tarfile.open(latest) as archive:
        for member in archive.getmembers():
            if member.isfile() and member.name in {
                "memories/MEMORY.md",
                "memories/memory_summary.md",
            }:
                stream = archive.extractfile(member)
                if stream:
                    content = stream.read()
                    evidence["memory_files"].append(
                        {
                            "name": member.name,
                            "bytes": len(content),
                            "sha256": hashlib.sha256(content).hexdigest(),
                        }
                    )
    return evidence


async def execute(args: argparse.Namespace) -> int:
    Limits(max_wakes=args.max_wakes, wake_timeout_seconds=args.wake_timeout)
    definition = memory_scenario(args.seed)
    modes = MODES if args.memory == "both" else tuple(m for m in MODES if m == args.memory)
    settings: Settings | None = None
    if args.actor == "sandbox":
        from agents import set_tracing_disabled

        set_tracing_disabled(True)
        settings = Settings.from_env()
        url = os.getenv("EVAL_DATABASE_URL", "")
        if not url.startswith("postgresql+asyncpg://"):
            raise ValueError("Set EVAL_DATABASE_URL to a separate disposable PostgreSQL database")
        if make_url(url).database == make_url(settings.database_url).database:
            raise ValueError("EVAL_DATABASE_URL must use a different database from DATABASE_URL")
        settings = replace(settings, database_url=url)
    root = args.output_dir.resolve() / str(uuid4())
    root.mkdir(parents=True, mode=0o700)
    meta = provenance()
    exit_code = 0
    for mode in modes:
        directory = root / mode
        directory.mkdir(mode=0o700)
        engine = create_async_engine(settings.database_url) if settings else None
        reference = ReferenceMemoryActor()

        def actor_for_wake(
            index: int,
            engine: AsyncEngine | None = engine,
            directory: Path = directory,
            mode: MemoryMode = mode,
            reference: ReferenceMemoryActor = reference,
        ) -> MemoryActor:
            if settings and engine:
                return SandboxMemoryActor(
                    SandboxRunner(
                        replace(settings, data_dir=workspace_for(directory, mode, index)),
                        engine,
                        output_type=MemoryAnswer,
                    )
                )
            return reference if mode == "persistent" else ReferenceMemoryActor()

        report: dict[str, Any] = {
            "status": "running",
            "provenance": meta,
            "scenario": "preference-revision",
            "scenario_version": definition.version,
            "scenario_sha256": definition.digest,
            "seed": args.seed,
            "grader": MEMORY_GRADER_VERSION,
            "actor_prompt": MEMORY_PROMPT_VERSION,
            "actor": args.actor,
            "backend": args.backend,
            "model": settings.model if settings else None,
            "memory_mode": mode,
            "initial_state": "fresh workspace and unique conversations",
            "isolation": "Reset mode clears all workspace files between wakes.",
            "limits": {
                "max_wakes": args.max_wakes,
                "wake_timeout_seconds": args.wake_timeout,
                "task_max_turns": 20,
                "consolidation_max_turns": 20,
            },
            "model_usage": None,
            "usage_note": "Task and memory token/cost totals are not instrumented.",
            "wakes": [],
            "workspace_evidence": [],
        }
        path = directory / "report.json"
        save_report(path, report)

        def checkpoint(
            wake: MemoryWake,
            report: dict[str, Any] = report,
            path: Path = path,
            directory: Path = directory,
            mode: MemoryMode = mode,
        ) -> None:
            report["wakes"].append(asdict(wake))
            if settings:
                report["workspace_evidence"].append(
                    {
                        "wake": wake.index,
                        **workspace_evidence(workspace_for(directory, mode, wake.index)),
                    }
                )
            save_report(path, report)
            print(
                f"  wake={wake.index} phase={wake.observation.phase} "
                f"elapsed={wake.elapsed_seconds:.1f}s error={wake.error}",
                flush=True,
            )

        print(f"Starting {mode} / {args.actor} / {args.backend}", flush=True)
        try:
            if args.backend == "hud":
                from .hud_adapter import run_memory_with_hud

                result, hud_reward = await run_memory_with_hud(
                    definition,
                    actor_for_wake,
                    directory / "hud",
                    max_wakes=args.max_wakes,
                    wake_timeout=args.wake_timeout,
                    on_wake=checkpoint,
                )
                report["hud_reward"] = hud_reward
            else:
                result = await run_memory_trial(
                    definition,
                    actor_for_wake,
                    max_wakes=args.max_wakes,
                    wake_timeout=args.wake_timeout,
                    on_wake=checkpoint,
                )
            report["status"] = result.status
            report["result"] = asdict(result)
            report.pop("wakes")
            exit_code = max(exit_code, int(result.status != "completed"))
            print(f"{mode}: {result.status}, correct={result.metrics.correct_probes}/2", flush=True)
        except Exception as exc:
            report["status"], report["error"] = "failed", type(exc).__name__
            exit_code = 1
        finally:
            # The private fixture is persisted for reproducibility, never passed to the actor.
            report["expected"] = {"initial": definition.initial, "revised": definition.revised}
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
