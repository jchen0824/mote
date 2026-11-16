# Event-driven local assistant

This milestone connects standing goals and calendar events to the real PostgreSQL
queue, worker, and SandboxAgent. The CLI is a trusted local operator interface;
it is not an authenticated webhook. The model calls typed Python tools executed
by the host SDK. MCP is not needed for this path.

## Try it

Run `uv run personal-agent init` after upgrading to create the additional tables.
Existing job and conversation tables are preserved. Start PostgreSQL first and set
`.env` as described in the [README](../README.md). Worker commands make paid model
calls and use the same persistent workspace as other tasks.

```sh
goal_id=$(uv run personal-agent goal meeting-1 \
  "Keep my meeting brief ready when the calendar changes." \
  --heading Status --heading Owner --heading "Next action" --notify)

cat > /tmp/personal-agent-calendar.json <<'JSON'
{
  "key": "meeting-1-revision-1",
  "source": "calendar",
  "resource_id": "meeting-1",
  "revision": 1,
  "starts_at": "2030-01-02T12:00:00+08:00",
  "text": "Maple review. Owner and supporting materials have not been provided."
}
JSON

uv run personal-agent event "$goal_id" /tmp/personal-agent-calendar.json
uv run personal-agent work --once
uv run personal-agent activity
```

Use a future meeting time. Submit another calendar event with a new key, higher
revision, and changed time to trigger an update. Repeating the identical event
returns its original decision and job; reusing a key with different data is an
error. A revision must increase monotonically for that resource. Events for another
resource, old revisions, and `document`/`noise` sources are recorded without a wake.
Even a document claiming a higher revision cannot change calendar state.

Multiple calendar changes arriving while a goal has a queued job coalesce into
that job. Only the newest event text is supplied, so this is latest-state processing,
not a summary of every event in a burst. All accepted events remain in the inbox.
An event arriving during execution creates a successor job; the old job immediately
loses permission to create effects for the older revision.

`--notify` is an explicit grant for local notification records. Without it, the
agent may save drafts only. `uv run personal-agent pause-goal "$goal_id"` blocks
new wakes and subsequent action attempts, including from an already running job.
It does not interrupt an in-flight model request or undo committed effects.

## Execution boundary

```text
Trusted local event ingestion
  -> transaction: inbox + calendar state + queued job
  -> worker claims job
  -> SandboxAgent calls typed tools in the host
  -> transaction: permission checks + local effect + action attempt
  -> inspect via activity
```

- `read_goal()` returns the authoritative goal, current revision, requested headings,
  notification grant, stale-job flag, and current effects.
- `save_brief(text: str)` writes a versioned brief in PostgreSQL. Required headings
  must appear on separate lines; Markdown heading prefixes are accepted. Content
  usefulness is not mechanically graded.
- `notify(text: str)` writes a notification record after a brief exists for the same
  revision. It does not deliver email, chat, or an operating-system notification.

The host binds every tool to the current job. The model cannot select a goal ID,
revision, timestamp, permission grant, or idempotency key. Credentials remain in the
host process. The sandbox retains filesystem/shell/memory access with networking
disabled and no host Docker socket or connector credentials mounted.

The executor rechecks job state, goal activity, current revision, action permission,
meeting deadline, and (for notifications) quiet hours. Unknown action types are
rejected. Learned memory and event text cannot change these grants.
Quiet hours are currently fixed at 18:00–08:00 Asia/Singapore. Notifications during
that interval are suppressed and logged, not rescheduled. Timing uses PostgreSQL's
clock in normal operation; the executor accepts a trusted test-clock override that
is never exposed in the tool schema.

## Persistence and recovery

`agent_goals` holds operator intent and grants; `agent_events` records delivery and
wake decisions; `agent_event_jobs` binds queued work to a goal revision.
`agent_effects` holds briefs and the local notification outbox; `agent_action_attempts`
records accepted, denied, suppressed, and duplicate execution requests.

The server derives effect identity from `(goal_id, revision, action_kind)`.
The first accepted effect wins. A retry with different prose returns the original
effect ID; it does not overwrite a brief or deliver another notification. Use a new
calendar revision for a new update. Effects and their audit record commit together.
Ingestion likewise commits the event, state change, and task together.

This provides duplicate suppression for local PostgreSQL effects, including a crash
after an effect commits and before the job completes. External delivery is not
implemented and would need provider idempotency/reconciliation. Single-worker and
shared-workspace restrictions still apply. Row locks prevent the event ingester
from changing a task while the worker claims it; they do not solve ownership loss
on database disconnect.

A completed job means the model run finished. Inspect effects and attempts to see
whether the requested action actually happened. SDK memory errors also need separate
artifact/recall checks. `activity` prints private content; do not share it indiscriminately.

## Verification and research scope

The integration gate covers event deduplication/coalescing, concurrent delivery,
actual SDK tool invocation, permission denial, quiet hours, stale execution,
notification ordering, concurrent duplicate actions, pausing, and process-crash
recovery after a committed notification. These tests use PostgreSQL and an injected
runner without paid model calls.

The existing synthetic HUD benchmark continues to use its separate virtual-clock
world and action proposals. Its scores do not validate this operational path.
This milestone does not add remote event authentication, real connectors, a UI,
customizable quiet hours, automatic deferred notifications, goal editing/resume,
or an isolated learned-memory benchmark.

See the [live acceptance evidence](event-driven-acceptance.md) for the first real-model run.
