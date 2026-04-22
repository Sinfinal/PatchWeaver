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
    target = root / "kernel" / "demo.c"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(file_body, encoding="utf-8")


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
