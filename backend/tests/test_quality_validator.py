"""Nodo determinista T6 (contracts/validacion-calidad.md §5, pruebas.md §2.1).

Los casos 11 ("publicador oficial: alias, alias ambiguo, entidad historica...")
y 14 ("entidad historica") del §5 ejercitan `resolve_publisher`/`is_publisher_
valid_for_reference_date`, ya cubiertos en `test_publishers_vigencia.py`,
`test_add_publishers.py` y `test_publisher_coverage.py` (T-106/T-201). T6 NO
resuelve publicadores: recibe `dataset_eligibility_status`/`_reasons` ya
calculados y solo verifica que los consume/propaga correctamente (ver casos
8 y 13 abajo).
"""

from datetime import UTC, datetime

import pytest

from app.quality.validator import (
    EvidenceDraft,
    SelectedColumn,
    classify_score,
    validate_evidence,
)

EVALUATED_AT = datetime(2026, 7, 9, tzinfo=UTC)


def draft(**overrides: object) -> EvidenceDraft:
    defaults: dict[str, object] = {
        "dataset_id": "nudc-7mev",
        "dataset_name": "MEN Estadísticas en Educación",
        "publisher": "Ministerio de Educación Nacional",
        "source_url": "https://www.datos.gov.co/d/nudc-7mev",
        "dataset_pii_risk_level": "low",
        "dataset_eligibility_status": "eligible",
        "dataset_eligibility_reasons": (),
        "canonical_soql": "SELECT a_o, avg(desercion) AS prom GROUP BY a_o LIMIT 1000 OFFSET 0",
        "selected_columns": (
            SelectedColumn("a_o", "low"),
            SelectedColumn("desercion", "low"),
        ),
        "rows": (
            {"a_o": "2026", "prom": "3.2"},
            {"a_o": "2025", "prom": "4.1"},
        ),
        "row_count": 2,
        "data_updated_at": datetime(2026, 6, 1, tzinfo=UTC),
        "evaluated_at": EVALUATED_AT,
    }
    defaults.update(overrides)
    return EvidenceDraft(**defaults)


# --- Caso 1: dataset fresco, completo, oficial => alta ----------------------


def test_case_1_fresh_complete_official_dataset_is_alta() -> None:
    result = validate_evidence(draft())

    assert result.classification == "alta"
    assert result.eligibility_status == "eligible"
    assert result.score_total >= 75


# --- Caso 2: corte > 48 meses => D3=15 + advertencia ------------------------


def test_case_2_cutoff_older_than_48_months_scores_15_with_warning() -> None:
    result = validate_evidence(
        draft(
            canonical_soql="SELECT a_o GROUP BY a_o LIMIT 1000 OFFSET 0",
            selected_columns=(SelectedColumn("a_o", "low"),),
            rows=({"a_o": "2020"}, {"a_o": "2019"}),
        )
    )

    assert result.dimensions["timeliness"].score == 15
    assert any("corte" in warning.lower() for warning in result.warnings_user)
    assert any("desactualizado" in warning for warning in result.warnings_user)


# --- Caso 3: columna citada con 60% nulos => null_ratio pierde puntos -------


def test_case_3_column_with_60_percent_nulls_scores_zero_null_ratio_points() -> None:
    result = validate_evidence(
        draft(
            canonical_soql="SELECT desercion GROUP BY desercion LIMIT 1000 OFFSET 0",
            selected_columns=(SelectedColumn("desercion", "low"),),
            rows=(
                {"desercion": None},
                {"desercion": None},
                {"desercion": None},
                {"desercion": "3.2"},
                {"desercion": "4.1"},
            ),
            row_count=5,
        )
    )

    null_ratio_check = result.dimensions["completeness"].checks[0]
    assert null_ratio_check.check == "completeness.null_ratio"
    assert null_ratio_check.passed is False
    # 3/5 = 60% > 50% => bucket 0% del maximo de 60 puntos.
    assert result.dimensions["completeness"].score == 40  # solo placeholder_values (40) suma


# --- Caso 4: placeholders confirmados por contexto --------------------------


def test_case_4a_generic_placeholder_above_ratio_loses_points_and_warns() -> None:
    result = validate_evidence(
        draft(
            canonical_soql="SELECT nomindicador GROUP BY nomindicador LIMIT 1000 OFFSET 0",
            selected_columns=(SelectedColumn("nomindicador", "low"),),
            rows=tuple({"nomindicador": "Default O_D_S"} for _ in range(4))
            + tuple({"nomindicador": "Valor real"} for _ in range(6)),
            row_count=10,
        )
    )

    placeholder_check = result.dimensions["completeness"].checks[1]
    assert placeholder_check.passed is False
    assert any("Default O_D_S" in warning for warning in result.warnings_user)


def test_case_4b_codebook_documented_code_loses_points() -> None:
    result = validate_evidence(
        draft(
            canonical_soql="SELECT estado_civil GROUP BY estado_civil LIMIT 1000 OFFSET 0",
            selected_columns=(
                SelectedColumn("estado_civil", "low", known_placeholder_codes=("9", "99")),
            ),
            rows=tuple({"estado_civil": "9"} for _ in range(3))
            + tuple({"estado_civil": "1"} for _ in range(7)),
            row_count=10,
        )
    )

    placeholder_check = result.dimensions["completeness"].checks[1]
    assert placeholder_check.passed is False


# --- Caso 5: falsos positivos evitados ---------------------------------------


def test_case_5a_total_as_legitimate_category_is_not_flagged() -> None:
    result = validate_evidence(
        draft(
            canonical_soql="SELECT categoria GROUP BY categoria LIMIT 1000 OFFSET 0",
            selected_columns=(SelectedColumn("categoria", "low"),),
            rows=tuple({"categoria": "Total"} for _ in range(10)),
            row_count=10,
        )
    )

    assert result.dimensions["completeness"].checks[1].passed is True


def test_case_5b_real_numeric_value_without_codebook_is_not_flagged() -> None:
    result = validate_evidence(
        draft(
            canonical_soql="SELECT edad_codigo GROUP BY edad_codigo LIMIT 1000 OFFSET 0",
            selected_columns=(SelectedColumn("edad_codigo", "low"),),
            rows=tuple({"edad_codigo": "9"} for _ in range(10)),
            row_count=10,
        )
    )

    assert result.dimensions["completeness"].checks[1].passed is True


# --- Caso 6: 0 filas => "consulta sin resultados" ---------------------------


def test_case_6_zero_rows_forces_schema_zero_and_no_recomendada() -> None:
    result = validate_evidence(draft(rows=(), row_count=0))

    assert result.dimensions["schema"].score == 0
    assert result.classification == "no_recomendada"
    assert any("no devolvió resultados" in warning for warning in result.warnings_user)


# --- Caso 7: falta source_url => no_recomendada forzada ---------------------


def test_case_7_missing_source_url_forces_no_recomendada() -> None:
    result = validate_evidence(draft(source_url=None))

    assert result.classification == "no_recomendada"
    assert result.dimensions["traceability"].checks[0].passed is False


# --- Caso 8: publisher no estatal => rechazada con explicación --------------


def test_case_8_unverified_publisher_is_diagnostic_only_with_reason() -> None:
    result = validate_evidence(
        draft(
            dataset_eligibility_status="diagnostic_only",
            dataset_eligibility_reasons=("publisher_unknown",),
        )
    )

    assert result.eligibility_status == "diagnostic_only"
    assert "publisher_unknown" in result.eligibility_reasons
    assert any("entidad oficial" in warning for warning in result.warnings_user)


# --- Caso 9: determinismo ----------------------------------------------------


def test_case_9_same_input_twice_produces_identical_output() -> None:
    assert validate_evidence(draft()) == validate_evidence(draft())


# --- Caso 10: corte inferible vs fallback -------------------------------------


def test_case_10_infers_cutoff_from_rows_when_possible() -> None:
    result = validate_evidence(draft())

    assert result.data_cutoff.basis == "data_cutoff_at"
    assert result.data_cutoff.column == "a_o"


def test_case_10_falls_back_to_data_updated_at_without_temporal_field() -> None:
    result = validate_evidence(
        draft(
            canonical_soql="SELECT nombre GROUP BY nombre LIMIT 1000 OFFSET 0",
            selected_columns=(SelectedColumn("nombre", "low"),),
            rows=({"nombre": "Colombia"},),
            row_count=1,
            data_updated_at=datetime(2021, 1, 1, tzinfo=UTC),
        )
    )

    assert result.data_cutoff.basis == "data_updated_at_fallback"
    warning = next(w for w in result.warnings_user if "actualizó" in w)
    assert "no fue posible inferir el corte estadístico" in warning


# --- Caso 12: datos personales -----------------------------------------------


def test_case_12_medium_pii_with_sufficient_aggregation_stays_eligible() -> None:
    result = validate_evidence(
        draft(
            dataset_pii_risk_level="medium",
            selected_columns=(SelectedColumn("genero", "medium"),),
            canonical_soql="SELECT genero, count(*) AS total GROUP BY genero LIMIT 1000 OFFSET 0",
            rows=({"genero": "F", "total": "10"}, {"genero": "M", "total": "8"}),
            row_count=2,
        )
    )

    assert result.eligibility_status == "eligible"
    assert result.row_policy.aggregation_min_count == 8
    assert result.row_policy.contains_individual_rows is False


def test_case_12_medium_pii_with_insufficient_aggregation_is_blocked() -> None:
    result = validate_evidence(
        draft(
            dataset_pii_risk_level="medium",
            selected_columns=(SelectedColumn("genero", "medium"),),
            canonical_soql="SELECT genero, count(*) AS total GROUP BY genero LIMIT 1000 OFFSET 0",
            rows=({"genero": "F", "total": "2"}, {"genero": "M", "total": "8"}),
            row_count=2,
        )
    )

    assert result.eligibility_status == "blocked"
    assert "pii_aggregation_insufficient" in result.eligibility_reasons


def test_case_12_medium_pii_count_without_explicit_alias_still_counts() -> None:
    """Regresion del hallazgo T-303: `count(*)` sin `AS` es una consulta valida
    (RF-401 solo exige "count(*) o agregado equivalente", no un alias); Socrata
    nombra esa columna `count` cuando no se declara alias."""
    result = validate_evidence(
        draft(
            dataset_pii_risk_level="medium",
            selected_columns=(SelectedColumn("desercion", "medium"),),
            canonical_soql="SELECT avg(desercion), count(*) LIMIT 1000 OFFSET 0",
            rows=({"avg_desercion": "3.966", "count": "5"},),
            row_count=1,
        )
    )

    assert result.eligibility_status == "eligible"
    assert result.row_policy.aggregation_min_count == 5


def test_case_12_medium_pii_sum_without_count_is_blocked_even_with_many_rows() -> None:
    """Hallazgo real (2026-07-12, smoke contra Gemini, pilot-002-seguridad-
    homicidios): `_count_alias` solo reconoce `count(...)`; una agregación
    `sum()`/`avg()`/`min()`/`max()` SIN `count(*)` acompañante no puede
    verificar cuántas filas reales aporta cada grupo (sum(cantidad)=66723
    es indistinguible de una sola fila con cantidad=66723 o de 66723 filas
    con cantidad=1), así que se bloquea aunque el agregado real sume miles
    de casos. Esto es una decisión de diseño correcta (Art. VI) -- lo que
    faltaba era que `router_v1.md` le exigiera al LLM incluir siempre
    count(*) al agrupar."""
    result = validate_evidence(
        draft(
            dataset_pii_risk_level="medium",
            selected_columns=(SelectedColumn("departamento", "medium"),),
            canonical_soql=(
                "SELECT departamento, sum(cantidad) AS total_homicidios "
                "GROUP BY departamento ORDER BY total_homicidios DESC LIMIT 1000 OFFSET 0"
            ),
            rows=({"departamento": "VALLE DEL CAUCA", "total_homicidios": "66723"},),
            row_count=1,
        )
    )

    assert result.eligibility_status == "blocked"
    assert "pii_aggregation_insufficient" in result.eligibility_reasons
    assert result.row_policy.aggregation_min_count is None


# --- Caso 13: elegibilidad vs calidad (independientes) -----------------------


def test_case_13_statistically_alta_but_unverified_publisher_is_diagnostic_only() -> None:
    result = validate_evidence(
        draft(
            dataset_eligibility_status="diagnostic_only",
            dataset_eligibility_reasons=("publisher_unknown",),
        )
    )

    assert result.score_total >= 75
    assert result.classification == "alta"
    assert result.eligibility_status == "diagnostic_only"


# --- Pruebas de frontera (pruebas.md §2.1) -----------------------------------


@pytest.mark.parametrize(
    "months,expected_score",
    [(12, 100), (13, 70), (24, 70), (25, 40), (48, 40), (49, 15)],
)
def test_boundary_age_thresholds(months: int, expected_score: int) -> None:
    # Construimos data_updated_at exactamente `months` meses antes de
    # evaluated_at (mismo dia-de-mes, para que la resta de meses sea exacta).
    total_months = EVALUATED_AT.year * 12 + (EVALUATED_AT.month - 1) - months
    year, month0 = divmod(total_months, 12)
    data_updated_at = datetime(year, month0 + 1, EVALUATED_AT.day, tzinfo=UTC)

    result = validate_evidence(
        draft(
            canonical_soql="SELECT nombre GROUP BY nombre LIMIT 1000 OFFSET 0",
            selected_columns=(SelectedColumn("nombre", "low"),),
            rows=({"nombre": "Colombia"},),
            row_count=1,
            data_updated_at=data_updated_at,
        )
    )

    assert result.dimensions["timeliness"].score == expected_score


def test_boundary_null_ratio_exactly_5_percent_scores_full_points() -> None:
    # 1 celda vacia de 20 (2 columnas x 10 filas) = 5.0% exacto.
    rows = tuple({"a": "x", "b": "y"} for _ in range(9)) + ({"a": "x", "b": None},)
    result = validate_evidence(
        draft(
            canonical_soql="SELECT a, b GROUP BY a, b LIMIT 1000 OFFSET 0",
            selected_columns=(SelectedColumn("a", "low"), SelectedColumn("b", "low")),
            rows=rows,
            row_count=10,
        )
    )

    null_ratio_check = result.dimensions["completeness"].checks[0]
    assert null_ratio_check.passed is True
    assert result.dimensions["completeness"].score == 100


@pytest.mark.parametrize(
    "score,expected",
    [
        (34, "no_recomendada"),
        (35, "baja"),
        (54, "baja"),
        (55, "media"),
        (74, "media"),
        (75, "alta"),
        (100, "alta"),
    ],
)
def test_boundary_classification_thresholds(score: int, expected: str) -> None:
    assert classify_score(score) == expected


# --- Lenguaje claro (Art. V.5): warnings_user sin jerga tecnica -------------


_TECHNICAL_TOKENS = (
    "schema.",
    "completeness.",
    "timeliness.",
    "traceability.",
    "eligibility_status",
    "pii_risk_level",
    "classification",
)


def test_warnings_user_never_mention_technical_check_names() -> None:
    scenarios = [
        draft(rows=(), row_count=0),
        draft(source_url=None),
        draft(
            dataset_eligibility_status="diagnostic_only",
            dataset_eligibility_reasons=("publisher_unknown",),
        ),
        draft(
            canonical_soql="SELECT a_o GROUP BY a_o LIMIT 1000 OFFSET 0",
            selected_columns=(SelectedColumn("a_o", "low"),),
            rows=({"a_o": "2019"},),
            row_count=1,
        ),
    ]

    for scenario in scenarios:
        result = validate_evidence(scenario)
        for warning in result.warnings_user:
            for token in _TECHNICAL_TOKENS:
                assert token not in warning, f"jerga tecnica en warning: {warning!r}"
