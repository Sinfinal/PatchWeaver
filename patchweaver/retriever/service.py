"""Patch 获取服务骨架。"""

from __future__ import annotations

from pathlib import Path

from patchweaver.models.patch import PatchBundle
from patchweaver.models.task import TaskContext
from patchweaver.retriever.repair_chain import RepairChainResolver


class RetrieverService:
    """负责组织 CVE 与补丁来源的检索流程。"""

    def __init__(self) -> None:
        """初始化修复链路解析器。"""

        self.repair_chain = RepairChainResolver()

    def fetch_patch_bundle(self, *, task: TaskContext, raw_patch_path: Path) -> PatchBundle:
        """生成真实来源链驱动的 PatchBundle。"""

        chain = self.repair_chain.resolve(task.cve_id)
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
