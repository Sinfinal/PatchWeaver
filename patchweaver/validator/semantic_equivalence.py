"""Lightweight semantic equivalence evidence for rewritten patches."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from shutil import which
from typing import Any


def run_light_semantic_equivalence(
    *,
    repair_intent_path: Path,
    semantic_guard_path: Path,
    rewritten_patch_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    """Check that RepairIntent obligations are still visible in rewritten.patch."""

    repair_intent = _read_json(repair_intent_path)
    semantic_guard = _read_json(semantic_guard_path)
    patch_text = rewritten_patch_path.read_text(encoding="utf-8", errors="replace")
    patch_index = _PatchIndex(patch_text)

    checks = {
        "guard_conditions": _check_items(
            _required_items(repair_intent, semantic_guard, "guard_conditions"),
            patch_index,
        ),
        "safe_exits": _check_items(
            _required_items(repair_intent, semantic_guard, "safe_exits", "safe_exit"),
            patch_index,
        ),
        "preserved_side_effects": _check_items(
            _required_items(repair_intent, semantic_guard, "preserved_side_effects", "side_effects"),
            patch_index,
        ),
        "semantic_guard_status": _check_semantic_guard_status(semantic_guard),
        "rewritten_patch_shape": _check_patch_shape(patch_text),
    }
    missing_required_items = sum(len(item.get("missing", [])) for item in checks.values() if isinstance(item, dict))
    failed_checks = [
        name
        for name, check in checks.items()
        if isinstance(check, dict) and check.get("status") == "failed"
    ]
    status = "passed" if missing_required_items == 0 and not failed_checks else "failed"
    result = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "light_semantic",
        "diffkemp_available": which("diffkemp") is not None,
        "status": status,
        "cve_id": repair_intent.get("cve_id"),
        "inputs": {
            "repair_intent_path": str(repair_intent_path),
            "semantic_guard_path": str(semantic_guard_path),
            "rewritten_patch_path": str(rewritten_patch_path),
        },
        "summary": {
            "missing_required_items": missing_required_items,
            "failed_checks": failed_checks,
            "note": "Static light semantic check only; real equivalence still requires validation-machine evidence.",
        },
        "checks": checks,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


class _PatchIndex:
    def __init__(self, patch_text: str) -> None:
        self.patch_text = patch_text
        self.added_text = "\n".join(
            line[1:] for line in patch_text.splitlines() if line.startswith("+") and not line.startswith("+++")
        )
        self.normalized_all = _normalize(patch_text)
        self.normalized_added = _normalize(self.added_text)

    def contains(self, item: str) -> bool:
        normalized_item = _normalize(item)
        if not normalized_item:
            return True
        if normalized_item in self.normalized_added or normalized_item in self.normalized_all:
            return True
        tokens = [token for token in re.split(r"[^A-Za-z0-9_]+", item) if len(token) >= 2]
        if not tokens:
            return False
        haystack = self.normalized_added or self.normalized_all
        return all(_normalize(token) in haystack for token in tokens)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _required_items(payload: dict[str, Any], guard_payload: dict[str, Any], *keys: str) -> list[str]:
    items: list[str] = []
    for source in (payload, guard_payload):
        for key in keys:
            value = source.get(key)
            if isinstance(value, str):
                items.append(value)
            elif isinstance(value, list):
                items.extend(str(item) for item in value if str(item).strip())
    return sorted(dict.fromkeys(item.strip() for item in items if item.strip()))


def _check_items(items: list[str], patch_index: _PatchIndex) -> dict[str, Any]:
    present = [item for item in items if patch_index.contains(item)]
    missing = [item for item in items if item not in present]
    return {
        "status": "passed" if not missing else "failed",
        "required": items,
        "present": present,
        "missing": missing,
    }


def _check_semantic_guard_status(payload: dict[str, Any]) -> dict[str, Any]:
    status = str(payload.get("status") or payload.get("semantic_guard_status") or "unknown")
    failed = status.lower() in {"failed", "error"}
    return {
        "status": "failed" if failed else "passed",
        "observed": status,
    }


def _check_patch_shape(patch_text: str) -> dict[str, Any]:
    ok = bool(patch_text.strip() and "diff --git " in patch_text and "@@" in patch_text)
    return {
        "status": "passed" if ok else "failed",
        "has_diff_header": "diff --git " in patch_text,
        "has_hunk": "@@" in patch_text,
    }


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()
