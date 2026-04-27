from __future__ import annotations

from pathlib import Path

from patchweaver.builder.orchestrator import BuildOrchestrator
from patchweaver.config.models import BuildConfig
from patchweaver.models.rewrite import RewritePlan
from patchweaver.models.task import TaskContext


def _write_kernel_tree(root: Path, *, file_body: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "Makefile").write_text("obj-y := demo.o\n", encoding="utf-8")
    (root / ".config").write_text("CONFIG_LIVEPATCH=y\n", encoding="utf-8")
    arch_makefile = root / "arch" / "x86" / "Makefile"
    arch_makefile.parent.mkdir(parents=True, exist_ok=True)
    arch_makefile.write_text(
        "PADDING_CFLAGS := -fpatchable-function-entry=$(CONFIG_FUNCTION_PADDING_BYTES),$(CONFIG_FUNCTION_PADDING_BYTES)\n",
        encoding="utf-8",
    )
    target = root / "kernel" / "demo.c"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(file_body, encoding="utf-8")


def _write_disabled_tomoyo_kernel_tree(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "Makefile").write_text("obj-y := demo.o\n", encoding="utf-8")
    (root / ".config").write_text("# CONFIG_SECURITY_TOMOYO is not set\n", encoding="utf-8")
    arch_makefile = root / "arch" / "x86" / "Makefile"
    arch_makefile.parent.mkdir(parents=True, exist_ok=True)
    arch_makefile.write_text(
        "PADDING_CFLAGS := -fpatchable-function-entry=$(CONFIG_FUNCTION_PADDING_BYTES),$(CONFIG_FUNCTION_PADDING_BYTES)\n",
        encoding="utf-8",
    )
    (root / "security" / "tomoyo").mkdir(parents=True, exist_ok=True)
    (root / "security" / "Makefile").write_text(
        "\n".join(
            [
                "obj-$(CONFIG_SECURITY_TOMOYO) += tomoyo/",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (root / "security" / "tomoyo" / "Makefile").write_text(
        "\n".join(
            [
                "obj-y := common.o gc.o",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (root / "security" / "tomoyo" / "common.c").write_text("old_value();\n", encoding="utf-8")


def test_build_orchestrator_switches_to_clean_source_tree_when_default_tree_is_already_patched(tmp_path: Path) -> None:
    patched_src = tmp_path / "patched-src"
    clean_src = tmp_path / "clean-src"
    devel_src = tmp_path / "kernel-devel"
    _write_kernel_tree(patched_src, file_body="new_value();\n")
    _write_kernel_tree(clean_src, file_body="old_value();\n")
    _write_kernel_tree(devel_src, file_body="old_value();\n")

    vmlinux_path = tmp_path / "vmlinux"
    vmlinux_path.write_text("fake vmlinux\n", encoding="utf-8")

    rewritten_patch_path = tmp_path / "rewrite.patch"
    rewritten_patch_path.write_text(
        "\n".join(
            [
                "diff --git a/kernel/demo.c b/kernel/demo.c",
                "--- a/kernel/demo.c",
                "+++ b/kernel/demo.c",
                "@@ -1 +1 @@",
                "-old_value();",
                "+new_value();",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    build_config = BuildConfig(
        clean_kernel_src_dir=str(clean_src),
        kernel_src_dir=str(patched_src),
        kernel_devel_dir=str(devel_src),
        build_source_priority=["kernel_src_dir", "clean_kernel_src_dir", "kernel_devel_dir"],
        auto_switch_source_tree=True,
        vmlinux_path=str(vmlinux_path),
        kpatch_build_cmd="git",
        build_timeout_sec=30,
    )
    orchestrator = BuildOrchestrator(build_config)
    task = TaskContext(
        task_id="TASK-BUILD-001",
        cve_id="CVE-2099-1000",
        target_kernel="6.6.102-5.2.an23.x86_64",
        workspace_dir=tmp_path / "workspace",
    )
    plan = RewritePlan(
        task_id=task.task_id,
        plan_id=f"{task.task_id}-plan-001",
        candidate_ids=[f"{task.task_id}-candidate-001"],
        selected_recipe="direct_apply_patch",
        selected_route_family="direct_apply",
        selected_execution_mode="direct_patch",
        selected_primitives=["direct_apply"],
        target_files=["kernel/demo.c"],
    )
    build_log_path = tmp_path / "attempt" / "logs" / "build.log"

    attempt_record, build_log, build_precheck, build_summary = orchestrator.execute_build(
        task=task,
        attempt_no=1,
        plan=plan,
        rewritten_patch_path=rewritten_patch_path,
        build_log_path=build_log_path,
    )

    assert build_precheck.source_dir == str(clean_src)
    assert build_summary.source_dir == str(clean_src)
    assert "备用源码树" in build_log
    assert attempt_record.failure_type != "target_already_patched"


def test_build_orchestrator_cleans_reverse_source_tree_after_build_attempt(tmp_path: Path) -> None:
    patched_src = tmp_path / "patched-src"
    _write_kernel_tree(patched_src, file_body="new_value();\n")

    vmlinux_path = tmp_path / "vmlinux"
    vmlinux_path.write_text("fake vmlinux\n", encoding="utf-8")

    rewritten_patch_path = tmp_path / "rewrite.patch"
    rewritten_patch_path.write_text(
        "\n".join(
            [
                "diff --git a/kernel/demo.c b/kernel/demo.c",
                "--- a/kernel/demo.c",
                "+++ b/kernel/demo.c",
                "@@ -1 +1 @@",
                "-old_value();",
                "+new_value();",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    build_config = BuildConfig(
        kernel_src_dir=str(patched_src),
        build_source_priority=["kernel_src_dir"],
        auto_switch_source_tree=True,
        auto_reverse_source_tree=True,
        cleanup_generated_source_tree=True,
        vmlinux_path=str(vmlinux_path),
        kpatch_build_cmd="git",
        build_timeout_sec=30,
    )
    orchestrator = BuildOrchestrator(build_config)
    task = TaskContext(
        task_id="TASK-BUILD-REVERSE-CLEANUP",
        cve_id="CVE-2099-1001",
        target_kernel="6.6.102-5.2.an23.x86_64",
        workspace_dir=tmp_path / "workspace",
    )
    plan = RewritePlan(
        task_id=task.task_id,
        plan_id=f"{task.task_id}-plan-001",
        candidate_ids=[f"{task.task_id}-candidate-001"],
        selected_recipe="direct_apply_patch",
        selected_route_family="direct_apply",
        selected_execution_mode="direct_patch",
        selected_primitives=["direct_apply"],
        target_files=["kernel/demo.c"],
    )
    build_log_path = tmp_path / "attempt" / "logs" / "build.log"

    orchestrator.execute_build(
        task=task,
        attempt_no=1,
        plan=plan,
        rewritten_patch_path=rewritten_patch_path,
        build_log_path=build_log_path,
    )

    reverse_source_dir = tmp_path / "attempt" / "sources" / "reverse_unpatched"
    build_log = build_log_path.read_text(encoding="utf-8")

    assert not reverse_source_dir.exists()
    assert "[source cleanup]" in build_log
    assert "临时源码树已清理" in build_log
    assert "[kpatch source normalization]" in build_log
    assert "已将 -fpatchable-function-entry 第二参数归零" in build_log


def test_build_orchestrator_marks_feature_not_enabled_before_running_kpatch_build(tmp_path: Path) -> None:
    source_dir = tmp_path / "kernel-src"
    _write_disabled_tomoyo_kernel_tree(source_dir)

    vmlinux_path = tmp_path / "vmlinux"
    vmlinux_path.write_text("fake vmlinux\n", encoding="utf-8")

    rewritten_patch_path = tmp_path / "rewrite.patch"
    rewritten_patch_path.write_text(
        "\n".join(
            [
                "diff --git a/security/tomoyo/common.c b/security/tomoyo/common.c",
                "--- a/security/tomoyo/common.c",
                "+++ b/security/tomoyo/common.c",
                "@@ -1 +1 @@",
                "-old_value();",
                "+new_value();",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    build_config = BuildConfig(
        kernel_src_dir=str(source_dir),
        build_source_priority=["kernel_src_dir"],
        vmlinux_path=str(vmlinux_path),
        kpatch_build_cmd="git",
        build_timeout_sec=30,
    )
    orchestrator = BuildOrchestrator(build_config)
    task = TaskContext(
        task_id="TASK-BUILD-DISABLED-FEATURE",
        cve_id="CVE-2099-1002",
        target_kernel="6.6.102-5.2.an23.x86_64",
        workspace_dir=tmp_path / "workspace",
    )
    plan = RewritePlan(
        task_id=task.task_id,
        plan_id=f"{task.task_id}-plan-001",
        candidate_ids=[f"{task.task_id}-candidate-001"],
        selected_recipe="direct_apply_patch",
        selected_route_family="direct_apply",
        selected_execution_mode="direct_patch",
        selected_primitives=["direct_apply"],
        target_files=["security/tomoyo/common.c"],
    )
    build_log_path = tmp_path / "attempt" / "logs" / "build.log"

    attempt_record, build_log, build_precheck, build_summary = orchestrator.execute_build(
        task=task,
        attempt_no=1,
        plan=plan,
        rewritten_patch_path=rewritten_patch_path,
        build_log_path=build_log_path,
    )

    assert build_precheck.ok is False
    assert build_precheck.failure_type == "feature_not_enabled"
    assert attempt_record.failure_type == "feature_not_enabled"
    assert attempt_record.build_exec_status == "not_run"
    assert build_summary.failure_type == "feature_not_enabled"
    assert "[build target coverage]" in build_log
    assert "security/tomoyo/common.c" in build_log
