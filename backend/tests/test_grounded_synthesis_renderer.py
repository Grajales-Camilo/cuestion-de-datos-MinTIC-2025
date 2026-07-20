from __future__ import annotations

import uuid

import pytest

from app.quality.grounded_facts import GroundedSynthesisPlan
from app.quality.grounded_synthesis import (
    AllowedGroundedFacts,
    AllowedQuantitativeFact,
    AllowedTextualFact,
    GroundedSynthesisValidationError,
    build_grounded_synthesis_fallback,
    render_grounded_synthesis,
    validate_grounded_synthesis_plan,
)

RUN_ID = uuid.UUID("10000000-0000-0000-0000-000000000001")
EVIDENCE_ID = uuid.UUID("20000000-0000-0000-0000-000000000001")
OTHER_EVIDENCE_ID = uuid.UUID("20000000-0000-0000-0000-000000000002")
CLAIM_ID = uuid.UUID("30000000-0000-0000-0000-000000000001")
FACT_ID = uuid.UUID("40000000-0000-0000-0000-000000000001")


def quantitative_fact(
    *,
    fact_id: uuid.UUID = CLAIM_ID,
    evidence_id: uuid.UUID = EVIDENCE_ID,
    dataset_id: str = "abcd-1234",
    source_row_indexes: tuple[int, ...] = (0,),
    columns: tuple[str, ...] = ("total",),
    source_hash: str = f"sha256:{'1' * 64}",
    quality_classification: str = "alta",
    label: str | None = "Total de registros",
    label_status: str = "verified",
) -> AllowedQuantitativeFact:
    return AllowedQuantitativeFact(
        id=fact_id,
        run_id=RUN_ID,
        evidence_id=evidence_id,
        dataset_id=dataset_id,
        source_row_indexes=source_row_indexes,
        columns=columns,
        source_hash=source_hash,
        claim="Total de registros",
        display_value="25",
        quality_classification=quality_classification,
        label=label,
        label_status=label_status,
    )


def textual_fact(
    *,
    fact_id: uuid.UUID = FACT_ID,
    evidence_id: uuid.UUID = EVIDENCE_ID,
    dataset_id: str = "abcd-1234",
    source_row_indexes: tuple[int, ...] = (1,),
    columns: tuple[str, ...] = ("categoria",),
    source_hash: str = f"sha256-jcs-v1:{'2' * 64}",
    quality_classification: str = "alta",
) -> AllowedTextualFact:
    return AllowedTextualFact(
        id=fact_id,
        run_id=RUN_ID,
        evidence_id=evidence_id,
        dataset_id=dataset_id,
        source_row_indexes=source_row_indexes,
        columns=columns,
        source_hash=source_hash,
        fact="La categoría seleccionada es Salud.",
        quality_classification=quality_classification,
    )


def plan(
    *,
    template: str,
    refs: list[dict[str, str]],
    connector: str = "sin_conector",
    closing: str = "sin_cierre",
) -> GroundedSynthesisPlan:
    return GroundedSynthesisPlan.model_validate(
        {
            "schema_version": "grounded-synthesis-plan-v1",
            "segments": [
                {
                    "segment_id": "s1",
                    "connector": connector,
                    "template": template,
                    "fact_refs": refs,
                }
            ],
            "closing": closing,
        }
    )


def test_literal_renderer_matches_the_three_approved_snapshots() -> None:
    allowed = AllowedGroundedFacts(
        run_id=RUN_ID,
        facts=(quantitative_fact(), textual_fact()),
    )

    quantitative = plan(
        template="fact_statement",
        refs=[{"fact_kind": "quantitative", "id": str(CLAIM_ID)}],
    )
    textual = plan(
        template="fact_statement",
        refs=[{"fact_kind": "textual", "id": str(FACT_ID)}],
    )
    mixed = plan(
        template="comparison_pair",
        refs=[
            {"fact_kind": "quantitative", "id": str(CLAIM_ID)},
            {"fact_kind": "textual", "id": str(FACT_ID)},
        ],
    )

    assert render_grounded_synthesis(quantitative, allowed) == "Total de registros: 25."
    assert render_grounded_synthesis(textual, allowed) == "La categoría seleccionada es Salud."
    assert render_grounded_synthesis(mixed, allowed) == (
        "Resultados relacionados: Total de registros: 25. La categoría seleccionada es Salud."
    )


def test_literal_renderer_preserves_verified_textual_identifier_exactly() -> None:
    exact_identifier = textual_fact().model_copy(
        update={
            "display_value": "05001",
            "label": "Cod mpio",
            "label_status": "verified",
        }
    )
    allowed = AllowedGroundedFacts(run_id=RUN_ID, facts=(exact_identifier,))
    textual = plan(
        template="fact_statement",
        refs=[{"fact_kind": "textual", "id": str(FACT_ID)}],
    )

    assert render_grounded_synthesis(textual, allowed) == "Cod mpio: 05001."


def test_literal_renderer_keeps_legacy_text_when_label_is_ambiguous() -> None:
    ambiguous = textual_fact().model_copy(
        update={"display_value": "05001", "label": None, "label_status": "ambiguous"}
    )
    allowed = AllowedGroundedFacts(run_id=RUN_ID, facts=(ambiguous,))
    textual = plan(
        template="fact_statement",
        refs=[{"fact_kind": "textual", "id": str(FACT_ID)}],
    )

    assert render_grounded_synthesis(textual, allowed) == ("La categoría seleccionada es Salud.")


@pytest.mark.parametrize(
    ("facts", "refs"),
    (
        (
            (
                quantitative_fact(),
                quantitative_fact(
                    fact_id=uuid.UUID("30000000-0000-0000-0000-000000000002"),
                    source_row_indexes=(1,),
                    source_hash=f"sha256:{'3' * 64}",
                ),
            ),
            (
                ("quantitative", CLAIM_ID),
                (
                    "quantitative",
                    uuid.UUID("30000000-0000-0000-0000-000000000002"),
                ),
            ),
        ),
        (
            (
                textual_fact(),
                textual_fact(
                    fact_id=uuid.UUID("40000000-0000-0000-0000-000000000002"),
                    source_row_indexes=(2,),
                    source_hash=f"sha256-jcs-v1:{'4' * 64}",
                ),
            ),
            (
                ("textual", FACT_ID),
                (
                    "textual",
                    uuid.UUID("40000000-0000-0000-0000-000000000002"),
                ),
            ),
        ),
        (
            (quantitative_fact(), textual_fact()),
            (("quantitative", CLAIM_ID), ("textual", FACT_ID)),
        ),
    ),
)
def test_comparison_pair_accepts_quantitative_textual_and_mixed_pairs(
    facts,
    refs,
) -> None:
    allowed = AllowedGroundedFacts(run_id=RUN_ID, facts=facts)
    synthesis = plan(
        template="comparison_pair",
        refs=[{"fact_kind": fact_kind, "id": str(fact_id)} for fact_kind, fact_id in refs],
    )

    validate_grounded_synthesis_plan(synthesis, allowed)
    assert render_grounded_synthesis(synthesis, allowed).startswith("Resultados relacionados: ")


def test_renderer_applies_only_approved_templates_connectors_and_closings() -> None:
    allowed = AllowedGroundedFacts(
        run_id=RUN_ID,
        facts=(quantitative_fact(), textual_fact()),
    )
    synthesis = GroundedSynthesisPlan.model_validate(
        {
            "schema_version": "grounded-synthesis-plan-v1",
            "segments": [
                {
                    "segment_id": "s1",
                    "connector": "sin_conector",
                    "template": "subject_fact",
                    "fact_refs": [{"fact_kind": "quantitative", "id": str(CLAIM_ID)}],
                },
                {
                    "segment_id": "s2",
                    "connector": "por_otra_parte",
                    "template": "fact_statement",
                    "fact_refs": [{"fact_kind": "textual", "id": str(FACT_ID)}],
                },
            ],
            "closing": "advertencia_calidad",
        }
    )

    assert render_grounded_synthesis(synthesis, allowed) == (
        "Resultado verificado: Total de registros: 25. "
        "Por otra parte, La categoría seleccionada es Salud. "
        "La evidencia utilizada presenta una advertencia de calidad."
    )


@pytest.mark.parametrize(
    ("connector", "literal"),
    (
        ("ademas", "Además, "),
        ("por_otra_parte", "Por otra parte, "),
        ("en_conjunto", "En conjunto, "),
    ),
)
def test_renderer_snapshots_every_approved_explicit_connector(
    connector: str,
    literal: str,
) -> None:
    allowed = AllowedGroundedFacts(
        run_id=RUN_ID,
        facts=(quantitative_fact(), textual_fact()),
    )
    synthesis = GroundedSynthesisPlan.model_validate(
        {
            "schema_version": "grounded-synthesis-plan-v1",
            "segments": [
                {
                    "segment_id": "s1",
                    "connector": "sin_conector",
                    "template": "fact_statement",
                    "fact_refs": [{"fact_kind": "quantitative", "id": str(CLAIM_ID)}],
                },
                {
                    "segment_id": "s2",
                    "connector": connector,
                    "template": "fact_statement",
                    "fact_refs": [{"fact_kind": "textual", "id": str(FACT_ID)}],
                },
            ],
            "closing": "sin_cierre",
        }
    )

    assert render_grounded_synthesis(synthesis, allowed) == (
        f"Total de registros: 25. {literal}La categoría seleccionada es Salud."
    )


@pytest.mark.parametrize(
    ("closing", "literal"),
    (
        ("sin_cierre", ""),
        (
            "limitacion_disponibilidad",
            " La respuesta se limita a la evidencia disponible.",
        ),
        (
            "advertencia_calidad",
            " La evidencia utilizada presenta una advertencia de calidad.",
        ),
    ),
)
def test_renderer_snapshots_every_approved_closing(
    closing: str,
    literal: str,
) -> None:
    allowed = AllowedGroundedFacts(run_id=RUN_ID, facts=(quantitative_fact(),))
    synthesis = plan(
        template="fact_statement",
        refs=[{"fact_kind": "quantitative", "id": str(CLAIM_ID)}],
        closing=closing,
    )

    assert render_grounded_synthesis(synthesis, allowed) == f"Total de registros: 25.{literal}"


@pytest.mark.parametrize(
    ("first_connector", "second_connector"),
    (("ademas", "por_otra_parte"), ("sin_conector", "sin_conector")),
)
def test_validator_rejects_invalid_connector_positions(
    first_connector: str,
    second_connector: str,
) -> None:
    allowed = AllowedGroundedFacts(
        run_id=RUN_ID,
        facts=(quantitative_fact(), textual_fact()),
    )
    synthesis = GroundedSynthesisPlan.model_validate(
        {
            "schema_version": "grounded-synthesis-plan-v1",
            "segments": [
                {
                    "segment_id": "s1",
                    "connector": first_connector,
                    "template": "fact_statement",
                    "fact_refs": [{"fact_kind": "quantitative", "id": str(CLAIM_ID)}],
                },
                {
                    "segment_id": "s2",
                    "connector": second_connector,
                    "template": "fact_statement",
                    "fact_refs": [{"fact_kind": "textual", "id": str(FACT_ID)}],
                },
            ],
            "closing": "sin_cierre",
        }
    )

    with pytest.raises(GroundedSynthesisValidationError, match="conector"):
        validate_grounded_synthesis_plan(synthesis, allowed)


def test_validator_rejects_unknown_kind_mismatch_and_incompatible_pair() -> None:
    allowed = AllowedGroundedFacts(
        run_id=RUN_ID,
        facts=(quantitative_fact(), textual_fact(evidence_id=OTHER_EVIDENCE_ID)),
    )
    unknown = plan(
        template="fact_statement",
        refs=[
            {
                "fact_kind": "quantitative",
                "id": "30000000-0000-0000-0000-000000000099",
            }
        ],
    )
    kind_mismatch = plan(
        template="fact_statement",
        refs=[{"fact_kind": "textual", "id": str(CLAIM_ID)}],
    )
    incompatible_pair = plan(
        template="comparison_pair",
        refs=[
            {"fact_kind": "quantitative", "id": str(CLAIM_ID)},
            {"fact_kind": "textual", "id": str(FACT_ID)},
        ],
    )

    with pytest.raises(GroundedSynthesisValidationError, match="no autorizada"):
        validate_grounded_synthesis_plan(unknown, allowed)
    with pytest.raises(GroundedSynthesisValidationError, match="no autorizada"):
        validate_grounded_synthesis_plan(kind_mismatch, allowed)
    with pytest.raises(GroundedSynthesisValidationError, match="misma evidencia"):
        validate_grounded_synthesis_plan(incompatible_pair, allowed)


def test_fallback_has_exact_order_limit_and_closing_precedence() -> None:
    facts = []
    for index in range(9):
        facts.append(
            textual_fact(
                fact_id=uuid.UUID(int=100 + index),
                dataset_id=f"ab{index:02d}-1234",
                source_row_indexes=(index,),
                source_hash=f"sha256-jcs-v1:{index + 1:064x}",
                quality_classification="baja",
            )
        )
    facts.append(
        quantitative_fact(
            fact_id=uuid.UUID(int=99),
            dataset_id="zzzz-9999",
            source_hash=f"sha256:{99:064x}",
        )
    )
    allowed = AllowedGroundedFacts(run_id=RUN_ID, facts=tuple(reversed(facts)))

    fallback = build_grounded_synthesis_fallback(allowed)

    assert len(fallback.segments) == 8
    assert fallback.closing.value == "limitacion_disponibilidad"
    assert fallback.segments[0].fact_refs[0].fact_kind == "quantitative"
    assert fallback.segments[0].connector.value == "sin_conector"
    assert all(segment.connector.value == "ademas" for segment in fallback.segments[1:])
    validate_grounded_synthesis_plan(fallback, allowed)


def test_fallback_uses_quality_warning_and_rejects_empty_allowed_set() -> None:
    allowed = AllowedGroundedFacts(
        run_id=RUN_ID,
        facts=(textual_fact(quality_classification="baja"),),
    )

    fallback = build_grounded_synthesis_fallback(allowed)

    assert fallback.closing.value == "advertencia_calidad"
    with pytest.raises(GroundedSynthesisValidationError, match="ningún hecho"):
        build_grounded_synthesis_fallback(AllowedGroundedFacts(run_id=RUN_ID, facts=()))


# --- RF-212 (T-617C-R1): relevancia y etiquetado del fallback T-615H ---------


def test_fallback_excludes_auxiliary_column_by_default() -> None:
    """El fallback estructural (flag textual activo) también prioriza
    columnas relevantes: un identificador auxiliar no solicitado no debe
    ser el único hecho renderizado si hay una alternativa relevante."""

    relevant = quantitative_fact(
        fact_id=uuid.UUID(int=1),
        columns=("cantidad_empleados",),
        label="Cantidad empleados",
        label_status="verified",
    )
    auxiliary = quantitative_fact(
        fact_id=uuid.UUID(int=2),
        source_hash=f"sha256:{2:064x}",
        columns=("codigo_interno",),
        label="Codigo interno",
        label_status="verified",
    )
    allowed = AllowedGroundedFacts(run_id=RUN_ID, facts=(relevant, auxiliary))

    fallback = build_grounded_synthesis_fallback(allowed, requested_tokens=frozenset())
    cited_ids = {ref.id for segment in fallback.segments for ref in segment.fact_refs}

    assert relevant.id in cited_ids
    assert auxiliary.id not in cited_ids


def test_fallback_includes_auxiliary_column_when_explicitly_requested() -> None:
    auxiliary = quantitative_fact(
        fact_id=uuid.UUID(int=2),
        columns=("codigo_interno",),
        label="Codigo interno",
        label_status="verified",
    )
    allowed = AllowedGroundedFacts(run_id=RUN_ID, facts=(auxiliary,))

    fallback = build_grounded_synthesis_fallback(
        allowed, requested_tokens=frozenset({"codigo", "interno"})
    )
    cited_ids = {ref.id for segment in fallback.segments for ref in segment.fact_refs}

    assert auxiliary.id in cited_ids


def test_fallback_renders_labeled_text_and_flags_ambiguous_without_inventing() -> None:
    ambiguous = quantitative_fact(label=None, label_status="ambiguous")
    allowed = AllowedGroundedFacts(run_id=RUN_ID, facts=(ambiguous,))

    fallback = build_grounded_synthesis_fallback(allowed)
    text = render_grounded_synthesis(fallback, allowed)

    assert "sin etiqueta verificable" in text
    assert "Total de registros" not in text
