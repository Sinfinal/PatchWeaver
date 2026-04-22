"""Patch 获取服务骨架"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from patchweaver.models.patch import PatchBundle
from patchweaver.models.task import TaskContext
from patchweaver.retriever.repair_chain import RepairChainResolver


class RetrieverService:
    """负责组织 CVE 与补丁来源的检索流程"""

    def __init__(self, *, cache_dir: Path | None = None) -> None:
        """初始化修复链路解析器"""

        self.repair_chain = RepairChainResolver(cache_dir=cache_dir)
        self.last_fetch_trace_path: Path | None = None

    def fetch_patch_bundle(self, *, task: TaskContext, raw_patch_path: Path) -> PatchBundle:
        """生成真实来源链驱动的 PatchBundle"""

        trace_path = raw_patch_path.parent.parent / "analysis" / "trace" / "source_fetch_trace.json"
        self.last_fetch_trace_path = None

        try:
            chain = self.repair_chain.resolve(task.cve_id)
        except Exception as exc:
            self._write_fetch_trace(trace_path, self.repair_chain.latest_fetch_trace())
            if self.last_fetch_trace_path is not None:
                raise ValueError(
                    f"{exc} 来源抓取轨迹已写入 {self.last_fetch_trace_path.as_posix()}"
                ) from exc
            raise

        self._write_fetch_trace(trace_path, chain.get("fetch_trace"))
        raw_patch_path.parent.mkdir(parents=True, exist_ok=True)
        raw_patch_path.write_text(str(chain["raw_patch_text"]), encoding="utf-8")
        return PatchBundle(
            task_id=task.task_id,
            cve_id=task.cve_id,
            upstream_commit=str(chain["upstream_commit"]) if chain["upstream_commit"] is not None else None,
            stable_commit=str(chain["stable_commit"]) if chain["stable_commit"] is not None else None,
            commit_message=str(chain["commit_message"]),
            affected_files=list(chain["affected_files"]),
            raw_patch_path=raw_patch_path,
            source_evidence=list(chain["source_evidence"]),
        )

    def _write_fetch_trace(self, trace_path: Path, payload: Any) -> None:
        """把来源抓取轨迹固定落盘，便于失败后排障"""

        if not isinstance(payload, dict) or not payload:
            return

        trace_path.parent.mkdir(parents=True, exist_ok=True)
        trace_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.last_fetch_trace_path = trace_path
