"""Validate PR titles and commit subjects without interpolating them into shell code."""

import argparse
import json
import re
import subprocess
from pathlib import Path

PATTERN = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)"
    r"(\([a-z][a-z0-9-]*\))?!?: [a-z0-9][^\n]*[^.\s]$"
)


def valid(subject: str) -> bool:
    return len(subject) <= 72 and PATTERN.fullmatch(subject) is not None


def main() -> None:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--message")
    source.add_argument("--event", type=Path)
    args = parser.parse_args()
    if args.message is not None:
        subjects = [args.message]
    else:
        pr = json.loads(args.event.read_text())["pull_request"]
        base, head = pr["base"]["sha"], pr["head"]["sha"]
        if not all(re.fullmatch(r"[0-9a-f]{40}", sha) for sha in (base, head)):
            raise SystemExit("Invalid GitHub commit SHA")
        subjects = [pr["title"]]
        subjects += subprocess.check_output(
            ["git", "log", "--no-merges", "--format=%s", f"{base}..{head}"], text=True
        ).splitlines()
    errors = [subject for subject in subjects if not valid(subject)]
    if errors:
        for subject in errors:
            print(f"Invalid subject: {subject!r}")
        raise SystemExit("Use type(scope): lower-case summary, <=72 characters, no final period")
    print("Conventional commit subjects passed")


if __name__ == "__main__":
    main()
