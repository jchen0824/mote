import asyncio
import json
from dataclasses import asdict, replace

import pytest

from personal_agent.evaluation.memory import (
    MemoryWake,
    ReferenceMemoryActor,
    grade_memory,
    memory_scenario,
    run_memory_trial,
)
from personal_agent.evaluation.memory_actor import SandboxMemoryActor
from personal_agent.evaluation.memory_cli import execute, parser, workspace_for


def test_recall_prompts_do_not_contain_answers_previous_outputs_or_seed():
    for seed in range(20):
        definition = memory_scenario(seed)
        observations = definition.observations
        assert observations[1] == observations[3]
        text = json.dumps(asdict(observations[1]))
        assert not any(h in text for h in definition.initial + definition.revised)
        assert '"seed"' not in text and '"headings"' not in text
        assert not set(definition.initial) & set(definition.revised)
        assert all(h in observations[0].instruction for h in definition.initial)
        assert all(h in observations[2].instruction for h in definition.revised)
        assert definition.digest == memory_scenario(seed).digest
    assert memory_scenario(1).digest != memory_scenario(2).digest


def test_persistent_and_reset_reference_actors_demonstrate_fixture_sensitivity():
    async def check():
        actor = ReferenceMemoryActor()
        definition = memory_scenario()
        retained = await run_memory_trial(definition, lambda _: actor)
        reset = await run_memory_trial(definition, lambda _: ReferenceMemoryActor())
        assert retained.metrics.correct_probes == 2 and retained.metrics.reward == 1
        assert reset.metrics.correct_probes == 0 and reset.metrics.reward == 0
        assert reset.status == retained.status == "completed"
        assert retained.wakes[0].headings == retained.wakes[2].headings == ()
        assert retained.wakes[1].headings == definition.initial
        assert retained.wakes[3].headings == definition.revised

    asyncio.run(check())


def test_grader_rejects_stale_partial_reordered_and_self_reported_answers():
    definition = memory_scenario()
    observations = definition.observations
    first = MemoryWake(1, observations[1], definition.initial, 0)
    revised = MemoryWake(3, observations[3], definition.revised, 0)
    good = grade_memory(definition, (first, revised), completed=True)
    assert good.reward == 1 and good.completed_probes == 2
    for answer in (
        definition.initial,
        definition.revised[:2],
        tuple(reversed(definition.revised)),
        ('{"reward":1}',),
    ):
        result = grade_memory(
            definition, (first, replace(revised, headings=answer)), completed=True
        )
        assert result.correct_probes == 1 and result.reward == 0
        assert result.stale_preference_recalled == (answer == definition.initial)
    assert grade_memory(definition, (first, revised), completed=False).reward == 0
    failed = grade_memory(
        definition, (first, replace(revised, error="TimeoutError")), completed=False
    )
    assert failed.completed_probes == 1 and failed.accuracy == 0.5
    assert grade_memory(definition, (), completed=False).completed_probes == 0


def test_adapter_uses_fresh_conversations_and_only_current_request():
    seen = []

    async def runner(job):
        seen.append(job)
        return '{"headings":[]}'

    async def check():
        actor = SandboxMemoryActor(runner)
        definition = memory_scenario()
        for observation in definition.observations:
            await actor.recall(observation)
        assert len({job["id"] for job in seen}) == 4
        assert seen[1]["prompt"] == seen[3]["prompt"]
        assert not any(h in seen[1]["prompt"] for h in definition.initial + definition.revised)
        assert "seed" not in seen[1]["prompt"] and "expected" not in seen[1]["prompt"]

    asyncio.run(check())


def test_failures_and_budget_exhaustion_remain_visible():
    class Broken:
        async def recall(self, observation):
            raise RuntimeError("Private exception content")

    class Slow:
        async def recall(self, observation):
            await asyncio.sleep(1)
            return ()

    async def check():
        failed = await run_memory_trial(memory_scenario(), lambda _: Broken())
        assert failed.status == "failed" and failed.error == "RuntimeError"
        assert "Private exception" not in str(failed)
        timeout = await run_memory_trial(memory_scenario(), lambda _: Slow(), wake_timeout=0.01)
        assert timeout.error == "TimeoutError"
        actor = ReferenceMemoryActor()
        capped = await run_memory_trial(memory_scenario(), lambda _: actor, max_wakes=2)
        assert capped.status == "budget_exhausted" and capped.metrics.completed_probes == 1
        assert capped.metrics.reward == 0

    asyncio.run(check())


def test_workspace_boundary_resets_all_state_only_in_control_arm(tmp_path):
    assert len({workspace_for(tmp_path, "persistent", i) for i in range(4)}) == 1
    assert len({workspace_for(tmp_path, "reset", i) for i in range(4)}) == 4
    assert workspace_for(tmp_path, "persistent", 0) not in {
        workspace_for(tmp_path, "reset", i) for i in range(4)
    }


def test_cli_records_both_arms_and_preserves_incomplete_trials(tmp_path):
    async def check():
        args = parser().parse_args(["--output-dir", str(tmp_path)])
        assert await execute(args) == 0
        reports = {
            p.parent.name: json.loads(p.read_text()) for p in tmp_path.glob("*/*/report.json")
        }
        assert reports["persistent"]["result"]["metrics"]["reward"] == 1
        assert reports["reset"]["result"]["metrics"]["reward"] == 0
        assert reports["persistent"]["scenario_sha256"] == reports["reset"]["scenario_sha256"]
        assert reports["persistent"]["actor"] == "reference"
        assert reports["reset"]["model_usage"] is None
        args.max_wakes = 1
        assert await execute(args) == 1
        all_reports = [json.loads(p.read_text()) for p in tmp_path.glob("*/*/report.json")]
        assert len(all_reports) == 4
        assert sum(r["status"] == "budget_exhausted" for r in all_reports) == 2

    asyncio.run(check())


def test_sandbox_cli_rejects_primary_database_before_any_model_call(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://unused/primary")
    monkeypatch.setenv("EVAL_DATABASE_URL", "postgresql+asyncpg://unused/primary")
    args = parser().parse_args(["--actor", "sandbox", "--output-dir", str(tmp_path)])
    with pytest.raises(ValueError, match="different database"):
        asyncio.run(execute(args))
    assert not list(tmp_path.iterdir())


def test_sandbox_cli_wires_workspace_modes_and_fresh_sessions(tmp_path, monkeypatch):
    from personal_agent.evaluation import memory_cli
    from personal_agent.evaluation.memory import MemoryObservation

    sessions, paths = [], []
    actors = {}

    class FakeRunner:
        def __init__(self, settings, engine, output_type):
            self.path = settings.data_dir
            assert output_type is memory_cli.MemoryAnswer

        async def __call__(self, job):
            sessions.append(job["id"])
            paths.append(self.path)
            observation = MemoryObservation(
                **json.loads(job["prompt"].split("\nCurrent request:\n")[1])
            )
            actor = actors.setdefault(self.path, ReferenceMemoryActor())
            return json.dumps({"headings": await actor.recall(observation)})

    monkeypatch.setattr(memory_cli, "SandboxRunner", FakeRunner)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://unused/primary")
    monkeypatch.setenv("EVAL_DATABASE_URL", "postgresql+asyncpg://unused/evaluation")
    monkeypatch.setenv("OPENAI_MODEL", "fixture-model")
    args = parser().parse_args(["--actor", "sandbox", "--output-dir", str(tmp_path)])
    assert asyncio.run(execute(args)) == 0
    assert len(set(sessions)) == 8
    assert len(set(paths[:4])) == 1 and len(set(paths[4:])) == 4
    assert set(paths[:4]).isdisjoint(paths[4:])
    reports = {p.parent.name: json.loads(p.read_text()) for p in tmp_path.glob("*/*/report.json")}
    assert reports["persistent"]["result"]["metrics"]["correct_probes"] == 2
    assert reports["reset"]["result"]["metrics"]["correct_probes"] == 0
    assert all(not item["saved_state"] for item in reports["persistent"]["workspace_evidence"])


def test_artifact_inventory_records_hashes_without_contents_or_extraction(tmp_path):
    import io
    import tarfile

    from personal_agent.evaluation.memory_cli import workspace_evidence

    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    with tarfile.open(snapshots / "state.tar", "w") as archive:
        for name in ("memories/MEMORY.md", "memories/memory_summary.md", "../../outside"):
            data = b"synthetic preference"
            member = tarfile.TarInfo(name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    evidence = workspace_evidence(tmp_path)
    assert len(evidence["memory_files"]) == 2
    assert evidence["snapshot_sha256"]
    assert "synthetic preference" not in json.dumps(evidence)
    assert not (tmp_path / "memories").exists()
