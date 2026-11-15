# Live acceptance — November 16, 2026

Environment: OpenAI Agents SDK 0.24.0, `gpt-6-luna`, PostgreSQL 17,
Docker `python:3.12-slim`, Python 3.12. Both memory-generation phases use the
configured model. No production user data was used.

## Scenario

1. Enqueue a task to remember a synthetic persona's project codename, weekly
   check-in, and meeting-brief headings.
2. Execute the task and let SDK extraction/consolidation finish on sandbox close.
3. Inspect the snapshot: `memories/MEMORY.md` and `memories/memory_summary.md`
   both contain all facts, along with raw memory and a rollout summary.
4. Remove the stopped test container while retaining its snapshot and state.
5. Enqueue a recall task that does not include the facts. Execute it in a new
   worker process with a distinct, initially empty PostgreSQL conversation.
6. Verify the response and replacement container identity.

The recall response was:

> For the acceptance-test persona, the fictional project codename is **Cedar Lantern**.
> The weekly check-in is **Thursday at 10:15 Asia/Singapore**. The required meeting-brief
> headings, in order, are **Decision, Evidence, Next action**.

## Bug caught and fixed

The original `task:UUID` conversation ID was also used by the SDK as a memory
rollout ID. Its colon failed the SDK's filename validation. The SDK logged
`Failed to enqueue sandbox memory after run`, while the job still completed and
the agent manually wrote a workspace file. That was not a passing memory test.

The runtime now uses `task-UUID`. A regression test exercises runtime wiring
against the pinned SDK's grouping and validation functions. Memory generation
also explicitly uses `OPENAI_MODEL` instead of the SDK's separate default models,
with consolidation limited to 20 turns.

## Local evidence

The isolated database is `personal_agent_acceptance_20261115`; test artifacts are
under ignored `.agent-data/acceptance-20261115/`. The name reflects the UTC start
date; completion was November 16 in Singapore.

- Seed job: `36182eab-1135-4cbe-a86d-2aafab90f6da`.
- Recall job: `162f74d2-e699-47d1-a3c3-2e04d97826d0`.
- Passing workspace: `workspace-fixed/`, including sandbox state and snapshots.
- Logs: `fixed-seed.log` and `fixed-recall.log`.
- Earlier failed attempts remain isolated for diagnosis.

Both passing jobs completed on their first attempt. The recall run emitted one
`Custom tool failed` warning during memory consolidation; the SDK did not expose
the underlying error in the default log. Consolidation subsequently finished:
`phase_two_selection.json` records both rollout IDs, both consolidated memory files
were updated, and the final snapshot was saved with the sandbox stopped. The
warning's cause remains unverified.

Eight automated tests passed, including PostgreSQL scheduling, deduplication,
worker serialization, crash recovery, retry, conversation persistence, Docker
snapshot restoration, and the runtime memory-ID regression. Ruff passed.

This is one live end-to-end acceptance scenario, not a guarantee of memory quality
for arbitrary conversations. SDK memory failures are currently best-effort log
events; the job status does not separately track consolidation health. No worker
was left running, and the default personal workspace was not seeded with test facts.
