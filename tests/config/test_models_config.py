from __future__ import annotations

from pathlib import Path

from patchweaver.config.loader import load_models_config


def test_load_models_config_from_project_root(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    (project_root / "patchweaver").mkdir(parents=True, exist_ok=True)
    (project_root / "config").mkdir(parents=True, exist_ok=True)
    (project_root / "pyproject.toml").write_text("[project]\nname='patchweaver'\n", encoding="utf-8")
    (project_root / "config" / "models.yaml").write_text(
        "\n".join(
            [
                "provider: bailian",
                "endpoint_mode: openai_compatible",
                "base_url: https://dashscope.aliyuncs.com/compatible-mode/v1",
                "api_key_env: PATCHWEAVER_BAILIAN_API_KEY",
                "topology: single_primary_with_optional_helpers",
                "default_model: qwen-plus-2025-07-28",
                "development_model: qwen-plus-2025-07-28",
                "delivery_model: qwen-plus-2025-07-28",
                "fallback_model: qwen-plus-2025-07-28",
                "helper_models:",
                "  code_assistant: qwen-coder-turbo-0919",
                "  vision: qwen-vl-plus-2025-05-07",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    config = load_models_config(project_root)

    assert config.provider == "bailian"
    assert config.topology == "single_primary_with_optional_helpers"
    assert config.default_model == "qwen-plus-2025-07-28"
    assert config.helper_models["code_assistant"] == "qwen-coder-turbo-0919"
    assert config.vision_model == "qwen-vl-plus-2025-05-07"
