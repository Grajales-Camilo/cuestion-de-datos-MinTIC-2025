"""Utilidades puras para medir RNF-010 (pruebas.md §2.3): percentiles de
latencia y generacion reproducible de consultas representativas.

Estas consultas NO estan anotadas a mano con un `dataset_id` esperado -- esa
exigencia es de `research.md` §1 (recall del benchmark de embeddings, T-205),
distinta de esta medicion. Aqui solo importa exigir texto realista en
espanol contra `/v2/catalog/search`, para medir latencia/cobertura reales
sobre el indice, no relevancia. Se generan a partir de metadatos YA reales
del catalogo (categorias de `catalog_datasets`, departamentos de
`divipola_entries`) para que sean reproducibles sin inventar temas.
"""

from __future__ import annotations

_GENERAL_TEMPLATES = (
    "¿qué datos hay sobre {topic}?",
    "estadísticas de {topic} en Colombia",
    "información abierta de {topic}",
    "conjunto de datos de {topic}",
)
_TERRITORIAL_TEMPLATES = (
    "datos de {topic} en {place}",
    "{topic} del departamento de {place}",
)


def percentile(values: list[float], pct: float) -> float:
    """Percentil por interpolacion lineal (metodo estandar, sin dependencias nuevas)."""

    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * (pct / 100)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)


def compute_latency_percentiles(latencies_ms: list[float]) -> dict[str, float]:
    return {
        "p50": percentile(latencies_ms, 50),
        "p95": percentile(latencies_ms, 95),
        "p99": percentile(latencies_ms, 99),
    }


def build_representative_queries(
    categories: list[str],
    places: list[str],
    *,
    minimum: int = 100,
) -> list[str]:
    """Genera consultas deterministas a partir de categorias/lugares reales.

    No garantiza relevancia (eso es responsabilidad de research.md §1); solo
    garantiza texto realista y una mezcla general/territorial para ejercitar
    el mismo tipo de distribucion que exige RNF-010."""

    queries: list[str] = []
    for category in categories:
        topic = category.strip().lower()
        if not topic:
            continue
        for template in _GENERAL_TEMPLATES:
            queries.append(template.format(topic=topic))

    if places:
        cleaned_places = [place.strip() for place in places if place.strip()]
        for index, category in enumerate(categories):
            topic = category.strip().lower()
            if not topic or not cleaned_places:
                continue
            place = cleaned_places[index % len(cleaned_places)].title()
            for template in _TERRITORIAL_TEMPLATES:
                queries.append(template.format(topic=topic, place=place))

    unique_queries = list(dict.fromkeys(queries))
    if len(unique_queries) < minimum:
        raise ValueError(
            f"Solo se generaron {len(unique_queries)} consultas unicas; "
            f"se requieren >= {minimum} (research.md/pruebas.md RNF-010). "
            "Amplia las categorias/lugares de origen."
        )
    return unique_queries
