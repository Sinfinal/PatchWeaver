# PatchWeaver Challenge 正向样例池筛选报告

## 1. 执行参数

- mode: `analyze`
- profile: `dev`
- task_prefix: `p1next0507`
- run_timeout_sec: `900`
- only_positive_candidates: `False`
- min_livepatchability_score: `75`
- only_high_livepatchability: `True`
- workspace_root: `/home/patchweaver/current/workspaces`

## 2. 汇总

- total_cases: `12`
- confirmed_positive_acceptance: `0`
- positive_pool_candidates: `2`
- stable_bucket_ready: `6`
- current_positive_pool_size: `6`
- positive_pool_target: `10`
- positive_pool_gap: `4`
- representative_success_rate: `0%`
- average_attempts: `0.0`
- rag_seed_hits: `12`
- known_pool_skipped: `0`
- stable_source_alignment_required: `0`
- stable_baseline_prepared: `0`
- minimal_config_fragments: `11`
- livepatchability_high: `2`

### bucket_counts

- `buildable_and_should_pass`: `2`
- `feature_not_enabled`: `4`
- `unbucketed`: `6`

### livepatchability_tier_counts

- `high`: `2`
- `low`: `9`
- `medium`: `1`

### rag_subsystem_counts

- `drivers/hwmon`: `1`
- `drivers/net`: `6`
- `drivers/phy`: `1`
- `drivers/spi`: `1`
- `drivers/usb`: `3`

## 3. 逐样例结果

| CVE | task_id | livepatchability | bucket | tier | rag_subsystem | failure_type | source_alignment | agent_next_action | build | validation | reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CVE-2024-26793 | `p1next0507-26793` | `0/low` | `` | `development_only_high_risk` | `drivers/net` | `` | `` | `` | `` | `` | 分析结果显示改写风险偏高，暂不作为正向验收样例 |
| CVE-2024-26754 | `p1next0507-26754` | `0/low` | `` | `development_only_high_risk` | `drivers/net` | `` | `` | `` | `` | `` | 分析结果显示改写风险偏高，暂不作为正向验收样例 |
| CVE-2024-26747 | `p1next0507-26747` | `0/low` | `` | `development_only_high_risk` | `drivers/usb` | `` | `` | `` | `` | `` | 分析结果显示改写风险偏高，暂不作为正向验收样例 |
| CVE-2024-26716 | `p1next0507-26716` | `52/medium` | `` | `deferred_vmlinux_target` | `drivers/usb` | `` | `` | `` | `` | `` | 低风险候选落到 vmlinux 或未知构建目标，本轮快速扩池只推进具体 .ko 模块目标 |
| CVE-2024-26715 | `p1next0507-26715` | `7/low` | `feature_not_enabled` | `development_only_feature_gate` | `drivers/usb` | `` | `` | `` | `` | `` | 目标文件在当前验证机配置下不可构建，先归入配置门控回归 |
| CVE-2024-26651 | `p1next0507-26651` | `17/low` | `feature_not_enabled` | `development_only_feature_gate` | `drivers/net` | `` | `` | `` | `` | `` | 目标文件在当前验证机配置下不可构建，先归入配置门控回归 |
| CVE-2024-26600 | `p1next0507-26600` | `7/low` | `feature_not_enabled` | `development_only_feature_gate` | `drivers/phy` | `` | `` | `` | `` | `` | 目标文件在当前验证机配置下不可构建，先归入配置门控回归 |
| CVE-2024-26807 | `p1next0507-26807` | `0/low` | `feature_not_enabled` | `development_only_feature_gate` | `drivers/spi` | `` | `` | `` | `` | `` | 目标文件在当前验证机配置下不可构建，先归入配置门控回归 |
| CVE-2024-26803 | `p1next0507-26803` | `100/high` | `buildable_and_should_pass` | `positive_candidate_livepatchability_high` | `drivers/net` | `` | `` | `` | `` | `` | livepatchability-first 打分通过，允许进入 full run |
| CVE-2024-26730 | `p1next0507-26730` | `100/high` | `buildable_and_should_pass` | `positive_candidate_livepatchability_high` | `drivers/hwmon` | `` | `` | `` | `` | `` | livepatchability-first 打分通过，允许进入 full run |
| CVE-2024-26724 | `p1next0507-26724` | `7/low` | `` | `development_only_source_or_analysis_error` | `drivers/net` | `` | `` | `` | `` | `` | create/analyze 阶段未完成，先作为开发样例观察 |
| CVE-2024-26684 | `p1next0507-26684` | `0/low` | `` | `development_only_high_risk` | `drivers/net` | `` | `` | `` | `` | `` | 分析结果显示改写风险偏高，暂不作为正向验收样例 |

## 4. 后续动作

1. 将 `positive_acceptance_confirmed` 样例加入正向池
2. 对 `kpatch_constraint` 样例进入专项改写优化
3. 对 `compile_failed` 样例优先查看 diagnostics 与 build.log
