# PatchWeaver Final Gate Report

- 生成时间: 2026-04-21T11:45:55.623805+00:00
- 总体状态: failed
- 通过: 13
- 带限制通过: 0
- 未通过: 1

## 门禁检查
- doctor_snapshot: passed / doctor 快照已生成。
- database_ready: passed / SQLite 数据库可用。
- evaluation_summary: passed / 已发现 1 组阶段评测摘要。
- task_report_closure: passed / 至少有一条任务已经打通报告、日志和 trace 闭环。
- system_log: passed / 系统日志文件已存在。
- jsonl_log: passed / JSONL 事件日志已存在。
- web_console: passed / Web 控制台源码目录存在。
- build_backend: failed / 构建环境预检通过。
- models_config: passed / 模型配置文件已就位。
- model_topology: passed / 模型拓扑已收敛为单主模型 + 可选辅助模型。
- bailian_api_key: passed / 已检测到百炼 API Key。
- submission_layout: passed / submission 目录结构已建立。
- final_manifest: passed / final_manifest 已生成。
- model_statement: passed / 模型选型说明已写入 submission/docs。

## 总目标检查
- 理解修复意图: 已实现 / 分析阶段已固化 semantic_card 输出和任务详情回显。
- 识别热补丁约束: 已实现 / 约束诊断结果会落到 constraint_report，并进入报告和详情页。
- 生成可解释的改写方案: 已实现 / rewrite_plan、planning_hints 和 route/prompt 产物已形成可回看链路。
- 自动执行构建与验证: 已实现 / BuildOrchestrator 和 Validator 已接入主链，实际效果依赖构建环境和样例运行结果。
- 对失败进行归因并驱动下一轮尝试: 部分实现 / 失败归因、failover 记录和回放链已经落地，多轮自动收敛能力仍以迭代增强为主。
- 输出结构化报告、日志和产物: 已实现 / report.json、report.md、evaluation summary、system log 和 artifact index 已形成统一出口。
