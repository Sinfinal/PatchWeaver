from __future__ import annotations

from patchweaver.harness.sample_pool import classify_sample_pool_result


def test_classify_confirmed_positive_acceptance() -> None:
    result = classify_sample_pool_result(
        {
            "selected_route": "minimal_livepatch_wrap",
            "high_risk_count": 0,
            "build_status": "built",
            "validation_status": "passed",
        }
    )

    assert result["sample_bucket"] == "buildable_and_should_pass"
    assert result["acceptance_role"] == "positive_acceptance_sample"
    assert result["screening_tier"] == "positive_acceptance_confirmed"
    assert result["positive_pool_candidate"] is True


def test_classify_low_risk_analyze_candidate() -> None:
    result = classify_sample_pool_result(
        {
            "selected_route": "direct_apply_patch",
            "high_risk_count": 0,
        }
    )

    assert result["sample_bucket"] == "buildable_and_should_pass"
    assert result["acceptance_role"] == "screening_candidate"
    assert result["screening_tier"] == "positive_candidate_low_risk"


def test_classify_target_already_patched_low_risk_case() -> None:
    result = classify_sample_pool_result(
        {
            "selected_route": "direct_apply_patch",
            "high_risk_count": 0,
            "failure_type": "target_already_patched",
        }
    )

    assert result["sample_bucket"] == "already_patched"
    assert result["screening_tier"] == "positive_candidate_blocked_by_target_state"
    assert result["stable_bucket_ready"] is True
    assert result["positive_pool_candidate"] is False


def test_classify_feature_not_enabled_case() -> None:
    result = classify_sample_pool_result(
        {
            "selected_route": "minimal_livepatch_wrap",
            "high_risk_count": 0,
            "failure_type": "feature_not_enabled",
        }
    )

    assert result["sample_bucket"] == "feature_not_enabled"
    assert result["acceptance_role"] == "development_sample"
    assert result["screening_tier"] == "development_only_feature_gate"


def test_classify_patch_apply_failed_case_is_not_stable_bucket() -> None:
    result = classify_sample_pool_result(
        {
            "selected_route": "direct_apply_patch",
            "high_risk_count": 0,
            "failure_type": "patch_apply_failed",
        }
    )

    assert result["sample_bucket"] is None
    assert result["stable_bucket_ready"] is False
    assert result["screening_tier"] == "development_only_apply_precheck"


def test_classify_build_cache_incomplete_as_environment_issue() -> None:
    result = classify_sample_pool_result(
        {
            "selected_route": "minimal_livepatch_wrap",
            "high_risk_count": 0,
            "failure_type": "build_cache_incomplete",
        }
    )

    assert result["sample_bucket"] is None
    assert result["acceptance_role"] == "environment_sample"
    assert result["screening_tier"] == "environment_build_cache_incomplete"
    assert result["stable_bucket_ready"] is False


def test_classify_target_arch_mismatch_as_profile_gate() -> None:
    result = classify_sample_pool_result(
        {
            "selected_route": "direct_apply_patch",
            "high_risk_count": 0,
            "failure_type": "target_arch_mismatch",
        }
    )

    assert result["sample_bucket"] == "feature_not_enabled"
    assert result["acceptance_role"] == "development_sample"
    assert result["screening_tier"] == "development_only_arch_gate"
    assert result["stable_bucket_ready"] is True


def test_classify_run_timeout_not_as_positive_candidate() -> None:
    result = classify_sample_pool_result(
        {
            "selected_route": "direct_apply_patch",
            "high_risk_count": 0,
            "run_status": "timeout",
            "run_failure_type": "run_timeout",
        }
    )

    assert result["sample_bucket"] is None
    assert result["acceptance_role"] == "blocked_sample"
    assert result["screening_tier"] == "blocked_by_run_timeout"
    assert result["positive_pool_candidate"] is False
