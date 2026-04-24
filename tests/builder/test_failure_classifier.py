from __future__ import annotations

from patchweaver.builder.failure_classifier import FailureClassifier


def test_classify_build_log_prefers_executed_build_failure_over_target_state_history() -> None:
    classifier = FailureClassifier()
    build_log = "\n".join(
        [
            "[apply precheck]",
            "目标源码已包含该补丁，apply 预检查判定无需重复应用。",
            "目标态结论: target_already_patched",
            "[local command]",
            "/usr/bin/kpatch-build ...",
            "[stderr]",
            "KERNELVERSION is not set",
            "ERROR: kpatch build failed. Check /root/.kpatch/build.log for more details.",
            "退出码: 1",
        ]
    )

    record = classifier.classify_build_log(
        task_id="TASK-TEST-FAILURE-CLASSIFIER",
        attempt_id="TASK-TEST-FAILURE-CLASSIFIER-A001",
        build_log=build_log,
        build_exec_status="executed",
        failure_type_hint="compile_failed",
    )

    assert record.failure_type == "compile_failed"
    assert "KERNELVERSION is not set" in record.summary or "kpatch build failed" in record.summary
    assert any("KERNELVERSION is not set" in item for item in record.evidence)


def test_classify_build_log_prefers_timeout_summary_after_local_command() -> None:
    classifier = FailureClassifier()
    build_log = "\n".join(
        [
            "[apply precheck]",
            "目标源码已包含该补丁，apply 预检查判定无需重复应用。",
            "error: patch failed: net/netfilter/nf_tables_api.c:5062",
            "[local command]",
            "/usr/bin/kpatch-build ...",
            "构建命令超时：3600 秒。",
            "[stdout]",
            "Using source directory at /tmp/reverse_unpatched",
            "Building original source",
            "退出码: -1",
        ]
    )

    record = classifier.classify_build_log(
        task_id="TASK-TEST-FAILURE-CLASSIFIER-TIMEOUT",
        attempt_id="TASK-TEST-FAILURE-CLASSIFIER-TIMEOUT-A001",
        build_log=build_log,
        build_exec_status="executed",
        failure_type_hint="compile_failed",
    )

    assert record.failure_type == "compile_failed"
    assert record.summary == "构建命令超时：3600 秒。"
    assert all("patch failed" not in item for item in record.evidence)
