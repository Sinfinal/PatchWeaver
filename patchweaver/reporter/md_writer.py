"""Markdown 报告写入器"""

from __future__ import annotations

from pathlib import Path

from patchweaver.models.report import FinalReport


class MdWriter:
    """负责输出简洁的人读报告"""

    def write_report(self, report: FinalReport, target_path: Path) -> Path:
        """把最终报告写成 Markdown"""

        target_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# PatchWeaver 任务报告",
            "",
            f"- 最终状态: {report.final_status}",
            "",
            "## 任务摘要",
        ]
        for key, value in report.task_summary.items():
            lines.append(f"- {key}: {value}")
        if report.attempt_digest:
            lines.extend(["", "## 尝试摘要"])
            for item in report.attempt_digest:
                digest = f"- 第 {item.attempt_no} 轮: {item.status} ({item.failure_type or '无'})"
                if item.build_exec_status:
                    digest += f" / build_exec_status={item.build_exec_status}"
                if item.target_state:
                    digest += f" / target_state={item.target_state}"
                lines.append(digest)
        if report.analysis_summary:
            lines.extend(["", "## 分析结果"])
            for key, value in report.analysis_summary.items():
                lines.append(f"- {key}: {value}")
        if report.build_summary:
            lines.extend(["", "## 构建结果"])
            for key, value in report.build_summary.items():
                lines.append(f"- {key}: {value}")
        if report.validation_summary:
            lines.extend(["", "## 验证结果"])
            for key, value in report.validation_summary.items():
                lines.append(f"- {key}: {value}")
        if report.closure_summary:
            lines.extend(["", "## 闭环状态"])
            for key, value in report.closure_summary.items():
                lines.append(f"- {key}: {value}")
        if report.replay_summary:
            lines.extend(["", "## 回放索引"])
            for key, value in report.replay_summary.items():
                lines.append(f"- {key}: {value}")
        if report.agent_decision_summary:
            lines.extend(["", "## Agent Decision Summary"])
            repair_intent = report.agent_decision_summary.get("repair_intent")
            strategy_switch = report.agent_decision_summary.get("strategy_switch")
            failure_attribution = report.agent_decision_summary.get("failure_attribution")
            if isinstance(repair_intent, dict):
                lines.append(f"- RepairIntent strategy: {repair_intent.get('recommended_strategy') or 'unknown'}")
                lines.append(f"- RepairIntent root_cause: {repair_intent.get('root_cause') or 'unknown'}")
            if isinstance(strategy_switch, dict):
                lines.append(f"- selected_recipe: {strategy_switch.get('selected_recipe') or 'unknown'}")
                lines.append(f"- selected_strategy: {strategy_switch.get('selected_strategy') or 'unknown'}")
                lines.append(f"- strategy_switched: {strategy_switch.get('switched')}")
                lines.append(f"- strategy_reason: {strategy_switch.get('reason') or 'unknown'}")
            if isinstance(failure_attribution, dict):
                lines.append(f"- failure_type: {failure_attribution.get('failure_type') or 'none'}")
                lines.append(f"- failure_summary: {failure_attribution.get('summary') or 'none'}")
                lines.append(f"- agent_next_action: {failure_attribution.get('agent_next_action') or 'none'}")
        if report.key_paths:
            lines.extend(["", "## 关键路径"])
            for key, value in report.key_paths.items():
                lines.append(f"- {key}: {value}")
        if report.evaluation_summary:
            lines.extend(["", "## 评测摘要"])
            for key, value in report.evaluation_summary.items():
                lines.append(f"- {key}: {value}")
        if report.known_limits:
            lines.extend(["", "## 当前限制"])
            for item in report.known_limits:
                lines.append(f"- {item}")
        if report.explanations:
            lines.extend(["", "## 说明"])
            for item in report.explanations:
                lines.append(f"- {item}")
        if report.next_priority_layer or report.next_action:
            lines.extend(["", "## 下一步"])
            if report.next_priority_layer:
                lines.append(f"- next_priority_layer: {report.next_priority_layer}")
            if report.next_action:
                lines.append(f"- next_action: {report.next_action}")
        target_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return target_path
