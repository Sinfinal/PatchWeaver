"""Failover 控制器。"""

from __future__ import annotations

from patchweaver.harness.failover_policy import build_failover_record
from patchweaver.models.failover import FailoverRecord


class FailoverController:
    """负责构造窄状态回退记录。"""

    def trigger(
        self,
        *,
        stage_name: str,
        trigger_reason: str,
        from_profile: str,
        to_profile: str,
        field_changes: dict[str, object],
    ) -> FailoverRecord:
        """生成一条 failover 记录。"""

        return build_failover_record(
            stage_name=stage_name,
            trigger_reason=trigger_reason,
            from_profile=from_profile,
            to_profile=to_profile,
            field_changes=field_changes,
            result="recorded",
        )

