# PatchWeaver Challenge 正向样例池筛选报告

## 1. 执行参数

- mode: `full`
- profile: `demo`
- task_prefix: `reviewv0510-complex`
- run_timeout_sec: `700`
- only_positive_candidates: `False`
- min_livepatchability_score: `75`
- only_high_livepatchability: `False`
- workspace_root: `/home/patchweaver/current/workspaces`

## 2. 汇总

- total_cases: `2`
- confirmed_positive_acceptance: `2`
- positive_pool_candidates: `2`
- stable_bucket_ready: `2`
- current_positive_pool_size: `12`
- positive_pool_target: `10`
- positive_pool_gap: `0`
- representative_success_rate: `100%`
- average_attempts: `1.0`
- rag_seed_hits: `2`
- known_pool_skipped: `0`
- stable_source_alignment_required: `0`
- stable_baseline_prepared: `2`
- minimal_config_fragments: `0`
- livepatchability_high: `2`

### bucket_counts

- `buildable_and_should_pass`: `2`

### livepatchability_tier_counts

- `high`: `2`

### rag_subsystem_counts

- `drivers/gpu`: `1`
- `net/mac80211`: `1`

## 3. 逐样例结果

| CVE | task_id | livepatchability | bucket | tier | rag_subsystem | failure_type | source_alignment | agent_next_action | build | validation | reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CVE-2024-26656 | `reviewv0510-complex-26656` | `77/high` | `buildable_and_should_pass` | `positive_acceptance_confirmed` | `drivers/gpu` | `none` | `` | `stop_or_manual_review` | `built` | `passed` | 已产出 .ko，且加载、卸载、smoke、自检均通过 |
| CVE-2024-26666 | `reviewv0510-complex-26666` | `77/high` | `buildable_and_should_pass` | `positive_acceptance_confirmed` | `net/mac80211` | `none` | `` | `stop_or_manual_review` | `built` | `passed` | 已产出 .ko，且加载、卸载、smoke、自检均通过 |

## 4. 后续动作

1. 本轮 2 条 `kpatch_constraint` 来源样例已纳入 `v0510` 复核证据，均已完成 `.ko` 构建和动态验证。
2. 该结果说明 section/call-sites 类后端约束在当前验证机上已经有突破复核证据。
3. 该结果不等价于 `callback`、`shadow_variable`、`state_preserving` 等所有复杂路线已完成真实 full run 覆盖。
