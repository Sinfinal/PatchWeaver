"""改写执行骨架。"""

from __future__ import annotations

import json
from pathlib import Path

from patchweaver.models.patch import PatchBundle
from patchweaver.models.rewrite import RewritePlan, TransformationStep, TransformationTrace
from patchweaver.rewriter.diff_editor import DiffEditor
from patchweaver.rewriter.smpl_engine import SmPLEngine
from patchweaver.rewriter.template_engine import TemplateEngine


class RewriteExecutor:
    """负责把 RewritePlan 落地为补丁文件。"""

    def __init__(self, project_root: Path) -> None:
        """初始化改写分层执行器。"""

        self.template_engine = TemplateEngine(project_root)
        self.smpl_engine = SmPLEngine(project_root)
        self.diff_editor = DiffEditor()

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
        """输出 rewritten.patch 及其配套元数据。"""

        source_patch_path = patch_bundle.normalized_patch_path or patch_bundle.raw_patch_path
        if source_patch_path is None:
            raise ValueError("PatchBundle 缺少可用的原始 patch 路径。")

        source_patch_text = source_patch_path.read_text(encoding="utf-8")
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

        rewrite_dir.mkdir(parents=True, exist_ok=True)
        rewrite_reason_path = rewrite_dir / "rewrite_reason.json"
        transformation_trace_path = rewrite_dir / "transformation_trace.json"
        apply_precheck_path = rewrite_dir / "apply_precheck.json"

        rewrite_reason_payload = {
            "task_id": task_id,
            "plan_id": plan.plan_id,
            "selected_recipe": plan.selected_recipe,
            "selected_primitives": plan.selected_primitives,
            "target_files": plan.target_files,
            "rule_hits": plan.rule_hits,
            "selection_reason": plan.selection_reason,
            "source_patch_path": str(source_patch_path),
            "source_commit": patch_bundle.stable_commit or patch_bundle.upstream_commit,
            "apply_precheck_status": apply_precheck_report.status,
            "notes": plan.notes,
        }
        rewrite_reason_path.write_text(
            json.dumps(rewrite_reason_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        transformation_trace_path.write_text(trace.model_dump_json(indent=2), encoding="utf-8")
        apply_precheck_path.write_text(apply_precheck_report.model_dump_json(indent=2), encoding="utf-8")
        return {
            "rewritten_patch": rewritten_patch_path,
            "rewrite_reason": rewrite_reason_path,
            "transformation_trace": transformation_trace_path,
            "apply_precheck": apply_precheck_path,
            "apply_precheck_report": apply_precheck_report,
        }
