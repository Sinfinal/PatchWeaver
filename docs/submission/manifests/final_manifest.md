# PatchWeaver Final Manifest

- 生成时间: 2026-05-10T08:36:14.584252+00:00
- 默认内核: 6.6.102-5.2.an23.x86_64
- 模型拓扑: single_primary_with_optional_helpers
- 主模型: qwen-plus-2025-07-28
- 正式交付模型: qwen-plus-2025-07-28
- API Key 来源: 未配置

## 提交快照目录
- docs: docs
- slides: docs/submission/slides
- video: docs/submission/video
- evidence: docs/submission/evidence
- manifests: docs/submission/manifests

## 模型说明
- code_assistant: qwen-coder-turbo-0919 / 用于草拟局部改写提示、模板和代码片段，不直接决定最终放行结果。
- vision: qwen-vl-plus-2025-05-07 / 用于截图识别、页面检查和演示材料辅助场景。
- log_summary: qwen-plus-2025-07-28 / 用于长日志压缩、失败解释和材料摘要，不直接替代构建判定。

## 文档清单
- PatchWeaver-模型选型说明.md: docs/PatchWeaver-模型选型说明.md / 类别 delivery_note / 版本 unversioned / 已复核 False
- PatchWeaver-百炼应用落地说明.md: docs/PatchWeaver-百炼应用落地说明.md / 类别 delivery_note / 版本 unversioned / 已复核 False
- deployment.md: docs/deployment.md / 类别 document / 版本 unversioned / 已复核 False
- web_api_e2e_validation.md: docs/web_api_e2e_validation.md / 类别 document / 版本 unversioned / 已复核 False
- README.md: README.md / 类别 readme / 版本 unversioned / 已复核 False

## 阶段评测摘要
- challenge_positive_pool_confirmed_v0426: 正向桶动态验证通过率 0.00% / .ko 产出率 0.00%
- challenge_sample_tiers_v0426: 正向桶动态验证通过率 0.00% / .ko 产出率 0.00%
- contest_samples: 兼容总成功率 0.00%
- validation_v0509/representative_metrics_report_v0509: 兼容总成功率 100.00%
- validation_v0509/representative_metrics_v0510: 兼容总成功率 100.00%
- review_v0510/review_26726_full: 兼容总成功率 100.00%
- review_v0510/review_26742_full: 兼容总成功率 100.00%
- review_v0510/review_complex2_full: 兼容总成功率 100.00%
- review_v0510/review_extra3_full: 兼容总成功率 100.00%
- validation_v0509/final_holdout10_full_run_v0509: 兼容总成功率 100.00%
- validation_v0509/final_holdout_full_run_v0509: 兼容总成功率 100.00%

## 任务闭环情况
- local-envroot-smoke-26742: 闭环 False / 状态 created / 报告 无
- local-api-doc-smoke-26742: 闭环 False / 状态 created / 报告 无
- local-readme-smoke-26742: 闭环 False / 状态 created / 报告 无
- TASK-SEED-20260420-1086: 闭环 False / 状态 analyzed / 报告 无
- TASK-STAGE-II-20260414-185447: 闭环 True / 状态 failed / 报告 workspaces/TASK-STAGE-II-20260414-185447/reports/report.json
- TASK-20260411-001: 闭环 True / 状态 failed / 报告 workspaces/TASK-20260411-001/reports/report.json
- TASK-20260410-001: 闭环 False / 状态 failed / 报告 workspaces/TASK-20260410-001/reports/report.json

## 当前限制
- 百炼 API Key 尚未配置，可通过环境变量或 config/models.yaml 补齐。
