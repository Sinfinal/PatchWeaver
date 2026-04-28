"""改写路线有效性检查"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from patchweaver.models.rewrite import RewritePlan
from patchweaver.utils.path_policy import relativize_payload


def build_route_effectiveness_report(
    *,
    project_root: Path,
    task_id: str,
    attempt_no: int,
    current_plan: RewritePlan,
    current_patch_path: Path,
    previous_attempt_dir: Path | None,
) -> dict[str, Any]:
    """比较本轮 rewritten.patch 和上一轮，判断换路线是否真的改变补丁形态"""

    current_text = current_patch_path.read_text(encoding="utf-8", errors="replace")
    current_signature = _patch_signature(current_text)
    previous_plan = _read_previous_plan(previous_attempt_dir)
    previous_patch_path = previous_attempt_dir / "rewrite" / "rewritten.patch" if previous_attempt_dir else None
    previous_text = (
        previous_patch_path.read_text(encoding="utf-8", errors="replace")
        if previous_patch_path is not None and previous_patch_path.exists()
        else None
    )

    if previous_text is None:
        return {
            "task_id": task_id,
            "attempt_no": attempt_no,
            "status": "first_attempt",
            "current_recipe": current_plan.selected_recipe,
            "current_patch_hash": current_signature["hash"],
            "current_changed_line_count": current_signature["changed_line_count"],
            "summary": "首轮尝试，无上一轮补丁可比较",
        }

    previous_signature = _patch_signature(previous_text)
    similarity = _jaccard_similarity(
        set(current_signature["meaningful_lines"]),
        set(previous_signature["meaningful_lines"]),
    )
    same_patch = current_signature["hash"] == previous_signature["hash"]
    ineffective = same_patch or similarity >= 0.98
    status = "ineffective_retry" if ineffective else "effective_retry"
    summary = (
        "本轮 recipe 发生变化，但 rewritten.patch 与上一轮基本一致"
        if ineffective
        else "本轮 rewritten.patch 相比上一轮已有可观变化"
    )

    return {
        "task_id": task_id,
        "attempt_no": attempt_no,
        "status": status,
        "previous_attempt_no": int(previous_attempt_dir.name) if previous_attempt_dir and previous_attempt_dir.name.isdigit() else None,
        "current_recipe": current_plan.selected_recipe,
        "previous_recipe": previous_plan.get("selected_recipe"),
        "current_patch_hash": current_signature["hash"],
        "previous_patch_hash": previous_signature["hash"],
        "current_changed_line_count": current_signature["changed_line_count"],
        "previous_changed_line_count": previous_signature["changed_line_count"],
        "changed_line_similarity": round(similarity, 4),
        "summary": summary,
        "current_patch_path": relativize_payload(current_patch_path, project_root),
        "previous_patch_path": relativize_payload(previous_patch_path, project_root),
    }


def write_route_effectiveness_report(*, report: dict[str, Any], path: Path, project_root: Path) -> Path:
    """写出路线有效性检查报告"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(relativize_payload(report, project_root), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _read_previous_plan(previous_attempt_dir: Path | None) -> dict[str, Any]:
    """读取上一轮 rewrite_plan"""

    if previous_attempt_dir is None:
        return {}
    path = previous_attempt_dir / "rewrite" / "rewrite_plan.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _patch_signature(text: str) -> dict[str, Any]:
    """生成用于比较的 patch 签名"""

    normalized_text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    meaningful_lines = [
        line.strip()
        for line in normalized_text.splitlines()
        if (line.startswith("+") or line.startswith("-"))
        and not line.startswith("+++")
        and not line.startswith("---")
        and line.strip()
    ]
    digest_source = "\n".join(meaningful_lines) or normalized_text
    return {
        "hash": hashlib.sha256(digest_source.encode("utf-8")).hexdigest(),
        "changed_line_count": len(meaningful_lines),
        "meaningful_lines": meaningful_lines,
    }


def _jaccard_similarity(left: set[str], right: set[str]) -> float:
    """计算两组变更行的 Jaccard 相似度"""

    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)
