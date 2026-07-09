import pytest

from app.catalog.embeddings import (
    EMBEDDING_DIMENSION,
    EXPECTED_EMBEDDING_MODEL,
    ensure_embedding_dimensions,
    require_supported_embedding_model,
)


def test_require_supported_embedding_model_accepts_decided_model() -> None:
    assert require_supported_embedding_model(EXPECTED_EMBEDDING_MODEL) == EXPECTED_EMBEDDING_MODEL


@pytest.mark.parametrize("model", [None, "", "text-embedding-004", "otro-modelo"])
def test_require_supported_embedding_model_rejects_other_models(model) -> None:
    with pytest.raises(ValueError, match="gemini-embedding-2"):
        require_supported_embedding_model(model)


def test_ensure_embedding_dimensions_rejects_wrong_dimension() -> None:
    with pytest.raises(ValueError, match=str(EMBEDDING_DIMENSION)):
        ensure_embedding_dimensions("aaaa-0001", [0.1, 0.2])
