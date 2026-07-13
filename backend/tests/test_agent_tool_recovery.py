"""Puerta 4 de la evaluación externa (docs/instrucciones-evaluacion-agente-
post-ajustes.md): un `tool_input` inválido debe corregirse ANTES de llamar a
la herramienta (repair loop de salida estructurada), no después con un
`INVALID_INPUT` que ya gastó un paso completo. Complementa
`test_agent_structured_repair.py` (que prueba `_router_node` aislado) con el
grafo completo (`build_graph`), confirmando que la herramienta real nunca ve
un input inválido.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest
from langchain_core.messages import AIMessage

from app.agent.graph import (
    ClaimPlannerOutput,
    GraphDependencies,
    PlannerOutput,
    RouterOutput,
    SynthesisOutput,
    build_graph,
    initial_state,
)
from app.agent.persistence import DatasetEvidenceMetadata

MISSING_TERMINO_ARGS = {
    "action": "explorar_valores",
    "reasoning_summary": "Reviso cómo aparece el evento",
    "tool_input": {"dataset_id": "abcd-1234", "columna": "nombre_evento"},
}

VALID_EXPLORAR_ARGS = {
    "action": "explorar_valores",
    "reasoning_summary": "Reviso cómo aparece el evento",
    "tool_input": {
        "dataset_id": "abcd-1234",
        "columna": "nombre_evento",
        "termino_busqueda": "varicela",
    },
}

FINISH_NO_EVIDENCE_ARGS = {
    "action": "finish",
    "reasoning_summary": "No logré verificar el dato",
    "tool_input": {},
}


def _validation_error(payload: dict) -> Exception:
    try:
        RouterOutput.model_validate(payload)
    except Exception as exc:  # noqa: BLE001 - se necesita el ValidationError real
        return exc
    raise AssertionError("se esperaba que la validación fallara para este payload")


class EnvelopeRouterScript:
    """Devuelve, en orden, cada entrada de `script`. Un `dict` se valida
    como si fuera la salida cruda del proveedor (puede fallar, imitando el
    sobre `{raw, parsed, parsing_error}` real); útil para intercalar un
    intento inválido antes de uno válido dentro del MISMO turno del router
    (el repair loop de `ainvoke_structured_chat_model` los consume sin que
    el grafo se entere)."""

    def __init__(self, script: list[dict]):
        self._script = list(script)
        self.calls = 0

    async def ainvoke(self, _messages, **_kwargs):
        self.calls += 1
        args = self._script.pop(0)
        raw = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "RouterOutput",
                    "args": args,
                    "id": f"call_{self.calls}",
                    "type": "tool_call",
                }
            ],
            usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        )
        try:
            parsed = RouterOutput.model_validate(args)
        except Exception as exc:  # noqa: BLE001 - se reenvia como parsing_error real
            return {"raw": raw, "parsed": None, "parsing_error": exc}
        return {"raw": raw, "parsed": parsed, "parsing_error": None}


class AlwaysInvalidExplorarValoresRouter:
    def __init__(self):
        self.calls = 0

    async def ainvoke(self, _messages, **_kwargs):
        self.calls += 1
        raw = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "RouterOutput",
                    "args": MISSING_TERMINO_ARGS,
                    "id": f"call_{self.calls}",
                    "type": "tool_call",
                }
            ],
        )
        return {
            "raw": raw,
            "parsed": None,
            "parsing_error": _validation_error(MISSING_TERMINO_ARGS),
        }


class ReactsToNonTextColumnRouter:
    """Guion determinista (no LLM real) que demuestra que el grafo SURTE el
    error `EXPLORAR_VALORES_NOT_TEXT` de vuelta al router en `observations`
    -- lo que el router real haga con esa señal se verifica aparte con LLM
    real (Art. IV.2); esta prueba solo confirma que el plomero del grafo
    entrega la señal correcta y que el router puede reaccionar con
    `ejecutar_soql` directo, como pide el contrato (contracts/agent-tools.md
    §T4)."""

    def __init__(self):
        self.calls = 0
        self.saw_not_text_error = False

    async def ainvoke(self, messages, **_kwargs):
        self.calls += 1
        payload = json.loads(messages[-1].content)
        if self.calls == 1:
            return RouterOutput.model_validate(
                {
                    "action": "buscar_catalogo",
                    "reasoning_summary": "Busco la fuente de eventos",
                    "tool_input": {"query": "eventos de salud pública", "k": 5},
                }
            )
        if self.calls == 2:
            return RouterOutput.model_validate(
                {
                    "action": "explorar_valores",
                    "reasoning_summary": "Reviso el valor del año",
                    "tool_input": {
                        "dataset_id": "abcd-1234",
                        "columna": "a_o",
                        "termino_busqueda": "2024",
                    },
                }
            )
        observations = payload.get("observations", [])
        last_output = observations[-1].get("output", {}) if observations else {}
        error_code = last_output.get("error", {}).get("code")
        if self.calls == 3:
            self.saw_not_text_error = error_code == "EXPLORAR_VALORES_NOT_TEXT"
            return RouterOutput.model_validate(
                {
                    "action": "ejecutar_soql",
                    "reasoning_summary": "Filtro directo por año sin explorar_valores",
                    "tool_input": {
                        "dataset_id": "abcd-1234",
                        "soql": "SELECT sector, sum(monto) AS total WHERE a_o=2024 GROUP BY sector",
                        "purpose": "Filtrar por año sin explorar_valores",
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


class NoEvidenceSynthesizerDouble:
    def __init__(self):
        self.calls = 0

    async def ainvoke(self, _messages, **_kwargs):
        self.calls += 1
        return SynthesisOutput(summary="No encontré evidencia suficiente en el catálogo.")


class SuccessfulSynthesizerDouble:
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
                "evidence_narratives": [
                    {"evidence_id": evidence_id, "narrative": f"El resultado es {value}."}
                ],
            }
        )


async def _metadata_loader(_dataset_id: str) -> DatasetEvidenceMetadata:
    return DatasetEvidenceMetadata(
        dataset_id="abcd-1234",
        name="Eventos de salud pública",
        publisher="Ministerio de Salud",
        official_publisher_id="min-salud",
        pii_risk_level="low",
        eligibility_status="eligible",
        eligibility_reasons=(),
        data_updated_at=datetime.now(UTC),
        column_pii={"sector": "low", "total": "low"},
        column_types={"sector": "text", "total": "number"},
    )


def _tools(*, explorar_valores=None, ejecutar_soql=None):
    calls: dict[str, int] = {"explorar_valores": 0, "ejecutar_soql": 0}

    async def buscar(_raw_input):
        return {
            "ok": True,
            "results": [
                {
                    "dataset_id": "abcd-1234",
                    "name": "Eventos de salud pública",
                    "eligibility_status": "eligible",
                    "columns": ["a_o", "sector", "total"],
                }
            ],
        }

    async def default_explorar(raw_input):
        calls["explorar_valores"] += 1
        assert "termino_busqueda" in raw_input, "la herramienta no debe recibir input incompleto"
        return {"ok": True, "values": ["ejemplo"], "truncated": False}

    async def default_ejecutar(_raw_input):
        calls["ejecutar_soql"] += 1
        return {
            "ok": True,
            "canonical_soql": (
                "SELECT sector, sum(monto) AS total WHERE a_o = 2024 GROUP BY sector LIMIT 50"
            ),
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
        "explorar_valores": explorar_valores or default_explorar,
        "ejecutar_soql": ejecutar_soql or default_ejecutar,
    }, calls


class StaticPlanner:
    async def ainvoke(self, _messages, **_kwargs):
        return PlannerOutput(
            intention="Verificar el evento con mayor volumen reportado",
            subqueries=["Encontrar la fuente", "Filtrar por año"],
            recommended_next_action="Buscar en el catálogo",
        )


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
                                "description": "Total del sector",
                                "source_row_indexes": [0],
                                "columns": ["total"],
                            }
                        ],
                    }
                ],
            }
        )


def _deps(router, synthesizer, tools_dict, *, max_steps=15) -> GraphDependencies:
    return GraphDependencies(
        engine=None,
        planner_model=StaticPlanner(),
        router_model=router,
        synthesizer_model=synthesizer,
        claim_model=StaticClaimPlanner(),
        tools=tools_dict,
        llm_provider="google",
        llm_model="gemini-2.5-flash",
        max_steps=max_steps,
        persist=False,
        metadata_loader=_metadata_loader,
    )


@pytest.mark.asyncio
async def test_invalid_input_returns_to_repair_path_not_general_router_loop():
    """El repair loop corrige el input DENTRO del mismo turno del router;
    la herramienta jamás ve la forma incompleta ni se dispara un segundo
    turno de router para "reintentar" -- confirmado con el guard del propio
    doble de herramienta (`assert "termino_busqueda" in raw_input`)."""
    router = EnvelopeRouterScript(
        [MISSING_TERMINO_ARGS, VALID_EXPLORAR_ARGS, FINISH_NO_EVIDENCE_ARGS]
    )
    tools_dict, calls = _tools()
    graph = build_graph(_deps(router, NoEvidenceSynthesizerDouble(), tools_dict), interrupt=False)

    result = await graph.ainvoke(
        initial_state(uuid.uuid4(), "¿Cómo aparece la varicela en el dataset?", max_steps=15)
    )

    assert result.get("terminal_error") is None
    assert calls["explorar_valores"] == 1


@pytest.mark.asyncio
async def test_corrected_explorar_valores_input_executes_once():
    router = EnvelopeRouterScript(
        [MISSING_TERMINO_ARGS, VALID_EXPLORAR_ARGS, FINISH_NO_EVIDENCE_ARGS]
    )
    tools_dict, calls = _tools()
    graph = build_graph(_deps(router, NoEvidenceSynthesizerDouble(), tools_dict), interrupt=False)

    await graph.ainvoke(
        initial_state(uuid.uuid4(), "¿Cómo aparece la varicela en el dataset?", max_steps=15)
    )

    assert calls["explorar_valores"] == 1
    assert calls["ejecutar_soql"] == 0


@pytest.mark.asyncio
async def test_repeated_invalid_input_stops_with_input_repair_exhausted():
    router = AlwaysInvalidExplorarValoresRouter()
    tools_dict, calls = _tools()
    graph = build_graph(_deps(router, NoEvidenceSynthesizerDouble(), tools_dict), interrupt=False)

    result = await graph.ainvoke(
        initial_state(uuid.uuid4(), "¿Cómo aparece la varicela en el dataset?", max_steps=15)
    )

    assert calls["explorar_valores"] == 0  # nunca llega a recibir un input invalido
    assert result["terminal_error"]["error"]["code"] == "STRUCTURED_OUTPUT_INVALID"


@pytest.mark.asyncio
async def test_non_text_column_error_causes_direct_soql_strategy():
    router = ReactsToNonTextColumnRouter()

    async def not_text_explorar(_raw_input):
        return {
            "ok": False,
            "error": {
                "code": "EXPLORAR_VALORES_NOT_TEXT",
                "message": "la columna a_o no es de texto; usa ejecutar_soql directo",
            },
        }

    tools_dict, calls = _tools(explorar_valores=not_text_explorar)
    graph = build_graph(_deps(router, SuccessfulSynthesizerDouble(), tools_dict), interrupt=False)

    result = await graph.ainvoke(
        initial_state(uuid.uuid4(), "¿Cuántos recursos recibió el sector en 2024?", max_steps=15)
    )

    assert router.saw_not_text_error is True
    assert calls["ejecutar_soql"] == 1
    assert result["final_answer"]["status"] == "completed"
