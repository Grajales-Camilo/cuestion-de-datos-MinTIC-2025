import pytest

from app.quality.placeholders import (
    ColumnValues,
    detect_placeholder,
    load_placeholder_patterns,
)

FIXTURE = load_placeholder_patterns()


def test_generic_placeholder_above_ratio_is_detected() -> None:
    values = tuple(["Default O_D_S"] * 4 + ["Real value"] * 6)
    column = ColumnValues("nomindicador", values)

    detection = detect_placeholder(column, FIXTURE, min_ratio=0.30)

    assert detection is not None
    assert detection.value == "Default O_D_S"
    assert detection.ratio == pytest.approx(0.4)


def test_generic_placeholder_below_ratio_is_not_detected() -> None:
    values = tuple(["Default O_D_S"] * 2 + ["Real value"] * 8)
    column = ColumnValues("nomindicador", values)

    assert detect_placeholder(column, FIXTURE, min_ratio=0.30) is None


def test_total_as_legitimate_category_is_never_flagged() -> None:
    column = ColumnValues("categoria", tuple(["Total"] * 10))

    assert detect_placeholder(column, FIXTURE, min_ratio=0.30) is None


def test_numeric_value_without_codebook_is_never_flagged() -> None:
    column = ColumnValues("edad_codigo", tuple(["9"] * 10))

    assert detect_placeholder(column, FIXTURE, min_ratio=0.30) is None


def test_codebook_documented_code_is_flagged_regardless_of_ratio() -> None:
    column = ColumnValues(
        "estado_civil", tuple(["9"] + ["1"] * 9), known_placeholder_codes=("9", "99")
    )

    detection = detect_placeholder(column, FIXTURE, min_ratio=0.30)

    assert detection is not None
    assert detection.value == "9"
    assert detection.ratio == pytest.approx(0.1)


def test_empty_column_is_never_flagged() -> None:
    column = ColumnValues("vacia", ())

    assert detect_placeholder(column, FIXTURE, min_ratio=0.30) is None
