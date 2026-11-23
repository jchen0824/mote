"""Compare matched probe outcomes; keep infrastructure failures distinct from recall losses."""

import json
import sys
from pathlib import Path


def summarize(root: Path, base: str, candidate: str, actor: str) -> bool:
    lines = [
        "# Memory comparison",
        "",
        f"main `{base}` · PR `{candidate}` · actor `{actor}`",
        "",
        "| Seed | Workspace | Probe | main | PR | Result |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    valid = True
    for seed in range(3):
        for mode in ("persistent", "reset"):
            reports = []
            comparable = True
            for side, sha in (("main", base), ("pr", candidate)):
                paths = list((root / str(seed) / side).glob(f"*/{mode}/report.json"))
                report = json.loads(paths[0].read_text()) if len(paths) == 1 else {}
                reports.append(report)
                if not (
                    report.get("status") == "completed"
                    and report.get("actor") == actor
                    and report.get("backend") == "hud"
                    and report.get("memory_mode") == mode
                    and report.get("seed") == seed
                    and report.get("provenance", {}).get("git_commit") == sha
                ):
                    comparable = False
            fields = ("model", "scenario_sha256", "actor_prompt", "grader", "limits")
            comparable = (
                comparable
                and all(all(k in r for k in fields) and r["status"] == "completed" for r in reports)
                and all(reports[0][k] == reports[1][k] for k in fields)
            )
            for probe in ("retention_correct", "revision_correct", "stale_preference_recalled"):
                values = [r.get("result", {}).get("metrics", {}).get(probe) for r in reports]
                if not comparable or any(type(v) is not bool for v in values):
                    result = "inconclusive"
                    valid = False
                elif probe == "stale_preference_recalled":
                    result = (
                        "unchanged"
                        if values[0] == values[1]
                        else ("new stale recall" if values[1] else "stale recall cleared")
                    )
                elif mode == "reset" and any(values):
                    result = "check reset control"
                elif values == [True, False]:
                    result = "lost recall"
                elif values == [False, True]:
                    result = "gained recall"
                else:
                    result = "unchanged"
                cells = [
                    str(v)
                    if r.get("status") == "completed" and v is not None
                    else r.get("status", "missing")
                    for v, r in zip(values, reports, strict=True)
                ]
                lines.append(f"| {seed} | {mode} | {probe} | {cells[0]} | {cells[1]} | {result} |")
    lines.append("\n" + ("All pairs completed." if valid else "Incomplete or mismatched evidence."))
    summary = "\n".join(lines) + "\n"
    (root / "summary.md").write_text(summary)
    print(summary)
    return valid


if __name__ == "__main__":
    raise SystemExit(0 if summarize(Path(sys.argv[1]), *sys.argv[2:]) else 1)
