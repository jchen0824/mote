import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "source",
    [
        "import agents as sdk",
        "from openai import AsyncOpenAI",
        "from .runtime import SandboxRunner",
        "from personal_agent import runtime",
        "from . import cli",
        "def deferred():\n    import docker",
    ],
)
def test_queue_boundary_rejects_execution_imports(source):
    checker = load_script("check_conventions")
    assert checker.import_errors(source, "worker.py")


def test_queue_boundary_allows_injected_runner_dependencies():
    checker = load_script("check_conventions")
    assert (
        checker.import_errors("from .models import Job\nfrom .store import jobs", "worker.py") == []
    )


@pytest.mark.parametrize(
    ("subject", "expected"),
    [
        ("fix(memory): preserve user preferences", True),
        ("feat!: change the task contract", True),
        ("Fixed memory.", False),
        ("fix: " + "a" * 68, False),
        ("fix: hide a second subject\nchore: bypass validation", False),
    ],
)
def test_conventional_commit_validation(subject, expected):
    assert load_script("check_commits").valid(subject) is expected


def test_ci_gate_fails_when_tests_skip(tmp_path):
    shutil.copy(ROOT / "tests/conftest.py", tmp_path / "conftest.py")
    (tmp_path / "test_skip.py").write_text(
        "import pytest\ndef test_missing_service(): pytest.skip()\n"
    )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--fail-on-skip", "-q", str(tmp_path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1, result.stdout + result.stderr
