import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from agents.run import _sandbox_memory_rollout_id
from agents.sandbox.capabilities import Memory
from agents.sandbox.memory.manager import _validate_rollout_id
from sqlalchemy.ext.asyncio import create_async_engine

from personal_agent import runtime
from personal_agent.config import Settings
from personal_agent.evaluation.sandbox_actor import ActionEnvelope


@pytest.mark.parametrize("structured", [False, True])
def test_runner_uses_file_safe_memory_id_and_configured_model(tmp_path, monkeypatch, structured):
    # Exercise our runtime wiring against the pinned SDK's grouping/validation rules.
    sandbox = MagicMock()
    sandbox.__aenter__ = AsyncMock(return_value=sandbox)
    sandbox.__aexit__ = AsyncMock(return_value=False)
    client = SimpleNamespace(create=AsyncMock(return_value=sandbox))
    monkeypatch.setenv("OPENAI_API_KEY", "test-placeholder")
    monkeypatch.setattr(runtime, "from_env", MagicMock())
    monkeypatch.setattr(runtime, "DockerSandboxClient", lambda docker: client)
    monkeypatch.setattr(runtime, "save_state", lambda path, state: None)
    observed = []

    async def run(agent, prompt, *, session, run_config, max_turns):
        rollout_id = _sandbox_memory_rollout_id(
            run_config=run_config, conversation_id=None, session=session
        )
        observed.append(_validate_rollout_id(rollout_id))
        memory = next(c for c in agent.capabilities if isinstance(c, Memory))
        assert memory.generate.phase_one_model == "configured-model"
        assert memory.generate.phase_two_model == "configured-model"
        assert memory.generate.phase_two_max_turns == 20
        assert agent.output_type is (ActionEnvelope if structured else None)
        return SimpleNamespace(final_output=ActionEnvelope(actions=[]) if structured else "Done")

    monkeypatch.setattr(runtime.Runner, "run", run)

    async def scenario():
        url = "postgresql+asyncpg://unused:unused@localhost/unused"
        engine = create_async_engine(url)
        try:
            runner = runtime.SandboxRunner(
                Settings(url, tmp_path, "configured-model", "python:3.12-slim"),
                engine,
                output_type=ActionEnvelope if structured else None,
            )
            result = await runner({"id": "test-job", "prompt": "Remember a preference"})
            assert (json.loads(result) if structured else result) == (
                {"actions": []} if structured else "Done"
            )
        finally:
            await engine.dispose()

    asyncio.run(scenario())
    assert observed == ["task-test-job"]
