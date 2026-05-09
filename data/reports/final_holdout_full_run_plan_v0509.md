# PatchWeaver Final 风格 Holdout Full Run 复测计划

日期：2026-05-09

范围：只准备和执行 PatchWeaver holdout/full-run 复测；不触碰百炼、FC、MCP 部署文件。

## 1. 候选结论

优先使用 `evaluations/fixtures/final_holdout_full_candidates_v0509.json` 中的 5 条样例：

| CVE | 子系统 | 选择原因 | 已有证据 |
| --- | --- | --- | --- |
| CVE-2024-26698 | drivers/net | v0507 新增 full-run positive；livepatchability 100/high；stable baseline prepared | `s1full0507-26698` 已 built + validation passed |
| CVE-2024-26693 | drivers/net | v0507 新增 full-run positive；livepatchability 100/high；stable baseline prepared | `s1full0507-26693` 已 built + validation passed |
| CVE-2024-26694 | drivers/net | v0507 新增 full-run positive；livepatchability 100/high；stable baseline prepared | `s1full0507-26694` 已 built + validation passed |
| CVE-2024-26615 | net/smc | v0507 新增 full-run positive；补足非 drivers/net 覆盖 | `s1full0507-26615` 已 built + validation passed |
| CVE-2024-26791 | fs/btrfs | v0507 新增 full-run positive；补足 filesystem 覆盖 | `s1full0507-26791` 已 built + validation passed |

备选第 6 条：`CVE-2024-26726`。它覆盖 `semantic_guard_rewrite`/`fs/btrfs` 路线且已通过 `s3sgpoolrerun0507-26726`，但报告中说明该成功偏 `pass_through`，所以不放入默认 5 条，适合专项复测。

## 2. 已执行的本地受控验证

本地只执行 dry-run/metadata 级命令，不触发 kpatch-build：

```powershell
$job = Start-Job -ScriptBlock { Set-Location 'D:\spaces\ai\PatchWeaver'; python scripts/run_holdout_blind.py --fixture evaluations/fixtures/challenge_positive_pool_confirmed_v0426.json --output data/evaluations/final_holdout_positive_pool_dry_run_v0509.json --mode dry-run }; if (Wait-Job $job -Timeout 30) { Receive-Job $job; Remove-Job $job; exit 0 } else { Stop-Job $job; Remove-Job $job; Write-Error 'timeout after 30s'; exit 124 }
```

结果：`holdout summary written: data\evaluations\final_holdout_positive_pool_dry_run_v0509.json`，`status=passed`，`total_cases=12`。限制：该脚本明确 `No kpatch-build command is invoked`。

## 3. 验证机 full run 命令

在验证机 `/home/patchweaver/current` 执行。所有命令都带外层 `timeout`，脚本内部也有 create/analyze/run/stable-baseline 分阶段 timeout。

### 3.1 预检

```bash
cd /home/patchweaver/current
timeout 30s python scripts/run_holdout_blind.py \
  --fixture evaluations/fixtures/final_holdout_full_candidates_v0509.json \
  --output data/evaluations/final_holdout_candidates_blind_dry_run_v0509.json \
  --mode dry-run
```

```bash
cd /home/patchweaver/current
timeout 30s python -m json.tool evaluations/fixtures/final_holdout_full_candidates_v0509.json >/tmp/final_holdout_full_candidates_v0509.json.checked
```

### 3.2 5 条样例 full run

```bash
cd /home/patchweaver/current
timeout 5400s python scripts/screen_challenge_pool.py \
  --mode full \
  --profile demo \
  --task-prefix finalholdout0509 \
  --fixture evaluations/fixtures/final_holdout_full_candidates_v0509.json \
  --output data/evaluations/final_holdout_full_run_v0509.json \
  --report-md data/evaluations/final_holdout_full_run_v0509.md \
  --max-run-attempts 1 \
  --create-timeout-sec 120 \
  --analyze-timeout-sec 600 \
  --run-timeout-sec 900 \
  --stable-baseline-timeout-sec 900 \
  --prepare-stable-baseline \
  --only-positive-candidates \
  --min-livepatchability-score 75 \
  --only-high-livepatchability
```

### 3.3 复测后证据 manifest

```bash
cd /home/patchweaver/current
timeout 120s python scripts/build_positive_pool_evidence_manifest.py \
  --fixture evaluations/fixtures/final_holdout_full_candidates_v0509.json \
  --workspace-root /home/patchweaver/current/workspaces \
  --output data/manifests/final_holdout_full_evidence_manifest_v0509.json
```

### 3.4 快速验收读取

```bash
cd /home/patchweaver/current
timeout 30s python - <<'PY'
import json
from pathlib import Path
summary = json.loads(Path("data/evaluations/final_holdout_full_run_v0509.json").read_text(encoding="utf-8"))["summary"]
manifest = json.loads(Path("data/manifests/final_holdout_full_evidence_manifest_v0509.json").read_text(encoding="utf-8"))
print("representative_total=", summary.get("representative_total"))
print("representative_success_rate=", summary.get("representative_success_rate"))
print("average_attempts=", summary.get("average_attempts"))
print("manifest_complete=", manifest.get("complete"), "/", manifest.get("total"))
for entry in manifest.get("entries", []):
    print(entry.get("cve_id"), entry.get("status"), entry.get("validation_status"), entry.get("module_path"))
PY
```

## 4. 证据缺口

当前正确验证机为 `10.223.185.3`，账号为 `root`。旧的预配置 SSH 目标已不再使用，不能作为验证机入口。因此本轮先完成本地 dry-run、候选 fixture、命令设计和已有 manifest 证据整理，后续 full run 应通过 `10.223.185.3` 执行。

full run 完成前仍缺：

1. `data/evaluations/final_holdout_full_run_v0509.json`
2. `data/evaluations/final_holdout_full_run_v0509.md`
3. `data/manifests/final_holdout_full_evidence_manifest_v0509.json`
4. 每条 `finalholdout0509-*` 工作区中的 `.ko`、`build_summary.json`、`validation_report.json`、`repair_intent.json`、`rewritten.patch`、`semantic_guard.json`、`report.json`

## 5. 成功判定

建议验收口径：

1. `representative_total=5`
2. `representative_success_rate >= 0.60`
3. `average_attempts <= 5`
4. evidence manifest `complete=total=5`
5. 每条 `.ko` 的 `vermagic` 匹配 `6.6.102-5.2.an23.x86_64`
6. `validation_status=passed`，且报告包含 load/unload/smoke/selftest 证据
