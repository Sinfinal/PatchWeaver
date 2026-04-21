# PatchWeaver 第四期与总目标验证报告 v0420

## 1. 验证范围

本次验证围绕两个目标展开：

1. 对照第四期实施手册，检查封版交付、模型口径、submission 清单和门禁检查是否已经落地。
2. 对照总设计文档中的项目总目标，核查本地项目当前已经实现到什么程度，并说明哪些部分已经被真实环境验证，哪些部分仍受外部条件限制。

验证时间：

- 本地验证时间：2026-04-20
- 验证机复核时间：2026-04-20

验证对象：

- 本地项目目录：`D:\spaces\ai\PatchWeaver`
- 验证机目录：`<project_root>`
- 验证机地址：`10.223.185.3`

---

## 2. 本地验证结果

### 2.1 代码与构建检查

本地已完成下列检查：

1. `python -m compileall patchweaver`
2. `python -m patchweaver models --json`
3. `python -m patchweaver finalize --json`
4. `python -m patchweaver gate --json`
5. `npm run build`

结果如下：

- Python 代码语法检查通过。
- Web 前端构建通过。
- `models` 命令可正确输出新的模型拓扑和辅助模型边界。
- `finalize` 可正确生成 `submission/` 目录、`final_manifest.json` 和 `final_manifest.md`。
- `gate` 在本地环境返回 `passed`。

### 2.2 第四期落地产物

本地封版产物已生成：

- `submission/manifests/final_manifest.json`
- `submission/manifests/final_manifest.md`
- `submission/manifests/final_gate_report.json`
- `submission/manifests/final_gate_report.md`

同时，`submission/docs` 中已补齐两份第四期新增说明材料：

- `PatchWeaver-模型选型说明.md`
- `PatchWeaver-百炼应用落地说明.md`

### 2.3 文档差异落实情况

对照总设计文档和分期实施手册的新变更，本地项目已经补齐下面几项：

1. 模型策略从“按角色分配多模型”收敛为“单主模型 + 可选辅助模型”。
2. `models.yaml` 中已明确：
   - 主模型
   - 开发口径模型
   - 正式交付模型
   - 回退模型
   - 辅助模型及其边界
   - API Key 的环境变量名、配置文件兜底字段和读取顺序
3. `doctor`、`models`、`finalize`、`gate` 已能直接展示上述模型口径。
4. `models` 命令已支持 `set-api-key`、`set-api-key-env` 和 `clear-api-key`，便于本地联调时维护模型密钥配置。
5. `final_manifest` 已补充文档分类、版本后缀、来源路径、最终存放位置和人工复核标记。
6. Web 总览页已改为展示主模型、交付模型、模型拓扑和辅助模型摘要。

---

## 3. 验证机复核结果

### 3.1 代码同步与环境准备

已通过脚本将本地项目上传到验证机：

- 上传命令：`python scripts/upload_to_validation.py --password ****** --remote-dir <project_root>`

上传后，在验证机上补齐了 Python 依赖：

- `python3 -m pip install -e .`

### 3.2 在验证机上成功执行的命令

在验证机上，下面命令已实际执行并返回正常结果：

1. `python3 -m patchweaver --help`
2. `python3 -m patchweaver doctor --json`
3. `python3 -m patchweaver models --json`
4. `python3 -m patchweaver finalize --json`
5. `python3 -m patchweaver gate --json`

其中验证机上的关键结论如下：

- `doctor` 结果表明：
  - `kpatch-build` 已存在
  - `kernel-devel`、`.config`、`vmlinux` 已就位
  - SSH 构建链可达
  - 模型拓扑与 API Key 配置均已生效
- `models` 结果表明：
  - 模型拓扑已为 `single_primary_with_optional_helpers`
  - 主模型与正式交付模型均为 `qwen-plus-2025-07-28`
  - 辅助模型为 `qwen-coder-turbo-0919`、`qwen-vl-plus-2025-05-07` 和日志摘要模型
  - API Key 状态会显示来源、脱敏值和是否来自 `config/models.yaml`
- `finalize` 已在远端生成 submission 清单与文档包。

### 3.3 验证机 gate 结果

验证机上的 `gate` 返回：

- 总状态：`failed`
- 通过项：`12`
- 失败项：`2`

失败项只有两项：

1. `evaluation_summary`
2. `task_report_closure`

失败原因不是第四期代码缺失，而是这次上传的是代码快照，不包含本地动态运行态：

- 上传脚本默认排除了 `data/`
- 上传脚本默认排除了 `workspaces/`

因此，验证机上的代码壳、配置壳、门禁壳和 submission 机制都能工作，但缺少已经跑完的任务闭环与阶段评测摘要。

### 3.4 验证机真实任务尝试结果

为补齐远端的 `task_report_closure` 和 `evaluation_summary`，在验证机上额外尝试过：

1. `python3 -m patchweaver init --with-db --json`
2. `python3 -m patchweaver create --cve CVE-2024-1086 --task-id TASK-REMOTE-PHASE4-001 --json`
3. `python3 -m patchweaver analyze --task TASK-REMOTE-PHASE4-001 --json`

其中：

- `init` 成功
- `create` 成功
- `analyze` 失败

失败根因已经定位清楚：

- 远端在拉取 `CVE-2024-1086` 对应来源链时，请求 `raw.githubusercontent.com` 失败
- 具体错误为：`[Errno 101] Network is unreachable`

这说明验证机当前对外网络出口受限，导致真实检索链无法完成，因此后续的：

- `run`
- `report`
- `evaluate`

也无法继续形成完整的闭环产物。

结论：

- 验证机已经证明第四期工程壳本身可以启动、可以读取配置、可以做构建预检、可以做封版收口。
- 但验证机当前无法完成真实上游补丁获取，因此“真实任务闭环验证”受外部网络条件限制。

---

## 4. 总设计文档总目标检查

总设计文档中的项目总目标如下：

1. 理解修复意图
2. 识别热补丁约束
3. 生成可解释的改写方案
4. 自动执行构建与验证
5. 对失败进行归因并驱动下一轮尝试
6. 输出结构化报告、日志和产物

本次核查结论如下。

### 4.1 已实现

#### 目标一：理解修复意图

已实现。

依据：

- 本地主链中已经固化 `semantic_card.json`
- 任务详情与报告链中可以回看语义分析产物
- 本地 `gate` 中对应目标状态为“已实现”

#### 目标二：识别热补丁约束

已实现。

依据：

- 已形成 `constraint_report.json`
- 风险项、约束分析结果能够进入报告和后续流程
- 本地 `gate` 中对应目标状态为“已实现”

#### 目标三：生成可解释的改写方案

已实现。

依据：

- 已形成 `rewrite_plan`
- 已形成 `planning_hints`
- 已形成 `PromptPacket / ContextBundle / SkillRoute` 等可解释产物链
- 本地 `gate` 中对应目标状态为“已实现”

#### 目标六：输出结构化报告、日志和产物

已实现。

依据：

- 已输出 `report.json`、`report.md`
- 已输出 `final_manifest`、`final_gate_report`
- 已输出日志文件、JSONL 事件流、artifact index
- 已输出 submission 文档包

### 4.2 部分实现或受环境限制

#### 目标四：自动执行构建与验证

当前为“本地已实现，验证机受环境限制未完全复核”。

依据：

- 本地主链已经接入 `BuildOrchestrator` 与 `Validator`
- 本地 `gate` 对该目标给出“已实现”
- 验证机上的构建预检通过
- 但验证机真实任务在来源获取阶段被外网限制拦截，未能完成完整任务样例

#### 目标五：对失败进行归因并驱动下一轮尝试

当前为“能力已落地，验证机未跑出完整多轮样例”。

依据：

- 本地主链已有失败归因、`failover` 记录、回放链和阶段 trace
- 本地 `gate` 对该目标给出“部分实现”
- 验证机尚未形成完整多轮尝试样例，因此该项未在远端补充验证完成

---

## 5. 最终结论

### 5.1 第四期工程施工结论

第四期要求的核心工程能力已经在本地项目中落地：

- 封版 `submission` 目录
- `final_manifest`
- `final_gate_report`
- 模型选型收口
- 百炼应用落地说明
- 对外材料口径收口

### 5.2 文档差异施工结论

总设计文档和分期实施手册里关于模型策略的新变化，已经落实到项目代码与交付产物中，尤其是：

- 统一采用“单主模型 + 可选辅助模型”
- 不再使用多模型协同主执行链叙事
- 明确区分开发口径与正式交付口径
- 明确辅助模型只承担解释、摘要、视觉辅助等旁路职责

### 5.3 验证结论

1. 本地第四期封版链路已验证通过。
2. 验证机上的工程壳、配置壳、模型壳和 submission 机制已验证通过。
3. 验证机未能完成真实任务闭环，根因是外网访问 `raw.githubusercontent.com` 失败，而不是本次第四期代码施工失败。

### 5.4 后续建议

若要把验证机上的 `gate` 也拉到完全通过，下一步优先做两件事：

1. 放通验证机对 `raw.githubusercontent.com` 等上游来源地址的访问。
2. 为上传脚本增加“可选携带 `data/` 与 `workspaces/` 运行态”的开关，便于把本地已形成的阶段产物一并同步到验证机。

