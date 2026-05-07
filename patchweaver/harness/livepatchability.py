"""Livepatch-first candidate scoring"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

LOW_RISK_ROUTES = {"direct_apply_patch", "minimal_livepatch_wrap"}
KPATCH_CONSTRAINT_RISKS = {"kpatch_constraint", "unsupported_section_change", "section_mismatch", "fentry_constraint"}


def analyze_patch_shape(patch_text: str) -> dict[str, Any]:
    """Extract livepatch-relevant shape signals from a unified diff"""

    normalized = patch_text.replace("\r\n", "\n").replace("\r", "\n")
    touched_files: list[str] = []
    touched_functions: list[str] = []
    changed_lines: list[str] = []
    added_lines: list[str] = []
    removed_lines: list[str] = []
    risky_markers: list[str] = []
    current_file: str | None = None

    for raw_line in normalized.splitlines():
        if raw_line.startswith("diff --git "):
            parts = raw_line.split()
            current_file = _normalize_diff_path(parts[3]) if len(parts) >= 4 else None
            if current_file:
                _append_unique(touched_files, current_file)
            continue
        if raw_line.startswith("+++ "):
            path = _normalize_diff_path(raw_line[4:].strip())
            if path:
                current_file = path
                _append_unique(touched_files, path)
            continue
        if raw_line.startswith("@@"):
            function_name = _extract_hunk_function(_hunk_header_tail(raw_line))
            if function_name:
                _append_unique(touched_functions, function_name)
            continue
        if raw_line.startswith(("+++", "---")):
            continue
        if raw_line.startswith("+") or raw_line.startswith("-"):
            line = raw_line[1:].strip()
            if not line:
                continue
            changed_lines.append(line)
            if raw_line.startswith("+"):
                added_lines.append(line)
            else:
                removed_lines.append(line)
            risky_markers.extend(_line_risk_markers(line=line, current_file=current_file))

    path_markers = _path_risk_markers(touched_files)
    risky_markers.extend(path_markers)
    risky_markers = list(dict.fromkeys(risky_markers))
    return {
        "touched_files": touched_files,
        "touched_file_count": len(touched_files),
        "touched_functions": touched_functions,
        "touched_function_count": len(touched_functions),
        "changed_line_count": len(changed_lines),
        "added_line_count": len(added_lines),
        "removed_line_count": len(removed_lines),
        "guard_like": _looks_guard_like(added_lines),
        "touches_kbuild": "kbuild_or_makefile_change" in risky_markers,
        "touches_header": "header_change" in risky_markers,
        "touches_init_or_probe": "init_probe_remove_exit_path" in risky_markers,
        "touches_global_or_static_data": "global_or_static_data_change" in risky_markers,
        "touches_struct_definition": "struct_or_type_definition_change" in risky_markers,
        "risk_markers": risky_markers,
    }


def score_livepatchability(record: dict[str, Any]) -> dict[str, Any]:
    """Score whether a CVE should be promoted to expensive full livepatch runs"""

    score = 50
    boosts: list[str] = []
    penalties: list[str] = []
    shape = record.get("patch_shape") if isinstance(record.get("patch_shape"), dict) else {}
    target_infos = record.get("build_target_details") or record.get("inferred_build_target_details") or []
    targets = [str(item) for item in record.get("inferred_build_targets") or []]
    states = [str(item) for item in record.get("build_target_states") or []]

    module_targets = [target for target in targets if target.endswith(".ko")]
    vmlinux_target = bool(record.get("vmlinux_target_candidate")) or "vmlinux" in targets
    disabled_target = "disabled" in states
    selected_route = str(record.get("selected_route") or record.get("preferred_route") or "")
    high_risk_count = int(record.get("high_risk_count") or 0)
    dominant_risks = {str(item) for item in record.get("dominant_risk_types") or []}

    if module_targets:
        score += 25
        boosts.append("目标能映射到具体 .ko 模块")
        if len(set(module_targets)) == 1:
            score += 8
            boosts.append("只涉及 1 个模块目标")
    else:
        score -= 30
        penalties.append("未能映射到具体 .ko 模块")

    if vmlinux_target:
        score -= 25
        penalties.append("目标落到 vmlinux 或未知内建路径")
    if disabled_target:
        score -= 35
        penalties.append("当前 .config 未启用目标源码")

    changed_line_count = int(shape.get("changed_line_count") or 0)
    if 1 <= changed_line_count <= 20:
        score += 15
        boosts.append("patch 变更行数在 1 到 20 行")
    elif changed_line_count <= 50:
        score += 5
        boosts.append("patch 变更行数仍处于中等范围")
    else:
        score -= 20
        penalties.append("patch 变更行数偏多")

    touched_file_count = int(shape.get("touched_file_count") or len(record.get("target_files") or []))
    if touched_file_count == 1:
        score += 10
        boosts.append("只触达 1 个源码文件")
    elif touched_file_count > 1:
        penalty = min(25, (touched_file_count - 1) * 8)
        score -= penalty
        penalties.append(f"触达 {touched_file_count} 个源码文件")

    touched_function_count = int(shape.get("touched_function_count") or int(record.get("target_function_count") or 0))
    if 1 <= touched_function_count <= 2:
        score += 10
        boosts.append("只触达 1 到 2 个函数")
    elif touched_function_count == 0:
        score -= 8
        penalties.append("未能从 hunk header 识别函数")
    else:
        score -= min(25, (touched_function_count - 2) * 8)
        penalties.append(f"触达 {touched_function_count} 个函数")

    if selected_route in LOW_RISK_ROUTES and high_risk_count == 0:
        score += 12
        boosts.append("约束诊断给出低风险路线")
    else:
        score -= min(25, high_risk_count * 8 + (0 if selected_route in LOW_RISK_ROUTES else 10))
        penalties.append("约束诊断不是纯低风险路线")

    if dominant_risks & KPATCH_CONSTRAINT_RISKS:
        score -= 20
        penalties.append("已出现 kpatch 后端约束风险")

    risk_markers = set(str(item) for item in shape.get("risk_markers") or [])
    marker_penalties = {
        "kbuild_or_makefile_change": 35,
        "init_probe_remove_exit_path": 25,
        "global_or_static_data_change": 25,
        "struct_or_type_definition_change": 30,
        "header_change": 15,
        "module_export_or_section_marker": 30,
    }
    marker_labels = {
        "kbuild_or_makefile_change": "修改 Kconfig/Makefile/Kbuild",
        "init_probe_remove_exit_path": "触达 __init/probe/remove/exit 路径",
        "global_or_static_data_change": "修改静态表或全局数据",
        "struct_or_type_definition_change": "修改结构体或类型定义",
        "header_change": "修改头文件",
        "module_export_or_section_marker": "修改导出符号或 section 相关宏",
    }
    for marker, penalty in marker_penalties.items():
        if marker in risk_markers:
            score -= penalty
            penalties.append(marker_labels[marker])

    if shape.get("guard_like") and not {"kbuild_or_makefile_change", "struct_or_type_definition_change"} & risk_markers:
        score += 10
        boosts.append("新增逻辑像函数局部 guard")

    score = max(0, min(100, score))
    tier = "high" if score >= 75 else "medium" if score >= 50 else "low"
    full_run_recommended = (
        tier == "high"
        and bool(module_targets)
        and not disabled_target
        and not vmlinux_target
        and "kbuild_or_makefile_change" not in risk_markers
        and "struct_or_type_definition_change" not in risk_markers
    )
    return {
        "score": score,
        "tier": tier,
        "full_run_recommended": full_run_recommended,
        "boosts": boosts[:12],
        "penalties": penalties[:12],
        "shape": shape,
    }


def classify_kpatch_constraint_rewrite(record: dict[str, Any]) -> dict[str, Any]:
    """Split kpatch constraints into guardable, callback/shadow and unfixable candidates"""

    shape = record.get("patch_shape") if isinstance(record.get("patch_shape"), dict) else {}
    risk_markers = set(str(item) for item in shape.get("risk_markers") or [])
    guard_like = bool(shape.get("guard_like"))
    changed_line_count = int(shape.get("changed_line_count") or 0)
    touched_function_count = int(shape.get("touched_function_count") or 0)

    if guard_like and changed_line_count <= 30 and touched_function_count <= 2 and not (
        {"kbuild_or_makefile_change", "struct_or_type_definition_change", "global_or_static_data_change"} & risk_markers
    ):
        return {
            "class": "rewritable_by_semantic_guard",
            "next_strategy": "semantic_guard_rewrite",
            "reason": "补丁形态接近函数局部条件保护，优先尝试等价 guard 收缩",
        }
    if {"global_or_static_data_change", "struct_or_type_definition_change"} & risk_markers:
        return {
            "class": "requires_callback_or_shadow",
            "next_strategy": "callback_or_shadow_state_strategy",
            "reason": "补丁触达数据状态或类型定义，普通函数局部 guard 不足以表达语义",
        }
    return {
        "class": "unfixable_by_livepatch_candidate",
        "next_strategy": "mark_unfixable_after_repeated_constraint",
        "reason": "补丁形态不适合继续盲目收缩，若多轮仍命中同一后端约束应收口",
    }


def apply_livepatchability_gate(
    records: list[dict[str, Any]],
    *,
    min_score: int = 75,
    only_high: bool = False,
) -> list[dict[str, Any]]:
    """Attach score and optionally gate positive candidates before full run"""

    for record in records:
        result = score_livepatchability(record)
        if record.get("known_pool_hit") == "kpatch_constraint_pool":
            result = {
                **result,
                "score": min(int(result.get("score") or 0), 40),
                "tier": "low",
                "full_run_recommended": False,
                "penalties": [
                    "已在 kpatch_constraint 专项池中确认，正向扩池时不再推进",
                    *list(result.get("penalties") or []),
                ][:12],
            }
        record["livepatchability"] = result
        record["livepatchability_score"] = result["score"]
        record["livepatchability_tier"] = result["tier"]
        if record.get("failure_type") in {"kpatch_constraint", "kpatch_constraint_unresolved"}:
            record["kpatch_constraint_rewrite_class"] = classify_kpatch_constraint_rewrite(record)
        if not only_high:
            continue
        if not record.get("positive_pool_candidate"):
            continue
        if result["score"] >= min_score and result["full_run_recommended"]:
            record["screening_tier"] = "positive_candidate_livepatchability_high"
            record["reason"] = "livepatchability-first 打分通过，允许进入 full run"
            continue
        record.update(
            {
                "sample_bucket": None,
                "acceptance_role": "deferred_sample",
                "screening_tier": "deferred_livepatchability_low_score",
                "reason": "livepatchability-first 打分不足，暂不推进昂贵 full run",
                "stable_bucket_ready": False,
                "positive_pool_candidate": False,
            }
        )
    return records


def load_patch_shape(path: Path) -> dict[str, Any]:
    """Read a patch file and return patch shape"""

    if not path.exists():
        return {}
    return analyze_patch_shape(path.read_text(encoding="utf-8", errors="replace"))


def _normalize_diff_path(raw_path: str) -> str | None:
    path = raw_path.strip()
    if not path or path == "/dev/null":
        return None
    if path.startswith("a/") or path.startswith("b/"):
        path = path[2:]
    return path


def _append_unique(items: list[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def _hunk_header_tail(line: str) -> str:
    parts = line.split("@@")
    return parts[-1].strip() if len(parts) >= 3 else ""


def _extract_hunk_function(section_header: str) -> str | None:
    header = section_header.strip()
    if not header:
        return None
    match = re.search(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(", header)
    if not match:
        return header[:120]
    name = match.group(1)
    if name in {"if", "for", "while", "switch", "return", "sizeof"}:
        return header[:120]
    return name


def _path_risk_markers(paths: list[str]) -> list[str]:
    markers: list[str] = []
    for raw_path in paths:
        path = raw_path.replace("\\", "/")
        name = Path(path).name
        if name in {"Kconfig", "Makefile", "Kbuild"}:
            markers.append("kbuild_or_makefile_change")
        if path.endswith(".h"):
            markers.append("header_change")
    return markers


def _line_risk_markers(*, line: str, current_file: str | None) -> list[str]:
    markers: list[str] = []
    stripped = line.strip()
    lowered = stripped.lower()
    if current_file and Path(current_file).name in {"Kconfig", "Makefile", "Kbuild"}:
        markers.append("kbuild_or_makefile_change")
    if any(token in lowered for token in ["__init", "__exit", ".init.", ".exit."]):
        markers.append("init_probe_remove_exit_path")
    if re.search(r"\b(probe|remove|exit|init)\s*\(", stripped):
        markers.append("init_probe_remove_exit_path")
    if stripped.startswith(("#define", "EXPORT_SYMBOL", "MODULE_")) or "export_symbol" in lowered:
        markers.append("module_export_or_section_marker")
    if re.match(r"^(typedef\s+)?(struct|enum|union)\s+\w+", stripped):
        markers.append("struct_or_type_definition_change")
    if re.match(r"^static\s+(?!inline\b).*(=|;|\[)", stripped):
        markers.append("global_or_static_data_change")
    if re.match(r"^(const\s+)?struct\s+\w+\s+\w+\s*(=|\[)", stripped):
        markers.append("global_or_static_data_change")
    return markers


def _looks_guard_like(added_lines: list[str]) -> bool:
    joined = "\n".join(added_lines)
    has_condition = any(re.search(r"\bif\s*\(", line) for line in added_lines)
    has_guard_exit = any(
        token in joined
        for token in [
            "return ",
            "goto ",
            "break;",
            "continue;",
            "-EINVAL",
            "-ENOMEM",
            "-EFAULT",
            "NULL",
        ]
    )
    has_bounds_or_null = any(token in joined.lower() for token in ["null", "size", "len", "bound", "overflow", "invalid"])
    return has_condition and (has_guard_exit or has_bounds_or_null)
