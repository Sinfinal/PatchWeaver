"""补丁来源路由。"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel


class SourceRoute(BaseModel):
    """表示一条候选来源。"""

    name: str
    url: str
    stage: str | None = None
    priority: int = 0


class RetrieverSourceRouter:
    """负责给检索阶段提供来源优先级。"""

    def ordered_sources(self, cve_id: str) -> list[SourceRoute]:
        """返回当前 CVE 默认使用的来源顺序。"""

        return [
            SourceRoute(
                name="nvd",
                url=f"https://services.nvd.nist.gov/rest/json/cves/2.0?cveId={cve_id}",
                stage="metadata",
                priority=10,
            ),
            SourceRoute(
                name="cvelistV5",
                url=self.cvelist_url(cve_id),
                stage="metadata",
                priority=20,
            ),
            SourceRoute(
                name="linux-cve-announce",
                url="https://lore.kernel.org/linux-cve-announce/",
                stage="announce",
                priority=30,
            ),
            SourceRoute(
                name="linux-kernel-cve-process",
                url="https://docs.kernel.org/process/security-bugs.html",
                stage="announce",
                priority=40,
            ),
            SourceRoute(
                name="linux-stable",
                url="https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git/",
                stage="patch",
                priority=50,
            ),
            SourceRoute(
                name="upstream",
                url="https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/",
                stage="patch",
                priority=60,
            ),
        ]

    def cvelist_url(self, cve_id: str) -> str:
        """返回 cvelistV5 中该 CVE 的原始 JSON 地址。"""

        year, serial = self._split_cve_id(cve_id)
        bucket = f"{int(serial) // 1000}xxx"
        return f"https://raw.githubusercontent.com/CVEProject/cvelistV5/main/cves/{year}/{bucket}/{cve_id}.json"

    def classify_reference(self, url: str) -> str:
        """根据 URL 判断来源类型。"""

        lowered = url.lower()
        parsed = urlparse(lowered)
        host = parsed.netloc
        path = parsed.path

        if "services.nvd.nist.gov" in host or "nvd.nist.gov" in host:
            return "nvd"
        if "raw.githubusercontent.com" in host and "cvelistv5" in path:
            return "cvelistV5"
        if "lore.kernel.org" in host and "linux-cve-announce" in path:
            return "linux-cve-announce"
        if "openwall.com" in host and "/lists/oss-security/" in path:
            return "linux-cve-announce"
        if "docs.kernel.org" in host and "security-bugs" in path:
            return "linux-kernel-cve-process"
        if "git.kernel.org" in host and "/stable/" in path:
            return "linux-stable"
        if "github.com" in host and "/gregkh/linux/commit/" in path:
            return "linux-stable"
        if "git.kernel.org" in host and "torvalds/linux.git" in path:
            return "upstream"
        if "github.com" in host and "/torvalds/linux/commit/" in path:
            return "upstream"
        return "reference"

    def extract_commit_id(self, url: str) -> str | None:
        """从来源链接中提取 commit id。"""

        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        candidate = query.get("id", [None])[0]
        if candidate and re.fullmatch(r"[0-9a-fA-F]{7,40}", candidate):
            return candidate.lower()

        patterns = [
            r"/stable/c/([0-9a-fA-F]{7,40})",
            r"/commit/([0-9a-fA-F]{7,40})",
            r"/([0-9a-fA-F]{7,40})\.patch$",
        ]
        for pattern in patterns:
            match = re.search(pattern, parsed.path)
            if match:
                return match.group(1).lower()
        return None

    def patch_url_for_commit(self, url: str) -> str | None:
        """把 commit 链接转换为可直接下载的 patch 链接。"""

        commit_id = self.extract_commit_id(url)
        if commit_id is None:
            return None

        source_name = self.classify_reference(url)
        if source_name == "linux-stable":
            return f"https://github.com/gregkh/linux/commit/{commit_id}.patch"
        if source_name == "upstream":
            return f"https://github.com/torvalds/linux/commit/{commit_id}.patch"
        if url.lower().endswith(".patch"):
            return url
        return None

    def _split_cve_id(self, cve_id: str) -> tuple[str, str]:
        """拆分 CVE 年份和序号。"""

        match = re.fullmatch(r"CVE-(\d{4})-(\d+)", cve_id.upper())
        if match is None:
            raise ValueError(f"无效的 CVE ID：{cve_id}")
        return match.group(1), match.group(2)

