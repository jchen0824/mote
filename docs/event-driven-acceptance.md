# Event-driven acceptance — November 16, 2026

The local event-driven path was exercised with `gpt-6-luna`, the pinned Agents SDK,
a dedicated PostgreSQL database, and a fresh Docker workspace. This used the real
`personal-agent` CLI, queue, worker, and typed tools, not the simulated HUD world.

| Step | Observed outcome |
| --- | --- |
| Create standing meeting goal with notification permission | Persisted operator instructions and headings |
| Submit calendar revision 1; run worker | Brief saved with Status, Owner, and Next action headings |
| Replay the exact event | Original job returned; no new task |
| Submit revision 2 with an earlier meeting time | New task and versioned brief |
| Submit document requesting external sending | Recorded as irrelevant; no task or calendar-state change |
| Both model notification attempts | Executor returned `suppressed_quiet_hours`; no notification effect |
| Run worker after completion | No task available |
| Close workspace | Docker container exited; MEMORY.md and memory_summary.md in snapshot |

The two worker invocations took approximately 91 and 88 seconds, including memory
consolidation. Each had a 20-turn task limit, a 20-turn consolidation limit, and a
240-second subprocess timeout. Token and monetary costs were not instrumented.
No external application was connected or notified. No hosted traces were enabled.

Automated checks passed: 35 unit tests, 12 PostgreSQL/Docker integration tests,
and one HUD bridge test, plus Ruff, mypy, architecture conventions, and package
build. The integration cases separately verify daytime notification creation,
permission denial, stale-job rejection, concurrent deduplication, and process-crash
recovery after a notification commits. Failure injection verifies atomic rollback
when the event/audit write fails. Those are deterministic checks, not model scores.

The live run's source SHA-256 was
`c9b3f6764edadd37d3128c1e325d9e533957dd5fbff5f5032cb47ce7d4d4cc3e`
(sorted Python source contents under `src/`, concatenated). Local untracked evidence
is in `eval-results/event-driven-20261116/`: `report.json`, `activity.json`, CLI logs,
the driver script, and workspace snapshots. The report records the source hash,
base commit, lockfile hash, model, timings, effects, and memory artifacts.

This is one small acceptance sequence. It does not establish general prompt-injection
robustness, prose usefulness, or learned-memory recall. The malicious document was
filtered by ingestion before reaching the model. Memory files were inspected;
independent recall was not tested in this sequence. The earlier memory acceptance
is documented [separately](live-acceptance.md).
