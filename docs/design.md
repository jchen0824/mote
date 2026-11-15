# Personal agent foundation

The user selected OpenAI Agents SDK with SandboxAgent, PostgreSQL for conversation
history and operational state, and persistent sandbox files for learned memory.
The initial milestone is a scheduled task that can continue after a worker restart.

OpenClaw and Deep Agents were considered. The user prefers the OpenAI SDK after
reviewing its sandbox, memory, session, and tool capabilities.

Implementation choices for this starter are Python 3.12, a CLI, Docker sandboxes,
and one personal workspace. PostgreSQL stores scheduled jobs and SDK conversations.
The sandbox state file and local snapshots live in `.agent-data`. A PostgreSQL
session advisory lock serializes worker access to the shared workspace. A running
job left behind by an interrupted worker is eligible for recovery by its successor.

The initial workload prepares private drafts and files. The Docker sandbox has
networking disabled. Model calls happen in the host SDK process. Connector credentials,
external delivery, webhooks, automatic follow-up tools, and a user interface are future
increments. SDK tracing is disabled for this starter.

Execution is at least once. A crash after a model action can cause work to repeat.
The database holds one result per job. Future external actions need idempotency and
reconciliation at the connector boundary. Concurrent workers on different hosts must
share the same persistent workspace/snapshot storage or use a remote sandbox provider.

Permission management and tenant authentication must precede multi-user deployment.
