#!/usr/bin/env bash
set -u
cd /home/patchweaver/current
export PYTHONIOENCODING=utf-8
export PYTHONUTF8=1
STAMP=20260509191933
SUITE="data/evaluations/judge_like_suite_v0510_${STAMP}"
CURRENT_PID=522086
log() { echo "[$(date -Is)] $*" | tee -a "$SUITE/suite.log"; }
run_round() {
  local name="$1"; shift
  log "ROUND_START $name"
  "$@" > "$SUITE/${name}.stdout.log" 2> "$SUITE/${name}.stderr.log"
  local status=$?
  log "ROUND_END $name status=$status"
  return $status
}
log "SUITE_START"
if ps -p "$CURRENT_PID" >/dev/null 2>&1; then
  log "waiting_existing_holdout pid=$CURRENT_PID"
  while ps -p "$CURRENT_PID" >/dev/null 2>&1; do sleep 30; done
fi
log "existing_holdout_finished_or_absent"
run_round positive12 python scripts/screen_challenge_pool.py   --mode full   --profile demo   --task-prefix "judge-like-positive12-${STAMP}"   --fixture evaluations/fixtures/challenge_positive_pool_confirmed_v0426.json   --max-cases 12   --output "$SUITE/positive12.json"   --report-md "$SUITE/positive12.md"   --max-run-attempts 1   --run-timeout-sec 900   --stable-baseline-timeout-sec 300   --prepare-stable-baseline   --positive-pool-fixture evaluations/fixtures/challenge_positive_pool_confirmed_v0426.json   --rag-seed-fixture evaluations/fixtures/rag_seed_linux_kernel_2024_batch200.json   --known-kpatch-constraint-fixture evaluations/fixtures/challenge_kpatch_constraint_pool_v0427.json   --include-known-pool-cases || true
run_round challenge14 python scripts/screen_challenge_pool.py   --mode full   --profile demo   --task-prefix "judge-like-challenge14-${STAMP}"   --fixture evaluations/fixtures/challenge_sample_tiers_v0426.json   --max-cases 14   --output "$SUITE/challenge14.json"   --report-md "$SUITE/challenge14.md"   --max-run-attempts 3   --run-timeout-sec 900   --stable-baseline-timeout-sec 300   --prepare-stable-baseline   --positive-pool-fixture evaluations/fixtures/challenge_positive_pool_confirmed_v0426.json   --rag-seed-fixture evaluations/fixtures/rag_seed_linux_kernel_2024_batch200.json   --known-kpatch-constraint-fixture evaluations/fixtures/challenge_kpatch_constraint_pool_v0427.json || true
run_round kpatch6 python scripts/screen_challenge_pool.py   --mode full   --profile demo   --task-prefix "judge-like-kpatch6-${STAMP}"   --fixture evaluations/fixtures/challenge_kpatch_constraint_pool_v0427.json   --max-cases 6   --output "$SUITE/kpatch6.json"   --report-md "$SUITE/kpatch6.md"   --max-run-attempts 3   --run-timeout-sec 900   --stable-baseline-timeout-sec 300   --prepare-stable-baseline   --positive-pool-fixture evaluations/fixtures/challenge_positive_pool_confirmed_v0426.json   --rag-seed-fixture evaluations/fixtures/rag_seed_linux_kernel_2024_batch200.json   --known-kpatch-constraint-fixture evaluations/fixtures/challenge_kpatch_constraint_pool_v0427.json   --include-known-pool-cases || true
python - <<'PY' > "$SUITE/suite_audit.json"
import json, glob, os
from pathlib import Path
root=Path('/home/patchweaver/current')
suite=root/'data/evaluations/judge_like_suite_v0510_20260509191933'
files=[root/'data/evaluations/judge_like_v0510_20260509191933/judge_like_full5.json', suite/'positive12.json', suite/'challenge14.json', suite/'kpatch6.json']
summary={'suite':str(suite),'rounds':[]}
for fp in files:
    round_sum={'file':str(fp),'exists':fp.exists()}
    if fp.exists():
        try:
            data=json.loads(fp.read_text(encoding='utf-8'))
            round_sum['summary']=data.get('summary') or data.get('metrics') or {}
            items=data.get('cases') or data.get('results') or data.get('items') or []
            round_sum['count']=len(items)
            statuses={}
            passed=0; ko=0
            for item in items:
                s=item.get('status') or item.get('final_status') or item.get('build_status') or item.get('validation_status') or 'unknown'
                statuses[s]=statuses.get(s,0)+1
                task=item.get('task_id') or item.get('task')
                if task:
                    ws=root/'workspaces'/task
                    if list(ws.rglob('*.ko')): ko+=1
                    vals=list(ws.rglob('validation_report.json'))
                    if vals:
                        try:
                            vp=json.loads(vals[-1].read_text(encoding='utf-8'))
                            if vp.get('status') == 'passed': passed+=1
                        except Exception: pass
            round_sum['status_counts']=statuses
            round_sum['ko_tasks']=ko
            round_sum['validation_passed_tasks']=passed
        except Exception as e:
            round_sum['error']=repr(e)
    summary['rounds'].append(round_sum)
print(json.dumps(summary, ensure_ascii=False, indent=2))
PY
log "SUITE_DONE"
