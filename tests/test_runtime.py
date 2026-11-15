import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from agents.run import _sandbox_memory_rollout_id
from agents.sandbox.capabilities import Memory
from agents.sandbox.memory.manager import _validate_rollout_id
from sqlalchemy.ext.asyncio import create_async_engine

from personal_agent import runtime
from personal_agent.config import Settings


def test_runner_uses_file_safe_memory_id_and_configured_model(tmp_path, monkeypatch):
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
        return SimpleNamespace(final_output="Done")

    monkeypatch.setattr(runtime.Runner, "run", run)

    async def scenario():
        url = "postgresql+asyncpg://unused:unused@localhost/unused"
        engine = create_async_engine(url)
        try:
            runner = runtime.SandboxRunner(
                Settings(url, tmp_path, "configured-model", "python:3.12-slim"), engine
            )
            assert await runner({"id": "test-job", "prompt": "Remember a preference"}) == "Done"
        finally:
            await engine.dispose()

    asyncio.run(scenario())
    assert observed == ["task-test-job"]
