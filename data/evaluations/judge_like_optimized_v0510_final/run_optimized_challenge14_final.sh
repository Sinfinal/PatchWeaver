#!/usr/bin/env bash
set -u
cd /home/patchweaver/current
export PYTHONIOENCODING=utf-8
export PYTHONUTF8=1
OUT="data/evaluations/judge_like_optimized_v0510_final"
echo "[$(date -Is)] OPT_CHALLENGE14_FINAL_START" | tee -a "$OUT/run.log"
python scripts/screen_challenge_pool.py \
  --mode full \
  --profile demo \
  --task-prefix "judge-like-challenge14final-2026050920" \
  --fixture evaluations/fixtures/challenge_sample_tiers_v0426.json \
  --max-cases 14 \
  --output "$OUT/challenge14final.json" \
  --report-md "$OUT/challenge14final.md" \
  --max-run-attempts 2 \
  --run-timeout-sec 900 \
  --stable-baseline-timeout-sec 300 \
  --prepare-stable-baseline \
  --positive-pool-fixture evaluations/fixtures/challenge_positive_pool_confirmed_v0426.json \
  --rag-seed-fixture evaluations/fixtures/rag_seed_linux_kernel_2024_batch200.json \
  --known-kpatch-constraint-fixture evaluations/fixtures/challenge_kpatch_constraint_pool_v0427.json \
  > "$OUT/challenge14final.stdout.log" \
  2> "$OUT/challenge14final.stderr.log"
STATUS=$?
echo "[$(date -Is)] OPT_CHALLENGE14_FINAL_END status=$STATUS" | tee -a "$OUT/run.log"
exit $STATUS
