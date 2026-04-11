"""补丁来源路由。"""

from __future__ import annotations

from pydantic import BaseModel


class SourceRoute(BaseModel):
    """表示一条候选来源。"""

    name: str
    url: str


class RetrieverSourceRouter:
    """负责给检索阶段提供来源优先级。"""

    def ordered_sources(self, cve_id: str) -> list[SourceRoute]:
        """返回当前 CVE 默认使用的来源顺序。"""

        return [
            SourceRoute(name="nvd", url=f"https://nvd.nist.gov/vuln/detail/{cve_id}"),
            SourceRoute(name="linux-cve-announce", url="https://lore.kernel.org/linux-cve-announce/"),
            SourceRoute(name="linux-stable", url="https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git/"),
            SourceRoute(name="upstream", url="https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/"),
        ]

