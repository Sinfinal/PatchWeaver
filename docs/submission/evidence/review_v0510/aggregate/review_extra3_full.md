# PatchWeaver Challenge 正向样例池筛选报告

## 1. 执行参数

- mode: `full`
- profile: `demo`
- task_prefix: `reviewv0510`
- run_timeout_sec: `700`
- only_positive_candidates: `False`
- min_livepatchability_score: `75`
- only_high_livepatchability: `False`
- workspace_root: `/home/patchweaver/current/workspaces`

## 2. 汇总

- total_cases: `3`
- confirmed_positive_acceptance: `3`
- positive_pool_candidates: `3`
- stable_bucket_ready: `3`
- current_positive_pool_size: `12`
- positive_pool_target: `10`
- positive_pool_gap: `0`
- representative_success_rate: `100%`
- average_attempts: `1.0`
- rag_seed_hits: `3`
- known_pool_skipped: `0`
- stable_source_alignment_required: `0`
- stable_baseline_prepared: `3`
- minimal_config_fragments: `0`
- livepatchability_high: `3`

### bucket_counts

- `buildable_and_should_pass`: `3`

### livepatchability_tier_counts

- `high`: `3`

### rag_subsystem_counts

- `drivers/net`: `1`
- `net/netfilter`: `1`
- `net/tipc`: `1`

## 3. 逐样例结果

| CVE | task_id | livepatchability | bucket | tier | rag_subsystem | failure_type | source_alignment | agent_next_action | build | validation | reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CVE-2024-26675 | `reviewv0510-26675` | `77/high` | `buildable_and_should_pass` | `positive_acceptance_confirmed` | `drivers/net` | `none` | `` | `stop_or_manual_review` | `built` | `passed` | 已产出 .ko，且加载、卸载、smoke、自检均通过 |
| CVE-2024-26663 | `reviewv0510-26663` | `77/high` | `buildable_and_should_pass` | `positive_acceptance_confirmed` | `net/tipc` | `none` | `` | `stop_or_manual_review` | `built` | `passed` | 已产出 .ko，且加载、卸载、smoke、自检均通过 |
| CVE-2024-26668 | `reviewv0510-26668` | `77/high` | `buildable_and_should_pass` | `positive_acceptance_confirmed` | `net/netfilter` | `none` | `` | `stop_or_manual_review` | `built` | `passed` | 已产出 .ko，且加载、卸载、smoke、自检均通过 |

## 4. 后续动作

1. 将 `positive_acceptance_confirmed` 样例加入正向池
2. 对 `kpatch_constraint` 样例进入专项改写优化
3. 对 `compile_failed` 样例优先查看 diagnostics 与 build.log
