

<p align="center">
  <a href="LICENSE"><img alt="License MIT" src="https://img.shields.io/badge/license-MIT-111827?style=flat-square&labelColor=374151&color=10b981"></a>
  <img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11%2B-1f2937?style=flat-square&labelColor=111827&color=3b82f6">
  <img alt="Anolis OS ANCK" src="https://img.shields.io/badge/Anolis%20OS-ANCK%206.6-1f2937?style=flat-square&labelColor=111827&color=f59e0b">
  <img alt="kpatch" src="https://img.shields.io/badge/kpatch-livepatch-1f2937?style=flat-square&labelColor=111827&color=22c55e">
  <img alt="Agent" src="https://img.shields.io/badge/agent-CVE%20livepatch-0f172a?style=flat-square&labelColor=020617&color=06b6d4">
</p>

# PatchWeaver
面向 Anolis OS ANCK 内核 CVE 的热补丁自动生成 Agent。

PatchWeaver 的目标是让使用者输入一个内核 CVE 后，系统能够自动获取修复补丁、理解修复意图、选择适合 `kpatch` 的改写策略、生成 livepatch `.ko`，并完成加载、卸载、冒烟测试、自测和结构化报告输出。

![img_1.png](docs/images/封面.png)

## 项目简介

PatchWeaver 面向操作系统内核热补丁生成场景，围绕 `CVE -> Patch -> Rewrite -> kpatch-build -> Validate -> Report` 建立完整自动化链路。

![PatchWeaver 总流程图占位](docs/images/PatchWeaver_总流程图占位.png)

系统不是简单执行脚本，而是由 Agent 驱动的工程闭环：

- `CVE` 来源获取：自动定位上游或 stable 修复来源，保存原始 patch 和来源证据。
- 修复意图理解：生成 `RepairIntent`，记录漏洞触发条件、插入点、安全退出路径和必须保留的副作用。
- 约束诊断：识别目标源码状态、模块启用状态、`kpatch` 后端限制和失败原因。
- 改写规划：根据诊断结果选择 `direct_apply`、`minimal_livepatch_wrap`、`section_change_avoidance`、`semantic_guard_rewrite` 等策略。
- 构建验证：调用 `kpatch-build` 生成 livepatch `.ko`，并执行 `load / unload / smoke / selftest`。
- 报告回放：输出 `report.json`、`report.md`、构建日志、验证报告和可回放证据链。

![PatchWeaver Agent 决策闭环占位](docs/images/PatchWeaver Agent 决策闭环占位.png)

## 快速使用

建议运行环境：

- Python `3.11+`
- Anolis OS 目标内核验证环境
- `kpatch-build`
- 与目标内核匹配的源码树、`.config`、`Module.symvers`、`vmlinux`

### 首选方式：Docker Compose

推荐优先使用 Docker Compose 启动 Web/API 和交付入口。Compose 默认启动两个交付容器：

- `patchweaver-api`：后端 API、CLI、任务创建、报告查询和百炼/FC/MCP 网关联调。
- `patchweaver-web`：前端 Web 控制台静态站点，基于 Nginx 暴露 `/console/`，并把 `/api` 反向代理到 `patchweaver-api`。

该方式会构建标准运行镜像，并把 `data/`、`workspaces/`、`docs/submission/` 挂载到 API 容器内，便于复现任务、查看报告和对接百炼/FC/MCP 网关。

```bash
docker compose -f build/patchweaver/compose.yml up --build patchweaver-api patchweaver-web
```

如果测评环境不能直接访问 Docker Hub，可通过环境变量指定已允许访问的 Python、Node 和 Nginx 基础镜像：

```bash
PATCHWEAVER_PYTHON_BASE_IMAGE=docker.1ms.run/library/python:3.11-slim \
PATCHWEAVER_NODE_BASE_IMAGE=docker.1ms.run/library/node:20-alpine \
PATCHWEAVER_NGINX_BASE_IMAGE=docker.1ms.run/library/nginx:1.27-alpine \
docker compose -f build/patchweaver/compose.yml up --build patchweaver-api patchweaver-web
```

安装后先做 API/Web 容器可用性检查：

```bash
curl -fsS http://localhost:18084/healthz
curl -fsS http://localhost:18084/api/v1/overview
curl -fsS http://localhost:18085/console/
```

再在容器内创建一个已知样例任务，确认 CLI、数据卷和 API 查询链路可用：

```bash
docker compose -f build/patchweaver/compose.yml exec patchweaver-api \
  patchweaver create \
  --cve CVE-2024-26742 \
  --task-id demo-container-26742 \
  --profile demo \
  --max-attempts 1 \
  --force-new \
  --json

curl -fsS http://localhost:18084/api/v1/tasks/demo-container-26742
curl -fsS http://localhost:18085/api/v1/tasks/demo-container-26742
```

如果运行环境只有 Docker Engine、没有 `docker compose` 插件，可使用等价的纯 Docker 启动方式：

```bash
docker build \
  --build-arg PYTHON_BASE_IMAGE="${PATCHWEAVER_PYTHON_BASE_IMAGE:-python:3.11-slim}" \
  -f build/patchweaver/Dockerfile \
  -t patchweaver:local \
  .
docker rm -f patchweaver-api 2>/dev/null || true
docker run -d --name patchweaver-api -p 18084:18084 \
  -e PATCHWEAVER_PROFILE=demo \
  -e PATCHWEAVER_BAILIAN_API_KEY="${PATCHWEAVER_BAILIAN_API_KEY:-}" \
  -e PYTHONIOENCODING=utf-8 \
  -e PYTHONUTF8=1 \
  -v "$(pwd)/data:/app/data" \
  -v "$(pwd)/workspaces:/app/workspaces" \
  -v "$(pwd)/docs/submission:/app/docs/submission" \
  -v "$(pwd)/config:/app/config:ro" \
  -v "$(pwd)/evaluations:/app/evaluations:ro" \
  patchweaver:local
```

Web 容器也可以独立构建和运行：

```bash
docker build \
  --build-arg NODE_BASE_IMAGE="${PATCHWEAVER_NODE_BASE_IMAGE:-node:20-alpine}" \
  --build-arg NGINX_BASE_IMAGE="${PATCHWEAVER_NGINX_BASE_IMAGE:-nginx:1.27-alpine}" \
  -f build/patchweaver/web.Dockerfile \
  -t patchweaver-web:local \
  .
docker rm -f patchweaver-web 2>/dev/null || true
docker run -d --name patchweaver-web -p 18085:18085 --link patchweaver-api:patchweaver-api patchweaver-web:local
```

需要真实 `kpatch-build` 和模块加载验证时，建议在验证机裸机运行，或使用 privileged validation 容器并挂载宿主机内核材料：

```bash
docker compose -f build/patchweaver/compose.yml --profile validation run --rm patchweaver-validation
```

容器化启动以本 README 中的 Docker Compose / Docker 命令为准。API/Web 容器 smoke 只证明安装、入口和查询链路可用；真实内核验证仍按 `docs/deployment.md` 准备宿主机内核材料。

### 备选方式：裸机安装

当需要直接访问宿主机内核、`kpatch-build`、`vmlinux`、`Module.symvers` 或执行 livepatch 模块加载时，使用裸机安装。部署人员可以先执行一键部署预检查。`dry-run` 只输出检查结果和执行计划，不会安装依赖、初始化数据库或触发构建：

```bash
python scripts/install_patchweaver.py --dry-run --json --target-kernel 6.6.102-5.2.an23.x86_64
```

确认验证机环境无阻塞问题后，再执行最小部署：

```bash
python scripts/install_patchweaver.py --with-db --target-kernel 6.6.102-5.2.an23.x86_64
```

如需手动执行，可使用等价命令：

```bash
python -m pip install -e .
python -m patchweaver init --with-db --json
python -m patchweaver doctor --json
```

更完整的验证机部署、源码基线、`kpatch-build` 和 Web/API 检查见 `docs/deployment.md`。

运行一个 CVE 任务：

```bash
python -m patchweaver create --cve CVE-2024-26742 --task-id demo-26742 --json
python -m patchweaver analyze --task demo-26742 --json
python -m patchweaver run --task demo-26742 --json
python -m patchweaver report --task demo-26742 --json
python -m patchweaver replay --task demo-26742 --json
```

启动 Web/API 服务：

```bash
python -m patchweaver serve-api --host 0.0.0.0 --port 18084
```

常用 API 能力包括任务创建、任务状态查询、报告查询和 Agent 决策查看。百炼应用可通过 Function Compute 或稳定 HTTPS 网关调用这些接口。

![PatchWeaver 使用入口占位](docs/images/PatchWeaver 使用入口占位.png)

## 效果展示

当前封版验证使用 confirmed 正向样例池、Final 风格 holdout 候选和混合 Challenge 批次作为主效果证据。以下结果只代表本项目公开代表集和本轮复测环境，不承诺官方 Final 隐藏集必然取得相同成功率。

![PatchWeaver 效果展示占位](docs/images/PatchWeaver 效果展示占位.png)

| 指标 | 当前结果 |
| --- | --- |
| confirmed 正向样例池 | `12` 条完整证据 |
| Final 风格 holdout | `5/5` 完成 `.ko` 构建与动态验证 |
| 混合 Challenge 批次 | `5/14` 成功，其余按边界原因归因 |
| 动态验证 | 成功样例均完成 `load / unload / smoke / selftest` |
| 正向代表集成功率 | `100%` |
| 平均尝试轮次 | `1.0` |
| 赛题目标参考 | Final 集合 `60%+` 成功率 |



单个成功样例会保留以下关键产物：

- `repair_intent.json`：修复意图和安全语义。
- `rewritten.patch`：最终进入构建的改写补丁。
- `semantic_guard.json`：语义守卫或改写策略记录。
- `build_summary.json`：构建结果和 `.ko` 产物信息。
- `validation_report.json`：加载、卸载、冒烟测试和自测结果。
- `report.json / report.md`：面向评审和回放的汇总报告。

## 百炼交付入口

PatchWeaver 已提供百炼应用对接所需的 Web/API 与 Function Compute 网关封装。使用者可通过百炼应用触发任务，并查看任务状态、构建结果、失败归因和 Agent 下一步决策。

为了保证交付安全，仓库不会保存真实 API Key、服务器密码或平台 Token。正式部署时请通过环境变量、平台 Secret 或云函数安全配置注入密钥。

## 目录说明

```text
patchweaver/                 核心 Python 包
scripts/                     验证、打包、报告和交付脚本
tmp/                         本地临时脚本、内部测试和一次性验证材料，不纳入提交
config/                      非敏感配置模板
evaluations/fixtures/        固定样例集输入
data/evaluations/            代表集、正向池和测试指标
data/submission/             脱敏检查、云函数包和临时交付产物
docs/                        对外部署、API 验证、交付说明、图片资源和提交快照
docs/submission/             生成的提交快照、证据包和 manifest
workspaces/                  单个 CVE 任务的运行产物目录
```

## 许可证

本项目采用 MIT License，见 `LICENSE`。
