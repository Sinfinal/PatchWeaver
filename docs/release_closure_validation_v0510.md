# PatchWeaver 封版交付收口验证报告 v0510

生成时间：`2026-05-10T05:28:04.294121+00:00`

## 1. 本轮目标

围绕赛题评审要点补齐 5 个交付缺口：百炼/FC/MCP 真实端到端验收、Web/API 端到端任务流、语义一致性抽查、文档口径校准、提交证据包。

## 2. 验证结果汇总

| 项目 | 结果 | 证据 |
| --- | --- | --- |
| 百炼/FC/MCP 网关 execute | `4/4` 动作成功 | `data/evaluations/bailian_gateway_e2e_v0510.md` |
| Web/API 真实全流程 | 新建 `TASK-20260510-001`，status=`built`，validation=`passed` | `data/evaluations/web_api_fullrun_v0510.md` |
| Web/API 证据查询 | `6/6` 接口成功 | `data/evaluations/web_api_e2e_v0510.md` |
| 语义一致性抽查 | `4` 个样例，含 3 成功 + 1 失败边界 | `docs/semantic_consistency_review_v0510.md` |
| 提交证据包 | `10` 个 task，`9` 个含 .ko，`10` 个含日志 | `data/submission/patchweaver_submission_evidence_bundle_v0510.zip` |
| 脱敏检查 | status=`passed`，findings=`0` | `data/submission/release_redaction_check_v0510_final_with_env.json` |
| FC Web 包 | `data\submission\bailian_gateway_fc_web_package_v0510.zip` | `data/submission/bailian_gateway_fc_web_package_v0510.json` |

## 3. 关键结论

- 百炼/FC/MCP 入口不再只停留在 dry-run：本轮通过网关 execute 模式访问验证机 API，完成 `status / agent_decision / report / replay` 四个动作，均返回 HTTP 200。
- Web/API 验收已覆盖真实执行链路：通过 HTTP 新建 CVE 任务，触发 analyze/run/report/replay，最终生成 `.ko` 且 validation 为 `passed`。
- 语义一致性抽查覆盖了 3 个 kpatch 约束突破成功样例和 1 个 `feature_not_enabled` 失败边界样例；该报告是工程证据抽查，仍建议人工逐行比对 patch。
- 提交证据包在验证机本地生成并下载，压缩包保留 `.ko`、`report.json`、`validation_report.json`、`rewritten.patch`、`raw_patch.patch` 和日志，避免 `.gitignore` 忽略日志导致证据丢失。
- README、第一次全流程测试报告和人工测评说明已校准口径：正向代表集达标不等于官方 Final 隐藏集承诺。

## 4. 仍需人工确认

- 百炼控制台应用链接和 FC/MCP 服务发布状态需要在真实平台页面最终确认。当前证据证明网关和 API 链路可执行，但不替代平台应用链接本身。
- 若提交外发版文档，应继续脱敏真实内网地址；本轮内部验收报告中保留验证机地址用于复现。
- 语义一致性最终仍需人工查看 `raw_patch.patch` 与 `rewritten.patch` 差异。

## 5. 本轮测试命令摘要

```bash
python -m pytest tests\integrations\test_bailian_fc_package.py tests\integrations\test_bailian_gateway.py tests\api\test_bailian_integration_router.py tests\scripts\test_deploy_patchweaver.py tests\scripts\test_validate_web_api_e2e.py tests\scripts\test_build_submission_evidence_bundle.py tests\reporter\test_submission_package.py tests\reporter\test_release_redaction.py
# 39 passed
python scripts\validate_bailian_gateway_e2e.py --task-id judge-like-v0510-20260509191933-26698 --api-base-url http://10.223.185.3:18084/api/v1 --execute
python scripts\validate_web_api_e2e.py --base-url http://10.223.185.3:18084 --task-id judge-like-v0510-20260509191933-26698
# Web/API full run: create -> analyze -> run -> report -> replay -> task_detail -> artifacts -> task_report
```
