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
_IDENTIFIER_TOKENS = _AUXILIARY_TOKENS | {"postal", "divipola"}
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

#: Artículos, preposiciones y conjunciones sin contenido temático propio.
#: T-617B-C13-D8 (golden-v2, pilot-018-transporte-ferreo):
#: `dataset_topic_overlaps_intent` comparaba tokens sin filtrar estos
#: conectores, así que CUALQUIER par de textos en español coincidía
#: trivialmente en "de"/"y" -- la pregunta ("¿Qué concesiones y
#: operadores...?") y el dataset de repliegue equivocado ("Operación de
#: pasajeros... por carretera") solo compartían esos conectores, nunca un
#: token con contenido real, pero el gate igual devolvía `True`. Se filtran
#: aquí, en el tokenizador compartido, porque ninguno de los cuatro usos de
#: `_tokens` (columnas, identificadores, tokens de intención, nombre de
#: dataset) puede depender legítimamente de un conector como señal.
#: Deliberadamente NO incluye pronombres interrogativos ("cuanto"/"cuanta"/
#: "cuantos"/"cuantas", "cual", "donde", etc.): `_distinct_count_specs`
#: (`deterministic_pipeline.py`) y `_direct_quantity_column`
#: (`llm_contracts.py`) ya los usan como señal léxica real -- filtrarlos
#: aquí les habría quitado la única evidencia con la que detectan la
#: pregunta ("¿Cuántas... distintas...?").
_STOPWORDS = frozenset(
    {
        "a",
        "al",
        "con",
        "de",
        "del",
        "desde",
        "e",
        "el",
        "en",
        "entre",
        "hacia",
        "hasta",
        "la",
        "las",
        "lo",
        "los",
        "ni",
        "o",
        "para",
        "por",
        "segun",
        "sin",
        "sobre",
        "u",
        "un",
        "una",
        "unas",
        "unos",
        "y",
    }
)


def _tokens(value: str) -> set[str]:
    plain = unicodedata.normalize("NFKD", value.casefold()).encode("ascii", "ignore").decode()
    return set(re.findall(r"[a-z0-9]+", plain)) - _STOPWORDS


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


def is_identifier_field_name(field_name: str) -> bool:
    """Clasifica identificadores/códigos que deben conservarse como texto.

    Aunque Socrata declare algunas de estas columnas como numéricas, sus
    valores no son magnitudes: ceros iniciales, puntos y longitud forman parte
    de la identidad publicada y no se pueden redondear (RF-211/RNF-003).
    """

    return bool(_tokens(field_name) & _IDENTIFIER_TOKENS)


def intent_relevance_tokens(topic: str, administrative_terms: tuple[str, ...]) -> frozenset[str]:
    """Tokens semánticos de la intención usados para permitir columnas
    auxiliares/temporales explícitamente solicitadas. Nunca incluye
    `case_id`, `dataset_id` ni literales de un caso concreto: solo el texto
    de la propia intención de la corrida en curso."""

    return frozenset(_tokens(" ".join((topic, *administrative_terms))))


def _tokens_overlap(requested: str, other: str) -> bool:
    return requested == other or (
        min(len(requested), len(other)) >= 4 and (requested in other or other in requested)
    )


def column_is_explicitly_requested(
    field_name: str,
    *,
    requested_tokens: frozenset[str],
) -> bool:
    """Comprueba solapamiento léxico entre una columna y la intención.

    Esta señal es más estricta que ``claim_is_relevant_to_narrative``: no
    basta con que una columna sea primaria. Se exige que alguno de sus tokens
    estructurados aparezca en la intención (o comparta una raíz de al menos
    cuatro caracteres). Sirve para seleccionar de forma conservadora campos
    textuales de una fila única sin exponer columnas auxiliares que el usuario
    no pidió. Nunca inspecciona valores, ``case_id`` ni ``dataset_id``.
    """

    column_tokens = _tokens(field_name)
    return any(
        _tokens_overlap(requested, column)
        for requested in requested_tokens
        for column in column_tokens
    )


def dataset_topic_overlaps_intent(
    dataset_name: str,
    *,
    requested_tokens: frozenset[str],
) -> bool:
    """Comprueba solapamiento léxico entre el nombre publicado del dataset y
    la intención (T-617B-C13, RF-205/RF-211).

    Hallazgo real (golden-v1, `pilot-026-paridad-genero`/`pilot-027-paridad-
    etnica`): cuando los candidatos mejor rankeados no producen evidencia
    elegible, el runtime se repliega a un candidato posterior (p. ej.
    `ji8i-4anb`, "deserción escolar") cuyas columnas son léxicamente
    "primarias" (`classify_column_relevance` nunca las marca auxiliar/
    temporal), así que `claim_is_relevant_to_narrative` las deja pasar pese a
    no tener ninguna relación temática con la pregunta ("paridad de
    género"/"paridad étnica"). El nombre de columna no es una señal
    confiable de tema (`cantidad`, `capacidad` no repiten la pregunta), pero
    el NOMBRE PUBLICADO del dataset sí está escrito en lenguaje natural y
    normalmente sí lo hace -- es la misma señal ya usada por la recuperación
    semántica, aplicada aquí como sanidad determinista adicional, nunca por
    `case_id`/`dataset_id` ni un candidato concreto.
    """

    if not requested_tokens:
        return True
    name_tokens = _tokens(dataset_name)
    return any(
        _tokens_overlap(requested, token) for requested in requested_tokens for token in name_tokens
    )


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
    answer: str,
    label: str,
    display_value: str,
    *,
    other_labels: frozenset[str] = frozenset(),
    other_values: frozenset[str] = frozenset(),
) -> bool:
    """Comprueba que `label` está inequívocamente asociada a `display_value`
    en `answer` (RF-212, T-617C-R1).

    No basta con proximidad: "Hombres: 719; Mujeres: 764" tiene la etiqueta
    "Hombres" cerca de "719" y también cerca de "764" dentro de una ventana
    corta, así que una distancia simple aceptaría el intercambio. En su
    lugar, para cada aparición de `display_value` se exige que la ocurrencia
    de ETIQUETA MÁS CERCANA entre todas las citadas (`label` más
    `other_labels`) sea justamente `label` -- y que ninguna otra cifra
    citada (`other_values`) se interponga entre esa etiqueta y este valor.
    Esto rechaza los dos casos de intercambio del prompt (con `;` o con `.`)
    y sigue aceptando redacciones naturales donde el par es inequívoco
    (p. ej. "764 hombres y 719 mujeres", con la etiqueta después del valor).
    """

    norm_answer = _normalize(answer)
    norm_label = _normalize(label)
    norm_value = _normalize(display_value)
    if not norm_label or not norm_value:
        return False

    all_labels = {norm_label} | {
        normalized for candidate in other_labels if (normalized := _normalize(candidate))
    }
    other_values_norm = {
        normalized
        for candidate in other_values
        if (normalized := _normalize(candidate)) and normalized != norm_value
    }

    label_occurrences = [
        (match.start(), match.end(), candidate)
        for candidate in all_labels
        for match in re.finditer(re.escape(candidate), norm_answer)
    ]
    other_value_positions = [
        match.start()
        for candidate in other_values_norm
        for match in re.finditer(re.escape(candidate), norm_answer)
    ]

    for match in re.finditer(re.escape(norm_value), norm_answer):
        v_start, v_end = match.span()
        # (distance, order, label, span_start, span_end); en empate de
        # distancia se prefiere la etiqueta que PRECEDE al valor (orden 0),
        # la convención dominante ("Etiqueta: valor"), sobre la que sigue al
        # siguiente valor de otro claim ("valor; Etiqueta_del_siguiente").
        closest: tuple[int, int, str, int, int] | None = None
        for l_start, l_end, candidate in label_occurrences:
            if l_end <= v_start:
                distance, span, order = v_start - l_end, (l_end, v_start), 0
            elif l_start >= v_end:
                distance, span, order = l_start - v_end, (v_end, l_start), 1
            else:
                continue
            key = (distance, order)
            if closest is None or key < (closest[0], closest[1]):
                closest = (distance, order, candidate, *span)
        if closest is None or closest[2] != norm_label:
            continue
        span_start, span_end = closest[3], closest[4]
        if any(span_start <= pos < span_end for pos in other_value_positions):
            continue
        return True
    return False
