from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from patchweaver.harness.semantic_guard_screening import build_semantic_guard_candidate, classify_guard_category
from scripts.screen_semantic_guard_candidates import (
    build_rag_seed_records,
    build_remote_analyze_command,
    build_validation_plan,
    discover_artifact_dirs,
    load_rag_seed_index,
    load_record,
    parse_args,
    screen_records,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("text", "category"),
    [
        ("if (!skb) return -EFAULT; /* NULL pointer */", "null"),
        ("if (len > PAGE_SIZE) return -EINVAL;", "size_len"),
        ("reject out-of-bounds index range", "bounds"),
        ("check_add_overflow(size, count, &total)", "overflow"),
        ("device is not ready and enters invalid state", "invalid_state"),
    ],
)
def test_classify_guard_category_covers_requested_buckets(text: str, category: str) -> None:
    assert classify_guard_category(text)[0] == category


def test_build_semantic_guard_candidate_scores_guard_patch() -> None:
    patch_text = "\n".join(
        [
            "diff --git a/drivers/demo.c b/drivers/demo.c",
            "--- a/drivers/demo.c",
            "+++ b/drivers/demo.c",
            "@@ -10,6 +10,9 @@ int demo_parse(char *buf, size_t len)",
            "+if (!buf || len > PAGE_SIZE)",
            "+    return -EINVAL;",
            " return 0;",
            "",
        ]
    )
    record = {
        "cve_id": "CVE-2024-29999",
        "task_id": "sgscreen-29999",
        "patch_text": patch_text,
        "patch_bundle": {
            "affected_files": ["drivers/demo.c"],
            "commit_message": "demo: reject NULL buffer and invalid length",
        },
        "semantic_card": {
            "must_keep_conditions": ["!buf", "len > PAGE_SIZE"],
            "touched_files": ["drivers/demo.c"],
            "touched_functions": ["demo_parse"],
        },
        "constraint_report": {"preferred_route": "direct_apply_patch"},
    }

    candidate = build_semantic_guard_candidate(record, min_confidence=0.55)

    assert candidate is not None
    assert candidate.cve_id == "CVE-2024-29999"
    assert candidate.guard_category == "null"
    assert candidate.confidence >= 0.75
    assert candidate.suggested_validation_mode in {"analyze", "single-cve-full-run-with-timeout"}
    assert candidate.affected_files == ["drivers/demo.c"]


def test_screen_records_filters_low_confidence_non_guard() -> None:
    records = [
        {
            "cve_id": "CVE-2024-29998",
            "patch_text": "diff --git a/a.c b/a.c\n+static int global_state;\n",
            "semantic_card": {"root_cause": "large refactor"},
        }
    ]

    assert screen_records(records, min_confidence=0.55, max_candidates=10, cves=None) == []


def test_screen_records_keeps_best_record_per_cve() -> None:
    records = [
        {
            "cve_id": "CVE-2024-29988",
            "task_id": "old",
            "patch_text": "",
            "semantic_card": {"root_cause": "NULL pointer", "touched_files": ["a.c"]},
            "affected_files": ["a.c"],
        },
        {
            "cve_id": "CVE-2024-29988",
            "task_id": "new",
            "patch_text": "diff --git a/a.c b/a.c\n+if (!p)\n+    return -EFAULT;\n",
            "semantic_card": {"root_cause": "NULL pointer", "must_keep_conditions": ["!p"], "touched_files": ["a.c"]},
            "affected_files": ["a.c"],
        },
    ]

    candidates = screen_records(records, min_confidence=0.55, max_candidates=10, cves=None)

    assert len(candidates) == 1
    assert candidates[0].task_id == "new"


def test_load_record_reads_workspace_style_artifacts(tmp_path: Path) -> None:
    task_dir = tmp_path / "TASK-CVE"
    (task_dir / "analysis").mkdir(parents=True)
    (task_dir / "input").mkdir()
    (task_dir / "normalized").mkdir()
    (task_dir / "task_context.json").write_text(
        json.dumps({"task_id": "TASK-CVE", "cve_id": "CVE-2024-29997"}),
        encoding="utf-8",
    )
    (task_dir / "input" / "patch_bundle.json").write_text(
        json.dumps({"cve_id": "CVE-2024-29997", "affected_files": ["net/demo.c"]}),
        encoding="utf-8",
    )
    (task_dir / "analysis" / "semantic_card.json").write_text(
        json.dumps({"must_keep_conditions": ["idx >= limit"], "touched_files": ["net/demo.c"]}),
        encoding="utf-8",
    )
    (task_dir / "normalized" / "normalized.patch").write_text(
        "diff --git a/net/demo.c b/net/demo.c\n+if (idx >= limit)\n+    return -EINVAL;\n",
        encoding="utf-8",
    )
    seed_index = {"CVE-2024-29997": {"subsystem": "net/demo", "summary": "fix bounds check"}}

    record = load_record(task_dir, seed_index)

    assert record is not None
    assert record["cve_id"] == "CVE-2024-29997"
    assert record["rag_seed"]["subsystem"] == "net/demo"
    assert record["patch_shape"]["guard_like"] is True
    assert discover_artifact_dirs([tmp_path]) == [task_dir]


def test_build_validation_plan_dry_run_limits_to_two_candidates(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "screen_semantic_guard_candidates.py",
            "--output",
            str(tmp_path / "out.json"),
            "--validation-mode",
            "dry-run",
        ],
    )
    args = parse_args()
    candidates = [
        _candidate("CVE-2024-29991"),
        _candidate("CVE-2024-29992"),
        _candidate("CVE-2024-29993"),
    ]

    plan = build_validation_plan(args, candidates)

    assert plan["executed"] is False
    assert plan["selected_cves"] == ["CVE-2024-29991", "CVE-2024-29992"]
    assert len(plan["commands"]) == 2
    assert "patchweaver analyze --task sgscreen-29991" in plan["commands"][0]


def test_build_validation_plan_rejects_more_than_two_validation_cves(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "screen_semantic_guard_candidates.py",
            "--output",
            str(tmp_path / "out.json"),
            "--validation-mode",
            "dry-run",
            "--validation-cve",
            "CVE-2024-1",
            "--validation-cve",
            "CVE-2024-2",
            "--validation-cve",
            "CVE-2024-3",
        ],
    )
    args = parse_args()

    with pytest.raises(ValueError, match="最多允许指定 2 条"):
        build_validation_plan(args, [])


def test_remote_analyze_command_always_has_timeout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "screen_semantic_guard_candidates.py",
            "--output",
            str(tmp_path / "out.json"),
            "--remote-timeout-sec",
            "123",
        ],
    )
    args = parse_args()

    command = build_remote_analyze_command(args, "CVE-2024-29990")

    assert "timeout 123s" in command
    assert "patchweaver create --cve CVE-2024-29990" in command
    assert "patchweaver analyze --task sgscreen-29990" in command


def test_load_rag_seed_index(tmp_path: Path) -> None:
    seed_path = tmp_path / "seed.json"
    seed_path.write_text('[{"cve_id":"CVE-2024-29989","summary":"fix overflow"}]\n', encoding="utf-8")

    index = load_rag_seed_index(seed_path)

    assert index["CVE-2024-29989"]["summary"] == "fix overflow"


def test_rag_seed_only_record_can_be_screened_as_dry_run_candidate() -> None:
    records = build_rag_seed_records(
        {
            "CVE-2024-29987": {
                "cve_id": "CVE-2024-29987",
                "subsystem": "drivers/phy",
                "summary": "phy: fix NULL pointer dereference before SRP setup",
            }
        }
    )

    candidates = screen_records(records, min_confidence=0.55, max_candidates=10, cves=None)

    assert len(candidates) == 1
    assert candidates[0].guard_category == "null"
    assert candidates[0].suggested_validation_mode == "dry-run"
    assert candidates[0].rag_seed_hit is True


def test_screen_semantic_guard_candidates_help_runs() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/screen_semantic_guard_candidates.py", "--help"],
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert "semantic_guard_rewrite" in proc.stdout
    assert "--validation-mode" in proc.stdout
    assert "--remote-timeout-sec" in proc.stdout


def _candidate(cve_id: str):
    from patchweaver.harness.semantic_guard_screening import SemanticGuardCandidate

    return SemanticGuardCandidate(
        cve_id=cve_id,
        guard_category="null",
        confidence=0.8,
        affected_files=["drivers/demo.c"],
        reason="test",
        suggested_validation_mode="analyze",
    )
