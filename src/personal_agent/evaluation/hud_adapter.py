"""Local HUD bridge. The trusted episode driver owns state; actor output is never a grade."""

import asyncio
import json
import os
from collections.abc import AsyncGenerator, Callable
from dataclasses import asdict
from pathlib import Path

from .episode import Actor, EpisodeResult, Limits, Policy, Wake, run_episode
from .grading import grade
from .world import World


async def run_with_hud(
    world: World,
    actor: Actor,
    policy: Policy,
    limits: Limits,
    trace_dir: Path,
    on_wake: Callable[[Wake], None] | None = None,
) -> tuple[EpisodeResult, float]:
    # Set before importing HUD, including when credentials exist on the host.
    os.environ["HUD_TELEMETRY_ENABLED"] = "0"
    os.environ["HUD_CLI_ANALYTICS_ENABLED"] = "0"
    resolved_trace_dir = str(await asyncio.to_thread(trace_dir.resolve))
    os.environ["HUD_TELEMETRY_LOCAL_DIR"] = resolved_trace_dir
    from hud import Environment, LocalRuntime, Run
    from hud.agents.base import Agent
    from hud.agents.types import AgentConfig, Step
    from hud.settings import settings

    settings.telemetry_enabled = False
    settings.cli_analytics_enabled = False
    settings.telemetry_local_dir = resolved_trace_dir
    env = Environment(name="personal-week", version="0.1.0")
    completed: list[EpisodeResult] = []

    @env.template()
    async def week() -> AsyncGenerator[str | float, str]:
        yield "Run the personal-agent episode through the trusted local driver."
        # Ignore the submitted answer: grade only the authoritative action ledger.
        yield grade(
            world.definition,
            world.records,
            completed=bool(completed and completed[0].status == "completed"),
        ).reward

    class EpisodeHarness(Agent[AgentConfig]):
        async def __call__(self, run: Run) -> None:
            def record(wake: Wake) -> None:
                # These are harness events, not fabricated model-level traces.
                run.record(Step(source="system", extra={"episode_wake": asdict(wake)}))
                if on_wake:
                    on_wake(wake)

            result = await run_episode(world, actor, policy, limits, on_wake=record)
            completed.append(result)
            run.trace.content = json.dumps(asdict(result.metrics))

    job = await week().run(EpisodeHarness(), runtime=LocalRuntime(env))
    if job.errors or len(completed) != 1:
        raise RuntimeError("HUD local rollout failed; inspect the local trace")
    return completed[0], float(job.reward)
