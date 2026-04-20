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

当前仓库已经具备以下基础能力：

- 最小 CLI 可运行
- 任务目录、配置体系和 SQLite 数据落地已建立
- 真实 `CVE` 检索链已开始接入
- 改写、构建、验证、回放、报告主链已具备最小闭环
- 失败样例已经能够形成较完整的证据链

当前更适合对外展示的内容是：

- 真实 `CVE` 输入和来源链
- 真实任务工作区产物
- 真实失败归因和回放能力

当前仍在持续收口的内容是：

- 稳定成功样例
- `.ko` 构建成功后的完整加载验证闭环
- 更高覆盖度的规则、`Recipe` 和经验库

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
- `docs/PatchWeaver-研发实施与交付总手册_一期.md`
- `docs/PatchWeaver-研发实施与交付总手册_二期.md`
- `docs/PatchWeaver-阶段汇报-2026-04-11.md`

如果是准备阶段汇报或答辩，建议同时查看：

- `E:/Desk/操作系统大赛/操作系统国赛/测试验收/PatchWeaver-一期二期阶段测试与验收报告_v0414.md`
- `E:/Desk/操作系统大赛/操作系统国赛/阶段性成果/样例证据包/失败样例_v0414/PatchWeaver-失败样例证据包_v0414.md`

## 9. 当前边界说明

当前版本已经能够稳定展示“真实输入 + 真实失败归因 + 真实回放”的主链，但还不适合对外宣称已经稳定实现“成功构建并完成加载验证”的全链目标。

现阶段对外表述建议保持一致：

- 工程主链已经落地
- 失败证据链已经具备展示价值
- 成功样例正在固化中

## 10. 联系当前阶段材料

如果需要快速准备阶段汇报或答辩，建议直接围绕下面这几类材料展开：

- 第二期测试与验收记录
- 第二期阶段汇报提纲
- 演示脚本与录屏说明
- 失败样例证据包
- 答辩问答稿与截图索引

这样可以避免临时翻目录，也更容易保持口径一致。
