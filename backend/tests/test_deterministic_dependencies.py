import pytest

from app.agent.deterministic_dependencies import (
    RuntimeLLMUsage,
    _column_type,
    build_real_runtime_dependencies,
)
from app.agent.llm_contracts import (
    EnumeratedPlanSelection,
    QuantitativePlanSelection,
)
from app.agent.query_plan import ColumnDataType
from tests.test_settings import settings


@pytest.mark.parametrize(
    ("catalog_type", "expected"),
    [
        ("Text", ColumnDataType.TEXT),
        ("Number", ColumnDataType.NUMBER),
        ("Calendar date", ColumnDataType.DATE),
        ("Floating timestamp", ColumnDataType.DATETIME),
        ("calendar_date", ColumnDataType.DATE),
        ("Point", ColumnDataType.LOCATION),
    ],
)
def test_column_type_normalizes_real_socrata_catalog_labels(
    catalog_type: str,
    expected: ColumnDataType,
) -> None:
    assert _column_type(catalog_type) is expected


@pytest.mark.parametrize(
    ("enabled", "expected"),
    [
        (False, QuantitativePlanSelection),
        (True, EnumeratedPlanSelection),
    ],
)
def test_feature_flag_changes_the_llm_schema_itself(
    monkeypatch,
    enabled: bool,
    expected: type,
) -> None:
    schemas: list[type] = []

    def fake_model(_settings, schema):
        schemas.append(schema)
        return object()

    monkeypatch.setattr("app.agent.deterministic_dependencies._model", fake_model)
    build_real_runtime_dependencies(
        settings=settings(DETERMINISTIC_TEXTUAL_FACTS_ENABLED=enabled),
        engine=object(),  # type: ignore[arg-type]
        http_client=object(),  # type: ignore[arg-type]
        embedding_client=object(),  # type: ignore[arg-type]
        usage=RuntimeLLMUsage(),
    )
    assert schemas[1] is expected
