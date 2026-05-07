from __future__ import annotations

from pathlib import Path

from patchweaver.builder.config_repair import infer_minimal_config_delta, render_config_fragment


def test_infer_minimal_config_delta_from_directory_and_object_gate(tmp_path: Path) -> None:
    source_dir = tmp_path / "kernel"
    (source_dir / "drivers").mkdir(parents=True)
    (source_dir / "drivers" / "demo").mkdir()
    (source_dir / "drivers" / "Makefile").write_text("obj-$(CONFIG_DEMO_BUS) += demo/\n", encoding="utf-8")
    (source_dir / "drivers" / "demo" / "Makefile").write_text(
        "obj-$(CONFIG_DEMO_DRIVER) += demo.o\n",
        encoding="utf-8",
    )

    result = infer_minimal_config_delta(
        source_dir=source_dir,
        target_files=[Path("drivers/demo/demo.c")],
    )

    assert result["status"] == "repairable"
    assert result["config_delta"] == {
        "CONFIG_DEMO_BUS": "m",
        "CONFIG_DEMO_DRIVER": "m",
    }
    assert render_config_fragment(result["config_delta"]) == "CONFIG_DEMO_BUS=m\nCONFIG_DEMO_DRIVER=m\n"


def test_infer_minimal_config_delta_handles_composite_object(tmp_path: Path) -> None:
    source_dir = tmp_path / "kernel"
    target_dir = source_dir / "drivers" / "demo"
    target_dir.mkdir(parents=True)
    (target_dir / "Makefile").write_text(
        "demo-core-y += main.o helper.o\nobj-$(CONFIG_DEMO_CORE) += demo-core.o\n",
        encoding="utf-8",
    )

    result = infer_minimal_config_delta(
        source_dir=source_dir,
        target_files=[Path("drivers/demo/main.c")],
    )

    assert result["status"] == "repairable"
    assert result["config_delta"] == {"CONFIG_DEMO_CORE": "m"}
