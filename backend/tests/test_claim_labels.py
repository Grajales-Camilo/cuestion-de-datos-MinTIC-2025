"""RF-212 (T-617C): etiquetado semántico y advertencias de presentación.

Fixtures genéricos: ningún caso usa `case_id`, `dataset_id` ni valores de
`pilot-005` (764/719/Ministerio de Relaciones Exteriores) como condición.
"""

from __future__ import annotations

from app.quality.claim_labels import (
    build_presentation_warnings,
    claim_is_relevant_to_narrative,
    classify_column_relevance,
    derive_claim_label,
    humanize_field_name,
    intent_relevance_tokens,
    label_grounded_in_text,
    looks_like_internal_alias,
)

# --- humanize_field_name / derive_claim_label --------------------------------


def test_humanize_field_name_derives_from_real_column_name() -> None:
    assert humanize_field_name("cantidad_empleados") == "Cantidad empleados"


def test_humanize_field_name_rejects_internal_alias_shapes() -> None:
    assert humanize_field_name("dim_2") is None
    assert humanize_field_name("metric_sum_1") is None
    # "group_count" es en sí mismo un alias interno (soql_renderer.py); solo
    # el centinela __count__ (a donde se traduce ese alias antes de llegar
    # aquí) produce la etiqueta estructural fija.
    assert humanize_field_name("group_count") is None
    assert humanize_field_name("__count__") == "Conteo de registros"


def test_derive_claim_label_single_column_is_verified() -> None:
    label, status = derive_claim_label(("cantidad_empleados",))
    assert status == "verified"
    assert label == "Cantidad empleados"


def test_derive_claim_label_multiple_distinct_columns_is_ambiguous() -> None:
    """Un claim `derived` que combina columnas distintas no recibe una
    etiqueta inventada que mezcle ambas."""

    label, status = derive_claim_label(("matriculados", "desertores"))
    assert label is None
    assert status == "ambiguous"


def test_derive_claim_label_unsafe_field_name_is_ambiguous() -> None:
    label, status = derive_claim_label(("Columna Con Espacios!",))
    assert label is None
    assert status == "ambiguous"


def test_derive_claim_label_never_leaks_internal_alias_as_label() -> None:
    """Si por error llegara un alias interno como 'columna real', no se
    humaniza como si fuera un nombre legítimo (regresión directa)."""

    label, status = derive_claim_label(("dim_3",))
    assert label is None
    assert status == "ambiguous"
    assert not looks_like_internal_alias("cantidad_empleados")
    assert looks_like_internal_alias("dim_3")
    assert looks_like_internal_alias("metric_avg_2")
    assert looks_like_internal_alias("group_count")


# --- classify_column_relevance / claim_is_relevant_to_narrative --------------


def test_classify_column_relevance_generic_categories() -> None:
    assert classify_column_relevance("cantidad_empleados") == "primary"
    assert classify_column_relevance("codigo_interno") == "auxiliary"
    assert classify_column_relevance("nit_proveedor") == "auxiliary"
    assert classify_column_relevance("fecha_reporte") == "temporal"
    assert classify_column_relevance("anio_vigencia") == "temporal"
    assert classify_column_relevance("__count__") == "primary"


def test_relevant_claim_included_by_default() -> None:
    tokens = intent_relevance_tokens("composición del personal", ())
    assert claim_is_relevant_to_narrative(("cantidad_empleados",), requested_tokens=tokens)


def test_auxiliary_identifier_excluded_unless_requested() -> None:
    tokens = intent_relevance_tokens("cantidad de proveedores activos", ())
    assert not claim_is_relevant_to_narrative(("codigo_interno",), requested_tokens=tokens)

    requested = intent_relevance_tokens("cuál es el código interno del proveedor", ())
    assert claim_is_relevant_to_narrative(("codigo_interno",), requested_tokens=requested)


def test_temporal_column_excluded_unless_requested() -> None:
    tokens = intent_relevance_tokens("cantidad de proveedores activos", ())
    assert not claim_is_relevant_to_narrative(("anio_vigencia",), requested_tokens=tokens)

    requested = intent_relevance_tokens("en qué año se reportó", ())
    assert claim_is_relevant_to_narrative(("anio_vigencia",), requested_tokens=requested)


def test_ambiguous_claim_without_source_columns_is_not_excluded() -> None:
    """Un claim sin columna resoluble (p. ej. group_count sin mapear) no se
    excluye por prudencia: la exclusión es solo para categorías conocidas."""

    tokens = intent_relevance_tokens("cualquier pregunta", ())
    assert claim_is_relevant_to_narrative((), requested_tokens=tokens)


# --- label_grounded_in_text (detección de intercambio) -----------------------


def test_label_grounded_in_text_accepts_adjacent_label_and_value() -> None:
    answer = "El resultado es Cantidad empleados: 12 en la última fila."
    assert label_grounded_in_text(answer, "Cantidad empleados", "12")


def test_label_grounded_in_text_rejects_swapped_label_and_value() -> None:
    """Etiqueta y cifra presentes en el texto, pero no asociadas entre sí
    (p. ej. dos claims cuyas etiquetas se intercambiaron) deben rechazarse."""

    answer = (
        "La categoría observada con mayor participación relativa este periodo "
        "es Categoría A, con un total de 30 registros verificados. "
        "Un resultado adicional y completamente distinto reportó 12."
    )
    # La etiqueta de un claim (Categoría A) queda lejos del valor del otro
    # claim que estamos verificando (12, que en realidad pertenece a otra
    # categoría no nombrada en este fragmento).
    assert not label_grounded_in_text(answer, "Categoría A", "12")


def test_label_grounded_in_text_rejects_missing_label() -> None:
    answer = "El resultado es 12."
    assert not label_grounded_in_text(answer, "Cantidad empleados", "12")


# --- build_presentation_warnings ---------------------------------------------


def test_build_presentation_warnings_empty_when_all_verified() -> None:
    claims = [
        {"claim_id": "c1", "label_status": "verified"},
        {"claim_id": "c2", "label_status": "verified"},
    ]
    assert build_presentation_warnings(claims) == []


def test_build_presentation_warnings_one_entry_per_ambiguous_claim() -> None:
    claims = [
        {"claim_id": "c1", "label_status": "verified"},
        {"claim_id": "c2", "label_status": "ambiguous"},
    ]
    warnings = build_presentation_warnings(claims)
    assert len(warnings) == 1
    assert warnings[0]["claim_id"] == "c2"
    assert warnings[0]["code"] == "AMBIGUOUS_LABEL"
    assert warnings[0]["message_user"]


def test_build_presentation_warnings_ignores_historical_claims_without_status() -> None:
    """Respuestas históricas sin `label_status` no generan advertencias
    fabricadas: equivalen a compatibilidad retroactiva, no a ambigüedad."""

    claims = [{"claim_id": "c1"}]
    assert build_presentation_warnings(claims) == []
