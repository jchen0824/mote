# Repository bootstrap plan

The conversation establishes the chosen design in `design.md`.

- [x] Create an installable Python package and lock the tested SDK dependency.
- [x] Add PostgreSQL job storage and a CLI for enqueue, execution, inspection, and retry.
- [x] Connect SandboxAgent memory and PostgreSQL sessions with persisted Docker state.
- [x] Verify duplicate submission, concurrent workers, interrupted jobs, and failed-job retry.
- [x] Document setup, recovery semantics, and remaining live acceptance checks.
