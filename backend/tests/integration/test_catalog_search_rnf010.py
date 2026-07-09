"""RNF-010 real (pruebas.md §2.3): p50/p95/p99 de /v2/catalog/search sobre
>= 100 consultas representativas + cobertura real del indice.

Requiere Postgres real con el catalogo ya ingerido (T-201/T-203) y
GOOGLE_API_KEY real (embebe cada consulta contra la API de Gemini, igual que
el endpoint en produccion) -- se salta limpiamente si falta cualquiera de
las dos cosas, en vez de fallar la suite de integracion por un problema de
entorno no relacionado con el codigo.

Corre secuencial (no concurrente) a proposito: es la medicion mas
conservadora (no se beneficia de pipelining) y evita ráfagas contra la API
de Google o el pool local de Postgres.
"""

from __future__ import annotations

from time import perf_counter

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.catalog.search_benchmark import build_representative_queries, compute_latency_percentiles
from app.config import get_settings
from app.db.engine import create_app_async_engine

pytestmark = pytest.mark.integration

_MIN_QUERIES = 100
_P95_BUDGET_MS = 1000.0
_MIN_COVERAGE_RATIO = 0.90


async def _distinct_active_categories(connection, limit: int = 40) -> list[str]:
    rows = (
        await connection.execute(
            text(
                "SELECT DISTINCT category FROM catalog_datasets "
                "WHERE api_active AND category IS NOT NULL AND category != '' "
                "ORDER BY category LIMIT :limit"
            ),
            {"limit": limit},
        )
    ).scalars()
    return list(rows)


async def _distinct_department_names(connection, limit: int = 20) -> list[str]:
    rows = (
        await connection.execute(
            text(
                "SELECT DISTINCT name FROM divipola_entries "
                "WHERE level = 'department' ORDER BY name LIMIT :limit"
            ),
            {"limit": limit},
        )
    ).scalars()
    return list(rows)


async def _catalog_metrics(connection) -> dict[str, float | int]:
    # inactive_datasets: excluidos de la busqueda misma (search.py filtra
    # WHERE api_active). active_ineligible_datasets: SI aparecen en la
    # busqueda (RF-302 no filtra por elegibilidad), pero no son usables como
    # evidencia mas adelante (RF-401, capa de calidad) -- son dos exclusiones
    # de proposito distinto, no se deben mezclar en un solo porcentaje o el
    # resultado es enganoso (ej.: hoy active_ineligible es ~100% del activo
    # por el hueco de cobertura de publicadores/PII ya documentado en
    # T-201A, pero eso NO significa que la busqueda no devuelva resultados).
    row = (
        await connection.execute(
            text(
                """
                SELECT
                    count(*) AS total_datasets,
                    count(*) FILTER (WHERE api_active) AS active_datasets,
                    count(*) FILTER (WHERE NOT api_active) AS inactive_datasets,
                    count(*) FILTER (
                        WHERE api_active AND eligibility_status != 'eligible'
                    ) AS active_ineligible_datasets
                FROM catalog_datasets
                """
            )
        )
    ).one()
    embeddings_count = (
        await connection.execute(
            text(
                """
                SELECT count(*)
                FROM catalog_embeddings e
                JOIN catalog_datasets d ON d.id = e.dataset_id
                WHERE d.api_active
                """
            )
        )
    ).scalar_one()
    return {
        "total_datasets": row.total_datasets,
        "active_datasets": row.active_datasets,
        "inactive_datasets": row.inactive_datasets,
        "active_ineligible_datasets": row.active_ineligible_datasets,
        "embeddings_over_active": embeddings_count,
    }


async def test_search_meets_rnf010_latency_and_coverage_budget() -> None:
    settings = get_settings()
    if settings.google_api_key is None or not settings.google_api_key.get_secret_value():
        pytest.skip("GOOGLE_API_KEY no configurada; RNF-010 requiere embeddings reales.")
    if settings.embedding_model is None:
        pytest.skip("EMBEDDING_MODEL no configurado.")

    engine = create_app_async_engine(settings.sqlalchemy_database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            categories = await _distinct_active_categories(connection)
            places = await _distinct_department_names(connection)
            metrics = await _catalog_metrics(connection)
    finally:
        await engine.dispose()

    if metrics["active_datasets"] == 0:
        pytest.skip("catalog_datasets sin filas activas; corre T-201/T-203 primero.")

    # Otras pruebas de integracion de este archivo/suite limpian
    # catalog_datasets/catalog_columns como parte de su propio aislamiento
    # (DELETE FROM ...); si esta prueba corre despues de esas en la misma
    # sesion de pytest, puede encontrar el catalogo real reducido a los
    # fixtures sinteticos de otra prueba. No es un fallo de RNF-010, es un
    # problema de orden/estado compartido de la suite -- se salta con
    # diagnostico claro en vez de fallar de forma confusa.
    try:
        queries = build_representative_queries(categories, places, minimum=_MIN_QUERIES)[
            :_MIN_QUERIES
        ]
    except ValueError as exc:
        pytest.skip(
            f"No hay suficiente diversidad real de categorias/departamentos "
            f"para generar >= {_MIN_QUERIES} consultas ahora mismo ({exc}). "
            "Otra prueba de esta sesion probablemente vacio catalog_datasets. "
            "Corre esta prueba aislada contra el catalogo real poblado: "
            "pytest -m integration -k rnf010."
        )

    import app.main as main

    main.app.state.settings = settings
    latencies_ms: list[float] = []
    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        for query in queries:
            start = perf_counter()
            response = await client.get("/v2/catalog/search", params={"q": query, "k": 10})
            latencies_ms.append((perf_counter() - start) * 1000)
            assert response.status_code == 200, (query, response.text)

    coverage_ratio = metrics["embeddings_over_active"] / metrics["active_datasets"]
    inactive_ratio = metrics["inactive_datasets"] / metrics["total_datasets"]
    active_ineligible_ratio = metrics["active_ineligible_datasets"] / metrics["active_datasets"]
    percentiles = compute_latency_percentiles(latencies_ms)

    print(
        f"\nRNF-010: {len(queries)} consultas | "
        f"p50={percentiles['p50']:.1f}ms p95={percentiles['p95']:.1f}ms "
        f"p99={percentiles['p99']:.1f}ms | "
        f"cobertura={coverage_ratio:.2%} "
        f"({metrics['embeddings_over_active']}/{metrics['active_datasets']} activos) | "
        f"excluidos de la busqueda (api_active=false)={inactive_ratio:.2%} "
        f"({metrics['inactive_datasets']}/{metrics['total_datasets']}) | "
        f"activos pero no elegibles como evidencia (RF-401, no filtrado por "
        f"esta busqueda)={active_ineligible_ratio:.2%} "
        f"({metrics['active_ineligible_datasets']}/{metrics['active_datasets']})"
    )

    assert coverage_ratio >= _MIN_COVERAGE_RATIO, (
        f"cobertura {coverage_ratio:.2%} < {_MIN_COVERAGE_RATIO:.0%} exigido por RNF-010"
    )
    assert percentiles["p95"] <= _P95_BUDGET_MS, (
        f"p95 {percentiles['p95']:.1f}ms excede el presupuesto RNF-010 de {_P95_BUDGET_MS:.0f}ms"
    )
