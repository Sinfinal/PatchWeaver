from __future__ import annotations

from pathlib import Path

from patchweaver.config.resolver import load_effective_configs, resolve_runtime
from patchweaver.harness.dispatch_policy import dispatch_mode


def test_profile_overrides_flow_into_verify_prompt_and_skill_configs() -> None:
    repo_root = Path(__file__).resolve().parents[2]

    dev_configs = load_effective_configs(project_root=repo_root, profile_name="dev")
    full_configs = load_effective_configs(project_root=repo_root, profile_name="full")

    dev_verify = dev_configs["verify"]
    full_verify = full_configs["verify"]
    dev_prompts = dev_configs["prompts"]
    full_prompts = full_configs["prompts"]
    dev_skills = dev_configs["skills"]
    full_skills = full_configs["skills"]

    assert dev_verify.enable_semantic_guard is False
    assert dev_verify.enable_regression is False
    assert full_verify.enable_semantic_guard is True
    assert full_verify.enable_regression is True

    assert dev_prompts.prompt_profiles["strict"].suppress_duplicate_evidence is True
    assert dev_prompts.prompt_profiles["strict"].track_token_cost is True
    assert full_prompts.prompt_profiles["strict"].suppress_duplicate_evidence is True
    assert full_prompts.prompt_profiles["strict"].track_token_cost is True

    dev_skill_profile = dev_skills.skill_profiles[dev_skills.default_skill_profile]
    full_skill_profile = full_skills.skill_profiles[full_skills.default_skill_profile]
    assert dev_skill_profile.allow_readonly_subagent is False
    assert dev_skill_profile.subagent_allowed_stages == []
    assert full_skill_profile.allow_readonly_subagent is True
    assert "retrieval" in full_skill_profile.subagent_allowed_stages


def test_profile_controls_read_parallel_dispatch_mode() -> None:
    repo_root = Path(__file__).resolve().parents[2]

    default_runtime = resolve_runtime(project_root=repo_root)
    full_runtime = resolve_runtime(project_root=repo_root, profile_name="full")

    assert default_runtime.enable_read_parallel is False
    assert full_runtime.enable_read_parallel is True
    assert dispatch_mode("retrieval", enable_read_parallel=default_runtime.enable_read_parallel) == "read-serial"
    assert dispatch_mode("retrieval", enable_read_parallel=full_runtime.enable_read_parallel) == "read-parallel"
    assert dispatch_mode("build", enable_read_parallel=full_runtime.enable_read_parallel) == "write-exclusive"
