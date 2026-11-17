# Preference retention and revision

This experiment tests whether persistent workspace state helps Mote remember a
user preference across fresh conversations and replace it when the user changes
that preference. It complements the meeting benchmark, where the visible previous
brief can reveal the requested headings.

## Why this matters for a personal agent

Mote should act on a standing goal without asking the user to repeat their preferences
at every wake. For example, a user first asks for a weekly brief with a particular
set of headings, then changes those headings. A later calendar-triggered task must
use the latest preference even though it starts a new conversation. Forgetting the
preference or following the superseded version produces unwanted autonomous work.

The event-driven milestone established when a task can run and which actions it
may execute. This experiment checks a separate prerequisite: whether information
learned in earlier conversations is available and current. The existing meeting
benchmark cannot establish that because the previous brief is visible in its input.

This PR adds a measurement, not a new memory implementation. Its four-conversation
sequence gives future changes to memory extraction, consolidation, or storage a
repeatable retention/revision check. The fresh-workspace control helps establish
whether the answer depends on persisted state rather than the current prompt.
The next research steps are repeated trials with usage/cost measurement, broader
preferences, and checking that recalled preferences actually guide tool actions.
A passing synthetic recall trial alone does not make the assistant dependable.

## Run it

The deterministic fixture needs no API key or Docker:

```sh
uv run personal-agent-memory-eval
```

The persistent reference actor should recall both preferences; the reset reference
actor should recall neither. This validates fixture sensitivity, not model quality.

A live run uses the existing SandboxRunner, Docker memory snapshots, and PostgreSQL
SDK sessions. Configure `.env`, start Docker/PostgreSQL, and create a separate
evaluation database as in the [episode guide](evaluation.md):

```sh
docker compose exec -T postgres createdb -U personal_agent personal_agent_memory_eval
EVAL_DATABASE_URL=postgresql+asyncpg://personal_agent:localdev@localhost:55432/personal_agent_memory_eval \
  uv run personal-agent-memory-eval --actor sandbox --memory both \
  --seed 0 --max-wakes 4 --wake-timeout 180
```

`--memory persistent` or `--memory reset` runs one arm. `both` runs eight fresh
conversations in total, sequentially. Live runs make paid model requests, including
memory extraction/consolidation. There is no hosted HUD integration for this
experiment; it is a separate local harness.

## Four conversations per arm

| Conversation | Input | Check |
| --- | --- | --- |
| Learn initial preference | Three ordered weekly-brief headings | Save for future conversations |
| Recall | Ask for current preferred headings | Exact initial headings in order |
| Learn replacement | Three different headings; explicitly replace the old preference | Update retained state |
| Recall again | The identical recall request | Exact replacement headings in order |

A seed selects six distinct headings from a fixed vocabulary. The two probes have
byte-identical prompts and no expected answer, previous output, seed, or grading
metadata. The adapter generates a new conversation ID for every request. Only the
current observation and response schema enter the actor prompt. The private
fixture and reports remain on the host, outside the agent workspace.

The actor returns a structured `headings` list. An empty list means it cannot recall
an answer. Both teaching conversations request an empty response; the later probes
measure retention. Reordering, partial answers, stale preferences, and self-reported
scores cannot satisfy the exact-match grader.

## Fixture and model contracts

The vocabulary in `memory_scenario` is synthetic test data, not a product restriction.
A fixed corpus and seed give both arms the same ordered preferences and an exact
expected answer without a second model acting as judge. Six distinct headings form
two nonoverlapping sets, making an obsolete answer distinguishable from the updated
one. The corpus is not passed to the actor; each teaching request supplies only
that stage's selected headings. Recall requests supply neither set. Changing the
corpus should change the scenario version. Real standing goals accept user-provided
headings; this fixture does not constrain them.

`MemoryObservation`, `MemoryScenario`, and result records are frozen Python
**dataclasses**: simple internal containers constructed by trusted harness code.
Type annotations support static checking, but dataclasses do not validate values
at runtime. Freezing prevents normal field reassignment; it is not a security boundary.

`MemoryAnswer` is a **Pydantic model** because its input comes from the model. It
provides the SDK's JSON schema and validates the returned structure: a headings
list, at most 12 entries, and no extra fields. That validates the response shape;
only the separate exact-match grader decides whether the recalled preference is
correct. Using Pydantic for all internal records would not add that evidence.

## What the comparison isolates

- **Persistent:** one workspace and its snapshots survive all four conversations.
- **Reset:** each conversation receives an independent, initially fresh workspace.
  Memory generation still runs, but its files do not reach the next conversation.

Both arms use the same model, observations, tool capabilities, and per-wake limits.
Their conversation histories are isolated by UUID session IDs in the evaluation
database. The reset arm removes all workspace state, including arbitrary notes;
it does not selectively disable only SDK-generated memory. Thus a benefit supports
persistent-workspace recall, not a claim about which particular memory mechanism
caused it. Source/model changes and multiple runs can change the outcome. A seed
makes the fixture reproducible, not the model deterministic.

## Reports and limits

Each invocation creates a UUID directory under `eval-results/`, with one
`report.json` per arm. Reports contain scenario/grader/prompt versions, source and
lockfile hashes, model, seed, observations, answers, elapsed time, and limits.
Private expected answers are saved for independent score recomputation. Never mount
these reports or the fixture into an acting sandbox.

Metrics separate initial retention, revised-preference recall, stale-preference
recall, completed probes, and correct probes. Accuracy is correct probes divided
by two, including missing probes in the denominator. Reward is 1 only if the trial
completes and both probes are correct. A completed wrong answer is distinct from a
runtime failure or exhausted wake budget.

Reports are saved before execution and checkpointed after each wake. Interrupting
the process leaves a visibly incomplete report. Failures record exception classes,
not potentially sensitive exception text. Each live wake also records snapshot and
memory-file hashes/sizes when available. File existence does not prove correct
memory extraction; the recall answers provide separate behavioral evidence.

The default is four wakes per arm, with a cooperative 180-second timeout per wake,
20 task turns, and 20 consolidation turns. SDK cleanup may exceed the timeout.
Task and memory token/currency totals are not yet instrumented. SDK tracing is
disabled; model inputs still reach the configured model provider.

This measures exact synthetic preference recall, not prose usefulness, general
memory quality, prompt-injection resistance, or multi-user isolation. Single trials
are acceptance checks. Repeated trials and uncertainty estimates remain future work.

## First live acceptance — November 17, 2026

One seed-0 trial per arm ran with `gpt-6-luna`, an isolated evaluation database,
and the existing production SandboxRunner. All eight conversations completed.

| Workspace mode | Initial recall | Revised recall | Correct probes | Elapsed |
| --- | --- | --- | --- | --- |
| Persistent | Correct | Correct; no stale preference | 2/2 | 223.9 seconds |
| Reset each wake | Incorrect | Incorrect | 0/2 | 151.8 seconds |

Scores were independently recomputed from the saved answers and matched the
reports. Both arms received identical observations. All five sandbox containers
exited. Memory artifact hashes and sizes were recorded after each wake.

The run used four wakes per arm, a 180-second cooperative timeout per wake,
20 task turns, and 20 consolidation turns. Cost and token counts were not measured.
The source hash was
`3c6c0315c60458fed86c28d02e6567d4198541c18efed586ffa43e6ccc909043`
(using the evaluator's filename-and-content hashing convention). Private local
reports and snapshots remain under
`eval-results/memory-live-20261117/8d55e7c2-a302-42b4-a2a3-ad69e29cbd28/`.
This is an acceptance comparison, not a statistical estimate of memory reliability.
