"""T-615D: normalización, operaciones y hash puros de hechos textuales."""

from __future__ import annotations

from dataclasses import replace
from math import inf, nan

import pytest

from app.quality.grounded_facts import (
    CategorySelectionParams,
    EmptyTextualFactOperationParams,
    ExtremumLabelParams,
    TextualFactOperation,
    ValuePresenceParams,
)
from app.quality.textual_facts import (
    TextualEvidence,
    TextualFactSpec,
    TextualOperationError,
    canonicalize_jcs,
    evaluate_textual_operation,
    normalize_text_es_v1,
)


def evidence(
    rows: tuple[dict[str, object], ...],
    *,
    dataset_id: str = "abcd-1234",
    canonical_soql: str = "SELECT municipio LIMIT 1000 OFFSET 0",
    validated_order_is_total: bool = False,
) -> TextualEvidence:
    return TextualEvidence(
        dataset_id=dataset_id,
        canonical_soql=canonical_soql,
        rows=rows,
        validated_order_is_total=validated_order_is_total,
    )


def spec(
    operation: TextualFactOperation,
    *,
    indexes: tuple[int, ...] = (0,),
    columns: tuple[str, ...] = ("municipio",),
    params=None,
) -> TextualFactSpec:
    if params is None:
        params = EmptyTextualFactOperationParams()
    return TextualFactSpec(
        operation=operation,
        source_row_indexes=indexes,
        columns=columns,
        operation_params=params,
    )


def build(rows: tuple[dict[str, object], ...], fact_spec: TextualFactSpec):
    return evaluate_textual_operation(
        evidence=evidence(rows),
        spec=fact_spec,
    )


def assert_rejected(code: str, callback) -> None:
    with pytest.raises(TextualOperationError) as captured:
        callback()
    assert captured.value.code == code


def test_text_es_v1_normalizes_unicode_spaces_and_line_endings_without_losing_graphy() -> None:
    raw = " \u00a0MEDELLI\u0301N\r\nD.C.\t¡Sí, señor!  "
    normalized = normalize_text_es_v1(raw)

    assert normalized.raw == raw
    assert normalized.display == "MEDELLÍN D.C. ¡Sí, señor!"
    assert normalized.comparison == "medellín d.c. ¡sí, señor!"
    assert "ñ" in normalized.comparison
    assert "í" in normalized.comparison
    assert "¡" in normalized.comparison


@pytest.mark.parametrize("value", [None, "", " \r\n\t\u00a0"])
def test_text_es_v1_rejects_null_or_empty_values(value: str | None) -> None:
    expected = "textual_null_value" if value is None else "textual_empty_value"
    assert_rejected(expected, lambda: normalize_text_es_v1(value))


def test_text_es_v1_rejects_invalid_unicode_surrogates() -> None:
    assert_rejected("textual_invalid_unicode", lambda: normalize_text_es_v1("\ud800"))


def test_text_es_v1_rejects_non_string_values() -> None:
    assert_rejected("textual_non_string_value", lambda: normalize_text_es_v1(123))  # type: ignore[arg-type]


def test_direct_text_preserves_display_and_builds_no_numeric_surrogate() -> None:
    fact = build(
        ({"municipio": "  Medellín  "},),
        spec(TextualFactOperation.DIRECT_TEXT),
    )

    assert fact.display_value == "Medellín"
    assert fact.raw_values == ("  Medellín  ",)
    assert fact.normalized_values == ("medellín",)
    assert not hasattr(fact, "fact")
    assert not hasattr(fact, "raw_value")


@pytest.mark.parametrize(
    ("rows", "fact_spec", "code"),
    [
        (
            ({"municipio": "Medellín"},),
            spec(TextualFactOperation.DIRECT_TEXT, indexes=(1,)),
            "textual_invalid_row_index",
        ),
        (({"otra": "Medellín"},), spec(TextualFactOperation.DIRECT_TEXT), "textual_missing_column"),
        (({"municipio": None},), spec(TextualFactOperation.DIRECT_TEXT), "textual_null_value"),
        (({"municipio": " \t"},), spec(TextualFactOperation.DIRECT_TEXT), "textual_empty_value"),
        (
            ({"municipio": "Medellín"}, {"municipio": "Bogotá"}),
            spec(TextualFactOperation.DIRECT_TEXT, indexes=(0, 1)),
            "textual_invalid_row_cardinality",
        ),
        (
            ({"municipio": "Medellín", "otra": "x"},),
            spec(TextualFactOperation.DIRECT_TEXT, columns=("municipio", "otra")),
            "textual_invalid_column_cardinality",
        ),
    ],
)
def test_direct_text_rejects_invalid_sources(rows, fact_spec, code: str) -> None:
    assert_rejected(code, lambda: build(rows, fact_spec))


@pytest.mark.parametrize(
    ("indexes", "columns", "code"),
    [
        ((), ("municipio",), "textual_source_rows_empty"),
        ((0, 0), ("municipio",), "textual_duplicate_row_index"),
        ((-1,), ("municipio",), "textual_invalid_row_index"),
        ((True,), ("municipio",), "textual_invalid_row_index"),
        ((0,), (), "textual_columns_empty"),
        ((0,), ("municipio", "municipio"), "textual_duplicate_column"),
    ],
)
def test_builder_rejects_invalid_index_and_column_shapes(
    indexes: tuple[int, ...],
    columns: tuple[str, ...],
    code: str,
) -> None:
    assert_rejected(
        code,
        lambda: build(
            ({"municipio": "Medellín"},),
            spec(
                TextualFactOperation.DIRECT_TEXT,
                indexes=indexes,
                columns=columns,
            ),
        ),
    )


@pytest.mark.parametrize(
    ("operation", "params"),
    [
        (
            TextualFactOperation.DIRECT_TEXT,
            ValuePresenceParams(target_raw="Medellín", target_normalized="medellín"),
        ),
        (TextualFactOperation.VALUE_PRESENCE, EmptyTextualFactOperationParams()),
        (TextualFactOperation.CATEGORY_SELECTION, EmptyTextualFactOperationParams()),
        (TextualFactOperation.ARGMAX_LABEL, EmptyTextualFactOperationParams()),
        (
            TextualFactOperation.CANONICAL_TEXT_SET,
            CategorySelectionParams(rule="unique_normalized_value"),
        ),
    ],
)
def test_builder_rejects_operation_params_from_another_branch(
    operation: TextualFactOperation,
    params,
) -> None:
    columns = (
        ("municipio", "total") if operation is TextualFactOperation.ARGMAX_LABEL else ("municipio",)
    )
    assert_rejected(
        "textual_invalid_operation_params",
        lambda: build(
            ({"municipio": "Medellín", "total": 1},),
            spec(operation, columns=columns, params=params),
        ),
    )


def test_value_presence_matches_by_casefold_and_ignores_nulls() -> None:
    fact = build(
        ({"municipio": None}, {"municipio": "Rural"}, {"municipio": "rural"}),
        spec(
            TextualFactOperation.VALUE_PRESENCE,
            indexes=(2, 0, 1),
            params=ValuePresenceParams(target_raw=" rural ", target_normalized="rural"),
        ),
    )

    assert fact.source_row_indexes == (0, 1, 2)
    assert fact.display_value == "Rural"
    assert fact.normalized_values == ("rural",)
    assert fact.operation_params.target_raw == " rural "


def test_value_presence_rejects_absence_bad_target_and_empty_cell() -> None:
    rows = ({"municipio": "Urbano"},)
    assert_rejected(
        "textual_value_absent",
        lambda: build(
            rows,
            spec(
                TextualFactOperation.VALUE_PRESENCE,
                params=ValuePresenceParams(target_raw="Rural", target_normalized="rural"),
            ),
        ),
    )
    assert_rejected(
        "textual_invalid_target",
        lambda: build(
            rows,
            spec(
                TextualFactOperation.VALUE_PRESENCE,
                params=ValuePresenceParams(target_raw="Rural", target_normalized="urbano"),
            ),
        ),
    )
    assert_rejected(
        "textual_empty_value",
        lambda: build(
            ({"municipio": "Urbano"}, {"municipio": "  "}),
            spec(
                TextualFactOperation.VALUE_PRESENCE,
                indexes=(0, 1),
                params=ValuePresenceParams(target_raw="Urbano", target_normalized="urbano"),
            ),
        ),
    )
    assert_rejected(
        "textual_no_values",
        lambda: build(
            ({"municipio": None},),
            spec(
                TextualFactOperation.VALUE_PRESENCE,
                params=ValuePresenceParams(target_raw="Urbano", target_normalized="urbano"),
            ),
        ),
    )


def test_category_selection_requires_a_reproducible_unique_winner() -> None:
    unique = build(
        ({"estado": "Activo"}, {"estado": None}, {"estado": "ACTIVO"}),
        spec(
            TextualFactOperation.CATEGORY_SELECTION,
            indexes=(0, 1, 2),
            columns=("estado",),
            params=CategorySelectionParams(rule="unique_normalized_value"),
        ),
    )
    assert unique.display_value == "ACTIVO"

    assert_rejected(
        "textual_ambiguous_category",
        lambda: build(
            ({"estado": "Activo"}, {"estado": "Inactivo"}),
            spec(
                TextualFactOperation.CATEGORY_SELECTION,
                indexes=(0, 1),
                columns=("estado",),
                params=CategorySelectionParams(rule="unique_normalized_value"),
            ),
        ),
    )


def test_category_first_by_order_requires_total_validated_order_and_limit() -> None:
    fact_spec = spec(
        TextualFactOperation.CATEGORY_SELECTION,
        columns=("estado",),
        params=CategorySelectionParams(rule="first_by_validated_order"),
    )
    unproved = evidence(
        ({"estado": "Activo"},),
        canonical_soql="SELECT estado ORDER BY estado ASC LIMIT 1 OFFSET 0",
    )
    assert_rejected(
        "textual_order_not_validated",
        lambda: evaluate_textual_operation(evidence=unproved, spec=fact_spec),
    )

    proved = replace(unproved, validated_order_is_total=True)
    fact = evaluate_textual_operation(evidence=proved, spec=fact_spec)
    assert fact.display_value == "Activo"

    without_limit = replace(
        proved,
        canonical_soql="SELECT estado ORDER BY estado ASC",
    )
    assert_rejected(
        "textual_order_not_validated",
        lambda: evaluate_textual_operation(evidence=without_limit, spec=fact_spec),
    )
    multiple_rows = replace(
        proved,
        rows=({"estado": "Activo"}, {"estado": "Inactivo"}),
    )
    assert_rejected(
        "textual_invalid_row_cardinality",
        lambda: evaluate_textual_operation(
            evidence=multiple_rows,
            spec=replace(fact_spec, source_row_indexes=(0, 1)),
        ),
    )


@pytest.mark.parametrize(
    ("operation", "expected"),
    [
        (TextualFactOperation.ARGMAX_LABEL, "Bogotá"),
        (TextualFactOperation.ARGMIN_LABEL, "Medellín"),
    ],
)
def test_extrema_select_the_unique_label(operation: TextualFactOperation, expected: str) -> None:
    fact = build(
        (
            {"municipio": "Medellín", "total": "2.0"},
            {"municipio": "Bogotá", "total": 5},
        ),
        spec(
            operation,
            indexes=(1, 0),
            columns=("municipio", "total"),
            params=ExtremumLabelParams(
                label_column="municipio",
                metric_column="total",
                tie_policy="reject",
            ),
        ),
    )

    assert fact.display_value == expected
    assert fact.raw_values == (expected,)


@pytest.mark.parametrize("metric", [None, "no-numérico", inf, -inf, nan, True])
def test_extrema_reject_null_non_numeric_or_non_finite_metrics(metric: object) -> None:
    assert_rejected(
        "textual_invalid_metric",
        lambda: build(
            ({"municipio": "Medellín", "total": metric},),
            spec(
                TextualFactOperation.ARGMAX_LABEL,
                columns=("municipio", "total"),
                params=ExtremumLabelParams(
                    label_column="municipio",
                    metric_column="total",
                ),
            ),
        ),
    )


@pytest.mark.parametrize(
    "operation",
    [TextualFactOperation.ARGMAX_LABEL, TextualFactOperation.ARGMIN_LABEL],
)
def test_extrema_reject_ties_instead_of_using_incidental_order(
    operation: TextualFactOperation,
) -> None:
    assert_rejected(
        "textual_extremum_tie",
        lambda: build(
            (
                {"municipio": "Medellín", "total": 5},
                {"municipio": "Bogotá", "total": 5},
            ),
            spec(
                operation,
                indexes=(0, 1),
                columns=("municipio", "total"),
                params=ExtremumLabelParams(
                    label_column="municipio",
                    metric_column="total",
                ),
            ),
        ),
    )


def test_extrema_reject_columns_that_do_not_match_typed_params() -> None:
    assert_rejected(
        "textual_invalid_extremum_columns",
        lambda: build(
            ({"municipio": "Medellín", "total": 5},),
            spec(
                TextualFactOperation.ARGMAX_LABEL,
                columns=("total", "municipio"),
                params=ExtremumLabelParams(
                    label_column="municipio",
                    metric_column="total",
                ),
            ),
        ),
    )


def test_canonical_text_set_deduplicates_and_orders_independently_of_index_input_order() -> None:
    rows = (
        {"municipio": "Bogotá"},
        {"municipio": "medellín"},
        {"municipio": "BOGOTÁ"},
        {"municipio": None},
    )
    forward = build(
        rows,
        spec(TextualFactOperation.CANONICAL_TEXT_SET, indexes=(0, 1, 2, 3)),
    )
    reordered = build(
        rows,
        spec(TextualFactOperation.CANONICAL_TEXT_SET, indexes=(3, 2, 1, 0)),
    )

    assert forward.raw_values == ("BOGOTÁ", "medellín")
    assert forward.normalized_values == ("bogotá", "medellín")
    assert forward.display_value == "BOGOTÁ; medellín"
    assert reordered.source_hash == forward.source_hash


def test_canonical_text_set_rejects_an_all_null_collection() -> None:
    assert_rejected(
        "textual_no_values",
        lambda: build(
            ({"municipio": None},),
            spec(TextualFactOperation.CANONICAL_TEXT_SET),
        ),
    )


def test_cardinality_limits_reject_instead_of_truncating() -> None:
    too_many_rows = tuple({"municipio": f"valor-{index}"} for index in range(101))
    assert_rejected(
        "textual_cardinality_exceeded",
        lambda: build(
            too_many_rows,
            spec(
                TextualFactOperation.CANONICAL_TEXT_SET,
                indexes=tuple(range(101)),
            ),
        ),
    )
    too_many_values = tuple({"municipio": f"valor-{index:02d}"} for index in range(51))
    assert_rejected(
        "textual_cardinality_exceeded",
        lambda: build(
            too_many_values,
            spec(
                TextualFactOperation.CANONICAL_TEXT_SET,
                indexes=tuple(range(51)),
            ),
        ),
    )


def test_rfc8785_known_primitive_vector_is_exact() -> None:
    value = {
        "numbers": [333333333.33333329, 1e30, 4.50, 2e-3, 1e-27],
        "string": '€$\u000f\nA\'B"\\\\"/',
        "literals": [None, True, False],
    }
    assert canonicalize_jcs(value) == (
        b'{"literals":[null,true,false],"numbers":[333333333.3333333,'
        b'1e+30,4.5,0.002,1e-27],"string":"\xe2\x82\xac$\\u000f\\nA\'B\\"'
        b'\\\\\\\\\\"/"}'
    )


def test_rfc8785_known_utf16_property_sort_vector_is_exact() -> None:
    value = {
        "\u20ac": "Euro Sign",
        "\r": "Carriage Return",
        "\ufb33": "Hebrew Letter Dalet With Dagesh",
        "1": "One",
        "\U0001f600": "Emoji: Grinning Face",
        "\u0080": "Control",
        "\u00f6": "Latin Small Letter O With Diaeresis",
    }
    assert canonicalize_jcs(value).decode("utf-8") == (
        '{"\\r":"Carriage Return","1":"One","\u0080":"Control",'
        '"ö":"Latin Small Letter O With Diaeresis","€":"Euro Sign",'
        '"😀":"Emoji: Grinning Face","דּ":"Hebrew Letter Dalet With Dagesh"}'
    )


@pytest.mark.parametrize("value", [nan, inf, -inf])
def test_rfc8785_rejects_non_finite_numbers(value: float) -> None:
    assert_rejected("textual_jcs_invalid", lambda: canonicalize_jcs({"value": value}))


def test_hash_changes_when_only_source_graphy_changes() -> None:
    fact_spec = spec(TextualFactOperation.DIRECT_TEXT)
    first = evaluate_textual_operation(
        evidence=evidence(({"municipio": "  Medellín  "},)),
        spec=fact_spec,
    )
    second = evaluate_textual_operation(
        evidence=evidence(({"municipio": "Medellín"},)),
        spec=fact_spec,
    )

    assert first.raw_values == ("  Medellín  ",)
    assert second.raw_values == ("Medellín",)
    assert first.display_value == second.display_value == "Medellín"
    assert first.normalized_values == second.normalized_values == ("medellín",)
    assert first.source_hash != second.source_hash


def test_raw_preserves_nfd_while_display_and_comparison_use_nfc() -> None:
    raw_nfd = "Medelli\u0301n"
    fact = build(
        ({"municipio": raw_nfd},),
        spec(TextualFactOperation.DIRECT_TEXT),
    )

    assert fact.raw_values == (raw_nfd,)
    assert fact.display_value == "Medellín"
    assert fact.normalized_values == ("medellín",)


def test_hash_uses_renderer_canonical_soql_verbatim() -> None:
    fact_spec = spec(TextualFactOperation.DIRECT_TEXT)
    first = evaluate_textual_operation(
        evidence=evidence(
            ({"municipio": "Medellín"},),
            canonical_soql="SELECT municipio LIMIT 1000 OFFSET 0",
        ),
        spec=fact_spec,
    )
    second = evaluate_textual_operation(
        evidence=evidence(
            ({"municipio": "Medellín"},),
            canonical_soql="SELECT  municipio LIMIT 1000 OFFSET 0",
        ),
        spec=fact_spec,
    )

    assert first.source_hash != second.source_hash


def test_hash_changes_for_each_semantic_material_change() -> None:
    base_evidence = evidence(
        ({"municipio": "Medellín", "otra": "x"},),
        canonical_soql="SELECT municipio LIMIT 1000 OFFSET 0",
    )
    base_spec = spec(TextualFactOperation.DIRECT_TEXT)
    base = evaluate_textual_operation(evidence=base_evidence, spec=base_spec)

    variants = (
        (
            replace(base_evidence, dataset_id="wxyz-9876"),
            base_spec,
        ),
        (
            replace(base_evidence, canonical_soql="SELECT municipio LIMIT 1 OFFSET 0"),
            base_spec,
        ),
        (
            replace(base_evidence, rows=({"municipio": "Bogotá", "otra": "x"},)),
            base_spec,
        ),
        (
            replace(base_evidence, rows=({"municipio": "Medellín", "otra": "Y"},)),
            spec(TextualFactOperation.DIRECT_TEXT, columns=("otra",)),
        ),
        (
            replace(base_evidence, rows=({"municipio": "MEDELLÍN", "otra": "x"},)),
            base_spec,
        ),
        (
            replace(base_evidence, rows=({"municipio": "Medellín", "otra": "x"},)),
            spec(TextualFactOperation.CANONICAL_TEXT_SET),
        ),
    )
    hashes = {
        evaluate_textual_operation(evidence=item_evidence, spec=item_spec).source_hash
        for item_evidence, item_spec in variants
    }

    assert base.source_hash not in hashes
    assert len(hashes) == len(variants)


def test_hash_ignores_rows_and_columns_outside_the_declared_source_subset() -> None:
    fact_spec = spec(TextualFactOperation.DIRECT_TEXT)
    first = evaluate_textual_operation(
        evidence=evidence(
            (
                {"municipio": "Medellín", "sin_usar": "A"},
                {"municipio": "Bogotá", "sin_usar": "B"},
            )
        ),
        spec=fact_spec,
    )
    changed_outside_subset = evaluate_textual_operation(
        evidence=evidence(
            (
                {"sin_usar": "CAMBIÓ", "municipio": "Medellín"},
                {"municipio": "Cali", "sin_usar": "OTRO"},
            )
        ),
        spec=fact_spec,
    )

    assert first.source_hash == changed_outside_subset.source_hash


def test_hash_changes_when_value_presence_parameter_changes() -> None:
    source = evidence(({"municipio": "Medellín"}, {"municipio": "Bogotá"}))
    medellin = evaluate_textual_operation(
        evidence=source,
        spec=spec(
            TextualFactOperation.VALUE_PRESENCE,
            indexes=(0, 1),
            params=ValuePresenceParams(target_raw="Medellín", target_normalized="medellín"),
        ),
    )
    bogota = evaluate_textual_operation(
        evidence=source,
        spec=spec(
            TextualFactOperation.VALUE_PRESENCE,
            indexes=(1, 0),
            params=ValuePresenceParams(target_raw="Bogotá", target_normalized="bogotá"),
        ),
    )

    assert medellin.source_hash != bogota.source_hash
