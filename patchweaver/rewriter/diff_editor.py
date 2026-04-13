"""受控 diff 输出与 apply 预检查。"""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path, PurePosixPath
from shutil import which
from uuid import uuid4

from patchweaver.models.rewrite import ApplyPrecheckReport, RewritePlan, TransformationStep


class DiffEditor:
    """负责输出 patch 并执行 apply 级别检查。"""

    def materialize(
        self,
        *,
        plan: RewritePlan,
        patch_text: str,
        target_path: Path,
    ) -> tuple[Path, TransformationStep]:
        """写出统一格式的 rewritten.patch。"""

        normalized = patch_text.replace("\r\n", "\n").replace("\r", "\n")
        if not normalized.endswith("\n"):
            normalized += "\n"

        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(normalized, encoding="utf-8")
        return target_path, TransformationStep(
            step_id="diff-001",
            engine="diff_editor",
            action="write_unified_diff",
            recipe_name=plan.selected_recipe,
            primitive="direct_apply" if "direct_apply" in plan.selected_primitives else None,
            target_files=plan.target_files,
            summary="已输出可直接用于 apply 检查的 unified diff 文件。",
        )

    def apply_precheck(
        self,
        *,
        builder: object,
        patch_path: Path,
        task_id: str,
        attempt_no: int,
    ) -> ApplyPrecheckReport:
        """在构建前执行 apply 级别预检查。"""

        probe = builder.probe_environment()
        backend = str(probe.get("backend") or getattr(builder.build_config, "build_backend", "unknown"))
        if backend == "ssh":
            return self._remote_apply_precheck(
                builder=builder,
                patch_path=patch_path,
                task_id=task_id,
                attempt_no=attempt_no,
                probe=probe,
            )
        return self._local_apply_precheck(patch_path=patch_path, probe=probe)

    def _local_apply_precheck(self, *, patch_path: Path, probe: dict[str, object]) -> ApplyPrecheckReport:
        """执行本地 apply 预检查。"""

        source_dir = probe.get("selected_source_dir")
        if not source_dir:
            return ApplyPrecheckReport(
                status="skipped",
                ok=False,
                backend="local",
                checked_patch_path=str(patch_path),
                summary="未找到可用本地源码目录，跳过 apply 预检查。",
            )
        if which("git") is None:
            return ApplyPrecheckReport(
                status="skipped",
                ok=False,
                backend="local",
                target_source_dir=str(source_dir),
                checked_patch_path=str(patch_path),
                summary="本机未找到 git，跳过 apply 预检查。",
            )

        command = ["git", "apply", "--check", "--verbose", str(patch_path)]
        completed = subprocess.run(
            command,
            cwd=str(source_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        stdout = completed.stdout.strip() or None
        stderr = completed.stderr.strip() or None
        combined = "\n".join(part for part in [stdout, stderr] if part)
        if completed.returncode == 0:
            return ApplyPrecheckReport(
                status="passed",
                ok=True,
                backend="local",
                target_source_dir=str(source_dir),
                command=" ".join(command),
                checked_patch_path=str(patch_path),
                exit_code=0,
                summary="本地 apply 预检查通过。",
                stdout=stdout,
                stderr=stderr,
            )

        if self._is_patch_apply_failure(combined):
            return ApplyPrecheckReport(
                status="failed",
                ok=False,
                backend="local",
                target_source_dir=str(source_dir),
                command=" ".join(command),
                checked_patch_path=str(patch_path),
                exit_code=completed.returncode,
                summary="本地 apply 预检查未通过，补丁当前无法应用到目标源码树。",
                stdout=stdout,
                stderr=stderr,
            )

        return ApplyPrecheckReport(
            status="skipped",
            ok=False,
            backend="local",
            target_source_dir=str(source_dir),
            command=" ".join(command),
            checked_patch_path=str(patch_path),
            exit_code=completed.returncode,
            summary="本地 apply 预检查未完成，当前更像环境或工具问题，继续交给构建阶段判定。",
            stdout=stdout,
            stderr=stderr,
        )

    def _remote_apply_precheck(
        self,
        *,
        builder: object,
        patch_path: Path,
        task_id: str,
        attempt_no: int,
        probe: dict[str, object],
    ) -> ApplyPrecheckReport:
        """执行远端 apply 预检查。"""

        if not probe.get("reachable"):
            return ApplyPrecheckReport(
                status="skipped",
                ok=False,
                backend="ssh",
                checked_patch_path=str(patch_path),
                summary=str(probe.get("error") or "远端构建机不可达，跳过 apply 预检查。"),
            )
        source_dir = probe.get("selected_source_dir")
        if not source_dir:
            return ApplyPrecheckReport(
                status="skipped",
                ok=False,
                backend="ssh",
                checked_patch_path=str(patch_path),
                summary="远端未找到可用源码目录，跳过 apply 预检查。",
            )

        password = builder._remote_password()
        if not password:
            return ApplyPrecheckReport(
                status="skipped",
                ok=False,
                backend="ssh",
                target_source_dir=str(source_dir),
                checked_patch_path=str(patch_path),
                summary="缺少远端认证信息，跳过 apply 预检查。",
            )

        client = None
        sftp = None
        remote_patch_path = (
            PurePosixPath(builder.build_config.remote_workspace_root)
            / "_precheck"
            / f"{task_id}-{attempt_no:03d}-{uuid4().hex[:8]}.patch"
        )
        command = (
            f"cd {shlex.quote(str(source_dir))} && "
            f"git apply --check --verbose {shlex.quote(remote_patch_path.as_posix())}"
        )
        try:
            client = builder._connect_remote(password)
            sftp = client.open_sftp()
            builder._remote_mkdirs(client, remote_patch_path.parent)
            sftp.put(str(patch_path), remote_patch_path.as_posix())
            stdout_text, stderr_text, exit_code = builder._remote_command(client, command, timeout=120)
            combined = "\n".join(part for part in [stdout_text, stderr_text] if part)
            if exit_code == 0:
                return ApplyPrecheckReport(
                    status="passed",
                    ok=True,
                    backend="ssh",
                    target_source_dir=str(source_dir),
                    command=command,
                    checked_patch_path=remote_patch_path.as_posix(),
                    exit_code=0,
                    summary="远端 apply 预检查通过。",
                    stdout=stdout_text or None,
                    stderr=stderr_text or None,
                )
            if self._is_patch_apply_failure(combined):
                return ApplyPrecheckReport(
                    status="failed",
                    ok=False,
                    backend="ssh",
                    target_source_dir=str(source_dir),
                    command=command,
                    checked_patch_path=remote_patch_path.as_posix(),
                    exit_code=exit_code,
                    summary="远端 apply 预检查未通过，补丁当前无法应用到目标源码树。",
                    stdout=stdout_text or None,
                    stderr=stderr_text or None,
                )
            return ApplyPrecheckReport(
                status="skipped",
                ok=False,
                backend="ssh",
                target_source_dir=str(source_dir),
                command=command,
                checked_patch_path=remote_patch_path.as_posix(),
                exit_code=exit_code,
                summary="远端 apply 预检查未完成，当前更像环境或工具问题，继续交给构建阶段判定。",
                stdout=stdout_text or None,
                stderr=stderr_text or None,
            )
        except Exception as exc:  # pragma: no cover - 远端依赖
            return ApplyPrecheckReport(
                status="skipped",
                ok=False,
                backend="ssh",
                target_source_dir=str(source_dir),
                command=command,
                checked_patch_path=remote_patch_path.as_posix(),
                summary=f"远端 apply 预检查执行失败：{exc}",
            )
        finally:
            if sftp is not None:
                sftp.close()
            if client is not None:
                client.close()

    def _is_patch_apply_failure(self, text: str) -> bool:
        """判断错误是否属于 patch 无法 apply。"""

        lowered = text.lower()
        markers = [
            "patch does not apply",
            "patch failed",
            "failed to apply",
            "can't find file to patch",
            "only garbage was found in the patch input",
            "error: corrupt patch",
        ]
        return any(marker in lowered for marker in markers)
