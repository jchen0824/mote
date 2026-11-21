"""Private memory fixture and grader; actors receive only one observation at a time."""

import asyncio
import hashlib
import json
import random
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Literal, Protocol

MEMORY_SCENARIO_VERSION = "preference-revision-v1"
MEMORY_GRADER_VERSION = "exact-ordered-headings-v1"
MemoryMode = Literal["persistent", "reset"]


# Internal fixture records use frozen dataclasses; they do not validate runtime inputs.
# Model-produced JSON is validated separately by MemoryAnswer in memory_actor.py.
@dataclass(frozen=True)
class MemoryObservation:
    phase: Literal["learn", "recall"]
    instruction: str


@dataclass(frozen=True)
class MemoryScenario:
    seed: int
    initial: tuple[str, ...]
    revised: tuple[str, ...]
    version: str = MEMORY_SCENARIO_VERSION

    @property
    def digest(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()

    @property
    def observations(self) -> tuple[MemoryObservation, ...]:
        def learn(headings: tuple[str, ...], *, revision: bool) -> MemoryObservation:
            return MemoryObservation(
                "learn",
                ("Replace my previous preference. " if revision else "Remember my preference. ")
                + "For my weekly brief, use exactly these headings in this order: "
                + json.dumps(headings)
                + ". Retain this preference for later conversations. "
                "Return an empty headings list now.",
            )

        # Both probes have identical input. Neither reveals any expected heading.
        recall = MemoryObservation(
            "recall",
            "What headings do I currently prefer for my weekly brief? Recall the exact headings "
            "in order from persistent memory. If you cannot recall them, return an empty list. "
            "Do not guess or invent a preference.",
        )
        return (
            learn(self.initial, revision=False),
            recall,
            learn(self.revised, revision=True),
            recall,
        )


def memory_scenario(seed: int = 0) -> MemoryScenario:
    # A controlled synthetic corpus makes each seed reproducible and exactly gradable.
    # This is not a whitelist for real user preferences. Corpus changes need a new version.
    vocabulary = (
        "Decisions",
        "Evidence",
        "Owners",
        "Follow-ups",
        "Risks",
        "Options",
        "Open questions",
        "Progress",
        "Dependencies",
        "Outcomes",
        "Experiments",
        "Commitments",
        "Blockers",
        "Assumptions",
        "Priorities",
        "Changes",
        "Signals",
        "Lessons",
        "Milestones",
        "Requests",
        "Context",
        "Tradeoffs",
        "Deadlines",
        "Resources",
    )
    selected = random.Random(seed).sample(vocabulary, 6)
    return MemoryScenario(seed, tuple(selected[:3]), tuple(selected[3:]))


class MemoryActor(Protocol):
    async def recall(self, observation: MemoryObservation) -> tuple[str, ...]: ...


class ReferenceMemoryActor:
    """Fixture sanity check; never a model-performance result."""

    def __init__(self) -> None:
        self.headings: tuple[str, ...] = ()

    async def recall(self, observation: MemoryObservation) -> tuple[str, ...]:
        if observation.phase == "learn":
            start = observation.instruction.index("[")
            end = observation.instruction.index("]", start) + 1
            self.headings = tuple(json.loads(observation.instruction[start:end]))
            return ()
        return self.headings


@dataclass(frozen=True)
class MemoryWake:
    index: int
    observation: MemoryObservation
    headings: tuple[str, ...]
    elapsed_seconds: float
    error: str | None = None


@dataclass(frozen=True)
class MemoryMetrics:
    retention_correct: bool
    revision_correct: bool
    stale_preference_recalled: bool
    completed_probes: int
    correct_probes: int
    total_probes: int
    accuracy: float
    reward: float


def grade_memory(
    definition: MemoryScenario,
    wakes: tuple[MemoryWake, ...],
    *,
    completed: bool,
) -> MemoryMetrics:
    # Probe positions come from the trusted fixture, not a model-provided label/score.
    answers = {w.index: w.headings for w in wakes if w.error is None and w.index in (1, 3)}
    retained = answers.get(1) == definition.initial
    revised = answers.get(3) == definition.revised
    correct = int(retained) + int(revised)
    return MemoryMetrics(
        retained,
        revised,
        answers.get(3) == definition.initial,
        len(answers),
        correct,
        2,
        correct / 2,
        float(completed and correct == 2),
    )


@dataclass(frozen=True)
class MemoryResult:
    status: Literal["completed", "failed", "budget_exhausted"]
    error: str | None
    wakes: tuple[MemoryWake, ...]
    metrics: MemoryMetrics
    elapsed_seconds: float


async def run_memory_trial(
    definition: MemoryScenario,
    actor_for_wake: Callable[[int], MemoryActor],
    *,
    max_wakes: int = 4,
    wake_timeout: float = 180,
    on_wake: Callable[[MemoryWake], None] | None = None,
) -> MemoryResult:
    from .episode import Limits

    Limits(max_wakes=max_wakes, wake_timeout_seconds=wake_timeout)
    started = time.monotonic()
    wakes: list[MemoryWake] = []
    status: Literal["completed", "failed", "budget_exhausted"] = "completed"
    error = None
    for index, observation in enumerate(definition.observations):
        if index >= max_wakes:
            status, error = "budget_exhausted", "wake_limit"
            break
        wake_start = time.monotonic()
        headings: tuple[str, ...] = ()
        try:
            headings = await asyncio.wait_for(
                actor_for_wake(index).recall(observation),
                timeout=wake_timeout,
            )
        except Exception as exc:
            status, error = "failed", type(exc).__name__
        wake = MemoryWake(index, observation, headings, time.monotonic() - wake_start, error)
        wakes.append(wake)
        if on_wake:
            on_wake(wake)
        if error:
            break
    return MemoryResult(
        status,
        error,
        tuple(wakes),
        grade_memory(definition, tuple(wakes), completed=status == "completed"),
        time.monotonic() - started,
    )
