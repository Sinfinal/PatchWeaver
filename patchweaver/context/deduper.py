"""上下文去重工具"""

from __future__ import annotations

from patchweaver.models.evidence import EvidenceSpan


def dedupe_spans(spans: list[EvidenceSpan]) -> tuple[list[EvidenceSpan], int]:
    """按来源和行号对证据片段去重"""

    seen: set[tuple[str, str, int | None, int | None]] = set()
    result: list[EvidenceSpan] = []
    duplicate_hits = 0
    for span in spans:
        key = (span.source_type, span.source_path, span.start_line, span.end_line)
        if key in seen:
            duplicate_hits += 1
            continue
        seen.add(key)
        result.append(span)
    return result, duplicate_hits

