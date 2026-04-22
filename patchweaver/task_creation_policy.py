"""任务创建阶段的查重与提示策略"""

from __future__ import annotations

from typing import Any

from patchweaver.models.attempt import AttemptRecord
from patchweaver.models.task import MachineProfile, TaskContext


def build_duplicate_scope(
    *,
    cve_id: str,
    target_kernel: str,
    target_kernel_source: str | None,
    profile_name: str | None,
    machine_profile: MachineProfile | None = None,
) -> dict[str, Any]:
    """生成任务创建查重时使用的等价范围摘要"""

    return {
        "cve_id": cve_id,
        "target_kernel": target_kernel,
        "target_kernel_source": target_kernel_source,
        "profile_name": profile_name,
        "selected_source_dir": machine_profile.selected_source_dir if machine_profile is not None else None,
    }


def build_duplicate_task_notice(task: TaskContext, latest_attempt: AttemptRecord | None) -> dict[str, Any]:
    """根据现有任务状态生成统一的重复创建提示"""

    latest_status = latest_attempt.status if latest_attempt is not None else task.status
    latest_failure_type = latest_attempt.failure_type if latest_attempt is not None else None
    latest_target_state = latest_attempt.target_state if latest_attempt is not None else None

    if latest_target_state == "target_already_patched" or latest_failure_type == "target_already_patched" or task.status == "target_state":
        return {
            "reason": "target_already_patched",
            "decision": "skip_already_fixed",
            "message": "已存在同配置任务，最近结论为目标源码已包含修复，默认不重复创建任务。",
            "recommended_action": "若当前源码树已切换为未修复版本，可显式使用 force_new 重新创建任务；否则直接复用现有任务结论。",
            "next_steps": [
                "查看现有任务的 build_precheck、failure_record 和 report 结论。",
                "确认当前源码树是否仍处于已修复状态。",
                "只有在源码树已切换或需要保留新实验记录时才强制新建任务。",
            ],
        }

    if latest_status in {"created", "analyzed", "running"}:
        return {
            "reason": "task_in_progress",
            "decision": "resume_existing",
            "message": "已存在同配置任务且仍在执行链路中，默认不重复创建任务。",
            "recommended_action": "继续对现有任务执行 analyze、run、report 或通过控制面查看当前进度。",
            "next_steps": [
                "优先检查现有任务是否已经有分析结果或尝试轮结果。",
                "继续推进现有任务，而不是为同一输入创建平行任务。",
            ],
        }

    return {
        "reason": "same_task_exists",
        "decision": "reuse_existing",
        "message": "已存在同配置任务，默认不重复创建任务。",
        "recommended_action": "优先复用已有任务结果；只有在需要保留独立重跑记录时才强制新建任务。",
        "next_steps": [
            "先查看现有任务状态、失败归因和最近一轮构建结果。",
            "确认是否真的需要保留新的任务编号和独立工作区。",
        ],
    }
