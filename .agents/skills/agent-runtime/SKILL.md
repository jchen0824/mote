---
name: agent-runtime
description: Use when changing personal-agent scheduling, PostgreSQL storage, sandbox execution, memory persistence, recovery, or SDK dependencies.
---

# Preserve execution and memory contracts

Read the affected module and [architecture decisions](../../../docs/design.md).
The queue accepts an injected runner so persistence tests do not need model calls.
Keep the SDK and Docker integration in `runtime.py`.

For concurrency or recovery changes, identify who owns the workspace and when that
ownership can be lost. Exercise a real process crash and PostgreSQL connection
behavior where relevant. A task retry is not proof that an external action did not
already occur; introduce idempotency at the action boundary before claiming it.

For memory changes, check three separate outcomes: task result, consolidated memory,
and snapshot recovery. A completed job can coexist with a failed SDK memory phase.
The SDK derives memory filenames from conversation IDs. Preserve file-safe IDs and
the pinned-SDK regression until the integration changes deliberately.

Use `make check` and `make check-integration` with a disposable database. A storage-only
test does not validate live model behavior. Run paid acceptance only within the
user's authorized scope, use synthetic facts in an isolated workspace, and retain
results with explicit limitations. Report model and memory-generation costs when
available; do not print credentials or private prompts into shared logs.

Keep one deployed worker until per-agent ownership and failure handling exist.
A retry, async task, container, or lease alone is not a safety boundary.
