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
    assert any("构建命令超时" in item for item in record.evidence)
    assert all("patch failed" not in item for item in record.evidence)


def test_classify_build_log_marks_feature_not_enabled_when_kernel_config_skips_target() -> None:
    classifier = FailureClassifier()
    build_log = "\n".join(
        [
            "[apply precheck]",
            "apply 级预检查通过。",
            "[build target coverage]",
            "目标内核配置未启用以下源码: security/tomoyo/common.c",
            "当前样例在该验证内核上不会编译出对应对象，已跳过 kpatch-build",
        ]
    )

    record = classifier.classify_build_log(
        task_id="TASK-TEST-FAILURE-FEATURE-DISABLED",
        attempt_id="TASK-TEST-FAILURE-FEATURE-DISABLED-A001",
        build_log=build_log,
        build_exec_status="not_run",
        failure_type_hint="feature_not_enabled",
    )

    assert record.failure_type == "feature_not_enabled"
    assert "未启用以下源码" in record.summary
    assert any("security/tomoyo/common.c" in item for item in record.evidence)
