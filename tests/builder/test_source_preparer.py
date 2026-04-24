from __future__ import annotations

from pathlib import Path

import yaml

from patchweaver.builder.source_preparer import _patch_setlocalversion, _write_prepared_path_to_build_config


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
    assert second is False
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
