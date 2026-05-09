#!/usr/bin/env bash
set -u
cd /home/patchweaver/current
export PYTHONIOENCODING=utf-8
export PYTHONUTF8=1
STAMP=20260509191933
echo "[START] $(date -Is) judge-like full-flow test"
echo "[ENV] kernel=$(uname -r)"
python -m patchweaver doctor --json > "data/evaluations/judge_like_v0510_${STAMP}/doctor.json" 2>&1 || true
python -m patchweaver paths --json > "data/evaluations/judge_like_v0510_${STAMP}/paths.json" 2>&1 || true
python -m patchweaver check-vendor-baseline --json > "data/evaluations/judge_like_v0510_${STAMP}/vendor_baseline.json" 2>&1 || true
curl -s http://127.0.0.1:18084/api/v1/overview > "data/evaluations/judge_like_v0510_${STAMP}/api_overview_before.json" || true
python scripts/screen_challenge_pool.py   --mode full   --profile demo   --task-prefix "judge-like-v0510-${STAMP}"   --fixture evaluations/fixtures/final_holdout_full_candidates_v0509.json   --max-cases 5   --output "data/evaluations/judge_like_v0510_${STAMP}/judge_like_full5.json"   --report-md "data/evaluations/judge_like_v0510_${STAMP}/judge_like_full5.md"   --max-run-attempts 3   --run-timeout-sec 900   --stable-baseline-timeout-sec 300   --prepare-stable-baseline   --positive-pool-fixture evaluations/fixtures/challenge_positive_pool_confirmed_v0426.json   --rag-seed-fixture evaluations/fixtures/rag_seed_linux_kernel_2024_batch200.json   --known-kpatch-constraint-fixture evaluations/fixtures/challenge_kpatch_constraint_pool_v0427.json
RUN_STATUS=$?
echo "[RUN_STATUS] $RUN_STATUS"
curl -s http://127.0.0.1:18084/api/v1/overview > "data/evaluations/judge_like_v0510_${STAMP}/api_overview_after.json" || true
python - <<'PY' > "data/evaluations/judge_like_v0510_20260509191933/artifact_audit.json"
import json
from pathlib import Path
root=Path('/home/patchweaver/current')
run_dir=root/'data/evaluations/judge_like_v0510_20260509191933'
result_path=run_dir/'judge_like_full5.json'
summary={'result_path':str(result_path),'tasks':[]}
try:
    data=json.loads(result_path.read_text(encoding='utf-8'))
except Exception as e:
    summary['error']=repr(e)
    print(json.dumps(summary,ensure_ascii=False,indent=2)); raise SystemExit(0)
items=data.get('cases') or data.get('results') or data.get('items') or []
for item in items:
    task=item.get('task_id') or item.get('task') or item.get('taskId')
    cve=item.get('cve_id') or item.get('cve')
    entry={'cve':cve,'task_id':task}
    if task:
        ws=root/'workspaces'/task
        entry['workspace_exists']=ws.exists()
        entry['ko_files']=[str(p.relative_to(ws)) for p in ws.rglob('*.ko')] if ws.exists() else []
        for name in ['repair_intent.json','semantic_card.json','constraint_report.json','rewritten.patch','build_summary.json','validation_report.json','failure_record.json','report.json','report.md']:
            found=list(ws.rglob(name)) if ws.exists() else []
            entry[name]=[str(p.relative_to(ws)) for p in found[:5]]
    summary['tasks'].append(entry)
print(json.dumps(summary,ensure_ascii=False,indent=2))
PY
exit $RUN_STATUS
