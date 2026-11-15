# Personal Agent

A local-first starter for a proactive personal assistant using OpenAI Agents SDK,
SandboxAgent, PostgreSQL conversations, and persistent sandbox memory.

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

## Current scope

Includes a CLI, scheduled task queue, PostgreSQL SDK sessions, Docker sandbox
create/resume, and SDK learned-memory support. Proactive scheduling is explicit
through the CLI. Event ingestion, agent-created follow-ups, connectors, notifications,
permission UI, and multi-user management are future work.

## Verification

```sh
uv run ruff check .
uv run pytest
# Against a dedicated disposable PostgreSQL database:
TEST_DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@localhost:PORT/test_agents uv run pytest
# Also exercise SDK snapshot restore in a replacement Docker container:
RUN_SANDBOX_TESTS=1 TEST_DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@localhost:PORT/test_agents uv run pytest
```

Integration tests create and drop `agent_jobs` and use the SDK session tables in the test database. They exercise
worker persistence with a deterministic runner and require no API key.

Verified locally with PostgreSQL 17 and Docker: job deduplication, scheduled-time
filtering, worker serialization, process-crash recovery, failed-job retry, SDK
conversation persistence, and sandbox snapshot restoration into a replacement
container. These checks use no model calls.

Live acceptance requires a configured API key and Docker. Run an initial task,
restart the worker, enqueue a task asking it to recall the preference, and inspect
the actual response and saved memory. This bootstrap has not yet passed that live check.

See [design](docs/design.md) for architecture decisions.
