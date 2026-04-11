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
        """生成一份最小可落盘的 PatchBundle。"""

        chain = self.repair_chain.resolve(task.cve_id)
        return PatchBundle(
            task_id=task.task_id,
            cve_id=task.cve_id,
            upstream_commit=str(chain["upstream_commit"]),
            stable_commit=str(chain["stable_commit"]),
            commit_message=str(chain["commit_message"]),
            affected_files=["kernel/example.c"],
            raw_patch_path=raw_patch_path,
            source_evidence=list(chain["source_evidence"]),
        )

    def render_placeholder_patch(self, cve_id: str) -> str:
        """输出一份占位 patch 文本。"""

        return "\n".join(
            [
                f"From: PatchWeaver <noreply@patchweaver.local>",
                f"Subject: [PATCH] {cve_id} placeholder fix",
                "",
                "--- a/kernel/example.c",
                "+++ b/kernel/example.c",
                "@@",
                "-return old_value;",
                "+return fixed_value;",
                "",
            ]
        )
