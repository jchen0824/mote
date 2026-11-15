# Research direction: proactive personal agents

Status: research roadmap with an initial implementation. The repository now includes
two synthetic episode fixtures, deterministic state graders, three wake policies,
an adapter to the existing sandbox runner, and a local HUD bridge. See
[evaluation scope and commands](evaluation.md) for what is verified and what remains
unimplemented; the broader scenarios below are the research roadmap.

## Question and first experiment

When should a personal agent act, ask, notify, or remain quiet? Compare a reactive
policy, a fixed-schedule policy, and an event-driven policy over the same simulated
week. All receive the same standing user goal, potential information, tool access,
model, initial memory, and spending limits; the wake policy determines observations
and execution times. Record wake opportunities, observations, and invocation counts
so differences can be attributed rather than hidden.

The initial world contains a synthetic calendar, inbox, task list, and notification
outbox. A trial is one complete week, driven by a virtual clock. The evaluator
advances time and delivers events. The agent cannot inspect future events, change
the clock, read private expected outcomes, or write the grading ledger. Waiting in
an episode consumes simulated time, not days of wall-clock time.

Preserve the agent's memory across sessions within one trial. Give each trial its
own database namespace, workspace, and snapshot location, reset between trials,
and record initial-state hashes. Keeping everything in one chat would test context
retention rather than persistent memory. Future events must not leak through a
fixture file mounted into the agent's sandbox.

Start with these scenarios:

1. A meeting changes time; a useful preparation task must follow the new deadline.
2. A user revises a preference; later work uses the revision rather than stale memory.
3. Several related updates arrive; one useful summary is better than repeated alerts.
4. Quiet hours apply; nonurgent information waits and genuinely urgent cases use the
   scenario's explicit exception policy.
5. Untrusted document text requests an unauthorized action; the permission boundary
   rejects it even if the agent attempts it.
6. No intervention is useful; the agent should remain quiet.
7. Execution restarts mid-task; work recovers without duplicating externally visible
   actions in the simulated outbox.

## What HUD supplies and what we build

HUD v6 supports custom harnesses, tasksets, repeated runs, multiple runtimes, and
trace recording. A custom `Agent.__call__(run)` adapter can drive our Agents SDK
runner, connect environment capabilities, record steps, and publish a final answer.
The initial local bridge is tested against pinned HUD 0.6.23. It records trusted
driver events and grades the private ledger; remote capability transport remains
future work.

| Component | Responsibility |
| --- | --- |
| Existing Agents SDK runtime | The personal agent under evaluation, including memory |
| Our simulated world | Virtual time, events, synthetic apps, tool permissions, private action ledger |
| Our episode driver | Multiple sessions per trial, wake policy, restart injection, budgets |
| Our graders | Outcomes and policy constraints checked against authoritative world state |
| HUD adapter | Connect the episode to a HUD task, emit structured traces and metrics |
| HUD runtime | Place and run the evaluation environment locally or remotely |

HUD's stock model agent is not a substitute for evaluating our own harness. Use the
same runner implementation in ordinary operation and evaluation where applicable;
keep environment transport and clock injection at explicit boundaries. Merely
choosing HUD's OpenAI model integration would evaluate a different agent loop.

LocalRuntime is useful for development but imported modules can share state.
For independent trials use fresh state and process/container isolation. Neither a
local process nor an evaluation runtime should be described as a verified security
sandbox. Keep the acting workspace separate from the private grader and fixtures;
exercise isolation with a deliberate attempt to read reference data.

Do not mount a host Docker socket into an acting environment. Decide which side
owns sandbox provisioning when implementing the adapter, to avoid nested Docker
requirements or two competing workspace lifecycles. Hosted deployment and any
Compose-based arrangement need their own acceptance test.

## Scoring and reporting

Report a vector of outcomes: useful tasks completed by their deadlines, missed
opportunities, unnecessary notifications, permission violations, duplicate effects,
model calls, tokens, cost when available, and wall-clock/virtual-time latency.
Log attempted forbidden actions separately from actions actually executed. Do not
hide a violation behind a high aggregate reward. For any scalar HUD reward, publish
the weighting and constraints alongside the individual metrics.

Use state-based graders for objective outcomes. Validate every grader using known
successful, unsuccessful, no-op, repeated-action, and policy-violating trajectories.
Subjective usefulness needs a published rubric and blinded human review before
claiming benefit to real users. Repeated model trials quantify variability; identical
seeds make the environment reproducible, not the model deterministic.

Record code revision, lockfile hash, scenario/grader version, seed, model, prompt,
policy, memory configuration, time/cost limits, and every failed or incomplete trial.
Retain error categories separately from zero-reward outcomes. Cap model turns and
wake counts as well as total episode cost and runtime. Reward improvement should
not come from extra unreported compute or grader-specific answers.

## Repository gates

PRs run deterministic quality, infrastructure, and convention tests. The first live
benchmark should be an explicitly invoked report with synthetic data and a budget.
Only promote a model-score threshold to a required gate once repeated measurements
establish its variance and a meaningful regression policy. Fork PRs must not require
model or HUD credentials to contribute.

Keep developer guidance in AGENTS.md and the local skills, objective repository
rules in check scripts and CI, and runtime permission enforcement in trusted code.
CI does not prove arbitrary agent actions are safe; model evaluations do not prove
code quality. Both contribute distinct evidence.

## Privacy and portability

Keep fixtures and deterministic graders runnable without a HUD account. Start with
local evaluation and direct model credentials. If adding HUD, disable trace uploads
and CLI analytics by default for local runs using the documented controls
`HUD_TELEMETRY_ENABLED=0` and `HUD_CLI_ANALYTICS_ENABLED=0`; store local traces in the
ignored `eval-results/` directory via `HUD_TELEMETRY_LOCAL_DIR`. Local files remain
sensitive, and disabling HUD telemetry does not disable model-provider processing.
Hosted traces require an intentional decision about what data is uploaded.

## Implementation order

1. Done: agent-ready repository and deterministic gates.
2. Done: simulated world, virtual clock, two fixtures, and grader tests.
3. Done: Agents SDK adapter and three wake policies; deterministic reference comparisons.
4. Done: pinned HUD adapter verified locally against the same episode.
5. Next: richer scenarios, usage instrumentation, repeated model trials and uncertainty,
   blinded usefulness review, then optional hosted execution.

## Sources inspected on November 16, 2026

- [HUD custom harnesses and multi-turn interactions](https://docs.hud.ai/v6/advanced/extending)
- [HUD runtimes and isolation semantics](https://docs.hud.ai/v6/reference/runtime)
- [HUD telemetry controls](https://github.com/hud-evals/hud-python/blob/main/docs/v6/reference/telemetry.mdx)
- [Guandan agent instructions](https://github.com/jchen0824/guandan-master/blob/main/AGENTS.md)
- [Guandan CI](https://github.com/jchen0824/guandan-master/blob/main/.github/workflows/ci.yml)

The Guandan reference informed the shared local/CI commands, skill routing,
architecture checks, and explicit evidence requirements. The rules here are written
for the Python personal-agent project; they do not inherit game-specific constraints.
