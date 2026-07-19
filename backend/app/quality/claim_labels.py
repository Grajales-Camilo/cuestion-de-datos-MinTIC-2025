"""Etiquetado semántico determinista y relevancia de claims públicos.

RF-212 (T-617C, contrato aprobado en T-617C-A, `contracts/api-rest.md` §4c).
Módulo puro: sin I/O, sin LLM. Deriva `label`/`label_status` exclusivamente
de metadatos estructurados (nombre real de columna fuente) y clasifica la
relevancia de una columna para la narrativa principal por su vocabulario
estructural, nunca por `case_id`, `dataset_id`, el texto literal de una
pregunta concreta ni el valor numérico presentado.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Literal

LabelStatus = Literal["verified", "ambiguous"]

#: Sentinel usado para columnas sin nombre de campo real (p. ej. `count(*)`
#: o el alias de agrupación de privacidad `group_count`). No es un alias
#: SoQL filtrable: se traduce a una etiqueta estructural fija, nunca a un
#: `dim_N`/`metric_N`.
COUNT_FIELD_SENTINEL = "__count__"
_COUNT_LABEL = "Conteo de registros"

_SAFE_FIELD_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_INTERNAL_ALIAS_RE = re.compile(r"^(dim_\d+|metric_[a-z]+_\d+|group_count)$")

_AUXILIARY_TOKENS = frozenset(
    {
        "codigo",
        "cod",
        "id",
        "identificador",
        "sigep",
        "nit",
        "llave",
        "key",
        "uuid",
        "consecutivo",
        "radicado",
    }
)
_TEMPORAL_TOKENS = frozenset(
    {
        "ano",
        "anio",
        "fecha",
        "mes",
        "periodo",
        "año",
        "year",
        "vigencia",
        "trimestre",
        "semestre",
    }
)

ColumnRelevance = Literal["primary", "temporal", "auxiliary"]


def _tokens(value: str) -> set[str]:
    plain = unicodedata.normalize("NFKD", value.casefold()).encode("ascii", "ignore").decode()
    return set(re.findall(r"[a-z0-9]+", plain))


def looks_like_internal_alias(value: str) -> bool:
    """Detecta si `value` tiene la forma de un alias interno de ejecución
    (`dim_N`, `metric_<op>_N`, `group_count`) que nunca debe filtrarse como
    nombre público de columna (RF-212)."""

    return bool(_INTERNAL_ALIAS_RE.match(value))


def humanize_field_name(field_name: str) -> str | None:
    """Humaniza de forma segura y determinista un nombre de columna real.

    Solo actúa sobre identificadores con la forma típica de columnas
    Socrata (minúsculas, dígitos, guion bajo) y nunca sobre algo que ya
    parezca un alias interno. No reconstruye tildes ni infiere significado:
    es una transformación mecánica del nombre ya existente, nunca una
    invención de contenido nuevo.
    """

    if field_name == COUNT_FIELD_SENTINEL:
        return _COUNT_LABEL
    if looks_like_internal_alias(field_name):
        return None
    if not _SAFE_FIELD_NAME_RE.match(field_name):
        return None
    words = [word for word in field_name.split("_") if word]
    if not words:
        return None
    text = " ".join(words)
    return text[0].upper() + text[1:]


def derive_claim_label(source_columns: tuple[str, ...]) -> tuple[str | None, LabelStatus]:
    """Deriva `label`/`label_status` desde los nombres de columna reales usados.

    Un claim que usa exactamente una columna fuente identificable obtiene una
    etiqueta verificada. Un claim que combina varias columnas distintas (p.
    ej. una fórmula derivada entre columnas distintas) o cuya columna no
    puede humanizarse de forma segura queda ambiguo: la cifra se conserva
    (RF-211), pero sin etiqueta inventada.
    """

    distinct = tuple(dict.fromkeys(source_columns))
    if len(distinct) != 1:
        return None, "ambiguous"
    label = humanize_field_name(distinct[0])
    if label is None:
        return None, "ambiguous"
    return label, "verified"


def classify_column_relevance(field_name: str) -> ColumnRelevance:
    if field_name == COUNT_FIELD_SENTINEL:
        return "primary"
    tokens = _tokens(field_name)
    if tokens & _AUXILIARY_TOKENS:
        return "auxiliary"
    if tokens & _TEMPORAL_TOKENS:
        return "temporal"
    return "primary"


def intent_relevance_tokens(topic: str, administrative_terms: tuple[str, ...]) -> frozenset[str]:
    """Tokens semánticos de la intención usados para permitir columnas
    auxiliares/temporales explícitamente solicitadas. Nunca incluye
    `case_id`, `dataset_id` ni literales de un caso concreto: solo el texto
    de la propia intención de la corrida en curso."""

    return frozenset(_tokens(" ".join((topic, *administrative_terms))))


def claim_is_relevant_to_narrative(
    source_columns: tuple[str, ...],
    *,
    requested_tokens: frozenset[str],
) -> bool:
    """Decide si un claim pertenece a la narrativa principal.

    Genérico y semántico: nunca condiciona por `case_id`, `dataset_id` ni el
    texto literal de una pregunta concreta, solo por la categoría léxica del
    nombre de columna y los tokens de la intención de la corrida en curso.
    Identificadores auxiliares quedan fuera salvo que la intención los
    mencione explícitamente (mismo vocabulario de categoría, no un valor
    concreto). Las columnas temporales sirven de contexto, no de cifra
    principal, salvo que la intención los solicite explícitamente.
    """

    if not source_columns:
        return True
    classifications = {classify_column_relevance(name) for name in source_columns}
    if "auxiliary" in classifications:
        return bool(requested_tokens & _AUXILIARY_TOKENS)
    if classifications == {"temporal"}:
        return bool(requested_tokens & _TEMPORAL_TOKENS)
    return True


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFKD", text.casefold()).encode("ascii", "ignore").decode()


def build_presentation_warnings(claims: list[dict]) -> list[dict]:
    """Construye `presentation_warnings` (RF-212, `contracts/api-rest.md`
    §4c) a partir de los claims públicos ya serializados. Vacío cuando
    ningún claim quedó con `label_status="ambiguous"`; nunca se deriva de
    `evidence[].quality.warnings_user` ni la reemplaza."""

    return [
        {
            "claim_id": claim["claim_id"],
            "code": "AMBIGUOUS_LABEL",
            "message_user": (
                "No se pudo asociar esta cifra con una etiqueta verificable; "
                "se conserva por ser útil y verificable, pero su significado "
                "exacto no está confirmado."
            ),
        }
        for claim in claims
        if claim.get("label_status") == "ambiguous"
    ]


def label_grounded_in_text(
    answer: str, label: str, display_value: str, *, window: int = 60
) -> bool:
    """Comprueba que `label` aparece cerca de `display_value` en `answer`.

    Una simple co-presencia de ambos textos en cualquier parte de la
    respuesta no basta: eso permitiría intercambiar la etiqueta de un valor
    con la de otro (p. ej. "Mujeres: 764" cuando 764 son hombres) sin que la
    validación lo detecte. Exigir proximidad textual entre la etiqueta y su
    propio valor bloquea ese intercambio sin exigir un parser de lenguaje
    natural completo.
    """

    norm_answer = _normalize(answer)
    norm_label = _normalize(label)
    norm_value = _normalize(display_value)
    if not norm_label or not norm_value:
        return False
    for match in re.finditer(re.escape(norm_value), norm_answer):
        start = max(0, match.start() - window)
        end = min(len(norm_answer), match.end() + window)
        if norm_label in norm_answer[start:end]:
            return True
    return False
