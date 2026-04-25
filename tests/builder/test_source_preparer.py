from __future__ import annotations

import json
import subprocess
from pathlib import Path

import yaml

from patchweaver.builder.source_preparer import (
    _maybe_warm_prepared_tree,
    _patch_setlocalversion,
    _warmup_marker_path,
    _write_prepared_path_to_build_config,
)


def test_patch_setlocalversion_accepts_save_scmversion(tmp_path: Path) -> None:
    source_dir = tmp_path / "kernel"
    scripts_dir = source_dir / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    script_path = scripts_dir / "setlocalversion"
    script_path.write_text(
        "#!/bin/sh\nset -e\nif [ -z \"${KERNELVERSION}\" ]; then\n\techo fail\nfi\nprintf 'ok\\n'\n",
        encoding="utf-8",
    )

    first = _patch_setlocalversion(source_dir)
    second = _patch_setlocalversion(source_dir)
    patched = script_path.read_text(encoding="utf-8")

    assert first is True
    assert second is True
    assert patched.startswith("#!/bin/sh\n")
    assert '--save-scmversion' in patched
    assert patched.count('--save-scmversion') == 1
    assert 'KERNELVERSION="$(cat include/config/kernel.release)"' in patched


def test_write_prepared_path_to_build_config_inserts_priority(tmp_path: Path) -> None:
    build_config_path = tmp_path / "build.yaml"
    build_config_path.write_text(
        yaml.safe_dump(
            {
                "clean_kernel_src_dir": "",
                "kernel_src_dir": "/opt/kernel-src",
                "build_source_priority": ["clean_kernel_src_dir", "kernel_src_dir"],
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    prepared_path = Path("/opt/patchweaver/kernel-src-prepared/6.6.102-5.2.an23.x86_64")
    _write_prepared_path_to_build_config(build_config_path, prepared_path)
    payload = yaml.safe_load(build_config_path.read_text(encoding="utf-8"))

    assert payload["prepared_kernel_src_dir"] == str(prepared_path)
    assert payload["build_source_priority"] == [
        "clean_kernel_src_dir",
        "prepared_kernel_src_dir",
        "kernel_src_dir",
    ]


def test_maybe_warm_prepared_tree_reuses_marker(tmp_path: Path, monkeypatch) -> None:
    source_dir = tmp_path / "kernel"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "Makefile").write_text("all:\n\t@echo ok\n", encoding="utf-8")

    calls: list[list[str]] = []

    def fake_run(command, cwd=None, stdout=None, stderr=None, text=None, encoding=None, errors=None, check=None):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("patchweaver.builder.source_preparer.subprocess.run", fake_run)

    first = _maybe_warm_prepared_tree(source_dir, warm_targets=["vmlinux"], warm_jobs=12, force=False)
    second = _maybe_warm_prepared_tree(source_dir, warm_targets=["vmlinux"], warm_jobs=12, force=False)

    marker_path = _warmup_marker_path(source_dir)
    marker_payload = json.loads(marker_path.read_text(encoding="utf-8"))

    assert first is True
    assert second is False
    assert calls == [["make", "-j12", "vmlinux"]]
    assert marker_payload["targets"] == ["vmlinux"]
    assert marker_payload["jobs"] == 12
