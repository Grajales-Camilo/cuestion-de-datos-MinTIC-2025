"""Puerta 8: aceptación integrada del runtime LEGADO (T-612, research.md §25).

Renombrado desde `test_agent_redesign_acceptance.py`: su nombre original
sugería el nuevo núcleo determinista, pero importa `app.agent.graph`
(`build_graph`/`initial_state`), el grafo histórico congelado — pertenece
al rollback, no al runtime productivo. Ver `test_deterministic_agent_acceptance.py`
para la aceptación E2E del runtime determinista (`execute_deterministic_agent_run_async`).

Esta suite no reemplaza las pruebas unitarias que diagnostican cada mecanismo.
Las reúne como historias de aceptación y añade una verificación persistente del
camino positivo contra PostgreSQL real. No usa Gemini ni modifica el golden set.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.agent.graph import build_graph, initial_state
from app.config import normalize_database_url_for_sqlalchemy
from tests.integration.test_t303_agent_graph import graph_dependencies, seed_run
from tests.test_agent_claim_planning import (
    test_rejected_claims_trigger_claim_repair_before_synthesis as _claim_repair_story,
)
from tests.test_agent_graph import (
    test_soql_forbidden_also_allows_only_two_corrections as _soql_repair_story,
)
from tests.test_agent_structured_repair import (
    test_router_repairs_invalid_tool_input_once_with_validation_feedback as _input_repair_story,
)
from tests.test_agent_tool_recovery import (
    test_corrected_explorar_valores_input_executes_once as _explore_once_story,
)
from tests.test_agent_tool_recovery import (
    test_non_text_column_error_causes_direct_soql_strategy as _non_text_pivot_story,
)

pytestmark = [pytest.mark.integration, pytest.mark.legacy_agent_acceptance]


@pytest.fixture
async def engine():
    database = create_async_engine(
        normalize_database_url_for_sqlalchemy(os.environ["DATABASE_URL"]),
        pool_pre_ping=True,
    )
    yield database
    await database.dispose()


@pytest.fixture(autouse=True)
async def clean_acceptance_rows(engine):
    dataset_ids = ("t303-test", "t402-diagnostic-only")

    async def clean():
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "DELETE FROM agent_runs WHERE question IN "
                    "('integracion T-303', 'aceptación integral del rediseño', "
                    "'integracion T-402 diagnostic_only')"
                )
            )
            await conn.execute(
                text("DELETE FROM catalog_datasets WHERE id = ANY(:dataset_ids)"),
                {"dataset_ids": list(dataset_ids)},
            )

    await clean()
    yield
    await clean()


async def test_positive_path_completes_and_persists_every_required_layer(engine):
    """T1 → T5 → T6 → claim_planner → T7 → síntesis → completed."""
    run_id = await seed_run(engine)
    state = await build_graph(graph_dependencies(engine), interrupt=False).ainvoke(
        initial_state(run_id, "aceptación integral del rediseño", max_steps=10)
    )

    assert state["final_answer"]["status"] == "completed"
    assert state["claims"]
    assert state["steps_used"] <= 10

    async with engine.connect() as conn:
        nodes = (
            (
                await conn.execute(
                    text("SELECT node FROM agent_steps WHERE run_id=:run_id ORDER BY step_number"),
                    {"run_id": run_id},
                )
            )
            .scalars()
            .all()
        )
        counts = (
            (
                await conn.execute(
                    text(
                        """
                    SELECT
                      (SELECT count(*) FROM evidence_results WHERE run_id=:run_id) evidence,
                      (SELECT count(*) FROM quality_reports q JOIN evidence_results e
                         ON e.id=q.evidence_id WHERE e.run_id=:run_id) quality,
                      (SELECT count(*) FROM quantitative_claims WHERE run_id=:run_id) claims
                    """
                    ),
                    {"run_id": run_id},
                )
            )
            .mappings()
            .one()
        )

    assert nodes == [
        "planner",
        "router",
        "tool:buscar_catalogo",
        "router",
        "tool:ejecutar_soql",
        "quality_validator",
        "router",
        "claim_planner",
        "claim_builder",
        "synthesizer",
    ]
    assert counts["evidence"] == 1
    assert counts["quality"] == 1
    assert counts["claims"] >= 1


async def test_invalid_tool_input_is_repaired_before_tool_execution():
    await _input_repair_story()


async def test_corrected_explorar_valores_executes_only_once():
    await _explore_once_story()


async def test_non_text_exploration_pivots_to_direct_soql_and_completes():
    await _non_text_pivot_story()


async def test_forbidden_soql_is_corrected_with_a_bounded_budget():
    await _soql_repair_story()


async def test_rejected_claim_is_replanned_before_synthesis():
    await _claim_repair_story()


async def test_no_evidence_path_remains_honest_without_fabricated_claims(engine):
    """Una fuente no utilizable debe terminar sin claims, no como `failed`."""
    from tests.integration.test_t402_quality_claims_integration import (
        test_evidencia_diagnostic_only_no_sustenta_claims as _no_evidence_story,
    )

    await _no_evidence_story(engine)
