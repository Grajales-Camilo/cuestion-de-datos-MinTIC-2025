"""Nodo determinista T7 (contracts/agent-tools.md §T7, pruebas.md §2.1, test_claims.py)."""

from decimal import Decimal

from app.quality.claims import (
    ClaimSpec,
    EvidenceContext,
    build_claims,
    compute_source_hash,
    find_figures,
    find_orphan_figures,
    format_es_co,
)

EVIDENCE = EvidenceContext(
    dataset_id="nudc-7mev",
    canonical_soql="SELECT a_o, matriculados, desertores GROUP BY a_o LIMIT 1000 OFFSET 0",
    rows=(
        {"a_o": "2025", "matriculados": "1000", "desertores": "84"},
        {"a_o": "2024", "matriculados": "950", "desertores": "76"},
    ),
)


def spec(**overrides: object) -> ClaimSpec:
    defaults: dict[str, object] = {
        "claim_type": "direct",
        "description": "Matriculados 2025",
        "source_row_indexes": (0,),
        "columns": ("matriculados",),
        "unit": "personas",
        "rounding": 0,
        "formula": None,
    }
    defaults.update(overrides)
    return ClaimSpec(**defaults)


# --- Claim direct ------------------------------------------------------------


def test_direct_claim_takes_exact_cell_value_with_es_co_format() -> None:
    result = build_claims(EVIDENCE, [spec()])

    assert result.rejected == ()
    assert len(result.claims) == 1
    claim = result.claims[0]
    assert claim.raw_value == Decimal("1000")
    assert claim.display_value == "1.000 personas"
    assert claim.columns_used == ("matriculados",)


def test_direct_claim_parses_thousands_separator_from_text_column() -> None:
    """Regresión real (pilot-004-justicia-presupuesto, dataset `f4a5-ab9q`,
    confirmado contra Socrata real): la fuente publica columnas monetarias
    como texto con coma de miles ("3,893,283,514,468.00"). Antes de este fix
    `Decimal(...)` rechazaba el valor como "no numérico" pese a que la fila
    y la columna eran exactamente las correctas -- empujando al router a
    intentar CAST/TO_NUMBER en el SoQL, ninguno permitido (SOQL_FORBIDDEN)."""
    evidence = EvidenceContext(
        dataset_id="f4a5-ab9q",
        canonical_soql=(
            "SELECT entidad, descripci_n, apropiaci_n_vigente WHERE a_o='2023' "
            "AND entidad='sector justicia' AND descripci_n='Funcionamiento' "
            "LIMIT 1000 OFFSET 0"
        ),
        rows=({"entidad": "sector justicia", "apropiaci_n_vigente": "3,893,283,514,468.00"},),
    )

    result = build_claims(
        evidence,
        [
            spec(
                description="Apropiación vigente sector Justicia 2023",
                columns=("apropiaci_n_vigente",),
                unit="COP",
                rounding=0,
            )
        ],
    )

    assert result.rejected == ()
    assert len(result.claims) == 1
    assert result.claims[0].raw_value == Decimal("3893283514468.00")


def test_direct_claim_rejects_more_than_one_row_or_column() -> None:
    result = build_claims(
        EVIDENCE,
        [spec(source_row_indexes=(0, 1), columns=("matriculados",))],
    )

    assert result.claims == ()
    assert "una fila" in result.rejected[0].reason


# --- Claim derived -------------------------------------------------------------


def test_derived_claim_division_and_percentage_reproduces_raw_value() -> None:
    formula = {
        "op": "mul",
        "args": [
            {"op": "div", "args": [{"col": "desertores"}, {"col": "matriculados"}]},
            {"const": 100},
        ],
    }
    result = build_claims(
        EVIDENCE,
        [
            spec(
                claim_type="derived",
                description="Tasa de deserción 2025",
                source_row_indexes=(0,),
                columns=("matriculados", "desertores"),
                unit="%",
                rounding=1,
                formula=formula,
            )
        ],
    )

    assert result.rejected == ()
    claim = result.claims[0]
    assert claim.raw_value == Decimal("8.4")
    assert claim.display_value == "8,4 %"
    assert claim.columns_used == ("desertores", "matriculados")


def test_derived_claim_col_resolves_across_multiple_rows_when_unambiguous() -> None:
    """Ejemplo literal de agent-tools.md §T7: source_row_indexes=[0,1] con 'col'
    simple funciona cuando cada columna tiene un unico valor no nulo entre las
    filas referenciadas (decision de diseno documentada en claims.py)."""
    evidence = EvidenceContext(
        dataset_id="nudc-7mev",
        canonical_soql="SELECT matriculados, desertores LIMIT 1000 OFFSET 0",
        rows=(
            {"matriculados": "1000", "desertores": None},
            {"matriculados": None, "desertores": "84"},
        ),
    )
    formula = {
        "op": "mul",
        "args": [
            {"op": "div", "args": [{"col": "desertores"}, {"col": "matriculados"}]},
            {"const": 100},
        ],
    }
    result = build_claims(
        evidence,
        [
            spec(
                claim_type="derived",
                description="Tasa de deserción 2025",
                source_row_indexes=(0, 1),
                columns=("matriculados", "desertores"),
                unit="%",
                rounding=1,
                formula=formula,
            )
        ],
    )

    assert result.rejected == ()
    assert result.claims[0].raw_value == Decimal("8.4")


def test_derived_claim_col_ambiguous_across_rows_requires_agg() -> None:
    result = build_claims(
        EVIDENCE,
        [
            spec(
                claim_type="derived",
                description="Matriculados ambiguos",
                source_row_indexes=(0, 1),
                columns=("matriculados",),
                formula={"col": "matriculados"},
            )
        ],
    )

    assert result.claims == ()
    assert "agg" in result.rejected[0].reason


def test_derived_claim_sum_and_avg_aggregation() -> None:
    result = build_claims(
        EVIDENCE,
        [
            spec(
                claim_type="derived",
                description="Total matriculados",
                source_row_indexes=(0, 1),
                columns=("matriculados",),
                unit="personas",
                rounding=0,
                formula={"agg": "sum", "col": "matriculados"},
            ),
            spec(
                claim_type="derived",
                description="Promedio matriculados",
                source_row_indexes=(0, 1),
                columns=("matriculados",),
                unit="personas",
                rounding=1,
                formula={"agg": "avg", "col": "matriculados"},
            ),
        ],
    )

    assert result.rejected == ()
    assert result.claims[0].raw_value == Decimal("1950")
    assert result.claims[1].raw_value == Decimal("975")


# --- Rechazos ------------------------------------------------------------------


def test_rejects_nonexistent_column() -> None:
    result = build_claims(
        EVIDENCE, [spec(claim_type="direct", columns=("no_existe",), source_row_indexes=(0,))]
    )

    assert result.claims == ()
    assert "no existe" in result.rejected[0].reason


def test_rejects_non_numeric_operand() -> None:
    evidence = EvidenceContext(
        dataset_id="nudc-7mev",
        canonical_soql="SELECT estado LIMIT 1000 OFFSET 0",
        rows=({"estado": "Finalizado"},),
    )
    result = build_claims(
        evidence, [spec(claim_type="direct", columns=("estado",), source_row_indexes=(0,))]
    )

    assert result.claims == ()
    assert "no numérico" in result.rejected[0].reason


def test_rejects_null_operand() -> None:
    evidence = EvidenceContext(
        dataset_id="nudc-7mev",
        canonical_soql="SELECT matriculados LIMIT 1000 OFFSET 0",
        rows=({"matriculados": None},),
    )
    result = build_claims(
        evidence, [spec(claim_type="direct", columns=("matriculados",), source_row_indexes=(0,))]
    )

    assert result.claims == ()
    assert "operando nulo" in result.rejected[0].reason


def test_rejects_division_by_zero() -> None:
    evidence = EvidenceContext(
        dataset_id="nudc-7mev",
        canonical_soql="SELECT matriculados, desertores LIMIT 1000 OFFSET 0",
        rows=({"matriculados": "0", "desertores": "10"},),
    )
    result = build_claims(
        evidence,
        [
            spec(
                claim_type="derived",
                columns=("matriculados", "desertores"),
                source_row_indexes=(0,),
                formula={"op": "div", "args": [{"col": "desertores"}, {"col": "matriculados"}]},
            )
        ],
    )

    assert result.claims == ()
    assert "división por cero" in result.rejected[0].reason


def test_rejects_disallowed_dsl_operation() -> None:
    result = build_claims(
        EVIDENCE,
        [
            spec(
                claim_type="derived",
                columns=("matriculados",),
                source_row_indexes=(0,),
                formula={"op": "exec", "args": [{"col": "matriculados"}, {"const": 1}]},
            )
        ],
    )

    assert result.claims == ()
    assert "no permitida" in result.rejected[0].reason


def test_rejects_disallowed_agg_function() -> None:
    result = build_claims(
        EVIDENCE,
        [
            spec(
                claim_type="derived",
                columns=("matriculados",),
                source_row_indexes=(0,),
                formula={"agg": "median", "col": "matriculados"},
            )
        ],
    )

    assert result.claims == ()
    assert "no permitida" in result.rejected[0].reason


def test_rejects_unknown_column_in_dsl_lookup() -> None:
    result = build_claims(
        EVIDENCE,
        [
            spec(
                claim_type="derived",
                columns=("matriculados",),
                source_row_indexes=(0,),
                formula={"col": "no_declarada"},
            )
        ],
    )

    assert result.claims == ()
    assert "no está declarada" in result.rejected[0].reason


# --- Formato es-CO -------------------------------------------------------------


def test_format_es_co_matches_literal_contract_example() -> None:
    assert format_es_co(Decimal("8.3721"), 1, "%") == "8,4 %"


def test_format_es_co_thousands_separator() -> None:
    assert format_es_co(Decimal("15230"), 0, "personas") == "15.230 personas"


def test_format_es_co_without_unit() -> None:
    assert format_es_co(Decimal("42"), 0, None) == "42"


# --- source_hash: determinismo y estabilidad ------------------------------------


def _hash_for(**overrides: object) -> str:
    defaults: dict[str, object] = {
        "dataset_id": "nudc-7mev",
        "canonical_soql": "SELECT matriculados LIMIT 1000 OFFSET 0",
        "source_row_indexes": (0,),
        "rows": ({"matriculados": "1000"},),
        "columns": ("matriculados",),
        "formula": None,
        "raw_value": Decimal("1000"),
        "unit": "personas",
        "rounding": 0,
    }
    defaults.update(overrides)
    return compute_source_hash(**defaults)


def test_source_hash_stable_across_runs_with_same_content() -> None:
    assert _hash_for() == _hash_for()


def test_source_hash_changes_with_formula() -> None:
    assert _hash_for(formula=None) != _hash_for(formula={"const": 1})


def test_source_hash_changes_with_row_content() -> None:
    base = _hash_for()
    changed = _hash_for(rows=({"matriculados": "2000"},))
    assert base != changed


def test_source_hash_changes_with_raw_value_unit_rounding() -> None:
    base = _hash_for()
    assert base != _hash_for(raw_value=Decimal("1001"))
    assert base != _hash_for(unit="casos")
    assert base != _hash_for(rounding=1)


def test_source_hash_reorder_of_source_row_indexes_is_not_semantically_relevant() -> None:
    """Bajo este DSL, `col`/`agg` no dependen de la posicion de los indices: el
    orden en que se declaran `source_row_indexes` no cambia raw_value, por lo
    que la canonicalizacion ascendente produce el mismo hash (decision
    documentada en claims.py, punto 3)."""
    rows = ({"matriculados": "1000"}, {"matriculados": "2000"})
    ascending = compute_source_hash(
        dataset_id="nudc-7mev",
        canonical_soql="SELECT matriculados LIMIT 1000 OFFSET 0",
        source_row_indexes=(0, 1),
        rows=rows,
        columns=("matriculados",),
        formula={"agg": "sum", "col": "matriculados"},
        raw_value=Decimal("3000"),
        unit="personas",
        rounding=0,
    )
    descending_input = compute_source_hash(
        dataset_id="nudc-7mev",
        canonical_soql="SELECT matriculados LIMIT 1000 OFFSET 0",
        source_row_indexes=(1, 0),
        rows=rows,
        columns=("matriculados",),
        formula={"agg": "sum", "col": "matriculados"},
        raw_value=Decimal("3000"),
        unit="personas",
        rounding=0,
    )
    assert ascending == descending_input


def test_source_hash_changing_referenced_indexes_changes_hash() -> None:
    rows = ({"matriculados": "1000"}, {"matriculados": "2000"})
    only_first = compute_source_hash(
        dataset_id="nudc-7mev",
        canonical_soql="SELECT matriculados LIMIT 1000 OFFSET 0",
        source_row_indexes=(0,),
        rows=rows,
        columns=("matriculados",),
        formula=None,
        raw_value=Decimal("1000"),
        unit="personas",
        rounding=0,
    )
    both = compute_source_hash(
        dataset_id="nudc-7mev",
        canonical_soql="SELECT matriculados LIMIT 1000 OFFSET 0",
        source_row_indexes=(0, 1),
        rows=rows,
        columns=("matriculados",),
        formula=None,
        raw_value=Decimal("1000"),
        unit="personas",
        rounding=0,
    )
    assert only_first != both


def test_source_hash_does_not_take_run_evidence_or_claim_ids() -> None:
    """compute_source_hash no recibe run_id/evidence_id/claim_id como parametro:
    dos corridas independientes de build_claims con el mismo contenido producen
    el mismo source_hash, simulando IDs de corrida/evidencia/claim distintos."""
    result_run_a = build_claims(EVIDENCE, [spec()])
    result_run_b = build_claims(EVIDENCE, [spec()])

    assert result_run_a.claims[0].source_hash == result_run_b.claims[0].source_hash


# --- Detector de cifras huerfanas ------------------------------------------------


def test_find_figures_covers_normative_definition() -> None:
    text = (
        "Se matricularon 1.000 personas, la tasa fue 8,4 % con un costo de $50.000 "
        "y un rango de 10-20 casos en 2025."
    )
    figures = find_figures(text)

    assert "1.000" in figures
    assert "8,4 %" in figures
    assert "$50.000" in figures
    assert "10" in figures
    assert "20" in figures
    assert "2025" in figures


def test_find_figures_excludes_technical_ids_and_dates() -> None:
    text = (
        "El dataset 2d3i-f9wd (uuid 9a2b1234-5678-41d4-a716-446655440000) fue "
        "citado el 6 de julio de 2026 (2026-07-06); el municipio tiene código "
        "05148 y ver sección 3 del anexo."
    )
    figures = find_figures(text)

    assert not any(figure in ("2d3i", "f9wd") for figure in figures)
    assert "2026" not in figures
    assert "05148" not in figures
    assert "3" not in figures


def test_find_orphan_figures_detects_unbacked_figure() -> None:
    text = "La tasa de deserción fue 8,4 %."
    orphans = find_orphan_figures(text, accepted_display_values=["5,0 %"])

    assert orphans == ("8,4 %",)


def test_find_orphan_figures_accepts_backed_figure() -> None:
    text = "La tasa de deserción fue 8,4 %."
    orphans = find_orphan_figures(text, accepted_display_values=["8,4 %"])

    assert orphans == ()


def test_find_orphan_figures_negative_case_no_figures_at_all() -> None:
    text = "No se encontró evidencia suficiente para responder esta pregunta."
    orphans = find_orphan_figures(text, accepted_display_values=[])

    assert orphans == ()


# --- Determinismo general -------------------------------------------------------


def test_same_rows_and_spec_produce_same_claim() -> None:
    result_a = build_claims(EVIDENCE, [spec()])
    result_b = build_claims(EVIDENCE, [spec()])

    assert result_a.claims[0].raw_value == result_b.claims[0].raw_value
    assert result_a.claims[0].display_value == result_b.claims[0].display_value
    assert result_a.claims[0].source_hash == result_b.claims[0].source_hash
