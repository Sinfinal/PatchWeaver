"""构建编排与本机构建执行"""

from __future__ import annotations

import platform
import re
import shlex
import shutil
import os
import signal
import subprocess
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from shutil import which
from typing import Any

from patchweaver.models.attempt import AttemptRecord, BuildPrecheck, BuildSummary
from patchweaver.models.rewrite import RewritePlan
from patchweaver.models.task import TaskContext
from patchweaver.builder.source_preparer import patch_setlocalversion_for_kpatch
from unidiff import PatchSet


class BuildOrchestrator:
    """负责组织单轮本机构建"""

    def __init__(self, build_config: Any) -> None:
        """保存构建配置，供预检和执行阶段复用"""

        self.build_config = build_config

    def start_attempt(self, *, task_id: str, attempt_no: int) -> AttemptRecord:
        """生成一条新的 AttemptRecord"""

        return AttemptRecord(
            task_id=task_id,
            attempt_no=attempt_no,
            attempt_id=f"{task_id}-A{attempt_no:03d}",
            status="running",
        )

    def probe_environment(self) -> dict[str, Any]:
        """检查当前运行机上的构建环境是否齐备"""

        return self._probe_local_environment()

    def precheck_patch(
        self,
        *,
        task_id: str,
        attempt_id: str,
        rewritten_patch_path: Path,
        source_dir: Path | None = None,
    ) -> BuildPrecheck:
        """对改写补丁执行 apply 级预检查"""

        selected_source_dir = source_dir
        if selected_source_dir is None:
            # 预检查和正式构建要落在同一套源码树上
            # 这里先做一次兜底选择，避免调用方遗漏 source_dir 时两边目录不一致
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
            # apply 级预检查直接复用 git apply --check
            # 没有 git 时不继续做假校验，统一走结构化失败结果
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
        failure_type = None
        summary = "apply 级预检查通过。"
        if ok and self._looks_like_skipped_patch_output(stdout_text=stdout_text, stderr_text=stderr_text):
            if self._patch_looks_already_applied_locally(patch_path=rewritten_patch_path, source_dir=selected_source_dir):
                ok = False
                failure_type = "target_already_patched"
                summary = self._summarize_precheck_failure(
                    stdout_text=stdout_text,
                    stderr_text=stderr_text,
                    failure_type=failure_type,
                )
        elif not ok:
            failure_type = self._classify_apply_precheck_failure(stdout_text=stdout_text, stderr_text=stderr_text)
            if failure_type == "patch_apply_failed":
                # 这里再补一次 reverse check
                # 目的是把“补丁打不上”与“目标内核其实已经修过”区分开
                if self._patch_looks_already_applied_locally(patch_path=rewritten_patch_path, source_dir=selected_source_dir):
                    failure_type = "target_already_patched"
            summary = self._summarize_precheck_failure(
                stdout_text=stdout_text,
                stderr_text=stderr_text,
                failure_type=failure_type,
            )

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
            build_exec_status="not_run" if not ok else None,
            target_state="target_already_patched" if failure_type == "target_already_patched" else None,
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
        """执行一轮本机构建尝试"""

        return self._execute_local_build(
            task=task,
            attempt_no=attempt_no,
            plan=plan,
            rewritten_patch_path=rewritten_patch_path,
            build_log_path=build_log_path,
        )

    def _probe_local_environment(self) -> dict[str, Any]:
        """检查本机构建环境"""

        builder_path = which(self.build_config.kpatch_build_cmd)
        selected_source_dir, selected_source_reason = self._select_local_source_dir()
        config_path = self._config_path_for_source(selected_source_dir)
        config_ok = config_path.exists() if config_path is not None else False

        return {
            "backend": "local",
            "builder_cmd": self.build_config.kpatch_build_cmd,
            "builder_path": builder_path,
            "builder_ok": builder_path is not None,
            "running_kernel": platform.release(),
            "clean_kernel_src_dir": self.build_config.clean_kernel_src_dir,
            "clean_kernel_src_ok": self._local_kernel_tree_ok(Path(self.build_config.clean_kernel_src_dir))
            if self.build_config.clean_kernel_src_dir
            else False,
            "prepared_kernel_src_dir": self.build_config.prepared_kernel_src_dir,
            "prepared_kernel_src_ok": self._local_kernel_tree_ok(Path(self.build_config.prepared_kernel_src_dir))
            if self.build_config.prepared_kernel_src_dir
            else False,
            "kernel_src_dir": self.build_config.kernel_src_dir,
            "kernel_src_ok": self._local_kernel_tree_ok(Path(self.build_config.kernel_src_dir)),
            "kernel_devel_dir": self.build_config.kernel_devel_dir,
            "kernel_devel_ok": self._local_kernel_tree_ok(Path(self.build_config.kernel_devel_dir)),
            "patched_kernel_src_dir": self.build_config.patched_kernel_src_dir,
            "patched_kernel_src_ok": self._local_kernel_tree_ok(Path(self.build_config.patched_kernel_src_dir))
            if self.build_config.patched_kernel_src_dir
            else False,
            "source_candidates": self._source_candidate_snapshot(),
            "selected_source_dir": str(selected_source_dir) if selected_source_dir else None,
            "selected_source_ok": selected_source_dir is not None,
            "selected_source_reason": selected_source_reason,
            "selected_source_expected_state": self._source_slot_expected_state(selected_source_reason),
            "config_path": str(config_path) if config_path else None,
            "config_ok": config_ok,
            "vmlinux_path": self.build_config.vmlinux_path,
            "vmlinux_ok": Path(self.build_config.vmlinux_path).exists(),
        }

    def _execute_local_build(
        self,
        *,
        task: TaskContext,
        attempt_no: int,
        plan: RewritePlan,
        rewritten_patch_path: Path,
        build_log_path: Path,
    ) -> tuple[AttemptRecord, str, BuildPrecheck, BuildSummary]:
        """执行本机构建"""

        record = self.start_attempt(task_id=task.task_id, attempt_no=attempt_no)
        build_log_path.parent.mkdir(parents=True, exist_ok=True)
        probe = self._probe_local_environment()

        # 无论构建是否真正执行，日志头部都先把关键环境写清楚
        # 这样 report 和人工排障都能直接看到失败卡在环境还是补丁本身
        lines = [
            "构建后端: local",
            f"构建命令: {probe['builder_path'] or self.build_config.kpatch_build_cmd}",
            f"源码目录: {probe['selected_source_dir'] or '未找到'}",
            f"源码槽位: {probe.get('selected_source_reason') or 'unknown'}",
            f"源码期望状态: {probe.get('selected_source_expected_state') or 'unknown'}",
            f"配置文件: {probe['config_path'] or '未找到'}",
            f"vmlinux: {self.build_config.vmlinux_path}",
        ]
        if probe.get("source_candidates"):
            candidate_digest = " | ".join(
                f"{item['slot']}={item['path']} ({'ok' if item['ok'] else 'missing'}, {item['expected_state']})"
                for item in probe["source_candidates"]
            )
            lines.append(f"源码候选: {candidate_digest}")

        failure_type = self._probe_failure_type(probe)
        if failure_type is not None:
            # 环境预检不过时，不再往下执行 build
            # 这里直接生成 precheck/build summary，保证后续报表字段完整
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
                build_exec_status="not_run",
            )
            build_log = "\n".join(lines) + "\n"
            self._persist_build_log(build_log_path=build_log_path, build_log=build_log)
            return (
                record.model_copy(
                    update={
                        "candidate_id": plan.candidate_ids[0] if plan.candidate_ids else None,
                        "status": "failed",
                        "failure_type": failure_type,
                        "build_exec_status": "not_run",
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

        selected_source_dir = Path(str(probe["selected_source_dir"]))
        mismatched_arch_files = self._collect_mismatched_arch_patch_target_files(rewritten_patch_path=rewritten_patch_path)
        if mismatched_arch_files:
            current_arch = self._current_kernel_arch()
            summary_text = "补丁触达目标架构之外的源码，已跳过本机构建。"
            lines.extend(
                [
                    "",
                    "[build target coverage]",
                    f"当前验证机内核架构: {current_arch}",
                    "目标架构不匹配源码: " + ", ".join(mismatched_arch_files),
                    "当前样例不会在该验证内核上形成 changed objects，已跳过 kpatch-build",
                ]
            )
            precheck = self._precheck_not_run(
                task_id=task.task_id,
                attempt_id=record.attempt_id,
                backend="local",
                rewritten_patch_path=rewritten_patch_path,
                source_dir=str(selected_source_dir),
                failure_type="target_arch_mismatch",
                summary=summary_text,
            )
            summary = BuildSummary(
                task_id=task.task_id,
                attempt_id=record.attempt_id,
                backend="local",
                builder_cmd=probe["builder_path"] or self.build_config.kpatch_build_cmd,
                status="not_run",
                summary=summary_text,
                rewritten_patch_path=rewritten_patch_path,
                source_dir=str(selected_source_dir),
                build_log_path=build_log_path,
                failure_type="target_arch_mismatch",
                build_exec_status="not_run",
            )
            build_log = "\n".join(lines) + "\n"
            self._persist_build_log(build_log_path=build_log_path, build_log=build_log)
            return (
                record.model_copy(
                    update={
                        "candidate_id": plan.candidate_ids[0] if plan.candidate_ids else None,
                        "status": "failed",
                        "failure_type": "target_arch_mismatch",
                        "build_exec_status": "not_run",
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

        disabled_target_files = self._collect_disabled_patch_target_files(
            source_dir=selected_source_dir,
            rewritten_patch_path=rewritten_patch_path,
        )
        if disabled_target_files:
            summary_text = "目标内核配置未启用补丁涉及源码，已跳过本机构建。"
            lines.extend(
                [
                    "",
                    "[build target coverage]",
                    "目标内核配置未启用以下源码: " + ", ".join(disabled_target_files),
                    "当前样例在该验证内核上不会编译出对应对象，已跳过 kpatch-build",
                ]
            )
            precheck = self._precheck_not_run(
                task_id=task.task_id,
                attempt_id=record.attempt_id,
                backend="local",
                rewritten_patch_path=rewritten_patch_path,
                source_dir=str(selected_source_dir),
                failure_type="feature_not_enabled",
                summary=summary_text,
            )
            summary = BuildSummary(
                task_id=task.task_id,
                attempt_id=record.attempt_id,
                backend="local",
                builder_cmd=probe["builder_path"] or self.build_config.kpatch_build_cmd,
                status="not_run",
                summary=summary_text,
                rewritten_patch_path=rewritten_patch_path,
                source_dir=str(selected_source_dir),
                build_log_path=build_log_path,
                failure_type="feature_not_enabled",
                build_exec_status="not_run",
            )
            build_log = "\n".join(lines) + "\n"
            self._persist_build_log(build_log_path=build_log_path, build_log=build_log)
            return (
                record.model_copy(
                    update={
                        "candidate_id": plan.candidate_ids[0] if plan.candidate_ids else None,
                        "status": "failed",
                        "failure_type": "feature_not_enabled",
                        "build_exec_status": "not_run",
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
            source_dir=selected_source_dir,
        )
        lines.extend(self._format_precheck_lines(precheck))
        primary_target_state_precheck: BuildPrecheck | None = None
        generated_source_dir: Path | None = None

        if (
            not precheck.ok
            and precheck.failure_type == "target_already_patched"
            and getattr(self.build_config, "auto_switch_source_tree", False)
        ):
            primary_target_state_precheck = precheck
            fallback_source_dir, fallback_source_reason = self._select_local_source_dir(exclude={selected_source_dir})
            if fallback_source_dir is not None:
                lines.extend(
                    [
                        "",
                        f"当前源码树已命中 target_already_patched，准备切换到备用源码树: {fallback_source_dir}",
                        f"备用源码槽位: {fallback_source_reason}",
                    ]
                )
                probe = self._override_selected_source(
                    probe=probe,
                    source_dir=fallback_source_dir,
                    source_reason=fallback_source_reason,
                )
                selected_source_dir = fallback_source_dir
                precheck = self.precheck_patch(
                    task_id=task.task_id,
                    attempt_id=record.attempt_id,
                    rewritten_patch_path=rewritten_patch_path,
                    source_dir=selected_source_dir,
                )
                lines.extend(self._format_precheck_lines(precheck))

        if (
            not precheck.ok
            and primary_target_state_precheck is not None
            and getattr(self.build_config, "auto_reverse_source_tree", False)
        ):
            reverse_source_dir, reverse_lines = self._prepare_reverse_source_tree(
                patched_source_dir=Path(primary_target_state_precheck.source_dir or selected_source_dir),
                rewritten_patch_path=rewritten_patch_path,
                attempt_dir=build_log_path.parent.parent,
            )
            lines.extend(reverse_lines)
            if reverse_source_dir is not None:
                generated_source_dir = reverse_source_dir
                probe = self._override_selected_source(
                    probe=probe,
                    source_dir=reverse_source_dir,
                    source_reason="synthetic_reverse_tree",
                )
                selected_source_dir = reverse_source_dir
                precheck = self.precheck_patch(
                    task_id=task.task_id,
                    attempt_id=record.attempt_id,
                    rewritten_patch_path=rewritten_patch_path,
                    source_dir=selected_source_dir,
                )
                lines.extend(self._format_precheck_lines(precheck))

        if not precheck.ok:
            failure_type = precheck.failure_type or "patch_apply_failed"
            target_state = "target_already_patched" if failure_type == "target_already_patched" else None
            summary_source_dir = precheck.source_dir
            if self._should_collapse_to_target_state(
                initial_precheck=primary_target_state_precheck,
                final_precheck=precheck,
            ):
                failure_type = "target_already_patched"
                target_state = "target_already_patched"
                summary_source_dir = primary_target_state_precheck.source_dir
                lines.extend(
                    [
                        "",
                        "[build outcome]",
                        f"首选源码树 {primary_target_state_precheck.source_dir or 'unknown'} 已命中 target_already_patched",
                        f"备用源码树 {precheck.source_dir or 'unknown'} 未能通过 apply 预检查",
                        "本轮按 target_already_patched 收口，不继续执行 kpatch-build",
                    ]
                )
            attempt_status = "target_state" if target_state else "failed"
            summary_text = (
                self._target_state_summary_after_switch(
                    initial_precheck=primary_target_state_precheck,
                    final_precheck=precheck,
                )
                if target_state
                else "apply 级预检查未通过，已跳过本机构建。"
            )
            # apply 级预检查没过时，不继续碰 kpatch-build
            # 这样失败原因会更集中，不会被后续一串派生报错淹没
            lines.append(summary_text)
            lines.extend(self._cleanup_generated_source_tree(generated_source_dir))
            summary = BuildSummary(
                task_id=task.task_id,
                attempt_id=record.attempt_id,
                backend="local",
                builder_cmd=probe["builder_path"] or self.build_config.kpatch_build_cmd,
                status="not_run",
                summary=summary_text,
                rewritten_patch_path=rewritten_patch_path,
                source_dir=summary_source_dir,
                build_log_path=build_log_path,
                failure_type=failure_type,
                build_exec_status="not_run",
                target_state=target_state,
            )
            build_log = "\n".join(lines) + "\n"
            self._persist_build_log(build_log_path=build_log_path, build_log=build_log)
            return (
                record.model_copy(
                    update={
                        "candidate_id": plan.candidate_ids[0] if plan.candidate_ids else None,
                        "status": attempt_status,
                        "failure_type": failure_type,
                        "build_exec_status": "not_run",
                        "target_state": target_state,
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

        disabled_target_files = self._collect_disabled_patch_target_files(
            source_dir=selected_source_dir,
            rewritten_patch_path=rewritten_patch_path,
        )
        if disabled_target_files:
            summary_text = "目标内核配置未启用补丁涉及源码，已跳过本机构建。"
            lines.extend(
                [
                    "",
                    "[build target coverage]",
                    "目标内核配置未启用以下源码: " + ", ".join(disabled_target_files),
                    "当前样例在该验证内核上不会编译出对应对象，已跳过 kpatch-build",
                ]
            )
            lines.extend(self._cleanup_generated_source_tree(generated_source_dir))
            summary = BuildSummary(
                task_id=task.task_id,
                attempt_id=record.attempt_id,
                backend="local",
                builder_cmd=probe["builder_path"] or self.build_config.kpatch_build_cmd,
                status="not_run",
                summary=summary_text,
                rewritten_patch_path=rewritten_patch_path,
                source_dir=precheck.source_dir,
                build_log_path=build_log_path,
                failure_type="feature_not_enabled",
                build_exec_status="not_run",
            )
            build_log = "\n".join(lines) + "\n"
            self._persist_build_log(build_log_path=build_log_path, build_log=build_log)
            return (
                record.model_copy(
                    update={
                        "candidate_id": plan.candidate_ids[0] if plan.candidate_ids else None,
                        "status": "failed",
                        "failure_type": "feature_not_enabled",
                        "build_exec_status": "not_run",
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

        output_dir = build_log_path.parent.parent / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        builder_cmd = probe["builder_path"] or self.build_config.kpatch_build_cmd
        build_targets = self._infer_build_targets(
            source_dir=selected_source_dir,
            rewritten_patch_path=rewritten_patch_path,
        )
        # 输出目录固定在 attempt 目录下，方便 report/replay 直接定位本轮产物
        command = [
            builder_cmd,
            "-s",
            str(selected_source_dir),
            "-c",
            str(probe["config_path"]),
            "-v",
            self.build_config.vmlinux_path,
            "-n",
            self._module_name(task.task_id, attempt_no),
            "-o",
            str(output_dir),
        ]
        for build_target in build_targets:
            command.extend(["-t", build_target])
        command.append(str(rewritten_patch_path.resolve()))
        command_text = " ".join(shlex.quote(part) for part in command)
        if build_targets:
            lines.extend(["", "[build targets]", ", ".join(build_targets)])
        missing_cache_files = self._missing_module_build_cache_files(
            source_dir=selected_source_dir,
            build_targets=build_targets,
        )
        if missing_cache_files:
            summary_text = "源码树缺少模块构建缓存，已跳过 kpatch-build。"
            lines.extend(
                [
                    "",
                    "[build cache]",
                    summary_text,
                    "模块构建目标需要完整 prepared source tree 缓存",
                    "缺失文件: " + ", ".join(missing_cache_files),
                    "处理方式: 先执行 prepare-build-tree --warm-target vmlinux 或同步已预热源码树",
                ]
            )
            lines.extend(self._cleanup_generated_source_tree(generated_source_dir))
            summary = BuildSummary(
                task_id=task.task_id,
                attempt_id=record.attempt_id,
                backend="local",
                builder_cmd=builder_cmd,
                status="not_run",
                summary=summary_text,
                rewritten_patch_path=rewritten_patch_path,
                source_dir=precheck.source_dir,
                build_log_path=build_log_path,
                failure_type="build_cache_incomplete",
                build_exec_status="not_run",
            )
            build_log = "\n".join(lines) + "\n"
            self._persist_build_log(build_log_path=build_log_path, build_log=build_log)
            return (
                record.model_copy(
                    update={
                        "candidate_id": plan.candidate_ids[0] if plan.candidate_ids else None,
                        "status": "failed",
                        "failure_type": "build_cache_incomplete",
                        "build_exec_status": "not_run",
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
        lines.extend(["", "[local command]", command_text])

        exit_code: int | None = None
        module_path: Path | None = None
        failure_type = None
        stdout_text = ""
        stderr_text = ""

        command_result = self._run_build_command(
            command=command,
            cwd=selected_source_dir,
            timeout_sec=self.build_config.build_timeout_sec,
        )
        stdout_text = command_result["stdout"].strip()
        stderr_text = command_result["stderr"].strip()
        exit_code = int(command_result["exit_code"])
        if command_result["timed_out"]:
            failure_type = "compile_failed"
            lines.append(f"构建命令超时: {self.build_config.build_timeout_sec} 秒")
            lines.extend(command_result["cleanup_lines"])

        lines.extend(
            [
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
            module_path = self._find_local_module(output_dir)
            if module_path is None:
                # 有些异常场景下 kpatch-build 会返回 0，但没有真正产出模块
                # 这里继续按失败处理，避免把空结果误记成成功
                lines.append("本机构建命令返回成功，但输出目录中没有找到 .ko 文件。")
                exit_code = 2
                failure_type = "compile_failed"
        else:
            failure_type = failure_type or self._classify_command_failure(stdout_text=stdout_text, stderr_text=stderr_text)
            # kpatch 的详细日志通常在用户目录下
            # 命令本身报错不够直观时，再把最近的 build.log 一并捞进来
            local_kpatch_log = self._read_local_kpatch_log()
            if local_kpatch_log:
                lines.extend(["", "[local kpatch log]", local_kpatch_log])

        lines.extend(self._cleanup_generated_source_tree(generated_source_dir))

        status = "built" if exit_code == 0 and module_path is not None else "failed"
        final_failure_type = None if status == "built" else (failure_type or "compile_failed")
        build_log = "\n".join(lines) + "\n"
        self._persist_build_log(build_log_path=build_log_path, build_log=build_log)
        summary = BuildSummary(
            task_id=task.task_id,
            attempt_id=record.attempt_id,
            backend="local",
            builder_cmd=builder_cmd,
            status=status,
            summary="本机构建成功，并已记录模块产物。" if status == "built" else "本机构建失败，已生成结构化失败摘要。",
            rewritten_patch_path=rewritten_patch_path,
            source_dir=precheck.source_dir,
            build_log_path=build_log_path,
            module_path=module_path,
            failure_type=final_failure_type,
            build_exec_status="executed",
            exit_code=exit_code,
        )
        return (
            record.model_copy(
                update={
                    "candidate_id": plan.candidate_ids[0] if plan.candidate_ids else None,
                    "status": status,
                    "failure_type": final_failure_type,
                    "build_exec_status": "executed",
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
        """为未实际执行的预检查生成结构化结果"""

        return BuildPrecheck(
            task_id=task_id,
            attempt_id=attempt_id,
            backend=backend,
            ok=False,
            summary=summary,
            patch_path=rewritten_patch_path,
            source_dir=source_dir,
            failure_type=failure_type,
            build_exec_status="not_run",
            target_state="target_already_patched" if failure_type == "target_already_patched" else None,
        )

    def _persist_build_log(self, *, build_log_path: Path, build_log: str) -> None:
        """写构建日志前兜底创建目录，避免中途切树后日志落盘失败"""

        build_log_path.parent.mkdir(parents=True, exist_ok=True)
        build_log_path.write_text(build_log, encoding="utf-8")

    def _should_collapse_to_target_state(
        self,
        *,
        initial_precheck: BuildPrecheck | None,
        final_precheck: BuildPrecheck,
    ) -> bool:
        """判断首选源码树已修复但备用树未接住时是否按目标态收口"""

        if initial_precheck is None:
            return False
        if initial_precheck.failure_type != "target_already_patched":
            return False
        if final_precheck.ok:
            return False
        return final_precheck.failure_type != "target_already_patched"

    def _target_state_summary_after_switch(
        self,
        *,
        initial_precheck: BuildPrecheck | None,
        final_precheck: BuildPrecheck,
    ) -> str:
        """生成 target_state 场景下更贴近真实原因的阶段摘要"""

        if self._should_collapse_to_target_state(
            initial_precheck=initial_precheck,
            final_precheck=final_precheck,
        ):
            return "首选源码树已包含该补丁，备用源码树未能提供可继续构建的落点，本轮按目标态已修复收口。"
        return "目标源码已包含该补丁，已识别为目标态已修复，本机构建未执行。"

    def _format_precheck_lines(self, precheck: BuildPrecheck) -> list[str]:
        """把预检查结果展开成构建日志片段"""

        lines = [
            "",
            "[apply precheck]",
            precheck.summary,
            f"源码目录: {precheck.source_dir or '未找到'}",
            f"源码期望状态: {self._guess_source_expected_state(precheck.source_dir) or 'unknown'}",
            f"补丁路径: {precheck.patch_path}",
        ]
        if precheck.command:
            lines.append(f"命令: {precheck.command}")
        if precheck.stdout_excerpt:
            lines.extend(["[precheck stdout]", precheck.stdout_excerpt])
        if precheck.stderr_excerpt:
            lines.extend(["[precheck stderr]", precheck.stderr_excerpt])
        if precheck.build_exec_status:
            lines.append(f"构建执行状态: {precheck.build_exec_status}")
        if precheck.target_state:
            lines.append(f"目标态结论: {precheck.target_state}")
        return lines

    def _select_local_source_dir(self, *, exclude: set[Path] | None = None) -> tuple[Path | None, str | None]:
        """挑选本地可用的源码目录"""

        excluded = {item.resolve() for item in (exclude or set())}
        for slot_name, path in self._iter_source_candidates():
            try:
                resolved = path.resolve()
            except OSError:
                resolved = path
            if resolved in excluded:
                continue
            if self._local_kernel_tree_ok(path):
                return path, slot_name

        return None, None

    def _iter_source_candidates(self) -> Iterable[tuple[str, Path]]:
        """按配置顺序展开候选源码树"""

        seen: set[Path] = set()
        for slot_name in self.build_config.build_source_priority:
            raw_path = str(getattr(self.build_config, slot_name, "") or "").strip()
            if not raw_path:
                continue
            path = Path(raw_path)
            try:
                resolved = path.resolve()
            except OSError:
                resolved = path
            if resolved in seen:
                continue
            seen.add(resolved)
            yield slot_name, path

    def _source_candidate_snapshot(self) -> list[dict[str, object]]:
        """输出当前可见源码树列表，供 doctor 和日志复用"""

        snapshot: list[dict[str, object]] = []
        for slot_name, path in self._iter_source_candidates():
            snapshot.append(
                {
                    "slot": slot_name,
                    "path": str(path),
                    "ok": self._local_kernel_tree_ok(path),
                    "expected_state": self._source_slot_expected_state(slot_name),
                }
            )
        return snapshot

    def _source_slot_expected_state(self, slot_name: str | None) -> str | None:
        """根据源码槽位返回预期状态"""

        if slot_name is None:
            return None
        mapping = {
            "clean_kernel_src_dir": "unpatched",
            "prepared_kernel_src_dir": "likely_patched",
            "kernel_src_dir": "likely_patched",
            "kernel_devel_dir": "unknown",
            "patched_kernel_src_dir": "patched",
            "synthetic_reverse_tree": "unpatched",
        }
        return mapping.get(slot_name, "unknown")

    def _infer_build_targets(self, *, source_dir: Path, rewritten_patch_path: Path) -> list[str]:
        """根据补丁触达文件尽量收窄 kpatch-build 的构建目标"""

        if not getattr(self.build_config, "auto_build_targets", True):
            return []

        config_values = self._load_kernel_config_values(source_dir)
        touched_files = self._collect_patch_target_files(rewritten_patch_path)
        if not touched_files:
            return ["vmlinux"]

        module_targets: list[str] = []
        built_in_needed = False

        for relative_path in touched_files:
            resolved_target, target_state = self._resolve_build_target_detail(
                source_dir=source_dir,
                relative_path=relative_path,
                config_values=config_values,
            )
            if target_state == "disabled":
                continue
            if resolved_target is None:
                built_in_needed = True
                continue
            if resolved_target == "vmlinux":
                built_in_needed = True
                continue
            if resolved_target not in module_targets:
                module_targets.append(resolved_target)

        if not module_targets and not built_in_needed:
            return ["vmlinux"]

        expanded_module_targets = self._expand_module_dependency_targets(module_targets)

        if expanded_module_targets and not built_in_needed:
            return expanded_module_targets

        targets = ["vmlinux"]
        targets.extend(expanded_module_targets)
        return targets

    def _collect_disabled_patch_target_files(self, *, source_dir: Path, rewritten_patch_path: Path) -> list[str]:
        """收集当前内核配置下不会参与编译的源码文件"""

        config_values = self._load_kernel_config_values(source_dir)
        touched_files = self._collect_patch_target_files(rewritten_patch_path)
        disabled_files: list[str] = []
        for relative_path in touched_files:
            _, target_state = self._resolve_build_target_detail(
                source_dir=source_dir,
                relative_path=relative_path,
                config_values=config_values,
            )
            if target_state == "disabled":
                disabled_files.append(relative_path.as_posix())
        return disabled_files

    def _collect_mismatched_arch_patch_target_files(self, *, rewritten_patch_path: Path) -> list[str]:
        """收集不属于当前目标架构的补丁源码文件"""

        current_arch = self._current_kernel_arch()
        mismatched_files: list[str] = []
        for relative_path in self._collect_patch_target_files(rewritten_patch_path):
            parts = relative_path.parts
            if len(parts) >= 3 and parts[0] == "arch" and parts[1] != current_arch:
                mismatched_files.append(relative_path.as_posix())
        return mismatched_files

    def _current_kernel_arch(self) -> str:
        """把当前机器架构映射为内核源码 arch 目录名"""

        machine = platform.machine().lower()
        mapping = {
            "amd64": "x86",
            "x86_64": "x86",
            "i386": "x86",
            "i686": "x86",
            "aarch64": "arm64",
            "arm64": "arm64",
            "loongarch64": "loongarch",
            "ppc64le": "powerpc",
            "s390x": "s390",
        }
        return mapping.get(machine, machine)

    def _expand_module_dependency_targets(self, module_targets: list[str]) -> list[str]:
        """按已安装模块依赖补齐 kpatch-build 目标"""

        if not module_targets:
            return []
        if not getattr(self.build_config, "auto_expand_module_dependencies", True):
            return module_targets

        expanded: list[str] = []
        for target in module_targets:
            for dependency_target in self._module_dependency_targets(target):
                if dependency_target not in expanded:
                    expanded.append(dependency_target)
            if target not in expanded:
                expanded.append(target)
        return expanded

    def _module_dependency_targets(self, module_target: str) -> list[str]:
        """通过 modinfo depends 推导模块依赖的源码树构建目标"""

        modinfo = which("modinfo")
        if modinfo is None:
            return []

        kernel_release = self._target_kernel_release()
        module_name = self._module_name_from_build_target(module_target)
        if not module_name:
            return []

        dependency_targets: list[str] = []
        seen_modules = {module_name}

        def visit(current_module: str, depth: int) -> None:
            if depth > 6:
                return
            depends_result = self._run_modinfo([modinfo, "-k", kernel_release, "-F", "depends", current_module])
            if depends_result.returncode != 0:
                return

            dependency_names = [
                item.strip()
                for item in depends_result.stdout.replace("\n", ",").split(",")
                if item.strip()
            ]
            for dependency_name in dependency_names:
                if dependency_name in seen_modules:
                    continue
                seen_modules.add(dependency_name)
                visit(dependency_name, depth + 1)
                dependency_target = self._module_target_from_modinfo(
                    modinfo=modinfo,
                    kernel_release=kernel_release,
                    module_name=dependency_name,
                )
                if dependency_target and dependency_target != module_target and dependency_target not in dependency_targets:
                    dependency_targets.append(dependency_target)

        visit(module_name, 0)
        return dependency_targets

    def _module_target_from_modinfo(self, *, modinfo: str, kernel_release: str, module_name: str) -> str | None:
        """查询单个模块对应的源码树构建目标"""

        path_result = self._run_modinfo([modinfo, "-k", kernel_release, "-n", module_name])
        if path_result.returncode != 0:
            return None
        return self._installed_module_path_to_build_target(
            installed_path=path_result.stdout.strip(),
            kernel_release=kernel_release,
        )

    def _run_modinfo(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        """执行 modinfo 查询，失败时让调用方按无依赖处理"""

        try:
            return subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return subprocess.CompletedProcess(command, returncode=1, stdout="", stderr=str(exc))

    def _target_kernel_release(self) -> str:
        """从 vmlinux 路径推导目标内核版本"""

        normalized = str(self.build_config.vmlinux_path).replace("\\", "/")
        match = re.search(r"/lib/modules/([^/]+)/vmlinux$", normalized)
        if match is not None:
            return match.group(1)
        return platform.release()

    def _module_name_from_build_target(self, module_target: str) -> str | None:
        """从 foo/bar.ko 目标中取出 modinfo 能识别的模块名"""

        name = Path(module_target).name
        for suffix in [".ko.xz", ".ko.zst", ".ko.gz", ".ko"]:
            if name.endswith(suffix):
                return name[: -len(suffix)]
        return None

    def _installed_module_path_to_build_target(self, *, installed_path: str, kernel_release: str) -> str | None:
        """把 /lib/modules 下的模块路径转回源码树 make target"""

        normalized = installed_path.strip().replace("\\", "/")
        marker = f"/lib/modules/{kernel_release}/kernel/"
        if marker not in normalized:
            return None
        relative = normalized.split(marker, 1)[1]
        for suffix in [".ko.xz", ".ko.zst", ".ko.gz"]:
            if relative.endswith(suffix):
                relative = relative[: -len(suffix)] + ".ko"
                break
        if not relative.endswith(".ko"):
            return None
        return relative

    def _collect_patch_target_files(self, patch_path: Path) -> list[Path]:
        """从 unified diff 里提取本轮实际触达的源码文件"""

        with patch_path.open("r", encoding="utf-8", errors="replace") as handle:
            patch_set = PatchSet(handle)

        touched_files: list[Path] = []
        for patched_file in patch_set:
            relative_path = getattr(patched_file, "path", None)
            if not relative_path:
                continue
            normalized = self._normalize_patch_relative_path(relative_path)
            if normalized is None or normalized in touched_files:
                continue
            touched_files.append(normalized)
        return touched_files

    def _normalize_patch_relative_path(self, raw_path: str) -> Path | None:
        """把 patch 里的 a/ b/ 路径整理成源码树相对路径"""

        normalized = raw_path.strip()
        if not normalized or normalized == "/dev/null":
            return None
        if normalized.startswith("a/") or normalized.startswith("b/"):
            normalized = normalized[2:]
        return Path(normalized)

    def _load_kernel_config_values(self, source_dir: Path) -> dict[str, str]:
        """读取 .config 里和目标推导有关的开关值"""

        config_path = source_dir / ".config"
        if not config_path.exists():
            return {}

        values: dict[str, str] = {}
        for raw_line in config_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw_line.strip()
            if not line.startswith("CONFIG_") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key] = value.strip()
        return values

    def _resolve_build_target_for_path(
        self,
        *,
        source_dir: Path,
        relative_path: Path,
        config_values: dict[str, str],
    ) -> str | None:
        """把源码文件映射成更贴近实际的 make target"""

        resolved_target, _ = self._resolve_build_target_detail(
            source_dir=source_dir,
            relative_path=relative_path,
            config_values=config_values,
        )
        return resolved_target

    def _resolve_build_target_detail(
        self,
        *,
        source_dir: Path,
        relative_path: Path,
        config_values: dict[str, str],
    ) -> tuple[str | None, str]:
        """返回源码文件对应的构建目标，以及当前内核配置下的启用状态"""

        if relative_path.suffix != ".c":
            return "vmlinux", "built_in"

        if self._directory_gate_state(
            source_dir=source_dir,
            relative_dir=relative_path.parent,
            config_values=config_values,
        ) == "disabled":
            return None, "disabled"

        file_name = relative_path.name
        object_name = relative_path.with_suffix(".o").name
        makefile_lines = self._load_kbuild_lines(source_dir / relative_path.parent)
        if not makefile_lines:
            return "vmlinux", "unknown"

        composite_object = self._find_composite_object(makefile_lines, member_object=object_name)
        final_object = composite_object or object_name
        final_target, target_state = self._find_final_kbuild_target_detail(
            makefile_lines,
            final_object=final_object,
            relative_dir=relative_path.parent,
            config_values=config_values,
        )
        if final_target is not None:
            return final_target, target_state

        if target_state == "disabled":
            return None, "disabled"

        if composite_object is not None:
            return "vmlinux", "unknown"

        if self._file_is_direct_module_member(makefile_lines, file_name=file_name):
            return "vmlinux", "unknown"

        return "vmlinux", "unknown"

    def _directory_gate_state(
        self,
        *,
        source_dir: Path,
        relative_dir: Path,
        config_values: dict[str, str],
    ) -> str:
        """检查源码目录链路里是否存在被 .config 关闭的子目录门控"""

        current_dir = Path()
        for part in relative_dir.parts:
            makefile_lines = self._load_kbuild_lines(source_dir / current_dir)
            gate_state = self._match_directory_gate(makefile_lines, subdir_name=part, config_values=config_values)
            if gate_state == "disabled":
                return "disabled"
            current_dir = current_dir / part
        return "enabled"

    def _match_directory_gate(
        self,
        makefile_lines: list[str],
        *,
        subdir_name: str,
        config_values: dict[str, str],
    ) -> str:
        """识别 obj-$(CONFIG_*) += foo/ 这类目录级门控是否被关闭"""

        pattern = re.compile(
            r"^obj-(?:(?P<config>\$\([^)]+\))|(?P<literal>[ym]))\s*[:+]?=\s*(?P<rest>.+)$"
        )
        token_name = f"{subdir_name}/"
        saw_disabled_match = False

        for line in makefile_lines:
            match = pattern.match(line)
            if match is None:
                continue
            tokens = match.group("rest").split()
            if token_name not in tokens:
                continue

            config_token = match.group("config")
            if config_token:
                config_key = config_token[2:-1]
                state = config_values.get(config_key)
            else:
                state = match.group("literal")

            if state in {"m", "y"}:
                return "enabled"
            if config_token and state not in {"m", "y"}:
                saw_disabled_match = True

        return "disabled" if saw_disabled_match else "unknown"

    def _load_kbuild_lines(self, directory: Path) -> list[str]:
        """读取 Makefile 或 Kbuild，并按续行拼成逻辑行"""

        for candidate_name in ["Makefile", "Kbuild"]:
            candidate = directory / candidate_name
            if not candidate.exists():
                continue
            content = candidate.read_text(encoding="utf-8", errors="replace")
            return self._collapse_make_lines(content)
        return []

    def _collapse_make_lines(self, content: str) -> list[str]:
        """把 Makefile 里的反斜杠续行合并起来，方便后续规则匹配"""

        logical_lines: list[str] = []
        pending = ""
        for raw_line in content.splitlines():
            body, _, _ = raw_line.partition("#")
            stripped = body.rstrip()
            if not stripped:
                continue
            if stripped.endswith("\\"):
                pending += stripped[:-1].rstrip() + " "
                continue
            combined = (pending + stripped).strip()
            pending = ""
            if combined:
                logical_lines.append(combined)
        if pending.strip():
            logical_lines.append(pending.strip())
        return logical_lines

    def _find_composite_object(self, makefile_lines: list[str], *, member_object: str) -> str | None:
        """判断当前 .c 是否只是某个复合目标的一部分"""

        pattern = re.compile(r"^(?P<parent>[\w-]+)-(?:objs|y|m|\$\([^)]+\))\s*[:+]?=\s*(?P<rest>.+)$")
        for line in makefile_lines:
            match = pattern.match(line)
            if match is None:
                continue
            parent_name = match.group("parent")
            # obj-y / lib-y 这类聚合变量只是把目标并到当前目录
            # 不能把它们误当成某个复合对象，否则会把最终目标错写成 obj.o / lib.o
            if parent_name in {"obj", "lib", "always", "extra", "subdir", "targets"}:
                continue
            members = match.group("rest").split()
            if member_object in members:
                return f"{parent_name}.o"
        return None

    def _find_final_kbuild_target(
        self,
        makefile_lines: list[str],
        *,
        final_object: str,
        relative_dir: Path,
        config_values: dict[str, str],
    ) -> str | None:
        """从 obj-* 规则里推导最终会生成的目标"""

        target, _ = self._find_final_kbuild_target_detail(
            makefile_lines,
            final_object=final_object,
            relative_dir=relative_dir,
            config_values=config_values,
        )
        return target

    def _find_final_kbuild_target_detail(
        self,
        makefile_lines: list[str],
        *,
        final_object: str,
        relative_dir: Path,
        config_values: dict[str, str],
    ) -> tuple[str | None, str]:
        """从 obj-* 规则里推导最终目标，并保留启用/禁用状态"""

        pattern = re.compile(
            r"^obj-(?:(?P<config>\$\([^)]+\))|(?P<literal>[ym]))\s*[:+]?=\s*(?P<rest>.+)$"
        )
        relative_dir_text = relative_dir.as_posix()
        saw_disabled_match = False

        for line in makefile_lines:
            match = pattern.match(line)
            if match is None:
                continue
            tokens = match.group("rest").split()
            if final_object not in tokens:
                continue

            config_token = match.group("config")
            if config_token:
                config_key = config_token[2:-1]
                state = config_values.get(config_key)
            else:
                state = match.group("literal")

            if state == "m":
                target_name = final_object.removesuffix(".o") + ".ko"
                if relative_dir_text in {"", "."}:
                    return target_name, "module"
                return f"{relative_dir_text}/{target_name}", "module"
            if state == "y":
                return "vmlinux", "built_in"
            if config_token and state not in {"m", "y"}:
                saw_disabled_match = True
        return None, ("disabled" if saw_disabled_match else "unknown")

    def _file_is_direct_module_member(self, makefile_lines: list[str], *, file_name: str) -> bool:
        """识别以 source 形式直接挂到模块规则里的少见写法"""

        pattern = re.compile(r"^[\w-]+-(?:src|y|m)\s*[:+]?=\s*(?P<rest>.+)$")
        for line in makefile_lines:
            match = pattern.match(line)
            if match is None:
                continue
            if file_name in match.group("rest").split():
                return True
        return False

    def _has_vmlinux_build_state(self, source_dir: Path) -> bool:
        """判断源码树里是否已经具备可复用的 vmlinux 构建缓存"""

        return (source_dir / "vmlinux.o").exists() and (source_dir / "Module.symvers").exists()

    def _missing_module_build_cache_files(self, *, source_dir: Path, build_targets: list[str]) -> list[str]:
        """返回模块目标构建所需但当前源码树缺失的缓存文件"""

        if not any(target.endswith(".ko") for target in build_targets):
            return []
        required_files = ["Module.symvers", "vmlinux.o", "vmlinux.a", ".vmlinux.objs"]
        return [name for name in required_files if not (source_dir / name).exists()]

    def _prepare_reverse_source_tree(
        self,
        *,
        patched_source_dir: Path,
        rewritten_patch_path: Path,
        attempt_dir: Path,
    ) -> tuple[Path | None, list[str]]:
        """从已修复源码树反向生成一棵本轮可用的未修复树"""

        reverse_source_dir = attempt_dir / "sources" / "reverse_unpatched"
        lines = [
            "",
            "[reverse source tree]",
            f"已修复源码树: {patched_source_dir}",
            f"反向源码树: {reverse_source_dir}",
        ]

        if not patched_source_dir.is_dir():
            lines.append("反向源码树生成失败: 已修复源码树不存在")
            return None, lines

        try:
            if reverse_source_dir.exists():
                shutil.rmtree(reverse_source_dir)
            reverse_source_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(patched_source_dir, reverse_source_dir, symlinks=True)
        except OSError as exc:
            lines.append(f"反向源码树复制失败: {exc}")
            lines.extend(self._cleanup_generated_source_tree(reverse_source_dir, force=True))
            return None, lines

        setlocalversion_ready = patch_setlocalversion_for_kpatch(reverse_source_dir)
        if setlocalversion_ready:
            lines.append("setlocalversion 兼容处理完成: 支持 kpatch-build --save-scmversion")
        else:
            lines.append("setlocalversion 兼容处理跳过: 未找到 scripts/setlocalversion")

        git_path = which("git")
        if git_path is None:
            lines.append("反向源码树生成失败: 未找到 git 命令")
            return None, lines

        check_command = [git_path, "apply", "--reverse", "--check", "--verbose", str(rewritten_patch_path.resolve())]
        check_result = subprocess.run(
            check_command,
            cwd=reverse_source_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        lines.append("反向检查命令: " + " ".join(shlex.quote(part) for part in check_command))
        if check_result.stdout.strip():
            lines.extend(["[reverse check stdout]", check_result.stdout.strip()[:2000]])
        if check_result.stderr.strip():
            lines.extend(["[reverse check stderr]", check_result.stderr.strip()[:2000]])
        if check_result.returncode != 0:
            lines.append("反向源码树生成失败: 当前补丁无法从已修复源码树回退")
            lines.extend(self._cleanup_generated_source_tree(reverse_source_dir))
            return None, lines

        apply_command = [git_path, "apply", "--reverse", "--verbose", str(rewritten_patch_path.resolve())]
        apply_result = subprocess.run(
            apply_command,
            cwd=reverse_source_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        lines.append("反向应用命令: " + " ".join(shlex.quote(part) for part in apply_command))
        if apply_result.stdout.strip():
            lines.extend(["[reverse apply stdout]", apply_result.stdout.strip()[:2000]])
        if apply_result.stderr.strip():
            lines.extend(["[reverse apply stderr]", apply_result.stderr.strip()[:2000]])
        if apply_result.returncode != 0:
            lines.append("反向源码树生成失败: 反向应用 patch 未成功")
            lines.extend(self._cleanup_generated_source_tree(reverse_source_dir))
            return None, lines

        lines.extend(self._normalize_x86_function_padding(reverse_source_dir))
        lines.append("反向源码树生成完成，继续在该源码树上执行 apply precheck")
        return reverse_source_dir, lines

    def _normalize_x86_function_padding(self, source_dir: Path) -> list[str]:
        """修正 x86 函数入口 padding，避开 kpatch diff-object offset 识别问题"""

        if not getattr(self.build_config, "normalize_x86_function_padding_for_kpatch", True):
            return []

        makefile_path = source_dir / "arch" / "x86" / "Makefile"
        lines = ["", "[kpatch source normalization]", f"x86 Makefile: {makefile_path}"]
        if not makefile_path.exists():
            lines.append("跳过函数入口 padding 修正: arch/x86/Makefile 不存在")
            return lines

        original = makefile_path.read_text(encoding="utf-8", errors="replace")
        normalized = original.replace(
            "-fpatchable-function-entry=$(CONFIG_FUNCTION_PADDING_BYTES),$(CONFIG_FUNCTION_PADDING_BYTES)",
            "-fpatchable-function-entry=$(CONFIG_FUNCTION_PADDING_BYTES),0",
        )
        if normalized == original:
            lines.append("函数入口 padding 已经符合 kpatch 构建要求")
            return lines

        makefile_path.write_text(normalized, encoding="utf-8")
        lines.append("已将 -fpatchable-function-entry 第二参数归零")
        return lines

    def _cleanup_generated_source_tree(self, source_dir: Path | None, *, force: bool = False) -> list[str]:
        """清理 attempt 内生成的临时源码树"""

        if source_dir is None:
            return []
        if not force and not getattr(self.build_config, "cleanup_generated_source_tree", True):
            return []

        if not self._is_safe_generated_source_dir(source_dir):
            return [
                "",
                "[source cleanup]",
                f"跳过临时源码树清理，路径不在 attempt/sources 下: {source_dir}",
            ]

        lines = ["", "[source cleanup]", f"临时源码树: {source_dir}"]
        if not source_dir.exists():
            lines.append("临时源码树不存在，无需清理")
            return lines

        try:
            shutil.rmtree(source_dir)
            lines.append("临时源码树已清理")
        except OSError as exc:
            lines.append(f"临时源码树清理失败: {exc}")
        return lines

    def _is_safe_generated_source_dir(self, source_dir: Path) -> bool:
        """限制自动清理范围，避免误删真实源码树"""

        parts = source_dir.parts
        return len(parts) >= 3 and parts[-1] == "reverse_unpatched" and parts[-2] == "sources"

    def _config_path_for_source(self, source_dir: Path | None) -> Path | None:
        """返回当前源码树对应的 .config 路径"""

        if source_dir is None:
            return None
        return source_dir / ".config"

    def _override_selected_source(
        self,
        *,
        probe: dict[str, Any],
        source_dir: Path,
        source_reason: str | None,
    ) -> dict[str, Any]:
        """把选中的源码树切到新的候选项"""

        updated = dict(probe)
        config_path = self._config_path_for_source(source_dir)
        updated["selected_source_dir"] = str(source_dir)
        updated["selected_source_ok"] = True
        updated["selected_source_reason"] = source_reason
        updated["selected_source_expected_state"] = self._source_slot_expected_state(source_reason)
        updated["config_path"] = str(config_path) if config_path else None
        updated["config_ok"] = config_path.exists() if config_path is not None else False
        return updated

    def _guess_source_expected_state(self, source_dir: str | None) -> str | None:
        """根据路径反推当前源码树在配置里的角色"""

        if source_dir is None:
            return None
        candidate_path = Path(source_dir)
        for slot_name, path in self._iter_source_candidates():
            try:
                if path.resolve() == candidate_path.resolve():
                    return self._source_slot_expected_state(slot_name)
            except OSError:
                if str(path) == str(candidate_path):
                    return self._source_slot_expected_state(slot_name)
        if candidate_path.name == "reverse_unpatched":
            return self._source_slot_expected_state("synthetic_reverse_tree")
        return "unknown"

    def _local_kernel_tree_ok(self, path: Path) -> bool:
        """判断本地目录能否作为内核源码树使用"""

        return path.is_dir() and (path / "Makefile").exists()

    def _probe_failure_type(self, probe: dict[str, Any]) -> str | None:
        """把预检结果映射成统一失败类型"""

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
        """生成更容易看懂的失败提示"""

        messages = {
            "build_env_missing": f"未找到构建命令：{self.build_config.kpatch_build_cmd}",
            "kernel_src_missing": "找不到可用的内核源码目录，已检查 clean_kernel_src_dir、prepared_kernel_src_dir、kernel_src_dir、kernel_devel_dir 和 patched_kernel_src_dir。",
            "kernel_config_missing": "源码目录中没有找到 .config，暂时无法继续构建。",
            "vmlinux_missing": "找不到可用的 vmlinux 文件，无法继续构建。",
            "target_already_patched": "目标源码已包含该补丁，无需重复应用，请更换未修复内核或切换样例。",
            "feature_not_enabled": "目标内核配置未启用补丁涉及源码，当前验证内核不会编译出对应对象。",
        }
        return messages.get(failure_type, "构建环境检查未通过。")

    def _summarize_precheck_failure(
        self,
        *,
        stdout_text: str,
        stderr_text: str,
        failure_type: str | None = None,
    ) -> str:
        """为 apply 级预检查生成摘要"""

        if failure_type == "target_already_patched":
            return "目标源码已包含该补丁，apply 预检查判定无需重复应用。"
        for raw_text in [stderr_text, stdout_text]:
            for line in raw_text.splitlines():
                stripped = line.strip()
                if stripped:
                    return stripped
        return "apply 级预检查未通过。"

    def _classify_apply_precheck_failure(self, *, stdout_text: str, stderr_text: str) -> str:
        """根据 apply 级预检查输出归类失败原因"""

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

    def _looks_like_skipped_patch_output(self, *, stdout_text: str, stderr_text: str) -> bool:
        """识别 git apply 输出中的 skipped patch 信号。"""

        combined = f"{stdout_text}\n{stderr_text}".lower()
        return "skipped patch" in combined

    def _patch_looks_already_applied_locally(self, *, patch_path: Path, source_dir: Path) -> bool:
        """根据目标文件内容确认补丁是否已经体现在源码树中。"""

        return self._patch_looks_already_applied(
            patch_path=patch_path,
            reader=lambda relative_path: self._read_local_text(source_dir / relative_path),
        )

    def _patch_looks_already_applied(self, *, patch_path: Path, reader) -> bool:
        """检查补丁新增行是否已存在且旧行是否已消失。"""

        with patch_path.open("r", encoding="utf-8", errors="replace") as handle:
            patch_set = PatchSet(handle)

        inspected = False
        for patched_file in patch_set:
            relative_path = getattr(patched_file, "path", None)
            if not relative_path:
                continue
            target_text = reader(relative_path)
            if target_text is None:
                return False
            target_lines = self._normalize_lines(target_text.splitlines())
            file_inspected = False
            for hunk in patched_file:
                for added_block, removed_block in self._collect_change_blocks(hunk):
                    if added_block and not self._contains_block(target_lines, added_block):
                        return False
                    if removed_block and self._contains_block(target_lines, removed_block):
                        return False
                    file_inspected = True
            inspected = inspected or file_inspected

        return inspected

    def _collect_change_blocks(self, hunk: object) -> list[tuple[list[str], list[str]]]:
        """按上下文行切分 hunk 内连续变更块。"""

        blocks: list[tuple[list[str], list[str]]] = []
        added_lines: list[str] = []
        removed_lines: list[str] = []

        def flush() -> None:
            nonlocal added_lines, removed_lines
            normalized_added = self._normalize_lines(added_lines)
            normalized_removed = self._normalize_lines(removed_lines)
            if normalized_added or normalized_removed:
                blocks.append((normalized_added, normalized_removed))
            added_lines = []
            removed_lines = []

        for line in hunk:
            value = line.value.rstrip("\n")
            if line.line_type == "+":
                added_lines.append(value)
            elif line.line_type == "-":
                removed_lines.append(value)
            else:
                flush()
        flush()
        return blocks

    def _normalize_lines(self, lines: Iterable[str]) -> list[str]:
        """规整行内容，减少缩进差异对匹配的影响。"""

        normalized: list[str] = []
        for line in lines:
            compact = " ".join(line.strip().split())
            if compact:
                normalized.append(compact)
        return normalized

    def _contains_block(self, target_lines: list[str], block_lines: list[str]) -> bool:
        """判断目标文件中是否存在按顺序连续出现的代码块。"""

        if not block_lines or len(target_lines) < len(block_lines):
            return False
        for index in range(len(target_lines) - len(block_lines) + 1):
            if target_lines[index : index + len(block_lines)] == block_lines:
                return True
        return False

    def _read_local_text(self, path: Path) -> str | None:
        """读取本地源码文件。"""

        if not path.exists():
            return None
        return path.read_text(encoding="utf-8", errors="replace")

    def _run_build_command(
        self,
        *,
        command: list[str],
        cwd: Path,
        timeout_sec: int,
    ) -> dict[str, object]:
        """执行构建命令并在超时时清理整棵子进程树"""

        creationflags = 0
        start_new_session = False
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            start_new_session = True

        process = subprocess.Popen(
            command,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            start_new_session=start_new_session,
            creationflags=creationflags,
        )
        try:
            stdout_text, stderr_text = process.communicate(timeout=timeout_sec)
            return {
                "stdout": stdout_text,
                "stderr": stderr_text,
                "exit_code": process.returncode,
                "timed_out": False,
                "cleanup_lines": [],
            }
        except subprocess.TimeoutExpired:
            cleanup_lines = self._cleanup_timed_out_process(process)
            try:
                stdout_text, stderr_text = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                stdout_text, stderr_text = "", ""
                cleanup_lines.append("构建进程组清理后仍未退出")
            return {
                "stdout": self._normalize_process_output(stdout_text),
                "stderr": self._normalize_process_output(stderr_text),
                "exit_code": -1,
                "timed_out": True,
                "cleanup_lines": cleanup_lines,
            }

    def _cleanup_timed_out_process(self, process: subprocess.Popen[str]) -> list[str]:
        """清理超时构建命令及其子进程"""

        cleanup_lines = ["[process cleanup]"]
        if process.poll() is not None:
            cleanup_lines.append(f"构建进程已退出: pid={process.pid}")
            return cleanup_lines

        if os.name == "nt":
            cleanup_lines.extend(self._cleanup_windows_process_tree(process))
        else:
            cleanup_lines.extend(self._cleanup_posix_process_group(process))
        return cleanup_lines

    def _cleanup_posix_process_group(self, process: subprocess.Popen[str]) -> list[str]:
        """按 POSIX 进程组清理构建子进程"""

        lines: list[str] = []
        pgids = self._collect_posix_descendant_process_groups(process.pid)
        pgids.add(process.pid)
        lines.extend(self._terminate_posix_process_groups(pgids, signal.SIGTERM))

        try:
            process.wait(timeout=3)
            lines.append(f"构建进程组已在 SIGTERM 后退出: pgid={process.pid}")
            return lines
        except subprocess.TimeoutExpired:
            lines.append(f"构建进程组 SIGTERM 后仍在运行: pgid={process.pid}")

        lines.extend(self._terminate_posix_process_groups(pgids, signal.SIGKILL))
        return lines

    def _collect_posix_descendant_process_groups(self, root_pid: int) -> set[int]:
        """收集构建命令下游子进程所在的 POSIX 进程组"""

        try:
            snapshot = subprocess.run(
                ["ps", "-eo", "pid=,ppid=,pgid="],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            ).stdout
        except OSError:
            return set()
        return self._parse_posix_descendant_process_groups(root_pid=root_pid, ps_output=snapshot)

    def _parse_posix_descendant_process_groups(self, root_pid: int, ps_output: str) -> set[int]:
        """从 ps 输出解析下游 PGID，覆盖子进程自行 setsid 的情况"""

        children_by_parent: dict[int, list[tuple[int, int]]] = {}
        for line in ps_output.splitlines():
            parts = line.split(None, 2)
            if len(parts) < 3:
                continue
            try:
                pid = int(parts[0])
                ppid = int(parts[1])
                pgid = int(parts[2])
            except ValueError:
                continue
            children_by_parent.setdefault(ppid, []).append((pid, pgid))

        pgids: set[int] = set()
        pending = [root_pid]
        seen: set[int] = set()
        while pending:
            parent = pending.pop()
            if parent in seen:
                continue
            seen.add(parent)
            for child_pid, child_pgid in children_by_parent.get(parent, []):
                if child_pgid > 0:
                    pgids.add(child_pgid)
                pending.append(child_pid)
        return pgids

    def _terminate_posix_process_groups(self, pgids: set[int], sig: signal.Signals) -> list[str]:
        """逐个终止进程组，避免构建超时后留下孤儿进程"""

        lines: list[str] = []
        for pgid in sorted(pgids, reverse=True):
            try:
                os.killpg(pgid, sig)
                lines.append(f"已发送 {sig.name} 到构建进程组: pgid={pgid}")
            except ProcessLookupError:
                lines.append(f"构建进程组已经退出: pgid={pgid}")
            except OSError as exc:
                lines.append(f"发送 {sig.name} 失败: pgid={pgid}, {exc}")
        return lines

    def _cleanup_windows_process_tree(self, process: subprocess.Popen[str]) -> list[str]:
        """在 Windows 上使用 taskkill 清理构建进程树"""

        lines: list[str] = []
        taskkill = shutil.which("taskkill")
        if taskkill is None:
            process.kill()
            lines.append(f"未找到 taskkill，已终止构建进程: pid={process.pid}")
            return lines

        result = subprocess.run(
            [taskkill, "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        lines.append(f"已执行 taskkill 清理构建进程树: pid={process.pid}, exit={result.returncode}")
        if result.stdout.strip():
            lines.append(result.stdout.strip()[:1000])
        if result.stderr.strip():
            lines.append(result.stderr.strip()[:1000])
        return lines

    def _classify_command_failure(self, *, stdout_text: str, stderr_text: str) -> str:
        """根据构建命令的直接输出给出一层快速归因"""

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
        if "unsupported section change" in combined:
            return "kpatch_constraint"
        if "section mismatch" in combined or "unsupported" in combined and "kpatch" in combined:
            return "kpatch_constraint"
        return "compile_failed"

    def _find_local_module(self, output_dir: Path) -> Path | None:
        """在输出目录中查找构建生成的模块"""

        candidates = sorted(output_dir.rglob("*.ko"))
        return candidates[0] if candidates else None

    def _read_local_kpatch_log(self) -> str | None:
        """读取当前运行机上最近的 kpatch 调试日志"""

        log_path = Path.home() / ".kpatch" / "build.log"
        if not log_path.exists():
            return None
        try:
            return self._tail_text(log_path, line_count=40)
        except OSError:
            return None

    def _tail_text(self, path: Path, *, line_count: int) -> str:
        """读取文本文件最后若干行"""

        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-line_count:]).strip()

    def _normalize_process_output(self, value: str | bytes | None) -> str:
        """把 subprocess 的异常输出统一整理成字符串"""

        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return value

    def _module_name(self, task_id: str, attempt_no: int) -> str:
        """生成模块名"""

        normalized = task_id.lower().replace("_", "-")
        return f"patchweaver-{normalized}-{attempt_no:03d}"
