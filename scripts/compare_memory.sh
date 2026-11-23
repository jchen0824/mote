#!/usr/bin/env bash
# Run from the repository root. Only execute reviewed revisions with live credentials.
set -euo pipefail
base=$(git rev-parse --verify "${1:-origin/main}^{commit}")
candidate=$(git rev-parse --verify "${2:-HEAD}^{commit}")
actor=${MEMORY_COMPARE_ACTOR:-sandbox}
case "$actor" in sandbox|reference) ;; *) exit 2 ;; esac
root=$(pwd)
mkdir -p "$root/eval-results"
out=$(mktemp -d "$root/eval-results/comparison-XXXXXXXX")
scratch=$(mktemp -d)
cleanup() {
  for side in main pr; do
    git worktree remove --force "$scratch/$side" 2>/dev/null || true
  done
  rm -rf "$scratch"
}
trap cleanup EXIT
git worktree add --quiet --detach "$scratch/main" "$base"
git worktree add --quiet --detach "$scratch/pr" "$candidate"
# Both targets run the candidate's complete evaluation package, including provenance helpers.
rm -rf "$scratch/main/src/personal_agent/evaluation"
cp -R "$scratch/pr/src/personal_agent/evaluation" "$scratch/main/src/personal_agent/"
echo "Comparison reports: $out"
for side in main pr; do
  (cd "$scratch/$side" && uv sync --locked --extra eval)
done
status=0
for seed in 0 1 2; do
  sides=(main pr)
  if ((seed % 2)); then sides=(pr main); fi
  for side in "${sides[@]}"; do
    # The older baseline need not have a memory CLI entry point in its package metadata.
    (cd "$scratch/$side" && .venv/bin/python -c \
      'from personal_agent.evaluation.memory_cli import main; main()' \
      --actor "$actor" --backend hud --memory both --seed "$seed" \
      --output-dir "$out/$seed/$side") || status=1
  done
done
python3 "$root/scripts/memory_comparison_report.py" "$out" "$base" "$candidate" "$actor" || status=1
exit "$status"
