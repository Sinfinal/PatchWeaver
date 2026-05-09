# PatchWeaver Challenge 正向样例池筛选报告

## 1. 执行参数

- mode: `full`
- profile: `demo`
- task_prefix: `judge-like-challenge14final-2026050920`
- run_timeout_sec: `900`
- only_positive_candidates: `False`
- min_livepatchability_score: `75`
- only_high_livepatchability: `False`
- workspace_root: `/home/patchweaver/current/workspaces`

## 2. 汇总

- total_cases: `14`
- confirmed_positive_acceptance: `5`
- positive_pool_candidates: `5`
- stable_bucket_ready: `14`
- current_positive_pool_size: `12`
- positive_pool_target: `10`
- positive_pool_gap: `0`
- representative_success_rate: `36%`
- average_attempts: `1.0`
- rag_seed_hits: `14`
- known_pool_skipped: `0`
- stable_source_alignment_required: `0`
- stable_baseline_prepared: `4`
- minimal_config_fragments: `0`
- livepatchability_high: `2`

### bucket_counts

- `already_patched`: `4`
- `buildable_and_should_pass`: `5`
- `feature_not_enabled`: `5`

### livepatchability_tier_counts

- `high`: `2`
- `low`: `3`
- `medium`: `9`

### rag_subsystem_counts

- `arch/parisc`: `1`
- `drivers/gpu`: `1`
- `drivers/scsi`: `1`
- `drivers/target`: `1`
- `fs/afs`: `1`
- `fs/btrfs`: `1`
- `net/ipv6`: `2`
- `net/l2tp`: `1`
- `net/llc`: `1`
- `net/netfilter`: `2`
- `net/sched`: `1`
- `security/tomoyo`: `1`

## 3. 逐样例结果

| CVE | task_id | livepatchability | bucket | tier | rag_subsystem | failure_type | source_alignment | agent_next_action | build | validation | reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CVE-2024-26742 | `judge-like-challenge14final-2026050920-26742` | `77/high` | `buildable_and_should_pass` | `positive_acceptance_confirmed` | `drivers/scsi` | `none` | `` | `stop_or_manual_review` | `built` | `passed` | 已产出 .ko，且加载、卸载、smoke、自检均通过 |
| CVE-2024-26631 | `judge-like-challenge14final-2026050920-26631` | `67/medium` | `already_patched` | `positive_candidate_blocked_by_target_state` | `net/ipv6` | `target_already_patched` | `` | `stop_or_manual_review` | `not_run` | `pending` | 路线低风险，但当前验证机源码树已包含修复，无法用于正向 .ko 成功率统计 |
| CVE-2024-26633 | `judge-like-challenge14final-2026050920-26633` | `27/low` | `buildable_and_should_pass` | `positive_acceptance_confirmed` | `net/ipv6` | `none` | `` | `stop_or_manual_review` | `built` | `passed` | 已产出 .ko，且加载、卸载、smoke、自检均通过 |
| CVE-2024-26642 | `judge-like-challenge14final-2026050920-26642` | `77/high` | `already_patched` | `positive_candidate_blocked_by_target_state` | `net/netfilter` | `target_already_patched` | `` | `stop_or_manual_review` | `not_run` | `pending` | 路线低风险，但当前验证机源码树已包含修复，无法用于正向 .ko 成功率统计 |
| CVE-2024-26706 | `judge-like-challenge14final-2026050920-26706` | `0/low` | `feature_not_enabled` | `development_only_arch_gate` | `arch/parisc` | `target_arch_mismatch` | `` | `stop_or_manual_review` | `not_run` | `pending` | 补丁命中的源码不属于当前验证机目标架构，适合作为架构门控识别回归 |
| CVE-2024-26740 | `judge-like-challenge14final-2026050920-26740` | `31/low` | `already_patched` | `positive_candidate_blocked_by_target_state` | `net/sched` | `target_already_patched` | `` | `stop_or_manual_review` | `not_run` | `pending` | 路线低风险，但当前验证机源码树已包含修复，无法用于正向 .ko 成功率统计 |
| CVE-2024-26752 | `judge-like-challenge14final-2026050920-26752` | `67/medium` | `already_patched` | `positive_candidate_blocked_by_target_state` | `net/l2tp` | `target_already_patched` | `` | `stop_or_manual_review` | `not_run` | `pending` | 路线低风险，但当前验证机源码树已包含修复，无法用于正向 .ko 成功率统计 |
| CVE-2024-26607 | `judge-like-challenge14final-2026050920-26607` | `67/medium` | `feature_not_enabled` | `development_only_feature_gate` | `drivers/gpu` | `feature_not_enabled` | `` | `exclude_from_positive_pool_or_enable_kernel_feature` | `not_run` | `pending` | 补丁命中的源码在当前验证机内核配置中未启用，适合做配置门控识别回归 |
| CVE-2024-26622 | `judge-like-challenge14final-2026050920-26622` | `67/medium` | `feature_not_enabled` | `development_only_feature_gate` | `security/tomoyo` | `feature_not_enabled` | `` | `exclude_from_positive_pool_or_enable_kernel_feature` | `not_run` | `pending` | 补丁命中的源码在当前验证机内核配置中未启用，适合做配置门控识别回归 |
| CVE-2024-26625 | `judge-like-challenge14final-2026050920-26625` | `67/medium` | `feature_not_enabled` | `development_only_feature_gate` | `net/llc` | `feature_not_enabled` | `` | `exclude_from_positive_pool_or_enable_kernel_feature` | `not_run` | `pending` | 补丁命中的源码在当前验证机内核配置中未启用，适合做配置门控识别回归 |
| CVE-2024-26736 | `judge-like-challenge14final-2026050920-26736` | `67/medium` | `feature_not_enabled` | `development_only_feature_gate` | `fs/afs` | `feature_not_enabled` | `` | `exclude_from_positive_pool_or_enable_kernel_feature` | `not_run` | `pending` | 补丁命中的源码在当前验证机内核配置中未启用，适合做配置门控识别回归 |
| CVE-2024-26643 | `judge-like-challenge14final-2026050920-26643` | `67/medium` | `buildable_and_should_pass` | `positive_acceptance_confirmed` | `net/netfilter` | `none` | `` | `stop_or_manual_review` | `built` | `passed` | 已产出 .ko，且加载、卸载、smoke、自检均通过 |
| CVE-2024-26726 | `judge-like-challenge14final-2026050920-26726` | `67/medium` | `buildable_and_should_pass` | `positive_acceptance_confirmed` | `fs/btrfs` | `none` | `` | `stop_or_manual_review` | `built` | `passed` | 已产出 .ko，且加载、卸载、smoke、自检均通过 |
| CVE-2024-26760 | `judge-like-challenge14final-2026050920-26760` | `67/medium` | `buildable_and_should_pass` | `positive_acceptance_confirmed` | `drivers/target` | `none` | `` | `stop_or_manual_review` | `built` | `passed` | 已产出 .ko，且加载、卸载、smoke、自检均通过 |

## 4. 后续动作

1. 将 `positive_acceptance_confirmed` 样例加入正向池
2. 对 `kpatch_constraint` 样例进入专项改写优化
3. 对 `compile_failed` 样例优先查看 diagnostics 与 build.log
