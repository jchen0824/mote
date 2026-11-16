import pytest


def pytest_addoption(parser):
    parser.addoption("--fail-on-skip", action="store_true", help="Reject skipped tests in CI gates")


def pytest_sessionfinish(session, exitstatus):
    if session.config.getoption("--fail-on-skip"):
        reporter = session.config.pluginmanager.get_plugin("terminalreporter")
        if reporter and reporter.stats.get("skipped"):
            session.exitstatus = pytest.ExitCode.TESTS_FAILED


@pytest.fixture
def database():
    import asyncio
    import os

    from sqlalchemy.ext.asyncio import create_async_engine

    from personal_agent import control, store

    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to a disposable PostgreSQL database")

    async def reset():
        engine = create_async_engine(url)
        async with engine.begin() as connection:
            await connection.run_sync(control.metadata.drop_all)
            await connection.run_sync(store.metadata.drop_all)
        await store.initialize(engine)
        await control.initialize(engine)
        await engine.dispose()

    asyncio.run(reset())
    yield url
    asyncio.run(reset())
