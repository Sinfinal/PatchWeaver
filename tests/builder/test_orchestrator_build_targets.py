from __future__ import annotations

from pathlib import Path

from patchweaver.builder.orchestrator import BuildOrchestrator
from patchweaver.config.models import BuildConfig


def _write_kernel_tree(root: Path, *, with_vmlinux_cache: bool) -> None:
    (root / "net" / "netfilter").mkdir(parents=True, exist_ok=True)
    (root / "Makefile").write_text("all:\n\t@echo ok\n", encoding="utf-8")
    (root / ".config").write_text("CONFIG_NF_TABLES=m\n", encoding="utf-8")
    (root / "Module.symvers").write_text("fake symvers\n", encoding="utf-8")
    (root / "vmlinux").write_text("fake vmlinux\n", encoding="utf-8")
    if with_vmlinux_cache:
        (root / "vmlinux.o").write_text("fake vmlinux.o\n", encoding="utf-8")
    (root / "net" / "netfilter" / "Makefile").write_text(
        "\n".join(
            [
                "nf_tables-objs := nf_tables_core.o nf_tables_api.o nft_chain_filter.o",
                "obj-$(CONFIG_NF_TABLES) += nf_tables.o",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_patch(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "diff --git a/net/netfilter/nf_tables_api.c b/net/netfilter/nf_tables_api.c",
                "--- a/net/netfilter/nf_tables_api.c",
                "+++ b/net/netfilter/nf_tables_api.c",
                "@@ -1 +1 @@",
                "-old_line();",
                "+new_line();",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_disabled_tomoyo_tree(root: Path) -> None:
    (root / "security" / "tomoyo").mkdir(parents=True, exist_ok=True)
    (root / "Makefile").write_text("all:\n\t@echo ok\n", encoding="utf-8")
    (root / ".config").write_text("# CONFIG_SECURITY_TOMOYO is not set\n", encoding="utf-8")
    (root / "Module.symvers").write_text("fake symvers\n", encoding="utf-8")
    (root / "vmlinux").write_text("fake vmlinux\n", encoding="utf-8")
    (root / "security" / "Makefile").write_text(
        "\n".join(
            [
                "obj-$(CONFIG_SECURITY_TOMOYO) += tomoyo/",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (root / "security" / "tomoyo" / "Makefile").write_text(
        "\n".join(
            [
                "obj-y := common.o gc.o",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_disabled_tomoyo_patch(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "diff --git a/security/tomoyo/common.c b/security/tomoyo/common.c",
                "--- a/security/tomoyo/common.c",
                "+++ b/security/tomoyo/common.c",
                "@@ -1 +1 @@",
                "-old_line();",
                "+new_line();",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_disabled_sii902x_tree(root: Path) -> None:
    (root / "drivers" / "gpu" / "drm" / "bridge").mkdir(parents=True, exist_ok=True)
    (root / "Makefile").write_text("all:\n\t@echo ok\n", encoding="utf-8")
    (root / ".config").write_text("# CONFIG_DRM_SII902X is not set\n", encoding="utf-8")
    (root / "Module.symvers").write_text("fake symvers\n", encoding="utf-8")
    (root / "vmlinux").write_text("fake vmlinux\n", encoding="utf-8")
    (root / "drivers" / "Makefile").write_text("obj-y += gpu/\n", encoding="utf-8")
    (root / "drivers" / "gpu" / "Makefile").write_text("obj-y += drm/\n", encoding="utf-8")
    (root / "drivers" / "gpu" / "drm" / "Makefile").write_text("obj-y += bridge/\n", encoding="utf-8")
    (root / "drivers" / "gpu" / "drm" / "bridge" / "Makefile").write_text(
        "\n".join(
            [
                "obj-y += panel.o",
                "obj-$(CONFIG_DRM_SII902X) += sii902x.o",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_obj_y_false_composite_tree(root: Path) -> None:
    (root / "drivers" / "gpu" / "drm" / "bridge").mkdir(parents=True, exist_ok=True)
    (root / "Makefile").write_text("all:\n\t@echo ok\n", encoding="utf-8")
    (root / ".config").write_text("CONFIG_DRM_PANEL=y\n", encoding="utf-8")
    (root / "Module.symvers").write_text("fake symvers\n", encoding="utf-8")
    (root / "vmlinux").write_text("fake vmlinux\n", encoding="utf-8")
    (root / "drivers" / "gpu" / "drm" / "bridge" / "Makefile").write_text(
        "\n".join(
            [
                "obj-y += panel.o",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_disabled_sii902x_patch(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "diff --git a/drivers/gpu/drm/bridge/sii902x.c b/drivers/gpu/drm/bridge/sii902x.c",
                "--- a/drivers/gpu/drm/bridge/sii902x.c",
                "+++ b/drivers/gpu/drm/bridge/sii902x.c",
                "@@ -1 +1 @@",
                "-old_line();",
                "+new_line();",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_infer_build_targets_adds_vmlinux_for_module_patch_without_cache(tmp_path: Path) -> None:
    source_dir = tmp_path / "kernel"
    patch_path = tmp_path / "rewritten.patch"
    _write_kernel_tree(source_dir, with_vmlinux_cache=False)
    _write_patch(patch_path)

    orchestrator = BuildOrchestrator(
        BuildConfig(
            kernel_src_dir=str(source_dir),
            kernel_devel_dir=str(source_dir),
            vmlinux_path=str(source_dir / "vmlinux"),
            auto_build_targets=True,
            auto_expand_module_dependencies=False,
        )
    )

    targets = orchestrator._infer_build_targets(source_dir=source_dir, rewritten_patch_path=patch_path)

    assert targets == ["vmlinux", "net/netfilter/nf_tables.ko"]


def test_infer_build_targets_uses_module_only_after_vmlinux_cache_is_ready(tmp_path: Path) -> None:
    source_dir = tmp_path / "kernel"
    patch_path = tmp_path / "rewritten.patch"
    _write_kernel_tree(source_dir, with_vmlinux_cache=True)
    _write_patch(patch_path)

    orchestrator = BuildOrchestrator(
        BuildConfig(
            kernel_src_dir=str(source_dir),
            kernel_devel_dir=str(source_dir),
            vmlinux_path=str(source_dir / "vmlinux"),
            auto_build_targets=True,
            auto_expand_module_dependencies=False,
        )
    )

    targets = orchestrator._infer_build_targets(source_dir=source_dir, rewritten_patch_path=patch_path)

    assert targets == ["net/netfilter/nf_tables.ko"]


def test_infer_build_targets_expands_module_dependencies_after_vmlinux_cache_is_ready(tmp_path: Path, monkeypatch) -> None:
    source_dir = tmp_path / "kernel"
    patch_path = tmp_path / "rewritten.patch"
    _write_kernel_tree(source_dir, with_vmlinux_cache=True)
    _write_patch(patch_path)

    orchestrator = BuildOrchestrator(
        BuildConfig(
            kernel_src_dir=str(source_dir),
            kernel_devel_dir=str(source_dir),
            vmlinux_path="/usr/lib/debug/lib/modules/6.6.102-5.2.an23.x86_64/vmlinux",
            auto_build_targets=True,
            auto_expand_module_dependencies=True,
        )
    )

    def fake_module_dependency_targets(module_target: str) -> list[str]:
        if module_target == "net/netfilter/nf_tables.ko":
            return ["net/netfilter/nfnetlink.ko", "lib/test-helper.ko"]
        return []

    monkeypatch.setattr(orchestrator, "_module_dependency_targets", fake_module_dependency_targets)

    targets = orchestrator._infer_build_targets(source_dir=source_dir, rewritten_patch_path=patch_path)

    assert targets == ["net/netfilter/nfnetlink.ko", "lib/test-helper.ko", "net/netfilter/nf_tables.ko"]


def test_collect_disabled_patch_target_files_reports_config_gated_sources(tmp_path: Path) -> None:
    source_dir = tmp_path / "kernel"
    patch_path = tmp_path / "rewritten.patch"
    _write_disabled_tomoyo_tree(source_dir)
    _write_disabled_tomoyo_patch(patch_path)

    orchestrator = BuildOrchestrator(
        BuildConfig(
            kernel_src_dir=str(source_dir),
            kernel_devel_dir=str(source_dir),
            vmlinux_path=str(source_dir / "vmlinux"),
            auto_build_targets=True,
        )
    )

    disabled_files = orchestrator._collect_disabled_patch_target_files(
        source_dir=source_dir,
        rewritten_patch_path=patch_path,
    )

    assert disabled_files == ["security/tomoyo/common.c"]


def test_collect_disabled_patch_target_files_ignores_obj_y_aggregate_false_positive(tmp_path: Path) -> None:
    source_dir = tmp_path / "kernel"
    patch_path = tmp_path / "rewritten.patch"
    _write_disabled_sii902x_tree(source_dir)
    _write_disabled_sii902x_patch(patch_path)

    orchestrator = BuildOrchestrator(
        BuildConfig(
            kernel_src_dir=str(source_dir),
            kernel_devel_dir=str(source_dir),
            vmlinux_path=str(source_dir / "vmlinux"),
            auto_build_targets=True,
        )
    )

    disabled_files = orchestrator._collect_disabled_patch_target_files(
        source_dir=source_dir,
        rewritten_patch_path=patch_path,
    )

    assert disabled_files == ["drivers/gpu/drm/bridge/sii902x.c"]


def test_resolve_build_target_detail_does_not_turn_obj_y_into_fake_obj_o(tmp_path: Path) -> None:
    source_dir = tmp_path / "kernel"
    _write_obj_y_false_composite_tree(source_dir)

    orchestrator = BuildOrchestrator(
        BuildConfig(
            kernel_src_dir=str(source_dir),
            kernel_devel_dir=str(source_dir),
            vmlinux_path=str(source_dir / "vmlinux"),
            auto_build_targets=True,
        )
    )

    makefile_lines = orchestrator._load_kbuild_lines(source_dir / "drivers" / "gpu" / "drm" / "bridge")
    composite_object = orchestrator._find_composite_object(makefile_lines, member_object="panel.o")

    assert composite_object is None
