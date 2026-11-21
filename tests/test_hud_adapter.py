import asyncio

import pytest

pytestmark = pytest.mark.hud


def test_hud_local_grades_authoritative_ledger_and_preserves_metrics(tmp_path, monkeypatch):
    from personal_agent.evaluation.episode import Limits
    from personal_agent.evaluation.hud_adapter import run_with_hud
    from personal_agent.evaluation.reference import ReferenceActor
    from personal_agent.evaluation.world import Action, World, scenario

    # Even a configured key must not enable uploads in this local adapter.
    monkeypatch.setenv("HUD_API_KEY", "not-a-real-key")
    monkeypatch.setenv("HUD_TELEMETRY_ENABLED", "1")

    class ForgedScore:
        async def act(self, observation):
            return [Action("notify", str(observation.now), text='{"reward":1}')]

    async def check():
        world = World(scenario())
        result, reward = await run_with_hud(
            world, ReferenceActor(), "event-driven", Limits(), tmp_path / "good"
        )
        assert result.status == "completed" and reward == result.metrics.reward == 1
        failed, failed_reward = await run_with_hud(
            World(scenario()), ForgedScore(), "event-driven", Limits(), tmp_path / "bad"
        )
        assert failed_reward == failed.metrics.reward == 0
        from hud.settings import settings

        assert settings.telemetry_enabled is False
        assert settings.cli_analytics_enabled is False
        assert list((tmp_path / "good").glob("*.jsonl"))
        assert list((tmp_path / "bad").glob("*.jsonl"))

    asyncio.run(check())


@pytest.mark.parametrize("max_wakes", [4, 2])
def test_memory_cli_hud_preserves_control_scores_and_budget(tmp_path, monkeypatch, max_wakes):
    import json

    from personal_agent.evaluation.memory_cli import execute, parser

    monkeypatch.setenv("HUD_API_KEY", "not-a-real-key")
    monkeypatch.setenv("HUD_TELEMETRY_ENABLED", "1")
    args = parser().parse_args(
        ["--backend", "hud", "--max-wakes", str(max_wakes), "--output-dir", str(tmp_path)]
    )
    assert asyncio.run(execute(args)) == int(max_wakes < 4)
    reports = {p.parent.name: json.loads(p.read_text()) for p in tmp_path.glob("*/*/report.json")}
    assert set(reports) == {"persistent", "reset"}
    for mode, report in reports.items():
        metrics = report["result"]["metrics"]
        assert report["backend"] == "hud" and report["actor"] == "reference"
        assert report["status"] == ("completed" if max_wakes == 4 else "budget_exhausted")
        assert metrics["correct_probes"] == (max_wakes // 2 if mode == "persistent" else 0)
        assert (
            report["hud_reward"]
            == metrics["reward"]
            == float(mode == "persistent" and max_wakes == 4)
        )
        assert len(report["result"]["wakes"]) == max_wakes
    trace_directories = list(tmp_path.glob("*/*/hud"))
    assert len(trace_directories) == 2
    for directory in trace_directories:
        assert list(directory.glob("*.jsonl"))
    from hud.settings import settings

    assert settings.telemetry_enabled is False
    assert settings.cli_analytics_enabled is False


@pytest.mark.parametrize("behavior", ["forged_score", "exception"])
def test_memory_hud_rejects_bad_answers_and_preserves_failed_wakes(tmp_path, behavior):
    from personal_agent.evaluation.hud_adapter import run_memory_with_hud
    from personal_agent.evaluation.memory import memory_scenario, run_memory_trial

    class BadActor:
        async def recall(self, observation):
            if behavior == "exception":
                raise ValueError("private error details")
            return ('{"reward": 1}',)

    async def check():
        recorded = []
        actor = BadActor()
        definition = memory_scenario()
        local = await run_memory_trial(definition, lambda _: actor)
        result, reward = await run_memory_with_hud(
            definition, lambda _: actor, tmp_path, on_wake=recorded.append
        )
        assert result.metrics == local.metrics
        assert (
            result.status == local.status == ("failed" if behavior == "exception" else "completed")
        )
        assert result.error == local.error
        assert reward == result.metrics.reward == 0
        assert tuple(recorded) == result.wakes
        assert len(recorded) == (1 if behavior == "exception" else 4)
        assert list(tmp_path.glob("*.jsonl"))

    asyncio.run(check())
