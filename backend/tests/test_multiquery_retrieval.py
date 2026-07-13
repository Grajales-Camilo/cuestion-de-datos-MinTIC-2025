from datetime import UTC, datetime

import pytest

from app.agent.llm_contracts import IntentExtraction
from app.agent.multiquery_retrieval import (
    build_query_variants,
    retrieve_candidates_multiquery,
)
from app.agent.query_plan import QueryOperation
from app.catalog.search import CatalogSearchItem, CatalogSearchSummary


def _item(
    dataset_id: str,
    similarity: float,
    *,
    verified: bool = True,
    eligible: bool = True,
) -> CatalogSearchItem:
    return CatalogSearchItem(
        dataset_id=dataset_id,
        name=f"Dataset {dataset_id}",
        publisher="Entidad",
        official_publisher_id="entidad" if verified else None,
        publisher_verification_status="verified" if verified else "unverified",
        pii_risk_level="low",
        eligibility_status="eligible" if eligible else "ineligible",
        eligibility_reasons=[],
        similarity=similarity,
        row_count=10,
        data_updated_at=None,
        latest_observed_cutoff_at=None,
        metadata_synced_at=datetime.now(UTC),
        index_stale=False,
        columns_preview=[],
    )


def _intent() -> IntentExtraction:
    return IntentExtraction(
        topic="homicidios",
        operation=QueryOperation.COUNT,
        territory="Valle del Cauca",
        period="2025",
        administrative_terms=("departamento", "municipio"),
    )


def test_query_variants_are_deterministic_unique_and_grounded_in_intent() -> None:
    variants = build_query_variants(_intent())
    assert variants == (
        "homicidios Valle del Cauca 2025",
        "homicidios",
        "homicidios departamento municipio",
        "homicidios count",
    )
    assert build_query_variants(_intent()) == variants


@pytest.mark.asyncio
async def test_multiquery_deduplicates_and_rewards_cross_query_coverage() -> None:
    shared = _item("aaaa-1111", 0.72)
    isolated = _item("bbbb-2222", 0.76)
    calls: list[tuple[str, int]] = []

    async def searcher(query: str, k: int) -> CatalogSearchSummary:
        calls.append((query, k))
        results = [shared]
        if len(calls) == 1:
            results.append(isolated)
        return CatalogSearchSummary(query=query, results=results)

    result = await retrieve_candidates_multiquery(_intent(), searcher=searcher, per_query=5)
    assert len(calls) == 4
    assert [candidate.item.dataset_id for candidate in result.candidates] == [
        "aaaa-1111",
        "bbbb-2222",
    ]
    assert result.candidates[0].matched_queries == result.queries


@pytest.mark.asyncio
async def test_multiquery_demotes_ineligible_candidate() -> None:
    async def searcher(query: str, k: int) -> CatalogSearchSummary:
        del k
        return CatalogSearchSummary(
            query=query,
            results=[_item("unsafe-1", 0.99, eligible=False), _item("safe-1", 0.70)],
        )

    result = await retrieve_candidates_multiquery(_intent(), searcher=searcher)
    assert result.candidates[0].item.dataset_id == "safe-1"


@pytest.mark.asyncio
async def test_multiquery_validates_limits_before_search() -> None:
    async def searcher(query: str, k: int) -> CatalogSearchSummary:
        raise AssertionError((query, k))

    with pytest.raises(ValueError, match="per_query"):
        await retrieve_candidates_multiquery(_intent(), searcher=searcher, per_query=0)
