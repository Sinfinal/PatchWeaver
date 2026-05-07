from __future__ import annotations

from types import SimpleNamespace

from patchweaver.builder.failure_classifier import FailureClassifier
from patchweaver.coordinator.services import AttemptExecutionService
from patchweaver.models.attempt import AttemptRecord, FailureRecord
from patchweaver.models.rewrite import ApplyPrecheckReport


def test_attempt_service_backfills_patch_apply_diagnostics() -> None:
    service = AttemptExecutionService.__new__(AttemptExecutionService)
    service.failure_classifier = FailureClassifier()
    record = FailureRecord(
        task_id="TASK-PATCH-APPLY-DIAG",
        attempt_id="TASK-PATCH-APPLY-DIAG-A001",
        stage_name="build",
        failure_type="patch_apply_failed",
        summary="apply 级预检查未通过",
        diagnostic_details={"route_effectiveness": {"status": "first_attempt"}},
    )
    build_log = "\n".join(
        [
            "构建阶段已跳过",
            "原因: apply 预检查未通过",
            "error: patch failed: fs/btrfs/disk-io.c:1553",
            "error: fs/btrfs/disk-io.c: patch does not apply",
        ]
    )

    updated = service._ensure_failure_specific_diagnostics(
        failure_record=record,
        build_log=build_log,
    )

    details = updated.diagnostic_details
    assert "route_effectiveness" in details
    assert details["patch_apply"]["subtype"] == "context_mismatch"
    assert details["patch_apply"]["stable_source_alignment_required"] is True
    assert details["agent_next_action"]["action"] == "prepare_unpatched_stable_source_baseline"


def test_attempt_service_attach_diagnostics_backfills_before_persist() -> None:
    service = AttemptExecutionService.__new__(AttemptExecutionService)
    service.failure_classifier = FailureClassifier()
    record = FailureRecord(
        task_id="TASK-PATCH-APPLY-ATTACH",
        attempt_id="TASK-PATCH-APPLY-ATTACH-A001",
        stage_name="build",
        failure_type="patch_apply_failed",
        summary="apply 级预检查未通过",
        diagnostic_details={},
    )
    build_log = "\n".join(
        [
            "构建阶段已跳过",
            "原因: apply 预检查未通过",
            "error: patch failed: fs/btrfs/disk-io.c:1553",
            "error: fs/btrfs/disk-io.c: patch does not apply",
        ]
    )

    updated = service._attach_attempt_diagnostics(
        failure_record=record,
        route_effectiveness={"status": "first_attempt"},
        section_change_report_path=None,
        build_log=build_log,
    )

    details = updated.diagnostic_details
    assert details["route_effectiveness"]["status"] == "first_attempt"
    assert details["patch_apply"]["subtype"] == "context_mismatch"
    assert details["patch_apply"]["stable_source_alignment_required"] is True
    assert details["agent_next_action"]["action"] == "prepare_unpatched_stable_source_baseline"


def test_attempt_service_allows_builder_retry_for_patch_apply_failed() -> None:
    service = AttemptExecutionService.__new__(AttemptExecutionService)
    service.build_config = SimpleNamespace(auto_switch_source_tree=True, auto_reverse_source_tree=True)
    report = ApplyPrecheckReport(
        status="failed",
        ok=False,
        backend="local",
        summary="本地 apply 预检查未通过，补丁当前无法应用到目标源码树",
        failure_type="patch_apply_failed",
        build_exec_status="not_run",
    )

    assert service._should_retry_apply_failure_in_builder(report) is True


def test_attempt_service_suggests_build_cache_prepare_action() -> None:
    service = AttemptExecutionService.__new__(AttemptExecutionService)
    record = FailureRecord(
        task_id="TASK-BUILD-CACHE",
        attempt_id="TASK-BUILD-CACHE-A001",
        stage_name="build",
        failure_type="build_cache_incomplete",
        summary="源码树缺少模块构建缓存，已跳过 kpatch-build",
        diagnostic_details={},
    )

    action = service._derive_agent_next_action(
        failure_record=record,
        diagnostic_details={},
    )

    assert action["action"] == "prepare_stable_build_cache"
    assert action["retry_scope"] == "build_cache"


def test_attempt_service_suggests_vendor_check_for_symbol_bundle_constraint() -> None:
    service = AttemptExecutionService.__new__(AttemptExecutionService)
    failure_record = FailureRecord(
        task_id="TASK-SYMBOL",
        attempt_id="TASK-SYMBOL-A001",
        stage_name="build",
        failure_type="kpatch_symbol_bundle_constraint",
        summary="disk-io.o: kpatch_bundle_symbols offset mismatch",
    )

    action = service._derive_agent_next_action(
        failure_record=failure_record,
        diagnostic_details={
            "kpatch_constraint": {
                "constraint_kind": "symbol_bundle_offset",
            }
        },
    )

    assert action["action"] == "check_vendor_baseline_then_section_symbol_rewrite"
    assert action["retry_scope"] == "source_baseline_then_rewrite_strategy"
    assert action["retryable_after_environment_update"] is True
    assert action["retryable_after_environment_update"] is True


def test_attempt_service_does_not_mark_unresolved_for_ineffective_retry(tmp_path) -> None:
    service = AttemptExecutionService.__new__(AttemptExecutionService)
    task = SimpleNamespace(task_id="TASK-INEFFECTIVE", max_attempts=2)
    attempt_record = AttemptRecord(
        task_id="TASK-INEFFECTIVE",
        attempt_no=2,
        attempt_id="TASK-INEFFECTIVE-A002",
        status="failed",
        failure_type="kpatch_constraint",
    )
    failure_record = FailureRecord(
        task_id="TASK-INEFFECTIVE",
        attempt_id=attempt_record.attempt_id,
        stage_name="build",
        failure_type="kpatch_constraint",
        summary="ioctl.o: 1 unsupported section change(s)",
        diagnostic_details={"kpatch_constraint": {"constraint_kind": "unsupported_section_change"}},
    )

    updated_attempt, updated_summary, updated_failure = service._maybe_mark_unresolved_kpatch_constraint(
        task=task,
        task_dir=tmp_path,
        attempt_record=attempt_record,
        build_summary=None,
        failure_record=failure_record,
        route_effectiveness={
            "status": "ineffective_retry",
            "summary": "recipe 变化但 rewritten.patch 与上一轮一致",
        },
    )

    assert updated_attempt.failure_type == "kpatch_constraint"
    assert updated_summary is None
    assert updated_failure.failure_type == "kpatch_constraint"
    assert updated_failure.diagnostic_details["unresolved_decision"]["status"] == "deferred_by_ineffective_retry"
