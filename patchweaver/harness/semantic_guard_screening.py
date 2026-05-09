"""Semantic guard candidate screening helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from patchweaver.harness.livepatchability import analyze_patch_shape, classify_kpatch_constraint_rewrite


GUARD_CATEGORIES = ("null", "size_len", "bounds", "overflow", "invalid_state")

_CATEGORY_PATTERNS: dict[str, tuple[str, ...]] = {
    "null": (
        r"\bnull\b",
        r"\bnullptr\b",
        r"!\s*[A-Za-z_][A-Za-z0-9_]*(?:->|\b)",
        r"\b-EFAULT\b",
        r"null pointer",
        r"npe",
    ),
    "size_len": (
        r"\bsize\b",
        r"\blen(?:gth)?\b",
        r"\bcount\b",
        r"\bnr_\w+\b",
        r"\bsizeof\b",
        r"\bPAGE_SIZE\b",
        r"\b-E2BIG\b",
    ),
    "bounds": (
        r"\bbounds?\b",
        r"\boob\b",
        r"out[- ]of[- ]bounds",
        r"\bindex\b",
        r"\boffset\b",
        r"\blimit\b",
        r"\brange\b",
        r"\b-EINVAL\b",
    ),
    "overflow": (
        r"\boverflow\b",
        r"\bwrap(?:around)?\b",
        r"\bcheck_(?:add|mul|sub)_overflow\b",
        r"\bsize_add\b",
        r"\bsize_mul\b",
        r"\bU(?:INT|LONG|LLONG)_MAX\b",
        r"\bMAX_\w+\b",
    ),
    "invalid_state": (
        r"\binvalid\b",
        r"\bstate\b",
        r"\brace\b",
        r"\bready\b",
        r"\binitiali[sz]ed\b",
        r"\bconfigured\b",
        r"\b-EIO\b",
        r"\b-ENODEV\b",
        r"\b-ENOENT\b",
        r"\b-EPERM\b",
    ),
}

_STATEFUL_PATCH_PATTERNS = (
    r"^(?:\+|-)\s*(?:typedef\s+)?(?:struct|enum|union)\s+\w+",
    r"^(?:\+|-)\s*static\s+(?!inline\b).*(?:=|;|\[)",
    r"\b(?:__init|__exit|MODULE_|EXPORT_SYMBOL|module_)\b",
)


@dataclass
class SemanticGuardCandidate:
    """A compact report row for semantic_guard_rewrite triage."""

    cve_id: str
    guard_category: str
    confidence: float
    affected_files: list[str]
    reason: str
    suggested_validation_mode: str
    task_id: str | None = None
    artifact_dir: str | None = None
    guard_signals: list[str] = field(default_factory=list)
    rag_seed_hit: bool = False
    rag_subsystem: str | None = None
    rag_summary: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable candidate row."""

        payload = {
            "cve_id": self.cve_id,
            "guard_category": self.guard_category,
            "confidence": self.confidence,
            "affected_files": self.affected_files,
            "reason": self.reason,
            "suggested_validation_mode": self.suggested_validation_mode,
        }
        for key in [
            "task_id",
            "artifact_dir",
            "guard_signals",
            "rag_seed_hit",
            "rag_subsystem",
            "rag_summary",
        ]:
            value = getattr(self, key)
            if value not in (None, [], False):
                payload[key] = value
        return payload


def classify_guard_category(text: str) -> tuple[str, list[str]]:
    """Classify guard intent text into the requested high-level category."""

    lowered = text.lower()
    scores: dict[str, int] = {}
    signals: dict[str, list[str]] = {}
    for category, patterns in _CATEGORY_PATTERNS.items():
        category_signals: list[str] = []
        for pattern in patterns:
            if re.search(pattern, lowered, flags=re.IGNORECASE | re.MULTILINE):
                category_signals.append(pattern)
        if category_signals:
            scores[category] = len(category_signals)
            signals[category] = category_signals
    if not scores:
        return "unknown", []
    if scores.get("overflow"):
        scores["overflow"] += 2
    ordered = sorted(scores.items(), key=lambda item: (-item[1], GUARD_CATEGORIES.index(item[0])))
    category = ordered[0][0]
    return category, signals[category][:6]


def score_semantic_guard_fit(record: dict[str, Any]) -> dict[str, Any]:
    """Score whether a record is a good semantic_guard_rewrite candidate."""

    patch_text = str(record.get("patch_text") or "")
    semantic_card = record.get("semantic_card") if isinstance(record.get("semantic_card"), dict) else {}
    rag_seed = record.get("rag_seed") if isinstance(record.get("rag_seed"), dict) else {}
    constraint = record.get("constraint_report") if isinstance(record.get("constraint_report"), dict) else {}
    rewrite_plan = record.get("rewrite_plan") if isinstance(record.get("rewrite_plan"), dict) else {}
    patch_bundle = record.get("patch_bundle") if isinstance(record.get("patch_bundle"), dict) else {}

    evidence_text = "\n".join(
        [
            patch_text,
            str(patch_bundle.get("commit_message") or ""),
            str(semantic_card.get("bug_class") or ""),
            str(semantic_card.get("root_cause") or ""),
            "\n".join(str(item) for item in semantic_card.get("must_keep_conditions") or []),
            "\n".join(str(item) for item in semantic_card.get("must_keep_side_effects") or []),
            str(rag_seed.get("summary") or ""),
            str(constraint.get("summary") or ""),
            str(rewrite_plan.get("selection_reason") or ""),
        ]
    )
    category, category_signals = classify_guard_category(evidence_text)
    patch_shape = analyze_patch_shape(patch_text) if patch_text else {}
    if not patch_shape and isinstance(record.get("patch_shape"), dict):
        patch_shape = dict(record["patch_shape"])

    score = 0.1
    reasons: list[str] = []
    guard_signals: list[str] = []
    if category != "unknown":
        score += 0.25
        reasons.append(f"命中 {category} guard 语义")
        guard_signals.extend(category_signals)
    if patch_shape.get("guard_like"):
        score += 0.25
        reasons.append("patch 形态像函数局部 guard")
        guard_signals.append("patch_shape.guard_like")
    if semantic_card.get("must_keep_conditions"):
        score += 0.15
        reasons.append("semantic_card 含必须保留条件")
    if category != "unknown" and rag_seed.get("summary") and not patch_text:
        score += 0.15
        reasons.append("RAG seed 摘要直接命中 guard 语义")
    if rag_seed.get("summary") and re.search(r"\b(?:fix|prevent|reject|check|guard)\b", str(rag_seed["summary"]), re.I):
        score += 0.05
        reasons.append("RAG seed 摘要包含修复/检查动词")
    if semantic_card.get("touched_functions") and len(semantic_card.get("touched_functions") or []) <= 2:
        score += 0.08
        reasons.append("触达函数数量较少")
    touched_files = _affected_files(record)
    if touched_files and len(touched_files) <= 2:
        score += 0.06
        reasons.append("触达文件数量较少")
    if _has_safe_exit_patch_line(patch_text):
        score += 0.12
        reasons.append("新增分支含安全退出路径")
        guard_signals.append("safe_exit")
    if _looks_stateful_patch(patch_text):
        score -= 0.25
        reasons.append("包含状态/section/类型改动，guard 适配度下调")
    if constraint.get("preferred_route") == "direct_apply_patch":
        score += 0.04
        reasons.append("约束诊断当前为低风险 direct apply")
    if _rewrite_plan_mentions_semantic_guard(rewrite_plan):
        score += 0.08
        reasons.append("rewrite_plan 已出现 semantic_guard 候选路线")

    confidence = max(0.0, min(0.99, round(score, 2)))
    suggested_validation_mode = "dry-run"
    if confidence >= 0.75:
        suggested_validation_mode = "analyze"
    if confidence >= 0.88 and patch_shape.get("guard_like"):
        suggested_validation_mode = "single-cve-full-run-with-timeout"

    return {
        "guard_category": category,
        "confidence": confidence,
        "affected_files": touched_files,
        "reason": "；".join(reasons) if reasons else "未发现足够 guard 证据",
        "suggested_validation_mode": suggested_validation_mode,
        "guard_signals": list(dict.fromkeys(guard_signals))[:12],
        "patch_shape": patch_shape,
        "kpatch_constraint_rewrite_class": classify_kpatch_constraint_rewrite({"patch_shape": patch_shape}),
    }


def build_semantic_guard_candidate(record: dict[str, Any], *, min_confidence: float = 0.55) -> SemanticGuardCandidate | None:
    """Build a candidate row when the record clears the confidence gate."""

    result = score_semantic_guard_fit(record)
    if result["guard_category"] == "unknown" or result["confidence"] < min_confidence:
        return None
    rag_seed = record.get("rag_seed") if isinstance(record.get("rag_seed"), dict) else {}
    return SemanticGuardCandidate(
        cve_id=str(record.get("cve_id") or ""),
        task_id=str(record.get("task_id") or "") or None,
        artifact_dir=str(record.get("artifact_dir") or "") or None,
        guard_category=str(result["guard_category"]),
        confidence=float(result["confidence"]),
        affected_files=list(result["affected_files"]),
        reason=str(result["reason"]),
        suggested_validation_mode=str(result["suggested_validation_mode"]),
        guard_signals=list(result["guard_signals"]),
        rag_seed_hit=bool(rag_seed),
        rag_subsystem=str(rag_seed.get("subsystem") or "") or None,
        rag_summary=str(rag_seed.get("summary") or "") or None,
    )


def sort_candidates(candidates: list[SemanticGuardCandidate]) -> list[SemanticGuardCandidate]:
    """Sort candidates by confidence and deterministic CVE id."""

    return sorted(candidates, key=lambda item: (-item.confidence, item.cve_id, item.task_id or ""))


def read_json_if_exists(path: Path) -> dict[str, Any]:
    """Read a JSON object if present, otherwise return an empty object."""

    if not path.exists():
        return {}
    try:
        payload = __import__("json").loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _affected_files(record: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for source in [
        record.get("affected_files"),
        (record.get("patch_bundle") or {}).get("affected_files") if isinstance(record.get("patch_bundle"), dict) else None,
        (record.get("semantic_card") or {}).get("touched_files") if isinstance(record.get("semantic_card"), dict) else None,
        (record.get("constraint_report") or {}).get("target_files") if isinstance(record.get("constraint_report"), dict) else None,
        (record.get("rewrite_plan") or {}).get("target_files") if isinstance(record.get("rewrite_plan"), dict) else None,
        (record.get("patch_shape") or {}).get("touched_files") if isinstance(record.get("patch_shape"), dict) else None,
    ]:
        if not isinstance(source, list):
            continue
        values.extend(str(item) for item in source if str(item).strip())
    return list(dict.fromkeys(values))


def _has_safe_exit_patch_line(patch_text: str) -> bool:
    return any(
        line.startswith("+")
        and not line.startswith("+++")
        and re.search(r"\breturn\b|\bgoto\b|\bbreak;\b|\bcontinue;\b", line)
        for line in patch_text.splitlines()
    )


def _looks_stateful_patch(patch_text: str) -> bool:
    for line in patch_text.splitlines():
        if not line.startswith(("+", "-")) or line.startswith(("+++", "---")):
            continue
        if any(re.search(pattern, line, flags=re.IGNORECASE) for pattern in _STATEFUL_PATCH_PATTERNS):
            return True
    return False


def _rewrite_plan_mentions_semantic_guard(rewrite_plan: dict[str, Any]) -> bool:
    text = "\n".join(
        [
            str(rewrite_plan.get("selected_recipe") or ""),
            str(rewrite_plan.get("selected_route_family") or ""),
            "\n".join(str(item) for item in rewrite_plan.get("rule_hits") or []),
            "\n".join(str(item) for item in rewrite_plan.get("notes") or []),
            "\n".join(str(item) for item in rewrite_plan.get("candidate_summaries") or []),
        ]
    ).lower()
    return "semantic_guard" in text or "guard" in text
