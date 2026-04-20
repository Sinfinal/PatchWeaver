# PatchWeaver 一期工作包人工测试与验收报告

## 1. 测试范围与环境配置

### 1.1 测试范围

本次仅验证 `PatchWeaver` 第一期工作包：

- `WP-I-01` 工程初始化与仓库结构
- `WP-I-02` 初版依赖、配置与 CLI
- `WP-I-03` 核心对象、接口与数据落地
- `WP-I-04` 首批代码文件与开发顺序
- `WP-I-05` MVP 路线与调试链路
- `WP-I-06` 三人分工与项目排期
- `WP-I-07` 测试体系与验收标准
- `WP-I-08` 交付、提交与答辩准备

验收依据：

- `D:\desktop\OS功能挑战\操作系统国赛\开发\PatchWeaver-总方案与创新设计总文档_v0412.md`
- `D:\desktop\OS功能挑战\操作系统国赛\开发\PatchWeaver-研发实施与交付总手册_一期_v0413.md`
- `D:\desktop\OS功能挑战\操作系统国赛\测试验收\PatchWeaver-一期二期工作包检验报告_v0414.md`
- `D:\desktop\OS功能挑战\操作系统国赛\测试验收\PatchWeaver-一期二期阶段测试与验收报告_v0414.md`

### 1.2 测试边界

依据总设计文档 `2.4`、`2.5` 与一期手册 `Challenge / Final` 边界说明，本次人工验收遵守以下约束：

- 第一期仅使用少量 `Challenge` 样例做本地链路验证。
- `Final` 数据集不纳入本次本地人工验收。
- 验收同时检查命令、代码入口、产物、报告与文档口径，不只检查“能否运行”。

### 1.3 当前主机环境

- 测试时间：`2026-04-20`
- 操作系统：`Microsoft Windows NT 10.0.22000.0`
- 项目路径：`F:\Work_Space\PatchWeaver`
- Python 解释器：`F:\Anaconda\python.exe`
- Python 版本：`3.13.9`
- Git 版本：`2.44.0.windows.1`
- 当前生效工作区目录：`F:\Work_Space\PatchWeaver\workspaces`
- 当前生效数据库路径：`F:\Work_Space\PatchWeaver\data\patchweaver.db`
- 当前生效 manifest 目录：`F:\Work_Space\PatchWeaver\data\manifests`
- 默认目标内核：`6.6.102-5.2.an23.x86_64`
- 远端环境：`root@10.223.185.3`
- 远端项目根目录：`/root/patchweaver`

### 1.4 本次主样例任务

- 主样例：`CVE-2024-1086`
- 主任务名：`TASK-STAGE-I-20260420-1086`
- 主任务目录：`F:\Work_Space\PatchWeaver\workspaces\TASK-STAGE-I-20260420-1086`
- 本报告保存位置：`F:\Work_Space\PatchWeaver\workspaces\TASK-STAGE-I-20260420-1086\reports\PatchWeaver-一期工作包人工测试与验收指导报告_v0420.md`

补充说明：

- `CVE-2022-0185` 作为补充 `Challenge` 样例，本轮未执行。
- `Final` 数据集本轮未执行。

## 2. 工作包验证清单

| 工作包编号 | 验证项 | 预期结果 | 实际结果 | 备注 |
| --- | --- | --- | --- | --- |
| `WP-I-01` | 工程初始化与仓库结构 | 核心目录、运行目录、模板目录齐备 | `通过` | 项目根目录存在 `config/`、`data/`、`workspaces/`、`rules/`、`recipes/`、`skills/`、`prompts/`、`evaluations/`、`tests/`、`docs/`、`web/`；任务目录已建立标准结构 |
| `WP-I-02` | 初版依赖、配置与 CLI | CLI 可调用，配置文件完整，数据库与 API 入口可用 | `基本通过` | `--help`、`paths --json`、`doctor --json`、`init --with-db --json` 均通过；`doctor` 结果为 `43 ok / 0 warn / 0 error`；但 `serve-api` 因缺少 `uvicorn` 失败 |
| `WP-I-03` | 核心对象、接口与数据落地 | 核心对象、SQLite 表结构、工作区产物契约稳定 | `基本通过` | `task_context.json`、`patch_bundle.json`、`semantic_card.json`、`constraint_report.json`、`report.json` 等产物已落盘；但 `attempts` 表未写入本轮尝试记录，导致 `report/replay` 与工作区实际尝试不一致 |
| `WP-I-04` | 首批代码文件与开发顺序 | 主链模块、关键文件、目录组织与一期手册一致 | `通过` | 代码结构与一期手册目录规划一致，主链模块齐备 |
| `WP-I-05` | MVP 路线与调试链路 | 至少打通“创建任务 -> 分析 -> 尝试 -> 报告 -> 回放”的最小链路 | `基本通过` | `status`、`analyze`、`run`、`report`、`replay` 已执行；分析成功，尝试轮落盘，失败类型明确，报告可生成；但 `run` 停在 `apply precheck`，未进入 `kpatch-build` 成功态 |
| `WP-I-06` | 三人分工与项目排期 | 文档中已有分工、里程碑、依赖关系和交接项 | `通过` | 本轮未发现与一期手册第 8 章冲突的工程口径问题 |
| `WP-I-07` | 测试体系与验收标准 | 一期测试矩阵、验收标准、基础测试入口存在 | `部分通过` | `compileall` 通过，`doctor` 单测通过；但 `context`、`skills`、`harness replay` 测试因硬编码 `E:\\Desk\\patchweaver_pytest_cases` 失败 |
| `WP-I-08` | 交付、提交与答辩准备 | README、文档、阶段材料、样例说明和验收记录可交付 | `基本通过` | `README`、总设计文档、一期手册、任务工作区证据链、本报告均已具备；但严格成功样例闭环仍未形成，不宜判“完整通过” |

## 3. 测试流程与执行结果

### 3.1 环境基线检查

执行命令：

```powershell
& 'F:\Anaconda\python.exe' -m patchweaver --help
& 'F:\Anaconda\python.exe' -m patchweaver paths --json
$env:PATCHWEAVER_REMOTE_PASSWORD='b314B314'
& 'F:\Anaconda\python.exe' -m patchweaver doctor --json
& 'F:\Anaconda\python.exe' -m patchweaver init --with-db --json
```

执行结果：

- `patchweaver --help`：通过，完整输出命令树。
- `patchweaver paths --json`：通过，返回当前主机上的有效路径配置。
- `patchweaver doctor --json`：通过，结果为 `43 ok / 0 warn / 0 error`。
- `patchweaver init --with-db --json`：通过，数据库初始化正常。

关键结论：

- 当前本地解释器、配置、SQLite、技能目录、bootstrap 目录均可用。
- 远端环境已联通，`kpatch-build`、`.config`、`vmlinux` 均可见。
- 远端 `kernel_src_dir=/opt/kernel-src` 不存在，但系统当前正确回退到 `/usr/src/kernels/6.6.102-5.2.an23.x86_64`。

### 3.2 API 入口检查

执行命令：

```powershell
& 'F:\Anaconda\python.exe' -m patchweaver serve-api --host 127.0.0.1 --port 18084
```

执行结果：

- 未通过。
- 错误原因为 `ModuleNotFoundError: No module named 'uvicorn'`。
- 因服务未启动，`/healthz` 与 `/api/v1/overview` 未能完成访问。

结论：

- `serve-api` 入口已在 CLI 中暴露，但当前主机缺少 API 运行依赖，不能视为本轮通过。

### 3.3 主样例任务状态检查

执行命令：

```powershell
& 'F:\Anaconda\python.exe' -m patchweaver status --task TASK-STAGE-I-20260420-1086 --json
```

执行结果：

- 初始状态：`created`
- 运行后状态：`failed`
- `current_attempt = 1`

结论：

- 主样例任务 `TASK-STAGE-I-20260420-1086` 已被系统识别和管理，任务状态在运行后发生了正确迁移。

### 3.4 分析链验证

执行命令：

```powershell
$env:PATCHWEAVER_REMOTE_PASSWORD='b314B314'
& 'F:\Anaconda\python.exe' -m patchweaver analyze --task TASK-STAGE-I-20260420-1086 --json
```

执行结果：

- 第一次执行失败：`[WinError 10054] 远程主机强迫关闭了一个现有的连接`
- 第二次重试成功，生成以下关键产物：
  - `input\patch_bundle.json`
  - `input\source_evidence.json`
  - `analysis\semantic_card.json`
  - `analysis\constraint_report.json`
  - `analysis\bootstrap\bootstrap_manifest.json`
  - `analysis\trace\analysis_trace.json`

关键证据：

- `patch_bundle.json` 中已出现真实来源链：
  - `upstream_commit = f342de4e2f33e0e39165d8639387aa6c19dff660`
  - `commit_message = netfilter: nf_tables: reject QUEUE/DROP verdict parameters`
  - `affected_files = net/netfilter/nf_tables_api.c`

结论：

- 分析链成功打通。
- 外部源存在瞬时不稳定，但重试后可以获得真实 `CVE` 来源链与分析产物。

### 3.5 尝试链、失败归因与验证链

执行命令：

```powershell
$env:PATCHWEAVER_REMOTE_PASSWORD='b314B314'
& 'F:\Anaconda\python.exe' -m patchweaver run --task TASK-STAGE-I-20260420-1086 --json
```

执行结果：

- 尝试编号：`TASK-STAGE-I-20260420-1086-A001`
- 本轮状态：`failed`
- 失败类型：`patch_apply_failed`

关键产物：

- `attempts\001\attempt_state.json`
- `attempts\001\rewrite\rewrite_plan.json`
- `attempts\001\rewrite\rewritten.patch`
- `attempts\001\rewrite\apply_precheck.json`
- `attempts\001\logs\build.log`
- `attempts\001\logs\failure_record.json`
- `attempts\001\artifacts\build_summary.json`
- `attempts\001\artifacts\validation_report.json`
- `attempts\001\trace\harness_trace.json`

失败摘要：

- `failure_record.json`：
  - `failure_type = patch_apply_failed`
  - `summary = error: net/netfilter/nf_tables_api.c: No such file or directory`

- `build_summary.json`：
  - `status = precheck_failed`
  - `summary = apply 级预检查未通过，已跳过远端构建。`
  - `source_dir = /usr/src/kernels/6.6.102-5.2.an23.x86_64`

- `harness_trace.json` 显示主链已走到：
  - `analyzed -> rewrite_recipe -> build -> failure_analysis -> validation`

验证结果：

- `validation_report.json` 显示：
  - `semantic_precheck = passed`
  - `load_result = pending`
  - `unload_result = pending`
  - `smoke_result = pending`
  - `semantic_guard_result = pending`

结论：

- 一期主链已走到“真实改写 -> apply 预检查 -> 失败归因 -> 验证报告”阶段。
- 本轮未进入真实 `kpatch-build` 成功态，也未产生可加载模块。

### 3.6 报告与回放验证

执行命令：

```powershell
& 'F:\Anaconda\python.exe' -m patchweaver report --task TASK-STAGE-I-20260420-1086 --json
& 'F:\Anaconda\python.exe' -m patchweaver replay --task TASK-STAGE-I-20260420-1086 --json
```

执行结果：

- `report`：通过，生成：
  - `reports\report.json`
  - `reports\report.md`
- `replay`：通过，生成：
  - `reports\evaluation_summary.json`

发现的问题：

- `status` 已显示 `current_attempt = 1`，且工作区内存在完整 `attempts\001` 目录。
- 但 SQLite `attempts` 表中没有 `TASK-STAGE-I-20260420-1086-A001` 记录。
- 因此：
  - `report.json` 中 `attempt_digest = []`
  - `evaluation_summary.json` 中 `total_attempts = 0`
  - `replay` 返回 `latest_attempt_id = null`

结论：

- 报告与回放命令本身可执行。
- 但当前任务的“工作区尝试产物”与“数据库尝试记录”不一致，导致回放摘要不完整。

### 3.7 一期辅助测试

执行命令：

```powershell
& 'F:\Anaconda\python.exe' -m compileall patchweaver
& 'F:\Anaconda\python.exe' -m pytest tests/doctor/test_doctor_service.py -q
& 'F:\Anaconda\python.exe' -m pytest tests/context/test_context_prompt_memory.py -q
& 'F:\Anaconda\python.exe' -m pytest tests/skills/test_skill_router.py -q
& 'F:\Anaconda\python.exe' -m pytest tests/harness/test_replay_evaluator.py -q
```

执行结果：

| 测试项 | 结果 | 说明 |
| --- | --- | --- |
| `python -m compileall patchweaver` | 通过 | 包级语法检查通过 |
| `tests/doctor/test_doctor_service.py -q` | 通过 | `1 passed` |
| `tests/context/test_context_prompt_memory.py -q` | 未通过 | `1 failed`，原因是硬编码路径 `E:\Desk\patchweaver_pytest_cases` 无权限 |
| `tests/skills/test_skill_router.py -q` | 未通过 | `1 passed, 2 failed`，失败原因同上 |
| `tests/harness/test_replay_evaluator.py -q` | 未通过 | `2 passed, 2 failed`，失败原因同上 |

结论：

- 一期测试体系的核心文件已存在，且部分模块测试可通过。
- 但当前主机上，多项测试受硬编码路径 `E:\Desk\patchweaver_pytest_cases` 影响，无法直接作为稳定回归入口。

## 4. 验收成果指标对照

### 4.1 成功样例验收指标

根据一期手册 `9.5`，成功样例必须满足：

1. patch 获取成功
2. 主状态机由 `AttemptEngine` 统一维护
3. 至少产生一轮有效改写尝试
4. `kpatch-build` 成功
5. 模块可加载
6. 模块可卸载
7. 生成完整报告、trace 和产物

本轮对照结果：

| 指标 | 结果 |
| --- | --- |
| patch 获取成功 | 达到 |
| 主状态机维护 | 基本达到，任务状态已迁移到 `failed` |
| 至少一轮有效改写尝试 | 达到 |
| `kpatch-build` 成功 | 未达到 |
| 模块可加载 | 未达到 |
| 模块可卸载 | 未达到 |
| 生成完整报告、trace 和产物 | 基本达到，报告与 trace 已生成，但回放摘要受 DB 记录缺失影响 |

### 4.2 失败样例验收指标

根据一期手册 `9.5`，失败样例也必须满足：

1. 输入来源可追溯
2. 失败轮次清晰
3. 每轮失败有明确分类
4. 最终报告说明失败原因和尝试策略
5. 若启用 `subagent`，不存在越权写主源码树或直接发起构建的记录
6. 若发生 failover，存在清晰的 `FailoverRecord`

本轮对照结果：

| 指标 | 结果 |
| --- | --- |
| 输入来源可追溯 | 达到，`patch_bundle.json/source_evidence.json` 已生成 |
| 失败轮次清晰 | 达到，当前为 `attempt 001` |
| 每轮失败有明确分类 | 达到，`failure_type = patch_apply_failed` |
| 报告说明失败原因和尝试策略 | 基本达到，`failure_record.json`、`build_summary.json`、`report.json` 已生成 |
| 无越权记录 | 当前未发现 `subagent_records` |
| failover 记录 | 本轮未发生 failover，`failover.jsonl` 为空 |

### 4.3 文档验收指标

根据一期手册 `9.5`、`9.6`，至少检查：

| 文档项 | 结果 |
| --- | --- |
| 总设计文档 | 已存在 |
| 第一期实施手册 | 已存在 |
| `README` 与环境说明 | 已存在 |
| 第一阶段测试说明或验收记录 | 本报告已形成 |
| 文档命令和路径与当前仓库一致 | 基本一致，已统一使用 `F:\Work_Space\PatchWeaver` 口径 |

## 5. 命令执行记录

| 步骤 | 命令 | 预期结果 | 实际结果 | 证据文件/截图 |
| --- | --- | --- | --- | --- |
| 环境检查 | `patchweaver doctor --json` | 返回结构化检查结果 | 通过，`43 ok / 0 warn / 0 error` | `doctor` JSON 输出 |
| 初始化 | `patchweaver init --with-db --json` | 初始化目录和数据库 | 通过 | `init` JSON 输出 |
| 状态检查 | `patchweaver status --task TASK-STAGE-I-20260420-1086 --json` | 返回任务状态 | 通过，运行后状态为 `failed/current_attempt=1` | `task_context.json`、`status` JSON 输出 |
| 分析链路 | `patchweaver analyze --task TASK-STAGE-I-20260420-1086 --json` | 生成分析产物 | 首次失败后重试通过 | `input\patch_bundle.json`、`analysis\semantic_card.json`、`analysis\constraint_report.json` |
| 尝试链路 | `patchweaver run --task TASK-STAGE-I-20260420-1086 --json` | 生成尝试轮和 trace | 失败，`failure_type=patch_apply_failed` | `attempts\001\logs\failure_record.json`、`attempts\001\trace\harness_trace.json` |
| 报告 | `patchweaver report --task TASK-STAGE-I-20260420-1086 --json` | 生成 `report.json/report.md` | 通过 | `reports\report.json`、`reports\report.md` |
| 回放 | `patchweaver replay --task TASK-STAGE-I-20260420-1086 --json` | 输出最近一轮回放摘要 | 通过，但摘要中 `attempt_count=0` | `reports\evaluation_summary.json` |
| API 健康检查 | `patchweaver serve-api --host 127.0.0.1 --port 18084` | 服务启动并可访问接口 | 失败，缺少 `uvicorn` | `data\logs\stage1_api_18084.err.log` |
| 语法检查 | `python -m compileall patchweaver` | 包级语法检查通过 | 通过 | 命令输出 |
| 定向测试 | `pytest tests/doctor/test_doctor_service.py -q` | 通过 | 通过，`1 passed` | 命令输出 |
| 定向测试 | `pytest tests/context/test_context_prompt_memory.py -q` | 通过 | 失败，`E:\Desk\patchweaver_pytest_cases` 权限问题 | 命令输出 |
| 定向测试 | `pytest tests/skills/test_skill_router.py -q` | 通过 | 部分失败，`1 passed, 2 failed` | 命令输出 |
| 定向测试 | `pytest tests/harness/test_replay_evaluator.py -q` | 通过 | 部分失败，`2 passed, 2 failed` | 命令输出 |

## 6. 工作包结论记录

| 工作包编号 | 本次人工结论 | 证据摘要 | 是否满足一期要求 |
| --- | --- | --- | --- |
| `WP-I-01` | `通过` | 仓库结构与任务目录骨架齐备 | `是` |
| `WP-I-02` | `基本通过` | CLI/配置/doctor/init 正常，API 缺少 `uvicorn` | `基本满足` |
| `WP-I-03` | `基本通过` | 核心对象、任务状态、分析与报告产物已落盘，但 `attempts` 表缺失本轮记录 | `基本满足` |
| `WP-I-04` | `通过` | 首批主链模块和关键文件齐备 | `是` |
| `WP-I-05` | `基本通过` | 已打通创建、分析、尝试、失败归因、报告、回放；未达到 `kpatch-build` 成功态 | `基本满足` |
| `WP-I-06` | `通过` | 未发现与一期文档口径冲突的分工/排期问题 | `是` |
| `WP-I-07` | `部分通过` | 编译检查和部分测试通过，但多项测试受硬编码路径阻塞 | `部分满足` |
| `WP-I-08` | `基本通过` | README、文档、任务证据链和本报告已具备，最终成功样例闭环仍缺失 | `基本满足` |

## 7. 问题与建议

- 发现问题：`serve-api` 因缺少 `uvicorn` 无法启动，说明 API 入口仍依赖未补齐的运行时包。
- 发现问题：`analyze` 第一次执行出现 `[WinError 10054]`，说明外部来源链存在瞬时网络不稳定，需要允许重试。
- 发现问题：`run` 已在工作区落下完整 `attempts\001` 产物，但 SQLite `attempts` 表没有对应记录，导致 `report/replay` 把尝试数统计为 `0`。这是当前一期验收中最明确的数据一致性问题。
- 发现问题：`run` 失败类型为 `patch_apply_failed`，失败摘要为 `net/netfilter/nf_tables_api.c: No such file or directory`，说明当前远端参与预检查的源码目录并不是适合该补丁的完整源码树。
- 发现问题：一期定向测试中，`context`、`skills`、`harness replay` 多个用例都硬编码 `E:\Desk\patchweaver_pytest_cases`，在当前主机上导致权限失败，影响 `WP-I-07` 的直接回归能力。

- 建议改进：补齐 `uvicorn`，把 `serve-api` 变成可直接验收的能力，而不是仅停留在 CLI 入口存在。
- 建议改进：修复尝试轮写入数据库的链路，使 `status`、`report`、`replay` 与 `attempts\001` 工作区证据保持一致。
- 建议改进：优先解决远端源码树与补丁目标文件不匹配的问题，否则一期严格验收会持续停在 `apply precheck` 阶段。
- 建议改进：把测试中的硬编码路径改为项目内临时目录或 `pytest` 标准临时目录，恢复一期测试体系在当前主机上的可移植性。
- 建议改进：在下一轮一期复检中，优先尝试至少形成一条成功进入 `kpatch-build` 的 fresh task 证据链，再判断是否达到“完整验收通过”。

## 8. 最终结论

本轮基于 `TASK-STAGE-I-20260420-1086` 的一期人工验收结论如下：

- 一期工程底座、配置、CLI、分析链、尝试链、失败归因、报告生成能力已经形成真实可运行证据。
- 一期主样例已完成“真实 `CVE` 输入 -> 真实来源链获取 -> 分析 -> 一轮尝试 -> 失败归因 -> 报告/回放”的最小闭环。
- 但当前仍未达到一期严格意义上的“完整验收通过”，主要差距有三项：
  1. 本轮未真正进入 `kpatch-build` 成功态。
  2. 未形成成功模块的加载/卸载验证证据。
  3. `attempts` 数据库记录与工作区尝试产物不一致，影响回放与统计可信度。

综合判断：

- 第一期：`基本达到阶段目标`
- 第一期：`未达到严格完整验收通过`
