"""Puerta 6 de la evaluación externa (docs/instrucciones-evaluacion-agente-
post-ajustes.md): el contrato del componente responsable de construir claims
-- no se separó en un nodo `claim_planner` dedicado (ver tasks.md, fuera de
alcance deliberado), así que estas pruebas cubren `ClaimSpecPayload`
(esquema propuesto por el router) + `_claim_builder_node` (T7 integrado al
grafo) + el loop de reparación acotado (`claim_builder` → `router` cuando
todo se rechaza). `app/quality/claims.py` (la función pura `build_claims`)
ya tiene su propia cobertura exhaustiva en `test_claims.py`; aquí se prueba
la INTEGRACIÓN con el grafo, no se repite esa lógica pura.

Caso obligatorio de regresión (Hallazgo T-403, 2026-07-11, ejecución real
run_id=32ad6d77-...): filas con `nombre_evento` y `total_casos` deben
producir claims sobre `total_casos`, con `nombre_evento` como contexto en
`description`, nunca como segunda columna de un claim "direct".
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest
from langgraph.graph import END
from pydantic import ValidationError

from app.agent.graph import (
    ClaimPlannerOutput,
    GraphDependencies,
    PlannerOutput,
    RouterOutput,
    SynthesisOutput,
    _after_claim_builder,
    _claim_builder_node,
    _claim_planner_node,
    build_graph,
    initial_state,
)
from app.agent.persistence import DatasetEvidenceMetadata


def _claim_builder_deps() -> GraphDependencies:
    return GraphDependencies(
        engine=None,
        planner_model=None,
        router_model=None,
        synthesizer_model=None,
        tools={},
        llm_provider="google",
        llm_model="gemini-2.5-flash",
        persist=False,
    )


def _state_with_evidence(
    *, rows: list[dict], claim_specs: list[dict], evidence_id: str | None = None
) -> dict:
    evidence_id = evidence_id or str(uuid.uuid4())
    return {
        "run_id": str(uuid.uuid4()),
        "evidences": [
            {
                "evidence_id": evidence_id,
                "dataset_id": "4hyg-wa9d",
                "soql_query": "SELECT nombre_evento, total_casos GROUP BY nombre_evento",
                "rows": rows,
                "quality": {
                    "eligibility_status": "eligible",
                    "classification": "alta",
                    "score_total": 91,
                },
            }
        ],
        "claim_specs_by_evidence": [{"evidence_id": evidence_id, "claim_specs": claim_specs}],
        "claims": [],
        "rejected_claims": [],
        "claim_repair_attempts": 0,
        "steps_used": 0,
        "usage": [],
    }


# --- 1. Celda numérica -> claim direct de 1 fila/1 columna -----------------


@pytest.mark.asyncio
async def test_numeric_cell_becomes_direct_claim_with_one_row_and_one_column():
    state = _state_with_evidence(
        rows=[{"nombre_evento": "Varicela", "total_casos": "1200"}],
        claim_specs=[
            {
                "claim_type": "direct",
                "description": "Casos reportados de Varicela",
                "source_row_indexes": [0],
                "columns": ["total_casos"],
                "unit": "casos",
                "rounding": 0,
            }
        ],
    )

    result = await _claim_builder_node(_claim_builder_deps(), state)

    assert len(result["claims"]) == 1
    assert result["claims"][0]["display_value"] == "1.200 casos"
    assert result["claims"][0]["columns"] == ["total_casos"]


# --- 2. La dimensión es contexto, no una segunda columna --------------------


def test_dimension_text_is_context_not_second_numeric_column():
    """Regresión directa del hallazgo T-403: un claim 'direct' con
    `columns=["nombre_evento", "total_casos"]` se rechaza en el esquema del
    router (antes de gastar un paso de `claim_builder`); la categoría debe
    ir en `description`."""
    bad_spec = {
        "reasoning_summary": "Propongo el claim del evento con más casos",
        "claim_specs_by_evidence": [
            {
                "evidence_id": str(uuid.uuid4()),
                "claim_specs": [
                    {
                        "claim_type": "direct",
                        "description": "Evento con más casos",
                        "source_row_indexes": [0],
                        "columns": ["nombre_evento", "total_casos"],
                    }
                ],
            }
        ],
    }
    with pytest.raises(ValidationError, match="direct"):
        ClaimPlannerOutput.model_validate(bad_spec)

    good_spec = {
        **bad_spec,
        "claim_specs_by_evidence": [
            {
                "evidence_id": bad_spec["claim_specs_by_evidence"][0]["evidence_id"],
                "claim_specs": [
                    {
                        "claim_type": "direct",
                        "description": "Casos reportados de Varicela (evento con mayor volumen)",
                        "source_row_indexes": [0],
                        "columns": ["total_casos"],
                    }
                ],
            }
        ],
    }
    parsed = ClaimPlannerOutput.model_validate(good_spec)
    spec = parsed.claim_specs_by_evidence[0].claim_specs[0]
    assert spec.columns == ["total_casos"]
    assert "nombre_evento" not in spec.columns
    assert "evento" in spec.description.lower()


# --- 3. Varias filas agregadas -> un claim por valor numérico --------------


@pytest.mark.asyncio
async def test_top_n_aggregated_rows_produce_one_claim_per_numeric_value():
    state = _state_with_evidence(
        rows=[
            {"nombre_evento": "Varicela", "total_casos": "1200"},
            {"nombre_evento": "Dengue", "total_casos": "800"},
            {"nombre_evento": "Tosferina", "total_casos": "150"},
        ],
        claim_specs=[
            {
                "claim_type": "direct",
                "description": "Casos de Varicela (mayor volumen)",
                "source_row_indexes": [0],
                "columns": ["total_casos"],
            },
            {
                "claim_type": "direct",
                "description": "Casos de Dengue (segundo mayor volumen)",
                "source_row_indexes": [1],
                "columns": ["total_casos"],
            },
            {
                "claim_type": "direct",
                "description": "Casos de Tosferina (tercer mayor volumen)",
                "source_row_indexes": [2],
                "columns": ["total_casos"],
            },
        ],
    )

    result = await _claim_builder_node(_claim_builder_deps(), state)

    assert len(result["claims"]) == 3
    assert {claim["display_value"] for claim in result["claims"]} == {"1.200", "800", "150"}


# --- 4. Fórmula solo cuando hace falta cómputo ------------------------------


@pytest.mark.asyncio
async def test_derived_claim_uses_formula_only_when_computation_is_required():
    nested_formula = {
        "op": "mul",
        "args": [
            {"op": "div", "args": [{"col": "desertores"}, {"col": "matriculados"}]},
            {"const": 100},
        ],
    }
    planned = ClaimPlannerOutput.model_validate(
        {
            "reasoning_summary": "La tasa requiere una fórmula compuesta",
            "claim_specs_by_evidence": [
                {
                    "evidence_id": "evidence-test",
                    "claim_specs": [
                        {
                            "claim_type": "direct",
                            "description": "Matriculados 2024",
                            "source_row_indexes": [0],
                            "columns": ["matriculados"],
                            "unit": "personas",
                            "rounding": 0,
                        },
                        {
                            "claim_type": "derived",
                            "description": "Tasa de deserción 2024",
                            "source_row_indexes": [0],
                            "columns": ["desertores", "matriculados"],
                            "formula_json": json.dumps(nested_formula),
                            "unit": "%",
                            "rounding": 1,
                        },
                    ],
                }
            ],
        }
    )
    claim_specs = [
        spec.to_claim_payload() for spec in planned.claim_specs_by_evidence[0].claim_specs
    ]
    state = _state_with_evidence(
        evidence_id="evidence-test",
        rows=[
            {"a_o": "2024", "matriculados": "1000", "desertores": "80"},
        ],
        claim_specs=claim_specs,
    )

    result = await _claim_builder_node(_claim_builder_deps(), state)

    direct_claim = next(c for c in result["claims"] if c["claim_type"] == "direct")
    derived_claim = next(c for c in result["claims"] if c["claim_type"] == "derived")
    assert direct_claim["display_value"] == "1.000 personas"
    assert direct_claim["formula"] is None
    assert derived_claim["display_value"] == "8,0 %"
    assert derived_claim["formula"] is not None


# --- 5. Solo referencia filas/columnas disponibles en la evidencia ----------


@pytest.mark.asyncio
async def test_claim_plan_references_only_available_evidence_rows_and_columns():
    state = _state_with_evidence(
        rows=[{"nombre_evento": "Varicela", "total_casos": "1200"}],
        claim_specs=[
            {
                "claim_type": "direct",
                "description": "Columna inventada",
                "source_row_indexes": [0],
                "columns": ["columna_que_no_existe"],
            },
            {
                "claim_type": "direct",
                "description": "Fila fuera de rango",
                "source_row_indexes": [5],
                "columns": ["total_casos"],
            },
        ],
    )

    result = await _claim_builder_node(_claim_builder_deps(), state)

    assert result["claims"] == []
    reasons = " ".join(item["reason"] for item in result["rejected_claims"])
    assert "columna_que_no_existe" in reasons
    assert "fuera de rango" in reasons


# --- Edge de reparación: unidad pura ----------------------------------------


def test_after_claim_builder_routes_to_router_when_retry_pending():
    assert _after_claim_builder({"claim_builder_retry_pending": True}) == "claim_planner"
    assert _after_claim_builder({"claim_builder_retry_pending": False}) == "synthesizer"
    assert _after_claim_builder({}) == "synthesizer"
    terminal_state = {"terminal_error": {"error": {}}, "claim_builder_retry_pending": True}
    assert _after_claim_builder(terminal_state) == END


# --- 6/7. Evidencia elegible no puede terminar en cero claims silenciosos --


async def _metadata_loader(_dataset_id: str) -> DatasetEvidenceMetadata:
    return DatasetEvidenceMetadata(
        dataset_id="4hyg-wa9d",
        name="Eventos de salud pública",
        publisher="Ministerio de Salud",
        official_publisher_id="min-salud",
        pii_risk_level="low",
        eligibility_status="eligible",
        eligibility_reasons=(),
        data_updated_at=datetime.now(UTC),
        column_pii={"nombre_evento": "low", "total_casos": "low"},
        column_types={"nombre_evento": "text", "total_casos": "number"},
    )


def _tools():
    async def buscar(_raw_input):
        return {
            "ok": True,
            "results": [
                {
                    "dataset_id": "4hyg-wa9d",
                    "name": "Eventos de salud pública",
                    "eligibility_status": "eligible",
                    "columns": ["nombre_evento", "total_casos"],
                }
            ],
        }

    async def ejecutar(_raw_input):
        return {
            "ok": True,
            "canonical_soql": "SELECT nombre_evento, total_casos ORDER BY total_casos DESC LIMIT 1",
            "rows": [{"nombre_evento": "Varicela", "total_casos": "1200"}],
            "row_count": 1,
            "executed_at": datetime.now(UTC).isoformat(),
            "source_url": "https://www.datos.gov.co/d/4hyg-wa9d",
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


class StaticPlanner:
    async def ainvoke(self, _messages, **_kwargs):
        return PlannerOutput(
            intention="Identificar el evento con mayor volumen reportado",
            subqueries=["Encontrar la fuente", "Identificar el máximo"],
            recommended_next_action="Buscar en el catálogo",
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
                "summary": f"El evento con mayor volumen registró {value}.",
                "evidence_narratives": [
                    {"evidence_id": evidence_id, "narrative": f"Se registraron {value}."}
                ],
            }
        )


class RepairingClaimPlanner:
    def __init__(self, *, invalid_first: bool = False):
        self.invalid_first = invalid_first
        self.calls = 0
        self.saw_rejected_claims = False

    async def ainvoke(self, messages, **_kwargs):
        self.calls += 1
        payload = json.loads(messages[-1].content)
        self.saw_rejected_claims = bool(payload.get("rejected_claims"))
        evidence_id = payload["evidences"][0]["evidence_id"]
        column = (
            "columna_inventada_por_el_llm"
            if self.invalid_first and self.calls == 1
            else "total_casos"
        )
        return ClaimPlannerOutput.model_validate(
            {
                "reasoning_summary": "Propongo una cifra verificable",
                "claim_specs_by_evidence": [
                    {
                        "evidence_id": evidence_id,
                        "claim_specs": [
                            {
                                "claim_type": "direct",
                                "description": "Casos del evento principal",
                                "source_row_indexes": [0],
                                "columns": [column],
                            }
                        ],
                    }
                ],
            }
        )


def _deps(router, synthesizer, *, claim_model=None) -> GraphDependencies:
    return GraphDependencies(
        engine=None,
        planner_model=StaticPlanner(),
        router_model=router,
        synthesizer_model=synthesizer,
        claim_model=claim_model or RepairingClaimPlanner(),
        tools=_tools(),
        llm_provider="google",
        llm_model="gemini-2.5-flash",
        max_steps=15,
        persist=False,
        metadata_loader=_metadata_loader,
    )


class ClaimRepairRouter:
    """Guion determinista: propone un claim inválido semánticamente (columna
    inexistente -- algo que SOLO `build_claims` en tiempo de ejecución puede
    detectar, no el esquema de Pydantic) en el primer "finish", y uno
    corregido en el segundo, leyendo `rejected_claims` del payload para
    confirmar que el grafo sí se lo entrega."""

    def __init__(self):
        self.calls = 0
        self.saw_rejected_claims = False

    async def ainvoke(self, messages, **_kwargs):
        self.calls += 1
        payload = json.loads(messages[-1].content)
        if self.calls == 1:
            return RouterOutput.model_validate(
                {
                    "action": "buscar_catalogo",
                    "reasoning_summary": "Busco la fuente",
                    "tool_input": {"query": "eventos de salud pública", "k": 5},
                }
            )
        if self.calls == 2:
            return RouterOutput.model_validate(
                {
                    "action": "ejecutar_soql",
                    "reasoning_summary": "Consulto el evento con más casos",
                    "tool_input": {
                        "dataset_id": "4hyg-wa9d",
                        "soql": (
                            "SELECT nombre_evento, total_casos ORDER BY total_casos DESC LIMIT 1"
                        ),
                        "purpose": "Evento con mayor volumen",
                    },
                }
            )
        evidence_id = payload["evidences"][0]["evidence_id"]
        if not payload.get("rejected_claims"):
            return RouterOutput.model_validate(
                {
                    "action": "finish",
                    "reasoning_summary": "Propongo el claim",
                    "tool_input": {},
                    "claim_specs_by_evidence": [
                        {
                            "evidence_id": evidence_id,
                            "claim_specs": [
                                {
                                    "claim_type": "direct",
                                    "description": "Casos del evento principal",
                                    "source_row_indexes": [0],
                                    "columns": ["columna_inventada_por_el_llm"],
                                }
                            ],
                        }
                    ],
                }
            )
        self.saw_rejected_claims = True
        return RouterOutput.model_validate(
            {
                "action": "finish",
                "reasoning_summary": "Corrijo el claim con la columna real",
                "tool_input": {},
                "claim_specs_by_evidence": [
                    {
                        "evidence_id": evidence_id,
                        "claim_specs": [
                            {
                                "claim_type": "direct",
                                "description": "Casos del evento principal",
                                "source_row_indexes": [0],
                                "columns": ["total_casos"],
                            }
                        ],
                    }
                ],
            }
        )


class ForgetsClaimsThenProposesRouter:
    """Primer "finish" sin `claim_specs_by_evidence` (el router simplemente
    no propuso nada, no un rechazo): evidencia elegible que terminaría en
    cero claims sin que nada la haya rechazado explícitamente."""

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
                    "tool_input": {"query": "eventos de salud pública", "k": 5},
                }
            )
        if self.calls == 2:
            return RouterOutput.model_validate(
                {
                    "action": "ejecutar_soql",
                    "reasoning_summary": "Consulto el evento con más casos",
                    "tool_input": {
                        "dataset_id": "4hyg-wa9d",
                        "soql": (
                            "SELECT nombre_evento, total_casos ORDER BY total_casos DESC LIMIT 1"
                        ),
                        "purpose": "Evento con mayor volumen",
                    },
                }
            )
        if self.calls == 3:
            return RouterOutput.model_validate(
                {
                    "action": "finish",
                    "reasoning_summary": "Ya reuní la evidencia",
                    "tool_input": {},
                }
            )
        evidence_id = payload["evidences"][0]["evidence_id"]
        return RouterOutput.model_validate(
            {
                "action": "finish",
                "reasoning_summary": "Propongo el claim que había olvidado",
                "tool_input": {},
                "claim_specs_by_evidence": [
                    {
                        "evidence_id": evidence_id,
                        "claim_specs": [
                            {
                                "claim_type": "direct",
                                "description": "Casos del evento principal",
                                "source_row_indexes": [0],
                                "columns": ["total_casos"],
                            }
                        ],
                    }
                ],
            }
        )


@pytest.mark.asyncio
async def test_rejected_claims_trigger_claim_repair_before_synthesis():
    router = ClaimRepairRouter()
    claim_planner = RepairingClaimPlanner(invalid_first=True)
    graph = build_graph(
        _deps(router, SuccessfulSynthesizer(), claim_model=claim_planner), interrupt=False
    )

    result = await graph.ainvoke(
        initial_state(
            uuid.uuid4(), "¿Qué evento de salud pública tuvo mayor volumen?", max_steps=15
        )
    )

    assert claim_planner.saw_rejected_claims is True
    assert result["final_answer"]["status"] == "completed"
    assert len(result["claims"]) == 1
    assert result["claims"][0]["columns"] == ["total_casos"]


@pytest.mark.asyncio
async def test_valid_high_quality_evidence_cannot_silently_finish_with_zero_claims():
    router = ForgetsClaimsThenProposesRouter()
    graph = build_graph(_deps(router, SuccessfulSynthesizer()), interrupt=False)

    result = await graph.ainvoke(
        initial_state(
            uuid.uuid4(), "¿Qué evento de salud pública tuvo mayor volumen?", max_steps=15
        )
    )

    assert result["final_answer"]["status"] == "completed"
    assert len(result["claims"]) == 1


# --- Regresión pilot-003 (2026-07-12): evidence_id alucinado por el LLM -----
#
# Ninguno de los dobles anteriores ejercita este caso: todos leen
# `evidence_id` directamente del payload real, así que nunca producen un id
# que no exista en `state["evidences"]`. En producción (smoke real con
# Gemini), el LLM sí lo hizo: `claim_planner` reportó `planned=10` y
# `claim_builder` aceptó 0 sin rechazar nada, porque
# `specs_by_id.get(evidence_id, [])` devuelve `[]` en silencio ante un id
# desconocido -- ni acepta ni rechaza, pierde la evidencia entera.


def _claim_planner_deps(claim_model) -> GraphDependencies:
    return GraphDependencies(
        engine=None,
        planner_model=None,
        router_model=None,
        synthesizer_model=None,
        claim_model=claim_model,
        tools={},
        llm_provider="google",
        llm_model="gemini-2.5-flash",
        persist=False,
    )


def _state_for_claim_planner(*, evidence_id: str) -> dict:
    return {
        "run_id": str(uuid.uuid4()),
        "question": "¿Cuántos casos se reportaron del evento principal?",
        "evidences": [
            {
                "evidence_id": evidence_id,
                "dataset_id": "4hyg-wa9d",
                "soql_query": "SELECT nombre_evento, total_casos GROUP BY nombre_evento",
                "rows": [{"nombre_evento": "Varicela", "total_casos": "1200"}],
                "quality": {
                    "eligibility_status": "eligible",
                    "classification": "alta",
                    "score_total": 91,
                },
            }
        ],
        "claims": [],
        "rejected_claims": [],
        "steps_used": 0,
        "usage": [],
    }


def _direct_claim_spec(evidence_id: str) -> dict:
    return {
        "reasoning_summary": "Propongo una cifra verificable",
        "claim_specs_by_evidence": [
            {
                "evidence_id": evidence_id,
                "claim_specs": [
                    {
                        "claim_type": "direct",
                        "description": "Casos del evento principal",
                        "source_row_indexes": [0],
                        "columns": ["total_casos"],
                    }
                ],
            }
        ],
    }


class HallucinatesEvidenceIdOnceThenCorrects:
    """Primer intento: `evidence_id` inventado, que no existe en
    `state["evidences"]`. Segundo intento: lee el `evidence_id` real del
    payload original (siempre en `messages[1]`, nunca en el mensaje de
    reparación que se le añade después) y responde con el id correcto --
    simula que el modelo SÍ puede corregirse cuando se le da la lista exacta
    de ids válidos."""

    def __init__(self):
        self.calls = 0

    async def ainvoke(self, messages, **_kwargs):
        self.calls += 1
        payload = json.loads(messages[1].content)
        real_evidence_id = payload["evidences"][0]["evidence_id"]
        evidence_id = (
            "evidencia-alucinada-no-existe" if self.calls == 1 else real_evidence_id
        )
        return ClaimPlannerOutput.model_validate(_direct_claim_spec(evidence_id))


class AlwaysHallucinatesEvidenceId:
    """Nunca corrige el evidence_id, ni siquiera tras recibir el mensaje de
    reparación con la lista exacta de ids válidos -- ejercita el camino de
    rechazo explícito una vez agotados los intentos de reparación."""

    def __init__(self):
        self.calls = 0

    async def ainvoke(self, _messages, **_kwargs):
        self.calls += 1
        return ClaimPlannerOutput.model_validate(
            _direct_claim_spec("evidencia-alucinada-no-existe")
        )


@pytest.mark.asyncio
async def test_hallucinated_evidence_id_is_repaired_within_the_same_graph_step():
    real_evidence_id = str(uuid.uuid4())
    claim_planner = HallucinatesEvidenceIdOnceThenCorrects()
    state = _state_for_claim_planner(evidence_id=real_evidence_id)

    result = await _claim_planner_node(_claim_planner_deps(claim_planner), state)

    assert claim_planner.calls == 2
    # La reparación ocurrió DENTRO del mismo paso: el grafo no gastó un paso
    # extra en corregir un evidence_id inventado, igual que el repair loop
    # de salida estructurada no cuenta como paso adicional.
    assert result["steps_used"] == 1
    assert result["claim_specs_by_evidence"] == [
        {
            "evidence_id": real_evidence_id,
            "claim_specs": [
                {
                    "claim_type": "direct",
                    "description": "Casos del evento principal",
                    "source_row_indexes": [0],
                    "columns": ["total_casos"],
                    "unit": None,
                    "rounding": None,
                    "formula": None,
                }
            ],
        }
    ]
    # No debe haber quedado ningún rechazo por el intento fallido inicial:
    # se corrigió antes de llegar a claim_builder.
    assert result["rejected_claims"] == []


@pytest.mark.asyncio
async def test_unrepaired_hallucinated_evidence_id_is_rejected_explicitly_not_silently():
    real_evidence_id = str(uuid.uuid4())
    claim_planner = AlwaysHallucinatesEvidenceId()
    state = _state_for_claim_planner(evidence_id=real_evidence_id)

    result = await _claim_planner_node(_claim_planner_deps(claim_planner), state)

    # El plan filtra el evidence_id inválido: claim_builder nunca lo ve, así
    # que nunca puede terminar en el "accepted=0, rejected=0" silencioso de
    # pilot-003.
    assert result["claim_specs_by_evidence"] == []
    # En cambio, queda un rechazo EXPLÍCITO y diagnosticable.
    assert len(result["rejected_claims"]) == 1
    rejection = result["rejected_claims"][0]
    assert rejection["evidence_id"] == "evidencia-alucinada-no-existe"
    assert "evidencia-alucinada-no-existe" in rejection["reason"]
    assert real_evidence_id not in [
        item.get("evidence_id") for item in result["claim_specs_by_evidence"]
    ]


@pytest.mark.asyncio
async def test_claim_builder_never_silently_finds_zero_accepted_and_zero_rejected():
    """Regresión directa de pilot-003: con evidencia elegible real y un plan
    de claims cuyo evidence_id nunca corresponde a esa evidencia, el grafo
    completo NUNCA debe llegar a `claim_builder` con accepted=0 y
    rejected=0 sin ninguna explicación -- o hay claims, o hay un rechazo
    explícito, nunca silencio total."""
    real_evidence_id = str(uuid.uuid4())
    claim_planner = AlwaysHallucinatesEvidenceId()
    planner_state = _state_for_claim_planner(evidence_id=real_evidence_id)
    plan_result = await _claim_planner_node(_claim_planner_deps(claim_planner), planner_state)

    merged_state = {
        **planner_state,
        **plan_result,
        "rejected_claims": plan_result["rejected_claims"],
    }
    builder_result = await _claim_builder_node(_claim_planner_deps(claim_planner), merged_state)

    assert builder_result["claims"] == []
    # rejected_claims trae al menos el rechazo del propio claim_planner, ni
    # accepted ni rejected quedan en cero sin explicación.
    assert len(builder_result["rejected_claims"]) >= 1
