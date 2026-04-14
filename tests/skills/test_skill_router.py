from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from patchweaver.skills.router import SkillRouter


def _case_dir(case_name: str) -> Path:
    base_dir = Path("E:/Desk/patchweaver_pytest_cases")
    base_dir.mkdir(parents=True, exist_ok=True)
    root = base_dir / f"{case_name}-{uuid4().hex[:8]}"
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_skill_router_uses_project_stage_manifest_and_subagent_policy() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    router = SkillRouter(repo_root)

    retrieval_route = router.route("retrieval")
    validation_route = router.route("validation")
    unknown_route = router.route("unknown_stage")

    assert retrieval_route.selected_skill == "retrieval"
    assert retrieval_route.readonly_subagent_allowed is True
    assert retrieval_route.route_source == "registry"
    assert any(item.startswith("输入:") for item in retrieval_route.contract_summary)

    assert validation_route.selected_skill == "validation"
    assert validation_route.readonly_subagent_allowed is False

    assert unknown_route.selected_skill is None
    assert unknown_route.fallback_used is True
    assert unknown_route.route_source == "fallback"


def test_skill_router_respects_configured_source_priority() -> None:
    project_root = _case_dir("skill-priority") / "skill-priority-project"
    (project_root / "patchweaver").mkdir(parents=True, exist_ok=True)
    (project_root / "config").mkdir(parents=True, exist_ok=True)
    (project_root / "skills" / "project" / "project_reporting").mkdir(parents=True, exist_ok=True)
    (project_root / "skills" / "builtin" / "builtin_reporting").mkdir(parents=True, exist_ok=True)
    (project_root / "pyproject.toml").write_text("[project]\nname='skill-priority-project'\nversion='0.1.0'\n", encoding="utf-8")
    (project_root / "config" / "skills.yaml").write_text(
        "\n".join(
            [
                "skill_source_priority:",
                "  - project",
                "  - builtin",
                "require_manifest: true",
                "enforce_allowlist: true",
                "allowed_skill_tags:",
                "  - contest",
                "  - core",
                "skill_dirs:",
                "  project: skills/project",
                "  builtin: skills/builtin",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (project_root / "skills" / "project" / "project_reporting" / "manifest.yaml").write_text(
        "\n".join(
            [
                "name: project_reporting",
                "version: 0.1.0",
                "enabled: true",
                "visibility: project",
                "priority: 10",
                "readonly: true",
                "allow_readonly_subagent: true",
                "tags:",
                "  - contest",
                "entry:",
                "  kind: workflow_template",
                "  stage: reporting",
                "description: project reporting skill",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (project_root / "skills" / "builtin" / "builtin_reporting" / "manifest.yaml").write_text(
        "\n".join(
            [
                "name: builtin_reporting",
                "version: 0.1.0",
                "enabled: true",
                "visibility: builtin",
                "priority: 10",
                "readonly: true",
                "allow_readonly_subagent: true",
                "tags:",
                "  - contest",
                "entry:",
                "  kind: workflow_template",
                "  stage: reporting",
                "description: builtin reporting skill",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    route = SkillRouter(project_root).route("reporting")

    assert route.selected_skill == "project_reporting"
    assert "builtin_reporting" in route.candidate_skills
