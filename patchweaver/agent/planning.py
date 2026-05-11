"""Translate Agent decisions into planner ranking hints."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from patchweaver.utils.path_policy import to_project_relative

_REQUIREMENT_ROUTE_MAP: dict[str, tuple[str, str]] = {
    "section_change_avoidance": (
        "section_change_avoidance_rewrite",
        "AgentDecision 要求避开 section change 约束，优先收缩全局和初始化类 hunk",
    ),
    "semantic_guard_rewrite": (
        "semantic_guard_rewrite",
        "AgentDecision 要求尝试函数局部 guard 等价改写",
    ),
    "smpl_primary": (
        "smpl_primary_rewrite",
        "AgentDecision 要求优先采用结构化 SmPL 改写缩小编辑半径",
    ),
    "callback_or_shadow_state_strategy": (
        "callback_shadow_wrap",
        "AgentDecision 要求切换 callback/shadow 状态保持路线",
    ),
}


def merge_agent_policy_hints(
    *,
    base_hints: dict[str, object] | None,
    task_dir: Path,
    attempt_no: int,
    project_root: Path | None = None,
) -> dict[str, object]:
    """Merge the latest AgentDecision into planner ranking hints.

    The planner already understands avoid/boost/extra route hints. This helper keeps
    Agent policy output as the source of truth instead of adding a second planner.
    """

    hints: dict[str, object] = copy.deepcopy(base_hints or {})
    trace_path = task_dir / "agent" / "agent_workflow_trace.json"
    trace_payload = _read_json(trace_path)
    decision = _latest_decision(trace_payload)
    if decision is None:
        return hints

    reason = str(decision.get("reason") or "AgentDecision 未提供原因")
    selected_action = str(decision.get("selected_action") or "")
    terminal = bool(decision.get("terminal"))
    requirements = [str(item) for item in list(decision.get("strategy_requirements") or []) if str(item)]
    disabled = [str(item) for item in list(decision.get("disabled_strategies") or []) if str(item)]

    agent_policy = _dict_value(hints, "agent_policy")
    agent_policy.update(
        {
            "selected_action": selected_action,
            "reason": reason,
            "terminal": terminal,
            "strategy_requirements": requirements,
            "disabled_strategies": disabled,
            "source_trace_path": to_project_relative(project_root, trace_path),
        }
    )
    hints["agent_policy"] = agent_policy

    if terminal:
        hints["terminal_stop_reason"] = reason
        return hints

    avoid_recipes = _dict_value(hints, "avoid_recipes")
    boost_recipes = _dict_value(hints, "boost_recipes")
    extra_candidate_routes = _list_value(hints, "extra_candidate_routes")
    previous_recipe = _previous_recipe(task_dir=task_dir, attempt_no=attempt_no)

    for recipe in disabled:
        avoid_recipes.setdefault(recipe, f"AgentDecision 禁用上一轮策略: {reason}")
    if previous_recipe and any(item in requirements for item in {"alternative_recipe", "select_distinct_recipe", "patch_shape_must_change"}):
        avoid_recipes.setdefault(previous_recipe, f"AgentDecision 要求下一轮选择不同 recipe: {reason}")

    for requirement in requirements:
        route = _REQUIREMENT_ROUTE_MAP.get(requirement)
        if route is None:
            continue
        route_name, route_reason = route
        boost_recipes.setdefault(route_name, route_reason)
        if route_name not in extra_candidate_routes:
            extra_candidate_routes.append(route_name)

    if "stable_source_baseline" in requirements:
        hints["stable_source_alignment_required"] = True
        hints["source_alignment_actions"] = list(
            dict.fromkeys(
                _list_value(hints, "source_alignment_actions")
                + ["prepare_stable_source_baseline", "reverse_unpatch", "context_adapter"]
            )
        )
    if "config_repair_required" in requirements:
        hints["config_repair_required"] = True

    hints["avoid_recipes"] = avoid_recipes
    hints["boost_recipes"] = boost_recipes
    hints["extra_candidate_routes"] = extra_candidate_routes
    return hints


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _latest_decision(trace_payload: dict[str, Any]) -> dict[str, Any] | None:
    decisions = trace_payload.get("decisions")
    if not isinstance(decisions, list) or not decisions:
        return None
    latest = decisions[-1]
    return latest if isinstance(latest, dict) else None


def _previous_recipe(*, task_dir: Path, attempt_no: int) -> str | None:
    if attempt_no <= 1:
        return None
    payload = _read_json(task_dir / "attempts" / f"{attempt_no - 1:03d}" / "rewrite" / "rewrite_plan.json")
    value = payload.get("selected_recipe")
    return str(value) if value else None


def _dict_value(payload: dict[str, object], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return dict(value) if isinstance(value, dict) else {}


def _list_value(payload: dict[str, object], key: str) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]
