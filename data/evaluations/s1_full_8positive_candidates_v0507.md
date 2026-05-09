# PatchWeaver Challenge 正向样例池筛选报告

## 1. 执行参数

- mode: `full`
- profile: `demo`
- task_prefix: `s1full0507`
- run_timeout_sec: `900`
- only_positive_candidates: `True`
- min_livepatchability_score: `75`
- only_high_livepatchability: `True`
- workspace_root: `/home/patchweaver/current/workspaces`

## 2. 汇总

- total_cases: `8`
- confirmed_positive_acceptance: `5`
- positive_pool_candidates: `5`
- stable_bucket_ready: `6`
- current_positive_pool_size: `12`
- positive_pool_target: `10`
- positive_pool_gap: `0`
- representative_success_rate: `62%`
- average_attempts: `1.0`
- rag_seed_hits: `8`
- known_pool_skipped: `0`
- stable_source_alignment_required: `2`
- stable_baseline_prepared: `8`
- minimal_config_fragments: `8`
- livepatchability_high: `8`

### bucket_counts

- `already_patched`: `1`
- `buildable_and_should_pass`: `5`
- `unbucketed`: `2`

### livepatchability_tier_counts

- `high`: `8`

### rag_subsystem_counts

- `drivers/net`: `4`
- `fs/btrfs`: `2`
- `fs/smb`: `1`
- `net/smc`: `1`

## 3. 逐样例结果

| CVE | task_id | livepatchability | bucket | tier | rag_subsystem | failure_type | source_alignment | agent_next_action | build | validation | reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CVE-2024-26698 | `s1full0507-26698` | `100/high` | `buildable_and_should_pass` | `positive_acceptance_confirmed` | `drivers/net` | `none` | `` | `stop_or_manual_review` | `built` | `passed` | 已产出 .ko，且加载、卸载、smoke、自检均通过 |
| CVE-2024-26610 | `s1full0507-26610` | `100/high` | `` | `development_only_apply_precheck` | `drivers/net` | `patch_apply_failed` | `required` | `prepare_unpatched_stable_source_baseline` | `not_run` | `pending` | 当前源码树无法通过 apply 预检查，先不纳入稳定四桶样例集 |
| CVE-2024-26693 | `s1full0507-26693` | `100/high` | `buildable_and_should_pass` | `positive_acceptance_confirmed` | `drivers/net` | `none` | `` | `stop_or_manual_review` | `built` | `passed` | 已产出 .ko，且加载、卸载、smoke、自检均通过 |
| CVE-2024-26694 | `s1full0507-26694` | `100/high` | `buildable_and_should_pass` | `positive_acceptance_confirmed` | `drivers/net` | `none` | `` | `stop_or_manual_review` | `built` | `passed` | 已产出 .ko，且加载、卸载、smoke、自检均通过 |
| CVE-2024-26615 | `s1full0507-26615` | `100/high` | `buildable_and_should_pass` | `positive_acceptance_confirmed` | `net/smc` | `none` | `` | `stop_or_manual_review` | `built` | `passed` | 已产出 .ko，且加载、卸载、smoke、自检均通过 |
| CVE-2024-26692 | `s1full0507-26692` | `100/high` | `already_patched` | `positive_candidate_blocked_by_target_state` | `fs/smb` | `target_already_patched` | `` | `stop_or_manual_review` | `not_run` | `pending` | 路线低风险，但当前验证机源码树已包含修复，无法用于正向 .ko 成功率统计 |
| CVE-2024-26727 | `s1full0507-26727` | `100/high` | `` | `development_only_apply_precheck` | `fs/btrfs` | `patch_apply_failed` | `required` | `prepare_unpatched_stable_source_baseline` | `not_run` | `pending` | 当前源码树无法通过 apply 预检查，先不纳入稳定四桶样例集 |
| CVE-2024-26791 | `s1full0507-26791` | `100/high` | `buildable_and_should_pass` | `positive_acceptance_confirmed` | `fs/btrfs` | `none` | `` | `stop_or_manual_review` | `built` | `passed` | 已产出 .ko，且加载、卸载、smoke、自检均通过 |

## 4. 后续动作

1. 将 `positive_acceptance_confirmed` 样例加入正向池
2. 对 `kpatch_constraint` 样例进入专项改写优化
3. 对 `compile_failed` 样例优先查看 diagnostics 与 build.log
