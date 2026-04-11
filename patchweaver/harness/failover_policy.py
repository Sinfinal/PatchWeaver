"""Failover 策略。"""

from __future__ import annotations

from patchweaver.models.failover import FailoverRecord


def build_failover_record(
    *,
    stage_name: str,
    trigger_reason: str,
    from_profile: str,
    to_profile: str,
    field_changes: dict[str, object],
    result: str,
) -> FailoverRecord:
    """生成一条窄状态 failover 记录。"""

    return FailoverRecord(
        stage_name=stage_name,
        trigger_reason=trigger_reason,
        from_profile=from_profile,
        to_profile=to_profile,
        field_changes=field_changes,
        result=result,
    )

