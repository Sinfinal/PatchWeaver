"""改写执行骨架。"""

from __future__ import annotations

from pathlib import Path

from patchweaver.models.rewrite import RewritePlan


class RewriteExecutor:
    """负责把 RewritePlan 落地为补丁文件。"""

    def render_placeholder_patch(self, plan: RewritePlan, target_path: Path) -> Path:
        """输出占位 rewritten.patch。"""

        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(f"# rewrite plan: {plan.plan_id}\n", encoding="utf-8")
        return target_path

    def write_rewrite_metadata(self, plan: RewritePlan, rewrite_dir: Path) -> dict[str, Path]:
        """写入改写说明和变换轨迹。"""

        rewrite_dir.mkdir(parents=True, exist_ok=True)
        rewrite_reason_path = rewrite_dir / "rewrite_reason.json"
        transformation_trace_path = rewrite_dir / "transformation_trace.json"
        rewrite_reason_path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
        transformation_trace_path.write_text(
            '{"stage":"rewrite","note":"MVP 阶段仅写入占位改写轨迹。"}\n',
            encoding="utf-8",
        )
        return {
            "rewrite_reason": rewrite_reason_path,
            "transformation_trace": transformation_trace_path,
        }
