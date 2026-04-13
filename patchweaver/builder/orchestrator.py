"""构建编排与后端接入。"""

from __future__ import annotations

import os
import shlex
import stat
import subprocess
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from shutil import which
from typing import Any

import paramiko

from patchweaver.models.attempt import AttemptRecord, BuildPrecheck, BuildSummary
from patchweaver.models.rewrite import RewritePlan
from patchweaver.models.task import TaskContext


class BuildOrchestrator:
    """负责组织单轮构建，并统一封装本地与 SSH 后端。"""

    def __init__(self, build_config: Any) -> None:
        """保存构建配置，供预检和执行阶段复用。"""

        self.build_config = build_config

    def start_attempt(self, *, task_id: str, attempt_no: int) -> AttemptRecord:
        """生成一条新的 AttemptRecord。"""

        return AttemptRecord(
            task_id=task_id,
            attempt_no=attempt_no,
            attempt_id=f"{task_id}-A{attempt_no:03d}",
            status="created",
        )

    def probe_environment(self) -> dict[str, Any]:
        """检查当前构建后端的关键环境是否齐备。"""

        if self.build_config.build_backend == "ssh":
            return self._probe_remote_environment()
        return self._probe_local_environment()

    def precheck_patch(
        self,
        *,
        task_id: str,
        attempt_id: str,
        rewritten_patch_path: Path,
        source_dir: Path | None = None,
    ) -> BuildPrecheck:
        """对本地改写补丁执行 apply 级预检查。"""

        selected_source_dir = source_dir
        if selected_source_dir is None:
            selected_source_dir, _ = self._select_local_source_dir()

        if selected_source_dir is None:
            return self._precheck_not_run(
                task_id=task_id,
                attempt_id=attempt_id,
                backend="local",
                rewritten_patch_path=rewritten_patch_path,
                failure_type="kernel_src_missing",
                summary="未找到可用源码目录，无法执行 apply 级预检查。",
            )

        git_path = which("git")
        if git_path is None:
            return self._precheck_not_run(
                task_id=task_id,
                attempt_id=attempt_id,
                backend="local",
                rewritten_patch_path=rewritten_patch_path,
                source_dir=str(selected_source_dir),
                failure_type="build_env_missing",
                summary="未找到 git 命令，无法执行 apply 级预检查。",
            )

        command = [git_path, "apply", "--check", "--verbose", str(rewritten_patch_path.resolve())]
        result = subprocess.run(
            command,
            cwd=selected_source_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        stdout_text = result.stdout.strip()
        stderr_text = result.stderr.strip()
        ok = result.returncode == 0
        failure_type = None if ok else self._classify_apply_precheck_failure(stdout_text=stdout_text, stderr_text=stderr_text)
        summary = "apply 级预检查通过。" if ok else self._summarize_precheck_failure(stdout_text=stdout_text, stderr_text=stderr_text)

        return BuildPrecheck(
            task_id=task_id,
            attempt_id=attempt_id,
            backend="local",
            ok=ok,
            summary=summary,
            patch_path=rewritten_patch_path,
            source_dir=str(selected_source_dir),
            command=" ".join(shlex.quote(part) for part in command),
            failure_type=failure_type,
            stdout_excerpt=stdout_text[:2000],
            stderr_excerpt=stderr_text[:2000],
        )

    def execute_build(
        self,
        *,
        task: TaskContext,
        attempt_no: int,
        plan: RewritePlan,
        rewritten_patch_path: Path,
        build_log_path: Path,
    ) -> tuple[AttemptRecord, str, BuildPrecheck, BuildSummary]:
        """执行一轮构建尝试。"""

        if self.build_config.build_backend == "ssh":
            return self._execute_remote_build(
                task=task,
                attempt_no=attempt_no,
                plan=plan,
                rewritten_patch_path=rewritten_patch_path,
                build_log_path=build_log_path,
            )
        return self._execute_local_build(
            task=task,
            attempt_no=attempt_no,
            plan=plan,
            rewritten_patch_path=rewritten_patch_path,
            build_log_path=build_log_path,
        )

    def _probe_local_environment(self) -> dict[str, Any]:
        """检查本机构建环境。"""

        builder_path = which(self.build_config.kpatch_build_cmd)
        selected_source_dir, selected_source_reason = self._select_local_source_dir()
        config_path = None
        config_ok = False
        if selected_source_dir is not None:
            config_path = selected_source_dir / ".config"
            config_ok = config_path.exists()

        return {
            "backend": "local",
            "builder_cmd": self.build_config.kpatch_build_cmd,
            "builder_path": builder_path,
            "builder_ok": builder_path is not None,
            "kernel_src_dir": self.build_config.kernel_src_dir,
            "kernel_src_ok": self._local_kernel_tree_ok(Path(self.build_config.kernel_src_dir)),
            "kernel_devel_dir": self.build_config.kernel_devel_dir,
            "kernel_devel_ok": self._local_kernel_tree_ok(Path(self.build_config.kernel_devel_dir)),
            "selected_source_dir": str(selected_source_dir) if selected_source_dir else None,
            "selected_source_ok": selected_source_dir is not None,
            "selected_source_reason": selected_source_reason,
            "config_path": str(config_path) if config_path else None,
            "config_ok": config_ok,
            "vmlinux_path": self.build_config.vmlinux_path,
            "vmlinux_ok": Path(self.build_config.vmlinux_path).exists(),
        }

    def _probe_remote_environment(self) -> dict[str, Any]:
        """检查远端构建环境。"""

        host_label = self._remote_host_label()
        password = self._remote_password()
        probe: dict[str, Any] = {
            "backend": "ssh",
            "builder_cmd": self.build_config.kpatch_build_cmd,
            "remote_host": self.build_config.remote_host,
            "remote_port": self.build_config.remote_port,
            "remote_username": self.build_config.remote_username,
            "remote_password_env": self.build_config.remote_password_env,
            "password_present": bool(password),
            "remote_workspace_root": self.build_config.remote_workspace_root,
            "host_label": host_label,
            "reachable": False,
            "builder_path": None,
            "builder_ok": False,
            "kernel_src_dir": self.build_config.kernel_src_dir,
            "kernel_src_ok": False,
            "kernel_devel_dir": self.build_config.kernel_devel_dir,
            "kernel_devel_ok": False,
            "selected_source_dir": None,
            "selected_source_ok": False,
            "selected_source_reason": None,
            "config_path": None,
            "config_ok": False,
            "vmlinux_path": self.build_config.vmlinux_path,
            "vmlinux_ok": False,
            "error": None,
        }

        if not self.build_config.remote_host or not self.build_config.remote_username:
            probe["error"] = "缺少远端主机或登录用户配置。"
            return probe
        if not self.build_config.remote_password_env:
            probe["error"] = "未配置远端密码环境变量名。"
            return probe
        if not password:
            probe["error"] = f"缺少远端密码环境变量：{self.build_config.remote_password_env}"
            return probe

        client: paramiko.SSHClient | None = None
        sftp: paramiko.SFTPClient | None = None
        try:
            client = self._connect_remote(password)
            sftp = client.open_sftp()
            probe["reachable"] = True
            probe["builder_path"] = self._remote_command_output(client, f"command -v {shlex.quote(self.build_config.kpatch_build_cmd)}")
            probe["builder_ok"] = bool(probe["builder_path"])
            probe["kernel_src_ok"] = self._remote_kernel_tree_ok(sftp, self.build_config.kernel_src_dir)
            probe["kernel_devel_ok"] = self._remote_kernel_tree_ok(sftp, self.build_config.kernel_devel_dir)

            selected_source_dir, selected_source_reason = self._select_remote_source_dir(sftp)
            probe["selected_source_dir"] = selected_source_dir
            probe["selected_source_reason"] = selected_source_reason
            probe["selected_source_ok"] = selected_source_dir is not None

            config_path = f"{selected_source_dir}/.config" if selected_source_dir else None
            probe["config_path"] = config_path
            probe["config_ok"] = bool(config_path and self._remote_file_exists(sftp, config_path))
            probe["vmlinux_ok"] = self._remote_file_exists(sftp, self.build_config.vmlinux_path)
        except Exception as exc:
            probe["error"] = f"远端连接失败：{exc}"
        finally:
            if sftp is not None:
                sftp.close()
            if client is not None:
                client.close()

        return probe

    def _execute_local_build(
        self,
        *,
        task: TaskContext,
        attempt_no: int,
        plan: RewritePlan,
        rewritten_patch_path: Path,
        build_log_path: Path,
    ) -> tuple[AttemptRecord, str, BuildPrecheck, BuildSummary]:
        """执行本机构建。"""

        record = self.start_attempt(task_id=task.task_id, attempt_no=attempt_no)
        build_log_path.parent.mkdir(parents=True, exist_ok=True)
        probe = self._probe_local_environment()

        lines = [
            "构建后端: local",
            f"构建命令: {probe['builder_path'] or self.build_config.kpatch_build_cmd}",
            f"源码目录: {probe['selected_source_dir'] or '未找到'}",
            f"配置文件: {probe['config_path'] or '未找到'}",
            f"vmlinux: {self.build_config.vmlinux_path}",
        ]

        failure_type = self._probe_failure_type(probe)
        if failure_type is not None:
            message = self._failure_message(failure_type)
            lines.append(message)
            precheck = self._precheck_not_run(
                task_id=task.task_id,
                attempt_id=record.attempt_id,
                backend="local",
                rewritten_patch_path=rewritten_patch_path,
                source_dir=probe.get("selected_source_dir"),
                failure_type=failure_type,
                summary=message,
            )
            summary = BuildSummary(
                task_id=task.task_id,
                attempt_id=record.attempt_id,
                backend="local",
                builder_cmd=probe["builder_path"] or self.build_config.kpatch_build_cmd,
                status="failed",
                summary=message,
                rewritten_patch_path=rewritten_patch_path,
                source_dir=probe.get("selected_source_dir"),
                build_log_path=build_log_path,
                failure_type=failure_type,
            )
            build_log = "\n".join(lines) + "\n"
            build_log_path.write_text(build_log, encoding="utf-8")
            return (
                record.model_copy(
                    update={
                        "candidate_id": plan.candidate_ids[0] if plan.candidate_ids else None,
                        "status": "failed",
                        "failure_type": failure_type,
                        "build_log_path": build_log_path,
                        "module_path": None,
                        "rewritten_patch_path": rewritten_patch_path,
                        "finished_at": datetime.now(timezone.utc),
                    }
                ),
                build_log,
                precheck,
                summary,
            )

        precheck = self.precheck_patch(
            task_id=task.task_id,
            attempt_id=record.attempt_id,
            rewritten_patch_path=rewritten_patch_path,
            source_dir=Path(str(probe["selected_source_dir"])),
        )
        lines.extend(self._format_precheck_lines(precheck))

        if not precheck.ok:
            failure_type = precheck.failure_type or "patch_apply_failed"
            summary_text = "apply 级预检查未通过，已跳过本地构建。"
            lines.append(summary_text)
            summary = BuildSummary(
                task_id=task.task_id,
                attempt_id=record.attempt_id,
                backend="local",
                builder_cmd=probe["builder_path"] or self.build_config.kpatch_build_cmd,
                status="precheck_failed",
                summary=summary_text,
                rewritten_patch_path=rewritten_patch_path,
                source_dir=precheck.source_dir,
                build_log_path=build_log_path,
                failure_type=failure_type,
            )
            build_log = "\n".join(lines) + "\n"
            build_log_path.write_text(build_log, encoding="utf-8")
            return (
                record.model_copy(
                    update={
                        "candidate_id": plan.candidate_ids[0] if plan.candidate_ids else None,
                        "status": "failed",
                        "failure_type": failure_type,
                        "build_log_path": build_log_path,
                        "module_path": None,
                        "rewritten_patch_path": rewritten_patch_path,
                        "finished_at": datetime.now(timezone.utc),
                    }
                ),
                build_log,
                precheck,
                summary,
            )

        failure_type = "build_not_implemented"
        lines.append("本地 apply 级预检查已通过，但当前版本优先接入真实 SSH 构建机，本地 Linux 构建流程暂未展开。")
        summary = BuildSummary(
            task_id=task.task_id,
            attempt_id=record.attempt_id,
            backend="local",
            builder_cmd=probe["builder_path"] or self.build_config.kpatch_build_cmd,
            status="failed",
            summary="本地构建链尚未实现，已在 apply 级预检查后停止。",
            rewritten_patch_path=rewritten_patch_path,
            source_dir=precheck.source_dir,
            build_log_path=build_log_path,
            failure_type=failure_type,
        )
        build_log = "\n".join(lines) + "\n"
        build_log_path.write_text(build_log, encoding="utf-8")
        return (
            record.model_copy(
                update={
                    "candidate_id": plan.candidate_ids[0] if plan.candidate_ids else None,
                    "status": "failed",
                    "failure_type": failure_type,
                    "build_log_path": build_log_path,
                    "module_path": None,
                    "rewritten_patch_path": rewritten_patch_path,
                    "finished_at": datetime.now(timezone.utc),
                }
            ),
            build_log,
            precheck,
            summary,
        )

    def _execute_remote_build(
        self,
        *,
        task: TaskContext,
        attempt_no: int,
        plan: RewritePlan,
        rewritten_patch_path: Path,
        build_log_path: Path,
    ) -> tuple[AttemptRecord, str, BuildPrecheck, BuildSummary]:
        """执行远端构建。"""

        record = self.start_attempt(task_id=task.task_id, attempt_no=attempt_no)
        build_log_path.parent.mkdir(parents=True, exist_ok=True)
        probe = self._probe_remote_environment()

        lines = [
            "构建后端: ssh",
            f"远端主机: {probe['host_label']}",
            f"构建命令: {probe['builder_path'] or self.build_config.kpatch_build_cmd}",
            f"源码目录: {probe['selected_source_dir'] or '未找到'}",
            f"配置文件: {probe['config_path'] or '未找到'}",
            f"vmlinux: {self.build_config.vmlinux_path}",
        ]

        failure_type = self._probe_failure_type(probe)
        if failure_type is not None:
            message = probe.get("error") or self._failure_message(failure_type)
            lines.append(message)
            precheck = self._precheck_not_run(
                task_id=task.task_id,
                attempt_id=record.attempt_id,
                backend="ssh",
                rewritten_patch_path=rewritten_patch_path,
                source_dir=probe.get("selected_source_dir"),
                failure_type=failure_type,
                summary=message,
            )
            summary = BuildSummary(
                task_id=task.task_id,
                attempt_id=record.attempt_id,
                backend="ssh",
                builder_cmd=probe["builder_path"] or self.build_config.kpatch_build_cmd,
                status="failed",
                summary=message,
                rewritten_patch_path=rewritten_patch_path,
                source_dir=probe.get("selected_source_dir"),
                build_log_path=build_log_path,
                failure_type=failure_type,
            )
            build_log = "\n".join(lines) + "\n"
            build_log_path.write_text(build_log, encoding="utf-8")
            return (
                record.model_copy(
                    update={
                        "candidate_id": plan.candidate_ids[0] if plan.candidate_ids else None,
                        "status": "failed",
                        "failure_type": failure_type,
                        "build_log_path": build_log_path,
                        "module_path": None,
                        "rewritten_patch_path": rewritten_patch_path,
                        "finished_at": datetime.now(timezone.utc),
                    }
                ),
                build_log,
                precheck,
                summary,
            )

        password = self._remote_password()
        assert password is not None  # 这里的密码存在性已经在 probe 阶段确认过。

        client: paramiko.SSHClient | None = None
        sftp: paramiko.SFTPClient | None = None
        module_path: Path | None = None
        remote_module_path: str | None = None
        exit_code = 1
        precheck: BuildPrecheck
        remote_patch_path_str: str | None = None
        remote_output_dir_str: str | None = None
        selected_source_dir = str(probe["selected_source_dir"])
        try:
            client = self._connect_remote(password)
            sftp = client.open_sftp()

            remote_attempt_dir = PurePosixPath(self.build_config.remote_workspace_root) / task.task_id / "attempts" / f"{attempt_no:03d}"
            remote_output_dir = remote_attempt_dir / "output"
            remote_patch_path = remote_attempt_dir / "rewritten.patch"
            remote_patch_path_str = remote_patch_path.as_posix()
            remote_output_dir_str = remote_output_dir.as_posix()

            self._remote_mkdirs(client, remote_output_dir)
            sftp.put(str(rewritten_patch_path), remote_patch_path_str)

            precheck = self._run_remote_apply_precheck(
                client=client,
                task_id=task.task_id,
                attempt_id=record.attempt_id,
                rewritten_patch_path=rewritten_patch_path,
                remote_patch_path=remote_patch_path_str,
                source_dir=selected_source_dir,
            )
            lines.extend(self._format_precheck_lines(precheck))

            if not precheck.ok:
                failure_type = precheck.failure_type or "patch_apply_failed"
                summary_text = "apply 级预检查未通过，已跳过远端构建。"
                lines.append(summary_text)
                summary = BuildSummary(
                    task_id=task.task_id,
                    attempt_id=record.attempt_id,
                    backend="ssh",
                    builder_cmd=probe["builder_path"] or self.build_config.kpatch_build_cmd,
                    status="precheck_failed",
                    summary=summary_text,
                    rewritten_patch_path=rewritten_patch_path,
                    source_dir=selected_source_dir,
                    build_log_path=build_log_path,
                    remote_patch_path=remote_patch_path_str,
                    remote_output_dir=remote_output_dir_str,
                    failure_type=failure_type,
                )
                build_log = "\n".join(lines) + "\n"
                build_log_path.write_text(build_log, encoding="utf-8")
                return (
                    record.model_copy(
                        update={
                            "candidate_id": plan.candidate_ids[0] if plan.candidate_ids else None,
                            "status": "failed",
                            "failure_type": failure_type,
                            "build_log_path": build_log_path,
                            "module_path": None,
                            "rewritten_patch_path": rewritten_patch_path,
                            "finished_at": datetime.now(timezone.utc),
                        }
                    ),
                    build_log,
                    precheck,
                    summary,
                )

            module_name = self._module_name(task.task_id, attempt_no)
            build_command = " ".join(
                [
                    shlex.quote(self.build_config.kpatch_build_cmd),
                    "-s",
                    shlex.quote(selected_source_dir),
                    "-c",
                    shlex.quote(str(probe["config_path"])),
                    "-v",
                    shlex.quote(self.build_config.vmlinux_path),
                    "-n",
                    shlex.quote(module_name),
                    "-o",
                    shlex.quote(remote_output_dir_str),
                    shlex.quote(remote_patch_path_str),
                ]
            )
            command = f"mkdir -p {shlex.quote(remote_output_dir_str)} && {build_command}"
            stdout_text, stderr_text, exit_code = self._remote_command(client, command, timeout=self.build_config.build_timeout_sec)

            lines.extend(
                [
                    "",
                    "[remote command]",
                    command,
                    "",
                    "[stdout]",
                    stdout_text or "<empty>",
                    "",
                    "[stderr]",
                    stderr_text or "<empty>",
                    "",
                    f"退出码: {exit_code}",
                ]
            )

            if exit_code == 0:
                remote_module_path = self._find_remote_module(client, remote_output_dir)
                if remote_module_path:
                    local_module_dir = build_log_path.parent.parent / "artifacts" / "module"
                    local_module_dir.mkdir(parents=True, exist_ok=True)
                    module_path = local_module_dir / Path(remote_module_path).name
                    sftp.get(remote_module_path, str(module_path))
                else:
                    lines.append("远端构建命令返回成功，但输出目录中没有找到 .ko 文件。")
                    exit_code = 2
                    failure_type = "compile_failed"
            else:
                remote_kpatch_log = self._read_remote_kpatch_log(client)
                if remote_kpatch_log:
                    lines.extend(
                        [
                            "",
                            "[remote kpatch log]",
                            remote_kpatch_log,
                        ]
                    )
                failure_type = self._classify_command_failure(stdout_text=stdout_text, stderr_text=stderr_text)
        except Exception as exc:
            lines.append(f"远端执行失败: {exc}")
            failure_type = "remote_connect_failed"
            precheck = self._precheck_not_run(
                task_id=task.task_id,
                attempt_id=record.attempt_id,
                backend="ssh",
                rewritten_patch_path=rewritten_patch_path,
                source_dir=selected_source_dir,
                failure_type=failure_type,
                summary=f"远端执行失败：{exc}",
            )
        finally:
            if sftp is not None:
                sftp.close()
            if client is not None:
                client.close()

        if exit_code == 0 and module_path is not None:
            status = "built"
            final_failure_type = None
        else:
            status = "failed"
            final_failure_type = failure_type or "compile_failed"

        build_log = "\n".join(lines) + "\n"
        build_log_path.write_text(build_log, encoding="utf-8")
        summary = BuildSummary(
            task_id=task.task_id,
            attempt_id=record.attempt_id,
            backend="ssh",
            builder_cmd=probe["builder_path"] or self.build_config.kpatch_build_cmd,
            status=status,
            summary="远端构建成功，并已拉回模块产物。" if status == "built" else "远端构建失败，已生成结构化失败摘要。",
            rewritten_patch_path=rewritten_patch_path,
            source_dir=selected_source_dir,
            build_log_path=build_log_path,
            module_path=module_path,
            remote_patch_path=remote_patch_path_str,
            remote_output_dir=remote_output_dir_str,
            remote_module_path=remote_module_path,
            failure_type=final_failure_type,
            exit_code=exit_code,
        )
        return (
            record.model_copy(
                update={
                    "candidate_id": plan.candidate_ids[0] if plan.candidate_ids else None,
                    "status": status,
                    "failure_type": final_failure_type,
                    "build_log_path": build_log_path,
                    "module_path": module_path,
                    "rewritten_patch_path": rewritten_patch_path,
                    "finished_at": datetime.now(timezone.utc),
                }
            ),
            build_log,
            precheck,
            summary,
        )

    def _run_remote_apply_precheck(
        self,
        *,
        client: paramiko.SSHClient,
        task_id: str,
        attempt_id: str,
        rewritten_patch_path: Path,
        remote_patch_path: str,
        source_dir: str,
    ) -> BuildPrecheck:
        """在远端源码树上执行 apply 级预检查。"""

        command = (
            f"cd {shlex.quote(source_dir)} && "
            f"git apply --check --verbose {shlex.quote(remote_patch_path)}"
        )
        stdout_text, stderr_text, exit_code = self._remote_command(client, command, timeout=60)
        ok = exit_code == 0
        failure_type = None if ok else self._classify_apply_precheck_failure(stdout_text=stdout_text, stderr_text=stderr_text)
        summary = "apply 级预检查通过。" if ok else self._summarize_precheck_failure(stdout_text=stdout_text, stderr_text=stderr_text)
        return BuildPrecheck(
            task_id=task_id,
            attempt_id=attempt_id,
            backend="ssh",
            ok=ok,
            summary=summary,
            patch_path=rewritten_patch_path,
            source_dir=source_dir,
            command=command,
            failure_type=failure_type,
            stdout_excerpt=stdout_text[:2000],
            stderr_excerpt=stderr_text[:2000],
        )

    def _precheck_not_run(
        self,
        *,
        task_id: str,
        attempt_id: str,
        backend: str,
        rewritten_patch_path: Path,
        failure_type: str,
        summary: str,
        source_dir: str | None = None,
    ) -> BuildPrecheck:
        """为未实际执行的预检查生成结构化结果。"""

        return BuildPrecheck(
            task_id=task_id,
            attempt_id=attempt_id,
            backend=backend,
            ok=False,
            summary=summary,
            patch_path=rewritten_patch_path,
            source_dir=source_dir,
            failure_type=failure_type,
        )

    def _format_precheck_lines(self, precheck: BuildPrecheck) -> list[str]:
        """把预检查结果展开成构建日志片段。"""

        lines = [
            "",
            "[apply precheck]",
            precheck.summary,
            f"源码目录: {precheck.source_dir or '未找到'}",
            f"补丁路径: {precheck.patch_path}",
        ]
        if precheck.command:
            lines.append(f"命令: {precheck.command}")
        if precheck.stdout_excerpt:
            lines.extend(["[precheck stdout]", precheck.stdout_excerpt])
        if precheck.stderr_excerpt:
            lines.extend(["[precheck stderr]", precheck.stderr_excerpt])
        return lines

    def _select_local_source_dir(self) -> tuple[Path | None, str | None]:
        """挑选本地可用的源码目录。"""

        kernel_src_dir = Path(self.build_config.kernel_src_dir)
        if self._local_kernel_tree_ok(kernel_src_dir):
            return kernel_src_dir, "kernel_src_dir"

        kernel_devel_dir = Path(self.build_config.kernel_devel_dir)
        if self._local_kernel_tree_ok(kernel_devel_dir):
            return kernel_devel_dir, "kernel_devel_dir_fallback"

        return None, None

    def _select_remote_source_dir(self, sftp: paramiko.SFTPClient) -> tuple[str | None, str | None]:
        """挑选远端可用的源码目录。"""

        if self._remote_kernel_tree_ok(sftp, self.build_config.kernel_src_dir):
            return self.build_config.kernel_src_dir, "kernel_src_dir"
        if self._remote_kernel_tree_ok(sftp, self.build_config.kernel_devel_dir):
            return self.build_config.kernel_devel_dir, "kernel_devel_dir_fallback"
        return None, None

    def _local_kernel_tree_ok(self, path: Path) -> bool:
        """判断本地目录能否作为内核源码树使用。"""

        return path.is_dir() and (path / "Makefile").exists()

    def _remote_kernel_tree_ok(self, sftp: paramiko.SFTPClient, path: str) -> bool:
        """判断远端目录能否作为内核源码树使用。"""

        return self._remote_dir_exists(sftp, path) and self._remote_file_exists(sftp, f"{path}/Makefile")

    def _remote_file_exists(self, sftp: paramiko.SFTPClient, path: str) -> bool:
        """检查远端文件是否存在。"""

        try:
            remote_stat = sftp.stat(path)
        except OSError:
            return False
        return stat.S_ISREG(remote_stat.st_mode)

    def _remote_dir_exists(self, sftp: paramiko.SFTPClient, path: str) -> bool:
        """检查远端目录是否存在。"""

        try:
            remote_stat = sftp.stat(path)
        except OSError:
            return False
        return stat.S_ISDIR(remote_stat.st_mode)

    def _remote_password(self) -> str | None:
        """读取远端密码环境变量。"""

        if not self.build_config.remote_password_env:
            return None
        return os.getenv(self.build_config.remote_password_env)

    def _remote_host_label(self) -> str:
        """生成远端主机展示名。"""

        username = self.build_config.remote_username or "unknown"
        host = self.build_config.remote_host or "unknown"
        port = self.build_config.remote_port or 22
        return f"{username}@{host}:{port}"

    def _connect_remote(self, password: str) -> paramiko.SSHClient:
        """建立远端 SSH 连接。"""

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=self.build_config.remote_host,
            port=self.build_config.remote_port,
            username=self.build_config.remote_username,
            password=password,
            timeout=self.build_config.remote_connect_timeout_sec,
        )
        return client

    def _remote_command_output(self, client: paramiko.SSHClient, command: str) -> str | None:
        """执行远端命令并返回 stdout。"""

        stdout_text, _, exit_code = self._remote_command(client, command, timeout=20)
        if exit_code != 0:
            return None
        text = stdout_text.strip()
        return text or None

    def _remote_command(self, client: paramiko.SSHClient, command: str, *, timeout: int) -> tuple[str, str, int]:
        """执行远端命令并返回标准输出、错误输出和退出码。"""

        stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        stdout_text = stdout.read().decode("utf-8", errors="replace").strip()
        stderr_text = stderr.read().decode("utf-8", errors="replace").strip()
        exit_code = stdout.channel.recv_exit_status()
        return stdout_text, stderr_text, exit_code

    def _remote_mkdirs(self, client: paramiko.SSHClient, remote_dir: PurePosixPath) -> None:
        """在远端递归创建目录。"""

        command = f"mkdir -p {shlex.quote(remote_dir.as_posix())}"
        _, stderr_text, exit_code = self._remote_command(client, command, timeout=20)
        if exit_code != 0:
            raise RuntimeError(stderr_text or f"创建远端目录失败：{remote_dir}")

    def _find_remote_module(self, client: paramiko.SSHClient, remote_output_dir: PurePosixPath) -> str | None:
        """在远端输出目录中查找构建出来的模块。"""

        command = f"find {shlex.quote(remote_output_dir.as_posix())} -type f -name '*.ko' | sort | head -n 1"
        return self._remote_command_output(client, command)

    def _read_remote_kpatch_log(self, client: paramiko.SSHClient) -> str | None:
        """读取远端 kpatch 的最近一段调试日志。"""

        command = "if [ -f /root/.kpatch/build.log ]; then tail -n 40 /root/.kpatch/build.log; fi"
        return self._remote_command_output(client, command)

    def _probe_failure_type(self, probe: dict[str, Any]) -> str | None:
        """把预检结果映射成统一失败类型。"""

        if probe["backend"] == "ssh":
            if not probe.get("password_present"):
                return "remote_auth_missing"
            if probe.get("error"):
                return "remote_connect_failed"

        if not probe.get("builder_ok"):
            return "build_env_missing"
        if not probe.get("selected_source_ok"):
            return "kernel_src_missing"
        if not probe.get("config_ok"):
            return "kernel_config_missing"
        if not probe.get("vmlinux_ok"):
            return "vmlinux_missing"
        return None

    def _failure_message(self, failure_type: str) -> str:
        """生成更容易看懂的失败提示。"""

        messages = {
            "remote_auth_missing": "缺少远端登录密码，先在本地环境变量中提供密码后再试。",
            "remote_connect_failed": "远端连接失败，请检查 IP、端口、账号或网络连通性。",
            "build_env_missing": f"未找到构建命令：{self.build_config.kpatch_build_cmd}",
            "kernel_src_missing": "找不到可用的内核源码目录，kernel_src_dir 和 kernel_devel_dir 都未通过校验。",
            "kernel_config_missing": "源码目录中没有找到 .config，暂时无法继续构建。",
            "vmlinux_missing": "找不到可用的 vmlinux 文件，无法继续构建。",
        }
        return messages.get(failure_type, "构建环境检查未通过。")

    def _summarize_precheck_failure(self, *, stdout_text: str, stderr_text: str) -> str:
        """为 apply 级预检查生成摘要。"""

        for raw_text in [stderr_text, stdout_text]:
            for line in raw_text.splitlines():
                stripped = line.strip()
                if stripped:
                    return stripped
        return "apply 级预检查未通过。"

    def _classify_apply_precheck_failure(self, *, stdout_text: str, stderr_text: str) -> str:
        """根据 apply 级预检查输出归类失败原因。"""

        combined = f"{stdout_text}\n{stderr_text}".lower()
        if "git: command not found" in combined or "not recognized as an internal or external command" in combined:
            return "build_env_missing"
        if "no valid patches in input" in combined:
            return "patch_apply_failed"
        if "patch does not apply" in combined or "corrupt patch" in combined:
            return "patch_apply_failed"
        if "does not exist in index" in combined or "no such file or directory" in combined:
            return "patch_apply_failed"
        if "fatal:" in combined and "not a git repository" in combined:
            return "patch_apply_failed"
        return "patch_apply_failed"

    def _classify_command_failure(self, *, stdout_text: str, stderr_text: str) -> str:
        """根据构建命令的直接输出给出一层快速归因。"""

        combined = f"{stdout_text}\n{stderr_text}".lower()
        if "failed to apply" in combined or "can't find file to patch" in combined or "patch failed" in combined:
            return "patch_apply_failed"
        if "only garbage was found in the patch input" in combined:
            return "patch_apply_failed"
        if "patch does not apply" in combined:
            return "patch_apply_failed"
        if "command not found" in combined:
            return "build_env_missing"
        if "unreconcilable difference" in combined or "fentry" in combined or "init section" in combined:
            return "kpatch_constraint"
        if "section mismatch" in combined or "unsupported" in combined and "kpatch" in combined:
            return "kpatch_constraint"
        return "compile_failed"

    def _module_name(self, task_id: str, attempt_no: int) -> str:
        """生成远端模块名。"""

        normalized = task_id.lower().replace("_", "-")
        return f"patchweaver-{normalized}-{attempt_no:03d}"
