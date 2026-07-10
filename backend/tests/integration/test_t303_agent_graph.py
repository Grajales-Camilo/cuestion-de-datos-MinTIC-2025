"""Persistencia real del grafo T-303 con PostgreSQL y LLM guionado."""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent.durability import write_terminal_event_once
from app.agent.graph import (
    GraphDependencies,
    PlannerOutput,
    RouterOutput,
    SynthesisOutput,
    build_graph,
    initial_state,
)
from app.agent.persistence import persist_final_answer
from app.config import normalize_database_url_for_sqlalchemy
from app.db.models import AgentRun, CatalogColumn, CatalogDataset, WorkerInstance

pytestmark = pytest.mark.integration
DATASET_ID = "t303-test"


class StaticModel:
    def __init__(self, value):
        self.value = value

    async def ainvoke(self, _messages, **_kwargs):
        return self.value


class IntegrationRouter:
    def __init__(self):
        self.calls = 0

    async def ainvoke(self, messages, **_kwargs):
        self.calls += 1
        if self.calls == 1:
            return RouterOutput(
                action="buscar_catalogo",
                reasoning_summary="Ubicar fuente",
                tool_input={"query": "cooperación", "k": 5},
            )
        if self.calls == 2:
            return RouterOutput(
                action="ejecutar_soql",
                reasoning_summary="Consultar fuente",
                tool_input={
                    "dataset_id": DATASET_ID,
                    "soql": "SELECT sector, sum(monto) AS total GROUP BY sector LIMIT 50",
                    "purpose": "Recursos por sector",
                },
            )
        payload = json.loads(messages[-1].content)
        return RouterOutput.model_validate(
            {
                "action": "finish",
                "reasoning_summary": "Responder",
                "tool_input": {},
                "claim_specs_by_evidence": [
                    {
                        "evidence_id": payload["evidences"][0]["evidence_id"],
                        "claim_specs": [
                            {
                                "claim_type": "direct",
                                "description": "Recursos en educación",
                                "source_row_indexes": [0],
                                "columns": ["total"],
                                "unit": "COP",
                                "rounding": 0,
                            }
                        ],
                    }
                ],
            }
        )


class IntegrationSynthesizer:
    async def ainvoke(self, messages, **_kwargs):
        payload = json.loads(messages[-1].content)
        value = payload["claims"][0]["display_value"]
        evidence_id = payload["evidences"][0]["evidence_id"]
        return SynthesisOutput.model_validate(
            {
                "summary": f"La fuente registra {value}.",
                "narrative": f"La evidencia respalda {value}.",
                "evidence_narratives": [
                    {"evidence_id": evidence_id, "narrative": f"El resultado es {value}."}
                ],
            }
        )


async def _catalog_tool(_raw_input):
    return {"ok": True, "results": [{"dataset_id": DATASET_ID}]}


async def _unused_tool(_raw_input):
    return {"ok": False, "error": {"code": "UNUSED", "message": "unused"}}


def graph_dependencies(engine):
    return GraphDependencies(
        engine=engine,
        planner_model=StaticModel(
            PlannerOutput(
                intention="Cuantificar recursos",
                subqueries=["Encontrar fuente", "Consultar montos"],
                recommended_next_action="Buscar catálogo",
            )
        ),
        router_model=IntegrationRouter(),
        synthesizer_model=IntegrationSynthesizer(),
        tools={
            "buscar_catalogo": _catalog_tool,
            "perfilar_dataset": _unused_tool,
            "resolver_geografia": _unused_tool,
            "explorar_valores": _unused_tool,
            "ejecutar_soql": _successful_t5,
        },
        llm_provider="google",
        llm_model="gemini-2.5-flash",
        max_steps=10,
        persist=True,
    )


@pytest.fixture
async def engine():
    engine = create_async_engine(
        normalize_database_url_for_sqlalchemy(os.environ["DATABASE_URL"]), pool_pre_ping=True
    )
    yield engine
    await engine.dispose()


@pytest.fixture(autouse=True)
async def clean_t303_rows(engine):
    async def clean():
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM agent_runs WHERE question = 'integracion T-303'")
            )
            await connection.execute(
                text("DELETE FROM worker_instances WHERE id LIKE 't303-worker-%'")
            )
            await connection.execute(
                text("DELETE FROM catalog_datasets WHERE id = :id"), {"id": DATASET_ID}
            )

    await clean()
    yield
    await clean()


async def seed_run(engine) -> uuid.UUID:
    now = datetime.now(UTC)
    worker_id = f"t303-worker-{uuid.uuid4()}"
    run_id = uuid.uuid4()
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session, session.begin():
        session.add(
            WorkerInstance(
                id=worker_id,
                started_at=now,
                heartbeat_at=now,
                lease_expires_at=now + timedelta(minutes=5),
                status="active",
            )
        )
        session.add(
            CatalogDataset(
                id=DATASET_ID,
                name="Cooperación internacional",
                publisher="Agencia estatal",
                publisher_verification_status="verified",
                metadata_synced_at=now,
                data_updated_at=now,
                api_active=True,
                pii_risk_level="low",
                eligibility_status="eligible",
                eligibility_reasons=[],
            )
        )
        await session.flush()
        for field, data_type in (("sector", "text"), ("monto", "number")):
            session.add(
                CatalogColumn(
                    dataset_id=DATASET_ID,
                    field_name=field,
                    data_type=data_type,
                    sample_values=[],
                    pii_risk_level="low",
                    contains_personal_data=False,
                    eligibility_status="eligible",
                    eligibility_reasons=[],
                )
            )
        session.add(
            AgentRun(
                id=run_id,
                question="integracion T-303",
                status="running",
                worker_instance_id=worker_id,
                heartbeat_at=now,
                last_event_seq=0,
                run_access_token_hash="x" * 64,
                run_access_token_expires_at=now + timedelta(days=1),
                retention_class="user",
                created_at=now,
            )
        )
    return run_id


async def test_t303_persists_complete_trace(engine):
    run_id = await seed_run(engine)
    graph_deps = graph_dependencies(engine)
    graph = build_graph(graph_deps, interrupt=False)
    state = await graph.ainvoke(initial_state(run_id, "integracion T-303", max_steps=10))
    final_answer = state["final_answer"]
    await persist_final_answer(
        engine,
        run_id,
        final_answer,
        latency_ms=100,
        llm_provider="google",
        llm_model="gemini-2.5-flash",
        input_tokens=0,
        output_tokens=0,
        estimated_cost_usd=0,
    )
    await write_terminal_event_once(
        engine, run_id, status="completed", error_code=None, payload=final_answer
    )

    async with engine.connect() as connection:
        counts = {}
        for table in (
            "agent_steps",
            "agent_run_events",
            "evidence_results",
            "quality_reports",
            "quantitative_claims",
        ):
            counts[table] = (
                await connection.execute(
                    text(
                        f"SELECT count(*) FROM {table} "  # noqa: S608 - lista cerrada local
                        "WHERE run_id = :run_id"
                        if table not in {"quality_reports"}
                        else "SELECT count(*) FROM quality_reports q JOIN evidence_results e "
                        "ON e.id=q.evidence_id WHERE e.run_id=:run_id"
                    ),
                    {"run_id": run_id},
                )
            ).scalar_one()
        run_row = (
            await connection.execute(
                text(
                    "SELECT status, steps_used, last_event_seq, final_answer "
                    "FROM agent_runs WHERE id=:run_id"
                ),
                {"run_id": run_id},
            )
        ).one()

    assert counts["agent_steps"] == state["steps_used"]
    assert counts["evidence_results"] == 1
    assert counts["quality_reports"] == 1
    assert counts["quantitative_claims"] == 1
    assert counts["agent_run_events"] == run_row.last_event_seq
    assert run_row.status == "completed"
    assert run_row.final_answer["claims"][0]["display_value"] == "100 COP"


async def _successful_t5(_raw_input):
    return {
        "ok": True,
        "canonical_soql": "SELECT sector, sum(monto) AS total GROUP BY sector LIMIT 50",
        "rows": [{"sector": "Educación", "total": "100"}],
        "row_count": 1,
        "executed_at": datetime.now(UTC).isoformat(),
        "source_url": f"https://www.datos.gov.co/d/{DATASET_ID}",
        "llm_view": {"rows_shown": 1},
    }
