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
