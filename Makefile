.PHONY: check check-integration format

check:
	uv run --locked ruff check .
	uv run --locked ruff format --check .
	uv run --locked mypy
	uv run --locked python scripts/check_conventions.py
	uv run --locked pytest -m 'not integration' --fail-on-skip --junitxml=test-results/unit.xml
	uv build

check-integration:
	@test -n "$$TEST_DATABASE_URL" || (echo 'Set TEST_DATABASE_URL to a disposable PostgreSQL database'; exit 1)
	RUN_SANDBOX_TESTS=1 uv run --locked pytest -m integration --fail-on-skip --junitxml=test-results/integration.xml

format:
	uv run --locked ruff check --fix .
	uv run --locked ruff format .
