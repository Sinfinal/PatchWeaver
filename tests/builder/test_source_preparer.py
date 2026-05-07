from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from patchweaver.builder.source_preparer import (
    _build_cache_ready,
    _build_cache_snapshot,
    _write_vendor_path_to_build_config,
    check_vendor_source_baseline,
    _maybe_warm_prepared_tree,
    _patch_setlocalversion,
    _resolve_stable_snapshot_commit,
    _warmup_marker_path,
    _write_prepared_path_to_build_config,
    _write_stable_path_to_build_config,
    prepare_stable_source_baseline,
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


def test_write_vendor_path_to_build_config_inserts_priority(tmp_path: Path) -> None:
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

    vendor_path = Path("/home/patchweaver/vendor-baselines/6.6.102-5.2.an23.x86_64")
    _write_vendor_path_to_build_config(build_config_path, vendor_path)
    payload = yaml.safe_load(build_config_path.read_text(encoding="utf-8"))

    assert payload["vendor_kernel_src_dir"] == str(vendor_path)
    assert payload["build_source_priority"] == [
        "clean_kernel_src_dir",
        "vendor_kernel_src_dir",
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


def test_build_cache_snapshot_requires_vmlinux_artifacts(tmp_path: Path) -> None:
    source_dir = tmp_path / "kernel"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "Module.symvers").write_text("fake symvers\n", encoding="utf-8")
    (source_dir / "vmlinux.o").write_text("fake vmlinux.o\n", encoding="utf-8")
    (source_dir / "vmlinux").write_text("fake vmlinux\n", encoding="utf-8")

    snapshot = _build_cache_snapshot(source_dir)

    assert snapshot == {
        "Module.symvers": True,
        "vmlinux.o": True,
        "vmlinux": True,
        "vmlinux.a": False,
        ".vmlinux.objs": False,
    }
    assert _build_cache_ready(snapshot) is True


def test_build_cache_ready_accepts_legacy_vmlinux_inputs(tmp_path: Path) -> None:
    source_dir = tmp_path / "kernel"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "Module.symvers").write_text("fake symvers\n", encoding="utf-8")
    (source_dir / "vmlinux.o").write_text("fake vmlinux.o\n", encoding="utf-8")
    (source_dir / "vmlinux.a").write_text("fake vmlinux.a\n", encoding="utf-8")
    (source_dir / ".vmlinux.objs").write_text("fake .vmlinux.objs\n", encoding="utf-8")

    snapshot = _build_cache_snapshot(source_dir)

    assert _build_cache_ready(snapshot) is True


def test_check_vendor_source_baseline_requires_exact_release_cache_and_patch_apply(tmp_path: Path) -> None:
    source_dir = tmp_path / "vendor"
    (source_dir / "scripts").mkdir(parents=True)
    (source_dir / "include" / "config").mkdir(parents=True)
    (source_dir / "drivers" / "demo").mkdir(parents=True)
    (source_dir / "Makefile").write_text("obj-m := drivers/demo/\n", encoding="utf-8")
    (source_dir / "scripts" / "setlocalversion").write_text("#!/bin/sh\n", encoding="utf-8")
    (source_dir / ".config").write_text("CONFIG_DEMO=m\n", encoding="utf-8")
    (source_dir / "include" / "config" / "kernel.release").write_text("6.6.102-5.2.an23.x86_64\n", encoding="utf-8")
    for name in ["Module.symvers", "vmlinux", "vmlinux.o", "vmlinux.a", ".vmlinux.objs"]:
        (source_dir / name).write_text("cache\n", encoding="utf-8")
    (source_dir / "drivers" / "demo" / "demo.c").write_text("int demo(void) { return 0; }\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=source_dir, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    subprocess.run(["git", "config", "user.email", "patchweaver@example.invalid"], cwd=source_dir, check=True)
    subprocess.run(["git", "config", "user.name", "PatchWeaver"], cwd=source_dir, check=True)
    subprocess.run(["git", "add", "."], cwd=source_dir, check=True)
    subprocess.run(["git", "commit", "-m", "vendor baseline"], cwd=source_dir, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    patch_path = tmp_path / "fix.patch"
    patch_path.write_text(
        "\n".join(
            [
                "diff --git a/drivers/demo/demo.c b/drivers/demo/demo.c",
                "--- a/drivers/demo/demo.c",
                "+++ b/drivers/demo/demo.c",
                "@@ -1 +1 @@",
                "-int demo(void) { return 0; }",
                "+int demo(void) { return 1; }",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    vmlinux_path = tmp_path / "debug-vmlinux"
    vmlinux_path.write_text("debug\n", encoding="utf-8")

    result = check_vendor_source_baseline(
        source_dir=source_dir,
        target_kernel="6.6.102-5.2.an23.x86_64",
        patch_path=patch_path,
        vmlinux_path=vmlinux_path,
    )

    assert result.vendor_baseline_ready is True
    assert result.kernel_release_matches is True
    assert result.build_cache_ready is True
    assert result.patch_apply_ok is True
    assert result.unpatched_state_verified is True
    assert result.problems == []


def test_check_vendor_source_baseline_rejects_stable_release_mismatch(tmp_path: Path) -> None:
    source_dir = tmp_path / "stable"
    (source_dir / "scripts").mkdir(parents=True)
    (source_dir / "include" / "config").mkdir(parents=True)
    (source_dir / "Makefile").write_text("all:\n\t@echo ok\n", encoding="utf-8")
    (source_dir / "scripts" / "setlocalversion").write_text("#!/bin/sh\n", encoding="utf-8")
    (source_dir / ".config").write_text("CONFIG_DEMO=m\n", encoding="utf-8")
    (source_dir / "include" / "config" / "kernel.release").write_text("6.6.17\n", encoding="utf-8")
    for name in ["Module.symvers", "vmlinux", "vmlinux.o", "vmlinux.a", ".vmlinux.objs"]:
        (source_dir / name).write_text("cache\n", encoding="utf-8")

    result = check_vendor_source_baseline(
        source_dir=source_dir,
        target_kernel="6.6.102-5.2.an23.x86_64",
    )

    assert result.vendor_baseline_ready is False
    assert result.kernel_release_matches is False
    assert "kernel_release_mismatch" in result.problems
    assert "patch_not_provided_unpatched_state_unknown" in result.problems


def test_write_stable_path_to_build_config_inserts_priority(tmp_path: Path) -> None:
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

    stable_path = Path("/opt/patchweaver/stable-baselines/demo")
    _write_stable_path_to_build_config(build_config_path, stable_path)
    payload = yaml.safe_load(build_config_path.read_text(encoding="utf-8"))

    assert payload["stable_kernel_src_dir"] == str(stable_path)
    assert payload["build_source_priority"] == [
        "clean_kernel_src_dir",
        "kernel_src_dir",
        "stable_kernel_src_dir",
    ]


def test_prepare_stable_source_baseline_uses_git_worktree(tmp_path: Path) -> None:
    if shutil.which("git") is None:
        pytest.skip("git not available")

    repo = tmp_path / "linux-stable"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    subprocess.run(["git", "config", "user.email", "patchweaver@example.invalid"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "PatchWeaver"], cwd=repo, check=True)
    (repo / "Makefile").write_text("all:\n\t@echo ok\n", encoding="utf-8")
    scripts_dir = repo / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "setlocalversion").write_text("#!/bin/sh\nset -e\necho ok\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    base_ref = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    (repo / "demo.c").write_text("int demo(void) { return 1; }\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "fix"], cwd=repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    config_source = tmp_path / ".config"
    config_source.write_text("CONFIG_DEMO=m\n", encoding="utf-8")

    result = prepare_stable_source_baseline(
        stable_git_dir=repo,
        baseline_ref="HEAD^",
        output_root=tmp_path / "baselines",
        config_source=config_source,
    )

    output_dir = Path(result.output_dir)
    assert result.git_head == base_ref
    assert (output_dir / "Makefile").exists()
    assert (output_dir / ".config").read_text(encoding="utf-8") == "CONFIG_DEMO=m\n"
    assert not (output_dir / "demo.c").exists()


def test_prepare_stable_source_baseline_copies_build_cache_from_config_source(tmp_path: Path) -> None:
    if shutil.which("git") is None:
        pytest.skip("git not available")

    repo = tmp_path / "linux-stable"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    subprocess.run(["git", "config", "user.email", "patchweaver@example.invalid"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "PatchWeaver"], cwd=repo, check=True)
    (repo / "Makefile").write_text("all:\n\t@echo ok\n", encoding="utf-8")
    scripts_dir = repo / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "setlocalversion").write_text("#!/bin/sh\nset -e\necho ok\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    prepared_source = tmp_path / "prepared"
    (prepared_source / "include" / "config").mkdir(parents=True)
    (prepared_source / "include" / "generated").mkdir(parents=True)
    (prepared_source / ".config").write_text("CONFIG_DEMO=m\n", encoding="utf-8")
    (prepared_source / "include" / "config" / "kernel.release").write_text("6.6.102-5.2.an23.x86_64\n", encoding="utf-8")
    (prepared_source / "include" / "generated" / "utsrelease.h").write_text(
        '#define UTS_RELEASE "6.6.102-5.2.an23.x86_64"\n',
        encoding="utf-8",
    )
    for name in ["Module.symvers", "vmlinux.o", "vmlinux"]:
        (prepared_source / name).write_text(f"{name}\n", encoding="utf-8")

    result = prepare_stable_source_baseline(
        stable_git_dir=repo,
        baseline_ref="HEAD",
        output_root=tmp_path / "baselines",
        config_source=prepared_source / ".config",
    )

    output_dir = Path(result.output_dir)
    assert result.build_cache_source == str(prepared_source.resolve())
    assert result.build_cache_ready is True
    assert result.build_cache_files is not None
    assert result.build_cache_files["Module.symvers"] is True
    assert (output_dir / "Module.symvers").read_text(encoding="utf-8") == "Module.symvers\n"
    assert (output_dir / "include" / "config" / "kernel.release").read_text(encoding="utf-8") == "6.6.102-5.2.an23.x86_64\n"


def test_prepare_stable_source_baseline_falls_back_to_snapshot(monkeypatch, tmp_path: Path) -> None:
    config_source = tmp_path / ".config"
    config_source.write_text("CONFIG_DEMO=m\n", encoding="utf-8")

    monkeypatch.setattr(
        "patchweaver.builder.source_preparer._resolve_stable_snapshot_commit",
        lambda baseline_ref: "a" * 40,
    )

    def fake_download_snapshot(*, commit_id: str, output_dir: Path) -> None:
        scripts_dir = output_dir / "scripts"
        scripts_dir.mkdir(parents=True)
        (output_dir / "Makefile").write_text("all:\n\t@echo ok\n", encoding="utf-8")
        (scripts_dir / "setlocalversion").write_text("#!/bin/sh\nset -e\necho ok\n", encoding="utf-8")

    monkeypatch.setattr(
        "patchweaver.builder.source_preparer._download_and_extract_stable_snapshot",
        fake_download_snapshot,
    )

    result = prepare_stable_source_baseline(
        stable_git_dir=tmp_path / "missing-stable-repo",
        baseline_ref="b" * 40 + "^",
        output_root=tmp_path / "baselines",
        config_source=config_source,
    )

    output_dir = Path(result.output_dir)
    assert output_dir.exists()
    assert (output_dir / ".config").read_text(encoding="utf-8") == "CONFIG_DEMO=m\n"
    assert result.git_head is None


def test_resolve_stable_snapshot_commit_accepts_direct_commit() -> None:
    commit_id = "a" * 40

    assert _resolve_stable_snapshot_commit(commit_id) == commit_id
