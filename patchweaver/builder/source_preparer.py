"""验证机构建源码树准备工具"""

from __future__ import annotations

import json
import hashlib
import re
import shutil
import subprocess
import tarfile
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

import yaml

WARMUP_MARKER_NAME = "patchweaver_source_warmup.json"
WARMUP_LOG_NAME = "patchweaver_source_warmup.log"


@dataclass(slots=True)
class PreparedSourceTreeResult:
    """记录一次源码树准备结果"""

    kernel_release: str
    kernel_devel_package: str
    output_dir: str
    srpm_path: str | None
    source_tarball: str | None
    overlay_dirs: list[str]
    config_path: str | None
    setlocalversion_patched: bool
    build_config_path: str | None = None
    reused_existing: bool = False
    warmup_targets: list[str] | None = None
    warmup_jobs: int | None = None
    warmup_performed: bool = False
    warmup_marker_path: str | None = None
    warmup_log_path: str | None = None
    build_cache_ready: bool = False
    build_cache_files: dict[str, bool] | None = None

    def to_payload(self) -> dict[str, object]:
        """转成可直接输出的结构化结果"""

        return asdict(self)


@dataclass(slots=True)
class StableBaselineTreeResult:
    """Record one stable source baseline preparation result"""

    stable_git_dir: str
    baseline_ref: str
    output_dir: str
    config_path: str | None
    setlocalversion_patched: bool
    reused_existing: bool = False
    build_config_path: str | None = None
    git_head: str | None = None
    build_cache_source: str | None = None
    build_cache_files: dict[str, bool] | None = None
    build_cache_ready: bool = False

    def to_payload(self) -> dict[str, object]:
        """Convert to serializable payload"""

        return asdict(self)


@dataclass(slots=True)
class VendorBaselineReadiness:
    """Record whether a vendor source baseline can support positive acceptance"""

    source_dir: str
    target_kernel: str
    path_exists: bool
    tree_ok: bool
    config_ok: bool
    kernel_release: str | None
    kernel_release_matches: bool
    required_cache_files: dict[str, bool]
    build_cache_ready: bool
    vmlinux_path: str | None = None
    vmlinux_ok: bool | None = None
    patch_path: str | None = None
    patch_apply_check_run: bool = False
    patch_apply_ok: bool | None = None
    patch_apply_stdout: str = ""
    patch_apply_stderr: str = ""
    unpatched_state_verified: bool = False
    vendor_baseline_ready: bool = False
    problems: list[str] | None = None

    def to_payload(self) -> dict[str, object]:
        """Convert to serializable payload"""

        return asdict(self)


def check_vendor_source_baseline(
    *,
    source_dir: Path,
    target_kernel: str,
    patch_path: Path | None = None,
    vmlinux_path: Path | None = None,
) -> VendorBaselineReadiness:
    """Check whether a vendor source tree is exact enough for acceptance runs"""

    normalized_source_dir = source_dir.resolve()
    problems: list[str] = []
    path_exists = normalized_source_dir.exists()
    tree_ok = _looks_like_prepared_tree(normalized_source_dir) if path_exists else False
    config_ok = (normalized_source_dir / ".config").exists() if path_exists else False
    kernel_release = _read_kernel_release(normalized_source_dir) if path_exists else None
    kernel_release_matches = kernel_release == target_kernel
    required_cache_files = _strict_vendor_cache_snapshot(normalized_source_dir) if path_exists else {
        name: False for name in _strict_vendor_cache_file_names()
    }
    build_cache_ready = all(required_cache_files.values())
    vmlinux_ok = vmlinux_path.exists() if vmlinux_path is not None else None
    patch_apply_check_run = patch_path is not None
    patch_apply_ok: bool | None = None
    patch_apply_stdout = ""
    patch_apply_stderr = ""

    if not path_exists:
        problems.append("source_dir_missing")
    if path_exists and not tree_ok:
        problems.append("source_tree_incomplete")
    if path_exists and not config_ok:
        problems.append("kernel_config_missing")
    if path_exists and kernel_release is None:
        problems.append("kernel_release_missing")
    if path_exists and kernel_release is not None and not kernel_release_matches:
        problems.append("kernel_release_mismatch")
    for name, exists in required_cache_files.items():
        if not exists:
            problems.append(f"cache_missing:{name}")
    if vmlinux_path is not None and not vmlinux_ok:
        problems.append("debug_vmlinux_missing")

    if patch_path is not None:
        patch_apply_ok, patch_apply_stdout, patch_apply_stderr = _check_patch_applies(
            source_dir=normalized_source_dir,
            patch_path=patch_path,
        )
        if not patch_apply_ok:
            problems.append("patch_apply_check_failed")
    else:
        problems.append("patch_not_provided_unpatched_state_unknown")

    unpatched_state_verified = patch_apply_check_run and bool(patch_apply_ok)
    vendor_baseline_ready = (
        path_exists
        and tree_ok
        and config_ok
        and kernel_release_matches
        and build_cache_ready
        and (vmlinux_ok is not False)
        and unpatched_state_verified
    )

    return VendorBaselineReadiness(
        source_dir=str(normalized_source_dir),
        target_kernel=target_kernel,
        path_exists=path_exists,
        tree_ok=tree_ok,
        config_ok=config_ok,
        kernel_release=kernel_release,
        kernel_release_matches=kernel_release_matches,
        required_cache_files=required_cache_files,
        build_cache_ready=build_cache_ready,
        vmlinux_path=str(vmlinux_path) if vmlinux_path is not None else None,
        vmlinux_ok=vmlinux_ok,
        patch_path=str(patch_path.resolve()) if patch_path is not None else None,
        patch_apply_check_run=patch_apply_check_run,
        patch_apply_ok=patch_apply_ok,
        patch_apply_stdout=patch_apply_stdout[:2000],
        patch_apply_stderr=patch_apply_stderr[:2000],
        unpatched_state_verified=unpatched_state_verified,
        vendor_baseline_ready=vendor_baseline_ready,
        problems=problems,
    )


def prepare_stable_source_baseline(
    *,
    stable_git_dir: Path,
    baseline_ref: str,
    output_root: Path,
    output_dir: Path | None = None,
    force: bool = False,
    config_source: Path | None = None,
    build_config_path: Path | None = None,
    write_build_config: bool = False,
) -> StableBaselineTreeResult:
    """Prepare a cached source tree at the stable fix commit parent"""

    normalized_ref = baseline_ref.strip()
    if not normalized_ref:
        raise ValueError("stable baseline ref 不能为空")
    git_repo_ready = stable_git_dir.exists() and _is_git_repository(stable_git_dir)

    final_output_dir = output_dir or output_root / _baseline_cache_name(normalized_ref)
    final_output_dir = final_output_dir.resolve()
    if final_output_dir.exists():
        if force:
            shutil.rmtree(final_output_dir)
        elif _looks_like_prepared_tree(final_output_dir):
            patched = _patch_setlocalversion(final_output_dir)
            if config_source is not None and config_source.exists() and not (final_output_dir / ".config").exists():
                shutil.copy2(config_source, final_output_dir / ".config")
            cache_source = _build_cache_source_from_config(config_source)
            _copy_stable_baseline_build_cache(cache_source=cache_source, output_dir=final_output_dir)
            build_cache_files = _build_cache_snapshot(final_output_dir)
            if write_build_config and build_config_path is not None:
                _write_stable_path_to_build_config(build_config_path, final_output_dir)
            return StableBaselineTreeResult(
                stable_git_dir=str(stable_git_dir.resolve()),
                baseline_ref=normalized_ref,
                output_dir=str(final_output_dir),
                config_path=str(_resolve_config_path(final_output_dir)) if _resolve_config_path(final_output_dir) else None,
                setlocalversion_patched=patched,
                reused_existing=True,
                build_config_path=str(build_config_path.resolve()) if write_build_config and build_config_path is not None else None,
                git_head=_git_rev_parse(final_output_dir, "HEAD"),
                build_cache_source=str(cache_source.resolve()) if cache_source is not None else None,
                build_cache_files=build_cache_files,
                build_cache_ready=_build_cache_ready(build_cache_files),
            )
        raise RuntimeError(f"目标目录已存在但不是可复用源码树: {final_output_dir}")

    final_output_dir.parent.mkdir(parents=True, exist_ok=True)
    worktree_cmd = [
        "git",
        "-C",
        str(stable_git_dir),
        "worktree",
        "add",
        "--detach",
        str(final_output_dir),
        normalized_ref,
    ]
    if git_repo_ready:
        try:
            _run_command(worktree_cmd)
        except RuntimeError as exc:
            _prepare_stable_snapshot_fallback(
                baseline_ref=normalized_ref,
                output_dir=final_output_dir,
                original_error=exc,
            )
    else:
        _prepare_stable_snapshot_fallback(
            baseline_ref=normalized_ref,
            output_dir=final_output_dir,
            original_error=RuntimeError(f"stable git repo 不可用: {stable_git_dir}"),
        )
    if config_source is not None and config_source.exists():
        shutil.copy2(config_source, final_output_dir / ".config")
    cache_source = _build_cache_source_from_config(config_source)
    _copy_stable_baseline_build_cache(cache_source=cache_source, output_dir=final_output_dir)

    patched = _patch_setlocalversion(final_output_dir)
    if write_build_config and build_config_path is not None:
        _write_stable_path_to_build_config(build_config_path, final_output_dir)
    build_cache_files = _build_cache_snapshot(final_output_dir)

    manifest_path = final_output_dir / "patchweaver_stable_baseline.json"
    result = StableBaselineTreeResult(
        stable_git_dir=str(stable_git_dir.resolve()),
        baseline_ref=normalized_ref,
        output_dir=str(final_output_dir),
        config_path=str(_resolve_config_path(final_output_dir)) if _resolve_config_path(final_output_dir) else None,
        setlocalversion_patched=patched,
        reused_existing=False,
        build_config_path=str(build_config_path.resolve()) if write_build_config and build_config_path is not None else None,
        git_head=_git_rev_parse(final_output_dir, "HEAD"),
        build_cache_source=str(cache_source.resolve()) if cache_source is not None else None,
        build_cache_files=build_cache_files,
        build_cache_ready=_build_cache_ready(build_cache_files),
    )
    manifest_path.write_text(json.dumps(result.to_payload(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


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
    warm_targets: list[str] | None = None,
    warm_jobs: int | None = None,
    force_warm: bool = False,
) -> PreparedSourceTreeResult:
    """准备可供 kpatch-build 使用的完整源码树"""

    package_name = kernel_devel_package or f"kernel-devel-{kernel_release}"
    normalized_output_dir = output_dir.resolve()
    normalized_warm_targets = _normalize_warm_targets(warm_targets)
    warmup_marker_path = _warmup_marker_path(normalized_output_dir)
    warmup_log_path = normalized_output_dir / WARMUP_LOG_NAME
    if normalized_output_dir.exists():
        if force:
            shutil.rmtree(normalized_output_dir)
        elif _looks_like_prepared_tree(normalized_output_dir):
            patched = _patch_setlocalversion(normalized_output_dir)
            if write_build_config and build_config_path is not None:
                _write_prepared_path_to_build_config(build_config_path, normalized_output_dir)
            warmup_performed = _maybe_warm_prepared_tree(
                normalized_output_dir,
                warm_targets=normalized_warm_targets,
                warm_jobs=warm_jobs,
                force=force_warm,
            )
            build_cache_files = _build_cache_snapshot(normalized_output_dir)
            return PreparedSourceTreeResult(
                kernel_release=kernel_release,
                kernel_devel_package=package_name,
                output_dir=str(normalized_output_dir),
                srpm_path=None,
                source_tarball=None,
                overlay_dirs=[str(path) for path in overlay_dirs if path.exists()],
                config_path=str(_resolve_config_path(normalized_output_dir)) if _resolve_config_path(normalized_output_dir) else None,
                setlocalversion_patched=patched,
                build_config_path=str(build_config_path.resolve()) if write_build_config and build_config_path is not None else None,
                reused_existing=True,
                warmup_targets=normalized_warm_targets or None,
                warmup_jobs=warm_jobs,
                warmup_performed=warmup_performed,
                warmup_marker_path=str(warmup_marker_path) if normalized_warm_targets else None,
                warmup_log_path=str(warmup_log_path) if normalized_warm_targets else None,
                build_cache_ready=_build_cache_ready(build_cache_files),
                build_cache_files=build_cache_files,
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
    warmup_performed = _maybe_warm_prepared_tree(
        normalized_output_dir,
        warm_targets=normalized_warm_targets,
        warm_jobs=warm_jobs,
        force=force_warm,
    )
    build_cache_files = _build_cache_snapshot(normalized_output_dir)

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
        warmup_targets=normalized_warm_targets or None,
        warmup_jobs=warm_jobs,
        warmup_performed=warmup_performed,
        warmup_marker_path=str(warmup_marker_path) if normalized_warm_targets else None,
        warmup_log_path=str(warmup_log_path) if normalized_warm_targets else None,
        build_cache_ready=_build_cache_ready(build_cache_files),
        build_cache_files=build_cache_files,
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


def _prepare_stable_snapshot_fallback(
    *,
    baseline_ref: str,
    output_dir: Path,
    original_error: RuntimeError,
) -> None:
    """在 git worktree 不可用时改用 git.kernel snapshot"""

    snapshot_commit = _resolve_stable_snapshot_commit(baseline_ref)
    if snapshot_commit is None:
        raise original_error
    if output_dir.exists():
        shutil.rmtree(output_dir)
    _download_and_extract_stable_snapshot(commit_id=snapshot_commit, output_dir=output_dir)


def _resolve_stable_snapshot_commit(baseline_ref: str) -> str | None:
    """把 stable baseline ref 转成可下载 snapshot 的 commit"""

    normalized_ref = baseline_ref.strip()
    if re.fullmatch(r"[0-9a-fA-F]{40}", normalized_ref):
        return normalized_ref.lower()
    if normalized_ref.endswith("^"):
        commit_id = normalized_ref[:-1].strip()
        if re.fullmatch(r"[0-9a-fA-F]{40}", commit_id):
            return _fetch_stable_parent_commit(commit_id)
    return None


def _fetch_stable_parent_commit(commit_id: str) -> str | None:
    """从 git.kernel commit 页面解析父提交"""

    url = f"https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git/commit/?id={commit_id}"
    request = Request(url, headers={"User-Agent": "PatchWeaver/0.1"})
    try:
        with urlopen(request, timeout=20) as response:
            html = response.read().decode("utf-8", errors="replace")
    except OSError:
        return None
    match = re.search(
        r"<tr><th>parent</th>.*?/commit/\?id=([0-9a-fA-F]{40})",
        html,
        flags=re.DOTALL,
    )
    return match.group(1).lower() if match else None


def _download_and_extract_stable_snapshot(*, commit_id: str, output_dir: Path) -> None:
    """下载并展开 git.kernel stable snapshot"""

    url = f"https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git/snapshot/linux-{commit_id}.tar.gz"
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="patchweaver-stable-snapshot-") as temp_root:
        temp_root_path = Path(temp_root)
        archive_path = temp_root_path / "stable-snapshot.tar.gz"
        request = Request(url, headers={"User-Agent": "PatchWeaver/0.1"})
        with urlopen(request, timeout=120) as response:
            with archive_path.open("wb") as archive_handle:
                shutil.copyfileobj(response, archive_handle)
        with tarfile.open(archive_path, mode="r:gz") as archive:
            _safe_extract_tar(archive, temp_root_path)
        extracted_roots = [path for path in temp_root_path.iterdir() if path.is_dir()]
        if not extracted_roots:
            raise RuntimeError(f"stable snapshot 解压后没有源码目录: {url}")
        shutil.move(str(extracted_roots[0]), str(output_dir))


def _build_cache_source_from_config(config_source: Path | None) -> Path | None:
    """Resolve the prepared tree that owns the copied .config"""

    if config_source is None or not config_source.exists():
        return None
    source_dir = config_source.parent
    if _build_cache_ready(_build_cache_snapshot(source_dir)):
        return source_dir
    return None


def _copy_stable_baseline_build_cache(*, cache_source: Path | None, output_dir: Path) -> dict[str, bool]:
    """Copy kpatch build cache from a prepared tree into a stable baseline"""

    if cache_source is None:
        return _build_cache_snapshot(output_dir)

    for name in _strict_vendor_cache_file_names():
        source_path = cache_source / name
        if source_path.exists():
            shutil.copy2(source_path, output_dir / name)

    for relative_dir in [
        Path("include") / "config",
        Path("include") / "generated",
    ]:
        source_dir = cache_source / relative_dir
        if source_dir.exists():
            shutil.copytree(source_dir, output_dir / relative_dir, dirs_exist_ok=True)

    for relative_file in [
        Path("include") / "linux" / "compile.h",
        Path("include") / "generated" / "utsrelease.h",
    ]:
        source_file = cache_source / relative_file
        if source_file.exists():
            target_file = output_dir / relative_file
            target_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, target_file)

    return _build_cache_snapshot(output_dir)


def _safe_extract_tar(archive: tarfile.TarFile, target_dir: Path) -> None:
    """安全展开 tar 内容到目标目录"""

    target_root = target_dir.resolve()
    for member in archive.getmembers():
        member_path = (target_root / member.name).resolve()
        if target_root not in [member_path, *member_path.parents]:
            raise RuntimeError(f"snapshot 中存在越界路径: {member.name}")
    archive.extractall(target_root)


def _looks_like_prepared_tree(path: Path) -> bool:
    """判断目录是否已经是一棵可复用的完整源码树"""

    return path.is_dir() and (path / "Makefile").exists() and (path / "scripts" / "setlocalversion").exists()


def _normalize_warm_targets(warm_targets: list[str] | None) -> list[str]:
    """清洗 prepare-build-tree 传入的预热目标"""

    normalized: list[str] = []
    for raw_target in warm_targets or []:
        target = raw_target.strip()
        if target and target not in normalized:
            normalized.append(target)
    return normalized


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


def patch_setlocalversion_for_kpatch(source_dir: Path) -> bool:
    """确保 vendor kernel 的 setlocalversion 满足 PatchWeaver 运行要求"""

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

    has_save_scmversion_support = "--save-scmversion" in body
    has_kernelversion_fallback = 'KERNELVERSION="$(cat include/config/kernel.release)"' in body

    if not has_save_scmversion_support:
        marker = "set -e\n"
        injected = "set -e\n\n" + save_scm_block
        if marker in body:
            body = body.replace(marker, injected, 1)
        else:
            body = save_scm_block + body

    if not has_kernelversion_fallback:
        marker = 'if [ -z "${KERNELVERSION}" ]; then\n'
        if marker in body:
            body = body.replace(marker, kernel_release_block + marker, 1)

    updated = shebang + body
    if updated == original:
        return has_save_scmversion_support and has_kernelversion_fallback

    script_path.write_text(updated, encoding="utf-8")
    script_path.chmod(script_path.stat().st_mode | 0o111)
    return True


def _patch_setlocalversion(source_dir: Path) -> bool:
    """兼容旧调用名"""

    return patch_setlocalversion_for_kpatch(source_dir)


def _warmup_marker_path(source_dir: Path) -> Path:
    """返回源码树预热状态文件路径"""

    return source_dir / WARMUP_MARKER_NAME


def _build_cache_snapshot(source_dir: Path) -> dict[str, bool]:
    """检查 prepared source tree 是否具备模块构建缓存"""

    cache_files = ["Module.symvers", "vmlinux.o", "vmlinux", "vmlinux.a", ".vmlinux.objs"]
    return {name: (source_dir / name).exists() for name in cache_files}


def _strict_vendor_cache_file_names() -> list[str]:
    """Return strict cache files required for vendor acceptance"""

    return ["Module.symvers", "vmlinux", "vmlinux.o", "vmlinux.a", ".vmlinux.objs"]


def _strict_vendor_cache_snapshot(source_dir: Path) -> dict[str, bool]:
    """Check exact vendor baseline cache files"""

    return {name: (source_dir / name).exists() for name in _strict_vendor_cache_file_names()}


def _build_cache_ready(snapshot: dict[str, bool]) -> bool:
    """判断当前缓存是否足够让模块类 kpatch-build 进入后端"""

    has_core = bool(snapshot.get("Module.symvers")) and bool(snapshot.get("vmlinux.o"))
    has_vmlinux_link_state = bool(snapshot.get("vmlinux")) or (
        bool(snapshot.get("vmlinux.a")) and bool(snapshot.get(".vmlinux.objs"))
    )
    return has_core and has_vmlinux_link_state


def _load_warmup_marker(marker_path: Path) -> dict[str, object] | None:
    """读取预热状态文件"""

    if not marker_path.exists():
        return None
    try:
        return json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _warmup_marker_matches(marker_path: Path, *, warm_targets: list[str], warm_jobs: int | None) -> bool:
    """判断当前预热记录是否可以直接复用"""

    payload = _load_warmup_marker(marker_path)
    if payload is None:
        return False
    return payload.get("targets") == warm_targets and payload.get("jobs") == warm_jobs


def _maybe_warm_prepared_tree(
    source_dir: Path,
    *,
    warm_targets: list[str],
    warm_jobs: int | None,
    force: bool,
) -> bool:
    """按需执行 prepared source tree 预热"""

    if not warm_targets:
        return False

    marker_path = _warmup_marker_path(source_dir)
    if not force and _warmup_marker_matches(marker_path, warm_targets=warm_targets, warm_jobs=warm_jobs):
        return False

    command = ["make"]
    if warm_jobs is not None:
        command.append(f"-j{warm_jobs}")
    command.extend(warm_targets)

    log_path = source_dir / WARMUP_LOG_NAME
    with log_path.open("w", encoding="utf-8", errors="replace") as log_handle:
        result = subprocess.run(
            command,
            cwd=source_dir,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

    if result.returncode != 0:
        log_excerpt = log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
        raise RuntimeError(
            "prepared source tree 预热失败\n"
            f"command: {' '.join(command)}\n"
            f"log: {log_path}\n"
            f"excerpt:\n{log_excerpt}"
        )

    marker_path.write_text(
        json.dumps(
            {
                "targets": warm_targets,
                "jobs": warm_jobs,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "log_path": str(log_path),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
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


def _write_vendor_path_to_build_config(build_config_path: Path, vendor_path: Path) -> None:
    """Write vendor_kernel_src_dir into build.yaml"""

    payload = yaml.safe_load(build_config_path.read_text(encoding="utf-8")) or {}
    payload["vendor_kernel_src_dir"] = str(vendor_path)

    priority = list(payload.get("build_source_priority") or [])
    if "vendor_kernel_src_dir" not in priority:
        if "clean_kernel_src_dir" in priority:
            insert_at = priority.index("clean_kernel_src_dir") + 1
            priority.insert(insert_at, "vendor_kernel_src_dir")
        else:
            priority.insert(0, "vendor_kernel_src_dir")
    payload["build_source_priority"] = priority

    build_config_path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _write_stable_path_to_build_config(build_config_path: Path, stable_path: Path) -> None:
    """Write stable_kernel_src_dir into build.yaml"""

    payload = yaml.safe_load(build_config_path.read_text(encoding="utf-8")) or {}
    payload["stable_kernel_src_dir"] = str(stable_path)

    priority = list(payload.get("build_source_priority") or [])
    if "stable_kernel_src_dir" not in priority:
        anchors = ["kernel_src_dir", "prepared_kernel_src_dir", "vendor_kernel_src_dir", "clean_kernel_src_dir"]
        insert_at = 0
        for anchor in anchors:
            if anchor in priority:
                insert_at = priority.index(anchor) + 1
                break
        priority.insert(insert_at, "stable_kernel_src_dir")
    payload["build_source_priority"] = priority

    build_config_path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _is_git_repository(path: Path) -> bool:
    """Check whether path can be used as a git repository"""

    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--git-dir"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return result.returncode == 0


def _git_rev_parse(path: Path, ref: str) -> str | None:
    """Resolve a git ref if possible"""

    if not (path / ".git").exists():
        return None
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", ref],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _read_kernel_release(source_dir: Path) -> str | None:
    """Read include/config/kernel.release from source tree"""

    release_path = source_dir / "include" / "config" / "kernel.release"
    if not release_path.exists():
        return None
    value = release_path.read_text(encoding="utf-8", errors="replace").strip()
    return value or None


def _check_patch_applies(*, source_dir: Path, patch_path: Path) -> tuple[bool, str, str]:
    """Run git apply --check to prove the baseline is still unpatched"""

    if not source_dir.exists() or not patch_path.exists():
        return False, "", "source_dir or patch_path missing"
    git_path = shutil.which("git")
    if git_path is None:
        return False, "", "git command missing"
    result = subprocess.run(
        [git_path, "apply", "--check", "--verbose", str(patch_path.resolve())],
        cwd=source_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return result.returncode == 0, result.stdout.strip(), result.stderr.strip()


def _baseline_cache_name(baseline_ref: str) -> str:
    """Build a safe cache directory name for a baseline ref"""

    digest = hashlib.sha1(baseline_ref.encode("utf-8")).hexdigest()[:12]
    safe_ref = "".join(char if char.isalnum() else "-" for char in baseline_ref)[:40].strip("-")
    return f"{safe_ref or 'baseline'}-{digest}"


def shlex_quote(value: str) -> str:
    """为 bash 脚本转义路径"""

    return "'" + value.replace("'", "'\"'\"'") + "'"
