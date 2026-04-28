from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.screen_challenge_pool import (
    apply_module_target_gate,
    annotate_with_rag_seed,
    count_existing_positive_pool,
    infer_build_targets_for_record,
    load_cves,
    load_rag_seed_index,
    parse_posix_descendant_process_groups,
    parse_args,
    should_continue_run,
    summarize,
    update_positive_pool_fixture,
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


def test_update_positive_pool_fixture_appends_confirmed_cases(tmp_path: Path) -> None:
    fixture_path = tmp_path / "positive.json"
    results = [
        {
            "cve_id": "CVE-2024-29999",
            "screening_tier": "positive_acceptance_confirmed",
        }
    ]

    added = update_positive_pool_fixture(
        fixture_path=fixture_path,
        results=results,
        screening_round="vtest",
    )

    assert added == ["CVE-2024-29999"]
    assert "CVE-2024-29999" in fixture_path.read_text(encoding="utf-8")


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
            "stable_bucket_ready": True,
            "positive_pool_candidate": True,
            "rag_seed_hit": True,
            "rag_subsystem": "net/demo",
        }
    ]

    summary = summarize(results, positive_pool_fixture=fixture_path, positive_pool_target=10)

    assert count_existing_positive_pool(fixture_path) == 1
    assert summary["projected_positive_pool_size"] == 2
    assert summary["positive_pool_gap"] == 8
    assert summary["rag_subsystem_counts"] == {"net/demo": 1}
