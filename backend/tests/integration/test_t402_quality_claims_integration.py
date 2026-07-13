"""T-402: verificación integrada de calidad (T6) y claims (T7) contra el grafo
real (T-303) con PostgreSQL real y router/sintetizador guionados.

Matriz cubierta (contracts/validacion-calidad.md, tasks.md T-402, RF-401..404,
RF-208):

1. Evidencia elegible y `alta`: produce claims reproducibles, cero cifras
   huérfanas, respuesta `completed`.
2. Evidencia elegible pero `baja` (corte >48 meses + columna mayormente vacía,
   ESC-05): conserva la advertencia en `quality.warnings_user`, SIGUE
   sustentando claims (RF-402: `baja` no es una regla dura de exclusión) y el
   sintetizador guionado prueba que la advertencia efectivamente viaja hasta
   el payload que ve el LLM.
3. Evidencia elegible pero `no_recomendada` (fuente incompleta, Art. I.2):
   aunque el router/LLM pida un claim sobre ella, `claim_builder` NO lo
   construye (regresión del fix de graph.py) y la corrida termina en
   `no_evidence`, nunca en una respuesta afirmativa sustentada en ella.
4. Evidencia `diagnostic_only` (publicador no verificado): T5 puede seguir
   ejecutándose para fines diagnósticos, pero tampoco sustenta claims.

En los 4 casos se verifica además que `quality_validator` corrió exactamente
una vez y que la evidencia + su reporte de calidad quedan persistidos
íntegramente, exista o no un claim asociado.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent.graph import (
    ClaimPlannerOutput,
    GraphDependencies,
    PlannerOutput,
    RouterOutput,
    SynthesisOutput,
    build_graph,
    initial_state,
)
from app.config import normalize_database_url_for_sqlalchemy
from app.db.models import AgentRun, CatalogColumn, CatalogDataset, WorkerInstance

pytestmark = pytest.mark.integration

DATASET_ALTA = "t402-alta"
DATASET_BAJA = "t402-baja"
DATASET_NO_RECOMENDADA = "t402-no-recomendada"
DATASET_DIAGNOSTIC = "t402-diagnostic-only"
ALL_DATASET_IDS = (DATASET_ALTA, DATASET_BAJA, DATASET_NO_RECOMENDADA, DATASET_DIAGNOSTIC)


class StaticModel:
    def __init__(self, value):
        self.value = value

    async def ainvoke(self, _messages, **_kwargs):
        return self.value


class ScriptedRouter:
    """Ubica el dataset, ejecuta el SoQL dado y SIEMPRE pide un claim sobre la
    evidencia resultante -- incluso en los escenarios donde esa evidencia no
    debe poder sustentarlo. El punto de la prueba es que el backend rechace
    esa construcción por sí solo, sin depender de que el router/LLM se
    comporte bien.
    """

    def __init__(self, *, dataset_id: str, soql: str):
        self.dataset_id = dataset_id
        self.soql = soql
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
                    "dataset_id": self.dataset_id,
                    "soql": self.soql,
                    "purpose": "Verificación T-402",
                },
            )
        payload = json.loads(messages[-1].content)
        return RouterOutput.model_validate(
            {
                "action": "finish",
                "reasoning_summary": "Intento construir la cifra con la evidencia obtenida",
                "tool_input": {},
                "claim_specs_by_evidence": [
                    {
                        "evidence_id": payload["evidences"][0]["evidence_id"],
                        "claim_specs": [
                            {
                                "claim_type": "direct",
                                "description": "Cifra bajo verificación T-402",
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


class ScriptedSynthesizer:
    """Refleja en la narrativa exactamente lo que el grafo le envía: si hay
    claims, cita su valor y las advertencias de calidad de la evidencia que lo
    sustenta (prueba que `warnings_user`/`classification` llegan al payload
    del LLM); si no hay claims, redacta el reporte `no_evidence` citando la
    evidencia revisada.
    """

    def __init__(self):
        self.received_warnings: list[str] | None = None
        self.received_classification: str | None = None

    async def ainvoke(self, messages, **_kwargs):
        payload = json.loads(messages[-1].content)
        evidence = payload["evidences"][0]
        warnings = evidence["quality"].get("warnings_user") or []
        self.received_warnings = warnings
        self.received_classification = evidence["quality"].get("classification")
        if payload["claims"]:
            claim = payload["claims"][0]
            value = claim["display_value"]
            # Deliberadamente cualitativo, sin repetir cifras de `warnings_user`:
            # el guardia de cifras huérfanas (`_orphan_figures`) solo acepta
            # números que coincidan con `claims[].display_value`; un número
            # citado desde una advertencia de calidad (p. ej. un porcentaje de
            # nulos) NO está en esa lista blanca y sería rechazado como cifra
            # huérfana aunque provenga de un cálculo determinista real de T6.
            warning_note = (
                " Advertencia: esta evidencia tiene limitaciones de calidad; "
                "revisa el detalle técnico antes de citarla."
                if warnings
                else ""
            )
            return SynthesisOutput.model_validate(
                {
                    "summary": f"La fuente registra {value}.{warning_note}",
                    "narrative": f"La evidencia respalda {value}.{warning_note}",
                    "evidence_narratives": [
                        {
                            "evidence_id": evidence["evidence_id"],
                            "narrative": f"El resultado es {value}.{warning_note}",
                        }
                    ],
                }
            )
        return SynthesisOutput.model_validate(
            {
                "summary": "No encontré evidencia suficiente en el catálogo para responder.",
                "no_evidence_report": {
                    "reason": "La única fuente consultada no puede sustentar cifras.",
                    "datasets_reviewed": [
                        {
                            "dataset_id": evidence["dataset_id"],
                            "name": evidence["dataset_name"],
                            "why_rejected": (
                                warnings[0] if warnings else "Evidencia no elegible para citar."
                            ),
                        }
                    ],
                    "suggestions": ["Reformular la consulta o buscar otra fuente oficial."],
                },
            }
        )


class ScriptedClaimPlanner:
    async def ainvoke(self, messages, **_kwargs):
        payload = json.loads(messages[-1].content)
        evidences = payload.get("evidences", [])
        plans = []
        if evidences:
            plans.append(
                {
                    "evidence_id": evidences[0]["evidence_id"],
                    "claim_specs": [
                        {
                            "claim_type": "direct",
                            "description": "Cifra bajo verificación T-402",
                            "source_row_indexes": [0],
                            "columns": ["total"],
                            "unit": "COP",
                            "rounding": 0,
                        }
                    ],
                }
            )
        return ClaimPlannerOutput.model_validate(
            {
                "reasoning_summary": "Planificar únicamente evidencia utilizable",
                "claim_specs_by_evidence": plans,
            }
        )


async def _unused_tool(_raw_input):
    return {"ok": False, "error": {"code": "UNUSED", "message": "unused"}}


def _t5_tool(*, canonical_soql: str, rows: list[dict], source_url: str | None, dataset_id: str):
    async def _tool(_raw_input):
        return {
            "ok": True,
            "canonical_soql": canonical_soql,
            "rows": rows,
            "row_count": len(rows),
            "executed_at": datetime.now(UTC).isoformat(),
            "source_url": source_url,
            "llm_view": {"rows_shown": len(rows)},
        }

    return _tool


def graph_dependencies(engine, *, dataset_id: str, soql: str, ejecutar_soql_tool, synthesizer=None):
    return GraphDependencies(
        engine=engine,
        planner_model=StaticModel(
            PlannerOutput(
                intention="Verificar la matriz de integración T-402",
                subqueries=["Encontrar fuente", "Consultar y validar"],
                recommended_next_action="Buscar catálogo",
            )
        ),
        router_model=ScriptedRouter(dataset_id=dataset_id, soql=soql),
        synthesizer_model=synthesizer or ScriptedSynthesizer(),
        claim_model=ScriptedClaimPlanner(),
        tools={
            "buscar_catalogo": _catalog_tool_stub,
            "perfilar_dataset": _unused_tool,
            "resolver_geografia": _unused_tool,
            "explorar_valores": _unused_tool,
            "ejecutar_soql": ejecutar_soql_tool,
        },
        llm_provider="google",
        llm_model="gemini-2.5-flash",
        max_steps=10,
        persist=True,
    )


async def _catalog_tool_stub(_raw_input):
    # El router siempre resuelve el dataset por su propio `tool_input.dataset_id`
    # en el paso 2 (ver ScriptedRouter); el resultado de búsqueda no se usa,
    # solo debe existir para que el paso 1 del router tenga una respuesta.
    return {"ok": True, "results": []}


@pytest.fixture
async def engine():
    engine = create_async_engine(
        normalize_database_url_for_sqlalchemy(os.environ["DATABASE_URL"]), pool_pre_ping=True
    )
    yield engine
    await engine.dispose()


@pytest.fixture(autouse=True)
async def clean_t402_rows(engine):
    async def clean():
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM agent_runs WHERE question LIKE 'integracion T-402%'")
            )
            await connection.execute(
                text("DELETE FROM worker_instances WHERE id LIKE 't402-worker-%'")
            )
            for dataset_id in ALL_DATASET_IDS:
                await connection.execute(
                    text("DELETE FROM catalog_datasets WHERE id = :id"), {"id": dataset_id}
                )

    await clean()
    yield
    await clean()


async def seed_run(
    engine,
    *,
    question: str,
    dataset_id: str,
    publisher_verification_status: str,
    eligibility_status: str,
    eligibility_reasons: list[str],
    data_updated_at: datetime,
    columns: list[str],
) -> uuid.UUID:
    now = datetime.now(UTC)
    worker_id = f"t402-worker-{uuid.uuid4()}"
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
                id=dataset_id,
                name="Dataset de verificación T-402",
                publisher="Agencia estatal",
                publisher_verification_status=publisher_verification_status,
                metadata_synced_at=now,
                data_updated_at=data_updated_at,
                api_active=True,
                pii_risk_level="low",
                eligibility_status=eligibility_status,
                eligibility_reasons=eligibility_reasons,
            )
        )
        await session.flush()
        for field in columns:
            session.add(
                CatalogColumn(
                    dataset_id=dataset_id,
                    field_name=field,
                    data_type="number" if field == "monto" else "text",
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
                question=question,
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


async def _quality_validator_step_count(engine, run_id: uuid.UUID) -> int:
    async with engine.connect() as connection:
        return (
            await connection.execute(
                text(
                    "SELECT count(*) FROM agent_steps "
                    "WHERE run_id = :run_id AND node = 'quality_validator'"
                ),
                {"run_id": run_id},
            )
        ).scalar_one()


async def _quality_report_row(engine, run_id: uuid.UUID):
    async with engine.connect() as connection:
        return (
            await connection.execute(
                text(
                    "SELECT q.classification, q.eligibility_status, q.warnings_user "
                    "FROM quality_reports q JOIN evidence_results e ON e.id = q.evidence_id "
                    "WHERE e.run_id = :run_id"
                ),
                {"run_id": run_id},
            )
        ).one()


async def _run_row(engine, run_id: uuid.UUID):
    async with engine.connect() as connection:
        return (
            await connection.execute(
                text("SELECT status, final_answer FROM agent_runs WHERE id = :run_id"),
                {"run_id": run_id},
            )
        ).one()


async def test_evidencia_alta_produce_claims_sin_cifras_huerfanas(engine):
    soql = "SELECT sector, sum(monto) AS total GROUP BY sector LIMIT 50"
    run_id = await seed_run(
        engine,
        question="integracion T-402 alta",
        dataset_id=DATASET_ALTA,
        publisher_verification_status="verified",
        eligibility_status="eligible",
        eligibility_reasons=[],
        data_updated_at=datetime.now(UTC),
        columns=["sector", "monto"],
    )
    tool = _t5_tool(
        canonical_soql=soql,
        rows=[{"sector": "Educación", "total": "100"}],
        source_url=f"https://www.datos.gov.co/d/{DATASET_ALTA}",
        dataset_id=DATASET_ALTA,
    )
    graph = build_graph(
        graph_dependencies(engine, dataset_id=DATASET_ALTA, soql=soql, ejecutar_soql_tool=tool),
        interrupt=False,
    )

    state = await graph.ainvoke(initial_state(run_id, "integracion T-402 alta", max_steps=10))

    assert state.get("terminal_error") is None
    assert state["evidences"][0]["quality"]["classification"] == "alta"
    assert state["evidences"][0]["quality"]["eligibility_status"] == "eligible"
    assert len(state["claims"]) == 1
    assert state["claims"][0]["display_value"] == "100 COP"
    assert state["final_answer"]["status"] == "completed"
    assert state["synthesis_attempts"] == 1  # sin reintentos por cifras huérfanas

    assert await _quality_validator_step_count(engine, run_id) == 1
    quality_row = await _quality_report_row(engine, run_id)
    assert quality_row.classification == "alta"
    assert quality_row.eligibility_status == "eligible"
    run_row = await _run_row(engine, run_id)
    assert run_row.status == "running"  # T-402 no cierra la corrida; eso es T-304


async def test_evidencia_baja_conserva_advertencia_y_llega_al_sintetizador(engine):
    soql = "SELECT sum(monto) AS total LIMIT 50"
    run_id = await seed_run(
        engine,
        question="integracion T-402 baja",
        dataset_id=DATASET_BAJA,
        publisher_verification_status="verified",
        eligibility_status="eligible",
        eligibility_reasons=[],
        data_updated_at=datetime.now(UTC) - timedelta(days=365 * 5),
        columns=["monto"],
    )
    tool = _t5_tool(
        canonical_soql=soql,
        rows=[
            {"total": "100"},
            {"total": "N/D"},
            {"total": ""},
            {"total": ""},
            {"total": ""},
        ],
        source_url=f"https://www.datos.gov.co/d/{DATASET_BAJA}",
        dataset_id=DATASET_BAJA,
    )
    synthesizer = ScriptedSynthesizer()
    graph = build_graph(
        graph_dependencies(
            engine,
            dataset_id=DATASET_BAJA,
            soql=soql,
            ejecutar_soql_tool=tool,
            synthesizer=synthesizer,
        ),
        interrupt=False,
    )

    state = await graph.ainvoke(initial_state(run_id, "integracion T-402 baja", max_steps=10))

    assert state.get("terminal_error") is None
    quality = state["evidences"][0]["quality"]
    assert quality["classification"] == "baja"
    assert quality["eligibility_status"] == "eligible"
    assert quality["warnings_user"], "la evidencia baja debe traer advertencias visibles"

    # RF-402: `baja` no es una regla dura de exclusión -- sigue sustentando claims.
    assert len(state["claims"]) == 1
    assert state["final_answer"]["status"] == "completed"

    # La advertencia estructurada (RF-403 "resumen en lenguaje claro") llega
    # intacta hasta el payload que ve el sintetizador -- la garantía dura que
    # T-402 puede exigir sin depender de que el LLM real la cite bien.
    assert synthesizer.received_classification == "baja"
    assert synthesizer.received_warnings == list(quality["warnings_user"])

    # Con un sintetizador guionado bien portado, la narrativa SÍ menciona la
    # limitación en términos cualitativos. No se verifica que reproduzca la
    # cifra exacta de la advertencia (p. ej. "60%"): `_orphan_figures` solo
    # acepta números que coincidan con `claims[].display_value`, así que un
    # LLM real citando un porcentaje de `warnings_user` sería bloqueado como
    # cifra huérfana pese a ser un cálculo determinista real de T6 -- una
    # tensión entre RF-402/403 (mostrar la advertencia) y RF-208/Art. I.1
    # (solo citar cifras respaldadas por claims) que documento como hallazgo
    # de T-402, no como algo que este test deba forzar a pasar.
    assert "limitaciones de calidad" in state["final_answer"]["narrative"]
    assert "limitaciones de calidad" in state["final_answer"]["evidence"][0]["narrative"]

    assert await _quality_validator_step_count(engine, run_id) == 1
    quality_row = await _quality_report_row(engine, run_id)
    assert quality_row.classification == "baja"


async def test_evidencia_no_recomendada_no_sustenta_claims_pese_a_ser_elegible(engine):
    """Escenario del fix: fuente incompleta (`source_url` ausente) fuerza
    `no_recomendada` aunque publicador y PII mantengan la evidencia `eligible`
    (contracts/validacion-calidad.md §3.1/§6.2, RF-404). El router igual pide
    un claim sobre ella -- `claim_builder` debe rechazarlo por su cuenta.
    """
    soql = "SELECT sector, sum(monto) AS total GROUP BY sector LIMIT 50"
    run_id = await seed_run(
        engine,
        question="integracion T-402 no_recomendada",
        dataset_id=DATASET_NO_RECOMENDADA,
        publisher_verification_status="verified",
        eligibility_status="eligible",
        eligibility_reasons=[],
        data_updated_at=datetime.now(UTC),
        columns=["sector", "monto"],
    )
    tool = _t5_tool(
        canonical_soql=soql,
        rows=[{"sector": "Educación", "total": "100"}],
        source_url=None,
        dataset_id=DATASET_NO_RECOMENDADA,
    )
    graph = build_graph(
        graph_dependencies(
            engine, dataset_id=DATASET_NO_RECOMENDADA, soql=soql, ejecutar_soql_tool=tool
        ),
        interrupt=False,
    )

    state = await graph.ainvoke(
        initial_state(run_id, "integracion T-402 no_recomendada", max_steps=10)
    )

    assert state.get("terminal_error") is None
    quality = state["evidences"][0]["quality"]
    assert quality["classification"] == "no_recomendada"
    assert quality["eligibility_status"] == "eligible"  # el eje que exponía el bug

    assert state["claims"] == []
    assert state["final_answer"]["status"] == "no_evidence"
    assert state["final_answer"]["claims"] == []
    assert state["final_answer"]["evidence"] == []

    assert await _quality_validator_step_count(engine, run_id) == 1
    quality_row = await _quality_report_row(engine, run_id)
    assert quality_row.classification == "no_recomendada"
    assert quality_row.eligibility_status == "eligible"


async def test_evidencia_diagnostic_only_no_sustenta_claims(engine):
    """Publicador no verificado: T5 puede seguir ejecutándose con fines
    diagnósticos (contrato §3.1), pero la evidencia no sustenta claims.
    """
    soql = "SELECT sector, sum(monto) AS total GROUP BY sector LIMIT 50"
    run_id = await seed_run(
        engine,
        question="integracion T-402 diagnostic_only",
        dataset_id=DATASET_DIAGNOSTIC,
        publisher_verification_status="unknown",
        eligibility_status="diagnostic_only",
        eligibility_reasons=["publisher_unknown"],
        data_updated_at=datetime.now(UTC),
        columns=["sector", "monto"],
    )
    tool = _t5_tool(
        canonical_soql=soql,
        rows=[{"sector": "Educación", "total": "100"}],
        source_url=f"https://www.datos.gov.co/d/{DATASET_DIAGNOSTIC}",
        dataset_id=DATASET_DIAGNOSTIC,
    )
    graph = build_graph(
        graph_dependencies(
            engine, dataset_id=DATASET_DIAGNOSTIC, soql=soql, ejecutar_soql_tool=tool
        ),
        interrupt=False,
    )

    state = await graph.ainvoke(
        initial_state(run_id, "integracion T-402 diagnostic_only", max_steps=10)
    )

    assert state.get("terminal_error") is None
    quality = state["evidences"][0]["quality"]
    assert quality["eligibility_status"] == "diagnostic_only"

    assert state["claims"] == []
    assert state["final_answer"]["status"] == "no_evidence"

    assert await _quality_validator_step_count(engine, run_id) == 1
    quality_row = await _quality_report_row(engine, run_id)
    assert quality_row.eligibility_status == "diagnostic_only"
