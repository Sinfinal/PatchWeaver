# PatchWeaver Challenge 正向样例池筛选报告

## 1. 执行参数

- mode: `full`
- profile: `dev`
- task_prefix: `p1nextfull0507`
- run_timeout_sec: `900`
- only_positive_candidates: `True`
- min_livepatchability_score: `75`
- only_high_livepatchability: `True`
- workspace_root: `/home/patchweaver/current/workspaces`

## 2. 汇总

- total_cases: `2`
- confirmed_positive_acceptance: `0`
- positive_pool_candidates: `1`
- stable_bucket_ready: `1`
- current_positive_pool_size: `6`
- positive_pool_target: `10`
- positive_pool_gap: `4`
- representative_success_rate: `0%`
- average_attempts: `1.0`
- rag_seed_hits: `2`
- known_pool_skipped: `0`
- stable_source_alignment_required: `0`
- stable_baseline_prepared: `2`
- minimal_config_fragments: `2`
- livepatchability_high: `2`

### bucket_counts

- `buildable_and_should_pass`: `1`
- `unbucketed`: `1`

### livepatchability_tier_counts

- `high`: `2`

### rag_subsystem_counts

- `drivers/hwmon`: `1`
- `drivers/net`: `1`

## 3. 逐样例结果

| CVE | task_id | livepatchability | bucket | tier | rag_subsystem | failure_type | source_alignment | agent_next_action | build | validation | reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CVE-2024-26803 | `p1nextfull0507-26803` | `100/high` | `buildable_and_should_pass` | `positive_candidate_low_risk` | `drivers/net` | `kpatch_symbol_bundle_constraint` | `` | `check_vendor_baseline_then_section_symbol_rewrite` | `failed` | `pending` | 当前分析结果显示为低风险路线，值得继续推进到真实构建筛选 |
| CVE-2024-26730 | `p1nextfull0507-26730` | `100/high` | `` | `blocked_by_compile_failure` | `drivers/hwmon` | `compile_failed` | `` | `adjust_build_target_or_dependencies` | `failed` | `pending` | 已进入构建但未形成稳定失败口径，先不纳入稳定四桶样例集 |

## 4. 后续动作

1. 将 `positive_acceptance_confirmed` 样例加入正向池
2. 对 `kpatch_constraint` 样例进入专项改写优化
3. 对 `compile_failed` 样例优先查看 diagnostics 与 build.log
