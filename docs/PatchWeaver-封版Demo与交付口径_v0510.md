# PatchWeaver 封版 Demo 与交付口径 v0510

## 1. 文档定位

本文档用于封版前统一 README、PRD、测试报告、Demo 脚本和百炼交付入口的表述口径。它不替代 PRD，也不重新设计主链，只回答评审和答辩时最容易混淆的 5 个问题：

1. PatchWeaver 到底是不是 Agent
2. 什么才算热补丁生成成功
3. Demo 应该展示哪些样例
4. 百炼入口和本地主链是什么关系
5. AI 在系统里发挥什么作用，哪些结论必须由工程证据确认

## 2. 统一产品口径

PatchWeaver 是面向 Anolis OS ANCK 内核 CVE 的热补丁生成 Agent。它不是单个脚本，也不是“下载 patch 后直接编译”的流水线。

正式口径如下：

- `Harness` 是唯一主状态中心，负责任务、尝试轮、终止条件、失败归因和回放。
- 模型用于语义理解、候选策略解释和日志归因辅助，不能直接决定构建成功、验证成功或正向池准入。
- 成功样例必须有真实 `.ko`，并通过 `load/unload/smoke/selftest`。
- 失败样例也必须有价值，至少能输出结构化失败原因、证据路径和下一步动作。
- 百炼应用是交互入口和工具调用桥，不替代 PatchWeaver 主链执行层。

## 3. Demo 样例组合

Demo 应覆盖三类样例，避免只展示成功或只展示失败解释。

| 类型 | 展示目的 | 必需证据 |
| --- | --- | --- |
| 成功样例 | 证明系统能产出可加载热补丁模块 | `.ko`、`vermagic`、`build_summary.json`、`validation_report.json`、load/unload/smoke/selftest 日志 |
| 失败归因样例 | 证明系统不会把后端限制误报为成功 | `failure_record.json`、失败桶、日志片段、`agent_next_action` |
| Agent 重试样例 | 证明失败能驱动下一轮策略调整 | `RepairIntent`、`rewrite_plan`、`strategy_switch`、尝试轮 trace |

当前封版代表集证据：

- `data/evaluations/validation_v0509/final_holdout10_full_run_v0509.json`
- `data/evaluations/validation_v0509/final_holdout10_evidence_manifest_v0509.json`
- `data/evaluations/validation_v0509/representative_metrics_v0510.json`
- `data/evaluations/validation_v0509/representative_metrics_v0510.md`

## 4. 推荐演示命令

生成 Demo 汇总报告：

```bash
python scripts/generate_demo_report.py \
  --workspace-root workspaces \
  --reports-root data/reports \
  --positive-evidence data/evaluations/validation_v0509/final_holdout10_evidence_manifest_v0509.json \
  --output-md data/reports/demo_report_v0510.md \
  --manifest-output data/reports/demo_submission_manifest_v0510.json
```

生成代表集指标报告：

```bash
python scripts/generate_representative_metrics_report.py \
  --holdout data/evaluations/validation_v0509/final_holdout10_full_run_v0509.json \
  --evidence-manifest data/evaluations/validation_v0509/final_holdout10_evidence_manifest_v0509.json \
  --output-json data/evaluations/validation_v0509/representative_metrics_v0510.json \
  --output-md data/evaluations/validation_v0509/representative_metrics_v0510.md
```

百炼 / Function Compute 网关打包：

```bash
python scripts/package_bailian_gateway.py \
  --package-type web \
  --output-zip data/submission/bailian_gateway_fc_web_package_v0509.zip \
  --manifest-output data/submission/bailian_gateway_fc_web_package_v0509.json \
  --readiness-output data/submission/bailian_gateway_readiness_v0509.json \
  --public-url https://<fc-or-gateway-public-host>
```

封版脱敏检查：

```bash
python scripts/release_redaction_check.py \
  --output data/submission/release_redaction_check.json
```

## 5. 百炼交付边界

百炼应用、MCP 服务和 Function Compute HTTPS 入口用于承接评委交互和工具调用。

当前交付边界：

- `dry_run=true` 可以证明百炼应用、MCP 工具、FC 网关和 PatchWeaver API contract 已连通。
- `dry_run=true` 不能证明真实 `kpatch-build`、`.ko` 生成或动态验证成功。
- 真实成功仍以验证机工作区产物和代表集指标报告为准。
- 如果最终要求评委直接打开生产级 Web 分享入口，应在 FC 默认域名前绑定自定义域名、API Gateway 或 ALB。

## 6. AI 使用说明

AI 在 PatchWeaver 中的作用是辅助，不是最终裁判。

可由模型辅助的环节：

- patch 语义摘要
- `RepairIntent` 初稿整理
- 候选路线解释
- 构建失败日志摘要
- 报告中的自然语言解释

必须由工程证据确认的环节：

- patch 是否能 apply
- `kpatch-build` 是否成功
- `.ko` 是否存在
- `vermagic` 是否匹配目标内核
- load/unload/smoke/selftest 是否通过
- 样例是否能进入 confirmed 正向池

模型交互记录应通过 `config/models.yaml` 中的 `interaction_record_mode` 与 `interaction_jsonl_path` 留痕，报告中可以引用记录路径和人工复核方式，但不能把模型输出当成最终成功证据。

## 7. 术语速查

| 术语 | 解释 |
| --- | --- |
| `Agent` | 有状态、会决策、能调用工具、可回放的任务系统 |
| `Harness` | 主状态中心，负责状态推进和最终判定 |
| `RepairIntent` | 修复意图对象，记录漏洞触发条件、guard、插入点、安全退出路径和保留副作用 |
| `Recipe` | 可复用改写方案 |
| `SmPL` | Coccinelle 语义补丁规则 |
| `positive pool` | confirmed 正向池，只收录真实 `.ko + validation` 通过样例 |
| `holdout` | 内部盲测或代表集，用于模拟 Final 压力 |
| `kpatch_constraint` | kpatch 后端限制，如 section change、符号偏移、`.rela.call_sites` |
| `section_change_avoidance` | 尽量规避 section 变化的补丁收缩策略 |
| `semantic_guard_rewrite` | 把修复意图转成函数局部 guard 的改写路线 |
| `RAG seed` | 用于筛样、经验召回和上下文补强的知识种子 |
| `dry_run` | 安全联调模式，只证明调用链，不证明真实构建成功 |

## 8. 封版前检查

封版前至少确认：

1. README、PRD、任务清单和本文档的成功定义一致。
2. 代表集报告包含 `representative_total`、`representative_success_rate`、`average_attempts` 和五类验证证据。
3. Demo 报告能展示成功、失败归因和 Agent 决策证据。
4. 百炼交付说明明确 `dry_run=true` 的边界。
5. 脱敏检查通过，文档和代码不含真实密钥、密码、平台 token 或 cookie。
