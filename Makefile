.PHONY: check check-integration check-hud format

check:
	uv run --locked ruff check .
	uv run --locked ruff format --check .
	uv run --locked mypy
	uv run --locked python scripts/check_conventions.py
	uv run --locked pytest -m 'not integration and not hud' --fail-on-skip --junitxml=test-results/unit.xml
	uv build

check-integration:
	@test -n "$$TEST_DATABASE_URL" || (echo 'Set TEST_DATABASE_URL to a disposable PostgreSQL database'; exit 1)
	RUN_SANDBOX_TESTS=1 uv run --locked pytest -m integration --fail-on-skip --junitxml=test-results/integration.xml

check-hud:
	uv run --locked --extra eval mypy
	HUD_TELEMETRY_ENABLED=0 HUD_CLI_ANALYTICS_ENABLED=0 uv run --locked --extra eval pytest -m hud --fail-on-skip --junitxml=test-results/hud.xml

format:
	uv run --locked ruff check --fix .
	uv run --locked ruff format .
