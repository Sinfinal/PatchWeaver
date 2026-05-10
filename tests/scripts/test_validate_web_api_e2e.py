from __future__ import annotations

from scripts.validate_web_api_e2e import _find_module_path, _validation_status


def test_web_api_e2e_extracts_module_path_from_latest_attempt() -> None:
    payload = {
        "attempts": [
            {"module_path": "old.ko"},
            {"module_path": "workspaces/task/attempts/001/output/patchweaver.ko"},
        ]
    }

    assert _find_module_path(payload, {}) == "workspaces/task/attempts/001/output/patchweaver.ko"


def test_web_api_e2e_detects_validation_status_from_detail() -> None:
    detail = {"latest_validation": {"status": "passed"}}

    assert _validation_status(detail, {}) == "passed"
