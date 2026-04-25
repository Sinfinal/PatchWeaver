from patchweaver.api.app import create_app


def test_rag_search_route_is_exposed() -> None:
    schema = create_app().openapi()
    assert "/api/v1/rag/search" in schema["paths"]
