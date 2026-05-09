from __future__ import annotations

from pathlib import Path

from patchweaver.rewriter.primitive_templates import PrimitiveTemplates


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_primitive_templates_loads_p1_recipe_catalog() -> None:
    catalog = PrimitiveTemplates(PROJECT_ROOT).catalog()
    names = {item.name for item in catalog}

    assert "smpl_primary_rewrite" in names
    assert "section_change_avoidance_rewrite" in names
    assert "callback_livepatch_wrap" in names
    assert "shadow_variable_wrap" in names
    assert "callback_shadow_wrap" in names
    assert all(item.template_path and item.template_path.exists() for item in catalog)
    assert all(item.smpl_path and item.smpl_path.exists() for item in catalog)


def test_primitive_templates_finds_callback_shadow_scaffold_routes() -> None:
    templates = PrimitiveTemplates(PROJECT_ROOT)
    callback_routes = {item.name for item in templates.by_primitive("callback")}
    shadow_routes = {item.name for item in templates.by_primitive("shadow_variable")}

    assert "callback_livepatch_wrap" in callback_routes
    assert "callback_shadow_wrap" in callback_routes
    assert "shadow_variable_wrap" in shadow_routes
    assert "state_preserving_wrap" in shadow_routes
    assert "callback_shadow_wrap" in shadow_routes
    assert "kernel_scaffold=True" in templates.render("callback_shadow_wrap")


def test_primitive_templates_exposes_section_change_avoidance_route() -> None:
    spec = PrimitiveTemplates(PROJECT_ROOT).get("section_change_avoidance_rewrite")

    assert spec is not None
    assert spec.route_family == "section_change_avoidance"
    assert spec.primitives == ("smpl", "section_change_avoidance")
    assert spec.requires_kernel_scaffold is False
