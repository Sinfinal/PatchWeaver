"""修复链路解析骨架。"""

from __future__ import annotations

from patchweaver.models.patch import SourceEvidence
from patchweaver.retriever.source_router import RetrieverSourceRouter


class RepairChainResolver:
    """负责生成最小修复链路信息。"""

    def __init__(self) -> None:
        """初始化来源路由器。"""

        self.router = RetrieverSourceRouter()

    def resolve(self, cve_id: str) -> dict[str, object]:
        """返回一份占位修复链路。"""

        sources = self.router.ordered_sources(cve_id)
        evidence = [
            SourceEvidence(
                source_name=source.name,
                url=source.url,
                summary=f"{cve_id} 的 {source.name} 来源占位记录。",
            )
            for source in sources
        ]
        return {
            "upstream_commit": f"upstream-{cve_id.lower()}",
            "stable_commit": f"stable-{cve_id.lower()}",
            "commit_message": f"{cve_id}: MVP 阶段占位修复链路",
            "source_evidence": evidence,
        }

