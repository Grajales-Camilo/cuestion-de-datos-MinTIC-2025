"""Recuperación multiquery determinista para candidatos del catálogo.

Satisface RF-201/RF-302/RF-303: amplía cobertura usando únicamente partes
estructuradas de la intención, deduplica por ID real y conserva trazabilidad
de las consultas que aportaron cada candidato.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.agent.llm_contracts import IntentExtraction
from app.catalog.search import CatalogSearchItem, CatalogSearchSummary

CatalogSearcher = Callable[[str, int], Awaitable[CatalogSearchSummary]]


@dataclass(frozen=True)
class RetrievedCandidate:
    item: CatalogSearchItem
    score: float
    matched_queries: tuple[str, ...]
    best_rank: int


@dataclass(frozen=True)
class MultiQueryRetrievalResult:
    queries: tuple[str, ...]
    candidates: tuple[RetrievedCandidate, ...]


def build_query_variants(intent: IntentExtraction) -> tuple[str, ...]:
    """Construye variantes acotadas sin tesauros ni texto generado libre."""

    topic = intent.topic.strip()
    qualifiers = tuple(
        value.strip()
        for value in (intent.entity, intent.territory, intent.period)
        if value and value.strip()
    )
    administrative = tuple(
        value.strip() for value in intent.administrative_terms if value.strip()
    )
    raw = (
        " ".join((topic, *qualifiers)),
        topic,
        " ".join((topic, *administrative)),
        " ".join((topic, intent.operation.value)),
    )
    normalized = (" ".join(value.split()) for value in raw)
    return tuple(dict.fromkeys(value for value in normalized if len(value) >= 3))


def _candidate_score(item: CatalogSearchItem, *, rank: int, matches: int) -> float:
    reciprocal_rank = 1.0 / (rank + 1)
    official = 0.08 if item.publisher_verification_status == "verified" else 0.0
    eligible = 0.08 if item.eligibility_status == "eligible" else -0.60
    freshness = -0.08 if item.index_stale else 0.0
    coverage = min(0.12, max(0, matches - 1) * 0.04)
    score = item.similarity + reciprocal_rank * 0.15
    return round(score + official + eligible + freshness + coverage, 8)


def _explicit_intent_boost(item: CatalogSearchItem, intent: IntentExtraction) -> float:
    def tokens(value: str) -> set[str]:
        plain = unicodedata.normalize("NFKD", value.casefold()).encode("ascii", "ignore").decode()
        observed = set(re.findall(r"[a-z0-9]+", plain))
        return {
            token[:-1] if token.endswith("s") and len(token) > 4 else token
            for token in observed
        }

    name = tokens(item.name)
    explicit = tokens(
        " ".join(
            (
                intent.topic,
                intent.entity or "",
                *intent.administrative_terms,
            )
        )
    )
    overlap = len(name.intersection(explicit))
    return min(0.72, overlap * 0.18)


async def retrieve_candidates_multiquery(
    intent: IntentExtraction,
    *,
    searcher: CatalogSearcher,
    per_query: int = 10,
    limit: int = 10,
) -> MultiQueryRetrievalResult:
    if not 1 <= per_query <= 25:
        raise ValueError("per_query debe estar entre 1 y 25")
    if not 1 <= limit <= 25:
        raise ValueError("limit debe estar entre 1 y 25")

    queries = build_query_variants(intent)
    observed: dict[str, tuple[CatalogSearchItem, list[str], int]] = {}
    for query in queries:
        summary = await searcher(query, per_query)
        for rank, item in enumerate(summary.results):
            previous = observed.get(item.dataset_id)
            if previous is None:
                observed[item.dataset_id] = (item, [query], rank)
                continue
            best_item, matched, best_rank = previous
            if query not in matched:
                matched.append(query)
            if item.similarity > best_item.similarity:
                best_item = item
            observed[item.dataset_id] = (best_item, matched, min(best_rank, rank))

    candidates = [
        RetrievedCandidate(
            item=item,
            score=round(
                _candidate_score(item, rank=best_rank, matches=len(matched))
                + _explicit_intent_boost(item, intent),
                8,
            ),
            matched_queries=tuple(matched),
            best_rank=best_rank,
        )
        for item, matched, best_rank in observed.values()
    ]
    candidates.sort(key=lambda candidate: (-candidate.score, candidate.item.dataset_id))
    return MultiQueryRetrievalResult(queries=queries, candidates=tuple(candidates[:limit]))
