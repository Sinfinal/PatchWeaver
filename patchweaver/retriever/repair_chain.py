"""修复链路解析骨架"""

from __future__ import annotations

import json
import re
import socket
import time
from copy import deepcopy
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from patchweaver.models.patch import SourceEvidence
from patchweaver.retriever.source_router import RetrieverSourceRouter


class RepairChainResolver:
    """负责生成最小修复链路信息"""

    def __init__(self) -> None:
        """初始化来源路由器"""

        self.router = RetrieverSourceRouter()
        self.request_timeout_sec = 20
        self.max_request_retries = 3
        self.retry_backoff_sec = 1.0
        self._fetch_trace: dict[str, Any] = {}

    def latest_fetch_trace(self) -> dict[str, Any] | None:
        """返回最近一次解析过程中的来源抓取轨迹"""

        if not self._fetch_trace:
            return None
        return deepcopy(self._fetch_trace)

    def resolve(self, cve_id: str) -> dict[str, object]:
        """解析真实的 CVE 元数据、来源链与 patch 文本"""

        self._start_fetch_trace(cve_id)
        # NVD 偏描述，cvelistV5 偏引用和 CNA 信息
        # 两边一起取，后面来源链更完整
        try:
            nvd_record = self._fetch_nvd_record(cve_id)
            cvelist_record = self._fetch_cvelist_record(cve_id)
            title = self._record_title(cvelist_record)
            description = self._record_description(nvd_record, cvelist_record)
            references = self._collect_references(cve_id, nvd_record, cvelist_record)
            stable_refs = self._commit_references(references, source_name="linux-stable")
            upstream_refs = self._commit_references(references, source_name="upstream")

            # 有些条目正文里能提到 commit，但引用区没补全
            # 这里补一个兜底，尽量把 upstream commit 推出来
            if not upstream_refs:
                upstream_from_text = self._extract_commit_from_text(description)
                if upstream_from_text is not None:
                    generated_url = (
                        "https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/"
                        f"commit/?id={upstream_from_text}"
                    )
                    upstream_refs.append(
                        {
                            "url": generated_url,
                            "source_name": "upstream",
                            "commit_id": upstream_from_text,
                            "patch_url": self.router.patch_url_for_commit(generated_url),
                            "patch_urls": self.router.patch_urls_for_commit(generated_url),
                        }
                    )

            # 当前优先级是 stable 优先，缺失时再回退 upstream
            # 这样更接近真实目标内核的修复链
            selected_ref = stable_refs[0] if stable_refs else (upstream_refs[0] if upstream_refs else None)
            if selected_ref is None or not (selected_ref.get("patch_urls") or selected_ref.get("patch_url")):
                raise ValueError(f"{cve_id} 未找到可下载的 stable/upstream patch 来源。")

            patch_text = self._fetch_patch_text(selected_ref)
            commit_message = self._patch_subject(patch_text) or title or f"{cve_id} kernel patch"
            selected_commit = str(selected_ref["commit_id"])
            stable_commit = str(stable_refs[0]["commit_id"]) if stable_refs else None
            upstream_commit = str(upstream_refs[0]["commit_id"]) if upstream_refs else None
            if upstream_commit is None:
                upstream_commit = self._extract_upstream_commit_from_patch(patch_text)

            # 这组 source_evidence 会直接进 patch_bundle 和报告
            # 这里整理好后，后面阶段都按同一份来源链复用
            evidence = self._build_source_evidence(
                cve_id=cve_id,
                title=title,
                description=description,
                nvd_record=nvd_record,
                cvelist_record=cvelist_record,
                references=references,
                stable_refs=stable_refs,
                upstream_refs=upstream_refs,
                selected_commit=selected_commit,
            )
            affected_files = self._extract_affected_files(patch_text)
            self._finish_fetch_trace(
                selected_ref=selected_ref,
                stable_commit=stable_commit,
                upstream_commit=upstream_commit,
                affected_files=affected_files,
            )
            return {
                "upstream_commit": upstream_commit,
                "stable_commit": stable_commit,
                "commit_message": commit_message,
                "raw_patch_text": patch_text,
                "affected_files": affected_files,
                "source_evidence": evidence,
                "fetch_trace": self.latest_fetch_trace(),
            }
        except Exception as exc:
            self._mark_trace_failed(str(exc))
            raise

    def _fetch_nvd_record(self, cve_id: str) -> dict[str, Any]:
        """读取 NVD CVE JSON"""

        url = f"https://services.nvd.nist.gov/rest/json/cves/2.0?cveId={cve_id}"
        try:
            payload = self._fetch_json(url, source_name="nvd", stage="metadata")
        except ValueError as exc:
            return {
                "_fetch_error": str(exc),
                "references": [],
                "descriptions": [],
            }
        vulnerabilities = payload.get("vulnerabilities") or []
        if not vulnerabilities:
            return {
                "_fetch_error": f"NVD 中未找到 {cve_id}。",
                "references": [],
                "descriptions": [],
            }
        return vulnerabilities[0].get("cve") or {}

    def _fetch_cvelist_record(self, cve_id: str) -> dict[str, Any]:
        """读取 cvelistV5 原始 JSON"""

        url = self.router.cvelist_url(cve_id)
        try:
            return self._fetch_json(url, source_name="cvelistV5", stage="metadata")
        except ValueError as exc:
            return {
                "_fetch_error": str(exc),
                "containers": {"cna": {"references": [], "descriptions": []}, "adp": []},
            }

    def _collect_references(
        self,
        cve_id: str,
        nvd_record: dict[str, Any],
        cvelist_record: dict[str, Any],
    ) -> list[dict[str, str | None]]:
        """汇总 NVD 与 cvelist 中的候选引用"""

        collected: list[str] = []

        for item in nvd_record.get("references") or []:
            url = item.get("url")
            if isinstance(url, str):
                collected.append(url)

        cna = ((cvelist_record.get("containers") or {}).get("cna") or {})
        for item in cna.get("references") or []:
            url = item.get("url")
            if isinstance(url, str):
                collected.append(url)

        for adp in (cvelist_record.get("containers") or {}).get("adp") or []:
            for item in adp.get("references") or []:
                url = item.get("url")
                if isinstance(url, str):
                    collected.append(url)

        ordered: list[dict[str, str | None]] = []
        seen: set[str] = set()
        for url in collected:
            if url in seen:
                continue
            seen.add(url)
            ordered.append(
                {
                    "url": url,
                    "source_name": self.router.classify_reference(url),
                    "commit_id": self.router.extract_commit_id(url),
                    "patch_url": self.router.patch_url_for_commit(url),
                    "patch_urls": self.router.patch_urls_for_commit(url),
                }
            )

        if not any(item["source_name"] == "linux-cve-announce" for item in ordered):
            for route in self.router.ordered_sources(cve_id):
                if route.name == "linux-kernel-cve-process":
                    ordered.append(
                        {
                            "url": route.url,
                            "source_name": route.name,
                            "commit_id": None,
                            "patch_url": None,
                        }
                    )
                    break

        return ordered

    def _commit_references(
        self,
        references: list[dict[str, str | None]],
        *,
        source_name: str,
    ) -> list[dict[str, str | None]]:
        """筛选出某类 commit 引用，并按顺序去重"""

        selected: list[dict[str, str | None]] = []
        seen: set[str] = set()
        for item in references:
            if item.get("source_name") != source_name:
                continue
            commit_id = item.get("commit_id")
            patch_urls = list(item.get("patch_urls") or [])
            if not patch_urls and item.get("patch_url") is not None:
                patch_urls = [str(item["patch_url"])]
            if commit_id is None or not patch_urls or commit_id in seen:
                continue
            seen.add(commit_id)
            normalized_item = dict(item)
            normalized_item["patch_urls"] = patch_urls
            normalized_item["patch_url"] = patch_urls[0]
            selected.append(normalized_item)
        return selected

    def _build_source_evidence(
        self,
        *,
        cve_id: str,
        title: str | None,
        description: str | None,
        nvd_record: dict[str, Any],
        cvelist_record: dict[str, Any],
        references: list[dict[str, str | None]],
        stable_refs: list[dict[str, str | None]],
        upstream_refs: list[dict[str, str | None]],
        selected_commit: str,
    ) -> list[SourceEvidence]:
        """把来源链整理为结构化证据条目"""

        evidence: list[SourceEvidence] = [
            SourceEvidence(
                source_name="nvd",
                url=f"https://services.nvd.nist.gov/rest/json/cves/2.0?cveId={cve_id}",
                stage="metadata",
                reference_type="cve_record",
                title=title,
                summary=self._shorten(
                    nvd_record.get("_fetch_error")
                    or description
                    or nvd_record.get("descriptions", [{}])[0].get("value")
                    or f"{cve_id} 元数据来自 NVD。",
                    limit=240,
                ),
            ),
            SourceEvidence(
                source_name="cvelistV5",
                url=self.router.cvelist_url(cve_id),
                stage="metadata",
                reference_type="cve_record",
                title=title,
                summary=self._shorten(
                    description
                    or self._record_description({}, cvelist_record)
                    or f"{cve_id} 元数据来自 cvelistV5。",
                    limit=240,
                ),
            ),
        ]

        for item in references:
            source_name = str(item.get("source_name"))
            if source_name not in {"linux-cve-announce", "linux-kernel-cve-process"}:
                continue
            evidence.append(
                SourceEvidence(
                    source_name=source_name,
                    url=str(item["url"]),
                    stage="announce",
                    reference_type="advisory",
                    summary=f"{cve_id} 的公告/流程来源：{item['url']}",
                )
            )

        for item in stable_refs[:3]:
            commit_id = str(item["commit_id"])
            evidence.append(
                SourceEvidence(
                    source_name="linux-stable",
                    url=str(item["url"]),
                    stage="patch",
                    reference_type="stable_commit",
                    commit_id=commit_id,
                    preferred=commit_id == selected_commit,
                    summary=f"stable backport 提交 {commit_id}，优先作为目标内核 patch 来源。",
                )
            )

        for item in upstream_refs[:3]:
            commit_id = str(item["commit_id"])
            evidence.append(
                SourceEvidence(
                    source_name="upstream",
                    url=str(item["url"]),
                    stage="patch",
                    reference_type="upstream_commit",
                    commit_id=commit_id,
                    preferred=commit_id == selected_commit,
                    summary=f"upstream 提交 {commit_id}，在无 stable backport 时作为回退来源。",
                )
            )

        return evidence

    def _record_title(self, cvelist_record: dict[str, Any]) -> str | None:
        """读取 cvelist 中的标题"""

        cna = ((cvelist_record.get("containers") or {}).get("cna") or {})
        title = cna.get("title")
        return title if isinstance(title, str) and title.strip() else None

    def _record_description(self, nvd_record: dict[str, Any], cvelist_record: dict[str, Any]) -> str | None:
        """读取更适合展示的描述文本"""

        descriptions = nvd_record.get("descriptions") or []
        for item in descriptions:
            value = item.get("value")
            if isinstance(value, str) and value.strip():
                return value.strip()

        cna = ((cvelist_record.get("containers") or {}).get("cna") or {})
        for item in cna.get("descriptions") or []:
            value = item.get("value")
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _patch_subject(self, patch_text: str) -> str | None:
        """从 patch 原文中提取 Subject"""

        for line in patch_text.splitlines():
            if not line.startswith("Subject:"):
                continue
            subject = line.removeprefix("Subject:").strip()
            subject = re.sub(r"^\[PATCH[^\]]*\]\s*", "", subject)
            return subject or None
        return None

    def _extract_upstream_commit_from_patch(self, patch_text: str) -> str | None:
        """从 stable patch 正文里提取 upstream commit"""

        match = re.search(r"commit ([0-9a-f]{7,40}) upstream\.", patch_text, flags=re.IGNORECASE)
        if match:
            return match.group(1).lower()
        return None

    def _extract_commit_from_text(self, text: str | None) -> str | None:
        """从描述文本中提取 commit id"""

        if not text:
            return None
        match = re.search(r"commit ([0-9a-f]{7,40})", text, flags=re.IGNORECASE)
        if match:
            return match.group(1).lower()
        return None

    def _extract_affected_files(self, patch_text: str) -> list[str]:
        """从 patch 文本中提取受影响文件列表"""

        files: list[str] = []
        seen: set[str] = set()
        for line in patch_text.splitlines():
            if line.startswith("diff --git "):
                parts = line.split()
                if len(parts) < 4:
                    continue
                candidate = parts[3]
                if candidate.startswith("b/"):
                    candidate = candidate[2:]
                if candidate and candidate != "/dev/null" and candidate not in seen:
                    seen.add(candidate)
                    files.append(candidate)
            elif line.startswith("+++ "):
                candidate = line[4:].strip()
                if candidate.startswith("b/"):
                    candidate = candidate[2:]
                if candidate and candidate != "/dev/null" and candidate not in seen:
                    seen.add(candidate)
                    files.append(candidate)
        return files

    def _shorten(self, text: str, *, limit: int) -> str:
        """裁剪说明文本长度"""

        normalized = " ".join(text.split())
        if len(normalized) <= limit:
            return normalized
        return normalized[: limit - 1].rstrip() + "…"

    def _fetch_patch_text(self, selected_ref: dict[str, str | None]) -> str:
        """按来源优先级依次尝试下载 patch 文本"""

        patch_urls = [str(item) for item in selected_ref.get("patch_urls") or [] if item]
        if not patch_urls and selected_ref.get("patch_url"):
            patch_urls = [str(selected_ref["patch_url"])]
        if not patch_urls:
            raise ValueError("当前引用没有可用的 patch 下载地址。")

        errors: list[str] = []
        for index, patch_url in enumerate(patch_urls, start=1):
            try:
                patch_text = self._fetch_text(
                    patch_url,
                    source_name=str(selected_ref.get("source_name") or "patch"),
                    stage="patch",
                )
                selected_ref["selected_patch_url"] = patch_url
                selected_ref["selected_patch_index"] = str(index)
                return patch_text
            except ValueError as exc:
                errors.append(str(exc))

        raise ValueError(
            "补丁下载失败，已尝试全部候选地址: "
            + " | ".join(errors)
        )

    def _fetch_json(self, url: str, *, source_name: str, stage: str) -> dict[str, Any]:
        """读取 JSON 内容"""

        return json.loads(self._fetch_text(url, source_name=source_name, stage=stage))

    def _fetch_text(self, url: str, *, source_name: str, stage: str) -> str:
        """下载文本内容"""

        request = Request(url, headers={"User-Agent": "PatchWeaver/0.1"})
        for attempt_no in range(1, self.max_request_retries + 1):
            started_at = time.monotonic()
            try:
                with urlopen(request, timeout=self.request_timeout_sec) as response:
                    charset = response.headers.get_content_charset() or "utf-8"
                    content = response.read().decode(charset, errors="replace")
                self._record_fetch_event(
                    source_name=source_name,
                    stage=stage,
                    url=url,
                    attempt_no=attempt_no,
                    outcome="success",
                    elapsed_ms=self._elapsed_ms(started_at),
                )
                return content
            except HTTPError as exc:  # pragma: no cover - 网络来源依赖
                retry_allowed = exc.code in {429, 500, 502, 503, 504} and attempt_no < self.max_request_retries
                message = f"请求来源失败：{url} ({exc.code})"
                self._record_fetch_event(
                    source_name=source_name,
                    stage=stage,
                    url=url,
                    attempt_no=attempt_no,
                    outcome="http_error",
                    elapsed_ms=self._elapsed_ms(started_at),
                    error=message,
                    retry_allowed=retry_allowed,
                )
                if not retry_allowed:
                    raise ValueError(message) from exc
            except (URLError, TimeoutError, socket.timeout, OSError) as exc:  # pragma: no cover - 网络来源依赖
                retry_allowed = attempt_no < self.max_request_retries
                message = f"请求来源失败：{url} ({self._reason_text(exc)})"
                self._record_fetch_event(
                    source_name=source_name,
                    stage=stage,
                    url=url,
                    attempt_no=attempt_no,
                    outcome="network_error",
                    elapsed_ms=self._elapsed_ms(started_at),
                    error=message,
                    retry_allowed=retry_allowed,
                )
                if not retry_allowed:
                    raise ValueError(message) from exc

            # 单个来源先做有限次重试
            # 连续超时还不通时，再交给上层切到镜像或下一来源
            time.sleep(self.retry_backoff_sec * attempt_no)

        raise ValueError(f"请求来源失败：{url} (超过最大重试次数)")

    def _start_fetch_trace(self, cve_id: str) -> None:
        """初始化一次来源抓取轨迹"""

        self._fetch_trace = {
            "cve_id": cve_id,
            "status": "running",
            "request_timeout_sec": self.request_timeout_sec,
            "max_request_retries": self.max_request_retries,
            "events": [],
            "summary": {
                "request_count": 0,
                "success_count": 0,
                "failure_count": 0,
            },
            "selected_patch_source": None,
        }

    def _record_fetch_event(
        self,
        *,
        source_name: str,
        stage: str,
        url: str,
        attempt_no: int,
        outcome: str,
        elapsed_ms: int,
        error: str | None = None,
        retry_allowed: bool | None = None,
    ) -> None:
        """记录一次来源请求尝试"""

        if not self._fetch_trace:
            return

        self._fetch_trace.setdefault("events", []).append(
            {
                "source_name": source_name,
                "stage": stage,
                "url": url,
                "attempt_no": attempt_no,
                "outcome": outcome,
                "elapsed_ms": elapsed_ms,
                "error": error,
                "retry_allowed": retry_allowed,
            }
        )

        summary = self._fetch_trace.setdefault("summary", {})
        summary["request_count"] = int(summary.get("request_count", 0)) + 1
        if outcome == "success":
            summary["success_count"] = int(summary.get("success_count", 0)) + 1
        else:
            summary["failure_count"] = int(summary.get("failure_count", 0)) + 1

    def _finish_fetch_trace(
        self,
        *,
        selected_ref: dict[str, str | None],
        stable_commit: str | None,
        upstream_commit: str | None,
        affected_files: list[str],
    ) -> None:
        """补齐来源抓取轨迹中的最终摘要"""

        if not self._fetch_trace:
            return

        self._fetch_trace["status"] = "passed"
        self._fetch_trace["selected_patch_source"] = {
            "source_name": selected_ref.get("source_name"),
            "commit_id": selected_ref.get("commit_id"),
            "selected_patch_url": selected_ref.get("selected_patch_url") or selected_ref.get("patch_url"),
            "patch_url_candidates": list(selected_ref.get("patch_urls") or []),
            "stable_commit": stable_commit,
            "upstream_commit": upstream_commit,
        }
        summary = self._fetch_trace.setdefault("summary", {})
        summary["affected_file_count"] = len(affected_files)

    def _mark_trace_failed(self, error: str) -> None:
        """在最终失败时补齐来源抓取轨迹状态"""

        if not self._fetch_trace:
            return
        self._fetch_trace["status"] = "failed"
        self._fetch_trace["error"] = error

    def _elapsed_ms(self, started_at: float) -> int:
        """把 monotonic 时间差换成毫秒整数"""

        return int((time.monotonic() - started_at) * 1000)

    def _reason_text(self, exc: BaseException) -> str:
        """统一整理网络异常说明文本"""

        if isinstance(exc, URLError):
            reason = exc.reason
            return str(reason)
        return str(exc)
