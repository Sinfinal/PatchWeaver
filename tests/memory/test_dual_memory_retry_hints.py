from __future__ import annotations

from patchweaver.memory.dual_memory import DualMemory
from patchweaver.models.attempt import AttemptRecord, FailureRecord
from patchweaver.models.rewrite import RewritePlan
from patchweaver.models.task import TaskContext


def test_dual_memory_emits_retry_hints_for_task_kpatch_constraint(tmp_path) -> None:
    memory = DualMemory(tmp_path / "memory")
    task = TaskContext(
        task_id="TASK-RETRY-HINT",
        cve_id="CVE-TEST-RETRY",
        target_kernel="6.6.102-5.2.an23.x86_64",
        max_attempts=3,
        workspace_dir=tmp_path / "workspaces" / "TASK-RETRY-HINT",
    )
    plan = RewritePlan(
        task_id=task.task_id,
        plan_id="TASK-RETRY-HINT-plan-001",
        selected_recipe="direct_apply_patch",
        selected_primitives=["direct_apply"],
        rule_hits=["static_local_change"],
    )
    attempt = AttemptRecord(
        task_id=task.task_id,
        attempt_no=1,
        attempt_id="TASK-RETRY-HINT-A001",
        status="failed",
        failure_type="kpatch_constraint",
    )
    failure = FailureRecord(
        task_id=task.task_id,
        attempt_id=attempt.attempt_id,
        stage_name="build",
        failure_type="kpatch_constraint",
        summary="nf_tables_api.o: 1 unsupported section change(s)",
        evidence=["nf_tables_api.o: 1 unsupported section change(s)"],
    )

    memory.record_attempt(task=task, plan=plan, attempt=attempt, failure_record=failure)
    hints = memory.build_ranking_hints(task_id=task.task_id, risk_types=["static_local_change"])

    assert hints["avoid_recipes"]["direct_apply_patch"] == failure.summary
    assert "section_change_avoidance_rewrite" in hints["boost_recipes"]
    assert "section_change_avoidance_rewrite" in hints["extra_candidate_routes"]
    assert "smpl_primary_rewrite" in hints["boost_recipes"]
    assert "state_preserving_wrap" in hints["extra_candidate_routes"]
    assert "shadow_variable_wrap" in hints["extra_candidate_routes"]
