"""评测统计写入器。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class StatsWriter:
    """负责把阶段评测结果写成 JSON 和 Markdown。"""

    def write_json(self, payload: dict[str, Any], target_path: Path) -> Path:
        """写出结构化统计结果。"""

        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return target_path

    def write_markdown(self, payload: dict[str, Any], target_path: Path) -> Path:
        """写出便于阶段汇报使用的人读摘要。"""

        target_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# PatchWeaver 阶段评测摘要",
            "",
            f"- 生成时间: {datetime.now(timezone.utc).isoformat()}",
            f"- 固定样例集: {payload.get('fixture_name', 'unknown')}",
            f"- 样例总数: {payload.get('total_fixtures', 0)}",
            f"- 命中样例: {payload.get('matched_fixtures', 0)}",
            f"- 缺失样例: {payload.get('missing_fixtures', 0)}",
            f"- 成功数: {payload.get('success_count', 0)}",
            f"- 失败数: {payload.get('failed_count', 0)}",
            f"- 成功率: {payload.get('success_rate', 0):.2%}" if isinstance(payload.get("success_rate"), float) else f"- 成功率: {payload.get('success_rate', 0)}",
            f"- 平均尝试轮次: {payload.get('average_attempts', 0)}",
            "",
            "## 状态分布",
        ]

        status_distribution = payload.get("status_distribution") or {}
        if status_distribution:
            for name, count in status_distribution.items():
                lines.append(f"- {name}: {count}")
        else:
            lines.append("- 当前没有状态分布记录。")

        lines.extend(["", "## 分组分布"])
        group_distribution = payload.get("group_distribution") or {}
        if group_distribution:
            for name, count in group_distribution.items():
                lines.append(f"- {name}: {count}")
        else:
            lines.append("- 当前没有分组分布记录。")

        lines.extend(["", "## 失败分布"])

        failure_distribution = payload.get("failure_distribution") or {}
        if failure_distribution:
            for name, count in failure_distribution.items():
                lines.append(f"- {name}: {count}")
        else:
            lines.append("- 当前没有失败分布记录。")

        fixtures = payload.get("fixtures") or []
        if fixtures:
            lines.extend(["", "## 样例结果"])
            for item in fixtures:
                lines.append(
                    f"- {item.get('fixture_id')}: {item.get('final_status')} / 尝试轮 {item.get('attempts')} / 失败类型 {item.get('latest_failure_type') or '无'}"
                )

        target_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return target_path
