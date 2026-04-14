# PatchWeaver 失败样例证据包

## 1. 样例概况

样例编号：

- `FAIL-20260414-01`

对应任务：

- `TASK-STAGE-II-20260414-185447`

对应 `CVE`：

- `CVE-2024-1086`

目标内核：

- `6.6.102-5.2.an23.x86_64`

远端构建机：

- `10.223.185.3`

## 2. 输入信息

本样例使用的是真实 `CVE` 输入，关键来源信息如下：

- `upstream_commit = f342de4e2f33e0e39165d8639387aa6c19dff660`
- `commit_message = netfilter: nf_tables: reject QUEUE/DROP verdict parameters`
- `affected_files = net/netfilter/nf_tables_api.c`

关键文件：

- `workspaces/TASK-STAGE-II-20260414-185447/input/patch_bundle.json`
- `workspaces/TASK-STAGE-II-20260414-185447/input/source_evidence.json`
- `workspaces/TASK-STAGE-II-20260414-185447/input/raw_patch.patch`

## 3. 主链执行情况

本样例已经完整走过下面这些阶段：

1. 任务创建
2. patch 获取与规范化
3. 语义卡片生成
4. 约束诊断
5. 上下文与提示词打包
6. 改写计划生成
7. `rewritten.patch` 落盘
8. 远端 `apply` 预检查
9. 失败归因记录
10. 报告生成
11. 回放信息生成

这说明当前样例并不是“入口就失败”，而是已经能形成完整的工程证据链。

## 4. 分析与改写产物

本样例已经生成以下关键分析和改写结果：

- `analysis/semantic_card.json`
- `analysis/constraint_report.json`
- `attempts/001/rewrite/rewrite_plan.json`
- `attempts/001/rewrite/rewritten.patch`
- `attempts/001/rewrite/rewrite_reason.json`
- `attempts/001/rewrite/transformation_trace.json`

其中 `rewrite_plan.json` 的关键信息为：

- `selected_recipe = minimal_livepatch_wrap`
- `selected_primitives = ["direct_apply"]`
- `rule_hits = ["direct_apply_ready"]`

这说明系统已经根据当前输入和规则命中情况做了受控的改写选择，而不是简单把 patch 原样透传到构建器。

## 5. 失败位置与失败类型

本样例最终失败在远端 `apply` 预检查阶段。

关键文件：

- `workspaces/TASK-STAGE-II-20260414-185447/attempts/001/rewrite/apply_precheck.json`
- `workspaces/TASK-STAGE-II-20260414-185447/attempts/001/logs/build.log`
- `workspaces/TASK-STAGE-II-20260414-185447/attempts/001/logs/failure_record.json`

核心结论如下：

- 失败类型：`patch_apply_failed`
- 失败摘要：`error: net/netfilter/nf_tables_api.c: No such file or directory`
- 参与预检查的目录：远端 `kernel_devel_dir` 对应目录

从 `build.log` 和 `doctor` 结果可以进一步确认：

- 远端主机可达
- `kpatch-build` 存在
- `.config` 存在
- `vmlinux` 存在
- 当前源码目录并不是完整内核源码树，而是回退到 `kernel-devel` 目录

因此本轮问题不属于“输入是假数据”或“模型输出全错”，而是“真实 patch 对接到了不完整源码树”。

## 6. 验证阶段结果

由于本轮没有产出 `.ko` 模块，验证阶段没有进入成功校验，而是输出了结构化待执行结果。

关键文件：

- `workspaces/TASK-STAGE-II-20260414-185447/attempts/001/artifacts/validation_report.json`

当前状态为：

- `load_result = pending`
- `unload_result = pending`
- `smoke_result = pending`
- `semantic_guard_result = pending`

这说明验证链本身已存在，只是前置构建成功条件还没有满足。

## 7. 报告与回放结果

最终报告和回放材料已生成：

- `workspaces/TASK-STAGE-II-20260414-185447/reports/report.json`
- `patchweaver_stage_test_logs/09_replay_real_cve_task.out.txt`

报告中的最终结论为：

- `final_status = failed`
- 当前共执行 `1` 轮尝试
- 最近一轮失败类型为 `patch_apply_failed`

## 8. 这个失败样例能证明什么

这个失败样例至少证明了下面几件事：

1. 项目已经能处理真实 `CVE` 输入
2. 来源链、改写链、构建链和报告链已经串起来了
3. 系统能把失败点定位到具体阶段和具体原因
4. 失败结果已经具备回放和答辩价值

对当前阶段来说，这类样例的价值并不低，因为它比“只展示架构图”更能说明系统已经开始触碰真实工程问题。

## 9. 后续修复方向

针对本样例，下一步动作已经比较清楚：

1. 在远端补齐完整内核源码树
2. 修正 `kernel_src_dir`
3. 重新执行 `apply` 预检查
4. 再进入 `kpatch-build`
5. 成功后补 `.ko`、加载、卸载和冒烟验证证据

## 10. 证据索引

| 类别 | 文件 |
| --- | --- |
| 输入 | `workspaces/TASK-STAGE-II-20260414-185447/input/patch_bundle.json` |
| 输入 | `workspaces/TASK-STAGE-II-20260414-185447/input/source_evidence.json` |
| 分析 | `workspaces/TASK-STAGE-II-20260414-185447/analysis/semantic_card.json` |
| 分析 | `workspaces/TASK-STAGE-II-20260414-185447/analysis/constraint_report.json` |
| 改写 | `workspaces/TASK-STAGE-II-20260414-185447/attempts/001/rewrite/rewrite_plan.json` |
| 改写 | `workspaces/TASK-STAGE-II-20260414-185447/attempts/001/rewrite/rewritten.patch` |
| 预检查 | `workspaces/TASK-STAGE-II-20260414-185447/attempts/001/rewrite/apply_precheck.json` |
| 构建 | `workspaces/TASK-STAGE-II-20260414-185447/attempts/001/logs/build.log` |
| 归因 | `workspaces/TASK-STAGE-II-20260414-185447/attempts/001/logs/failure_record.json` |
| 验证 | `workspaces/TASK-STAGE-II-20260414-185447/attempts/001/artifacts/validation_report.json` |
| 汇总 | `workspaces/TASK-STAGE-II-20260414-185447/reports/report.json` |


