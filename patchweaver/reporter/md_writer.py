"""Markdown 报告写入器。"""

from __future__ import annotations

from pathlib import Path

from patchweaver.models.report import FinalReport


class MdWriter:
    """负责输出简洁的人读报告。"""

    def write_report(self, report: FinalReport, target_path: Path) -> Path:
        """把最终报告写成 Markdown。"""

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
                lines.append(f"- 第 {item.attempt_no} 轮: {item.status} ({item.failure_type or '无'})")
        if report.evaluation_summary:
            lines.extend(["", "## 评测摘要"])
            for key, value in report.evaluation_summary.items():
                lines.append(f"- {key}: {value}")
        if report.explanations:
            lines.extend(["", "## 说明"])
            for item in report.explanations:
                lines.append(f"- {item}")
        target_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return target_path
