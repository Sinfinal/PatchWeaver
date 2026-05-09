from __future__ import annotations

import os
import uuid
from pathlib import Path


def pytest_configure(config) -> None:
    """Use project-local isolated temp roots for reliable parallel Windows runs."""

    if getattr(config.option, "basetemp", None):
        return

    project_root = Path(config.rootpath)
    worker_id = os.environ.get("PYTEST_XDIST_WORKER", "main")
    unique_name = f"pytest-{worker_id}-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    basetemp = project_root / "data" / "cache" / "pytest-tmp" / unique_name
    basetemp.mkdir(parents=True, exist_ok=True)
    config.option.basetemp = basetemp
