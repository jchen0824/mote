import os
from pathlib import Path

from agents import Runner, Tool, function_tool
from agents.extensions.memory import SQLAlchemySession
from agents.run import RunConfig
from agents.sandbox import (
    LocalSnapshotSpec,
    Manifest,
    SandboxAgent,
    SandboxRunConfig,
)
from agents.sandbox.capabilities import Filesystem, Memory, Shell
from agents.sandbox.config import MemoryGenerateConfig
from agents.sandbox.sandboxes.docker import (
    DockerSandboxClient,
    DockerSandboxClientOptions,
    DockerSandboxSessionState,
)
from docker import from_env
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncEngine

from . import control
from .config import Settings
from .models import Job


def save_state(path: Path, state: BaseModel) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(state.model_dump_json())
    temporary.chmod(0o600)
    temporary.replace(path)


class SandboxRunner:
    def __init__(
        self,
        settings: Settings,
        engine: AsyncEngine,
        output_type: type[BaseModel] | None = None,
        enable_event_tools: bool = False,
    ):
        self.settings = settings
        self.engine = engine
        self.output_type = output_type
        self.enable_event_tools = enable_event_tools

    async def __call__(self, job: Job) -> str:
        if not os.getenv("OPENAI_API_KEY") or not self.settings.model:
            raise ValueError("Set OPENAI_API_KEY and OPENAI_MODEL before running agent jobs")
        directory = self.settings.data_dir
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        state_path = directory / "sandbox.json"
        docker = from_env()
        client = DockerSandboxClient(docker)
        try:
            if state_path.exists():
                state = DockerSandboxSessionState.model_validate_json(state_path.read_text())
                sandbox = await client.resume(state)
            else:
                sandbox = await client.create(
                    manifest=Manifest(),
                    snapshot=LocalSnapshotSpec(base_path=directory / "snapshots"),
                    options=DockerSandboxClientOptions(
                        image=self.settings.image,
                        network_mode="none",
                        labels={"personal-agent.workspace": str(directory)},
                    ),
                )
            # Record the container identity before work so a restarted worker can reconnect.
            save_state(state_path, sandbox.state)
            agent = SandboxAgent(
                name="Personal assistant",
                model=self.settings.model,
                output_type=self.output_type,
                tools=(await event_tools(self.engine, job["id"]))
                if self.enable_event_tools
                else [],
                instructions=(
                    "Complete the assigned task and report a concise, verifiable result. "
                    "Use persistent memory for user preferences and lessons. "
                    "Prepare drafts and artifacts inside the workspace. "
                    "For requests requiring unavailable tools, explain what is pending. "
                    "When retrying interrupted work, inspect existing artifacts first."
                ),
                capabilities=[
                    Memory(
                        generate=MemoryGenerateConfig(
                            phase_one_model=self.settings.model,
                            phase_two_model=self.settings.model,
                            phase_two_max_turns=20,
                        )
                    ),
                    Filesystem(),
                    Shell(),
                ],
            )
            conversation = SQLAlchemySession(
                # The SDK also uses this ID as the memory rollout filename.
                f"task-{job['id']}",
                engine=self.engine,
                create_tables=True,
            )
            try:
                async with sandbox:
                    result = await Runner.run(
                        agent,
                        job["prompt"],
                        session=conversation,
                        run_config=RunConfig(
                            sandbox=SandboxRunConfig(session=sandbox),
                            tracing_disabled=True,
                        ),
                        max_turns=20,
                    )
                # Session close performs memory consolidation and snapshot persistence.
                if isinstance(result.final_output, BaseModel):
                    return result.final_output.model_dump_json()
                return str(result.final_output)
            finally:
                save_state(state_path, sandbox.state)
        finally:
            docker.close()


async def event_tools(engine: AsyncEngine, job_id: str) -> list[Tool]:
    """Bind authority on the host; the model cannot supply identity, time, or grants."""
    if await control.read_goal(engine, job_id) is None:
        return []

    @function_tool(failure_error_function=None)
    async def read_goal() -> dict[str, object]:
        """Read authoritative goal, meeting revision, permissions, and completed effects."""
        return await control.read_goal(engine, job_id) or {}

    @function_tool(failure_error_function=None)
    async def save_brief(text: str) -> dict[str, object]:
        """Save a local brief. Use each requested heading on its own line. First write wins."""
        return await control.execute_action(engine, job_id, "save_brief", text)

    @function_tool(failure_error_function=None)
    async def notify(text: str) -> dict[str, object]:
        """Add one local notification after saving the brief, subject to permission and quiet hours.

        This creates a database outbox entry; it does not send email or chat messages.
        """
        return await control.execute_action(engine, job_id, "notify", text)

    return [read_goal, save_brief, notify]
