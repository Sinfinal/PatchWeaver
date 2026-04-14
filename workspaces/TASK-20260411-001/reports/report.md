# PatchWeaver 任务报告

- 最终状态: failed

## 任务摘要
- task_id: TASK-20260411-001
- cve_id: CVE-2024-0001
- target_kernel: 6.6.102-5.2.an23.x86_64

## 尝试摘要
- 第 1 轮: failed (build_env_missing)
- 第 2 轮: failed (compile_failed)
- 第 3 轮: failed (patch_apply_failed)
- 第 4 轮: failed (patch_apply_failed)
- 第 5 轮: failed (patch_apply_failed)

## 说明
- 当前共执行 5 轮尝试。
- 分析、归因和报告阶段按只读路径整理证据，改写与构建阶段走写入独占路径。
- 当前成功率为 0%，已归档产物类型 47 类。
- 最近一轮结果为 failed，失败类型为 patch_apply_failed。
