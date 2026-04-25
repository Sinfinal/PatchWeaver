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
        )
    )

    targets = orchestrator._infer_build_targets(source_dir=source_dir, rewritten_patch_path=patch_path)

    assert targets == ["net/netfilter/nf_tables.ko"]
