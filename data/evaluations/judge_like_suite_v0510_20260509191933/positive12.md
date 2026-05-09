# PatchWeaver Challenge 正向样例池筛选报告

## 1. 执行参数

- mode: `full`
- profile: `demo`
- task_prefix: `judge-like-positive12-20260509191933`
- run_timeout_sec: `900`
- only_positive_candidates: `False`
- min_livepatchability_score: `75`
- only_high_livepatchability: `False`
- workspace_root: `/home/patchweaver/current/workspaces`

## 2. 汇总

- total_cases: `12`
- confirmed_positive_acceptance: `12`
- positive_pool_candidates: `12`
- stable_bucket_ready: `12`
- current_positive_pool_size: `12`
- positive_pool_target: `10`
- positive_pool_gap: `0`
- representative_success_rate: `100%`
- average_attempts: `1.0`
- rag_seed_hits: `12`
- known_pool_skipped: `0`
- stable_source_alignment_required: `0`
- stable_baseline_prepared: `12`
- minimal_config_fragments: `0`
- livepatchability_high: `6`

### bucket_counts

- `buildable_and_should_pass`: `12`

### livepatchability_tier_counts

- `high`: `6`
- `medium`: `6`

### rag_subsystem_counts

- `drivers/gpu`: `1`
- `drivers/net`: `4`
- `drivers/scsi`: `1`
- `fs/btrfs`: `2`
- `net/mac80211`: `1`
- `net/netfilter`: `1`
- `net/smc`: `1`
- `net/tipc`: `1`

## 3. 逐样例结果

| CVE | task_id | livepatchability | bucket | tier | rag_subsystem | failure_type | source_alignment | agent_next_action | build | validation | reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CVE-2024-26742 | `judge-like-positive12-20260509191933-26742` | `77/high` | `buildable_and_should_pass` | `positive_acceptance_confirmed` | `drivers/scsi` | `none` | `` | `stop_or_manual_review` | `built` | `passed` | 已产出 .ko，且加载、卸载、smoke、自检均通过 |
| CVE-2024-26675 | `judge-like-positive12-20260509191933-26675` | `77/high` | `buildable_and_should_pass` | `positive_acceptance_confirmed` | `drivers/net` | `none` | `` | `stop_or_manual_review` | `built` | `passed` | 已产出 .ko，且加载、卸载、smoke、自检均通过 |
| CVE-2024-26663 | `judge-like-positive12-20260509191933-26663` | `77/high` | `buildable_and_should_pass` | `positive_acceptance_confirmed` | `net/tipc` | `none` | `` | `stop_or_manual_review` | `built` | `passed` | 已产出 .ko，且加载、卸载、smoke、自检均通过 |
| CVE-2024-26668 | `judge-like-positive12-20260509191933-26668` | `77/high` | `buildable_and_should_pass` | `positive_acceptance_confirmed` | `net/netfilter` | `none` | `` | `stop_or_manual_review` | `built` | `passed` | 已产出 .ko，且加载、卸载、smoke、自检均通过 |
| CVE-2024-26666 | `judge-like-positive12-20260509191933-26666` | `77/high` | `buildable_and_should_pass` | `positive_acceptance_confirmed` | `net/mac80211` | `none` | `` | `stop_or_manual_review` | `built` | `passed` | 已产出 .ko，且加载、卸载、smoke、自检均通过 |
| CVE-2024-26656 | `judge-like-positive12-20260509191933-26656` | `77/high` | `buildable_and_should_pass` | `positive_acceptance_confirmed` | `drivers/gpu` | `none` | `` | `stop_or_manual_review` | `built` | `passed` | 已产出 .ko，且加载、卸载、smoke、自检均通过 |
| CVE-2024-26726 | `judge-like-positive12-20260509191933-26726` | `67/medium` | `buildable_and_should_pass` | `positive_acceptance_confirmed` | `fs/btrfs` | `none` | `` | `stop_or_manual_review` | `built` | `passed` | 已产出 .ko，且加载、卸载、smoke、自检均通过 |
| CVE-2024-26698 | `judge-like-positive12-20260509191933-26698` | `67/medium` | `buildable_and_should_pass` | `positive_acceptance_confirmed` | `drivers/net` | `none` | `` | `stop_or_manual_review` | `built` | `passed` | 已产出 .ko，且加载、卸载、smoke、自检均通过 |
| CVE-2024-26693 | `judge-like-positive12-20260509191933-26693` | `59/medium` | `buildable_and_should_pass` | `positive_acceptance_confirmed` | `drivers/net` | `none` | `` | `stop_or_manual_review` | `built` | `passed` | 已产出 .ko，且加载、卸载、smoke、自检均通过 |
| CVE-2024-26694 | `judge-like-positive12-20260509191933-26694` | `67/medium` | `buildable_and_should_pass` | `positive_acceptance_confirmed` | `drivers/net` | `none` | `` | `stop_or_manual_review` | `built` | `passed` | 已产出 .ko，且加载、卸载、smoke、自检均通过 |
| CVE-2024-26615 | `judge-like-positive12-20260509191933-26615` | `67/medium` | `buildable_and_should_pass` | `positive_acceptance_confirmed` | `net/smc` | `none` | `` | `stop_or_manual_review` | `built` | `passed` | 已产出 .ko，且加载、卸载、smoke、自检均通过 |
| CVE-2024-26791 | `judge-like-positive12-20260509191933-26791` | `67/medium` | `buildable_and_should_pass` | `positive_acceptance_confirmed` | `fs/btrfs` | `none` | `` | `stop_or_manual_review` | `built` | `passed` | 已产出 .ko，且加载、卸载、smoke、自检均通过 |

## 4. 后续动作

1. 将 `positive_acceptance_confirmed` 样例加入正向池
2. 对 `kpatch_constraint` 样例进入专项改写优化
3. 对 `compile_failed` 样例优先查看 diagnostics 与 build.log
