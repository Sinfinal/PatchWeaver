from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_readme_covers_slice8_delivery_surface() -> None:
    readme = _read("README.md")

    required_phrases = [
        "PatchWeaver 的正式定位是一个有状态、会决策、能调用工具、可回放的内核 CVE 热补丁生成 Agent",
        "python -m patchweaver serve-api",
        "scripts/package_bailian_gateway.py",
        "scripts/generate_demo_report.py",
        "scripts/generate_representative_metrics_report.py",
        "scripts/release_redaction_check.py",
        "Demo 口径固定为三类样例",
        "专业名词速查",
        "AI 使用与人工复核",
        "封版检查清单",
    ]
    for phrase in required_phrases:
        assert phrase in readme


def test_delivery_demo_doc_has_success_failure_retry_and_bailian_boundaries() -> None:
    doc = _read("docs/PatchWeaver-封版Demo与交付口径_v0510.md")

    required_phrases = [
        "成功样例",
        "失败归因样例",
        "Agent 重试样例",
        "`dry_run=true` 不能证明真实 `kpatch-build`",
        "模型交互记录应通过 `config/models.yaml`",
        "脱敏检查通过",
    ]
    for phrase in required_phrases:
        assert phrase in doc


def test_legacy_design_doc_no_longer_recommends_plaintext_model_key() -> None:
    design = _read("docs/PatchWeaver-总方案与创新设计总文档.md")

    forbidden_phrases = [
        "环境变量未命中时，再回退到 `config/models.yaml` 中的 `api_key`",
        "本地开发联调时允许在 `config/models.yaml` 中写入临时 `api_key`",
        "把明文 Key 写入 `config/models.yaml`",
    ]
    for phrase in forbidden_phrases:
        assert phrase not in design
    assert "封版与交付口径统一为“环境变量或平台 Secret 注入”" in design
