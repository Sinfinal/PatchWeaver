from __future__ import annotations

from patchweaver.doctor.service import DoctorService
from patchweaver.models.doctor import DoctorCheck


def test_doctor_service_builds_summary_counts() -> None:
    report = DoctorService().build_report(
        runtime={"python": "3.11", "platform": "win-64"},
        checks=[
            DoctorCheck(category="runtime", name="python", label="Python", ok=True, status="ok", detail="ok"),
            DoctorCheck(category="build", name="kernel", label="Kernel", ok=False, status="warn", detail="missing"),
            DoctorCheck(category="ssh", name="remote", label="Remote", ok=False, status="error", detail="offline"),
        ],
    )

    assert report.summary == {"total": 3, "ok": 1, "warn": 1, "error": 1}
    assert report.runtime["python"] == "3.11"
