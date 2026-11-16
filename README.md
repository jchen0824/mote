# Mote

Mote is a research prototype for proactive personal agents using OpenAI Agents SDK,
SandboxAgent, PostgreSQL conversations, and persistent sandbox memory. The research
focus is when an agent should act, ask, notify, or stay quiet. See the
[experiment design and HUD integration plan](docs/research.md).

Contributors and coding agents start with [AGENTS.md](AGENTS.md) and
[CONTRIBUTING.md](CONTRIBUTING.md). Repository skills guide runtime and evaluation
work; CI runs executable quality and architecture checks.

## Run locally

Requirements are Python 3.12+, uv, Docker with its daemon running, and an OpenAI API
key with access to your chosen model. Run commands from this repository directory.

```sh
cp .env.example .env
# Set OPENAI_API_KEY and OPENAI_MODEL in .env.
uv sync --locked

docker compose up -d --wait postgres
docker pull python:3.12-slim
uv run personal-agent init
uv run personal-agent enqueue "Remember that I prefer concise updates. Draft a meeting preparation checklist."
uv run personal-agent work --once
uv run personal-agent jobs
```

Schedule a follow-up and keep the worker running to process due jobs.

```sh
uv run personal-agent enqueue "Use my preferences to draft a short meeting brief." --at "2026-12-01T09:00:00+08:00" --key meeting-brief-dec-1
uv run personal-agent work
```

Use an explicit `--at` value with a stable `--key` when retrying a submission. A
reused key must have exactly the same prompt and scheduled instant. Times must
include a timezone. Failed jobs remain visible and can be requeued with
`uv run personal-agent retry JOB_ID`.

## Storage and recovery

PostgreSQL holds jobs, results, and SDK conversation history. `.agent-data/sandbox.json`
holds the sandbox identity and snapshot metadata. `.agent-data/snapshots` holds
workspace snapshots, including the SDK memory directory. Back up the database and
the entire data directory together. Treat both as private user data.

All jobs use one personal workspace. Workers serialize through a database advisory
lock. Restarting the worker recovers a task left in `running`. Successful jobs are
excluded from subsequent runs. Recovery can repeat an interrupted model invocation
or workspace edit. External exactly-once delivery is a future connector concern.
A lost database connection can release the lock before sandbox execution stops,
so this starter requires a single deployed worker for live use.

Sandbox closure runs SDK memory consolidation and persists its snapshot. Keep the
saved state and snapshots on the same host, or configure shared storage/provider
support before moving workers. The sandbox has networking disabled and exposes
filesystem and shell tools. The host SDK makes model requests and holds the API key.
`OPENAI_MODEL` is used for the task, memory extraction, and memory consolidation.
Consolidation allows up to 20 agent turns and adds model calls and latency after
the task response. The pinned SDK logs memory-generation errors without necessarily
failing the task, so a completed job alone does not prove memory was saved.

## Current scope

Includes a CLI, scheduled task queue, PostgreSQL SDK sessions, Docker sandbox
create/resume, SDK learned memory, and an event-driven path for standing meeting
goals. Local calendar events create or coalesce jobs; typed Python tools save
briefs and local notification records through a trusted, audited executor.
See the [event-driven walkthrough](docs/event-driven.md). Run `personal-agent init`
after upgrading to create its additional tables.

Remote event ingestion, real connector delivery, agent-created follow-ups, a
permission UI, and multi-user management remain future work.

The research CLI includes a meeting-reschedule episode, a no-action episode, three
wake policies, and a local HUD bridge. Run the deterministic reference actor with
no API key, or select our sandbox runner for a paid model experiment:

```sh
uv run personal-agent-eval
uv run personal-agent-eval --scenario quiet-week
uv run --extra eval personal-agent-eval --backend hud
```

See [evaluation setup and scoring](docs/evaluation.md) before interpreting results.
The reference actor validates the fixture; its scores are not model performance.

## Verification

```sh
make check
make check-hud
# Real PostgreSQL and Docker, against a dedicated disposable database:
TEST_DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@localhost:PORT/test_agents make check-integration
```

Integration tests create and drop `agent_jobs` and use the SDK session tables in the test database. They exercise
worker persistence with a deterministic runner and require no API key.
Both gates reject skipped tests. The quality gate also runs Ruff formatting and
linting, mypy, repository conventions, and a package build. CI invokes these same
commands; [GitHub branch rules](CONTRIBUTING.md#making-ci-a-merge-gate) still need
configuration after the repository is published. No remote enforcement is claimed.

Verified locally with PostgreSQL 17 and Docker: job deduplication, scheduled-time
filtering, worker serialization, process-crash recovery, failed-job retry, SDK
conversation persistence, and sandbox snapshot restoration into a replacement
container. These checks use no model calls.

Live acceptance passed on November 16, 2026 (Asia/Singapore), using `gpt-6-luna`:
the SDK generated memory from a synthetic persona, and a fresh worker with a
separate conversation recalled all facts after restoring the workspace into a
replacement Docker container. See [live acceptance evidence](docs/live-acceptance.md).

See [design](docs/design.md) for architecture decisions.
