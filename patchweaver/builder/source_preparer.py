"""验证机构建源码树准备工具"""

from __future__ import annotations

import json
import shutil
import subprocess
import tarfile
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml


@dataclass(slots=True)
class PreparedSourceTreeResult:
    """记录一次源码树准备结果"""

    kernel_release: str
    kernel_devel_package: str
    output_dir: str
    srpm_path: str
    source_tarball: str
    overlay_dirs: list[str]
    config_path: str | None
    setlocalversion_patched: bool
    build_config_path: str | None = None
    reused_existing: bool = False

    def to_payload(self) -> dict[str, object]:
        """转成可直接输出的结构化结果"""

        return asdict(self)


def prepare_validation_source_tree(
    *,
    kernel_release: str,
    output_dir: Path,
    overlay_dirs: list[Path],
    force: bool = False,
    work_dir: Path | None = None,
    dnf_cmd: str = "dnf",
    kernel_devel_package: str | None = None,
    build_config_path: Path | None = None,
    write_build_config: bool = False,
) -> PreparedSourceTreeResult:
    """准备可供 kpatch-build 使用的完整源码树"""

    package_name = kernel_devel_package or f"kernel-devel-{kernel_release}"
    normalized_output_dir = output_dir.resolve()
    if normalized_output_dir.exists():
        if force:
            shutil.rmtree(normalized_output_dir)
        elif _looks_like_prepared_tree(normalized_output_dir):
            patched = _patch_setlocalversion(normalized_output_dir)
            if write_build_config and build_config_path is not None:
                _write_prepared_path_to_build_config(build_config_path, normalized_output_dir)
            return PreparedSourceTreeResult(
                kernel_release=kernel_release,
                kernel_devel_package=package_name,
                output_dir=str(normalized_output_dir),
                srpm_path="",
                source_tarball="",
                overlay_dirs=[str(path) for path in overlay_dirs if path.exists()],
                config_path=str(_resolve_config_path(normalized_output_dir)) if _resolve_config_path(normalized_output_dir) else None,
                setlocalversion_patched=patched,
                build_config_path=str(build_config_path.resolve()) if write_build_config and build_config_path is not None else None,
                reused_existing=True,
            )
        else:
            raise RuntimeError(f"目标目录已存在但不是可复用的源码树: {normalized_output_dir}")

    prepared_temp_root = Path(work_dir) if work_dir is not None else Path(tempfile.mkdtemp(prefix="patchweaver-source-"))
    srpm_dir = prepared_temp_root / "srpm"
    extract_dir = prepared_temp_root / "extract"
    unpack_dir = prepared_temp_root / "unpack"
    srpm_dir.mkdir(parents=True, exist_ok=True)
    extract_dir.mkdir(parents=True, exist_ok=True)
    unpack_dir.mkdir(parents=True, exist_ok=True)

    _run_command(
        [
            dnf_cmd,
            "download",
            "--source",
            "--destdir",
            str(srpm_dir),
            package_name,
        ]
    )

    srpm_candidates = sorted(srpm_dir.glob("*.src.rpm"))
    if not srpm_candidates:
        raise RuntimeError(f"未下载到 source rpm: {package_name}")
    srpm_path = srpm_candidates[-1]

    extract_script = (
        f"set -e\n"
        f"cd {shlex_quote(str(extract_dir))}\n"
        f"rpm2cpio {shlex_quote(str(srpm_path))} | cpio -idmu >/dev/null 2>&1\n"
    )
    _run_shell_script(extract_script)

    tarball_candidates = sorted(extract_dir.glob("linux-*.tar.*"))
    if not tarball_candidates:
        raise RuntimeError(f"在 {extract_dir} 中未找到 linux 源码压缩包")
    tarball_path = tarball_candidates[-1]

    with tarfile.open(tarball_path) as archive:
        archive.extractall(unpack_dir)

    extracted_roots = [path for path in unpack_dir.iterdir() if path.is_dir()]
    if len(extracted_roots) != 1:
        raise RuntimeError(f"源码压缩包解压结果异常: {unpack_dir}")
    extracted_root = extracted_roots[0]

    normalized_output_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(extracted_root), str(normalized_output_dir))

    effective_overlay_dirs = [path for path in overlay_dirs if path.exists()]
    for overlay_dir in effective_overlay_dirs:
        _overlay_tree(overlay_dir, normalized_output_dir)

    config_path = _resolve_config_path(normalized_output_dir)
    if config_path is None:
        boot_config = Path(f"/boot/config-{kernel_release}")
        if boot_config.exists():
            shutil.copy2(boot_config, normalized_output_dir / ".config")
            config_path = normalized_output_dir / ".config"

    setlocalversion_patched = _patch_setlocalversion(normalized_output_dir)

    manifest_path = normalized_output_dir / "patchweaver_source_prepare.json"
    result = PreparedSourceTreeResult(
        kernel_release=kernel_release,
        kernel_devel_package=package_name,
        output_dir=str(normalized_output_dir),
        srpm_path=str(srpm_path),
        source_tarball=str(tarball_path),
        overlay_dirs=[str(path) for path in effective_overlay_dirs],
        config_path=str(config_path) if config_path is not None else None,
        setlocalversion_patched=setlocalversion_patched,
        build_config_path=str(build_config_path.resolve()) if write_build_config and build_config_path is not None else None,
        reused_existing=False,
    )
    manifest_path.write_text(json.dumps(result.to_payload(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if write_build_config and build_config_path is not None:
        _write_prepared_path_to_build_config(build_config_path, normalized_output_dir)

    return result


def _run_command(command: list[str]) -> None:
    """执行命令并在失败时抛出完整错误"""

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "命令执行失败\n"
            f"command: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


def _run_shell_script(script: str) -> None:
    """通过 bash 执行一段脚本"""

    _run_command(["bash", "-lc", script])


def _looks_like_prepared_tree(path: Path) -> bool:
    """判断目录是否已经是一棵可复用的完整源码树"""

    return path.is_dir() and (path / "Makefile").exists() and (path / "scripts" / "setlocalversion").exists()


def _resolve_config_path(source_dir: Path) -> Path | None:
    """返回源码树中的 .config 路径"""

    config_path = source_dir / ".config"
    return config_path if config_path.exists() else None


def _overlay_tree(source_dir: Path, target_dir: Path) -> None:
    """把一棵已有源码树覆盖到目标完整源码树上"""

    script = (
        f"set -e\n"
        f"mkdir -p {shlex_quote(str(target_dir))}\n"
        f"cp -a {shlex_quote(str(source_dir))}/. {shlex_quote(str(target_dir))}/\n"
    )
    _run_shell_script(script)


def _patch_setlocalversion(source_dir: Path) -> bool:
    """让 vendor kernel 的 setlocalversion 忽略 --save-scmversion"""

    script_path = source_dir / "scripts" / "setlocalversion"
    if not script_path.exists():
        return False

    original = script_path.read_text(encoding="utf-8", errors="replace")
    updated = original

    save_scm_block = (
        'if [ "$1" = "--save-scmversion" ]; then\n'
        "    shift\n"
        "fi\n"
    )
    kernel_release_block = (
        'if [ -z "${KERNELVERSION}" ] && [ -f include/config/kernel.release ]; then\n'
        '    KERNELVERSION="$(cat include/config/kernel.release)"\n'
        "fi\n\n"
    )

    shebang = ""
    body = updated
    if body.startswith("#!"):
        shebang, _, body = body.partition("\n")
        shebang += "\n"

    if "--save-scmversion" not in body:
        marker = "set -e\n"
        injected = "set -e\n\n" + save_scm_block
        if marker in body:
            body = body.replace(marker, injected, 1)
        else:
            body = save_scm_block + body

    if 'KERNELVERSION="$(cat include/config/kernel.release)"' not in body:
        marker = 'if [ -z "${KERNELVERSION}" ]; then\n'
        if marker in body:
            body = body.replace(marker, kernel_release_block + marker, 1)

    updated = shebang + body
    if updated == original:
        return False

    script_path.write_text(updated, encoding="utf-8")
    script_path.chmod(script_path.stat().st_mode | 0o111)
    return True


def _write_prepared_path_to_build_config(build_config_path: Path, prepared_path: Path) -> None:
    """把 prepared_kernel_src_dir 写回构建配置"""

    payload = yaml.safe_load(build_config_path.read_text(encoding="utf-8")) or {}
    payload["prepared_kernel_src_dir"] = str(prepared_path)

    priority = list(payload.get("build_source_priority") or [])
    if "prepared_kernel_src_dir" not in priority:
        if "clean_kernel_src_dir" in priority:
            insert_at = priority.index("clean_kernel_src_dir") + 1
            priority.insert(insert_at, "prepared_kernel_src_dir")
        else:
            priority.insert(0, "prepared_kernel_src_dir")
    payload["build_source_priority"] = priority

    build_config_path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def shlex_quote(value: str) -> str:
    """为 bash 脚本转义路径"""

    return "'" + value.replace("'", "'\"'\"'") + "'"
