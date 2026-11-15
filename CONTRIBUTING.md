# Contributing

People and coding agents use the same commands and review process. Read
[AGENTS.md](AGENTS.md) for architecture and the skill relevant to your change.

## Setup and verification

Install Python 3.12+, uv, and Docker. Run `uv sync --locked` and `make check`.
This gate needs no `.env`, API key, PostgreSQL service, or HUD account.

For integration tests, start an isolated test database and pull the sandbox image:

```sh
docker run --detach --rm --name personal-agent-tests \
  -e POSTGRES_USER=personal_agent -e POSTGRES_PASSWORD=testonly \
  -e POSTGRES_DB=personal_agent_test -p 127.0.0.1:55433:5432 postgres:17
docker exec personal-agent-tests pg_isready -U personal_agent -d personal_agent_test
# Wait for pg_isready to report accepting connections before proceeding.
docker pull python:3.12-slim
TEST_DATABASE_URL=postgresql+asyncpg://personal_agent:testonly@localhost:55433/personal_agent_test make check-integration
docker stop personal-agent-tests
```

Tests create and drop tables. Use only a disposable database. The integration gate
fails when tests skip. Ordinary CI runs deterministic tests with synthetic data;
model-based experiments need a separately configured model and budget.

## Pull requests

Create a branch such as `feat/event-policy` or `fix/memory-recovery`. Keep each PR
focused. Add regression tests for changed behavior, update affected documentation,
and include evidence and limitations in the PR template. Use Conventional Commits:
`type(scope): lower-case summary`, at most 72 characters, with no trailing period.
Scopes are optional; useful scopes include `runtime`, `memory`, `evals`, and `ci`.
CI checks the title and all non-merge commit subjects. Do not bump the version or
publish a release as part of ordinary feature work.

## Making CI a merge gate

The repository includes workflows named `quality`, `integration`, and
`conventional-commits`. After publishing to GitHub and verifying their first runs,
configure a ruleset for `main` that requires these checks, pull requests, and an
up-to-date branch; block force pushes and deletion and control bypass permissions.
Squash merging keeps the validated PR title as the commit subject.

This local repository currently has no remote. Workflow files do not create branch
protection, and the presence of this document does not prove remote enforcement.
Changes to CI, policy, and graders deserve explicit review: ordinary PR checks run
the candidate code and are not tamper-proof against someone authorized to edit them.

## Research contributions

See [research direction](docs/research.md) for the first proposed benchmark and HUD
integration. Keep scenarios and graders inspectable, synthetic, and reproducible.
Report results across trials, including failures and cost. Do not use private
personal data in shared fixtures or uploaded traces.
