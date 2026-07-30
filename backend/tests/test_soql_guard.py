import pytest

from app.quality.claim_labels import COUNT_FIELD_SENTINEL
from app.tools.soql_parser import (
    ColumnInfo,
    DatasetCatalogInfo,
    SoqlGuardError,
    extract_column_field_names,
    validate_and_canonicalize,
)


def _dataset(**overrides: object) -> DatasetCatalogInfo:
    defaults: dict[str, object] = {
        "dataset_id": "nudc-7mev",
        "api_active": True,
        "eligibility_status": "eligible",
        "columns": (
            ColumnInfo("a_o", "low", "eligible"),
            ColumnInfo("desercion", "low", "eligible"),
            ColumnInfo("codigo_municipio", "low", "eligible"),
        ),
    }
    defaults.update(overrides)
    return DatasetCatalogInfo(**defaults)


# --- Aceptacion --------------------------------------------------------------


def test_accepts_simple_select() -> None:
    result = validate_and_canonicalize("SELECT a_o", _dataset())
    assert result.canonical_soql == "SELECT a_o LIMIT 1000 OFFSET 0"


def test_accepts_group_by_order_by_and_whitelisted_functions() -> None:
    soql = (
        "SELECT a_o, avg(desercion) AS prom "
        "WHERE codigo_municipio='05756' GROUP BY a_o ORDER BY a_o DESC"
    )
    result = validate_and_canonicalize(soql, _dataset())
    assert result.canonical_soql == (
        "SELECT a_o, avg(desercion) AS prom WHERE codigo_municipio = '05756' "
        "GROUP BY a_o ORDER BY a_o DESC LIMIT 1000 OFFSET 0"
    )


def test_accepts_like_and_is_null_predicates() -> None:
    soql = "SELECT a_o WHERE upper(a_o) LIKE '2025%' AND desercion IS NOT NULL"
    result = validate_and_canonicalize(soql, _dataset())
    assert "LIKE '2025%'" in result.canonical_soql
    assert "IS NOT NULL" in result.canonical_soql


# --- Rechazos estructurales (SOQL_FORBIDDEN) ---------------------------------


@pytest.mark.parametrize(
    "soql",
    [
        "SELECT *",
        "SELECT a_o; SELECT desercion",
        "SELECT stddev(desercion)",
        "SELECT a_o FOO BAR",
        "SELECT a_o WHERE a_o = 'texto sin cerrar",
        "SELECT a_o OFFSET 6000",
    ],
)
def test_rejects_structural_violations(soql: str) -> None:
    with pytest.raises(SoqlGuardError) as excinfo:
        validate_and_canonicalize(soql, _dataset())
    assert excinfo.value.code == "SOQL_FORBIDDEN"


@pytest.mark.parametrize(
    "soql",
    [
        "SELECT a_o FROM nudc-7mev WHERE a_o = 2020",
        'SELECT a_o FROM "nudc-7mev" WHERE a_o = 2020',
        "SELECT a_o FROM _nudc_7mev WHERE a_o = 2020",
        "SELECT desercion FROM nudc-7mev",
    ],
)
def test_rejects_hallucinated_from_clause_with_actionable_message(soql: str) -> None:
    """Hallazgo T-402 (2026-07-11, ejecucion real con LLM real): el LLM
    escribio SoQL con FROM (habito SQL) contra dos datasets reales distintos
    y, sin este mensaje especifico, tardo varios intentos fallidos en
    autocorregirse (probo comillas, guion bajo) porque el error generico de
    la gramatica no explicaba la causa real."""
    with pytest.raises(SoqlGuardError) as excinfo:
        validate_and_canonicalize(soql, _dataset())
    assert excinfo.value.code == "SOQL_FORBIDDEN"
    assert "FROM" in excinfo.value.message
    assert "dataset_id" in excinfo.value.message


def test_from_inside_string_literal_is_not_mistaken_for_a_clause() -> None:
    result = validate_and_canonicalize("SELECT a_o WHERE codigo_municipio = 'from'", _dataset())
    assert result.canonical_soql == "SELECT a_o WHERE codigo_municipio = 'from' LIMIT 1000 OFFSET 0"


def test_rejects_order_by_alias_not_declared_in_select() -> None:
    with pytest.raises(SoqlGuardError) as excinfo:
        validate_and_canonicalize("SELECT count(*) AS total ORDER BY totall", _dataset())
    assert excinfo.value.code == "SOQL_FORBIDDEN"


def test_rejects_too_many_where_conditions() -> None:
    conditions = " AND ".join(f"a_o = {i}" for i in range(16))
    with pytest.raises(SoqlGuardError) as excinfo:
        validate_and_canonicalize(f"SELECT a_o WHERE {conditions}", _dataset())
    assert excinfo.value.code == "SOQL_FORBIDDEN"


def test_rejects_too_many_group_by_columns() -> None:
    columns = tuple(ColumnInfo(f"col{i}", "low", "eligible") for i in range(6)) + (
        ColumnInfo("a_o", "low", "eligible"),
    )
    dataset = _dataset(columns=columns)
    group_by = ", ".join(f"col{i}" for i in range(6))
    with pytest.raises(SoqlGuardError) as excinfo:
        validate_and_canonicalize(f"SELECT a_o GROUP BY {group_by}", dataset)
    assert excinfo.value.code == "SOQL_FORBIDDEN"


@pytest.mark.parametrize(
    "soql",
    [
        "SELECT a_o; DROP TABLE catalog_datasets",
        "DELETE FROM a_o",
        "SELECT a_o WHERE a_o = 1 UPDATE a_o SET a_o = 2",
        "SELECT a_o;",
    ],
)
def test_blacklist_defense_in_depth_blocks_even_if_parser_would_not(soql: str) -> None:
    with pytest.raises(SoqlGuardError) as excinfo:
        validate_and_canonicalize(soql, _dataset())
    assert excinfo.value.code == "SOQL_FORBIDDEN"


# --- Columnas inexistentes (SOQL_UNKNOWN_COLUMN) -----------------------------


def test_rejects_unknown_column_and_reports_valid_ones() -> None:
    with pytest.raises(SoqlGuardError) as excinfo:
        validate_and_canonicalize("SELECT no_existe", _dataset())
    assert excinfo.value.code == "SOQL_UNKNOWN_COLUMN"
    assert excinfo.value.valid_columns == ["a_o", "codigo_municipio", "desercion"]


# --- Limites de LIMIT/OFFSET --------------------------------------------------


def test_injects_default_limit_when_missing() -> None:
    result = validate_and_canonicalize("SELECT a_o", _dataset())
    assert result.limit == 1000


def test_clamps_limit_above_1000() -> None:
    result = validate_and_canonicalize("SELECT a_o LIMIT 50000", _dataset())
    assert result.limit == 1000


def test_preserves_explicit_limit_under_1000() -> None:
    result = validate_and_canonicalize("SELECT a_o LIMIT 10", _dataset())
    assert result.limit == 10


# --- Canonicalizacion estable --------------------------------------------------


def test_canonicalization_is_stable_across_case_and_spacing() -> None:
    q1 = "select a_o,   avg(desercion) as prom group by a_o"
    q2 = "SELECT a_o, AVG(desercion) AS prom GROUP BY a_o"
    assert (
        validate_and_canonicalize(q1, _dataset()).canonical_soql
        == validate_and_canonicalize(q2, _dataset()).canonical_soql
    )


# --- Elegibilidad/PII antes de Socrata ----------------------------------------


def test_rejects_dataset_not_eligible_without_calling_socrata() -> None:
    dataset = _dataset(eligibility_status="diagnostic_only")
    with pytest.raises(SoqlGuardError) as excinfo:
        validate_and_canonicalize("SELECT a_o", dataset)
    assert excinfo.value.code == "EVIDENCE_NOT_ELIGIBLE"


def test_rejects_dataset_inactive() -> None:
    dataset = _dataset(api_active=False)
    with pytest.raises(SoqlGuardError) as excinfo:
        validate_and_canonicalize("SELECT a_o", dataset)
    assert excinfo.value.code == "DATASET_INACTIVE"


@pytest.mark.parametrize("pii_risk_level", ["unknown", "high"])
def test_rejects_column_with_unknown_or_high_pii(pii_risk_level: str) -> None:
    dataset = _dataset(
        columns=(ColumnInfo("a_o", pii_risk_level, "eligible"),),
    )
    with pytest.raises(SoqlGuardError) as excinfo:
        validate_and_canonicalize("SELECT a_o", dataset)
    assert excinfo.value.code == "EVIDENCE_NOT_ELIGIBLE"


def test_rejects_column_not_eligible() -> None:
    dataset = _dataset(columns=(ColumnInfo("a_o", "low", "blocked"),))
    with pytest.raises(SoqlGuardError) as excinfo:
        validate_and_canonicalize("SELECT a_o", dataset)
    assert excinfo.value.code == "EVIDENCE_NOT_ELIGIBLE"


def _medium_pii_dataset() -> DatasetCatalogInfo:
    return _dataset(
        columns=(
            ColumnInfo("edad", "medium", "eligible"),
            ColumnInfo("genero", "medium", "eligible"),
        ),
    )


def test_medium_pii_requires_aggregation_and_count() -> None:
    with pytest.raises(SoqlGuardError) as excinfo:
        validate_and_canonicalize("SELECT edad WHERE genero = 'F'", _medium_pii_dataset())
    assert excinfo.value.code == "PII_AGGREGATION_REQUIRED"


def test_medium_pii_with_proper_aggregation_and_group_by_dimension_passes() -> None:
    result = validate_and_canonicalize(
        "SELECT genero, avg(edad) AS promedio, count(*) AS total GROUP BY genero",
        _medium_pii_dataset(),
    )
    assert "count(*) AS total" in result.canonical_soql


def test_medium_pii_without_count_aggregate_is_rejected() -> None:
    with pytest.raises(SoqlGuardError) as excinfo:
        validate_and_canonicalize(
            "SELECT genero, avg(edad) AS promedio GROUP BY genero", _medium_pii_dataset()
        )
    assert excinfo.value.code == "PII_AGGREGATION_REQUIRED"


# --- extract_column_field_names (RF-212, T-617C-R1) --------------------------


def test_extract_column_field_names_resolves_plain_column_alias() -> None:
    mapping = extract_column_field_names("select genero_hombre as dim_1 limit 1")
    assert mapping == {"dim_1": "genero_hombre"}


def test_extract_column_field_names_resolves_aggregate_argument() -> None:
    mapping = extract_column_field_names(
        "select municipio as dim_1, sum(valor) as metric_sum_1 group by municipio limit 1"
    )
    assert mapping == {"dim_1": "municipio", "metric_sum_1": "valor"}


def test_extract_column_field_names_maps_count_star_to_sentinel() -> None:
    mapping = extract_column_field_names("select count(*) as metric_count_1 limit 1")
    assert mapping == {"metric_count_1": COUNT_FIELD_SENTINEL}


def test_extract_column_field_names_maps_privacy_group_count_to_sentinel() -> None:
    mapping = extract_column_field_names(
        "select genero as dim_1, avg(edad) as metric_avg_1, count(*) as group_count "
        "group by genero limit 1"
    )
    assert mapping == {
        "dim_1": "genero",
        "metric_avg_1": "edad",
        "group_count": COUNT_FIELD_SENTINEL,
    }


def test_extract_column_field_names_ignores_items_without_alias() -> None:
    mapping = extract_column_field_names("select genero_hombre limit 1")
    assert mapping == {}
