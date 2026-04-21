from __future__ import annotations

from pathlib import Path

from patchweaver.config.loader import load_models_config, save_models_api_settings
from patchweaver.config.models import ModelsConfig


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


def test_models_config_prefers_environment_api_key(monkeypatch) -> None:
    config = ModelsConfig(api_key_env="PATCHWEAVER_BAILIAN_API_KEY", api_key="config-key")

    monkeypatch.setenv("PATCHWEAVER_BAILIAN_API_KEY", "env-key")

    assert config.resolve_api_key() == "env-key"
    assert config.resolve_api_key_source() == "env"
    assert config.api_key_status()["api_key_ready"] is True


def test_models_config_falls_back_to_config_api_key(monkeypatch) -> None:
    monkeypatch.delenv("PATCHWEAVER_BAILIAN_API_KEY", raising=False)
    config = ModelsConfig(api_key_env="PATCHWEAVER_BAILIAN_API_KEY", api_key="config-key")

    assert config.resolve_api_key() == "config-key"
    assert config.resolve_api_key_source() == "config"
    assert config.api_key_status()["api_key_in_config"] is True


def test_save_models_api_settings_updates_api_key_fields(tmp_path: Path) -> None:
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
                "api_key: \"\"",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    save_models_api_settings(
        project_root,
        api_key_env="PATCHWEAVER_BAILIAN_API_KEY_ALT",
        api_key="demo-key",
    )

    saved_text = (project_root / "config" / "models.yaml").read_text(encoding="utf-8")
    assert 'api_key_env: "PATCHWEAVER_BAILIAN_API_KEY_ALT"' in saved_text
    assert 'api_key: "demo-key"' in saved_text
