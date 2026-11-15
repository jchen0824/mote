---
name: evaluation-design
description: Use when designing personal-agent scenarios, proactive policies, memory experiments, HUD adapters, scoring, or benchmark reports.
---

# Evaluate personal agents over time

Read [the research contract](../../../docs/research.md). The experiment unit is a
whole episode: preserve memory across its sessions and reset it between independent
trials. Keep event generation, virtual time, and private grading state outside the
agent's control. Future events and reference answers are not observations.

The implemented fixture and commands are in [evaluation.md](../../../docs/evaluation.md).
The reference actor is a deterministic plumbing test, not a measured model. Current
graders check structural correctness; do not claim they score prose usefulness.
Run `make check-hud` when changing the bridge. Hosted execution is not implemented.

Compare policies on the same seeded events, tool access, initial memory, model, and
budget. Record user-requested versus agent-initiated actions. A policy cannot improve
its score by sending unlimited notifications, waking forever, or reading the grader.
Include a legitimate no-action case and a changed-preference case.

Grade observable world state and action records where possible. Test graders with
known-good, known-bad, no-op, duplicate-action, and forbidden-action trajectories.
Keep task utility, interruption burden, permission violations, and cost visible as
separate metrics. Explain any scalar weighting; never hide a permission violation
inside a high average utility score. Use blinded human judgments for subjective
usefulness claims and describe uncertainty across repeated trials.

HUD runs and records experiments; the existing Agents SDK remains the tested
harness. Put integration in an adapter and verify the pinned HUD version's APIs.
Local tests need no HUD account. Hosted telemetry is an explicit choice for synthetic
or approved data; local execution does not by itself mean telemetry is disabled.

For a behavior change, compare before/after runs and report failures, seeds, code
revision, model, policy, scenario version, and budgets. Deterministic environment and
grader tests belong in PR gates; live-model scores begin as separate reports until
their variance and acceptance thresholds are established.
