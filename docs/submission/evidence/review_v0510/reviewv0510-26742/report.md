# PatchWeaver 任务报告

- 最终状态: built

## 任务摘要
- task_id: reviewv0510-26742
- cve_id: CVE-2024-26742
- target_kernel: 6.6.102-5.2.an23.x86_64
- profile_name: demo
- workspace_dir: workspaces/reviewv0510-26742

## 尝试摘要
- 第 1 轮: built (无) / build_exec_status=executed

## 分析结果
- semantic_card_path: workspaces/reviewv0510-26742/analysis/semantic_card.json
- constraint_report_path: workspaces/reviewv0510-26742/analysis/constraint_report.json
- patch_bundle_path: workspaces/reviewv0510-26742/input/patch_bundle.json

## 构建结果
- latest_attempt_id: reviewv0510-26742-A001
- latest_attempt_status: built
- latest_failure_type: None
- latest_build_exec_status: executed
- latest_target_state: None
- build_log_path: workspaces/reviewv0510-26742/attempts/001/logs/build.log
- module_path: workspaces/reviewv0510-26742/attempts/001/output/patchweaver-reviewv0510-26742-001.ko
- rewritten_patch_path: workspaces/reviewv0510-26742/attempts/001/rewrite/rewritten.patch

## 验证结果
- validation_report_path: workspaces/reviewv0510-26742/attempts/001/artifacts/validation_report.json
- validation_matrix_path: workspaces/reviewv0510-26742/attempts/001/artifacts/validation_matrix.json
- semantic_guard_path: workspaces/reviewv0510-26742/attempts/001/artifacts/semantic_guard.json
- validation_status: passed
- validation_intensity: standard
- semantic_guard_status: passed
- load_status: passed
- unload_status: passed
- smoke_status: passed
- selftest_status: passed
- regression_status: skipped

## 闭环状态
- closure_type: success
- closure_status: ready
- failure_replay_ready: False
- success_replay_ready: True
- validation_status: passed
- missing_success_evidence: []
- recommended_replay_files: ['workspaces/reviewv0510-26742/attempts/001/trace/harness_trace.json', 'workspaces/reviewv0510-26742/attempts/001/rewrite/rewritten.patch', 'workspaces/reviewv0510-26742/attempts/001/logs/build.log', 'workspaces/reviewv0510-26742/attempts/001/artifacts/validation_report.json', 'workspaces/reviewv0510-26742/attempts/001/artifacts/validation_matrix.json', 'workspaces/reviewv0510-26742/attempts/001/logs/selftest.log', 'workspaces/reviewv0510-26742/attempts/001/logs/load.log', 'workspaces/reviewv0510-26742/attempts/001/logs/unload.log', 'workspaces/reviewv0510-26742/attempts/001/logs/smoke.log', 'workspaces/reviewv0510-26742/attempts/001/logs/regression.log']

## 回放索引
- trace_path: workspaces/reviewv0510-26742/attempts/001/trace/harness_trace.json
- failover_record_path: None
- evaluation_summary_path: workspaces/reviewv0510-26742/reports/evaluation_summary.json
- recommended_replay_files: ['workspaces/reviewv0510-26742/attempts/001/trace/harness_trace.json', 'workspaces/reviewv0510-26742/attempts/001/rewrite/rewritten.patch', 'workspaces/reviewv0510-26742/attempts/001/logs/build.log', 'workspaces/reviewv0510-26742/attempts/001/artifacts/validation_report.json', 'workspaces/reviewv0510-26742/attempts/001/artifacts/validation_matrix.json', 'workspaces/reviewv0510-26742/attempts/001/logs/selftest.log', 'workspaces/reviewv0510-26742/attempts/001/logs/load.log', 'workspaces/reviewv0510-26742/attempts/001/logs/unload.log', 'workspaces/reviewv0510-26742/attempts/001/logs/smoke.log', 'workspaces/reviewv0510-26742/attempts/001/logs/regression.log']

## Agent Decision Summary
- RepairIntent strategy: semantic_guard
- RepairIntent root_cause: pqi_map_queues 中存在条件判断或状态转换缺陷，修复围绕条件 `!ctrl_info->disable_managed_interrupts` 展开。 依据：[ Upstream commit 5761eb9761d2d5fe8248a9b719efc4d8baf1f24a ]
- selected_recipe: semantic_guard_rewrite
- selected_strategy: unknown
- strategy_switched: True
- strategy_reason: 优先选择综合得分最高的候选，当前命中 semantic_guard_rewrite，排序得分 0.837
- failure_type: none
- failure_summary: 构建阶段已完成。
- agent_next_action: none

## 关键路径
- report_json: workspaces/reviewv0510-26742/reports/report.json
- report_md: workspaces/reviewv0510-26742/reports/report.md
- workspace_dir: workspaces/reviewv0510-26742
- report_trace: workspaces/reviewv0510-26742/attempts/001/trace/harness_trace.json
- report_build_log: workspaces/reviewv0510-26742/attempts/001/logs/build.log

## 评测摘要
- total_attempts: 1
- built_attempts: 1
- failed_attempts: 0
- success_rate: 1.0
- average_attempt_no: 1.0
- latest_status: built
- latest_failure_type: None
- failure_breakdown: {}
- artifact_type_counts: {'task_context': 1, 'raw_patch': 1, 'normalized_patch': 1, 'patch_bundle': 1, 'source_evidence': 1, 'source_fetch_trace': 1, 'semantic_card': 1, 'semantic_card_enrichment': 1, 'repair_intent': 2, 'constraint_report': 1, 'analysis_bootstrap_manifest': 1, 'analysis_evidence_bundle': 1, 'analysis_context_bundle': 1, 'retrieval_skill_route': 1, 'retrieval_prompt_packet': 1, 'semantic_card_skill_route': 1, 'semantic_card_prompt_packet': 1, 'constraint_skill_route': 1, 'constraint_prompt_packet': 1, 'analysis_trace': 1, 'rewrite_bootstrap_manifest': 1, 'rewrite_evidence_bundle': 1, 'rewrite_context_bundle': 1, 'rewrite_skill_route': 1, 'rewrite_prompt_packet': 1, 'rewrite_plan': 1, 'planning_hints': 1, 'route_effectiveness': 1, 'rewritten_patch': 1, 'rewrite_reason': 1, 'transformation_trace': 1, 'apply_precheck': 1, 'semantic_guard_rewrite': 1, 'environment_check_log': 1, 'build_log': 1, 'build_precheck': 1, 'build_summary': 1, 'failure_record': 1, 'failure_memory_snapshot': 1, 'recipe_memory_snapshot': 1, 'validate_log': 1, 'semantic_precheck': 1, 'semantic_guard': 1, 'validation_matrix': 1, 'selftest_log': 1, 'load_log': 1, 'unload_log': 1, 'smoke_log': 1, 'regression_log': 1, 'regression_summary': 1, 'validation_report': 1, 'validation_evidence_bundle': 1, 'validation_context_bundle': 1, 'validation_skill_route': 1, 'validation_prompt_packet': 1, 'attempt_state': 1, 'harness_trace': 1}

## 说明
- 当前共执行 1 轮尝试。
- 分析、归因和报告阶段按只读路径整理证据，改写与构建阶段走写入独占路径。
- 当前成功率为 100%，已归档产物类型 57 类。
- 最近一轮结果为 built，失败类型为 无。

## 下一步
- next_priority_layer: freeze
- next_action: 当前任务已具备成功回放闭环，优先固化样例、脚本和验收材料
