from __future__ import annotations

import json
import subprocess
from pathlib import Path
from uuid import uuid4

from patchweaver.config.models import PromptProfile, PromptsConfig, ResolvedRuntime
from patchweaver.coordinator.task_runner import TaskRunner
from patchweaver.builder.orchestrator import BuildOrchestrator
from patchweaver.config.models import BuildConfig, VerifyConfig
from patchweaver.models.attempt import AttemptRecord, BuildSummary
from patchweaver.models.constraint import ConstraintReport
from patchweaver.models.context import BootstrapManifest, ContextBundle
from patchweaver.models.patch import PatchBundle
from patchweaver.models.prompt import PromptPacket
from patchweaver.models.rewrite import ApplyPrecheckReport, RewritePlan
from patchweaver.models.semantic import SemanticCard
from patchweaver.models.skill import SkillRouteDecision
from patchweaver.models.task import TaskContext
from patchweaver.models.validation import ValidationItem, ValidationReport
from patchweaver.reporter.report_builder import ReportBuilder
from patchweaver.rewriter.diff_editor import DiffEditor
from patchweaver.validator.validator import Validator


def _project_root() -> Path:
    current = Path(__file__).resolve().parent
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").exists():
            return candidate
    raise RuntimeError(f"Unable to locate project root from {__file__}")


def _case_dir(case_name: str) -> Path:
    base_dir = _project_root() / ".pytest_tmp"
    base_dir.mkdir(parents=True, exist_ok=True)
    root = base_dir / f"{case_name}-{uuid4().hex[:8]}"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _write_kernel_tree(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "Makefile").write_text("all:\n\t@echo ok\n", encoding="utf-8")
    (root / ".config").write_text("CONFIG_LIVEPATCH=y\n", encoding="utf-8")
    (root / "foo.c").write_text("int value = 1;\n", encoding="utf-8")
    (root / "vmlinux").write_text("fake-vmlinux\n", encoding="utf-8")


def test_local_apply_precheck_rejects_placeholder_patch() -> None:
    tmp_path = _case_dir("build-precheck-placeholder")
    source_dir = tmp_path / "kernel"
    _write_kernel_tree(source_dir)
    patch_path = tmp_path / "rewritten.patch"
    patch_path.write_text("# rewrite plan: TASK-1-plan-001\n", encoding="utf-8")

    build_config = BuildConfig(
        build_backend="local",
        kernel_src_dir=str(source_dir),
        kernel_devel_dir=str(source_dir),
        vmlinux_path=str(source_dir / "vmlinux"),
        kpatch_build_cmd="git",
    )
    orchestrator = BuildOrchestrator(build_config)

    result = orchestrator.precheck_patch(
        task_id="TASK-TEST-001",
        attempt_id="TASK-TEST-001-A001",
        rewritten_patch_path=patch_path,
        source_dir=source_dir,
    )

    assert result.ok is False
    assert result.failure_type == "patch_apply_failed"
    assert "预检查" in result.summary or "patch" in result.summary.lower()


def test_local_apply_precheck_accepts_valid_unified_diff() -> None:
    tmp_path = _case_dir("build-precheck-valid")
    source_dir = tmp_path / "kernel"
    _write_kernel_tree(source_dir)
    patch_path = tmp_path / "rewritten.patch"
    patch_path.write_text(
        "\n".join(
            [
                "diff --git a/foo.c b/foo.c",
                "--- a/foo.c",
                "+++ b/foo.c",
                "@@ -1 +1 @@",
                "-int value = 1;",
                "+int value = 2;",
                "",
            ]
        ),
        encoding="utf-8",
    )

    build_config = BuildConfig(
        build_backend="local",
        kernel_src_dir=str(source_dir),
        kernel_devel_dir=str(source_dir),
        vmlinux_path=str(source_dir / "vmlinux"),
        kpatch_build_cmd="git",
    )
    orchestrator = BuildOrchestrator(build_config)

    result = orchestrator.precheck_patch(
        task_id="TASK-TEST-002",
        attempt_id="TASK-TEST-002-A001",
        rewritten_patch_path=patch_path,
        source_dir=source_dir,
    )

    assert result.ok is True
    assert result.failure_type is None


def test_local_build_executes_real_local_flow(monkeypatch) -> None:
    tmp_path = _case_dir("build-local-flow")
    source_dir = tmp_path / "kernel"
    _write_kernel_tree(source_dir)
    patch_path = tmp_path / "rewritten.patch"
    patch_path.write_text(
        "\n".join(
            [
                "diff --git a/foo.c b/foo.c",
                "--- a/foo.c",
                "+++ b/foo.c",
                "@@ -1 +1 @@",
                "-int value = 1;",
                "+int value = 2;",
                "",
            ]
        ),
        encoding="utf-8",
    )
    build_log_path = tmp_path / "attempts" / "001" / "logs" / "build.log"

    build_config = BuildConfig(
        build_backend="local",
        kernel_src_dir=str(source_dir),
        kernel_devel_dir=str(source_dir),
        vmlinux_path=str(source_dir / "vmlinux"),
        kpatch_build_cmd="kpatch-build",
        build_timeout_sec=120,
    )
    orchestrator = BuildOrchestrator(build_config)

    def fake_which(command: str) -> str | None:
        if command == "git":
            return "/usr/bin/git"
        if command == "kpatch-build":
            return "/usr/bin/kpatch-build"
        return None

    def fake_run(command, cwd=None, capture_output=None, text=None, encoding=None, errors=None, check=None, timeout=None):
        if "apply" in command:
            return subprocess.CompletedProcess(command, 0, "", "")

        output_dir = Path(command[command.index("-o") + 1])
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "demo_patch.ko").write_text("fake ko\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "kpatch build ok\n", "")

    monkeypatch.setattr("patchweaver.builder.orchestrator.which", fake_which)
    monkeypatch.setattr("patchweaver.builder.orchestrator.subprocess.run", fake_run)

    task = TaskContext(
        task_id="TASK-TEST-LOCAL-BUILD",
        cve_id="CVE-2099-0100",
        target_kernel="6.6.102-5.2.an23.x86_64",
        workspace_dir=tmp_path / "workspace",
    )
    plan = RewritePlan(
        task_id=task.task_id,
        plan_id=f"{task.task_id}-plan-001",
        candidate_ids=["cand-001"],
        selected_recipe="direct_apply_patch",
        selected_primitives=["direct_apply"],
        target_files=["foo.c"],
        selection_reason="unit test",
    )

    attempt, build_log, precheck, summary = orchestrator.execute_build(
        task=task,
        attempt_no=1,
        plan=plan,
        rewritten_patch_path=patch_path,
        build_log_path=build_log_path,
    )

    assert precheck.ok is True
    assert attempt.status == "built"
    assert attempt.module_path is not None and attempt.module_path.exists()
    assert summary.status == "built"
    assert summary.module_path is not None and summary.module_path.exists()
    assert "[local command]" in build_log


def test_local_apply_precheck_marks_target_already_patched() -> None:
    tmp_path = _case_dir("build-precheck-already-patched")
    source_dir = tmp_path / "kernel"
    _write_kernel_tree(source_dir)
    patch_path = tmp_path / "rewritten.patch"
    patch_path.write_text(
        "\n".join(
            [
                "diff --git a/foo.c b/foo.c",
                "--- a/foo.c",
                "+++ b/foo.c",
                "@@ -1 +1 @@",
                "-int value = 1;",
                "+int value = 2;",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (source_dir / "foo.c").write_text("int value = 2;\n", encoding="utf-8")

    build_config = BuildConfig(
        build_backend="local",
        kernel_src_dir=str(source_dir),
        kernel_devel_dir=str(source_dir),
        vmlinux_path=str(source_dir / "vmlinux"),
        kpatch_build_cmd="git",
    )
    orchestrator = BuildOrchestrator(build_config)

    result = orchestrator.precheck_patch(
        task_id="TASK-TEST-ALREADY-001",
        attempt_id="TASK-TEST-ALREADY-001-A001",
        rewritten_patch_path=patch_path,
        source_dir=source_dir,
    )

    assert result.ok is False
    assert result.failure_type == "target_already_patched"
    assert "已包含该补丁" in result.summary


def test_diff_editor_apply_precheck_marks_target_already_patched() -> None:
    tmp_path = _case_dir("diff-editor-already-patched")
    source_dir = tmp_path / "kernel"
    _write_kernel_tree(source_dir)
    patch_path = tmp_path / "rewritten.patch"
    patch_path.write_text(
        "\n".join(
            [
                "diff --git a/foo.c b/foo.c",
                "--- a/foo.c",
                "+++ b/foo.c",
                "@@ -1 +1 @@",
                "-int value = 1;",
                "+int value = 2;",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (source_dir / "foo.c").write_text("int value = 2;\n", encoding="utf-8")

    build_config = BuildConfig(
        build_backend="local",
        kernel_src_dir=str(source_dir),
        kernel_devel_dir=str(source_dir),
        vmlinux_path=str(source_dir / "vmlinux"),
        kpatch_build_cmd="git",
    )
    orchestrator = BuildOrchestrator(build_config)
    diff_editor = DiffEditor()

    result = diff_editor.apply_precheck(
        builder=orchestrator,
        patch_path=patch_path,
        task_id="TASK-TEST-ALREADY-002",
        attempt_no=1,
    )

    assert result.status == "failed"
    assert result.failure_type == "target_already_patched"
    assert "已包含该补丁" in result.summary


def test_diff_editor_heuristic_detects_reordered_already_patched_block() -> None:
    tmp_path = _case_dir("diff-editor-heuristic-already-patched")
    source_dir = tmp_path / "kernel"
    _write_kernel_tree(source_dir)
    target_file = source_dir / "net" / "netfilter" / "nf_tables_api.c"
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text(
        "\n".join(
            [
                "static int nft_verdict_init(const struct nft_ctx *ctx, struct nft_data *data,",
                "                            struct nft_data_desc *desc, genmask_t genmask)",
                "{",
                "data->verdict.code = ntohl(nla_get_be32(tb[NFTA_VERDICT_CODE]));",
                "",
                "switch (data->verdict.code) {",
                "case NF_ACCEPT:",
                "case NF_DROP:",
                "case NF_QUEUE:",
                "    break;",
                "case NFT_CONTINUE:",
                "case NFT_BREAK:",
                "case NFT_RETURN:",
                "    break;",
                "case NFT_JUMP:",
                "case NFT_GOTO:",
                "    data->verdict.chain = chain;",
                "    break;",
                "default:",
                "    return -EINVAL;",
                "}",
                "",
                "desc->len = sizeof(data->verdict);",
                "}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    patch_path = tmp_path / "rewritten.patch"
    patch_path.write_text(
        "\n".join(
            [
                "diff --git a/net/netfilter/nf_tables_api.c b/net/netfilter/nf_tables_api.c",
                "index 02f45424644b4..c537104411e7d 100644",
                "--- a/net/netfilter/nf_tables_api.c",
                "+++ b/net/netfilter/nf_tables_api.c",
                "@@ -10992,16 +10992,10 @@ static int nft_verdict_init(const struct nft_ctx *ctx, struct nft_data *data,",
                " \tdata->verdict.code = ntohl(nla_get_be32(tb[NFTA_VERDICT_CODE]));",
                " ",
                " \tswitch (data->verdict.code) {",
                "-\tdefault:",
                "-\t\tswitch (data->verdict.code & NF_VERDICT_MASK) {",
                "-\t\tcase NF_ACCEPT:",
                "-\t\tcase NF_DROP:",
                "-\t\tcase NF_QUEUE:",
                "-\t\t\tbreak;",
                "-\t\tdefault:",
                "-\t\t\treturn -EINVAL;",
                "-\t\t}",
                "-\t\tfallthrough;",
                "+\tcase NF_ACCEPT:",
                "+\tcase NF_DROP:",
                "+\tcase NF_QUEUE:",
                "+\t\tbreak;",
                " \tcase NFT_CONTINUE:",
                " \tcase NFT_BREAK:",
                " \tcase NFT_RETURN:",
                "@@ -11036,6 +11030,8 @@ static int nft_verdict_init(const struct nft_ctx *ctx, struct nft_data *data,",
                " ",
                " \t\tdata->verdict.chain = chain;",
                " \t\tbreak;",
                "+\tdefault:",
                "+\t\treturn -EINVAL;",
                " \t}",
                " ",
                " \tdesc->len = sizeof(data->verdict);",
                " ",
            ]
        ),
        encoding="utf-8",
    )

    diff_editor = DiffEditor()

    assert diff_editor._patch_looks_already_applied_locally(
        patch_path=patch_path,
        source_dir=source_dir,
    )


def test_report_builder_emits_next_priority_for_already_patched() -> None:
    report = ReportBuilder().build_report(
        task=TaskContext(
            task_id="TASK-TEST-REPORT-001",
            cve_id="CVE-2099-0009",
            target_kernel="6.6.102-5.2.an23.x86_64",
            workspace_dir=Path("D:/PatchWeaver/workspaces/TASK-TEST-REPORT-001"),
        ),
        attempts=[
            AttemptRecord(
                task_id="TASK-TEST-REPORT-001",
                attempt_no=1,
                attempt_id="TASK-TEST-REPORT-001-A001",
                status="failed",
                failure_type="target_already_patched",
            )
        ],
        artifacts=[],
        evaluation_summary={},
        explanations=[],
    )

    assert report.next_priority_layer == "target_state"
    assert report.next_action is not None


def test_validator_outputs_structured_pending_validation_when_module_missing() -> None:
    tmp_path = _case_dir("validator-pending")
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    smoke_script = project_root / "scripts" / "validate_smoke.sh"
    smoke_script.parent.mkdir(parents=True, exist_ok=True)
    smoke_script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

    attempt_dir = tmp_path / "attempts" / "001"
    rewritten_patch_path = attempt_dir / "rewrite" / "rewritten.patch"
    rewritten_patch_path.parent.mkdir(parents=True, exist_ok=True)
    rewritten_patch_path.write_text("# rewrite plan: TASK-TEST-003-plan-001\n", encoding="utf-8")

    task = TaskContext(
        task_id="TASK-TEST-003",
        cve_id="CVE-2099-0001",
        target_kernel="6.6.102-5.2.an23.x86_64",
        workspace_dir=tmp_path / "workspace",
    )
    attempt = AttemptRecord(
        task_id=task.task_id,
        attempt_no=1,
        attempt_id=f"{task.task_id}-A001",
        status="failed",
        failure_type="patch_apply_failed",
        rewritten_patch_path=rewritten_patch_path,
    )
    verify_config = VerifyConfig(
        enable_load_test=True,
        enable_unload_test=True,
        enable_smoke_test=True,
        enable_regression=False,
        smoke_test_script="scripts/validate_smoke.sh",
    )
    build_config = BuildConfig(build_backend="local")
    validator = Validator(
        verify_config=verify_config,
        build_config=build_config,
        project_root=project_root,
    )

    report, artifacts = validator.run(
        task=task,
        attempt=attempt,
        attempt_dir=attempt_dir,
        rewritten_patch_path=rewritten_patch_path,
        build_summary=BuildSummary(
            task_id=task.task_id,
            attempt_id=attempt.attempt_id,
            backend="local",
            builder_cmd="git",
            status="failed",
            summary="预检查未通过",
            rewritten_patch_path=rewritten_patch_path,
        ),
    )

    assert report.load_result.status == "pending"
    assert report.unload_result.status == "pending"
    assert report.smoke_result.status == "pending"
    assert report.semantic_guard_result.status == "failed"
    assert Path(artifacts["semantic_precheck"]).exists()
    assert Path(artifacts["validation_report"]).exists()
    assert Path(artifacts["load_log"]).exists()


def test_attempt_service_uses_builder_summary_and_validator_outputs(monkeypatch) -> None:
    tmp_path = _case_dir("attempt-service-integration")
    repo_root = Path(__file__).resolve().parents[2]
    kernel_dir = tmp_path / "kernel"
    _write_kernel_tree(kernel_dir)

    runtime = ResolvedRuntime(
        project_root=repo_root,
        config_dir=repo_root / "config",
        data_dir=tmp_path / "data",
        workspace_root=tmp_path / "workspaces",
        database_path=tmp_path / "data" / "patchweaver.db",
        manifest_dir=tmp_path / "data" / "manifests",
        default_kernel="6.6.102-5.2.an23.x86_64",
        max_attempts=5,
        parallel_read_limit=3,
        write_lock_scope="task",
        trace_mode="full",
    )
    runner = TaskRunner(
        runtime=runtime,
        build_config=BuildConfig(
            build_backend="local",
            kernel_src_dir=str(kernel_dir),
            kernel_devel_dir=str(kernel_dir),
            vmlinux_path=str(kernel_dir / "vmlinux"),
            kpatch_build_cmd="git",
        ),
        verify_config=VerifyConfig(
            enable_load_test=True,
            enable_unload_test=True,
            enable_smoke_test=True,
            enable_regression=False,
            smoke_test_script="scripts/validate_smoke.sh",
        ),
        prompts_config=PromptsConfig(prompt_profiles={"strict": PromptProfile()}),
    )

    task = TaskContext(
        task_id="TASK-TEST-004",
        cve_id="CVE-2099-0004",
        target_kernel=runtime.default_kernel,
        workspace_dir=runtime.workspace_root / "TASK-TEST-004",
    )
    runner.services.task_repo.create_task(task)
    task_dir = runner.services.workspace_guard.create_task_workspace(task)

    raw_patch_path = task_dir / "input" / "raw_patch.patch"
    raw_patch_path.parent.mkdir(parents=True, exist_ok=True)
    raw_patch_path.write_text(
        "\n".join(
            [
                "diff --git a/foo.c b/foo.c",
                "--- a/foo.c",
                "+++ b/foo.c",
                "@@ -1 +1 @@",
                "-int value = 1;",
                "+int value = 2;",
                "",
            ]
        ),
        encoding="utf-8",
    )
    normalized_patch_path = task_dir / "normalized" / "normalized.patch"
    normalized_patch_path.parent.mkdir(parents=True, exist_ok=True)
    normalized_patch_path.write_text(raw_patch_path.read_text(encoding="utf-8"), encoding="utf-8")

    runner.services.json_writer.write_model(
        PatchBundle(
            task_id=task.task_id,
            cve_id=task.cve_id,
            affected_files=["foo.c"],
            raw_patch_path=raw_patch_path,
            normalized_patch_path=normalized_patch_path,
        ),
        task_dir / "input" / "patch_bundle.json",
    )
    runner.services.json_writer.write_model(
        SemanticCard(
            bug_class="logic_error",
            root_cause="unit test",
            touched_functions=["foo"],
        ),
        task_dir / "analysis" / "semantic_card.json",
    )
    runner.services.json_writer.write_model(
        ConstraintReport(
            task_id=task.task_id,
            summary="unit test",
        ),
        task_dir / "analysis" / "constraint_report.json",
    )

    attempt_service = runner.attempt_service

    def fake_build_bootstrap_manifest() -> BootstrapManifest:
        return BootstrapManifest(fragment_ids=["boot-001"], total_token_cost=1)

    def fake_assemble_context(*, stage_name: str, evidence_bundle: object) -> ContextBundle:
        evidence_ids = list(getattr(evidence_bundle, "evidence_ids", []))
        return ContextBundle(evidence_ids=evidence_ids, token_cost=len(evidence_ids), notes=[f"stage={stage_name}"])

    def fake_materialize_stage_packet(
        *,
        stage_name: str,
        schema_name: str,
        context_bundle: ContextBundle,
        bootstrap_manifest: BootstrapManifest,
        base_dir: Path,
    ) -> dict[str, object]:
        route = SkillRouteDecision(
            stage_name=stage_name,
            candidate_skills=["unit-test-skill"],
            selected_skill="unit-test-skill",
            selection_reason="unit test route",
            fallback_used=False,
            route_source="unit-test",
        )
        prompt_packet = PromptPacket(
            stage_name=stage_name,
            system_prompt_version="test",
            worker_prompt_version="test",
            schema_name=schema_name,
            budget_snapshot={"token_cost": context_bundle.token_cost},
            bootstrap_fragments=bootstrap_manifest.fragment_ids,
            prompt_sections=[f"schema={schema_name}"],
        )
        route_path = attempt_service.json_writer.write_model(route, base_dir / "route" / f"{stage_name}_skill_route.json")
        prompt_path = attempt_service.json_writer.write_model(
            prompt_packet,
            base_dir / "prompt" / f"{stage_name}_prompt_packet.json",
        )
        return {
            "route": route,
            "prompt_packet": prompt_packet,
            "route_path": route_path,
            "prompt_path": prompt_path,
        }

    def fake_plan(*, task_id: str, semantic_card: SemanticCard, constraint_report: ConstraintReport) -> RewritePlan:
        return RewritePlan(
            task_id=task_id,
            plan_id=f"{task_id}-plan-001",
            candidate_ids=["cand-001"],
            selected_recipe="direct_apply_patch",
            selected_primitives=["direct_apply"],
            target_files=["foo.c"],
            selection_reason="unit test plan",
        )

    def fake_rewriter_execute(
        *,
        plan: RewritePlan,
        patch_bundle: PatchBundle,
        rewrite_dir: Path,
        builder: object,
        task_id: str,
        attempt_no: int,
    ) -> dict[str, object]:
        rewrite_dir.mkdir(parents=True, exist_ok=True)
        rewritten_patch_path = rewrite_dir / "rewritten.patch"
        rewritten_patch_path.write_text(patch_bundle.normalized_patch_path.read_text(encoding="utf-8"), encoding="utf-8")
        rewrite_reason_path = rewrite_dir / "rewrite_reason.json"
        rewrite_reason_path.write_text("{\"reason\": \"unit test\"}\n", encoding="utf-8")
        transformation_trace_path = rewrite_dir / "transformation_trace.json"
        transformation_trace_path.write_text("{\"trace\": \"unit test\"}\n", encoding="utf-8")
        apply_precheck_path = rewrite_dir / "apply_precheck.json"
        apply_precheck_report = ApplyPrecheckReport(
            status="passed",
            ok=True,
            backend="local",
            target_source_dir=str(kernel_dir),
            checked_patch_path=str(rewritten_patch_path),
            summary="预检查通过。",
        )
        apply_precheck_path.write_text(apply_precheck_report.model_dump_json(indent=2), encoding="utf-8")
        return {
            "rewritten_patch": rewritten_patch_path,
            "rewrite_reason": rewrite_reason_path,
            "transformation_trace": transformation_trace_path,
            "apply_precheck": apply_precheck_path,
            "apply_precheck_report": apply_precheck_report,
        }

    def fake_execute_build(
        *,
        task: TaskContext,
        attempt_no: int,
        plan: RewritePlan,
        rewritten_patch_path: Path,
        build_log_path: Path,
    ) -> tuple[AttemptRecord, str, object, BuildSummary]:
        build_log_path.parent.mkdir(parents=True, exist_ok=True)
        build_log = "unit test build ok\n"
        build_log_path.write_text(build_log, encoding="utf-8")
        module_path = build_log_path.parent.parent / "output" / "livepatch.ko"
        module_path.parent.mkdir(parents=True, exist_ok=True)
        module_path.write_text("fake module", encoding="utf-8")
        attempt_record = AttemptRecord(
            task_id=task.task_id,
            attempt_no=attempt_no,
            attempt_id=f"{task.task_id}-A{attempt_no:03d}",
            candidate_id=plan.candidate_ids[0],
            status="built",
            build_log_path=build_log_path,
            module_path=module_path,
            rewritten_patch_path=rewritten_patch_path,
        )
        build_precheck = runner.services.builder.precheck_patch(
            task_id=task.task_id,
            attempt_id=attempt_record.attempt_id,
            rewritten_patch_path=rewritten_patch_path,
            source_dir=kernel_dir,
        )
        build_summary = BuildSummary(
            task_id=task.task_id,
            attempt_id=attempt_record.attempt_id,
            backend="local",
            builder_cmd="git",
            status="built",
            summary="unit test build summary",
            rewritten_patch_path=rewritten_patch_path,
            source_dir=str(kernel_dir),
            build_log_path=build_log_path,
            module_path=module_path,
        )
        return attempt_record, build_log, build_precheck, build_summary

    validator_calls: dict[str, object] = {}

    def fake_validator_run(
        *,
        task: TaskContext,
        attempt: AttemptRecord,
        attempt_dir: Path,
        rewritten_patch_path: Path,
        build_summary: BuildSummary | None = None,
    ) -> tuple[ValidationReport, dict[str, Path]]:
        validator_calls["build_summary"] = build_summary
        artifacts_dir = attempt_dir / "artifacts"
        logs_dir = attempt_dir / "logs"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)

        semantic_precheck_path = artifacts_dir / "semantic_precheck.json"
        semantic_precheck_path.write_text("{\"status\": \"passed\"}\n", encoding="utf-8")
        load_log_path = logs_dir / "load.log"
        unload_log_path = logs_dir / "unload.log"
        smoke_log_path = logs_dir / "smoke.log"
        for log_path, content in [
            (load_log_path, "load skipped\n"),
            (unload_log_path, "unload skipped\n"),
            (smoke_log_path, "smoke skipped\n"),
        ]:
            log_path.write_text(content, encoding="utf-8")

        report = ValidationReport(
            load_result=ValidationItem(status="skipped", ok=False, detail="unit test load"),
            unload_result=ValidationItem(status="skipped", ok=False, detail="unit test unload"),
            smoke_result=ValidationItem(status="skipped", ok=False, detail="unit test smoke"),
            semantic_guard_result=ValidationItem(status="passed", ok=True, detail="unit test semantic guard"),
            notes=["validator invoked"],
        )
        validation_report_path = artifacts_dir / "validation_report.json"
        validation_report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        return report, {
            "semantic_precheck": semantic_precheck_path,
            "validation_report": validation_report_path,
            "load_log": load_log_path,
            "unload_log": unload_log_path,
            "smoke_log": smoke_log_path,
        }

    monkeypatch.setattr(attempt_service, "build_bootstrap_manifest", fake_build_bootstrap_manifest)
    monkeypatch.setattr(attempt_service, "assemble_context", fake_assemble_context)
    monkeypatch.setattr(attempt_service, "materialize_stage_packet", fake_materialize_stage_packet)
    monkeypatch.setattr(attempt_service.planner, "plan", fake_plan)
    monkeypatch.setattr(attempt_service.rewriter, "execute", fake_rewriter_execute)
    monkeypatch.setattr(attempt_service.builder, "execute_build", fake_execute_build)
    monkeypatch.setattr(attempt_service.validator, "run", fake_validator_run)

    result = runner.run_task(task.task_id)
    attempt_dir = task_dir / "attempts" / "001"

    assert result["status"] == "built"
    assert isinstance(validator_calls["build_summary"], BuildSummary)
    assert validator_calls["build_summary"].status == "built"
    assert (attempt_dir / "artifacts" / "build_precheck.json").exists()
    assert (attempt_dir / "artifacts" / "build_summary.json").exists()
    assert (attempt_dir / "artifacts" / "semantic_precheck.json").exists()
    assert (attempt_dir / "artifacts" / "validation_report.json").exists()
    assert (attempt_dir / "logs" / "validate.log").exists()
    assert (attempt_dir / "logs" / "load.log").exists()
    assert (attempt_dir / "logs" / "unload.log").exists()
    assert (attempt_dir / "logs" / "smoke.log").exists()

    artifact_types = {artifact.artifact_type for artifact in runner.services.artifact_repo.list_artifacts(task.task_id)}
    assert "build_precheck" in artifact_types
    assert "build_summary" in artifact_types
    assert "semantic_precheck" in artifact_types
    assert "load_log" in artifact_types
    assert "unload_log" in artifact_types
    assert "smoke_log" in artifact_types


def test_attempt_service_records_narrow_failover_when_failure_occurs(monkeypatch) -> None:
    tmp_path = _case_dir("attempt-service-failover")
    repo_root = Path(__file__).resolve().parents[2]
    kernel_dir = tmp_path / "kernel"
    _write_kernel_tree(kernel_dir)

    runtime = ResolvedRuntime(
        project_root=repo_root,
        config_dir=repo_root / "config",
        data_dir=tmp_path / "data",
        workspace_root=tmp_path / "workspaces",
        database_path=tmp_path / "data" / "patchweaver.db",
        manifest_dir=tmp_path / "data" / "manifests",
        default_kernel="6.6.102-5.2.an23.x86_64",
        max_attempts=5,
        parallel_read_limit=3,
        write_lock_scope="task",
        trace_mode="full",
        profile_name="full",
        enable_narrow_failover=True,
        enable_read_parallel=True,
    )
    runner = TaskRunner(
        runtime=runtime,
        build_config=BuildConfig(
            build_backend="local",
            kernel_src_dir=str(kernel_dir),
            kernel_devel_dir=str(kernel_dir),
            vmlinux_path=str(kernel_dir / "vmlinux"),
            kpatch_build_cmd="git",
            build_timeout_sec=900,
        ),
        verify_config=VerifyConfig(
            enable_load_test=True,
            enable_unload_test=True,
            enable_smoke_test=True,
            enable_regression=False,
            smoke_test_script="scripts/validate_smoke.sh",
        ),
        prompts_config=PromptsConfig(
            default_prompt_profile="strict",
            prompt_profiles={
                "strict": PromptProfile(),
                "debug": PromptProfile(max_evidence_snippets=12),
            },
        ),
    )

    task = TaskContext(
        task_id="TASK-TEST-005",
        cve_id="CVE-2099-0005",
        target_kernel=runtime.default_kernel,
        workspace_dir=runtime.workspace_root / "TASK-TEST-005",
    )
    runner.services.task_repo.create_task(task)
    task_dir = runner.services.workspace_guard.create_task_workspace(task)

    raw_patch_path = task_dir / "input" / "raw_patch.patch"
    raw_patch_path.parent.mkdir(parents=True, exist_ok=True)
    raw_patch_path.write_text("# placeholder patch\n", encoding="utf-8")
    normalized_patch_path = task_dir / "normalized" / "normalized.patch"
    normalized_patch_path.parent.mkdir(parents=True, exist_ok=True)
    normalized_patch_path.write_text(raw_patch_path.read_text(encoding="utf-8"), encoding="utf-8")

    runner.services.json_writer.write_model(
        PatchBundle(
            task_id=task.task_id,
            cve_id=task.cve_id,
            affected_files=["foo.c"],
            raw_patch_path=raw_patch_path,
            normalized_patch_path=normalized_patch_path,
        ),
        task_dir / "input" / "patch_bundle.json",
    )
    runner.services.json_writer.write_model(
        SemanticCard(
            bug_class="logic_error",
            root_cause="unit test failover",
            touched_functions=["foo"],
        ),
        task_dir / "analysis" / "semantic_card.json",
    )
    runner.services.json_writer.write_model(
        ConstraintReport(
            task_id=task.task_id,
            risk_level="high",
            constraints=["patch_apply_failed"],
            summary="unit test failover",
        ),
        task_dir / "analysis" / "constraint_report.json",
    )

    attempt_service = runner.attempt_service

    def fake_build_bootstrap_manifest() -> BootstrapManifest:
        return BootstrapManifest(fragment_ids=["boot-001"], total_token_cost=1)

    def fake_assemble_context(*, stage_name: str, evidence_bundle: object) -> ContextBundle:
        evidence_ids = list(getattr(evidence_bundle, "evidence_ids", []))
        return ContextBundle(evidence_ids=evidence_ids, token_cost=len(evidence_ids), notes=[f"stage={stage_name}"])

    def fake_materialize_stage_packet(
        *,
        stage_name: str,
        schema_name: str,
        context_bundle: ContextBundle,
        bootstrap_manifest: BootstrapManifest,
        base_dir: Path,
    ) -> dict[str, object]:
        route = SkillRouteDecision(
            stage_name=stage_name,
            candidate_skills=["unit-test-skill"],
            selected_skill="unit-test-skill",
            selection_reason="unit test route",
            fallback_used=False,
            route_source="unit-test",
        )
        prompt_packet = PromptPacket(
            stage_name=stage_name,
            system_prompt_version="test",
            worker_prompt_version="test",
            schema_name=schema_name,
            budget_snapshot={"token_cost": context_bundle.token_cost},
            bootstrap_fragments=bootstrap_manifest.fragment_ids,
            prompt_sections=[f"schema={schema_name}"],
        )
        route_path = attempt_service.json_writer.write_model(route, base_dir / "route" / f"{stage_name}_skill_route.json")
        prompt_path = attempt_service.json_writer.write_model(
            prompt_packet,
            base_dir / "prompt" / f"{stage_name}_prompt_packet.json",
        )
        return {
            "route": route,
            "prompt_packet": prompt_packet,
            "route_path": route_path,
            "prompt_path": prompt_path,
        }

    def fake_plan(*, task_id: str, semantic_card: SemanticCard, constraint_report: ConstraintReport) -> RewritePlan:
        return RewritePlan(
            task_id=task_id,
            plan_id=f"{task_id}-plan-001",
            candidate_ids=["cand-001"],
            selected_recipe="direct_apply_patch",
            selected_primitives=["direct_apply"],
            target_files=["foo.c"],
            selection_reason="unit test failover plan",
        )

    def fake_rewriter_execute(
        *,
        plan: RewritePlan,
        patch_bundle: PatchBundle,
        rewrite_dir: Path,
        builder: object,
        task_id: str,
        attempt_no: int,
    ) -> dict[str, object]:
        rewrite_dir.mkdir(parents=True, exist_ok=True)
        rewritten_patch_path = rewrite_dir / "rewritten.patch"
        rewritten_patch_path.write_text("# invalid patch for failover\n", encoding="utf-8")
        rewrite_reason_path = rewrite_dir / "rewrite_reason.json"
        rewrite_reason_path.write_text("{\"reason\": \"unit test failover\"}\n", encoding="utf-8")
        transformation_trace_path = rewrite_dir / "transformation_trace.json"
        transformation_trace_path.write_text("{\"trace\": \"unit test failover\"}\n", encoding="utf-8")
        apply_precheck_path = rewrite_dir / "apply_precheck.json"
        apply_precheck_report = ApplyPrecheckReport(
            status="failed",
            ok=False,
            backend="local",
            target_source_dir=str(kernel_dir),
            checked_patch_path=str(rewritten_patch_path),
            command="git apply --check",
            summary="预检查失败。",
            stdout="",
            stderr="patch does not apply",
            failure_type="patch_apply_failed",
        )
        apply_precheck_path.write_text(apply_precheck_report.model_dump_json(indent=2), encoding="utf-8")
        return {
            "rewritten_patch": rewritten_patch_path,
            "rewrite_reason": rewrite_reason_path,
            "transformation_trace": transformation_trace_path,
            "apply_precheck": apply_precheck_path,
            "apply_precheck_report": apply_precheck_report,
        }

    def fake_validator_run(
        *,
        task: TaskContext,
        attempt: AttemptRecord,
        attempt_dir: Path,
        rewritten_patch_path: Path,
        build_summary: BuildSummary | None = None,
    ) -> tuple[ValidationReport, dict[str, Path]]:
        artifacts_dir = attempt_dir / "artifacts"
        logs_dir = attempt_dir / "logs"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)

        semantic_precheck_path = artifacts_dir / "semantic_precheck.json"
        semantic_precheck_path.write_text("{\"status\": \"failed\"}\n", encoding="utf-8")
        load_log_path = logs_dir / "load.log"
        unload_log_path = logs_dir / "unload.log"
        smoke_log_path = logs_dir / "smoke.log"
        for log_path in [load_log_path, unload_log_path, smoke_log_path]:
            log_path.write_text("skipped\n", encoding="utf-8")

        report = ValidationReport(
            load_result=ValidationItem(status="pending", ok=False, detail="unit test load pending"),
            unload_result=ValidationItem(status="pending", ok=False, detail="unit test unload pending"),
            smoke_result=ValidationItem(status="pending", ok=False, detail="unit test smoke pending"),
            semantic_guard_result=ValidationItem(status="failed", ok=False, detail="unit test semantic guard failed"),
            notes=["validator invoked"],
        )
        validation_report_path = artifacts_dir / "validation_report.json"
        validation_report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        return report, {
            "semantic_precheck": semantic_precheck_path,
            "validation_report": validation_report_path,
            "load_log": load_log_path,
            "unload_log": unload_log_path,
            "smoke_log": smoke_log_path,
        }

    monkeypatch.setattr(attempt_service, "build_bootstrap_manifest", fake_build_bootstrap_manifest)
    monkeypatch.setattr(attempt_service, "assemble_context", fake_assemble_context)
    monkeypatch.setattr(attempt_service, "materialize_stage_packet", fake_materialize_stage_packet)
    monkeypatch.setattr(attempt_service.planner, "plan", fake_plan)
    monkeypatch.setattr(attempt_service.rewriter, "execute", fake_rewriter_execute)
    monkeypatch.setattr(attempt_service.validator, "run", fake_validator_run)

    result = runner.run_task(task.task_id)
    failover_path = Path(result["failover_record_path"])

    assert result["status"] == "failed"
    assert failover_path.exists()

    failover_record = json.loads(failover_path.read_text(encoding="utf-8").strip().splitlines()[0])
    assert failover_record["stage_name"] == "failure_analysis"
    assert failover_record["from_profile"] == "full"
    assert failover_record["field_changes"]["build_timeout_sec"]["from"] == 900
    assert failover_record["field_changes"]["build_timeout_sec"]["to"] == 1200
    assert failover_record["field_changes"]["parallel_read_limit"]["from"] == 3
    assert failover_record["field_changes"]["parallel_read_limit"]["to"] == 1
    assert failover_record["field_changes"]["prompt_profile"]["from"] == "strict"
    assert failover_record["field_changes"]["prompt_profile"]["to"] == "debug"

    artifact_types = {artifact.artifact_type for artifact in runner.services.artifact_repo.list_artifacts(task.task_id)}
    assert "failover_record" in artifact_types
