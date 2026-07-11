import pytest

from app.quality.territorial import TerritorioComparabilidad, evaluate_comparability


def _territorio(code: str, level: str, tipologia: str | None, categoria: str | None = None):
    return TerritorioComparabilidad(
        divipola_code=code, level=level, tipologia_dnp=tipologia, categoria_ley_617=categoria
    )


def test_same_level_and_adjacent_tipologia_is_comparable() -> None:
    result = evaluate_comparability(
        (
            _territorio("05001", "municipality", "3"),
            _territorio("05002", "municipality", "4"),
        )
    )

    assert result.comparable is True
    assert result.reasons == ()


def test_municipality_vs_department_is_level_mismatch() -> None:
    result = evaluate_comparability(
        (
            _territorio("05148", "municipality", "5"),
            _territorio("05", "department", "1"),
        )
    )

    assert result.comparable is False
    assert result.reasons == ("level_mismatch",)


def test_tipologia_gap_of_three_or_more_positions() -> None:
    result = evaluate_comparability(
        (
            _territorio("05001", "municipality", "1"),
            _territorio("05002", "municipality", "5"),
        )
    )

    assert result.comparable is False
    assert "tipologia_gap" in result.reasons


def test_tipologia_gap_below_threshold_is_comparable() -> None:
    result = evaluate_comparability(
        (
            _territorio("05001", "municipality", "2"),
            _territorio("05002", "municipality", "4"),
        )
    )

    assert result.comparable is True


def test_top_tier_vs_regular_municipality_is_gap() -> None:
    result = evaluate_comparability(
        (
            _territorio("11001", "municipality", "Bogotá"),
            _territorio("05148", "municipality", "2"),
        )
    )

    assert result.comparable is False
    assert result.reasons == ("tipologia_gap",)


def test_bogota_and_ciudades_grandes_is_gap() -> None:
    result = evaluate_comparability(
        (
            _territorio("11001", "municipality", "Bogotá"),
            _territorio("05001", "municipality", "Ciudades grandes"),
        )
    )

    assert result.comparable is False
    assert result.reasons == ("tipologia_gap",)


def test_two_ciudades_grandes_is_not_a_gap() -> None:
    result = evaluate_comparability(
        (
            _territorio("05001", "municipality", "Ciudades grandes"),
            _territorio("76001", "municipality", "Ciudades grandes"),
        )
    )

    assert result.comparable is True


def test_missing_tipologia_returns_null_comparable_with_sin_tipologia_reason() -> None:
    result = evaluate_comparability(
        (
            _territorio("05148", "municipality", "5"),
            _territorio("99999", "municipality", None),
        )
    )

    assert result.comparable is None
    assert result.reasons == ("sin_tipologia",)


def test_output_never_carries_population_or_income_fields() -> None:
    """Regla de uso (Art. I, data-model.md §6): T8 no puede exponer cifras."""

    territorio = _territorio("05001", "municipality", "3")
    assert not hasattr(territorio, "poblacion")
    assert not hasattr(territorio, "ingresos_totales_cop")


@pytest.mark.parametrize(
    "tipologia",
    ["6", "desconocida", ""],
)
def test_tipologia_outside_known_scale_does_not_crash_or_assert_gap(tipologia: str) -> None:
    result = evaluate_comparability(
        (
            _territorio("05001", "municipality", tipologia),
            _territorio("05002", "municipality", "3"),
        )
    )

    # No se afirma una brecha que no se puede sustentar contra una escala
    # desconocida (Art. I) -- no debe lanzar ni marcar comparable=False por
    # una tipologia fuera de MUNICIPAL_TIPOLOGIA_SCALE.
    assert result.comparable is True
