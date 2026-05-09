from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.screen_challenge_pool import (
    apply_module_target_gate,
    apply_known_pool_gate,
    annotate_with_rag_seed,
    count_existing_positive_pool,
    infer_build_targets_for_record,
    load_cves,
    load_full_artifacts,
    load_rag_seed_index,
    parse_posix_descendant_process_groups,
    parse_args,
    prepare_stable_baselines_for_records,
    positive_acceptance_evidence_ok,
    should_continue_run,
    summarize,
    update_positive_pool_fixture,
    write_minimal_config_fragments,
    write_markdown_report,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_screen_challenge_pool_help_runs() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/screen_challenge_pool.py", "--help"],
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert "Challenge 样例分层与正向样例池筛选" in proc.stdout
    assert "--run-timeout-sec" in proc.stdout
    assert "--only-positive-candidates" in proc.stdout
    assert "--max-run-attempts" in proc.stdout
    assert "--update-positive-pool" in proc.stdout
    assert "--positive-pool-target" in proc.stdout
    assert "--rag-seed-fixture" in proc.stdout
    assert "--known-kpatch-constraint-fixture" in proc.stdout
    assert "--include-known-pool-cases" in proc.stdout
    assert "--min-livepatchability-score" in proc.stdout
    assert "--only-high-livepatchability" in proc.stdout
    assert "--prepare-stable-baseline" in proc.stdout
    assert "--stable-source-git-dir" in proc.stdout
    assert "--stable-source-cache-dir" in proc.stdout
    assert "--stable-config-source" in proc.stdout
    assert "--config-fragment-dir" in proc.stdout
    assert "check-vendor-baseline" in subprocess.run(
        [sys.executable, "-m", "patchweaver", "--help"],
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    ).stdout


def test_should_continue_run_for_recoverable_failures() -> None:
    record = {
        "run_status": "failed",
        "failure_type": "kpatch_constraint",
        "screening_tier": "blocked_by_kpatch_constraint",
    }

    assert should_continue_run(record=record, run_index=1, max_run_attempts=3) is True


def test_should_not_continue_run_for_terminal_target_state() -> None:
    record = {
        "run_status": "target_state",
        "failure_type": "target_already_patched",
        "screening_tier": "positive_candidate_blocked_by_target_state",
    }

    assert should_continue_run(record=record, run_index=1, max_run_attempts=3) is False


def test_should_not_continue_run_for_terminal_arch_mismatch() -> None:
    record = {
        "run_status": "failed",
        "failure_type": "target_arch_mismatch",
        "screening_tier": "development_only_arch_gate",
    }

    assert should_continue_run(record=record, run_index=1, max_run_attempts=3) is False


def test_should_not_continue_run_for_outer_timeout() -> None:
    record = {
        "run_status": "timeout",
        "failure_type": "run_timeout",
        "screening_tier": "blocked_by_run_timeout",
    }

    assert should_continue_run(record=record, run_index=1, max_run_attempts=3) is False


def test_should_not_continue_run_when_task_attempt_budget_exhausted() -> None:
    record = {
        "run_status": "failed",
        "failure_type": "kpatch_constraint",
        "max_attempts_exhausted": True,
        "screening_tier": "blocked_by_kpatch_constraint",
    }

    assert should_continue_run(record=record, run_index=1, max_run_attempts=3) is False


def test_load_cves_supports_start_index(tmp_path: Path, monkeypatch) -> None:
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        '[{"cve_id":"CVE-1"},{"cve_id":"CVE-2"},{"cve_id":"CVE-3"}]\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "screen_challenge_pool.py",
            "--fixture",
            str(fixture_path),
            "--output",
            str(tmp_path / "out.json"),
            "--start-index",
            "1",
            "--max-cases",
            "1",
        ],
    )

    args = parse_args()
    cves = load_cves(args)

    assert cves == ["CVE-2"]


def test_parse_posix_descendant_process_groups_includes_detached_grandchild() -> None:
    ps_output = "\n".join(
        [
            "100 1 100",
            "110 100 110",
            "120 110 120",
            "130 1 130",
        ]
    )

    pgids = parse_posix_descendant_process_groups(root_pid=100, ps_output=ps_output)

    assert pgids == {110, 120}


def test_infer_build_targets_for_record_marks_module_target() -> None:
    class FakeOrchestrator:
        def _resolve_build_target_detail(self, *, source_dir, relative_path, config_values):
            return "drivers/demo/demo.ko", "module"

    result = infer_build_targets_for_record(
        orchestrator=FakeOrchestrator(),
        source_dir=Path("/tmp/kernel"),
        config_values={},
        target_files=[Path("drivers/demo/demo.c")],
    )

    assert result == [
        {
            "file": "drivers/demo/demo.c",
            "target": "drivers/demo/demo.ko",
            "state": "module",
        }
    ]


def test_apply_module_target_gate_defers_vmlinux_candidate(tmp_path: Path, monkeypatch) -> None:
    source_dir = tmp_path / "kernel"
    source_dir.mkdir()
    (source_dir / "Makefile").write_text("obj-y := demo.o\n", encoding="utf-8")

    class FakeBuildConfig:
        clean_kernel_src_dir = ""
        prepared_kernel_src_dir = str(source_dir)
        kernel_src_dir = ""
        kernel_devel_dir = ""

    class FakeOrchestrator:
        def __init__(self, build_config):
            self.build_config = build_config

        def _load_kernel_config_values(self, source_dir):
            return {}

        def _resolve_build_target_detail(self, *, source_dir, relative_path, config_values):
            return "vmlinux", "built_in"

    monkeypatch.setattr("scripts.screen_challenge_pool.load_build_config", lambda project_root: FakeBuildConfig())
    monkeypatch.setattr("scripts.screen_challenge_pool.BuildOrchestrator", FakeOrchestrator)
    records = [
        {
            "cve_id": "CVE-2024-29998",
            "target_files": ["kernel/demo.c"],
            "positive_pool_candidate": True,
        }
    ]

    gated = apply_module_target_gate(records, project_root=tmp_path)

    assert gated[0]["positive_pool_candidate"] is False
    assert gated[0]["screening_tier"] == "deferred_vmlinux_target"
    assert gated[0]["vmlinux_target_candidate"] is True


def test_apply_module_target_gate_keeps_module_candidate(tmp_path: Path, monkeypatch) -> None:
    source_dir = tmp_path / "kernel"
    source_dir.mkdir()
    (source_dir / "Makefile").write_text("obj-m := demo.o\n", encoding="utf-8")

    class FakeBuildConfig:
        clean_kernel_src_dir = ""
        prepared_kernel_src_dir = str(source_dir)
        kernel_src_dir = ""
        kernel_devel_dir = ""

    class FakeOrchestrator:
        def __init__(self, build_config):
            self.build_config = build_config

        def _load_kernel_config_values(self, source_dir):
            return {}

        def _resolve_build_target_detail(self, *, source_dir, relative_path, config_values):
            return "drivers/demo/demo.ko", "module"

    monkeypatch.setattr("scripts.screen_challenge_pool.load_build_config", lambda project_root: FakeBuildConfig())
    monkeypatch.setattr("scripts.screen_challenge_pool.BuildOrchestrator", FakeOrchestrator)
    records = [
        {
            "cve_id": "CVE-2024-29997",
            "target_files": ["drivers/demo/demo.c"],
            "positive_pool_candidate": True,
        }
    ]

    gated = apply_module_target_gate(records, project_root=tmp_path)

    assert gated[0]["positive_pool_candidate"] is True
    assert gated[0]["module_target_candidate"] is True


def test_write_minimal_config_fragments_materializes_profile(tmp_path: Path) -> None:
    records = [
        {
            "cve_id": "CVE-2024-29996",
            "minimal_config_repair": {
                "status": "repairable",
                "config_delta": {"CONFIG_DEMO": "m"},
            },
            "minimal_config_fragment": "CONFIG_DEMO=m\n",
        }
    ]

    written = write_minimal_config_fragments(records=records, fragment_dir=tmp_path / "fragments")

    assert written == ["CVE-2024-29996"]
    fragment_path = Path(records[0]["minimal_config_fragment_path"])
    assert fragment_path.name == "CVE-2024-29996.config.fragment"
    assert fragment_path.read_text(encoding="utf-8") == "CONFIG_DEMO=m\n"
    assert records[0]["minimal_config_profile"]["status"] == "fragment_ready"
    assert "merge_config.sh" in records[0]["minimal_config_profile"]["merge_config_cmd"]


def test_prepare_stable_baselines_for_records_calls_cli_for_positive_candidate(monkeypatch) -> None:
    calls: list[list[str]] = []

    class Args:
        prepare_stable_baseline = True
        only_positive_candidates = True
        python = sys.executable
        stable_baseline_timeout_sec = 321

    def fake_run_cli_json(*, python_bin, cwd, cli_args, timeout_sec=None):
        calls.append(cli_args)
        assert timeout_sec == 321
        return {
            "output_dir": "/tmp/stable-baselines/demo",
            "reused_existing": False,
            "git_head": "abc123",
            "config_path": "/tmp/stable-baselines/demo/.config",
        }

    monkeypatch.setattr("scripts.screen_challenge_pool.run_cli_json", fake_run_cli_json)
    records = [
        {
            "cve_id": "CVE-2024-29995",
            "positive_pool_candidate": True,
            "stable_source_baseline_ref": "abc123^",
        }
    ]

    prepared = prepare_stable_baselines_for_records(records=records, args=Args())

    assert calls == [["prepare-stable-baseline", "--baseline-ref", "abc123^", "--no-write-build-config", "--json"]]
    assert prepared[0]["stable_baseline_preparation"]["status"] == "prepared"
    assert prepared[0]["stable_kernel_src_dir"] == "/tmp/stable-baselines/demo"
    assert prepared[0]["stable_baseline_ready"] is True


def test_prepare_stable_baselines_blocks_positive_candidate_on_prepare_failure(monkeypatch) -> None:
    class Args:
        prepare_stable_baseline = True
        only_positive_candidates = True
        python = sys.executable
        stable_baseline_timeout_sec = 321

    def fake_run_cli_json(*, python_bin, cwd, cli_args, timeout_sec=None):
        raise RuntimeError("stable repo missing")

    monkeypatch.setattr("scripts.screen_challenge_pool.run_cli_json", fake_run_cli_json)
    records = [
        {
            "cve_id": "CVE-2024-29994",
            "positive_pool_candidate": True,
            "stable_source_baseline_ref": "abc123^",
        }
    ]

    prepared = prepare_stable_baselines_for_records(records=records, args=Args())

    assert prepared[0]["stable_baseline_preparation"]["status"] == "failed"
    assert prepared[0]["positive_pool_candidate"] is False
    assert prepared[0]["screening_tier"] == "blocked_by_stable_baseline_prepare_failed"
    assert prepared[0]["agent_next_action"] == "inspect_stable_source_baseline_failure"


def test_apply_known_pool_gate_skips_confirmed_positive_case(tmp_path: Path) -> None:
    positive_fixture = tmp_path / "positive.json"
    kpatch_fixture = tmp_path / "kpatch.json"
    positive_fixture.write_text('[{"cve_id":"CVE-2024-26742"}]\n', encoding="utf-8")
    kpatch_fixture.write_text("[]\n", encoding="utf-8")
    records = [
        {
            "cve_id": "CVE-2024-26742",
            "positive_pool_candidate": True,
            "screening_tier": "positive_candidate_low_risk",
        }
    ]

    gated = apply_known_pool_gate(
        records,
        positive_pool_fixture=positive_fixture,
        known_kpatch_constraint_fixture=kpatch_fixture,
    )

    assert gated[0]["known_pool_hit"] == "positive_pool"
    assert gated[0]["sample_bucket"] == "buildable_and_should_pass"
    assert gated[0]["screening_tier"] == "positive_candidate_already_confirmed"


def test_load_full_artifacts_does_not_emit_empty_failure_type(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspaces"
    attempt_dir = workspace_root / "task-001" / "attempts" / "002"
    (attempt_dir / "artifacts").mkdir(parents=True)
    (attempt_dir / "logs").mkdir(parents=True)

    payload = load_full_artifacts(workspace_root=workspace_root, task_id="task-001")

    assert "failure_type" not in payload


def test_load_full_artifacts_reads_module_vermagic(tmp_path: Path, monkeypatch) -> None:
    task_id = "poolscan-29997"
    attempt_dir = tmp_path / task_id / "attempts" / "001"
    (attempt_dir / "artifacts").mkdir(parents=True)
    (attempt_dir / "output").mkdir()
    module_path = attempt_dir / "output" / "patchweaver.ko"
    module_path.write_text("fake module\n", encoding="utf-8")
    (attempt_dir / "artifacts" / "build_summary.json").write_text(
        json.dumps({"status": "built", "module_path": str(module_path)}, ensure_ascii=False),
        encoding="utf-8",
    )
    (attempt_dir / "artifacts" / "validation_report.json").write_text(
        json.dumps({"status": "passed"}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "scripts.screen_challenge_pool.read_module_vermagic",
        lambda path: "6.6.102-5.2.an23.x86_64 SMP",
    )
    monkeypatch.setattr("scripts.screen_challenge_pool.platform.release", lambda: "6.6.102-5.2.an23.x86_64")

    payload = load_full_artifacts(workspace_root=tmp_path, task_id=task_id)

    assert payload["module_exists"] is True
    assert payload["module_vermagic"] == "6.6.102-5.2.an23.x86_64 SMP"
    assert payload["target_kernel_release"] == "6.6.102-5.2.an23.x86_64"


def test_apply_known_pool_gate_skips_known_kpatch_constraint_case(tmp_path: Path) -> None:
    positive_fixture = tmp_path / "positive.json"
    kpatch_fixture = tmp_path / "kpatch.json"
    positive_fixture.write_text("[]\n", encoding="utf-8")
    kpatch_fixture.write_text('[{"cve_id":"CVE-2024-26643"}]\n', encoding="utf-8")
    records = [
        {
            "cve_id": "CVE-2024-26643",
            "positive_pool_candidate": True,
            "screening_tier": "positive_candidate_low_risk",
        }
    ]

    gated = apply_known_pool_gate(
        records,
        positive_pool_fixture=positive_fixture,
        known_kpatch_constraint_fixture=kpatch_fixture,
    )

    assert gated[0]["known_pool_hit"] == "kpatch_constraint_pool"
    assert gated[0]["sample_bucket"] == "kpatch_constraint"
    assert gated[0]["screening_tier"] == "blocked_by_known_kpatch_constraint"
    assert gated[0]["positive_pool_candidate"] is False


def test_known_kpatch_constraint_fixture_marks_p0_breakthrough_cases() -> None:
    fixture_path = PROJECT_ROOT / "evaluations" / "fixtures" / "challenge_kpatch_constraint_pool_v0427.json"
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    breakthrough = {
        item["cve_id"]: item
        for item in payload
        if item.get("breakthrough_status") == "positive_acceptance_confirmed"
    }

    assert {"CVE-2024-26675", "CVE-2024-26663"}.issubset(breakthrough)
    assert all(item["breakthrough_strategy"] == "call_sites_section_compat" for item in breakthrough.values())


def test_update_positive_pool_fixture_appends_confirmed_cases(tmp_path: Path) -> None:
    fixture_path = tmp_path / "positive.json"
    results = [
        {
            "cve_id": "CVE-2024-29999",
            "build_status": "built",
            "validation_status": "passed",
            "module_path": "/tmp/patchweaver.ko",
            "module_exists": True,
            "module_vermagic": "6.6.102-5.2.an23.x86_64 SMP preempt mod_unload modversions",
            "target_kernel_release": "6.6.102-5.2.an23.x86_64",
            "sample_bucket": "buildable_and_should_pass",
            "screening_tier": "positive_acceptance_confirmed",
        }
    ]

    added = update_positive_pool_fixture(
        fixture_path=fixture_path,
        results=results,
        screening_round="vtest",
    )

    assert added == ["CVE-2024-29999"]
    text = fixture_path.read_text(encoding="utf-8")
    assert "CVE-2024-29999" in text
    assert "repair_intent.json" in text
    assert "rewritten.patch" in text
    assert "semantic_guard.json" in text


def test_update_positive_pool_fixture_rejects_missing_vermagic(tmp_path: Path) -> None:
    fixture_path = tmp_path / "positive.json"
    results = [
        {
            "cve_id": "CVE-2024-29998",
            "build_status": "built",
            "validation_status": "passed",
            "module_path": "/tmp/patchweaver.ko",
            "module_exists": True,
            "sample_bucket": "buildable_and_should_pass",
            "screening_tier": "positive_acceptance_confirmed",
        }
    ]

    added = update_positive_pool_fixture(
        fixture_path=fixture_path,
        results=results,
        screening_round="vtest",
    )

    assert added == []
    assert not fixture_path.exists()


def test_positive_acceptance_evidence_rejects_vermagic_mismatch() -> None:
    ok = positive_acceptance_evidence_ok(
        {
            "build_status": "built",
            "validation_status": "passed",
            "module_path": "/tmp/patchweaver.ko",
            "module_exists": True,
            "module_vermagic": "6.6.18 SMP preempt mod_unload modversions",
            "target_kernel_release": "6.6.102-5.2.an23.x86_64",
            "sample_bucket": "buildable_and_should_pass",
            "screening_tier": "positive_acceptance_confirmed",
        }
    )

    assert ok is False


def test_update_positive_pool_fixture_excludes_kpatch_constraint_cases(tmp_path: Path) -> None:
    fixture_path = tmp_path / "positive.json"
    results = [
        {
            "cve_id": "CVE-2024-26643",
            "screening_tier": "positive_acceptance_confirmed",
            "sample_bucket": "kpatch_constraint",
            "failure_type": "kpatch_constraint_unresolved",
        }
    ]

    added = update_positive_pool_fixture(
        fixture_path=fixture_path,
        results=results,
        screening_round="vtest",
    )

    assert added == []
    assert not fixture_path.exists()


def test_rag_seed_index_annotates_screening_records(tmp_path: Path) -> None:
    seed_path = tmp_path / "rag_seed.json"
    seed_path.write_text(
        '[{"cve_id":"CVE-2024-29999","seed_group":"rag-test","subsystem":"net/demo","summary":"demo fix"}]\n',
        encoding="utf-8",
    )

    seed_index = load_rag_seed_index(seed_path)
    records = annotate_with_rag_seed([{"cve_id": "CVE-2024-29999"}], seed_index)

    assert records[0]["rag_seed_hit"] is True
    assert records[0]["rag_subsystem"] == "net/demo"
    assert records[0]["rag_summary"] == "demo fix"


def test_summarize_reports_positive_pool_gap(tmp_path: Path) -> None:
    fixture_path = tmp_path / "positive.json"
    fixture_path.write_text('[{"cve_id":"CVE-2024-20000"}]\n', encoding="utf-8")
    results = [
        {
            "cve_id": "CVE-2024-29999",
            "sample_bucket": "buildable_and_should_pass",
            "acceptance_role": "positive_acceptance_sample",
            "screening_tier": "positive_acceptance_confirmed",
            "build_status": "built",
            "validation_status": "passed",
            "module_path": "/tmp/patchweaver.ko",
            "module_exists": True,
            "module_vermagic": "6.6.102-5.2.an23.x86_64 SMP preempt mod_unload modversions",
            "target_kernel_release": "6.6.102-5.2.an23.x86_64",
            "stable_bucket_ready": True,
            "positive_pool_candidate": True,
            "rag_seed_hit": True,
            "rag_subsystem": "net/demo",
            "stable_source_alignment_required": True,
        }
    ]

    summary = summarize(results, positive_pool_fixture=fixture_path, positive_pool_target=10)

    assert count_existing_positive_pool(fixture_path) == 1
    assert summary["projected_positive_pool_size"] == 2
    assert summary["positive_pool_gap"] == 8
    assert summary["representative_success_rate"] == 1.0
    assert summary["average_attempts"] == 1.0
    assert summary["rag_subsystem_counts"] == {"net/demo": 1}
    assert summary["stable_source_alignment_required"] == ["CVE-2024-29999"]


def test_summarize_reports_representative_success_rate_and_attempts(tmp_path: Path) -> None:
    fixture_path = tmp_path / "positive.json"
    fixture_path.write_text("[]\n", encoding="utf-8")
    results = [
        {
            "cve_id": "CVE-2024-29991",
            "sample_bucket": "buildable_and_should_pass",
            "acceptance_role": "positive_acceptance_sample",
            "screening_tier": "positive_acceptance_confirmed",
            "build_status": "built",
            "validation_status": "passed",
            "module_path": "/tmp/patchweaver.ko",
            "module_exists": True,
            "module_vermagic": "6.6.102-5.2.an23.x86_64 SMP preempt mod_unload modversions",
            "target_kernel_release": "6.6.102-5.2.an23.x86_64",
            "run_attempts": [{"run_index": 1}, {"run_index": 2}],
        },
        {
            "cve_id": "CVE-2024-29992",
            "sample_bucket": "kpatch_constraint",
            "screening_tier": "blocked_by_kpatch_constraint",
            "build_status": "failed",
            "validation_status": "",
            "failure_type": "kpatch_constraint",
            "run_attempts": [{"run_index": 1}, {"run_index": 2}, {"run_index": 3}],
        },
    ]

    summary = summarize(results, positive_pool_fixture=fixture_path, positive_pool_target=10)

    assert summary["representative_total"] == 2
    assert summary["representative_success_rate"] == 0.5
    assert summary["average_attempts"] == 2.5


def test_load_full_artifacts_exposes_patch_apply_source_alignment(tmp_path: Path) -> None:
    task_id = "poolscan-29999"
    attempt_dir = tmp_path / task_id / "attempts" / "001"
    (attempt_dir / "logs").mkdir(parents=True)
    (attempt_dir / "artifacts").mkdir()
    (attempt_dir / "logs" / "failure_record.json").write_text(
        """
        {
          "failure_type": "patch_apply_failed",
            "diagnostic_details": {
            "patch_apply": {
              "subtype": "source_too_new_or_already_patched",
              "reverse_unpatch_status": "failed",
              "stable_source_alignment_required": true,
              "stable_source_baseline_action": "prepare_unpatched_stable_source_baseline"
            },
            "agent_next_action": {
              "action": "prepare_unpatched_stable_source_baseline"
            }
          }
        }
        """,
        encoding="utf-8",
    )

    artifacts = load_full_artifacts(workspace_root=tmp_path, task_id=task_id)

    assert artifacts["failure_type"] == "patch_apply_failed"
    assert artifacts["patch_apply_subtype"] == "source_too_new_or_already_patched"
    assert artifacts["reverse_unpatch_status"] == "failed"
    assert artifacts["stable_source_alignment_required"] is True
    assert artifacts["stable_source_baseline_action"] == "prepare_unpatched_stable_source_baseline"
    assert artifacts["agent_next_action"] == "prepare_unpatched_stable_source_baseline"


def test_write_markdown_report_marks_source_alignment_required(tmp_path: Path) -> None:
    report_path = tmp_path / "screening.md"
    payload = {
        "mode": "full",
        "profile": "dev",
        "task_prefix": "poolscan",
        "run_timeout_sec": 900,
        "only_positive_candidates": True,
        "workspace_root": str(tmp_path / "workspaces"),
        "summary": {
            "total_cases": 1,
            "confirmed_positive_acceptance": [],
            "positive_pool_candidates": [],
            "stable_bucket_ready": [],
            "current_positive_pool_size": 2,
            "positive_pool_target": 10,
            "positive_pool_gap": 8,
            "rag_seed_hits": [],
            "known_pool_skipped": [],
            "stable_source_alignment_required": ["CVE-2024-29999"],
            "bucket_counts": {"unbucketed": 1},
            "rag_subsystem_counts": {},
        },
        "results": [
            {
                "cve_id": "CVE-2024-29999",
                "task_id": "poolscan-29999",
                "failure_type": "patch_apply_failed",
                "stable_source_alignment_required": True,
                "agent_next_action": "prepare_unpatched_stable_source_baseline",
                "reason": "需要准备未修复 stable source 基线",
            }
        ],
    }

    write_markdown_report(report_path=report_path, payload=payload)

    text = report_path.read_text(encoding="utf-8")
    assert "stable_source_alignment_required: `1`" in text
    assert "| CVE-2024-29999 | `poolscan-29999` |" in text
    assert "`required`" in text
    assert "`prepare_unpatched_stable_source_baseline`" in text
