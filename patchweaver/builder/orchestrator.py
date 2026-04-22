"""构建编排与本机构建执行"""

from __future__ import annotations

import shlex
import platform
import subprocess
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from shutil import which
from typing import Any

from patchweaver.models.attempt import AttemptRecord, BuildPrecheck, BuildSummary
from patchweaver.models.rewrite import RewritePlan
from patchweaver.models.task import TaskContext
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
            build_log_path.write_text(build_log, encoding="utf-8")
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
        precheck = self.precheck_patch(
            task_id=task.task_id,
            attempt_id=record.attempt_id,
            rewritten_patch_path=rewritten_patch_path,
            source_dir=selected_source_dir,
        )
        lines.extend(self._format_precheck_lines(precheck))

        if (
            not precheck.ok
            and precheck.failure_type == "target_already_patched"
            and getattr(self.build_config, "auto_switch_source_tree", False)
        ):
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

        if not precheck.ok:
            failure_type = precheck.failure_type or "patch_apply_failed"
            target_state = "target_already_patched" if failure_type == "target_already_patched" else None
            attempt_status = "target_state" if target_state else "failed"
            summary_text = (
                "目标源码已包含该补丁，已识别为目标态已修复，本机构建未执行。"
                if target_state
                else "apply 级预检查未通过，已跳过本机构建。"
            )
            # apply 级预检查没过时，不继续碰 kpatch-build
            # 这样失败原因会更集中，不会被后续一串派生报错淹没
            lines.append(summary_text)
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
                failure_type=failure_type,
                build_exec_status="not_run",
                target_state=target_state,
            )
            build_log = "\n".join(lines) + "\n"
            build_log_path.write_text(build_log, encoding="utf-8")
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

        output_dir = build_log_path.parent.parent / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        builder_cmd = probe["builder_path"] or self.build_config.kpatch_build_cmd
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
            str(rewritten_patch_path.resolve()),
        ]
        command_text = " ".join(shlex.quote(part) for part in command)
        lines.extend(["", "[local command]", command_text])

        exit_code: int | None = None
        module_path: Path | None = None
        failure_type = None
        stdout_text = ""
        stderr_text = ""

        try:
            # 这里保持一次性执行，不做流式输出
            # 一方面简化最小 MVP，另一方面方便把 stdout/stderr 成块写进构建日志
            result = subprocess.run(
                command,
                cwd=str(selected_source_dir),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=self.build_config.build_timeout_sec,
            )
            stdout_text = result.stdout.strip()
            stderr_text = result.stderr.strip()
            exit_code = result.returncode
        except subprocess.TimeoutExpired as exc:
            stdout_text = self._normalize_process_output(exc.stdout).strip()
            stderr_text = self._normalize_process_output(exc.stderr).strip()
            exit_code = -1
            failure_type = "compile_failed"
            lines.append(f"构建命令超时：{self.build_config.build_timeout_sec} 秒。")

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

        status = "built" if exit_code == 0 and module_path is not None else "failed"
        final_failure_type = None if status == "built" else (failure_type or "compile_failed")
        build_log = "\n".join(lines) + "\n"
        build_log_path.write_text(build_log, encoding="utf-8")
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
            "kernel_src_dir": "unknown",
            "kernel_devel_dir": "unknown",
            "patched_kernel_src_dir": "patched",
        }
        return mapping.get(slot_name, "unknown")

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
            "kernel_src_missing": "找不到可用的内核源码目录，已检查 clean_kernel_src_dir、kernel_src_dir、kernel_devel_dir 和 patched_kernel_src_dir。",
            "kernel_config_missing": "源码目录中没有找到 .config，暂时无法继续构建。",
            "vmlinux_missing": "找不到可用的 vmlinux 文件，无法继续构建。",
            "target_already_patched": "目标源码已包含该补丁，无需重复应用，请更换未修复内核或切换样例。",
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
