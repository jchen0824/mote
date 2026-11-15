import asyncio
import io
import os
from pathlib import Path

import pytest
from agents.sandbox import LocalSnapshotSpec, Manifest
from agents.sandbox.sandboxes.docker import (
    DockerSandboxClient,
    DockerSandboxClientOptions,
    DockerSandboxSessionState,
)
from docker import from_env

from personal_agent.runtime import save_state


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("RUN_SANDBOX_TESTS") != "1",
    reason="Set RUN_SANDBOX_TESTS=1 with Docker running and python:3.12-slim available",
)
def test_snapshot_restores_files_in_replacement_container(tmp_path):
    async def scenario():
        docker = from_env()
        client = DockerSandboxClient(docker)
        sandbox = await client.create(
            manifest=Manifest(),
            snapshot=LocalSnapshotSpec(base_path=tmp_path / "snapshots"),
            options=DockerSandboxClientOptions(image="python:3.12-slim", network_mode="none"),
        )
        try:
            async with sandbox:
                await sandbox.mkdir(Path("/workspace/memories"))
                await sandbox.write(
                    Path("/workspace/memories/MEMORY.md"),
                    io.BytesIO(b"User prefers concise updates.\n"),
                )
            state_path = tmp_path / "sandbox.json"
            save_state(state_path, sandbox.state)
            old_container = sandbox.state.container_id
            await client.delete(sandbox)
            state = DockerSandboxSessionState.model_validate_json(state_path.read_text())
            sandbox = await client.resume(state)
            assert sandbox.state.container_id != old_container
            async with sandbox:
                content = await sandbox.read(Path("/workspace/memories/MEMORY.md"))
                assert content.read() == b"User prefers concise updates.\n"
        finally:
            await client.delete(sandbox)
            docker.close()

    asyncio.run(scenario())
