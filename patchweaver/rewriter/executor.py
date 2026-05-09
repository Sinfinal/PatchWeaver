"""改写执行骨架"""

from __future__ import annotations

import json
from pathlib import Path

from patchweaver.models.patch import PatchBundle
from patchweaver.models.rewrite import RewritePlan, TransformationStep, TransformationTrace
from patchweaver.models.semantic import RepairIntent
from patchweaver.rewriter.diff_editor import DiffEditor
from patchweaver.rewriter.primitive_templates import PrimitiveTemplates
from patchweaver.rewriter.semantic_guard import SemanticGuardRewriter
from patchweaver.rewriter.smpl_engine import SmPLEngine
from patchweaver.rewriter.template_engine import TemplateEngine
from patchweaver.utils.path_policy import relativize_payload, to_project_relative


class RewriteExecutor:
    """负责把 RewritePlan 落地为补丁文件"""

    def __init__(self, project_root: Path) -> None:
        """初始化改写分层执行器"""

        self.template_engine = TemplateEngine(project_root)
        self.semantic_guard_rewriter = SemanticGuardRewriter()
        self.smpl_engine = SmPLEngine(project_root)
        self.diff_editor = DiffEditor()
        self.project_root = project_root.resolve()
        self.primitive_templates = PrimitiveTemplates(self.project_root)

    def execute(
        self,
        *,
        plan: RewritePlan,
        patch_bundle: PatchBundle,
        rewrite_dir: Path,
        builder: object,
        task_id: str,
        attempt_no: int,
        repair_intent: RepairIntent | None = None,
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
        semantic_guard_patch, semantic_guard_step, semantic_guard_report = self._apply_semantic_guard(
            plan=plan,
            patch_text=template_patch,
            repair_intent=repair_intent,
        )
        smpl_patch, smpl_step = self.smpl_engine.apply(plan=plan, patch_text=semantic_guard_patch)
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
                semantic_guard_step,
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
        semantic_guard_rewrite_path = self._write_semantic_guard_report(
            rewrite_dir=rewrite_dir,
            report=semantic_guard_report,
        )
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
            "semantic_guard_rewrite_path": to_project_relative(self.project_root, semantic_guard_rewrite_path),
            "section_change_avoidance_path": to_project_relative(self.project_root, section_change_report_path),
            "repair_intent": repair_intent.model_dump(mode="json") if repair_intent is not None else None,
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
            "semantic_guard_rewrite": semantic_guard_rewrite_path,
            "section_change_avoidance": section_change_report_path,
        }

    def _apply_semantic_guard(
        self,
        *,
        plan: RewritePlan,
        patch_text: str,
        repair_intent: RepairIntent | None,
    ) -> tuple[str, TransformationStep, dict[str, object]]:
        """按计划执行 semantic guard 改写"""

        enabled = (
            plan.selected_recipe == "semantic_guard_rewrite"
            or plan.selected_route_family == "semantic_guard"
            or "semantic_guard" in plan.selected_primitives
        )
        if not enabled:
            report = {
                "strategy": "semantic_guard_rewrite",
                "status": "skipped",
                "effective": False,
                "summary": "当前 recipe 未选择 semantic guard 路线",
            }
            return patch_text, self._semantic_guard_step(plan=plan, report=report), report

        rewritten, report = self.semantic_guard_rewriter.rewrite(
            patch_text=patch_text,
            repair_intent=repair_intent,
            force=enabled,
        )
        return rewritten, self._semantic_guard_step(plan=plan, report=report), report

    def _semantic_guard_step(self, *, plan: RewritePlan, report: dict[str, object]) -> TransformationStep:
        """把 semantic guard 执行结果写成 trace step"""

        return TransformationStep(
            step_id="semantic-guard-001",
            engine="semantic_guard",
            action=str(report.get("status") or "skipped"),
            recipe_name=plan.selected_recipe,
            primitive="semantic_guard",
            target_files=plan.target_files,
            summary=str(report.get("summary") or "semantic guard 未执行"),
        )

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

        scaffold_files = self._write_kernel_scaffold_files(plan=plan, rewrite_dir=rewrite_dir)
        template_spec = self.primitive_templates.get(plan.selected_recipe or "")
        path = rewrite_dir / "kernel_adapter_plan.json"
        payload = {
            "plan_id": plan.plan_id,
            "selected_recipe": plan.selected_recipe,
            "selected_route_family": plan.selected_route_family,
            "selected_execution_mode": plan.selected_execution_mode,
            "selected_primitives": plan.selected_primitives,
            "template_spec": {
                "template_path": to_project_relative(self.project_root, template_spec.template_path)
                if template_spec and template_spec.template_path
                else None,
                "smpl_path": to_project_relative(self.project_root, template_spec.smpl_path)
                if template_spec and template_spec.smpl_path
                else None,
                "requires_kernel_scaffold": template_spec.requires_kernel_scaffold if template_spec else True,
            },
            "scaffold_files": [to_project_relative(self.project_root, item) for item in scaffold_files],
            "scaffold_contract": self._kernel_scaffold_contract(plan),
            "notes": plan.scaffold_notes,
        }
        path.write_text(
            json.dumps(relativize_payload(payload, self.project_root), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return path

    def _write_kernel_scaffold_files(self, *, plan: RewritePlan, rewrite_dir: Path) -> list[Path]:
        """为 callback/shadow 路线写出第一版辅助模板"""

        primitives = set(plan.selected_primitives)
        if not primitives.intersection({"callback", "shadow_variable", "state_preserving"}):
            return []

        scaffold_path = rewrite_dir / "kernel_adapter_scaffold.c"
        blocks: list[str] = [
            "/* PatchWeaver kernel adapter scaffold */",
            f"/* recipe: {plan.selected_recipe or 'unknown'} */",
            f"/* route: {plan.selected_route_family or 'unknown'} */",
            "",
            "#include <linux/livepatch.h>",
            "#include <linux/slab.h>",
            "",
        ]
        if "shadow_variable" in primitives:
            blocks.extend(
                [
                    "struct patchweaver_shadow_state {",
                    "\tvoid *object;",
                    "\tunsigned long flags;",
                    "};",
                    "",
                    "static int patchweaver_shadow_init(void *obj, struct patchweaver_shadow_state **state)",
                    "{",
                    "\t*state = kzalloc(sizeof(**state), GFP_KERNEL);",
                    "\tif (!*state)",
                    "\t\treturn -ENOMEM;",
                    "\t(*state)->object = obj;",
                    "\treturn 0;",
                    "}",
                    "",
                    "static void patchweaver_shadow_free(struct patchweaver_shadow_state *state)",
                    "{",
                    "\tkfree(state);",
                    "}",
                    "",
                ]
            )
        if "callback" in primitives:
            blocks.extend(
                [
                    "static int patchweaver_pre_patch_callback(struct klp_object *obj)",
                    "{",
                    "\treturn 0;",
                    "}",
                    "",
                    "static void patchweaver_post_unpatch_callback(struct klp_object *obj)",
                    "{",
                    "}",
                    "",
                ]
            )
        if "state_preserving" in primitives:
            blocks.extend(
                [
                    "static int patchweaver_state_preserve(void *old_obj, void *new_obj)",
                    "{",
                    "\treturn old_obj || new_obj ? 0 : -EINVAL;",
                    "}",
                    "",
                ]
            )
        blocks.extend(
            [
                "/* This scaffold is an execution contract, not a standalone module */",
                "/* The final adapter must bind these hooks to the selected livepatch object */",
                "",
            ]
        )
        scaffold_path.write_text("\n".join(blocks), encoding="utf-8")
        return [scaffold_path]

    def _kernel_scaffold_contract(self, plan: RewritePlan) -> dict[str, object]:
        """整理 callback/shadow 辅助模板的落地契约"""

        primitives = set(plan.selected_primitives)
        return {
            "requires_callback_hooks": "callback" in primitives,
            "requires_shadow_state": "shadow_variable" in primitives,
            "requires_state_preservation": "state_preserving" in primitives,
            "target_files": plan.target_files,
            "review_points": [
                "确认 callback 绑定到正确 klp_object",
                "确认 shadow state 生命周期覆盖 load 和 unload",
                "确认辅助状态不改变原补丁安全语义",
            ],
        }

    def _write_semantic_guard_report(self, *, rewrite_dir: Path, report: dict[str, object]) -> Path | None:
        """写出 semantic guard 改写报告"""

        if not report or report.get("status") == "skipped":
            return None
        path = rewrite_dir / "semantic_guard_rewrite.json"
        path.write_text(
            json.dumps(relativize_payload(report, self.project_root), ensure_ascii=False, indent=2) + "\n",
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
