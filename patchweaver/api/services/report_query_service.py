"""报告与固定样例查询服务"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from patchweaver.api.deps import ApiContext
from patchweaver.api.services.task_query_service import TaskQueryService
from patchweaver.utils.path_policy import resolve_project_path, to_project_relative


class ReportQueryService:
    """负责报告中心、固定样例和阶段统计查询"""

    def __init__(self, context: ApiContext) -> None:
        """保存 API 共享上下文"""

        self.context = context
        self.task_query = TaskQueryService(context)

    def get_task_report(self, task_id: str) -> dict[str, Any]:
        """返回任务级报告页需要的聚合数据"""

        detail = self.task_query.get_task_detail(task_id)
        report_json_path = self._resolve(detail["reports"]["json_path"])
        report_md_path = self._resolve(detail["reports"]["md_path"])
        evaluation_summary_path = self._resolve(detail["reports"]["evaluation_summary_path"])

        return {
            "task": detail["task"],
            "report": {
                "json_path": detail["reports"]["json_path"],
                "md_path": detail["reports"]["md_path"],
                "json": self._read_json(report_json_path),
                "markdown": self._read_text(report_md_path),
            },
            "latest_failure": detail["latest_failure"],
            "latest_validation": detail["latest_validation"],
            "evaluation_summary": self._read_json(evaluation_summary_path),
            "replay": detail["replay"],
            "artifact_index": detail["artifact_index"],
            "result_source": {
                "report_json_exists": report_json_path.exists(),
                "report_md_exists": report_md_path.exists(),
                "evaluation_summary_exists": evaluation_summary_path.exists(),
            },
        }

    def list_evaluation_groups(self) -> dict[str, Any]:
        """返回固定样例分组清单"""

        items: list[dict[str, Any]] = []
        evaluations_root = self._evaluations_root()
        if not evaluations_root.exists():
            return {"items": items}

        preferred_order = {
            "challenge_dev": 0,
            "challenge-dev": 0,
            "holdout": 1,
            "regression": 2,
            "contest_samples": 3,
            "contest-samples": 3,
        }

        for summary_path in sorted(evaluations_root.glob("*/summary.json")):
            payload = self._read_json(summary_path)
            if not isinstance(payload, dict):
                continue

            fixture_name = str(payload.get("fixture_name") or summary_path.parent.name)
            fixture_group = self._fixture_group(summary_path.parent.name)
            items.append(
                {
                    "fixture_group": fixture_group,
                    "group_id": fixture_group,
                    "display_name": fixture_name,
                    "summary_json_path": self._path(summary_path),
                    "summary_md_path": self._path(summary_path.with_name("summary.md")),
                    "total_fixtures": int(payload.get("total_fixtures", 0) or 0),
                    "matched_fixtures": int(payload.get("matched_fixtures", 0) or 0),
                    "missing_fixtures": int(payload.get("missing_fixtures", 0) or 0),
                    "success_count": int(payload.get("success_count", 0) or 0),
                    "success_rate": float(payload.get("success_rate", 0.0) or 0.0),
                    "average_attempts": float(payload.get("average_attempts", 0.0) or 0.0),
                    "updated_at": self._format_mtime(summary_path),
                    "sort_order": preferred_order.get(fixture_group, 99),
                }
            )

        items.sort(key=lambda item: (int(item["sort_order"]), str(item["display_name"])))
        for item in items:
            item.pop("sort_order", None)
        return {"items": items}

    def get_group_summary(self, group_name: str) -> dict[str, Any]:
        """返回单个固定样例分组的摘要"""

        group_dir = self._resolve_group_dir(group_name)
        summary_path = group_dir / "summary.json"
        summary_md_path = group_dir / "summary.md"
        summary_payload = self._read_json(summary_path)
        if not isinstance(summary_payload, dict):
            raise ValueError(f"分组摘要不存在：{summary_path}")

        fixtures = summary_payload.get("fixtures")
        if not isinstance(fixtures, list):
            fixtures = []

        enriched_fixtures: list[dict[str, Any]] = []
        for item in fixtures:
            if not isinstance(item, dict):
                continue
            fixture_id = str(item.get("fixture_id") or "")
            task_id = item.get("task_id")
            item_fixture_group = str(
                item.get("fixture_group") or item.get("sample_group") or item.get("group") or self._fixture_group(group_dir.name)
            ).replace("-", "_")
            enriched_fixtures.append(
                {
                    **item,
                    "fixture_id": fixture_id,
                    "fixture_group": item_fixture_group,
                    "report_route": f"/reports/fixtures/{self._fixture_group(group_dir.name)}/{fixture_id}" if fixture_id else None,
                    "task_report_route": f"/reports/tasks/{task_id}" if task_id else None,
                    "task_detail_route": f"/tasks/{task_id}" if task_id else None,
                }
            )
        return {
            "fixture_group": self._fixture_group(group_dir.name),
            "group_id": self._fixture_group(group_dir.name),
            "display_name": str(summary_payload.get("fixture_name") or group_dir.name),
            "summary_json_path": self._path(summary_path),
            "summary_md_path": self._path(summary_md_path),
            "summary_markdown": self._read_text(summary_md_path),
            "summary": summary_payload,
            "fixtures": enriched_fixtures,
        }

    def get_fixture_detail(self, group_name: str, fixture_id: str) -> dict[str, Any]:
        """返回单个固定样例的详情"""

        group_dir = self._resolve_group_dir(group_name)
        detail_path = self._resolve_fixture_path(group_dir, fixture_id)
        detail_payload = self._read_json(detail_path)
        if not isinstance(detail_payload, dict):
            raise ValueError(f"样例详情不存在：{detail_path}")

        task_id = detail_payload.get("task_id")
        return {
            "fixture_group": self._fixture_group(group_dir.name),
            "group_id": self._fixture_group(group_dir.name),
            "display_name": self._group_display_name(group_dir),
            "fixture_id": detail_path.stem,
            "detail_path": self._path(detail_path),
            "detail": detail_payload,
            "task_report_route": f"/reports/tasks/{task_id}" if task_id else None,
            "task_detail_route": f"/tasks/{task_id}" if task_id else None,
        }

    def _evaluations_root(self) -> Path:
        """返回评测结果根目录"""

        return (self.context.runtime.data_dir / "evaluations").resolve()

    def _resolve_group_dir(self, group_name: str) -> Path:
        """把路由里的分组标识映射到真实目录"""

        evaluations_root = self._evaluations_root()
        if not evaluations_root.exists():
            raise ValueError("当前还没有评测结果目录。")

        normalized = self._normalize_token(group_name)
        for item in evaluations_root.iterdir():
            if not item.is_dir():
                continue
            if self._normalize_token(item.name) == normalized:
                return item.resolve()
        raise ValueError(f"未找到评测分组：{group_name}")

    def _resolve_fixture_path(self, group_dir: Path, fixture_id: str) -> Path:
        """按样例编号定位详情文件"""

        normalized = self._normalize_token(fixture_id)
        for item in group_dir.glob("*.json"):
            if item.name == "summary.json":
                continue
            if self._normalize_token(item.stem) == normalized:
                return item.resolve()
        raise ValueError(f"未找到样例详情：{fixture_id}")

    def _group_display_name(self, group_dir: Path) -> str:
        """优先从 summary.json 里读取分组展示名"""

        payload = self._read_json(group_dir / "summary.json")
        if isinstance(payload, dict) and payload.get("fixture_name"):
            return str(payload["fixture_name"])
        return group_dir.name

    def _fixture_group(self, value: str) -> str:
        """把目录名转换成统一的固定样例分组标识"""

        return value.strip().lower().replace("-", "_")

    def _normalize_token(self, value: str) -> str:
        """统一路由参数和目录名的比较口径"""

        return value.strip().lower().replace("-", "_")

    def _read_json(self, path: Path) -> dict[str, Any] | None:
        """安全读取 JSON 文件"""

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _read_text(self, path: Path) -> str | None:
        """安全读取文本文件"""

        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return None

    def _resolve(self, value: str | None) -> Path:
        """把接口中的相对路径还原成当前项目可访问的绝对路径"""

        resolved = resolve_project_path(self.context.project_root, value)
        if resolved is None:
            raise ValueError("报告路径不能为空。")
        return resolved

    def _path(self, value: Path | None) -> str | None:
        """把项目内路径转换成相对源码根目录表达"""

        return to_project_relative(self.context.project_root, value)

    def _format_mtime(self, path: Path) -> str:
        """把文件修改时间转成 ISO 字符串"""

        return datetime.fromtimestamp(path.stat().st_mtime).isoformat()
