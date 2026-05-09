from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.plan_p1_expansion_batch import build_payload, plan_candidates, write_markdown


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_plan_p1_expansion_batch_help_runs() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/plan_p1_expansion_batch.py", "--help"],
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert "Plan the next small P1 positive-pool expansion batch" in proc.stdout
    assert "--recent-full-run" in proc.stdout


def test_plan_candidates_excludes_known_pools_and_terminal_recent_failures(tmp_path: Path) -> None:
    rag_seed = write_json(
        tmp_path / "rag.json",
        [
            {"cve_id": "CVE-2024-30001", "subsystem": "drivers/net", "summary": "wifi: fix null pointer"},
            {"cve_id": "CVE-2024-30002", "subsystem": "drivers/usb", "summary": "usb: fix bounds"},
            {"cve_id": "CVE-2024-30003", "subsystem": "drivers/media", "summary": "media: fix oob"},
            {"cve_id": "CVE-2024-30004", "subsystem": "drivers/input", "summary": "input: fix crash"},
            {"cve_id": "CVE-2024-30005", "subsystem": "drivers/hwmon", "summary": "hwmon: fix leak"},
        ],
    )
    confirmed = write_json(tmp_path / "confirmed.json", [{"cve_id": "CVE-2024-30001"}])
    kpatch = write_json(tmp_path / "kpatch.json", [{"cve_id": "CVE-2024-30002"}])
    already = write_json(tmp_path / "already.json", [{"cve_id": "CVE-2024-30003"}])
    recent = write_json(
        tmp_path / "recent.json",
        {
            "results": [
                {"cve_id": "CVE-2024-30004", "failure_type": "target_already_patched"},
                {"cve_id": "CVE-2024-30099", "failure_type": "compile_failed"},
            ]
        },
    )

    candidates, summary = plan_candidates(
        rag_seed_path=rag_seed,
        confirmed_path=confirmed,
        known_kpatch_constraint_path=kpatch,
        already_patched_path=already,
        recent_full_run_paths=[recent],
        max_candidates=10,
    )

    assert [candidate.cve_id for candidate in candidates] == ["CVE-2024-30005"]
    assert summary["excluded_confirmed_count"] == 1
    assert summary["excluded_kpatch_constraint_count"] == 1
    assert summary["excluded_already_patched_count"] == 1
    assert summary["excluded_recent_failure_count"] == 1


def test_plan_candidates_scores_module_like_above_core_subsystems(tmp_path: Path) -> None:
    rag_seed = write_json(
        tmp_path / "rag.json",
        [
            {"cve_id": "CVE-2024-30011", "subsystem": "mm", "summary": "mm: fix null pointer"},
            {"cve_id": "CVE-2024-30012", "subsystem": "drivers/net", "summary": "wifi: fix null pointer"},
        ],
    )
    empty = write_json(tmp_path / "empty.json", [])

    candidates, _summary = plan_candidates(
        rag_seed_path=rag_seed,
        confirmed_path=empty,
        known_kpatch_constraint_path=empty,
        already_patched_path=empty,
        recent_full_run_paths=[],
        max_candidates=10,
    )

    assert candidates[0].cve_id == "CVE-2024-30012"
    assert candidates[0].score > candidates[1].score
    assert "module-like subsystem" in candidates[0].reasons
    assert "lower priority vmlinux/core subsystem" in candidates[1].reasons


def test_payload_and_markdown_include_required_output_structure(tmp_path: Path) -> None:
    rag_seed = write_json(
        tmp_path / "rag.json",
        [{"cve_id": "CVE-2024-30021", "subsystem": "drivers/usb", "summary": "usb: fix bounds"}],
    )
    empty = write_json(tmp_path / "empty.json", [])

    candidates, summary = plan_candidates(
        rag_seed_path=rag_seed,
        confirmed_path=empty,
        known_kpatch_constraint_path=empty,
        already_patched_path=empty,
        recent_full_run_paths=[],
        max_candidates=1,
    )
    payload = build_payload(candidates, summary)
    candidate = payload["candidates"][0]

    assert set(candidate) == {"cve_id", "subsystem", "score", "reasons", "suggested_command_fragment"}
    assert candidate["suggested_command_fragment"].endswith("--cve CVE-2024-30021")

    report_path = tmp_path / "plan.md"
    write_markdown(report_path, payload)
    report = report_path.read_text(encoding="utf-8")

    assert "| CVE | Subsystem | Score | Reasons | Suggested command fragment |" in report
    assert "CVE-2024-30021" in report
