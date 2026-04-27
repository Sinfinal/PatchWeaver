"""固定样例分层与正向样例池判定"""

from __future__ import annotations

from typing import Any

LOW_RISK_ROUTES = {"direct_apply_patch", "minimal_livepatch_wrap"}
STABLE_BUCKETS = {
    "already_patched",
    "feature_not_enabled",
    "kpatch_constraint",
    "buildable_and_should_pass",
}


def classify_sample_pool_result(result: dict[str, Any]) -> dict[str, Any]:
    """根据分析结果或全链结果判断样例定位"""

    selected_route = str(result.get("selected_route") or result.get("preferred_route") or "").strip()
    high_risk_count = int(result.get("high_risk_count") or 0)
    run_status = str(result.get("run_status") or result.get("status") or "").strip()
    build_status = str(result.get("build_status") or "").strip()
    validation_status = str(result.get("validation_status") or "").strip()
    failure_type = str(result.get("failure_type") or result.get("latest_failure_type") or "").strip()
    low_risk_route = selected_route in LOW_RISK_ROUTES and high_risk_count == 0

    if build_status == "built" and validation_status == "passed":
        return _classification(
            sample_bucket="buildable_and_should_pass",
            acceptance_role="positive_acceptance_sample",
            screening_tier="positive_acceptance_confirmed",
            reason="已产出 .ko，且加载、卸载、smoke、自检均通过",
        )

    if failure_type == "target_already_patched":
        if low_risk_route:
            return _classification(
                sample_bucket="already_patched",
                acceptance_role="screening_candidate",
                screening_tier="positive_candidate_blocked_by_target_state",
                reason="路线低风险，但当前验证机源码树已包含修复，无法用于正向 .ko 成功率统计",
            )
        return _classification(
            sample_bucket="already_patched",
            acceptance_role="development_sample",
            screening_tier="development_only_target_state",
            reason="当前验证机源码树已包含修复，适合做目标态识别回归，不适合做正向验收",
        )

    if failure_type == "feature_not_enabled":
        return _classification(
            sample_bucket="feature_not_enabled",
            acceptance_role="development_sample",
            screening_tier="development_only_feature_gate",
            reason="补丁命中的源码在当前验证机内核配置中未启用，适合做配置门控识别回归",
        )

    if failure_type == "kpatch_constraint":
        return _classification(
            sample_bucket="kpatch_constraint",
            acceptance_role="blocked_sample",
            screening_tier="blocked_by_kpatch_constraint",
            reason="已进入真实构建，但被 kpatch 后端约束拦截，适合做约束解释回归",
        )

    if failure_type == "patch_apply_failed":
        return _classification(
            sample_bucket=None,
            acceptance_role="development_sample",
            screening_tier="development_only_apply_precheck",
            reason="当前源码树无法通过 apply 预检查，先不纳入稳定四桶样例集",
        )

    if failure_type == "compile_failed":
        return _classification(
            sample_bucket=None,
            acceptance_role="blocked_sample",
            screening_tier="blocked_by_compile_failure",
            reason="已进入构建但未形成稳定失败口径，先不纳入稳定四桶样例集",
        )

    if low_risk_route:
        return _classification(
            sample_bucket="buildable_and_should_pass",
            acceptance_role="screening_candidate",
            screening_tier="positive_candidate_low_risk",
            reason="当前分析结果显示为低风险路线，值得继续推进到真实构建筛选",
        )

    if run_status in {"failed", "target_state"} or failure_type:
        return _classification(
            sample_bucket=None,
            acceptance_role="development_sample",
            screening_tier="development_only_unstable_bucket",
            reason="当前结果无法稳定收口到四桶验收口径，继续作为开发样例观察",
        )

    return _classification(
        sample_bucket=None,
        acceptance_role="development_sample",
        screening_tier="development_only_high_risk",
        reason="分析结果显示改写风险偏高，暂不作为正向验收样例",
    )


def _classification(
    *,
    sample_bucket: str | None,
    acceptance_role: str,
    screening_tier: str,
    reason: str,
) -> dict[str, Any]:
    """整理统一输出结构"""

    return {
        "sample_bucket": sample_bucket,
        "acceptance_role": acceptance_role,
        "screening_tier": screening_tier,
        "reason": reason,
        "stable_bucket_ready": sample_bucket in STABLE_BUCKETS,
        "positive_pool_candidate": screening_tier
        in {
            "positive_acceptance_confirmed",
            "positive_candidate_low_risk",
            "positive_candidate_blocked_by_target_state",
        },
    }
