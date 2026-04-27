# PatchWeaver 阶段评测摘要

- 生成时间: 2026-04-26T13:23:58.792207+00:00
- 固定样例集: challenge_sample_tiers_v0426
- 样例总数: 14
- 命中样例: 0
- 缺失样例: 14
- 成功数: 0
- 失败数: 0
- 兼容总成功率: 0.00%
- 平均尝试轮次: 0.0
- 说明: 兼容总成功率只用于存量接口兼容，不再作为固定样例的主结论

## 分桶评测

### 目标已修复类
- bucket: already_patched
- 关注目标: 看目标态识别是否准确
- 样例总数: 6
- 命中样例: 0
- 缺失样例: 6
- 主指标: 目标态识别率 0.00% (0/0)
- 状态分布: {}
- 失败分布: {}

### 配置关闭类
- bucket: feature_not_enabled
- 关注目标: 看配置门控识别是否准确
- 样例总数: 4
- 命中样例: 0
- 缺失样例: 4
- 主指标: 配置关闭识别率 0.00% (0/0)
- 状态分布: {}
- 失败分布: {}

### 热补丁约束类
- bucket: kpatch_constraint
- 关注目标: 看约束识别和结构化解释是否完整
- 样例总数: 3
- 命中样例: 0
- 缺失样例: 3
- 主指标: 约束解释完整率 0.00% (0/0)
- 次指标: 约束识别率 0.00% (0/0)
- 状态分布: {}
- 失败分布: {}

### 正向可构建类
- bucket: buildable_and_should_pass
- 关注目标: 看 .ko 产出率和动态验证通过率
- 样例总数: 1
- 命中样例: 0
- 缺失样例: 1
- 主指标: 动态验证通过率 0.00% (0/0)
- 次指标: .ko 产出率 0.00% (0/0)
- 状态分布: {}
- 失败分布: {}

## 状态分布
- 当前没有状态分布记录。

## 分组分布
- regression: 14

## 失败分布
- 当前没有失败分布记录。

## 样例结果
- challenge-pass-cve-2024-26742: bucket=buildable_and_should_pass / missing / 尝试轮 0 / 失败类型 无
- challenge-target-state-cve-2024-26631: bucket=already_patched / missing / 尝试轮 0 / 失败类型 无
- challenge-target-state-cve-2024-26633: bucket=already_patched / missing / 尝试轮 0 / 失败类型 无
- challenge-target-state-cve-2024-26642: bucket=already_patched / missing / 尝试轮 0 / 失败类型 无
- challenge-target-state-cve-2024-26706: bucket=already_patched / missing / 尝试轮 0 / 失败类型 无
- challenge-target-state-cve-2024-26740: bucket=already_patched / missing / 尝试轮 0 / 失败类型 无
- challenge-target-state-cve-2024-26752: bucket=already_patched / missing / 尝试轮 0 / 失败类型 无
- challenge-feature-gate-cve-2024-26607: bucket=feature_not_enabled / missing / 尝试轮 0 / 失败类型 无
- challenge-feature-gate-cve-2024-26622: bucket=feature_not_enabled / missing / 尝试轮 0 / 失败类型 无
- challenge-feature-gate-cve-2024-26625: bucket=feature_not_enabled / missing / 尝试轮 0 / 失败类型 无
- challenge-feature-gate-cve-2024-26736: bucket=feature_not_enabled / missing / 尝试轮 0 / 失败类型 无
- challenge-kpatch-cve-2024-26643: bucket=kpatch_constraint / missing / 尝试轮 0 / 失败类型 无
- challenge-kpatch-cve-2024-26726: bucket=kpatch_constraint / missing / 尝试轮 0 / 失败类型 无
- challenge-kpatch-cve-2024-26760: bucket=kpatch_constraint / missing / 尝试轮 0 / 失败类型 无
