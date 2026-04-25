from patchweaver.api.app import create_app


def test_rag_routes_are_exposed() -> None:
    schema = create_app().openapi()
    assert "/api/v1/rag/search" in schema["paths"]
    assert "/api/v1/rag/health" in schema["paths"]
    assert "/api/v1/rag/stats" in schema["paths"]
    assert "/api/v1/rag/import-status" in schema["paths"]
    assert "/api/v1/rag/reindex" in schema["paths"]
