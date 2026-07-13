"""Puerta 3 de la evaluación externa (docs/instrucciones-evaluacion-agente-
post-ajustes.md): el repair loop de salida estructurada (`app/llm/factory.py`)
probado a nivel de `_router_node`, no solo a nivel de
`ainvoke_structured_chat_model` (ya cubierto en `test_llm_factory.py`).
Usa un doble de router que imita el sobre `{raw, parsed, parsing_error}`
real de `with_structured_output(..., include_raw=True)` para poder devolver
JSON inválido en un intento y válido en el siguiente, igual que haría el
proveedor real corrigiéndose con el feedback de errores.
"""

from __future__ import annotations

import uuid

import pytest
from langchain_core.messages import AIMessage

from app.agent.graph import (
    MAX_ROUTER_FINISH_REPAIR_ATTEMPTS,
    GraphDependencies,
    RouterOutput,
    _router_node,
    initial_state,
)
from app.llm.factory import MAX_STRUCTURED_REPAIR_ATTEMPTS

VALID_EVIDENCE_ID = "9a2b1c3d-0000-0000-0000-000000000000"

MISSING_FIELD_ARGS = {
    "action": "explorar_valores",
    "reasoning_summary": "Reviso cómo aparece el evento",
    "tool_input": {"dataset_id": "abcd-1234", "columna": "nombre_evento"},
}

VALID_FIELD_ARGS = {
    "action": "explorar_valores",
    "reasoning_summary": "Reviso cómo aparece el evento",
    "tool_input": {
        "dataset_id": "abcd-1234",
        "columna": "nombre_evento",
        "termino_busqueda": "varicela",
    },
}


def _validation_error(payload: dict) -> Exception:
    try:
        RouterOutput.model_validate(payload)
    except Exception as exc:  # noqa: BLE001 - se necesita el ValidationError real
        return exc
    raise AssertionError("se esperaba que la validación fallara para este payload")


class EnvelopeRouterDouble:
    """Imita el sobre `{raw, parsed, parsing_error}` real que produce
    `with_structured_output(..., include_raw=True)` cuando la validación de
    Pydantic falla, para poder probar el repair loop end-to-end a través de
    `_router_node` con LLM guionado (sin red real)."""

    def __init__(self, script: list[dict]):
        self._script = list(script)
        self.calls = 0

    async def ainvoke(self, _messages, **_kwargs):
        self.calls += 1
        args = self._script.pop(0)
        usage = {"input_tokens": 10 * self.calls, "output_tokens": 5 * self.calls}
        usage["total_tokens"] = usage["input_tokens"] + usage["output_tokens"]
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
            usage_metadata=usage,
        )
        try:
            parsed = RouterOutput.model_validate(args)
        except Exception as exc:  # noqa: BLE001 - se reenvia como parsing_error real
            return {"raw": raw, "parsed": None, "parsing_error": exc}
        return {"raw": raw, "parsed": parsed, "parsing_error": None}


class AlwaysInvalidRouterDouble:
    """Nunca se corrige, sin importar cuántas veces se le pida -- prueba el
    límite `MAX_STRUCTURED_REPAIR_ATTEMPTS` y el error terminal específico."""

    def __init__(self, args: dict):
        self._args = args
        self.calls = 0

    async def ainvoke(self, _messages, **_kwargs):
        self.calls += 1
        raw = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "RouterOutput",
                    "args": self._args,
                    "id": f"call_{self.calls}",
                    "type": "tool_call",
                }
            ],
        )
        return {"raw": raw, "parsed": None, "parsing_error": _validation_error(self._args)}


def _deps(router) -> GraphDependencies:
    return GraphDependencies(
        engine=None,
        planner_model=None,
        router_model=router,
        synthesizer_model=None,
        tools={},
        llm_provider="google",
        llm_model="gemini-2.5-flash",
        max_steps=10,
        persist=False,
    )


def _fresh_state():
    return initial_state(uuid.uuid4(), "¿Qué eventos tuvieron mayor volumen?", max_steps=10)


@pytest.mark.asyncio
async def test_router_repairs_invalid_tool_input_once_with_validation_feedback():
    router = EnvelopeRouterDouble([MISSING_FIELD_ARGS, VALID_FIELD_ARGS])

    result = await _router_node(_deps(router), _fresh_state())

    assert router.calls == 2
    assert result["pending_action"]["action"] == "explorar_valores"
    assert result["pending_action"]["tool_input"]["termino_busqueda"] == "varicela"


@pytest.mark.asyncio
async def test_router_repairs_missing_required_tool_field():
    router = EnvelopeRouterDouble([MISSING_FIELD_ARGS, VALID_FIELD_ARGS])

    result = await _router_node(_deps(router), _fresh_state())

    assert router.calls == 2
    assert result["pending_action"]["action"] == "explorar_valores"
    assert result["pending_action"]["tool_input"]["termino_busqueda"] == "varicela"


@pytest.mark.asyncio
async def test_structured_repair_is_bounded_to_two_attempts():
    router = AlwaysInvalidRouterDouble(MISSING_FIELD_ARGS)

    result = await _router_node(_deps(router), _fresh_state())

    # intento inicial + MAX_STRUCTURED_REPAIR_ATTEMPTS reparaciones, nunca mas
    assert router.calls == 1 + MAX_STRUCTURED_REPAIR_ATTEMPTS
    assert result["terminal_error"]["error"]["code"] == "STRUCTURED_OUTPUT_INVALID"


@pytest.mark.asyncio
async def test_unrepairable_output_ends_with_specific_error_not_generic_provider_error():
    """Un error de repair loop agotado NO debe confundirse con una caída
    real del proveedor (red, cuota, timeout) -- deben ser códigos
    distintos para que el diagnóstico (RF-703) no los mezcle."""
    router = AlwaysInvalidRouterDouble(MISSING_FIELD_ARGS)

    result = await _router_node(_deps(router), _fresh_state())

    error = result["terminal_error"]["error"]
    assert error["code"] == "STRUCTURED_OUTPUT_INVALID"
    assert error["code"] != "LLM_PROVIDER_ERROR"
    assert error["retryable"] is False


@pytest.mark.asyncio
async def test_structured_repair_does_not_consume_semantic_step_budget():
    """Dos llamadas internas al LLM (una invalida + una reparada) deben
    contar como UN solo paso del grafo, no dos -- el repair loop vive dentro
    de `ainvoke_structured_chat_model`, el nodo del grafo se ejecuta una
    sola vez."""
    router = EnvelopeRouterDouble([MISSING_FIELD_ARGS, VALID_FIELD_ARGS])
    state = _fresh_state()
    assert state["steps_used"] == 0

    result = await _router_node(_deps(router), state)

    assert router.calls == 2
    assert result["steps_used"] == 1


@pytest.mark.asyncio
async def test_structured_repairs_use_separate_repair_budget_from_step_budget():
    """El repair loop se agota tras `MAX_STRUCTURED_REPAIR_ATTEMPTS`
    intentos de LLM, pero eso sigue siendo UN solo paso registrado en
    `agent_steps` -- confirma que el presupuesto de reparación (interno a
    `ainvoke_structured_chat_model`) es independiente del presupuesto de
    pasos del grafo (`steps_used`/`max_steps`)."""
    router = AlwaysInvalidRouterDouble(MISSING_FIELD_ARGS)
    state = _fresh_state()

    result = await _router_node(_deps(router), state)

    assert router.calls == 1 + MAX_STRUCTURED_REPAIR_ATTEMPTS
    assert result["steps_used"] == 1


@pytest.mark.asyncio
async def test_structured_repair_preserves_usage_and_attempt_trace():
    """Los tokens/costo de AMBOS intentos (el fallido y el reparado) deben
    quedar contados -- no solo los del ultimo intento (RNF-009, Art.
    VII.3)."""
    router = EnvelopeRouterDouble([MISSING_FIELD_ARGS, VALID_FIELD_ARGS])

    result = await _router_node(_deps(router), _fresh_state())

    assert len(result["usage"]) == 1  # un solo registro de uso para el paso "router"
    usage = result["usage"][0]
    assert usage["input_tokens"] == 10 + 20  # intento 1 (calls=1) + intento 2 (calls=2)
    assert usage["output_tokens"] == 5 + 10


# --- Regresión smoke real (2026-07-12, success_rate=20%): abandono ---------
# --- prematuro del router pese a la regla de router_v1.md ------------------
#
# pilot-004/005/007/008 mostraron el LLM real encontrando (y a veces hasta
# perfilando) un dataset elegible y declarando `finish` sin intentar
# ejecutar_soql -- la regla de prompt sola no bastó. `_has_untried_eligible_
# dataset` + la reparación semántica dentro del mismo paso de `_router_node`
# cierran esto de forma determinista, igual que el guard de `evidence_id`.


class PrematureFinishThenEjecutarSoqlRouter:
    def __init__(self):
        self.calls = 0

    async def ainvoke(self, _messages, **_kwargs):
        self.calls += 1
        if self.calls == 1:
            return RouterOutput.model_validate(
                {
                    "action": "finish",
                    "reasoning_summary": "Ya reuní lo necesario para preparar la respuesta",
                    "tool_input": {},
                }
            )
        return RouterOutput.model_validate(
            {
                "action": "ejecutar_soql",
                "reasoning_summary": "Consulto el dataset elegible que ya encontré",
                "tool_input": {
                    "dataset_id": "abcd-1234",
                    "soql": "SELECT sector, sum(monto) AS total GROUP BY sector",
                    "purpose": "Recursos por sector",
                },
            }
        )


class AlwaysFinishesRouter:
    def __init__(self):
        self.calls = 0

    async def ainvoke(self, _messages, **_kwargs):
        self.calls += 1
        return RouterOutput.model_validate(
            {
                "action": "finish",
                "reasoning_summary": "Este dataset no tiene columnas pertinentes a la pregunta",
                "tool_input": {},
            }
        )


def _state_with_untried_eligible_dataset():
    state = _fresh_state()
    state["observations"] = [
        {
            "tool": "buscar_catalogo",
            "input": {"query": "cooperación internacional"},
            "output": {
                "ok": True,
                "results": [
                    {
                        "dataset_id": "abcd-1234",
                        "name": "Cooperación internacional",
                        "eligibility_status": "eligible",
                    }
                ],
            },
        }
    ]
    return state


@pytest.mark.asyncio
async def test_router_repairs_premature_finish_when_eligible_dataset_untried():
    router = PrematureFinishThenEjecutarSoqlRouter()

    result = await _router_node(_deps(router), _state_with_untried_eligible_dataset())

    assert router.calls == 2
    assert result["pending_action"]["action"] == "ejecutar_soql"
    # La reparación ocurrió DENTRO del mismo paso: no cuenta como un paso
    # adicional del grafo, igual que la reparación de esquema.
    assert result["steps_used"] == 1


@pytest.mark.asyncio
async def test_router_accepts_finish_after_premature_finish_repair_is_exhausted():
    """Si el LLM insiste en `finish` incluso tras el mensaje de reparación,
    se acepta su decisión (pudo tener una razón legítima) -- el mecanismo
    solo le da una oportunidad extra de reconsiderar, nunca lo obliga."""
    router = AlwaysFinishesRouter()

    result = await _router_node(_deps(router), _state_with_untried_eligible_dataset())

    # intento inicial + MAX_ROUTER_FINISH_REPAIR_ATTEMPTS reparaciones.
    assert router.calls == 1 + MAX_ROUTER_FINISH_REPAIR_ATTEMPTS
    assert result["pending_action"]["action"] == "finish"
    assert result["steps_used"] == 1


def _state_with_blocked_evidence_after_soql():
    """Regresión pilot-002 (2026-07-12): ejecutar_soql SÍ se intentó
    (t5_calls=1) pero la evidencia resultante quedó `blocked` por PII/
    agregación insuficiente -- no es evidencia usable, así que `finish`
    sigue siendo prematuro aunque `evidences` ya no esté vacío."""
    state = _fresh_state()
    state["t5_calls"] = 1
    state["evidences"] = [
        {
            "evidence_id": "e1",
            "dataset_id": "abcd-1234",
            "quality": {"eligibility_status": "blocked", "classification": "alta"},
        }
    ]
    return state


@pytest.mark.asyncio
async def test_router_repairs_premature_finish_when_only_evidence_is_blocked():
    router = PrematureFinishThenEjecutarSoqlRouter()

    result = await _router_node(_deps(router), _state_with_blocked_evidence_after_soql())

    assert router.calls == 2
    assert result["pending_action"]["action"] == "ejecutar_soql"
    assert result["steps_used"] == 1


@pytest.mark.asyncio
async def test_router_accepts_finish_when_evidence_is_already_usable():
    """Con evidencia elegible y no `no_recomendada` ya reunida, `finish` es
    una decisión legítima de inmediato -- el guard no debe intervenir."""
    router = AlwaysFinishesRouter()
    state = _fresh_state()
    state["t5_calls"] = 1
    state["evidences"] = [
        {
            "evidence_id": "e1",
            "dataset_id": "abcd-1234",
            "quality": {"eligibility_status": "eligible", "classification": "alta"},
        }
    ]

    result = await _router_node(_deps(router), state)

    assert router.calls == 1
    assert result["pending_action"]["action"] == "finish"


@pytest.mark.asyncio
async def test_router_does_not_repair_finish_when_no_eligible_dataset_was_found():
    """`finish` inmediato sin ninguna observación (o sin ningún dataset
    elegible) sigue siendo un motivo válido de abstención -- el guard no
    debe dispararse sin una pista real que investigar."""
    router = AlwaysFinishesRouter()

    result = await _router_node(_deps(router), _fresh_state())

    assert router.calls == 1
    assert result["pending_action"]["action"] == "finish"
