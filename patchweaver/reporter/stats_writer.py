"""评测统计写入器"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from patchweaver.utils.path_policy import relativize_payload


class StatsWriter:
    """负责把阶段评测结果写成 JSON 和 Markdown"""

    def __init__(self, project_root: Path | None = None) -> None:
        """保存项目根目录，供路径序列化使用"""

        self.project_root = project_root.resolve() if project_root is not None else None

    def write_json(self, payload: dict[str, Any], target_path: Path) -> Path:
        """写出结构化统计结果"""

        target_path.parent.mkdir(parents=True, exist_ok=True)
        normalized = relativize_payload(payload, self.project_root)
        target_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return target_path

    def write_markdown(self, payload: dict[str, Any], target_path: Path) -> Path:
        """写出便于阶段汇报使用的人读摘要"""

        success_rate = payload.get("success_rate", 0)
        bucket_summary = payload.get("bucket_summary") or {}
        bucket_order = payload.get("bucket_order") or list(bucket_summary.keys())
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
            f"- 兼容总成功率: {success_rate:.2%}" if isinstance(success_rate, float) else f"- 兼容总成功率: {success_rate}",
            f"- 平均尝试轮次: {payload.get('average_attempts', 0)}",
            f"- 说明: {payload.get('mixed_summary_note')}" if payload.get("mixed_summary_note") else "- 说明: 当前没有兼容口径说明",
            "",
            "## 分桶评测",
        ]

        if bucket_order:
            for bucket_name in bucket_order:
                item = bucket_summary.get(bucket_name) or {}
                primary_metric = item.get("primary_metric") or {}
                secondary_metric = item.get("secondary_metric") or {}
                lines.extend(
                    [
                        "",
                        f"### {item.get('label') or bucket_name}",
                        f"- bucket: {bucket_name}",
                        f"- 关注目标: {item.get('goal') or '未定义'}",
                        f"- 样例总数: {item.get('total_fixtures', 0)}",
                        f"- 命中样例: {item.get('matched_fixtures', 0)}",
                        f"- 缺失样例: {item.get('missing_fixtures', 0)}",
                    ]
                )
                if primary_metric:
                    lines.append(
                        f"- 主指标: {primary_metric.get('label', primary_metric.get('name', 'unknown'))} "
                        f"{primary_metric.get('display_value') or primary_metric.get('value')}"
                        f" ({primary_metric.get('numerator', 0)}/{primary_metric.get('denominator', 0)})"
                    )
                if secondary_metric:
                    lines.append(
                        f"- 次指标: {secondary_metric.get('label', secondary_metric.get('name', 'unknown'))} "
                        f"{secondary_metric.get('display_value') or secondary_metric.get('value')}"
                        f" ({secondary_metric.get('numerator', 0)}/{secondary_metric.get('denominator', 0)})"
                    )
                lines.append(f"- 状态分布: {item.get('status_distribution') or {}}")
                lines.append(f"- 失败分布: {item.get('failure_distribution') or {}}")
        else:
            lines.append("- 当前没有分桶评测结果")

        lines.extend(["", "## 状态分布"])

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
                    f"- {item.get('fixture_id')}: bucket={item.get('sample_bucket') or 'unknown'} / {item.get('final_status')} / 尝试轮 {item.get('attempts')} / 失败类型 {item.get('latest_failure_type') or '无'}"
                )

        target_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return target_path
