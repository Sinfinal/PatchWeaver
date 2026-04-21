"""策略守卫"""

from __future__ import annotations

from patchweaver.harness.dispatch_policy import dispatch_mode


class PolicyGuard:
    """负责检查当前阶段是否符合执行边界"""

    def ensure_stage_allowed(
        self,
        stage_name: str,
        *,
        require_write: bool = False,
        enable_read_parallel: bool = True,
    ) -> None:
        """检查阶段和调度模式是否匹配"""

        mode = dispatch_mode(stage_name, enable_read_parallel=enable_read_parallel)
        if require_write and mode != "write-exclusive":
            raise ValueError(f"阶段 `{stage_name}` 不允许进入写入型执行路径。")
