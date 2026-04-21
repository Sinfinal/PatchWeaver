"""尝试轮状态机"""

from __future__ import annotations

from typing import Any

from patchweaver.models.attempt import AttemptState


class AttemptEngine:
    """维护单任务的唯一主状态"""

    def create_initial_state(self, *, task_id: str, max_attempts: int) -> AttemptState:
        """生成首轮默认状态"""

        return AttemptState(
            task_id=task_id,
            attempt_no=0,
            stage="created",
            remaining_budget={"retries": max_attempts},
            disabled_strategies=[],
        )

    def advance(self, state: AttemptState, *, stage: str, remaining_budget: dict[str, Any] | None = None) -> AttemptState:
        """推进到下一个阶段"""

        return state.model_copy(
            update={
                "stage": stage,
                "remaining_budget": remaining_budget or state.remaining_budget,
            }
        )

    def terminate(self, state: AttemptState, *, reason: str) -> AttemptState:
        """结束当前状态"""

        return state.model_copy(update={"termination_reason": reason})

