import pytest

from app.catalog.embeddings import (
    EMBEDDING_DIMENSION,
    EXPECTED_EMBEDDING_MODEL,
    ensure_embedding_dimensions,
    require_supported_embedding_model,
)
from app.catalog.search import build_text_search_query


def test_require_supported_embedding_model_accepts_decided_model() -> None:
    assert require_supported_embedding_model(EXPECTED_EMBEDDING_MODEL) == EXPECTED_EMBEDDING_MODEL


@pytest.mark.parametrize("model", [None, "", "text-embedding-004", "otro-modelo"])
def test_require_supported_embedding_model_rejects_other_models(model) -> None:
    with pytest.raises(ValueError, match="gemini-embedding-2"):
        require_supported_embedding_model(model)


def test_ensure_embedding_dimensions_rejects_wrong_dimension() -> None:
    with pytest.raises(ValueError, match=str(EMBEDDING_DIMENSION)):
        ensure_embedding_dimensions("aaaa-0001", [0.1, 0.2])


def test_build_text_search_query_expands_escolar_terms() -> None:
    text_query = build_text_search_query("deserción escolar")

    assert "desercion:*" in text_query
    assert "escolar:*" in text_query
    assert "educacion:*" in text_query
