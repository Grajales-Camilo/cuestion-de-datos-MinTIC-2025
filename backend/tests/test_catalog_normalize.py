import json
from pathlib import Path

import pytest

from app.catalog.normalize import (
    build_embedding_text,
    clean_description_html,
    extract_columns,
    extract_publisher_text,
    is_tabular_with_active_api,
    parse_data_updated_at,
    to_normalized_dataset,
    truncate_description,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "discovery_sample.json"


@pytest.fixture
def sample_items() -> dict[str, dict]:
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return {item["resource"]["id"]: item for item in data["results"]}


def test_is_tabular_with_active_api_true_for_dataset(sample_items) -> None:
    covid = sample_items["gt2j-8ykr"]
    assert is_tabular_with_active_api(covid["resource"]) is True


def test_is_tabular_with_active_api_false_for_map(sample_items) -> None:
    mapa = sample_items["p57x-7s28"]
    assert is_tabular_with_active_api(mapa["resource"]) is False


def test_clean_description_html_strips_tags_and_unescapes() -> None:
    cleaned = clean_description_html("<p>Datos &amp; más <b>información</b></p>")
    assert cleaned == "Datos & más información"


def test_clean_description_html_none_stays_none() -> None:
    assert clean_description_html(None) is None


def test_truncate_description_respects_limit() -> None:
    long_text = "a" * 3000
    assert len(truncate_description(long_text)) == 2000


def test_extract_publisher_text_prefers_owner_display_name(sample_items) -> None:
    covid = sample_items["gt2j-8ykr"]
    assert extract_publisher_text(covid) == "Instituto Nacional de Salud"


def test_extract_publisher_text_falls_back_to_attribution() -> None:
    item = {"resource": {"attribution": "Alguna Entidad"}}
    assert extract_publisher_text(item) == "Alguna Entidad"


def test_extract_publisher_text_none_when_missing() -> None:
    assert extract_publisher_text({"resource": {}}) is None


def test_extract_columns_real_dataset(sample_items) -> None:
    covid = sample_items["gt2j-8ykr"]
    columns = extract_columns(covid["resource"])
    assert len(columns) == len(covid["resource"]["columns_field_name"])
    assert all(column.field_name for column in columns)


def test_extract_columns_empty_for_map(sample_items) -> None:
    mapa = sample_items["p57x-7s28"]
    assert extract_columns(mapa["resource"]) == []


def test_parse_data_updated_at_real_format() -> None:
    parsed = parse_data_updated_at("2024-01-18T17:30:09.000Z")
    assert parsed is not None
    assert parsed.year == 2024
    assert parsed.month == 1
    assert parsed.day == 18


def test_parse_data_updated_at_none() -> None:
    assert parse_data_updated_at(None) is None


def test_parse_data_updated_at_invalid_string_returns_none() -> None:
    assert parse_data_updated_at("no es una fecha") is None


def test_build_embedding_text_short_description_repeats_title_and_columns() -> None:
    text = build_embedding_text(
        name="Dataset X",
        description="corta",
        publisher_text="Entidad Y",
        category="Categoria Z",
        column_names=["a", "b"],
    )
    assert text.count("Dataset X") == 2
    assert text.count("Columnas") == 2


def test_build_embedding_text_normal_description_does_not_repeat() -> None:
    text = build_embedding_text(
        name="Dataset X",
        description="a" * 150,
        publisher_text="Entidad Y",
        category="Categoria Z",
        column_names=["a", "b"],
    )
    assert text.count("Dataset X") == 1


def test_to_normalized_dataset_full_real_record(sample_items) -> None:
    covid = sample_items["gt2j-8ykr"]
    normalized = to_normalized_dataset(covid)

    assert normalized is not None
    assert normalized.id == "gt2j-8ykr"
    assert normalized.name == "Casos positivos de COVID-19 en Colombia."
    assert normalized.publisher_text == "Instituto Nacional de Salud"
    assert normalized.category == "Salud y Protección Social"
    assert len(normalized.columns) > 0
    assert normalized.data_updated_at is not None
    assert normalized.embedding_text


def test_to_normalized_dataset_returns_none_for_map(sample_items) -> None:
    mapa = sample_items["p57x-7s28"]
    assert to_normalized_dataset(mapa) is None


def test_to_normalized_dataset_returns_none_without_name() -> None:
    item = {
        "resource": {
            "id": "xxxx-yyyy",
            "type": "dataset",
            "columns_field_name": ["a"],
            "columns_name": ["A"],
            "columns_datatype": ["Text"],
        }
    }
    assert to_normalized_dataset(item) is None
