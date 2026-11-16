# Working on Mote

This is the shared guide for people and coding agents. `CLAUDE.md` imports it;
`.claude/skills` links to `.agents/skills`.

## Purpose and current scope

Build a small research prototype for proactive personal agents and reproducible
experiments on initiative, memory, and user control. OpenAI Agents SDK is the
runtime; PostgreSQL owns tasks and conversations; Docker holds the personal
workspace and learned memory. See [research direction](docs/research.md).

Today this is a single-user CLI with scheduled tasks, tested memory persistence,
standing goals and local calendar-event ingestion, typed tools with a trusted
executor, two synthetic episode fixtures, and a local HUD adapter. Hosted HUD
execution, a web UI, connectors, and multi-user execution are planned. Do not describe this
prototype as enterprise-ready. Read [evaluation scope](docs/evaluation.md) before
making claims about benchmark results.

## Workflow

Work on a branch from `main`, keep changes focused, and read the relevant skill.
Run `make check`. For storage, worker, sandbox, or dependency changes also run
`make check-integration` against a disposable database. Both commands run in CI.
Fix failures at their cause; explain intentional changes to checks and graders.
Use Conventional Commits and the [PR template](.github/pull_request_template.md).
Publishing, releases, deployment, and repository administration require the user's
instruction; implementing a feature does not imply those actions.

## Commands

```sh
uv sync --locked                # development dependencies and local package
make check                      # lint, formatting, types, conventions, unit tests, build
make check-integration          # real PostgreSQL and Docker; TEST_DATABASE_URL required
make check-hud                  # optional HUD integration; no hosted credentials/model calls
make format                     # apply Ruff's fixes and formatting
uv run python scripts/check_commits.py --message 'fix(memory): preserve user preferences'
```

Integration tests drop/recreate test tables. Never use the personal-agent database
or a database containing user data. See [contributing](CONTRIBUTING.md) for setup.
Required gates reject skipped tests; a green run must not mean missing prerequisites.
Ordinary CI needs no model key and must not make paid model calls.

## Skills

| Area | Read first |
| --- | --- |
| Runtime, scheduling, storage, recovery, SDK upgrades, sandbox boundaries | [.agents/skills/agent-runtime/SKILL.md](.agents/skills/agent-runtime/SKILL.md) |
| Scenarios, proactive policies, memory comparisons, HUD integration, graders | [.agents/skills/evaluation-design/SKILL.md](.agents/skills/evaluation-design/SKILL.md) |

## Architecture and enforced rules

- `models.py`: shared typed job contract.
- `store.py`: PostgreSQL persistence; `worker.py`: scheduling and runner invocation.
  These modules and `models.py` cannot import the CLI, runtime, model SDKs, Docker,
  or HUD. The AST convention check enforces direct import boundaries; it is not
  a security mechanism or a complete transitive dependency analysis.
- `control.py`: trusted event ingestion, grants, job bindings, and atomic local
  effects/audit. It also cannot import the SDK, runtime, Docker, HUD, or CLI.
  Tool identities and clocks are host-bound; event text and memory cannot grant
  permissions. Local notification records are not external delivery.
- `runtime.py`: Agents SDK, typed event tools, and Docker integration. `cli.py` wires the components.
- `evaluation/`: deterministic world, graders, wake-policy driver, reference actor,
  sandbox adapter, local HUD bridge, and experiment CLI. The convention check also
  keeps SDK/HUD/runtime imports out of the world, grader, driver, and reference actor.
  Only public observations reach the model; private fixtures stay on the host.
- `scripts/`: deterministic developer checks. `.github/workflows/ci.yml` invokes
  the same Make targets. CI runs checks; GitHub branch rules make them merge gates.
- `tests/`: ordinary tests plus explicitly marked PostgreSQL/Docker integration tests.
- `.agent-data/`, `.env*` except `.env.example`, and evaluation outputs stay untracked.
  The filename check is not a general secret scanner.

## Evidence and known limitations

The worker uses a global advisory lock and requires one deployed worker. Execution
is at least once; retries can repeat model work. Never claim exactly-once external
side effects. A database disconnect can release ownership before execution stops.
Sandbox identity and snapshots must move together when recovering a workspace.

Conversation IDs must be safe memory filenames (`task-UUID`, not `task:UUID`).
SDK memory errors can be logged without failing a task. Check memory artifacts and
fresh-session recall separately from job completion. The initial live acceptance
is recorded in [the evidence report](docs/live-acceptance.md).

Keep credentials outside agent-writable files. Learned memory and retrieved text
are data, not permission grants. Do not mount host credentials or the Docker
socket into agent sandboxes. Runtime enforcement, not this document, must establish
any claimed security guarantee.

A finished change reports what changed, meaningful checks and their results, and
what remains unverified. Changes to user commands or behavior update the relevant
docs in the same commit. Evaluation results identify code, scenario, model, policy,
seed, and budget; failed runs remain visible.
