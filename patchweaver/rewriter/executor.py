"""改写执行骨架"""

from __future__ import annotations

import json
from pathlib import Path

from patchweaver.models.patch import PatchBundle
from patchweaver.models.rewrite import RewritePlan, TransformationStep, TransformationTrace
from patchweaver.rewriter.diff_editor import DiffEditor
from patchweaver.rewriter.smpl_engine import SmPLEngine
from patchweaver.rewriter.template_engine import TemplateEngine
from patchweaver.utils.path_policy import relativize_payload, to_project_relative


class RewriteExecutor:
    """负责把 RewritePlan 落地为补丁文件"""

    def __init__(self, project_root: Path) -> None:
        """初始化改写分层执行器"""

        self.template_engine = TemplateEngine(project_root)
        self.smpl_engine = SmPLEngine(project_root)
        self.diff_editor = DiffEditor()
        self.project_root = project_root.resolve()

    def execute(
        self,
        *,
        plan: RewritePlan,
        patch_bundle: PatchBundle,
        rewrite_dir: Path,
        builder: object,
        task_id: str,
        attempt_no: int,
    ) -> dict[str, object]:
        """输出 rewritten.patch 及其配套元数据"""

        source_patch_path = patch_bundle.normalized_patch_path or patch_bundle.raw_patch_path
        if source_patch_path is None:
            raise ValueError("PatchBundle 缺少可用的原始 patch 路径。")

        rewrite_dir.mkdir(parents=True, exist_ok=True)
        source_patch_text = source_patch_path.read_text(encoding="utf-8")
        dispatch_step = self._route_dispatch_step(plan)
        template_patch, template_step = self.template_engine.render(
            recipe_name=plan.selected_recipe,
            patch_text=source_patch_text,
            target_files=plan.target_files,
        )
        smpl_patch, smpl_step = self.smpl_engine.apply(plan=plan, patch_text=template_patch)
        rewritten_patch_path, diff_step = self.diff_editor.materialize(
            plan=plan,
            patch_text=smpl_patch,
            target_path=rewrite_dir / "rewritten.patch",
        )
        apply_precheck_report = self.diff_editor.apply_precheck(
            builder=builder,
            patch_path=rewritten_patch_path,
            task_id=task_id,
            attempt_no=attempt_no,
        )

        trace = TransformationTrace(
            task_id=task_id,
            plan_id=plan.plan_id,
            source_patch_path=source_patch_path,
            rewritten_patch_path=rewritten_patch_path,
            steps=[
                dispatch_step,
                template_step,
                smpl_step,
                diff_step,
                TransformationStep(
                    step_id="apply-001",
                    engine="apply_precheck",
                    action=apply_precheck_report.status,
                    recipe_name=plan.selected_recipe,
                    target_files=plan.target_files,
                    summary=apply_precheck_report.summary,
                ),
            ],
        )

        rewrite_reason_path = rewrite_dir / "rewrite_reason.json"
        transformation_trace_path = rewrite_dir / "transformation_trace.json"
        apply_precheck_path = rewrite_dir / "apply_precheck.json"
        kernel_adapter_plan_path = self._write_kernel_adapter_plan(plan=plan, rewrite_dir=rewrite_dir)
        section_change_report_path = self._write_section_change_report(rewrite_dir=rewrite_dir)

        rewrite_reason_payload = {
            "task_id": task_id,
            "plan_id": plan.plan_id,
            "selected_recipe": plan.selected_recipe,
            "selected_route_family": plan.selected_route_family,
            "selected_execution_mode": plan.selected_execution_mode,
            "selected_primitives": plan.selected_primitives,
            "target_files": plan.target_files,
            "rule_hits": plan.rule_hits,
            "requires_kernel_scaffold": plan.requires_kernel_scaffold,
            "scaffold_notes": plan.scaffold_notes,
            "selection_reason": plan.selection_reason,
            "source_patch_path": to_project_relative(self.project_root, source_patch_path),
            "source_commit": patch_bundle.stable_commit or patch_bundle.upstream_commit,
            "apply_precheck_status": apply_precheck_report.status,
            "kernel_adapter_plan_path": to_project_relative(self.project_root, kernel_adapter_plan_path),
            "section_change_avoidance_path": to_project_relative(self.project_root, section_change_report_path),
            "notes": plan.notes,
        }
        rewrite_reason_path.write_text(
            json.dumps(relativize_payload(rewrite_reason_payload, self.project_root), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        transformation_trace_path.write_text(
            json.dumps(relativize_payload(trace, self.project_root), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        apply_precheck_path.write_text(
            json.dumps(relativize_payload(apply_precheck_report, self.project_root), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return {
            "rewritten_patch": rewritten_patch_path,
            "rewrite_reason": rewrite_reason_path,
            "transformation_trace": transformation_trace_path,
            "apply_precheck": apply_precheck_path,
            "apply_precheck_report": apply_precheck_report,
            "kernel_adapter_plan": kernel_adapter_plan_path,
            "section_change_avoidance": section_change_report_path,
        }

    def _route_dispatch_step(self, plan: RewritePlan) -> TransformationStep:
        """把候选路线转成一条显式执行轨迹"""

        summary = (
            f"当前轮选择 {plan.selected_route_family or 'wrapper'} 路线，"
            f"执行模式为 {plan.selected_execution_mode or 'template_wrap'}"
        )
        if plan.requires_kernel_scaffold and plan.scaffold_notes:
            summary = summary + "，后续还需要内核侧辅助处理: " + "；".join(plan.scaffold_notes)

        return TransformationStep(
            step_id="dispatch-001",
            engine="route_dispatch",
            action=plan.selected_execution_mode or "dispatch",
            recipe_name=plan.selected_recipe,
            primitive=plan.selected_primitives[0] if plan.selected_primitives else None,
            target_files=plan.target_files,
            summary=summary,
        )

    def _write_kernel_adapter_plan(self, *, plan: RewritePlan, rewrite_dir: Path) -> Path | None:
        """对需要内核侧辅助逻辑的路线补一份说明文件"""

        if not plan.requires_kernel_scaffold:
            return None

        path = rewrite_dir / "kernel_adapter_plan.json"
        payload = {
            "plan_id": plan.plan_id,
            "selected_recipe": plan.selected_recipe,
            "selected_route_family": plan.selected_route_family,
            "selected_execution_mode": plan.selected_execution_mode,
            "selected_primitives": plan.selected_primitives,
            "notes": plan.scaffold_notes,
        }
        path.write_text(
            json.dumps(relativize_payload(payload, self.project_root), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return path

    def _write_section_change_report(self, *, rewrite_dir: Path) -> Path | None:
        """写出 section change 收缩策略报告"""

        report = getattr(self.smpl_engine, "last_section_change_report", None)
        if not report:
            return None
        path = rewrite_dir / "section_change_avoidance.json"
        path.write_text(
            json.dumps(relativize_payload(report, self.project_root), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return path
