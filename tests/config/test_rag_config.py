from patchweaver.config.loader import discover_project_root, load_rag_config


def test_load_rag_config_defaults() -> None:
    config = load_rag_config(discover_project_root())
    assert config.milvus_collection == "patchweaver_cve_chunks"
    assert config.embedding_model == "text-embedding-v3"
    assert config.embedding_dimensions == 1024
    assert config.rerank_enabled is True
    assert config.rerank_model == "qwen3-rerank"
