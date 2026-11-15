import asyncio
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from .grading import Metrics, grade
from .world import Action, Observation, Record, World

Policy = Literal["reactive", "scheduled", "event-driven"]


class Actor(Protocol):
    async def act(self, observation: Observation) -> list[Action]: ...


@dataclass(frozen=True)
class Limits:
    max_wakes: int = 8
    max_actions: int = 24
    wake_timeout_seconds: float = 180

    def __post_init__(self) -> None:
        if min(
            self.max_wakes, self.max_actions, self.wake_timeout_seconds
        ) <= 0 or not math.isfinite(self.wake_timeout_seconds):
            raise ValueError("Episode limits must be positive")


@dataclass(frozen=True)
class Wake:
    observation: Observation
    trigger: str
    records: tuple[Record, ...]
    elapsed_seconds: float
    error: str | None = None


@dataclass(frozen=True)
class EpisodeResult:
    status: Literal["completed", "failed", "budget_exhausted"]
    error: str | None
    policy: Policy
    wakes: tuple[Wake, ...]
    metrics: Metrics
    elapsed_seconds: float


def wake_times(world: World, policy: Policy) -> list[int]:
    user_times = {e.at for e in world.definition.events if e.kind == "user"}
    if policy == "reactive":
        return sorted(user_times)
    if policy == "scheduled":
        return sorted(user_times | set(range(0, world.definition.end + 1, 24)))
    if policy == "event-driven":
        return sorted({e.at for e in world.definition.events})
    raise ValueError(f"Unknown policy: {policy}")


async def run_episode(
    world: World,
    actor: Actor,
    policy: Policy,
    limits: Limits = Limits(),
    on_wake: Callable[[Wake], None] | None = None,
) -> EpisodeResult:
    started = time.monotonic()
    wakes: list[Wake] = []
    since = -1
    action_count = 0
    status: Literal["completed", "failed", "budget_exhausted"] = "completed"
    error = None
    for at in wake_times(world, policy):
        if len(wakes) == limits.max_wakes:
            status, error = "budget_exhausted", "wake_limit"
            break
        world.advance(at)
        observation = world.observe(since)
        trigger = (
            "user" if any(e.at == at and e.kind == "user" for e in observation.events) else policy
        )
        wake_start = time.monotonic()
        record_start = len(world.records)
        try:
            actions = await asyncio.wait_for(actor.act(observation), limits.wake_timeout_seconds)
            if action_count + len(actions) > limits.max_actions:
                status, error = "budget_exhausted", "action_limit"
                actions = []
            for action in actions:
                world.execute(action)
            action_count += len(actions)
        except Exception as exc:
            status, error = "failed", type(exc).__name__
        records = world.records[record_start:]
        wake = Wake(observation, trigger, records, time.monotonic() - wake_start, error)
        wakes.append(wake)
        if on_wake:
            on_wake(wake)
        since = at
        if status != "completed":
            break
    world.advance(world.definition.end)
    return EpisodeResult(
        status,
        error,
        policy,
        tuple(wakes),
        grade(world.definition, world.records, completed=status == "completed"),
        time.monotonic() - started,
    )
