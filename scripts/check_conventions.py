"""Small, explicit repository checks with actionable failures; not a security sandbox."""

import ast
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def import_errors(source: str, path: str) -> list[str]:
    """Keep queue/storage contracts independent of agent execution and CLI wiring."""
    forbidden = {"agents", "docker", "openai", "hud", "runtime", "cli"}
    errors = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [item.name for item in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
            if (node.level and not node.module) or node.module == "personal_agent":
                names.extend(item.name for item in node.names)
        else:
            continue
        for name in names:
            if set(name.split(".")) & forbidden:
                errors.append(
                    f"{path}:{node.lineno}: execution dependency {name!r}; "
                    "inject a runner from the CLI instead"
                )
    return errors


def check(root: Path) -> list[str]:
    errors = []
    agents_path = root / "AGENTS.md"
    agents = agents_path.read_text() if agents_path.exists() else ""
    if not agents:
        errors.append("AGENTS.md: restore the single source of contributor instructions")
    claude = root / "CLAUDE.md"
    if not claude.exists() or claude.read_text().strip() != "@AGENTS.md":
        errors.append("CLAUDE.md: keep only @AGENTS.md; put guidance in AGENTS.md")
    alias = root / ".claude/skills"
    if not alias.is_symlink() or alias.resolve() != (root / ".agents/skills").resolve():
        errors.append(".claude/skills: link to ../.agents/skills instead of duplicating skills")
    for directory in sorted((root / ".agents/skills").iterdir()):
        if not directory.is_dir():
            continue
        skill = directory / "SKILL.md"
        path = skill.relative_to(root).as_posix()
        if not skill.exists():
            errors.append(f"{path}: add a skill entrypoint")
            continue
        front = re.match(r"---\n(.*?)\n---\n", skill.read_text(), re.DOTALL)
        fields = dict(re.findall(r"^(name|description):\s*(.+)$", front[1], re.M)) if front else {}
        if fields.get("name") != directory.name or not fields.get("description", "").strip():
            errors.append(f"{path}: set matching name and a nonempty description in frontmatter")
        if path not in agents:
            errors.append(f"AGENTS.md: link {path} in the skill routing table")
    docs = [root / name for name in ("AGENTS.md", "README.md", "CONTRIBUTING.md")]
    docs += list((root / "docs").rglob("*.md"))
    docs += list((root / ".agents/skills").rglob("*.md"))
    docs += list((root / ".github").glob("*.md"))
    for doc in docs:
        if not doc.exists():
            errors.append(f"{doc.relative_to(root)}: restore this contributor entrypoint")
            continue
        for match in re.finditer(r"\]\(([^\s)]+)\)", doc.read_text()):
            target = match[1].split("#")[0]
            if target and not re.match(r"[a-z]+:", target) and not (doc.parent / target).exists():
                errors.append(f"{doc.relative_to(root)}: fix broken relative link {target}")
    # AST checks keep these deterministic modules independent of execution providers.
    # Adding the memory fixture here extends the existing CI rule to the new module.
    for name in (
        "models",
        "store",
        "worker",
        "control",
        "evaluation/world",
        "evaluation/grading",
        "evaluation/episode",
        "evaluation/reference",
        "evaluation/memory",
    ):
        path = f"src/personal_agent/{name}.py"
        errors.extend(import_errors((root / path).read_text(), path))
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0")
    for path in tracked:
        parts = Path(path).parts
        if any(p in {".agent-data", ".venv", "eval-results", ".hud"} for p in parts) or any(
            (p == ".env" or p.startswith(".env.")) and p != ".env.example" for p in parts
        ):
            errors.append(f"{path}: untrack private data or environment files")
    return errors


if __name__ == "__main__":
    problems = check(ROOT)
    for problem in problems:
        print(problem)
    if problems:
        raise SystemExit(1)
    print("Repository conventions passed")
