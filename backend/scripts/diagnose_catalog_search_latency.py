"""Diagnostico reproducible y de solo lectura para RNF-010 (T-614R).

No imprime secretos, no modifica datos y limita por defecto cada experimento.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time

from langchain_google_genai import GoogleGenerativeAIEmbeddings
from sqlalchemy import event

from app.catalog.search import embed_search_query, search_catalog
from app.catalog.search_benchmark import percentile
from app.config import get_settings
from app.db.engine import create_app_async_engine
from app.main import (
    CatalogSearchResources,
    _catalog_search_async,
    catalog_search_with_platform_loop,
)


def summary(values: list[float]) -> dict[str, float | int]:
    return {
        "count": len(values),
        "min": min(values),
        "p50": percentile(values, 50),
        "p95": percentile(values, 95),
        "p99": percentile(values, 99),
        "max": max(values),
        "mean": statistics.fmean(values),
    }


async def timed(awaitable) -> tuple[object, float]:
    start = time.perf_counter()
    value = await awaitable
    return value, (time.perf_counter() - start) * 1000


class FixedEmbedding:
    def __init__(self, vector: list[float]):
        self.vector = vector

    async def aembed_query(self, text: str, **kwargs) -> list[float]:
        return self.vector


async def main(samples: int) -> None:
    settings = get_settings()
    assert settings.google_api_key and settings.embedding_model
    query = "estadísticas de educación en Colombia"
    reused = GoogleGenerativeAIEmbeddings(
        model=settings.embedding_model, google_api_key=settings.google_api_key
    )
    vector, _ = await timed(embed_search_query(reused, query))
    fixed = FixedEmbedding(vector)
    engine = create_app_async_engine(settings.sqlalchemy_database_url, pool_pre_ping=True)
    results: dict[str, object] = {"samples_per_experiment": samples}
    try:
        vals = []
        for _ in range(samples):
            _, ms = await timed(embed_search_query(reused, query))
            vals.append(ms)
        results["embedding_reused_client_ms"] = summary(vals)
        vals = []
        for _ in range(samples):
            client = GoogleGenerativeAIEmbeddings(
                model=settings.embedding_model, google_api_key=settings.google_api_key
            )
            _, ms = await timed(embed_search_query(client, query))
            vals.append(ms)
        results["embedding_new_client_ms"] = summary(vals)
        vals = []
        for _ in range(samples):
            _, ms = await timed(search_catalog(engine, embedding_client=fixed, query=query, k=10))
            vals.append(ms)
        results["fixed_vector_reused_engine_sql_python_ms"] = summary(vals)
        captured: dict[str, object] = {}

        @event.listens_for(engine.sync_engine, "before_cursor_execute")
        def capture(conn, cursor, statement, parameters, context, executemany):
            if "WITH vector_candidates" in statement and not captured:
                captured.update(statement=statement, parameters=parameters)

        await search_catalog(engine, embedding_client=fixed, query=query, k=10)
        event.remove(engine.sync_engine, "before_cursor_execute", capture)
        async with engine.connect() as connection:
            plan_start = time.perf_counter()
            plan = (
                await connection.exec_driver_sql(
                    "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + str(captured["statement"]),
                    captured["parameters"],
                )
            ).scalar_one()
            results["explain_wall_ms"] = (time.perf_counter() - plan_start) * 1000
            root = plan[0]["Plan"]
            results["explain_execution_ms"] = plan[0]["Execution Time"]
            results["explain_planning_ms"] = plan[0]["Planning Time"]
            results["explain_root"] = {
                "node": root["Node Type"],
                "actual_rows": root["Actual Rows"],
            }

            def nodes(node):
                yield node
                for child in node.get("Plans", []):
                    yield from nodes(child)

            results["plan_nodes"] = [
                {
                    "node": n["Node Type"],
                    "relation": n.get("Relation Name"),
                    "index": n.get("Index Name"),
                    "actual_ms": n.get("Actual Total Time"),
                    "actual_rows": n.get("Actual Rows"),
                    "loops": n.get("Actual Loops"),
                }
                for n in nodes(root)
            ]
        vals = []
        reused_resources = CatalogSearchResources(engine, reused)
        for _ in range(samples):
            _, ms = await timed(
                _catalog_search_async(
                    resources=reused_resources,
                    embedding_model=settings.embedding_model,
                    query=query,
                    k=10,
                    stale_after_days=settings.catalog_stale_after_days,
                )
            )
            vals.append(ms)
        results["direct_full_reused_resources_ms"] = summary(vals)
        vals = []
        for _ in range(samples):
            _, ms = await timed(
                catalog_search_with_platform_loop(
                    resources=reused_resources,
                    embedding_model=settings.embedding_model,
                    query=query,
                    k=10,
                    stale_after_days=settings.catalog_stale_after_days,
                )
            )
            vals.append(ms)
        results["platform_route_reused_resources_ms"] = summary(vals)
    finally:
        await engine.dispose()
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=10, choices=range(3, 31))
    args = parser.parse_args()
    asyncio.run(main(args.samples), loop_factory=asyncio.SelectorEventLoop)
