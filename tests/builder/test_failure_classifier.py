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


def test_classify_build_log_marks_build_cache_incomplete_before_kpatch_build() -> None:
    classifier = FailureClassifier()
    build_log = "\n".join(
        [
            "[apply precheck]",
            "apply 级预检查通过。",
            "[build targets]",
            "drivers/scsi/smartpqi/smartpqi.ko",
            "[build cache]",
            "模块构建目标需要完整 prepared source tree 缓存",
            "缺失文件: vmlinux.o, vmlinux.a, .vmlinux.objs",
            "处理方式: 先执行 prepare-build-tree --warm-target vmlinux 或同步已预热源码树",
            "源码树缺少模块构建缓存，已跳过 kpatch-build。",
        ]
    )

    record = classifier.classify_build_log(
        task_id="TASK-TEST-BUILD-CACHE",
        attempt_id="TASK-TEST-BUILD-CACHE-A001",
        build_log=build_log,
        build_exec_status="not_run",
        failure_type_hint="build_cache_incomplete",
    )

    assert record.failure_type == "build_cache_incomplete"
    assert "缺失文件" in record.summary or "源码树缺少模块构建缓存" in record.summary
    assert any("prepare-build-tree" in item for item in record.evidence)


def test_classify_build_log_marks_unsupported_section_change_as_kpatch_constraint() -> None:
    classifier = FailureClassifier()
    build_log = "\n".join(
        [
            "[local command]",
            "/usr/bin/kpatch-build ...",
            "[stderr]",
            "nf_tables_api.o: 1 unsupported section change(s)",
            "ERROR: kpatch build failed. Check /root/.kpatch/build.log for more details.",
            "退出码: 1",
        ]
    )

    record = classifier.classify_build_log(
        task_id="TASK-TEST-UNSUPPORTED-SECTION",
        attempt_id="TASK-TEST-UNSUPPORTED-SECTION-A001",
        build_log=build_log,
        build_exec_status="executed",
        failure_type_hint="compile_failed",
    )

    assert record.failure_type == "kpatch_constraint"
    assert record.summary == "nf_tables_api.o: 1 unsupported section change(s)"
    assert any("unsupported section change" in item for item in record.evidence)


def test_classify_build_log_marks_rela_call_sites_as_kpatch_constraint() -> None:
    classifier = FailureClassifier()
    build_log = "\n".join(
        [
            "[local command]",
            "/usr/bin/kpatch-build ...",
            "[stderr]",
            "ERROR: .rela.call_sites changed in target object",
            "ERROR: kpatch build failed. Check /root/.kpatch/build.log for more details.",
        ]
    )

    record = classifier.classify_build_log(
        task_id="TASK-TEST-RELA-CALL-SITES",
        attempt_id="TASK-TEST-RELA-CALL-SITES-A001",
        build_log=build_log,
        build_exec_status="executed",
        failure_type_hint="compile_failed",
    )

    assert record.failure_type == "kpatch_constraint"
    assert record.diagnostic_details["kpatch_constraint"]["constraint_kind"] == "rela_call_sites"


def test_classify_build_log_marks_symbol_bundle_offset_constraint(tmp_path) -> None:
    patch_path = tmp_path / "rewritten.patch"
    patch_path.write_text(
        "\n".join(
            [
                "diff --git a/fs/btrfs/disk-io.c b/fs/btrfs/disk-io.c",
                "--- a/fs/btrfs/disk-io.c",
                "+++ b/fs/btrfs/disk-io.c",
                "@@ -1550,6 +1550,8 @@ static int btrfs_init_fs_root(struct btrfs_root *root)",
                "+\tif (!root)",
                "+\t\treturn -EINVAL;",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    classifier = FailureClassifier()
    build_log = "\n".join(
        [
            "[local command]",
            "/usr/bin/kpatch-build ...",
            "[stdout]",
            "create-diff-object: ERROR: disk-io.o: kpatch_bundle_symbols: 260: symbol btrfs_global_root_id at offset 16 within section .text.btrfs_global_root_id, expected 0: Success",
        ]
    )

    record = classifier.classify_build_log(
        task_id="TASK-TEST-SYMBOL-BUNDLE",
        attempt_id="TASK-TEST-SYMBOL-BUNDLE-A001",
        build_log=build_log,
        build_exec_status="executed",
        failure_type_hint="compile_failed",
        rewritten_patch_path=patch_path,
    )

    assert record.failure_type == "kpatch_symbol_bundle_constraint"
    details = record.diagnostic_details["kpatch_constraint"]
    assert details["constraint_kind"] == "symbol_bundle_offset"
    assert details["object_file"] == "disk-io.o"
    assert details["source_files"] == ["fs/btrfs/disk-io.c"]
    assert details["functions"] == ["btrfs_init_fs_root"]
    assert details["symbol_bundle"]["object_file"] == "disk-io.o"
    assert details["symbol_bundle"]["symbol"] == "btrfs_global_root_id"
    assert details["symbol_bundle"]["offset"] == 16
    assert details["symbol_bundle"]["source_files"] == ["fs/btrfs/disk-io.c"]
    assert details["symbol_bundle"]["functions"] == ["btrfs_init_fs_root"]


def test_classify_build_log_locates_section_change_source_and_function(tmp_path) -> None:
    patch_path = tmp_path / "rewritten.patch"
    patch_path.write_text(
        "\n".join(
            [
                "diff --git a/net/netfilter/nf_tables_api.c b/net/netfilter/nf_tables_api.c",
                "--- a/net/netfilter/nf_tables_api.c",
                "+++ b/net/netfilter/nf_tables_api.c",
                "@@ -100,7 +100,7 @@ static int nf_tables_newrule(struct net *net)",
                "-\treturn -EINVAL;",
                "+\treturn nft_validate_register_load(ctx);",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    classifier = FailureClassifier()
    build_log = "\n".join(
        [
            "[local command]",
            "/usr/bin/kpatch-build ...",
            "[stderr]",
            "ERROR: nf_tables_api.o: 1 unsupported section change(s)",
        ]
    )

    record = classifier.classify_build_log(
        task_id="TASK-TEST-SECTION-DETAIL",
        attempt_id="TASK-TEST-SECTION-DETAIL-A001",
        build_log=build_log,
        build_exec_status="executed",
        failure_type_hint="compile_failed",
        rewritten_patch_path=patch_path,
    )

    details = record.diagnostic_details["kpatch_constraint"]
    assert details["constraint_kind"] == "unsupported_section_change"
    assert details["object_file"] == "nf_tables_api.o"
    assert details["source_files"] == ["net/netfilter/nf_tables_api.c"]
    assert details["functions"] == ["nf_tables_newrule"]
    assert details["section_change_count"] == 1
    assert details["section_changes"][0]["object_file"] == "nf_tables_api.o"
    assert details["section_changes"][0]["source_files"] == ["net/netfilter/nf_tables_api.c"]
    assert details["section_changes"][0]["functions"] == ["nf_tables_newrule"]
    assert details["rewrite_classification"]["next_strategy"] in {
        "semantic_guard_rewrite",
        "mark_unfixable_after_repeated_constraint",
    }


def test_classify_build_log_marks_target_arch_mismatch_before_kpatch_build() -> None:
    classifier = FailureClassifier()
    build_log = "\n".join(
        [
            "[apply precheck]",
            "apply 级预检查通过。",
            "[build target coverage]",
            "补丁触达目标架构之外的源码，已跳过本机构建。",
            "当前验证机内核架构: x86",
            "目标架构不匹配源码: arch/arm64/kernel/fpsimd.c",
            "当前样例不会在该验证内核上形成 changed objects，已跳过 kpatch-build",
        ]
    )

    record = classifier.classify_build_log(
        task_id="TASK-TEST-ARCH-MISMATCH",
        attempt_id="TASK-TEST-ARCH-MISMATCH-A001",
        build_log=build_log,
        build_exec_status="not_run",
        failure_type_hint="target_arch_mismatch",
    )

    assert record.failure_type == "target_arch_mismatch"
    assert "目标架构不匹配源码" in record.summary or "补丁触达目标架构之外" in record.summary
    assert any("arch/arm64/kernel/fpsimd.c" in item for item in record.evidence)


def test_classify_patch_apply_failed_includes_source_alignment_details() -> None:
    classifier = FailureClassifier()
    build_log = "\n".join(
        [
            "[apply precheck]",
            "源码期望状态: likely_patched",
            "补丁路径: /tmp/rewritten.patch",
            "[precheck stderr]",
            "Checking patch drivers/net/wireless/intel/iwlwifi/iwl-dbg-tlv.c...",
            "error: patch failed: drivers/net/wireless/intel/iwlwifi/iwl-dbg-tlv.c:876",
            "error: drivers/net/wireless/intel/iwlwifi/iwl-dbg-tlv.c: patch does not apply",
        ]
    )

    record = classifier.classify_build_log(
        task_id="TASK-TEST-APPLY-DETAIL",
        attempt_id="TASK-TEST-APPLY-DETAIL-A001",
        build_log=build_log,
        build_exec_status="not_run",
        failure_type_hint="patch_apply_failed",
    )

    details = record.diagnostic_details["patch_apply"]
    assert record.failure_type == "patch_apply_failed"
    assert details["subtype"] == "source_too_new_or_already_patched"
    assert details["source_state"] == "likely_patched"
    assert details["conflict_files"] == ["drivers/net/wireless/intel/iwlwifi/iwl-dbg-tlv.c"]
    assert details["conflict_hunks"] == [{"file": "drivers/net/wireless/intel/iwlwifi/iwl-dbg-tlv.c", "line": 876}]
    assert details["reverse_unpatch_recommended"] is True
    assert details["reverse_unpatch_attempted"] is False
    assert details["reverse_unpatch_status"] == "not_attempted"
    assert details["stable_source_baseline_action"] == "try_reverse_unpatch_or_switch_unpatched_source"


def test_classify_patch_apply_failed_marks_reverse_failure_as_source_alignment_required() -> None:
    classifier = FailureClassifier()
    build_log = "\n".join(
        [
            "[apply precheck]",
            "源码期望状态: likely_patched",
            "error: patch failed: drivers/net/netdevsim/dev.c:42",
            "[reverse source tree]",
            "反向源码树: /tmp/attempt/sources/reverse_unpatched",
            "反向检查命令: git apply --reverse --check rewritten.patch",
            "反向源码树生成失败: 当前补丁无法从已修复源码树回退",
        ]
    )

    record = classifier.classify_build_log(
        task_id="TASK-TEST-APPLY-REVERSE-FAILED",
        attempt_id="TASK-TEST-APPLY-REVERSE-FAILED-A001",
        build_log=build_log,
        build_exec_status="not_run",
        failure_type_hint="patch_apply_failed",
    )

    details = record.diagnostic_details["patch_apply"]
    assert details["subtype"] == "source_too_new_or_already_patched"
    assert details["reverse_unpatch_attempted"] is True
    assert details["reverse_unpatch_status"] == "failed"
    assert details["stable_source_alignment_required"] is True
    assert details["stable_source_baseline_action"] == "prepare_unpatched_stable_source_baseline"


def test_classify_patch_apply_failed_marks_missing_file() -> None:
    classifier = FailureClassifier()
    build_log = "\n".join(
        [
            "[precheck stderr]",
            "can't find file to patch at input line 12",
            "Perhaps you used the wrong -p or --strip option?",
        ]
    )

    record = classifier.classify_build_log(
        task_id="TASK-TEST-APPLY-MISSING",
        attempt_id="TASK-TEST-APPLY-MISSING-A001",
        build_log=build_log,
        build_exec_status="not_run",
        failure_type_hint="patch_apply_failed",
    )

    details = record.diagnostic_details["patch_apply"]
    assert details["subtype"] == "missing_file"
    assert details["stable_source_alignment_required"] is True
    assert details["stable_source_baseline_action"] == "align_to_stable_source_baseline"
