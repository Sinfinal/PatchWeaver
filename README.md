# PatchWeaver

面向 Anolis OS ANCK 内核的 CVE 热补丁自动生成智能体。

## 1. 项目简介

`PatchWeaver` 用于把上游 Linux 内核 `CVE` 修复补丁整理、分析、改写并接入 `kpatch-build` 构建链，目标是在不停机场景下形成可加载的 `livepatch` 热补丁模块，并输出完整的过程记录、失败归因和验证报告。

本项目对应的核心问题不是“把 patch 拉下来直接编译”，而是解决下面这条工程链：

- 从 `CVE ID` 自动定位修复来源
- 获取适配目标内核版本的 patch
- 结合 `kpatch` 约束做结构化改写
- 在目标源码树上执行 `apply` 预检查与构建
- 对失败进行分类归因并保留重试依据
- 对成功产物执行加载、卸载和最小功能验证
- 输出可回放、可答辩、可追溯的结构化报告

## 2. 当前工程状态

当前仓库已经进入封版收口阶段，不再按“最小脚本流水线”口径描述。PatchWeaver 的正式定位是一个有状态、会决策、能调用工具、可回放的内核 CVE 热补丁生成 Agent。

当前已经完成并可作为封版证据的能力：

- `create/analyze/run/report/replay` CLI 主链可运行
- SQLite、任务工作区、构建日志、验证报告和回放产物已经统一落盘
- confirmed 正向池达到 `12` 条，证据 manifest 为 `12/12 complete`
- `v0509` Final 风格 holdout10 在验证机完成 `10/10 .ko built` 与 `10/10 load/unload/smoke/selftest passed`
- 代表集指标报告显示 `representative_success_rate=100%`，`average_attempts=1.0`
- Web/API 与百炼 FC/MCP 网关已具备受控 `dry_run=true` smoke 能力
- 封版脱敏检查已覆盖 `README/config/docs/submission/docs/patchweaver/scripts/tests`

当前仍需在答辩和最终材料中如实说明的边界：

- `Final` 官方评测集不可见，内部 holdout 成功不等价于最终成绩保证
- 已确认成功样例仍集中在较高 livepatchability 的候选上
- `semantic_guard_rewrite` 主动生成非 pass-through guard 后完成动态验证的真实 CVE 样例仍是增强项
- 若最终要求评委直接打开生产级 Web 分享链接，需要在 FC 默认域名前补自定义域名、API Gateway/ALB 或百炼发布渠道说明

## 3. 赛题对应关系

本项目围绕赛题要求中的 4 条主线建设：

1. `CVE` 查询与补丁获取
2. 补丁自动改写与 `kpatch` 约束适配
3. 自动构建与热补丁生成
4. 结构化报告、日志、证据包和阶段材料输出

项目当前已经把“真实输入、真实失败归因、真实工作区产物”落到了本地工程中，后续重点继续补强成功样例和稳定性。

## 4. 环境准备

建议环境：

- Python `3.11+`
- Anolis OS 对应内核开发环境
- `kpatch-build`
- 可访问的内核源码树、`.config` 和 `vmlinux`

当前项目使用的核心 Python 依赖包括：

- `typer`
- `pydantic`
- `pyyaml`
- `jinja2`
- `unidiff`
- `rich`
- `paramiko`

安装方式示例：

```bash
python -m pip install -e . --no-deps
python -m pip install typer pydantic pyyaml jinja2 unidiff rich paramiko
```

### 部署环境变量

正式部署、百炼网关和封版验收只通过环境变量或平台密钥注入敏感值，仓库配置、文档和测试夹具不得写入真实 API Key、root 密码、平台 token 或私有 cookie。

必须配置：

- `PATCHWEAVER_BAILIAN_API_KEY`：百炼 / DashScope API Key。只放在本机 `.env`、shell 环境、Function Compute 受保护环境变量或平台 Secret 中。
- `PATCHWEAVER_API_BASE_URL`：百炼网关调用的 PatchWeaver Web/API 基础地址，例如 `http://127.0.0.1:18084` 或受控 HTTPS 网关。

可选配置：

- `PATCHWEAVER_API_TIMEOUT_SECONDS`：百炼网关 HTTP 超时时间，默认 `30`。

封版前执行脱敏检查：

```bash
python scripts/release_redaction_check.py --output data/submission/release_redaction_check.json
```

## 5. 快速启动

查看命令入口：

```bash
python -m patchweaver --help
```

初始化最小运行目录与数据库：

```bash
python -m patchweaver init --with-db --json
```

检查当前运行机的本机构建环境：

```bash
python -m patchweaver doctor --json
```

创建一个任务：

```bash
python -m patchweaver create --cve CVE-2024-1086 --task-id TASK-DEMO-001 --json
```

执行分析阶段：

```bash
python -m patchweaver analyze --task TASK-DEMO-001 --json
```

执行主链：

```bash
python -m patchweaver run --task TASK-DEMO-001 --json
```

生成报告与回放信息：

```bash
python -m patchweaver report --task TASK-DEMO-001 --json
python -m patchweaver replay --task TASK-DEMO-001 --json
```

在 Linux 验证机上安装并启动 Web/API 常驻服务：

```bash
python -m patchweaver install-api-service
systemctl status patchweaver-web --no-pager
```

默认服务地址来自 `config/system.yaml`，当前默认监听 `0.0.0.0:18084`。

本地前台调试 Web/API：

```bash
python -m patchweaver serve-api --host 0.0.0.0 --port 18084
```

百炼 / Function Compute 网关交付包：

```bash
python scripts/package_bailian_gateway.py \
  --package-type web \
  --output-zip data/submission/bailian_gateway_fc_web_package_v0509.zip \
  --manifest-output data/submission/bailian_gateway_fc_web_package_v0509.json \
  --readiness-output data/submission/bailian_gateway_readiness_v0509.json \
  --public-url https://<fc-or-gateway-public-host>
```

代表集指标与封版脱敏检查：

```bash
python scripts/generate_representative_metrics_report.py \
  --holdout data/evaluations/validation_v0509/final_holdout10_full_run_v0509.json \
  --evidence-manifest data/evaluations/validation_v0509/final_holdout10_evidence_manifest_v0509.json \
  --output-json data/evaluations/validation_v0509/representative_metrics_v0510.json \
  --output-md data/evaluations/validation_v0509/representative_metrics_v0510.md

python scripts/release_redaction_check.py \
  --output data/submission/release_redaction_check.json
```

Demo 证据报告：

```bash
python scripts/generate_demo_report.py \
  --workspace-root workspaces \
  --reports-root data/reports \
  --positive-evidence data/evaluations/validation_v0509/final_holdout10_evidence_manifest_v0509.json \
  --output-md data/reports/demo_report_v0510.md \
  --manifest-output data/reports/demo_submission_manifest_v0510.json
```

Demo 口径固定为三类样例：成功 `.ko + load/unload/smoke/selftest` 样例、失败归因样例、Agent 根据 `RepairIntent / failure_record / strategy_switch` 给出下一步动作的重试样例。

## 6. 典型输出

一个任务运行后，通常会在 `workspaces/<task_id>/` 下形成以下几类产物：

- 输入侧：`raw_patch.patch`、`patch_bundle.json`、`source_evidence.json`
- 分析侧：`semantic_card.json`、`constraint_report.json`
- 改写侧：`rewrite_plan.json`、`rewritten.patch`
- 构建侧：`build.log`、`build_summary.json`、`failure_record.json`
- 验证侧：`validation_report.json`
- 汇总侧：`report.json`、`report.md`、`evaluation_summary.json`

这套目录同时也是后续做答辩、视频和证据包的主要材料来源。

## 7. 目录说明

```text
patchweaver/
├─ patchweaver/          主包，包含 CLI、检索、分析、改写、构建、验证、报告等模块
├─ config/               运行配置
├─ data/                 SQLite、日志、manifest 模板
├─ workspaces/           任务工作区与过程产物
├─ rules/                规则库
├─ recipes/              模板与 SmPL 配方
├─ prompts/              Prompt 契约与阶段提示词
├─ evaluations/          样例与评测素材
├─ tests/                单元测试和定向测试
├─ web/                  控制台前后端代码
└─ docs/                 项目文档
```

## 8. 关键文档

建议优先阅读下面几份材料：

- `docs/PatchWeaver-总方案与创新设计总文档.md`
- `docs/PatchWeaver-封版Demo与交付口径_v0510.md`
- `docs/bailian_gateway.md`
- `docs/PatchWeaver-研发实施与交付总手册_一期.md`
- `docs/PatchWeaver-研发实施与交付总手册_二期.md`
- `docs/PatchWeaver-阶段汇报-2026-04-11.md`

如果是准备阶段汇报或答辩，建议同时查看：

- 测试验收目录中的《PatchWeaver-一期二期阶段测试与验收报告》
- 阶段性成果目录中的《PatchWeaver-失败样例证据包》

## 9. 当前边界说明

当前版本可以对外展示“真实输入 + Agent 决策 + `.ko` 构建 + 动态验证 + 报告回放”的封版主链。成功口径必须严格来自代表集和正向池证据，不允许把模板单测、dry-run、already-patched 或 feature-disabled 样例计入热补丁成功率。

现阶段对外表述建议保持一致：

- PatchWeaver 是受 Harness 控制的 Agent，而不是若干脚本拼接
- 成功定义为真实 `.ko` 产物加 `load/unload/smoke/selftest` 通过
- 失败定义也有价值，因为失败归因会驱动下一轮策略或给出不可热补丁化判断
- 百炼入口用于交互和工具调用桥接，不替代主链对构建、验证和放行的判定

## 10. 联系当前阶段材料

如果需要快速准备阶段汇报或答辩，建议直接围绕下面这几类材料展开：

- 第二期测试与验收记录
- 第二期阶段汇报提纲
- 演示脚本与录屏说明
- 失败样例证据包
- 答辩问答稿与截图索引

这样可以避免临时翻目录，也更容易保持口径一致。

## 11. 专业名词速查

| 术语 | 说明 |
| --- | --- |
| `Agent` | 有状态、会决策、能调用工具、可回放的执行系统。PatchWeaver 的最终判定由 Harness 控制，不由模型单独决定 |
| `Harness` | 主状态中心，维护任务、尝试轮、终止条件、失败归因和回放证据 |
| `RepairIntent` | 修复意图对象，记录漏洞触发条件、guard 条件、插入点、安全退出路径、必须保留副作用和推荐策略 |
| `Recipe` | 可复用改写方案，例如 `direct_apply_patch`、`minimal_livepatch_wrap`、`semantic_guard_rewrite` |
| `SmPL` | Coccinelle 语义补丁规则，用于结构化匹配和改写 Linux 内核代码 |
| `kpatch_constraint` | `kpatch-build` 后端限制，例如不支持的 section change、`.rela.call_sites`、符号偏移等 |
| `section_change_avoidance` | 针对 section 变化约束的补丁收缩策略，尽量保留函数局部变更，避免触碰全局表或初始化路径 |
| `semantic_guard_rewrite` | 把修复意图转成函数局部 guard 或关键调用点 guard 的改写路线 |
| 正向池 | 只保存真实产出 `.ko` 且通过加载、卸载、smoke、自检的 CVE 样例池 |
| 代表集 | 用于对照赛题指标的一组封版样例，报告必须包含成功率、平均尝试轮次和证据路径 |
| RAG seed | 用于筛样和经验检索的外部样例/知识种子，不等于成功证明 |
| `dry_run` | 平台或网关联调用的安全模式，只证明调用链，不证明真实构建或验证成功 |

## 12. AI 使用与人工复核

PatchWeaver 使用模型辅助语义摘要、修复意图整理、候选策略解释和日志归因，但模型不能直接决定构建成功、动态验证成功或正向池准入。

AI 使用记录与复核口径：

- 模型配置来源通过 `python -m patchweaver models --json` 查看，只显示来源和脱敏状态
- 模型交互记录按 `config/models.yaml` 中的 `interaction_record_mode` 和 `interaction_jsonl_path` 控制
- 关键样例的模型请求/响应应随测试报告或任务工作区留痕
- 人工复核重点检查 `RepairIntent`、`rewritten.patch`、`build_summary.json`、`validation_report.json` 和 `failure_record.json`
- 任何模型建议都必须回到 Harness 执行链，由 apply、kpatch-build、load/unload/smoke/selftest 和报告证据确认

## 13. 封版检查清单

封版前至少执行：

```bash
python -m pytest tests/reporter/test_release_redaction.py tests/reporter/test_representative_metrics.py tests/scripts/test_holdout_and_demo_scripts.py -q
python scripts/release_redaction_check.py --output data/submission/release_redaction_check.json
python scripts/generate_representative_metrics_report.py --holdout data/evaluations/validation_v0509/final_holdout10_full_run_v0509.json --evidence-manifest data/evaluations/validation_v0509/final_holdout10_evidence_manifest_v0509.json --output-json data/evaluations/validation_v0509/representative_metrics_v0510.json --output-md data/evaluations/validation_v0509/representative_metrics_v0510.md
```

若 `release_redaction_check.py` 发现明文 API Key、root 密码、平台 token 或 cookie，必须先清理再进入提交包生成。
