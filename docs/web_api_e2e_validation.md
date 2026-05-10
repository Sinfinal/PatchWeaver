# PatchWeaver Web/API 端到端验收方案

本文面向评委验收口径，说明如何通过 Web/API 与 CLI 形成 `CVE -> task -> analyze/run -> report/replay -> artifact evidence` 的端到端闭环。验收重点不是只看 overview 汇总页，而是逐层核验任务创建、任务执行、报告、回放、Agent 决策、`.ko` 产物和 `validation_report.json`。

## 验收边界

- 验收目标：证明 Web/API 可以创建任务、查询任务、触发或承接执行、查询报告和回放证据，并能定位 livepatch `.ko` 与验证报告。
- 不在本文承诺：不宣称覆盖官方 Final 隐藏集；不写固定机器 IP、密码、API Key 或平台 Token；不把缺失证据解释为成功。
- 当前主路径：当前后端已提供 `POST /api/v1/tasks/{task_id}/analyze`、`POST /api/v1/tasks/{task_id}/run`、`POST /api/v1/tasks/{task_id}/report`，因此可通过 HTTP 完成创建、执行、报告生成和查询。
- 兼容路径：如部署环境把执行入口限制为查询型 API，可用 CLI 在同一工作区执行 `analyze/run/report/replay`，再用 API 查询同一 `task_id` 的证据。

## 当前 API 能力清单

| 能力 | HTTP 接口 | 验收用途 |
| --- | --- | --- |
| 健康检查 | `GET /healthz` | 确认 API 服务可达 |
| 创建任务 | `POST /api/v1/tasks` | 创建 CVE 任务并初始化工作区 |
| 查询任务列表 | `GET /api/v1/tasks` | 按状态、CVE、内核、失败类型等过滤 |
| 查询任务详情 | `GET /api/v1/tasks/{task_id}` | 查看 task、attempts、latest_validation、reports、replay、agent_decision_summary、artifact_index |
| Agent 决策摘要 | `GET /api/v1/tasks/{task_id}/agent-decision` | 核验修复意图、策略选择、失败归因和下一步建议 |
| 分析阶段 | `POST /api/v1/tasks/{task_id}/analyze` | 触发语义卡、约束报告、修复意图等前置分析 |
| 单轮执行 | `POST /api/v1/tasks/{task_id}/run` | 触发改写、构建、验证链路 |
| 生成报告 | `POST /api/v1/tasks/{task_id}/report` | 生成 `report.json` 与 `report.md` |
| 回放信息 | `GET /api/v1/tasks/{task_id}/replay` | 查询最近一轮 trace、stage routes、comparison 和 replay files |
| 任务报告聚合 | `GET /api/v1/reports/tasks/{task_id}` | 一次读取 report、latest_validation、replay、Agent 决策和 artifact_index |
| 产物树 | `GET /api/v1/tasks/{task_id}/artifacts` | 遍历工作区，核验 `.ko`、日志、报告、trace 是否存在 |
| 文本产物内容 | `GET /api/v1/tasks/{task_id}/artifacts/content?path=...` | 读取 JSON、Markdown、log、patch 等文本证据 |

## 前置条件

1. 在验收机上完成 PatchWeaver 运行环境安装，并保证目标内核源码、`kpatch-build`、验证配置和模型调用配置符合当前项目要求。
2. 通过环境变量或平台 Secret 注入模型密钥，不在命令行、文档或仓库文件中写明文 Key。
3. 启动 API 服务。示例只使用占位符，不写真实地址：

```powershell
$env:PATCHWEAVER_BAILIAN_API_KEY = "<injected-by-env-or-secret>"
python -m patchweaver serve-api --host <API_HOST> --port <API_PORT>
```

4. 另开一个终端准备执行验收脚本：

```powershell
$BaseUrl = "http://<API_HOST>:<API_PORT>"
$Api = "$BaseUrl/api/v1"
$CveId = "CVE-YYYY-NNNNN"
$TargetKernel = "<target-kernel-version>"
$Profile = "<profile-name>"
```

## HTTP 端到端验收脚本草案

### 1. 健康检查

```powershell
Invoke-RestMethod -Method Get -Uri "$BaseUrl/healthz"
```

通过标准：

- 返回 `status=ok`。
- 返回版本字段，说明访问的是 PatchWeaver API 服务。

### 2. 通过 HTTP 创建任务

```powershell
$CreateBody = @{
  cve_id = $CveId
  target_kernel = $TargetKernel
  profile = $Profile
  max_attempts = 1
  note = "web-api-e2e-validation"
  force_new = $true
} | ConvertTo-Json

$Created = Invoke-RestMethod `
  -Method Post `
  -Uri "$Api/tasks" `
  -ContentType "application/json" `
  -Body $CreateBody

$TaskId = $Created.task.task_id
$TaskId
```

通过标准：

- 返回 `status=ok` 且 `created=true`。
- `task.task_id`、`task.cve_id`、`task.workspace_dir` 非空。
- `request_path` 指向 `input/task_request.json`，可作为 Web 创建请求留痕。

如返回 `status=duplicate`，验收时不要混淆新旧证据；建议保留响应中的 `existing_task.task_id` 作为复核对象，或使用 `force_new=true` 创建独立任务。

### 3. 查询任务列表和详情

```powershell
Invoke-RestMethod -Method Get -Uri "$Api/tasks?cve_id=$CveId&limit=20"

$DetailBeforeRun = Invoke-RestMethod -Method Get -Uri "$Api/tasks/$TaskId"
$DetailBeforeRun.task
$DetailBeforeRun.process_summary
$DetailBeforeRun.report_closure
```

通过标准：

- 列表中可按 `cve_id` 找到该任务。
- 详情中的 `task.status` 应为 `created` 或后续阶段状态。
- 初始状态不应被误判为成功；`process_summary` 应说明还未形成构建或验证结论。

### 4. 通过 HTTP 触发 analyze/run/report

```powershell
$Analyze = Invoke-RestMethod -Method Post -Uri "$Api/tasks/$TaskId/analyze"
$Analyze.detail

$Run = Invoke-RestMethod -Method Post -Uri "$Api/tasks/$TaskId/run"
$Run.detail

$Report = Invoke-RestMethod -Method Post -Uri "$Api/tasks/$TaskId/report"
$Report.detail
```

通过标准：

- `analyze` 返回分析产物路径，例如 semantic card、constraint report、repair intent 或 bootstrap manifest。
- `run` 返回 `task_id`、`attempt_id`、`status`、`failure_type`、`build_log_path`，如构建成功还应能在后续详情或产物树中定位 `.ko`。
- `report` 返回 `report_json` 和 `report_md` 路径。
- 如果 `run` 失败，验收不应只看 HTTP 状态码；应继续查询 `failure_record.json`、`build.log`、`replay` 和 Agent 决策，确认失败归因是否可解释、可回放。

### 5. 如果当前部署只允许查询 API，使用 CLI 配合

某些交付环境可能只暴露查询接口，或禁止长耗时 HTTP 请求直接执行构建。此时可用 CLI 在同一项目和同一数据库/工作区执行，再用 API 查询证据：

```powershell
python -m patchweaver create --cve $CveId --kernel $TargetKernel --profile $Profile --max-attempts 1 --force-new --json
python -m patchweaver analyze --task $TaskId --json
python -m patchweaver run --task $TaskId --json
python -m patchweaver report --task $TaskId --json
python -m patchweaver replay --task $TaskId --json
```

配合方式：

- CLI 输出的 `task_id` 必须与后续 API 查询的 `task_id` 一致。
- CLI 写入的工作区、SQLite 任务库和 API 服务读取的项目根目录必须一致。
- API 仍负责验收查询：`GET /tasks/{task_id}`、`GET /reports/tasks/{task_id}`、`GET /tasks/{task_id}/replay`、`GET /tasks/{task_id}/artifacts`。

## 报告、回放和 Agent 决策核验

### 1. 查询任务报告聚合

```powershell
$TaskReport = Invoke-RestMethod -Method Get -Uri "$Api/reports/tasks/$TaskId"
$TaskReport.result_source
$TaskReport.report.json
$TaskReport.latest_validation
$TaskReport.replay
$TaskReport.agent_decision_summary
```

通过标准：

- `result_source.report_json_exists=true` 且 `result_source.report_md_exists=true`。
- `report.json` 和 `report.md` 可读，且内容不只包含 overview 指标，应能关联 attempt、构建、验证、失败归因或成功证据。
- `latest_validation` 不为空时，应包含 `status`、`load_result`、`unload_result`、`smoke_result`、`selftest_result`、`semantic_guard_result` 或 `validation_matrix`。
- `replay` 应指向最近一轮 attempt、trace、report 和 stage routes。
- `agent_decision_summary` 应说明修复意图、策略选择、失败类型、构建执行状态和推荐下一步。

### 2. 单独查询 replay

```powershell
$Replay = Invoke-RestMethod -Method Get -Uri "$Api/tasks/$TaskId/replay"
$Replay
```

通过标准：

- `latest_attempt_id` 与任务最新 attempt 一致。
- `trace_path`、`report_path`、`evaluation_summary_path`、`stage_routes`、`dispatch_modes`、`replay_files` 至少能解释最近一轮从分析到验证或失败归因的路径。
- 如果没有 attempt，应返回 empty/pending 语义，不能伪造成功。

### 3. 单独查询 Agent 决策

```powershell
$Decision = Invoke-RestMethod -Method Get -Uri "$Api/tasks/$TaskId/agent-decision"
$Decision
```

通过标准：

- 能看到 repair intent、selected strategy/recipe、latest failure type、build exec status、target state 或 next action 等字段。
- 对失败任务，应给出失败归因和下一步建议，而不是只返回状态码。
- 对目标已修复场景，应明确 `target_already_patched` 或等价状态，不能当作 `.ko` 构建成功。

## `.ko` 与 validation_report 核验

### 1. 查询详情中的 attempt 证据

```powershell
$DetailAfterRun = Invoke-RestMethod -Method Get -Uri "$Api/tasks/$TaskId"
$LatestAttempt = $DetailAfterRun.attempts | Select-Object -Last 1
$LatestAttempt
$DetailAfterRun.latest_validation
$DetailAfterRun.report_closure
```

`.ko` 通过标准：

- 成功侧任务的最新 attempt 应包含 `module_path`，且路径后缀为 `.ko`。
- `status` 应为 `built` 或与构建成功等价的项目状态。
- `build_log_path` 应存在，且能通过产物树定位。
- 如果 `module_path` 为空，不能宣称已完成 livepatch 构建；应按失败或待补证据处理。

`validation_report.json` 通过标准：

- `report_closure.validation_report_path` 或最新 attempt 的 `validation_report_path` 指向 `attempts/<NNN>/artifacts/validation_report.json`。
- `latest_validation.status` 为 `passed` 时，至少应满足 load 与 selftest 成功；unload、smoke、regression、semantic guard 可按配置为 passed 或 skipped，但必须有明确状态和原因。
- `latest_validation.validation_matrix` 应记录各验证项名称、类别、启用状态、风险等级和日志路径。
- 如果验证状态为 `pending`、`partial` 或 `failed`，验收报告必须保留该状态，不得把 report 生成成功等同于验证成功。

### 2. 查询产物树，不只测 overview

```powershell
$Artifacts = Invoke-RestMethod -Method Get -Uri "$Api/tasks/$TaskId/artifacts"
$Artifacts.key_artifacts
$Artifacts.items | Where-Object {
  $_.relative_path -match '\.ko$|validation_report\.json$|build\.log$|harness_trace\.json$|report\.json$|report\.md$|failure_record\.json$'
}
```

通过标准：

- 至少核验这些证据路径：`reports/report.json`、`reports/report.md`、`attempts/<NNN>/trace/harness_trace.json`、`attempts/<NNN>/artifacts/validation_report.json`、`attempts/<NNN>/logs/build.log`。
- 成功构建任务还必须能在 `items` 中找到 `.ko`，并检查 `size > 0`。
- 不能只访问 `/api/v1/overview` 或 Web overview 页面后就宣称端到端通过；overview 只能作为总览，不能替代任务级证据。

### 3. 读取文本证据内容

```powershell
$ValidationPath = $LatestAttempt.validation_report_path
$ValidationRelativePath = $ValidationPath -replace '^workspaces/[^/]+/', ''

Invoke-RestMethod `
  -Method Get `
  -Uri "$Api/tasks/$TaskId/artifacts/content?path=$([uri]::EscapeDataString($ValidationRelativePath))"
```

说明：

- `artifacts/content` 适合读取 JSON、Markdown、log、patch、diff 等文本证据。
- 当前接口不适合下载或展示二进制 `.ko` 内容；`.ko` 应通过 `module_path`、产物树 `suffix=.ko`、`size > 0` 和验证日志共同核验。
- 如果需要二进制下载能力，应新增专门的安全下载接口，而不是复用文本预览接口。

## 建议的一键验收脚本草案

以下脚本保留占位符，交付时由验收人员填入环境变量。它不会输出密钥，也不会写入仓库代码。

```powershell
param(
  [Parameter(Mandatory=$true)][string]$BaseUrl,
  [Parameter(Mandatory=$true)][string]$CveId,
  [Parameter(Mandatory=$true)][string]$TargetKernel,
  [string]$Profile = "default",
  [int]$MaxAttempts = 1
)

$ErrorActionPreference = "Stop"
$Api = "$BaseUrl/api/v1"

function Assert-True($Condition, $Message) {
  if (-not $Condition) {
    throw "验收失败: $Message"
  }
}

$Health = Invoke-RestMethod -Method Get -Uri "$BaseUrl/healthz"
Assert-True ($Health.status -eq "ok") "healthz 未返回 ok"

$CreateBody = @{
  cve_id = $CveId
  target_kernel = $TargetKernel
  profile = $Profile
  max_attempts = $MaxAttempts
  note = "web-api-e2e-validation"
  force_new = $true
} | ConvertTo-Json

$Created = Invoke-RestMethod -Method Post -Uri "$Api/tasks" -ContentType "application/json" -Body $CreateBody
Assert-True ($Created.created -eq $true) "任务未创建；如命中 duplicate，请改用响应中的 existing_task 或 force_new"
$TaskId = $Created.task.task_id
Assert-True ($TaskId) "响应缺少 task_id"

$null = Invoke-RestMethod -Method Get -Uri "$Api/tasks/$TaskId"
$null = Invoke-RestMethod -Method Post -Uri "$Api/tasks/$TaskId/analyze"
$Run = Invoke-RestMethod -Method Post -Uri "$Api/tasks/$TaskId/run"
$null = Invoke-RestMethod -Method Post -Uri "$Api/tasks/$TaskId/report"

$Detail = Invoke-RestMethod -Method Get -Uri "$Api/tasks/$TaskId"
$TaskReport = Invoke-RestMethod -Method Get -Uri "$Api/reports/tasks/$TaskId"
$Replay = Invoke-RestMethod -Method Get -Uri "$Api/tasks/$TaskId/replay"
$Decision = Invoke-RestMethod -Method Get -Uri "$Api/tasks/$TaskId/agent-decision"
$Artifacts = Invoke-RestMethod -Method Get -Uri "$Api/tasks/$TaskId/artifacts"

$LatestAttempt = $Detail.attempts | Select-Object -Last 1
Assert-True ($LatestAttempt) "没有 attempt，不能验收 run 链路"
Assert-True ($TaskReport.result_source.report_json_exists -eq $true) "缺少 report.json"
Assert-True ($TaskReport.result_source.report_md_exists -eq $true) "缺少 report.md"
Assert-True ($Replay.task_id -eq $TaskId) "replay task_id 不一致"
Assert-True ($Decision.task_id -eq $TaskId) "agent-decision task_id 不一致"

$Evidence = $Artifacts.items | Where-Object {
  $_.relative_path -match 'validation_report\.json$|build\.log$|harness_trace\.json$|report\.json$|report\.md$|failure_record\.json$|\.ko$'
}
Assert-True (($Evidence | Measure-Object).Count -gt 0) "产物树没有关键证据"

$KoItems = $Artifacts.items | Where-Object { $_.relative_path -match '\.ko$' -and $_.size -gt 0 }
$ValidationReady = $null -ne $Detail.latest_validation

[pscustomobject]@{
  task_id = $TaskId
  run_status = $Run.detail.status
  latest_attempt_status = $LatestAttempt.status
  module_path = $LatestAttempt.module_path
  ko_found = (($KoItems | Measure-Object).Count -gt 0)
  validation_status = $Detail.latest_validation.status
  validation_ready = $ValidationReady
  report_json_exists = $TaskReport.result_source.report_json_exists
  replay_status = $Replay.status
  decision_failure_type = $Decision.latest_failure_type
  evidence_count = ($Evidence | Measure-Object).Count
}
```

判定口径：

- `report_json_exists=true`、`validation_ready=true`、`replay` 和 `agent-decision` 均可查询，说明 Web/API 证据链可用。
- `ko_found=true` 且 `validation_status=passed`，才可判定该任务达到 `.ko + validation_report` 成功闭环。
- 如果 `ko_found=false` 或 `validation_status` 非 passed，应输出失败归因和缺口，不能把任务创建、overview 展示或报告生成当作构建验证成功。

## API 缺口与改进建议

1. `.ko` 二进制下载缺口：当前 `artifacts/content` 以文本方式读取文件，不适合下载或校验二进制 `.ko`。现阶段可通过 `module_path`、产物树后缀和大小、build log、validation report 交叉核验；后续建议新增只读安全下载接口。
2. 运行接口同步执行风险：`POST /tasks/{task_id}/run` 会直接触发单轮执行，长耗时构建可能受 HTTP 超时影响。正式交付建议补充异步 job、队列状态、取消和重试接口。
3. 关键产物索引仍偏文本证据：`key_artifacts` 已覆盖 report、build log、validation report、trace，但未把 `.ko` 作为显式 key artifact；验收脚本需要遍历 `items` 才能找到 `.ko`。
4. 报告成功不等于验证成功：当前 API 能查询 `report.json` 和 `validation_report.json`，但评委口径必须区分 report 生成、构建成功和动态验证通过，避免只测 overview 或只测 report。
5. 认证与审计需按部署补齐：当前文档不写密钥和内网地址；如果对外暴露 API，应由部署层补充鉴权、审计和访问控制。
