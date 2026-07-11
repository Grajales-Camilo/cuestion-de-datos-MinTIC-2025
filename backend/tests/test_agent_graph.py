from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest

from app.agent.graph import (
    EVIDENCE_EVENT_MAX_BYTES,
    EVIDENCE_ROWS_MAX_BYTES,
    GraphDependencies,
    NoEvidenceReport,
    PlannerOutput,
    ReviewedDataset,
    RouterOutput,
    SynthesisOutput,
    _bounded_rows,
    _evidence_event_payload,
    build_graph,
    initial_state,
)
from app.agent.persistence import DatasetEvidenceMetadata


class StaticModel:
    def __init__(self, value):
        self.value = value
        self.calls = 0

    async def ainvoke(self, _input, **_kwargs):
        self.calls += 1
        return self.value


class ScriptedRouter:
    def __init__(self, *, unknown_tool: bool = False):
        self.calls = 0
        self.unknown_tool = unknown_tool

    async def ainvoke(self, messages, **_kwargs):
        self.calls += 1
        payload = json.loads(messages[-1].content)
        if self.unknown_tool:
            return RouterOutput(
                action="consultar_internet",
                reasoning_summary="Intento de herramienta no permitida",
                tool_input={},
            )
        if self.calls == 1:
            return RouterOutput(
                action="buscar_catalogo",
                reasoning_summary="Primero ubico una fuente pertinente",
                tool_input={"query": "cooperación internacional Oriente antioqueño", "k": 5},
            )
        if self.calls == 2:
            return RouterOutput(
                action="ejecutar_soql",
                reasoning_summary="La fuente tiene las columnas necesarias",
                tool_input={
                    "dataset_id": "abcd-1234",
                    "soql": "SELECT sector, sum(monto) AS total GROUP BY sector LIMIT 50",
                    "purpose": "Recursos por sector",
                },
            )
        evidence_id = payload["evidences"][0]["evidence_id"]
        return RouterOutput.model_validate(
            {
                "action": "finish",
                "reasoning_summary": "La evidencia ya permite responder",
                "tool_input": {},
                "claim_specs_by_evidence": [
                    {
                        "evidence_id": evidence_id,
                        "claim_specs": [
                            {
                                "claim_type": "direct",
                                "description": "Recursos del sector educación",
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


class SuccessfulSynthesizer:
    def __init__(self):
        self.calls = 0

    async def ainvoke(self, messages, **_kwargs):
        self.calls += 1
        payload = json.loads(messages[-1].content)
        claim = payload["claims"][0]
        evidence_id = payload["evidences"][0]["evidence_id"]
        value = claim["display_value"]
        return SynthesisOutput.model_validate(
            {
                "summary": f"La fuente registra {value}.",
                "narrative": f"La evidencia oficial respalda {value}.",
                "evidence_narratives": [
                    {"evidence_id": evidence_id, "narrative": f"El resultado es {value}."}
                ],
            }
        )


class OrphanSynthesizer:
    def __init__(self):
        self.calls = 0

    async def ainvoke(self, _messages, **_kwargs):
        self.calls += 1
        return SynthesisOutput(summary="La fuente registra 999 casos.")


class BudgetRouter:
    async def ainvoke(self, _messages, **_kwargs):
        return RouterOutput(
            action="buscar_catalogo",
            reasoning_summary="Quiero seguir buscando",
            tool_input={"query": "cooperación", "k": 5},
        )


class RepeatingT5Router:
    async def ainvoke(self, _messages, **_kwargs):
        return RouterOutput(
            action="ejecutar_soql",
            reasoning_summary="Reintentar consulta",
            tool_input={
                "dataset_id": "abcd-1234",
                "soql": "SELECT monto LIMIT 10",
                "purpose": "misma consulta",
            },
        )


class NoEvidenceSynthesizer:
    async def ainvoke(self, _messages, **_kwargs):
        return SynthesisOutput(
            summary="No encontré evidencia suficiente en el catálogo.",
            no_evidence_report=NoEvidenceReport(
                reason="Las fuentes revisadas no tienen el nivel territorial solicitado.",
                datasets_reviewed=[
                    ReviewedDataset(
                        dataset_id="abcd-1234",
                        name="Cooperación internacional",
                        why_rejected="No presenta la desagregación necesaria.",
                    )
                ],
                suggestions=["Reformular la consulta por departamento."],
            ),
        )


async def metadata_loader(_dataset_id: str) -> DatasetEvidenceMetadata:
    return DatasetEvidenceMetadata(
        dataset_id="abcd-1234",
        name="Cooperación internacional",
        publisher="Agencia estatal",
        official_publisher_id="agencia-estatal",
        pii_risk_level="low",
        eligibility_status="eligible",
        eligibility_reasons=(),
        data_updated_at=datetime.now(UTC),
        column_pii={"sector": "low", "monto": "low"},
        column_types={"sector": "text", "monto": "number"},
    )


def tools():
    async def buscar(_raw_input):
        return {
            "ok": True,
            "results": [
                {
                    "dataset_id": "abcd-1234",
                    "name": "Cooperación internacional",
                    "eligibility_status": "eligible",
                    "columns": ["sector", "monto"],
                }
            ],
        }

    async def ejecutar(_raw_input):
        return {
            "ok": True,
            "canonical_soql": "SELECT sector, sum(monto) AS total GROUP BY sector LIMIT 50",
            "rows": [{"sector": "Educación", "total": "100"}],
            "row_count": 1,
            "executed_at": datetime.now(UTC).isoformat(),
            "source_url": "https://www.datos.gov.co/d/abcd-1234",
            "llm_view": {"rows_shown": 1},
        }

    async def unused(_raw_input):
        return {"ok": False, "error": {"code": "UNUSED", "message": "unused"}}

    return {
        "buscar_catalogo": buscar,
        "perfilar_dataset": unused,
        "resolver_geografia": unused,
        "explorar_valores": unused,
        "ejecutar_soql": ejecutar,
    }


def deps(router, synthesizer, *, max_steps=10):
    return GraphDependencies(
        engine=None,
        planner_model=StaticModel(
            PlannerOutput(
                intention="Cuantificar recursos por sector",
                subqueries=["Encontrar la fuente", "Agregar recursos por sector"],
                recommended_next_action="Buscar en el catálogo",
            )
        ),
        router_model=router,
        synthesizer_model=synthesizer,
        tools=tools(),
        llm_provider="google",
        llm_model="gemini-2.5-flash",
        max_steps=max_steps,
        persist=False,
        metadata_loader=metadata_loader,
    )


@pytest.mark.asyncio
async def test_real_graph_runs_t6_t7_and_blocks_orphans():
    synthesizer = SuccessfulSynthesizer()
    graph = build_graph(deps(ScriptedRouter(), synthesizer), interrupt=False)
    result = await graph.ainvoke(
        initial_state(uuid.uuid4(), "¿Cuántos recursos recibió el Oriente?", max_steps=10)
    )

    assert result["final_answer"]["status"] == "completed"
    assert result["steps_used"] <= 10
    assert len(result["evidences"]) == 1
    assert result["evidences"][0]["quality"]["eligibility_status"] == "eligible"
    assert result["claims"][0]["display_value"] == "100 COP"
    assert synthesizer.calls == 1


@pytest.mark.asyncio
async def test_unknown_tool_is_controlled_graph_error():
    graph = build_graph(
        deps(ScriptedRouter(unknown_tool=True), NoEvidenceSynthesizer()), interrupt=False
    )
    result = await graph.ainvoke(
        initial_state(uuid.uuid4(), "Pregunta válida extensa", max_steps=10)
    )

    assert result["terminal_error"]["error"]["code"] == "INTERNAL"
    assert result["steps_used"] == 2


@pytest.mark.asyncio
async def test_orphan_figures_trigger_two_resynthesis_retries_then_failure():
    synthesizer = OrphanSynthesizer()
    graph = build_graph(deps(ScriptedRouter(), synthesizer), interrupt=False)
    result = await graph.ainvoke(
        initial_state(uuid.uuid4(), "Pregunta válida extensa", max_steps=10)
    )

    assert synthesizer.calls == 3
    assert result["synthesis_attempts"] == 3
    assert result["terminal_error"]["error"]["code"] == "INTERNAL"


@pytest.mark.asyncio
async def test_step_budget_forces_no_evidence_without_exceeding_limit():
    graph = build_graph(deps(BudgetRouter(), NoEvidenceSynthesizer(), max_steps=5), interrupt=False)
    result = await graph.ainvoke(
        initial_state(uuid.uuid4(), "Pregunta válida extensa", max_steps=5)
    )

    assert result["final_answer"]["status"] == "no_evidence"
    assert result["final_answer"]["usage"]["termination_reason"] == "STEP_BUDGET_EXCEEDED"
    assert result["steps_used"] <= 5


@pytest.mark.asyncio
async def test_soql_syntax_allows_only_two_corrections_after_initial_attempt():
    calls = 0

    async def syntax_error(_raw_input):
        nonlocal calls
        calls += 1
        return {"ok": False, "error": {"code": "SOQL_SYNTAX", "message": "sintaxis"}}

    graph_deps = deps(RepeatingT5Router(), NoEvidenceSynthesizer(), max_steps=20)
    graph_deps.tools["ejecutar_soql"] = syntax_error
    graph = build_graph(graph_deps, interrupt=False)
    result = await graph.ainvoke(
        initial_state(uuid.uuid4(), "Pregunta válida extensa", max_steps=20)
    )

    assert calls == 3  # intento inicial + dos autocorrecciones
    assert result["final_answer"]["status"] == "no_evidence"


@pytest.mark.asyncio
async def test_at_most_four_soql_calls_per_run():
    calls = 0

    async def inactive(_raw_input):
        nonlocal calls
        calls += 1
        return {
            "ok": False,
            "error": {"code": "DATASET_INACTIVE", "message": "dataset inactivo"},
        }

    graph_deps = deps(RepeatingT5Router(), NoEvidenceSynthesizer(), max_steps=25)
    graph_deps.tools["ejecutar_soql"] = inactive
    graph = build_graph(graph_deps, interrupt=False)
    await graph.ainvoke(initial_state(uuid.uuid4(), "Pregunta válida extensa", max_steps=25))

    assert calls == 4


def test_evidence_and_event_byte_budgets_are_enforced():
    rows = [{"texto": "x" * 20_000, "valor": index} for index in range(100)]
    bounded = _bounded_rows(rows, EVIDENCE_ROWS_MAX_BYTES)
    event = _evidence_event_payload({"rows": bounded, "dataset_id": "abcd-1234"})

    assert len(json.dumps(bounded).encode()) <= EVIDENCE_ROWS_MAX_BYTES
    assert len(json.dumps(event).encode()) <= EVIDENCE_EVENT_MAX_BYTES
    assert event["rows_truncated"] is True
