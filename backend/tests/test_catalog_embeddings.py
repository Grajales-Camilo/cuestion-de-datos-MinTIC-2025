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


def test_build_text_search_query_returns_plain_terms_when_no_synonym_matches() -> None:
    """El boost lexical es un parche acotado (ver comentario de SYNONYMS_ES en
    search.py): una consulta sin sinonimos conocidos no debe romperse ni
    inventar terminos, solo usa las palabras literales de la consulta."""

    text_query = build_text_search_query("trafico portuario maritimo")

    assert "trafico:*" in text_query
    assert "portuario:*" in text_query
    assert "maritimo:*" in text_query
    assert "educacion:*" not in text_query
    assert "escolar:*" not in text_query


def test_build_text_search_query_drops_terms_shorter_than_three_chars() -> None:
    text_query = build_text_search_query("de la ANI")

    assert "ani:*" in text_query
    assert "de:*" not in text_query
    assert "la:*" not in text_query


def test_build_text_search_query_returns_empty_string_when_only_short_terms() -> None:
    assert build_text_search_query("de la") == ""
