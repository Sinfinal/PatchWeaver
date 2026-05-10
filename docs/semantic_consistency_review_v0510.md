# PatchWeaver 语义一致性人工抽查报告 v0510

生成时间：`2026-05-10T05:17:30.117258+00:00`

本文按评委关注点抽查 3 个成功样例和 1 个失败边界样例。结论只代表本次抽查，不外推官方 Final 隐藏集。

## 1. 抽查结论

- 3 个成功样例均能通过 API 关联到原始补丁、规范化补丁、语义卡、约束报告、改写补丁、构建日志、`.ko` 和验证报告。
- 1 个失败边界样例未被误报为成功，失败类型保留为功能/配置门控类，符合安全验收口径。
- 本报告是工程证据抽查，不替代人工逐行审查；最终答辩建议现场打开 `raw_patch.patch` 与 `rewritten.patch` 对照说明。

## 2. 样例明细

| CVE | 角色 | Task | 状态 | 失败类型 | 验证状态 | `.ko` | 改写补丁 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `CVE-2024-26643` | 成功样例：kpatch 约束突破 | `judge-like-challenge14final-2026050920-26643` | `built` | `none` | `passed` | `True` | `True` |
| `CVE-2024-26726` | 成功样例：kpatch 约束突破 | `judge-like-challenge14final-2026050920-26726` | `built` | `none` | `passed` | `True` | `True` |
| `CVE-2024-26760` | 成功样例：kpatch 约束突破 | `judge-like-challenge14final-2026050920-26760` | `built` | `none` | `passed` | `True` | `True` |
| `CVE-2024-26607` | 失败边界样例：feature_not_enabled | `judge-like-challenge14final-2026050920-26607` | `failed` | `feature_not_enabled` | `pending` | `False` | `True` |

## 3. 逐项检查

### CVE-2024-26643 - 成功样例：kpatch 约束突破

- 修复主题：netfilter: nf_tables: mark set as dead when unbinding anonymous set
- 影响文件：net/netfilter/nf_tables_api.c
- 原始 patch：`workspaces/judge-like-challenge14final-2026050920-26643/input/raw_patch.patch`
- 规范化 patch：`workspaces/judge-like-challenge14final-2026050920-26643/normalized/normalized.patch`
- 语义卡：`workspaces/judge-like-challenge14final-2026050920-26643/analysis/semantic_card.json`
- 约束报告：`workspaces/judge-like-challenge14final-2026050920-26643/analysis/constraint_report.json`
- 改写 patch：`workspaces/judge-like-challenge14final-2026050920-26643/attempts/001/rewrite/rewritten.patch`
- 构建日志：`workspaces/judge-like-challenge14final-2026050920-26643/attempts/001/logs/build.log`
- 模块产物：`workspaces/judge-like-challenge14final-2026050920-26643/attempts/001/output/patchweaver-judge-like-challenge14final-2026050920-2664.ko`
- 验证报告：`workspaces/judge-like-challenge14final-2026050920-26643/attempts/001/artifacts/validation_report.json`
- 当前判断：成功样例具备完整工程证据，需人工对照 patch 语义。

### CVE-2024-26726 - 成功样例：kpatch 约束突破

- 修复主题：btrfs: don't drop extent_map for free space inode on write error
- 影响文件：fs/btrfs/inode.c
- 原始 patch：`workspaces/judge-like-challenge14final-2026050920-26726/input/raw_patch.patch`
- 规范化 patch：`workspaces/judge-like-challenge14final-2026050920-26726/normalized/normalized.patch`
- 语义卡：`workspaces/judge-like-challenge14final-2026050920-26726/analysis/semantic_card.json`
- 约束报告：`workspaces/judge-like-challenge14final-2026050920-26726/analysis/constraint_report.json`
- 改写 patch：`workspaces/judge-like-challenge14final-2026050920-26726/attempts/001/rewrite/rewritten.patch`
- 构建日志：`workspaces/judge-like-challenge14final-2026050920-26726/attempts/001/logs/build.log`
- 模块产物：`workspaces/judge-like-challenge14final-2026050920-26726/attempts/001/output/patchweaver-judge-like-challenge14final-2026050920-2672.ko`
- 验证报告：`workspaces/judge-like-challenge14final-2026050920-26726/attempts/001/artifacts/validation_report.json`
- 当前判断：成功样例具备完整工程证据，需人工对照 patch 语义。

### CVE-2024-26760 - 成功样例：kpatch 约束突破

- 修复主题：scsi: target: pscsi: Fix bio_put() for error case
- 影响文件：drivers/target/target_core_pscsi.c
- 原始 patch：`workspaces/judge-like-challenge14final-2026050920-26760/input/raw_patch.patch`
- 规范化 patch：`workspaces/judge-like-challenge14final-2026050920-26760/normalized/normalized.patch`
- 语义卡：`workspaces/judge-like-challenge14final-2026050920-26760/analysis/semantic_card.json`
- 约束报告：`workspaces/judge-like-challenge14final-2026050920-26760/analysis/constraint_report.json`
- 改写 patch：`workspaces/judge-like-challenge14final-2026050920-26760/attempts/001/rewrite/rewritten.patch`
- 构建日志：`workspaces/judge-like-challenge14final-2026050920-26760/attempts/001/logs/build.log`
- 模块产物：`workspaces/judge-like-challenge14final-2026050920-26760/attempts/001/output/patchweaver-judge-like-challenge14final-2026050920-2676.ko`
- 验证报告：`workspaces/judge-like-challenge14final-2026050920-26760/attempts/001/artifacts/validation_report.json`
- 当前判断：成功样例具备完整工程证据，需人工对照 patch 语义。

### CVE-2024-26607 - 失败边界样例：feature_not_enabled

- 修复主题：drm/bridge: sii902x: Fix probing race issue
- 影响文件：drivers/gpu/drm/bridge/sii902x.c
- 原始 patch：`workspaces/judge-like-challenge14final-2026050920-26607/input/raw_patch.patch`
- 规范化 patch：`workspaces/judge-like-challenge14final-2026050920-26607/normalized/normalized.patch`
- 语义卡：`workspaces/judge-like-challenge14final-2026050920-26607/analysis/semantic_card.json`
- 约束报告：`workspaces/judge-like-challenge14final-2026050920-26607/analysis/constraint_report.json`
- 改写 patch：`workspaces/judge-like-challenge14final-2026050920-26607/attempts/001/rewrite/rewritten.patch`
- 构建日志：`workspaces/judge-like-challenge14final-2026050920-26607/attempts/001/logs/build.log`
- 模块产物：`missing`
- 验证报告：`workspaces/judge-like-challenge14final-2026050920-26607/attempts/001/artifacts/validation_report.json`
- 当前判断：失败样例未产出 .ko，不能计入成功率；重点检查失败归因是否准确。

## 4. 仍需人工复核的点

- 对 3 个成功样例逐行比对 `raw_patch.patch` 与 `rewritten.patch`，确认没有删除关键安全检查。
- 对 `semantic_card.json` 中的触发条件、关键调用和副作用进行抽查，确认与 CVE 修复主题一致。
- 对失败边界样例确认 `feature_not_enabled` 或目标状态归因没有掩盖真实构建错误。
- 不把本报告作为 Final 隐藏集语义正确性的全量证明。
