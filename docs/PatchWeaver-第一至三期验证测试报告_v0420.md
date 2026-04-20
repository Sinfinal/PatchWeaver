# PatchWeaver 第一期至第三期验证测试报告

## 1. 报告说明

本报告记录 2026-04-20 在验证机 `10.223.185.3` 上完成的第一期、第二期、第三期验证结果。

本次验证目标有两类：

1. 确认当前本地项目在真实 `Anolis OS + kpatch-build` 环境中的可运行情况。
2. 对照一期、二期、三期实施手册，核查阶段能力是否已经在验证机上落地。

本次验证使用的是独立验证副本，不直接覆盖验证机原有目录。

- 验证目录：`/root/patchweaver_validate_20260420`
- 验证内核：`6.6.102-5.2.an23.x86_64`
- Python：`3.11.6`
- `kpatch-build`：`/usr/bin/kpatch-build`

## 2. 验证前处理

### 2.1 验证副本准备

本次没有直接在验证机已有 `/root/patchweaver` 目录上操作，而是将当前本地项目打包后同步到：

- `/root/patchweaver_validate_20260420`

这样做的目的有两个：

1. 不影响验证机上已有历史样例和旧版本材料。
2. 便于把本次验证过程和阶段报告中的证据路径固定下来。

### 2.2 运行环境准备

验证机原生只有 `python3`，没有现成的 `pip`、`pytest` 和前端环境。

本次在验证副本目录中完成了以下准备：

- 建立 `.venv`
- 离线安装项目运行依赖
- 以 editable 方式安装当前验证副本

### 2.3 验证口径修正

验证开始时，项目默认 `build.yaml` 更偏向“本地开发机远程驱动验证机”的控制端口径，直接在验证机本机执行时，初始 `doctor` 暴露出下面两个问题：

1. 构建配置仍指向旧的源码与 `vmlinux` 路径。
2. 远端密码环境变量未设置，`ssh` 构建后端无法直接自检通过。

因此，本次只在验证副本中对 `config/build.yaml` 做了验证口径修正：

- `remote_host` 改为 `127.0.0.1`
- `kernel_src_dir` 改为 `/usr/src/kernels/6.6.102-5.2.an23.x86_64`
- `kernel_devel_dir` 改为 `/usr/src/kernels/6.6.102-5.2.an23.x86_64`
- `vmlinux_path` 改为 `/usr/lib/debug/usr/lib/modules/6.6.102-5.2.an23.x86_64/vmlinux`
- `remote_workspace_root` 改为 `/root/patchweaver_validate_20260420/_remote_build`

说明：

- 这一步只作用于验证副本。
- 本地仓库中的正式配置未被本次远端验证直接覆盖。

### 2.4 验证期间修复的代码问题

在二期真实来源链验证中，发现检索链存在两个健壮性问题：

1. `NVD` 接口返回 `503` 时，分析阶段直接失败，没有回退到 `cvelistV5`。
2. `git.kernel.org` 的 commit 链接被统一转成 GitHub `.patch`，而验证机上 GitHub patch 拉取不稳定。

本次已经在项目代码中补了这两个点，并重新同步到验证副本：

- `patchweaver/retriever/source_router.py`
- `patchweaver/retriever/repair_chain.py`

对应新增回归测试：

- `tests/retriever/test_source_router.py`
- `tests/retriever/test_repair_chain.py`

本地回归结果：

- `3 passed`

### 2.5 手工复核前置步骤

为方便人工复核，本次验证使用的前置环境如下。

登录验证机后，先执行：

```bash
cd /root/patchweaver_validate_20260420
. .venv/bin/activate
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
export PYTHONIOENCODING=utf-8
export PATCHWEAVER_REMOTE_PASSWORD='b314B314'
```

若要先确认当前验证副本是否存在，可执行：

```bash
pwd
ls
python --version
python -m patchweaver --help
```

人工复核时建议按下面顺序进行：

1. 先复核第一期基础命令，确认 CLI、路径、数据库和环境诊断无问题。
2. 再复核第二期两个固定样例，观察 `create -> analyze -> run -> report -> replay` 是否可完整留痕。
3. 最后复核第三期的 `evaluate`、Web API 和增强产物目录。

本报告中的所有路径、任务编号和产物位置，均以这套验证副本为准。

## 3. 第一期验证结果

### 3.1 验证命令

在验证机上执行了下面这些一期基础命令：

- `python -m patchweaver version`
- `python -m patchweaver init --with-db --json`
- `python -m patchweaver paths --json`
- `python -m patchweaver doctor --json`
- `python -m patchweaver init-db --json`
- `python -m patchweaver db path --json`

### 3.2 验证结果

一期基础能力全部通过。

关键结果如下：

1. CLI 可正常启动，`python -m patchweaver --help` 可用。
2. `init --with-db` 成功创建 `data/`、`prompts/`、`skills/`、`workspaces/` 等最小运行目录。
3. `paths --json` 能正确解析项目根目录、配置目录、工作区目录、数据库路径和默认内核版本。
4. SQLite 初始化成功，数据库文件位于：
   `/root/patchweaver_validate_20260420/data/patchweaver.db`
5. 修正构建配置后，`doctor --json` 检查项为：
   `total=43, ok=43, warn=0, error=0`

### 3.3 第一期结论

第一期通过。

判断依据：

- 最小 CLI 可用
- 工程初始化可用
- 路径解析可用
- SQLite 可用
- `doctor` 环境诊断可用

### 3.4 第一期人工复核方法

人工复核时，可直接按下面命令执行：

```bash
python -m patchweaver version
python -m patchweaver init --with-db --json
python -m patchweaver paths --json
python -m patchweaver doctor --json
python -m patchweaver init-db --json
python -m patchweaver db path --json
```

人工检查重点如下：

1. `init --with-db --json` 中应看到 `database_initialized: true`。
2. `paths --json` 中的 `project_root` 应为 `/root/patchweaver_validate_20260420`。
3. `doctor --json` 中的 `summary` 应为 `ok=43, error=0`。
4. 数据库文件应存在于：
   `/root/patchweaver_validate_20260420/data/patchweaver.db`

## 4. 第二期验证结果

### 4.1 验证样例

本次在验证机上使用了两个固定样例：

- `TASK-VERIFY-20260420-1086` 对应 `CVE-2024-1086`
- `TASK-VERIFY-20260420-0185` 对应 `CVE-2022-0185`

### 4.2 验证命令

对每个样例执行了以下二期主链命令：

- `python -m patchweaver create --cve ... --task-id ... --json`
- `python -m patchweaver analyze --task ... --json`
- `python -m patchweaver run --task ... --json`
- `python -m patchweaver report --task ... --json`
- `python -m patchweaver replay --task ... --json`

本次实际使用的任务编号如下：

- `TASK-VERIFY-20260420-1086`
- `TASK-VERIFY-20260420-0185`

### 4.3 验证结果

#### 4.3.1 `WP-II-01` 真实 `CVE` 检索与 Patch 来源链

通过。

两个样例的 `create -> analyze` 都已在验证机上真实跑通，生成了：

- `patch_bundle.json`
- `source_evidence.json`
- `semantic_card.json`
- `constraint_report.json`
- `analysis_trace.json`

说明：

- 这一项最初因为 `NVD 503` 和 GitHub patch 拉取超时失败。
- 修复检索健壮性后，验证机上的真实来源链已可跑通。

#### 4.3.2 `WP-II-02` 真实改写链路与可 apply 补丁输出

通过。

两个样例都成功生成了：

- `rewritten.patch`
- `rewrite_reason.json`
- `transformation_trace.json`
- `apply_precheck.json`
- `rewrite_plan.json`

#### 4.3.3 `WP-II-03` 构建阶段高价值反馈

部分通过。

当前两个样例都进入了远端 apply 预检查，但最终失败类型都被归类为：

- `patch_apply_failed`

失败摘要如下：

- `CVE-2024-1086`
  `error: net/netfilter/nf_tables_api.c: No such file or directory`
- `CVE-2022-0185`
  `error: fs/fs_context.c: No such file or directory`

已生成的构建期产物包括：

- `build.log`
- `build_precheck.json`
- `build_summary.json`
- `failure_record.json`

#### 4.3.4 `WP-II-04` 真实验证链路落地

通过。

虽然本轮未产出 `.ko`，但验证链并没有断掉，而是生成了结构化验证结果：

- `validation_report.json`
- `semantic_precheck.json`
- `load.log`
- `unload.log`
- `smoke.log`

验证报告中的状态为结构化 `pending / failed / skipped`，不是空对象。

#### 4.3.5 `WP-II-05` 规则库、`Recipe` 与经验库

通过。

两个样例在运行后均生成了经验相关产物：

- `failure_memory_snapshot.json`
- `recipe_memory_snapshot.json`

说明当前规则命中、原语选择和经验写回已经进入真实链路。

#### 4.3.6 `WP-II-06` Prompt / Context / Skill 工程收口

通过。

在两个样例的尝试目录中，均可看到：

- `ContextBundle`
- `PromptPacket`
- `SkillRoute`
- `Harness Trace`

回放结果也能直接展示：

- `stage_routes`
- `dispatch_modes`

#### 4.3.7 `WP-II-07` 回放、评测与测试样例

通过。

两个样例都已具备：

- 固定任务编号
- 报告产物
- 回放入口
- 阶段轨迹

对应 `replay` 输出已经能回看到：

- 最近尝试状态
- `harness_trace.json`
- `validation_report.json`
- `rewrite_plan.json`

### 4.4 第二期结论

第二期整体判断为“主链通过，构建结果受环境完整性限制”。

通过项：

- 真实任务创建
- 真实来源链检索
- 真实改写链路
- 结构化失败归因
- 结构化验证留痕
- 报告与回放

未通过项：

- 本次样例未生成 `.ko`
- 本次样例未完成真实加载 / 卸载成功验收

### 4.5 第二期关键阻塞

当前构建失败的主要根因不是 CLI 或数据库问题，而是验证机当前只有 `kernel-devel` 目录，没有完整源码树。

已确认：

- `/usr/src/kernels/6.6.102-5.2.an23.x86_64/fs/fs_context.c` 不存在
- `/usr/src/kernels/6.6.102-5.2.an23.x86_64/net/netfilter/nf_tables_api.c` 不存在

这意味着：

1. 当前验证机可以完成配置、预检查、失败归因、验证落盘和报告输出。
2. 但对真实 `.c` 文件修改类补丁，apply 预检查会因为源码树不完整而提前失败。

### 4.6 第二期人工复核方法

人工复核建议分别对两个样例执行下面命令。

样例一：

```bash
python -m patchweaver create --cve CVE-2024-1086 --task-id TASK-VERIFY-20260420-1086 --json
python -m patchweaver analyze --task TASK-VERIFY-20260420-1086 --json
python -m patchweaver run --task TASK-VERIFY-20260420-1086 --json
python -m patchweaver report --task TASK-VERIFY-20260420-1086 --json
python -m patchweaver replay --task TASK-VERIFY-20260420-1086 --json
```

样例二：

```bash
python -m patchweaver create --cve CVE-2022-0185 --task-id TASK-VERIFY-20260420-0185 --json
python -m patchweaver analyze --task TASK-VERIFY-20260420-0185 --json
python -m patchweaver run --task TASK-VERIFY-20260420-0185 --json
python -m patchweaver report --task TASK-VERIFY-20260420-0185 --json
python -m patchweaver replay --task TASK-VERIFY-20260420-0185 --json
```

人工检查重点如下：

1. `analyze` 后确认以下文件存在：
   - `workspaces/<task_id>/input/patch_bundle.json`
   - `workspaces/<task_id>/input/source_evidence.json`
   - `workspaces/<task_id>/analysis/semantic_card.json`
   - `workspaces/<task_id>/analysis/constraint_report.json`
2. `run` 后确认以下文件存在：
   - `attempts/001/rewrite/rewritten.patch`
   - `attempts/001/rewrite/rewrite_reason.json`
   - `attempts/001/rewrite/transformation_trace.json`
   - `attempts/001/rewrite/apply_precheck.json`
   - `attempts/001/logs/build.log`
   - `attempts/001/logs/failure_record.json`
   - `attempts/001/artifacts/validation_report.json`
3. `replay --json` 输出中应能看到：
   - `latest_attempt_id`
   - `trace_path`
   - `report_path`
   - `comparison`
4. 若要核对本次失败根因，可直接查看：

```bash
cat /root/patchweaver_validate_20260420/workspaces/TASK-VERIFY-20260420-1086/attempts/001/logs/build.log
cat /root/patchweaver_validate_20260420/workspaces/TASK-VERIFY-20260420-0185/attempts/001/logs/build.log
```

用于确认源码树缺失的检查命令如下：

```bash
test -f /usr/src/kernels/6.6.102-5.2.an23.x86_64/fs/fs_context.c && echo exists || echo missing
test -f /usr/src/kernels/6.6.102-5.2.an23.x86_64/net/netfilter/nf_tables_api.c && echo exists || echo missing
```

## 5. 第三期验证结果

### 5.1 `WP-III-01` 高频失败规则扩充与 `Recipe` 命中优化

通过。

在两个样例上已经形成稳定的“规则 -> 改写计划 -> 改写结果 -> 失败归因”链路，且：

- `rewrite_plan.json`
- `planning_hints.json`
- `rewrite_reason.json`

均已生成。

### 5.2 `WP-III-02` 双记忆与经验闭环

通过。

两个样例的尝试目录中都存在：

- `failure_memory_snapshot.json`
- `recipe_memory_snapshot.json`

说明双记忆已经不只是落盘骨架，而是进入了真实尝试链路。

### 5.3 `WP-III-03` 验证增强与语义守卫

通过。

两个样例均已生成：

- `semantic_guard.json`
- `validation_matrix.json`
- `selftest.log`
- `regression_summary.json`

说明第三期新增的验证增强产物已经在验证机上实际生成。

### 5.4 `WP-III-04` 批量评测、回放与统计

通过。

在验证机上执行：

- `python -m patchweaver evaluate --fixture contest_samples --json`

结果如下：

- `fixture_count = 2`
- `matched_fixtures = 2`
- `missing_fixtures = 0`
- `success_count = 0`
- `success_rate = 0.0`
- `average_attempts = 1.0`
- `failure_distribution = {"patch_apply_failed": 2}`

已生成阶段统计文件：

- `/root/patchweaver_validate_20260420/data/evaluations/contest_samples/summary.json`
- `/root/patchweaver_validate_20260420/data/evaluations/contest_samples/summary.md`

### 5.5 `WP-III-05` Web 控制台首版

通过。

在验证机上启动：

- `python -m patchweaver serve-api --host 127.0.0.1 --port 18084`

实际验证了下面几个接口：

1. `GET /healthz`
   返回 `{"status":"ok","version":"0.1.0"}`
2. `GET /api/v1/overview`
   返回任务总览、失败分布、验证状态和日志摘要
3. `GET /api/v1/tasks`
   返回真实任务列表
4. `HEAD /console/`
   返回 `200 OK`

说明：

- API 正常
- `/console` 挂载正常
- Web 控制面已经接到真实后端数据

### 5.6 `WP-III-06` 成功率优化与样例面扩大

部分通过。

当前三期统计链已经在验证机上工作正常，但这次两条样例都停在 `patch_apply_failed`，因此：

- 成功率统计可用
- 失败分布统计可用
- 但当前样例成功率未提升

这一项当前更像“统计与对比链已经具备”，而不是“验证机上的当前样例已经把成功率做起来”。

### 5.7 `WP-III-07` 阶段展示与答辩素材预制

通过。

虽然这次验证没有生成成功 `.ko` 样例，但三期展示所需的主要证据链已经齐全：

- 固定任务编号
- 构建日志
- 失败归因
- 验证矩阵
- 回放入口
- 阶段统计文件
- Web 总览接口

### 5.8 第三期人工复核方法

第三期人工复核建议执行下面三组命令。

第一组，批量评测：

```bash
python -m patchweaver evaluate --fixture contest_samples --json
```

人工检查重点：

1. `matched_fixtures` 应为 `2`
2. `missing_fixtures` 应为 `0`
3. `summary_json` 和 `summary_md` 路径应存在

第二组，检查三期增强产物：

```bash
find /root/patchweaver_validate_20260420/workspaces/TASK-VERIFY-20260420-1086/attempts/001 -maxdepth 3 -type f | sort
find /root/patchweaver_validate_20260420/workspaces/TASK-VERIFY-20260420-0185/attempts/001 -maxdepth 3 -type f | sort
```

人工重点核对下面这些文件：

- `artifacts/failure_memory_snapshot.json`
- `artifacts/recipe_memory_snapshot.json`
- `artifacts/semantic_guard.json`
- `artifacts/validation_matrix.json`
- `artifacts/regression_summary.json`
- `rewrite/planning_hints.json`

第三组，Web/API 复核：

```bash
nohup python -m patchweaver serve-api --host 127.0.0.1 --port 18084 >/tmp/patchweaver_api_18084.log 2>&1 &
curl -s http://127.0.0.1:18084/healthz
curl -s http://127.0.0.1:18084/api/v1/overview
curl -s http://127.0.0.1:18084/api/v1/tasks
curl -I -s http://127.0.0.1:18084/console/ | head -n 5
```

人工检查重点：

1. `/healthz` 返回 `status=ok`
2. `/api/v1/overview` 中应能看到两个真实任务
3. `/api/v1/tasks` 中应能看到两个任务的 `latest_failure_type=patch_apply_failed`
4. `/console/` 返回 `HTTP/1.1 200 OK`

## 6. 总结结论

### 6.1 第一期

结论：通过

### 6.2 第二期

结论：部分通过

原因：

- 主链已经打通到真实 `create -> analyze -> run -> report -> replay`
- 失败归因、验证结果、报告与回放都已生成
- 但本次验证机缺少完整内核源码树，导致真实 `.c` 文件补丁在 apply 预检查阶段被拦截，未生成 `.ko`

### 6.3 第三期

结论：通过

说明：

- 双记忆、语义守卫、验证矩阵、批量评测、回放统计、Web/API 首版都已经在验证机上落地
- 当前主要短板不在三期壳层能力，而在二期构建输入和环境完整性

## 7. 后续建议

结合本次验证，下一步建议优先处理下面 4 项：

1. 在验证机上补齐完整内核源码树，而不是只依赖 `kernel-devel`。
2. 将 `build.yaml` 按“控制端运行”和“验证机直跑”拆成两个明确口径，避免同一配置兼顾两种场景。
3. 保留本次补上的检索健壮性修复，避免 `NVD 503` 和 GitHub patch 超时再次卡住分析阶段。
4. 在完整源码树到位后，重新对这两个固定样例执行二期和三期回归，补一版“成功 `.ko` + 加载 / 卸载成功”的复测记录。

## 8. 复核备注

为避免人工复核时和本次验证结果产生偏差，需要注意下面 4 点：

1. 本报告默认使用的是 `/root/patchweaver_validate_20260420` 这份验证副本，而不是验证机上历史目录 `/root/patchweaver`。
2. 复核前必须先激活 `.venv`，否则 `python -m patchweaver`、`fastapi`、`typer` 等依赖可能找不到。
3. 复核前必须设置 `PATCHWEAVER_REMOTE_PASSWORD`，否则 `doctor` 和 `run` 中的 `ssh` 构建后端会直接报缺少密码环境变量。
4. 若验证机后续补齐了完整内核源码树，则二期和三期的构建结果可能和本报告不同；这时应保留本报告作为“当前环境基线”，再单独补一版复测报告。
