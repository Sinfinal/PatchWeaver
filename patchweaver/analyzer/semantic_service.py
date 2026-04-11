"""语义卡片骨架。"""

from __future__ import annotations

from patchweaver.models.semantic import SemanticCard
from patchweaver.models.patch import PatchBundle
from patchweaver.models.task import TaskContext


class SemanticAnalyzer:
    """负责生成语义卡片。"""

    def analyze(self, task: TaskContext, patch_bundle: PatchBundle) -> SemanticCard:
        """根据任务与补丁输入返回占位语义卡片。"""

        return SemanticCard(
            bug_class="cve_fix",
            root_cause=f"{task.cve_id} 的修复意图待补充",
            touched_functions=patch_bundle.affected_files,
        )
