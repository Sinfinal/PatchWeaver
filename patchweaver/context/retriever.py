"""上下文检索器。"""

from __future__ import annotations

from patchweaver.models.evidence import EvidenceBundle


class ContextRetriever:
    """负责从已有证据中挑选上下文候选。"""

    def select(self, bundle: EvidenceBundle) -> EvidenceBundle:
        """当前先直接返回输入证据。"""

        return bundle

