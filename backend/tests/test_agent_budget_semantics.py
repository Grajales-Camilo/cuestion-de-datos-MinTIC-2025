"""Puerta 7 de la evaluación externa (docs/instrucciones-evaluacion-agente-
post-ajustes.md): `steps_used` nunca debe exceder `max_steps` en ninguna
ruta, y cada `termination_reason` debe describir la causa real (hallazgo
T-403, 2026-07-11: antes todas las paradas por presupuesto compartían la
etiqueta `STEP_BUDGET_EXCEEDED`, sin importar si el agotamiento era real o
preventivo).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest
from langchain_core.messages import AIMessage

import app.agent.graph as graph_module
from app.agent.graph import (
    MAX_SOQL_CALLS,
    TERMINATION_INSUFFICIENT_BUDGET_FOR_ACTION,
    TERMINATION_SOQL_CALL_BUDGET_EXCEEDED,
    TERMINATION_STEP_BUDGET_EXCEEDED,
    ClaimPlannerOutput,
    GraphDependencies,
    PlannerOutput,
    RouterOutput,
    SynthesisOutput,
    _router_node,
    build_graph,
    initial_state,
)
from app.agent.persistence import DatasetEvidenceMetadata
from app.llm.factory import MAX_STRUCTURED_REPAIR_ATTEMPTS


class StaticPlanner:
    async def ainvoke(self, _messages, **_kwargs):
        return PlannerOutput(
            intention="Cuantificar recursos por sector",
            subqueries=["Encontrar la fuente", "Agregar recursos por sector"],
            recommended_next_action="Buscar en el catálogo",
        )


class NeverFinishesRouter:
    """Nunca propone "finish": obliga al grafo a parar por presupuesto
    preventivo, no por decisión propia."""

    async def ainvoke(self, _messages, **_kwargs):
        return RouterOutput.model_validate(
            {
                "action": "buscar_catalogo",
                "reasoning_summary": "Sigo buscando",
                "tool_input": {"query": "cooperación", "k": 5},
            }
        )


class AlwaysEjecutarSoqlRouter:
    async def ainvoke(self, _messages, **_kwargs):
        return RouterOutput.model_validate(
            {
                "action": "ejecutar_soql",
                "reasoning_summary": "Reintentar consulta",
                "tool_input": {
                    "dataset_id": "abcd-1234",
                    "soql": "SELECT monto LIMIT 10",
                    "purpose": "misma consulta",
                },
            }
        )


class ExplodingRouter:
    async def ainvoke(self, *_args, **_kwargs):
        raise AssertionError("no debería invocarse: el presupuesto ya está agotado")


class AlwaysInvalidRouter:
    """Nunca produce una salida valida -- agota el repair loop en cada
    turno, sin importar cuantos pasos de presupuesto (`max_steps`) queden."""

    async def ainvoke(self, _messages, **_kwargs):
        args = {
            "action": "explorar_valores",
            "reasoning_summary": "Reviso valores",
            "tool_input": {"dataset_id": "abcd-1234", "columna": "sector"},
        }
        raw = AIMessage(
            content="",
            tool_calls=[
                {"name": "RouterOutput", "args": args, "id": "call_1", "type": "tool_call"}
            ],
        )
        try:
            RouterOutput.model_validate(args)
        except Exception as exc:  # noqa: BLE001 - se reenvia como parsing_error real
            return {"raw": raw, "parsed": None, "parsing_error": exc}
        raise AssertionError("este payload siempre debe fallar la validación")


async def _no_evidence_synthesizer_ainvoke(_messages, **_kwargs):
    return SynthesisOutput(summary="No encontré evidencia suficiente en el catálogo.")


class NoEvidenceSynthesizer:
    async def ainvoke(self, messages, **kwargs):
        return await _no_evidence_synthesizer_ainvoke(messages, **kwargs)


class StaticClaimPlanner:
    async def ainvoke(self, messages, **_kwargs):
        payload = json.loads(messages[-1].content)
        evidence_id = payload["evidences"][0]["evidence_id"]
        return ClaimPlannerOutput.model_validate(
            {
                "reasoning_summary": "La evidencia contiene una cifra directa",
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


async def _metadata_loader(_dataset_id: str) -> DatasetEvidenceMetadata:
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


def _tools():
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


def _graph_deps(router, synthesizer, *, max_steps) -> GraphDependencies:
    return GraphDependencies(
        engine=None,
        planner_model=StaticPlanner(),
        router_model=router,
        synthesizer_model=synthesizer,
        claim_model=StaticClaimPlanner(),
        tools=_tools(),
        llm_provider="google",
        llm_model="gemini-2.5-flash",
        max_steps=max_steps,
        persist=False,
        metadata_loader=_metadata_loader,
    )


def _router_deps(router, *, max_steps=10, persist=False, engine=None) -> GraphDependencies:
    return GraphDependencies(
        engine=engine,
        planner_model=None,
        router_model=router,
        synthesizer_model=None,
        tools={},
        llm_provider="google",
        llm_model="gemini-2.5-flash",
        max_steps=max_steps,
        persist=persist,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "router_factory,max_steps",
    [
        (NeverFinishesRouter, 5),
        (NeverFinishesRouter, 3),
        (AlwaysEjecutarSoqlRouter, 8),
        (AlwaysInvalidRouter, 4),
    ],
)
async def test_steps_used_never_exceeds_configured_max_on_every_route(router_factory, max_steps):
    graph = build_graph(
        _graph_deps(router_factory(), NoEvidenceSynthesizer(), max_steps=max_steps), interrupt=False
    )

    result = await graph.ainvoke(
        initial_state(uuid.uuid4(), "Pregunta válida extensa", max_steps=max_steps)
    )

    assert result["steps_used"] <= max_steps


@pytest.mark.asyncio
async def test_exact_budget_exhaustion_uses_step_budget_exceeded():
    """`steps_used` ya alcanzó `max_steps` al entrar al router: ni siquiera
    debe invocarse al LLM (el doble revienta si se le llama)."""
    state = initial_state(uuid.uuid4(), "Pregunta válida extensa", max_steps=4)
    state["steps_used"] = 4

    result = await _router_node(_router_deps(ExplodingRouter(), max_steps=4), state)

    assert result["termination_reason"] == TERMINATION_STEP_BUDGET_EXCEEDED
    assert result["pending_action"] == {"action": "finish", "tool_input": {}}


@pytest.mark.asyncio
async def test_action_rejected_by_reservation_uses_insufficient_budget_for_action():
    graph = build_graph(
        _graph_deps(NeverFinishesRouter(), NoEvidenceSynthesizer(), max_steps=5), interrupt=False
    )

    result = await graph.ainvoke(
        initial_state(uuid.uuid4(), "Pregunta válida extensa", max_steps=5)
    )

    assert result["steps_used"] <= 5
    assert (
        result["final_answer"]["usage"]["termination_reason"]
        == TERMINATION_INSUFFICIENT_BUDGET_FOR_ACTION
    )


@pytest.mark.asyncio
async def test_termination_records_requested_action_remaining_and_required_steps(monkeypatch):
    captured: dict = {}

    async def fake_record_step_and_event(*_args, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(graph_module, "record_step_and_event", fake_record_step_and_event)

    state = initial_state(uuid.uuid4(), "Pregunta válida extensa", max_steps=6)
    state["steps_used"] = 2  # next_step=3, remaining=3 < minimo(ejecutar_soql)=5

    result = await _router_node(
        _router_deps(AlwaysEjecutarSoqlRouter(), max_steps=6, persist=True, engine=object()),
        state,
    )

    assert result["termination_reason"] == TERMINATION_INSUFFICIENT_BUDGET_FOR_ACTION
    detail = captured["detail"]
    assert detail["requested_action"] == "ejecutar_soql"
    assert detail["remaining_steps"] == 3
    assert detail["required_steps"] == 6


@pytest.mark.asyncio
async def test_soql_call_budget_records_requested_action_and_call_counts(monkeypatch):
    captured: dict = {}

    async def fake_record_step_and_event(*_args, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(graph_module, "record_step_and_event", fake_record_step_and_event)

    state = initial_state(uuid.uuid4(), "Pregunta válida extensa", max_steps=20)
    state["t5_calls"] = MAX_SOQL_CALLS

    result = await _router_node(
        _router_deps(AlwaysEjecutarSoqlRouter(), max_steps=20, persist=True, engine=object()),
        state,
    )

    assert result["termination_reason"] == TERMINATION_SOQL_CALL_BUDGET_EXCEEDED
    detail = captured["detail"]
    assert detail["requested_action"] == "ejecutar_soql"
    assert detail["t5_calls"] == MAX_SOQL_CALLS
    assert detail["max_t5_calls"] == MAX_SOQL_CALLS


@pytest.mark.asyncio
async def test_structured_and_input_repairs_use_separate_repair_budget():
    """El repair loop de salida estructurada (interno, acotado por
    `MAX_STRUCTURED_REPAIR_ATTEMPTS`) es independiente del presupuesto de
    pasos del grafo (`max_steps`): agotar el primero SIEMPRE cuesta
    exactamente 1 paso, sin importar qué tan grande sea `max_steps`."""
    state = initial_state(uuid.uuid4(), "Pregunta válida extensa", max_steps=100)

    result = await _router_node(_router_deps(AlwaysInvalidRouter(), max_steps=100), state)

    assert result["steps_used"] == 1
    assert result["terminal_error"]["error"]["code"] == "STRUCTURED_OUTPUT_INVALID"
    assert MAX_STRUCTURED_REPAIR_ATTEMPTS < 100  # el repair budget no escala con max_steps


@pytest.mark.asyncio
async def test_happy_path_t1_t5_t6_t7_synthesis_fits_default_budget():
    """El camino feliz estándar (T1 → T5 → T6 → T7 → síntesis) debe caber
    en el presupuesto por defecto de 10 pasos (contracts/agent-tools.md
    §Presupuestos)."""

    class HappyPathRouter:
        def __init__(self):
            self.calls = 0

        async def ainvoke(self, messages, **_kwargs):
            self.calls += 1
            payload = json.loads(messages[-1].content)
            if self.calls == 1:
                return RouterOutput.model_validate(
                    {
                        "action": "buscar_catalogo",
                        "reasoning_summary": "Busco la fuente",
                        "tool_input": {"query": "cooperación internacional", "k": 5},
                    }
                )
            if self.calls == 2:
                return RouterOutput.model_validate(
                    {
                        "action": "ejecutar_soql",
                        "reasoning_summary": "Consulto la fuente",
                        "tool_input": {
                            "dataset_id": "abcd-1234",
                            "soql": "SELECT sector, sum(monto) AS total GROUP BY sector LIMIT 50",
                            "purpose": "Recursos por sector",
                        },
                    }
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

    class HappyPathSynthesizer:
        async def ainvoke(self, messages, **_kwargs):
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

    graph = build_graph(
        _graph_deps(HappyPathRouter(), HappyPathSynthesizer(), max_steps=10), interrupt=False
    )

    result = await graph.ainvoke(
        initial_state(uuid.uuid4(), "¿Cuántos recursos recibió el Oriente?", max_steps=10)
    )

    assert result["final_answer"]["status"] == "completed"
    assert result["steps_used"] <= 10
