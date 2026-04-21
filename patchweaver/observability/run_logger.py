"""轻量运行日志写入器"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from patchweaver.utils.path_policy import ensure_within_root, relativize_payload


class RunLogger:
    """统一写入文本日志和 JSONL 事件日志"""

    def __init__(self, project_root: Path, logging_config: Any) -> None:
        """根据项目根目录和日志配置解析实际落盘路径"""

        self.project_root = project_root
        self.logging_config = logging_config
        self.text_log_path = self._resolve_path(logging_config.file_path)
        self.jsonl_log_path = self._resolve_path(logging_config.jsonl_path)

    def info(self, event: str, message: str, **payload: Any) -> None:
        """记录一条普通信息"""

        self._write("INFO", event, message, payload)

    def warning(self, event: str, message: str, **payload: Any) -> None:
        """记录一条告警信息"""

        self._write("WARNING", event, message, payload)

    def error(self, event: str, message: str, **payload: Any) -> None:
        """记录一条错误信息"""

        self._write("ERROR", event, message, payload)

    def _write(self, level: str, event: str, message: str, payload: dict[str, Any]) -> None:
        """把同一条事件同时写到文本日志和 JSONL"""

        timestamp = datetime.now(timezone.utc).isoformat()
        normalized_payload = relativize_payload(payload, self.project_root)
        self.text_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.text_log_path.open("a", encoding="utf-8") as handle:
            handle.write(self._format_text_line(timestamp, level, event, message, normalized_payload))

        if not self.logging_config.enable_jsonl:
            return

        self.jsonl_log_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": timestamp,
            "level": level,
            "event": event,
            "message": message,
            "payload": normalized_payload,
        }
        with self.jsonl_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _format_text_line(
        self,
        timestamp: str,
        level: str,
        event: str,
        message: str,
        payload: dict[str, Any],
    ) -> str:
        """整理文本日志的单行格式"""

        if not payload:
            return f"{timestamp} [{level}] [{event}] {message}\n"
        compact_payload = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        return f"{timestamp} [{level}] [{event}] {message} | {compact_payload}\n"

    def _resolve_path(self, raw_path: str) -> Path:
        """把日志配置路径统一展开成绝对路径"""

        return ensure_within_root(self.project_root, raw_path, label="logging_path")
