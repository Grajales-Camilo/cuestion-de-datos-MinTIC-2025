"""Grafo LangGraph real del agente (T-303, RF-201..209, RF-703).

El LLM solo decide en planificador/enrutador/sintetizador. T6 y T7 son nodos
deterministas y ocupan posiciones obligatorias del grafo. El estado contiene
solo valores serializables; clientes, modelos y conexiones viven en cierres
inyectados mediante :class:`GraphDependencies`.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Any, Literal, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncEngine

from app.agent.durability import reserve_and_emit_event
from app.agent.persistence import (
    DatasetEvidenceMetadata,
    json_safe,
    load_dataset_evidence_metadata,
    persist_claims,
    persist_evidence_and_quality,
    record_step_and_event,
    update_evidence_narratives,
)
from app.llm.factory import (
    LLMProviderError,
    ainvoke_structured_chat_model,
    usage_from_message,
)
from app.quality.claims import ClaimSpec, EvidenceContext, build_claims, find_orphan_figures
from app.quality.validator import EvidenceDraft, SelectedColumn, validate_evidence
from app.tools.soql_parser import Column, FuncCall, Star, parse_soql

PROMPT_VERSION = "v1"
PROMPTS_DIR = Path(__file__).with_name("prompts")
TOOL_NAMES = (
    "buscar_catalogo",
    "perfilar_dataset",
    "resolver_geografia",
    "explorar_valores",
    "ejecutar_soql",
)
GRAPH_NODES = (
    "planner",
    "router",
    *(f"tool__{name}" for name in TOOL_NAMES),
    "quality_validator",
    "claim_builder",
    "synthesizer",
)
MAX_SOQL_CALLS = 4
MAX_SOQL_CORRECTIONS = 2
# Hallazgo T-402 (2026-07-11, ejecucion real): antes solo "SOQL_SYNTAX"
# (rechazo real de Socrata) contaba para el presupuesto de correcciones;
# "SOQL_FORBIDDEN"/"SOQL_UNKNOWN_COLUMN" (rechazo de nuestra propia guardia
# estructural, p. ej. una clausula FROM alucinada) nunca se contaban, asi
# que el router podia repetir el mismo error sin limite dentro del
# presupuesto de pasos general. Ambos son igual de "corregibles reescribiendo
# el SoQL" -- a diferencia de EVIDENCE_NOT_ELIGIBLE/DATASET_INACTIVE/
# PII_AGGREGATION_REQUIRED, que no se arreglan cambiando la sintaxis.
_CORRECTABLE_SOQL_ERROR_CODES = {"SOQL_SYNTAX", "SOQL_FORBIDDEN", "SOQL_UNKNOWN_COLUMN"}
MAX_SYNTHESIS_RETRIES = 2
LLM_ROWS_MAX = 50
EVIDENCE_ROWS_MAX_BYTES = 1024 * 1024
EVIDENCE_EVENT_MAX_BYTES = 256 * 1024

ToolCallable = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
MetadataLoader = Callable[[str], Awaitable[DatasetEvidenceMetadata | None]]


class PlannerOutput(BaseModel):
    intention: str = Field(min_length=1, max_length=500)
    subqueries: list[str] = Field(min_length=1, max_length=5)
    recommended_next_action: str = Field(min_length=1, max_length=200)


class ConstFormulaNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    const: float


class ColFormulaNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    col: str


class AggFormulaNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Debe coincidir con app.quality.claims.ALLOWED_AGG_FUNCTIONS.
    agg: Literal["sum", "avg", "count", "min", "max"]
    col: str


class OpFormulaNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Debe coincidir con app.quality.claims.ALLOWED_OPS.
    op: Literal["add", "sub", "mul", "div", "ratio", "pct_change"]
    args: list[FormulaNode] = Field(min_length=1)


FormulaNode = ConstFormulaNode | ColFormulaNode | AggFormulaNode | OpFormulaNode
OpFormulaNode.model_rebuild()
# El modelo Python es recursivo sin limite (`ClaimSpecPayload.model_validate`
# acepta `op` anidado dentro de `op`, e `_eval_node` en claims.py lo evalua
# igual sin tope de profundidad). El unico limite real esta en que el LLM
# puede *generar*: `convert_to_openai_tool` (usado por
# `with_structured_output`) inlinea la union recursiva para el esquema de
# function-calling pero corta esa expansion en profundidad 1 -- dentro de
# `OpFormulaNode.args` el proveedor solo puede ofrecer `const`/`col`/`agg`,
# no otro `op` anidado (verificado: 2026-07-11, la palabra "OpFormulaNode"
# aparece una sola vez en el JSON schema generado por
# `convert_to_openai_tool(RouterOutput)`). Limitacion aceptada (Art. III
# YAGNI) del lado del LLM: cubre "suma de una columna" u "operacion sobre
# columnas/agregados simples", que es todo lo que T-402 encontro necesario;
# una formula con dos niveles de `op` anidados (p. ej. "(a+b)/c") debe
# expresarse pidiendo esos subtotales como claims `derived` separados.


class ClaimSpecPayload(BaseModel):
    """Hallazgo T-303 (2026-07-10, ejecucion real): `claim_type` como `str`
    libre permitia que el LLM alucinara valores como `direct_value`, que
    `build_claims` rechaza (`claim_type '...' no reconocido`, contracts/
    agent-tools.md §T7 solo admite `direct`/`derived`). Restringirlo a
    `Literal` hace que el proveedor de structured output (Gemini/Claude)
    nunca pueda producir un valor fuera de esos dos, en vez de depender de
    que T7 lo rechace despues de gastar un paso completo del presupuesto.

    Hallazgo T-402 (2026-07-11, ejecucion real con LLM real): `formula` como
    `dict[str, Any]` sufria el mismo problema para claims `derived` -- el LLM
    inventaba formas de nodo fuera de la DSL real de `app.quality.claims`
    (`_eval_node` solo reconoce `{const}`/`{col}`/{agg,col}`/{op,args}`) y
    `build_claims` las rechazaba con "forma de nodo desconocida" tras gastar
    un paso completo. `FormulaNode` (union discriminada, recursiva en `args`)
    aplica la misma correccion: el esquema de function-calling del proveedor
    ya no puede producir una quinta forma inventada.
    """

    claim_type: Literal["direct", "derived"]
    description: str = Field(min_length=1, max_length=500)
    source_row_indexes: list[int] = Field(min_length=1)
    columns: list[str] = Field(min_length=1)
    unit: str | None = None
    rounding: int | None = Field(default=None, ge=0, le=8)
    formula: FormulaNode | None = None


class EvidenceClaimSpecs(BaseModel):
    evidence_id: str
    claim_specs: list[ClaimSpecPayload]


class RouterToolInput(BaseModel):
    query: str | None = None
    k: int | None = Field(default=None, ge=1, le=10)
    dataset_id: str | None = None
    columns_of_interest: list[str] | None = None
    termino: str | None = None
    columna: str | None = None
    termino_busqueda: str | None = None
    soql: str | None = None
    purpose: str | None = None


class RouterOutput(BaseModel):
    action: str = Field(min_length=1)
    reasoning_summary: str = Field(min_length=1, max_length=500)
    tool_input: RouterToolInput
    claim_specs_by_evidence: list[EvidenceClaimSpecs] = Field(default_factory=list)


class EvidenceNarrative(BaseModel):
    evidence_id: str
    narrative: str


class ReviewedDataset(BaseModel):
    dataset_id: str
    name: str
    why_rejected: str


class NoEvidenceReport(BaseModel):
    reason: str
    datasets_reviewed: list[ReviewedDataset] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class SynthesisOutput(BaseModel):
    summary: str | None = None
    narrative: str | None = None
    evidence_narratives: list[EvidenceNarrative] = Field(default_factory=list)
    no_evidence_report: NoEvidenceReport | None = None


class AgentState(TypedDict, total=False):
    run_id: str
    question: str
    context_hint: str | None
    intention: str
    plan: list[str]
    observations: list[dict[str, Any]]
    pending_action: dict[str, Any]
    pending_t5: dict[str, Any]
    evidences: list[dict[str, Any]]
    claim_specs_by_evidence: list[dict[str, Any]]
    claims: list[dict[str, Any]]
    rejected_claims: list[dict[str, Any]]
    steps_used: int
    max_steps: int
    t5_calls: int
    soql_corrections: dict[str, int]
    usage: list[dict[str, Any]]
    termination_reason: str | None
    final_answer: dict[str, Any]
    terminal_error: dict[str, Any]
    synthesis_attempts: int


@dataclass
class GraphDependencies:
    engine: AsyncEngine | None
    planner_model: Runnable
    router_model: Runnable
    synthesizer_model: Runnable
    tools: dict[str, ToolCallable]
    llm_provider: str
    llm_model: str
    max_steps: int = 10
    placeholder_min_ratio: float = 0.30
    persist: bool = True
    metadata_loader: MetadataLoader | None = None


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}_{PROMPT_VERSION}.md").read_text(encoding="utf-8")


def initial_state(
    run_id: uuid.UUID,
    question: str,
    *,
    max_steps: int,
    context_hint: str | None = None,
) -> AgentState:
    return {
        "run_id": str(run_id),
        "question": question,
        "context_hint": context_hint,
        "observations": [],
        "evidences": [],
        "claims": [],
        "rejected_claims": [],
        "steps_used": 0,
        "max_steps": max_steps,
        "t5_calls": 0,
        "soql_corrections": {},
        "usage": [],
        "termination_reason": None,
        "synthesis_attempts": 0,
    }


def _usage_totals(state: AgentState) -> dict[str, Any]:
    usages = state.get("usage", [])
    return {
        "input_tokens": sum(int(item.get("input_tokens", 0)) for item in usages),
        "output_tokens": sum(int(item.get("output_tokens", 0)) for item in usages),
        "estimated_cost_usd": round(
            sum(float(item.get("estimated_cost_usd", 0)) for item in usages), 6
        ),
    }


async def _invoke_structured(
    deps: GraphDependencies,
    model: Runnable,
    schema: type[BaseModel],
    prompt_name: str,
    payload: dict[str, Any],
) -> tuple[BaseModel, dict[str, Any] | None]:
    messages = [
        SystemMessage(content=load_prompt(prompt_name)),
        HumanMessage(content=json.dumps(json_safe(payload), ensure_ascii=False)),
    ]
    result = await ainvoke_structured_chat_model(model, messages, schema=schema)
    parsed = schema.model_validate(result.parsed)
    if result.raw_message is None:
        return parsed, None
    usage = usage_from_message(deps.llm_provider, deps.llm_model, result.raw_message)
    return parsed, asdict(usage)


async def _record(
    deps: GraphDependencies,
    state: AgentState,
    *,
    node: str,
    display_message: str,
    detail: Any = None,
    tool_input: Any = None,
    tool_output: Any = None,
    latency_ms: int | None = None,
    error: str | None = None,
    extra_usage: dict[str, Any] | None = None,
) -> tuple[int, list[dict[str, Any]]]:
    step_number = state.get("steps_used", 0) + 1
    usages = [*state.get("usage", [])]
    if extra_usage is not None:
        usages.append(extra_usage)
    if deps.persist:
        assert deps.engine is not None
        totals = _usage_totals({**state, "usage": usages})
        await record_step_and_event(
            deps.engine,
            uuid.UUID(state["run_id"]),
            step_number=step_number,
            node=node,
            display_message=display_message,
            detail=detail,
            tool_input=tool_input,
            tool_output=tool_output,
            latency_ms=latency_ms,
            error=error,
            run_values={
                "llm_provider": deps.llm_provider,
                "llm_model": deps.llm_model,
                **totals,
            },
        )
    return step_number, usages


def _terminal_error(code: str, message_user: str, message_dev: str) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "status": "failed",
            "message_user": message_user,
            "message_dev": message_dev,
            "retryable": code in {"SOCRATA_TIMEOUT", "SOCRATA_ERROR"},
        }
    }


def _llm_observations(state: AgentState) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for observation in state.get("observations", []):
        item = json_safe(observation)
        output = item.get("output")
        if isinstance(output, dict) and isinstance(output.get("rows"), list):
            item["output"] = {**output, "rows": output["rows"][:LLM_ROWS_MAX]}
        observations.append(item)
    return observations


def _bounded_rows(rows: list[dict[str, Any]], max_bytes: int) -> list[dict[str, Any]]:
    if len(json.dumps(json_safe(rows), ensure_ascii=False).encode("utf-8")) <= max_bytes:
        return rows
    low, high = 0, len(rows)
    while low < high:
        middle = (low + high + 1) // 2
        size = len(
            json.dumps(json_safe(rows[:middle]), ensure_ascii=False).encode("utf-8")
        )
        if size <= max_bytes:
            low = middle
        else:
            high = middle - 1
    return rows[:low]


def _evidence_event_payload(evidence: dict[str, Any]) -> dict[str, Any]:
    rows = evidence.get("rows", [])[:LLM_ROWS_MAX]
    payload = {
        **evidence,
        "rows": rows,
        "rows_truncated": len(rows) < len(evidence.get("rows", [])),
    }
    while rows and len(
        json.dumps(json_safe(payload), ensure_ascii=False).encode("utf-8")
    ) > EVIDENCE_EVENT_MAX_BYTES:
        rows = rows[: max(0, len(rows) // 2)]
        payload["rows"] = rows
        payload["rows_truncated"] = True
    return payload


def _router_force_finish(state: AgentState) -> bool:
    remaining_before_router = state.get("max_steps", 10) - state.get("steps_used", 0)
    # router + claim_builder + synthesizer, o router + synthesizer sin evidencia
    required = 3 if state.get("evidences") else 2
    return remaining_before_router <= required


def _minimum_after_router(action: str) -> int:
    if action == "ejecutar_soql":
        # tool + T6 + router final + T7 + sintetizador
        return 5
    # tool + router final + sintetizador
    return 3


def _source_columns(expr: Any) -> list[str]:
    if isinstance(expr, Column):
        return [expr.name]
    if isinstance(expr, FuncCall):
        result: list[str] = []
        for arg in expr.args:
            if not isinstance(arg, Star):
                result.extend(_source_columns(arg))
        return result
    return []


def _selected_columns(
    canonical_soql: str, metadata: DatasetEvidenceMetadata
) -> tuple[SelectedColumn, ...]:
    parsed = parse_soql(canonical_soql)
    severity = {"low": 0, "medium": 1, "unknown": 2, "high": 3}
    selected: list[SelectedColumn] = []
    for item in parsed.select_items:
        output_name = item.alias
        if output_name is None and isinstance(item.expr, Column):
            output_name = item.expr.name
        if output_name is None:
            continue
        sources = _source_columns(item.expr)
        risks = [metadata.column_pii.get(name, metadata.pii_risk_level) for name in sources]
        risk = max(risks or [metadata.pii_risk_level], key=lambda value: severity[value])
        selected.append(SelectedColumn(field_name=output_name, pii_risk_level=risk))
    return tuple(selected)


async def _planner_node(deps: GraphDependencies, state: AgentState) -> AgentState:
    started = time.perf_counter()
    try:
        output, usage = await _invoke_structured(
            deps,
            deps.planner_model,
            PlannerOutput,
            "planner",
            {
                "question": state["question"],
                "context_hint": state.get("context_hint"),
                "max_steps": state.get("max_steps", deps.max_steps),
            },
        )
    except LLMProviderError as exc:
        step, usages = await _record(
            deps,
            state,
            node="planner",
            display_message="No fue posible iniciar la planificación.",
            error=str(exc),
        )
        return {
            "steps_used": step,
            "usage": usages,
            "terminal_error": _terminal_error(
                "LLM_PROVIDER_ERROR",
                "El servicio de inteligencia artificial no está disponible en este momento.",
                str(exc),
            ),
        }
    assert isinstance(output, PlannerOutput)
    step, usages = await _record(
        deps,
        state,
        node="planner",
        display_message="Organicé la pregunta en partes verificables.",
        detail={"subqueries": output.subqueries},
        latency_ms=round((time.perf_counter() - started) * 1000),
        extra_usage=usage,
    )
    return {
        "intention": output.intention,
        "plan": output.subqueries,
        "steps_used": step,
        "usage": usages,
    }


async def _router_node(deps: GraphDependencies, state: AgentState) -> AgentState:
    started = time.perf_counter()
    force_finish = _router_force_finish(state)
    try:
        output, usage = await _invoke_structured(
            deps,
            deps.router_model,
            RouterOutput,
            "router",
            {
                "question": state["question"],
                "intention": state.get("intention"),
                "plan": state.get("plan", []),
                "observations": _llm_observations(state),
                "evidences": [
                    {**evidence, "rows": evidence.get("rows", [])[:LLM_ROWS_MAX]}
                    for evidence in state.get("evidences", [])
                ],
                "budget": {
                    "steps_used": state.get("steps_used", 0),
                    "max_steps": state.get("max_steps", deps.max_steps),
                    "t5_calls": state.get("t5_calls", 0),
                    "max_t5_calls": MAX_SOQL_CALLS,
                    "soql_corrections": state.get("soql_corrections", {}),
                },
                "force_finish": force_finish,
            },
        )
    except LLMProviderError as exc:
        step, usages = await _record(
            deps,
            state,
            node="router",
            display_message="No fue posible decidir el siguiente paso.",
            error=str(exc),
        )
        return {
            "steps_used": step,
            "usage": usages,
            "terminal_error": _terminal_error(
                "LLM_PROVIDER_ERROR",
                "El servicio de inteligencia artificial no está disponible en este momento.",
                str(exc),
            ),
        }
    assert isinstance(output, RouterOutput)
    action = output.action.strip()
    termination_reason = state.get("termination_reason")
    if force_finish and action != "finish":
        action = "finish"
        termination_reason = "STEP_BUDGET_EXCEEDED"
    if action not in {*TOOL_NAMES, "finish"}:
        step, usages = await _record(
            deps,
            state,
            node="router",
            display_message="La acción solicitada no es válida.",
            detail={"requested_action": action},
            error=f"Herramienta fuera de T1-T5: {action}",
            latency_ms=round((time.perf_counter() - started) * 1000),
            extra_usage=usage,
        )
        return {
            "steps_used": step,
            "usage": usages,
            "terminal_error": _terminal_error(
                "INTERNAL",
                "El agente solicitó una acción que no está permitida.",
                f"Herramienta fuera de T1-T5: {action}",
            ),
        }
    step, usages = await _record(
        deps,
        state,
        node="router",
        display_message=(
            "Ya reuní lo necesario para preparar la respuesta."
            if action == "finish"
            else "Elegí el siguiente paso de verificación."
        ),
        detail={"action": action, "reason": output.reasoning_summary},
        latency_ms=round((time.perf_counter() - started) * 1000),
        extra_usage=usage,
    )
    remaining = state.get("max_steps", deps.max_steps) - step
    if action != "finish" and remaining < _minimum_after_router(action):
        action = "finish"
        termination_reason = "STEP_BUDGET_EXCEEDED"
    if action == "ejecutar_soql" and state.get("t5_calls", 0) >= MAX_SOQL_CALLS:
        action = "finish"
        termination_reason = "STEP_BUDGET_EXCEEDED"
    if action == "ejecutar_soql":
        tool_input = output.tool_input.model_dump(exclude_none=True)
        correction_key = (
            f"{tool_input.get('dataset_id', '')}:{tool_input.get('purpose', '')}"
        )
        if state.get("soql_corrections", {}).get(correction_key, 0) > MAX_SOQL_CORRECTIONS:
            action = "finish"
    return {
        "pending_action": {
            "action": action,
            "tool_input": output.tool_input.model_dump(exclude_none=True),
        },
        "claim_specs_by_evidence": [item.model_dump() for item in output.claim_specs_by_evidence],
        "termination_reason": termination_reason,
        "steps_used": step,
        "usage": usages,
    }


def _tool_node(deps: GraphDependencies, tool_name: str):
    async def _run(state: AgentState) -> AgentState:
        raw_input = state.get("pending_action", {}).get("tool_input", {})
        started = time.perf_counter()
        output = await deps.tools[tool_name](raw_input)
        latency_ms = round((time.perf_counter() - started) * 1000)
        error = None if output.get("ok") else output.get("error", {}).get("code")
        step, usages = await _record(
            deps,
            state,
            node=f"tool:{tool_name}",
            display_message={
                "buscar_catalogo": "Busqué conjuntos de datos relacionados.",
                "perfilar_dataset": "Revisé la estructura y los valores del conjunto de datos.",
                "resolver_geografia": "Verifiqué el territorio solicitado.",
                "explorar_valores": "Comprobé cómo aparece el valor en la fuente.",
                "ejecutar_soql": "Consulté la fuente oficial de datos.",
            }[tool_name],
            detail={"ok": bool(output.get("ok")), "error_code": error},
            tool_input=raw_input,
            tool_output=output,
            latency_ms=latency_ms,
            error=error,
        )
        observations = [
            *state.get("observations", []),
            {"tool": tool_name, "input": raw_input, "output": output},
        ]
        result: AgentState = {"steps_used": step, "usage": usages, "observations": observations}
        if tool_name != "ejecutar_soql":
            return result
        result["t5_calls"] = state.get("t5_calls", 0) + 1
        if output.get("ok"):
            result["pending_t5"] = {"input": raw_input, "output": output}
            return result
        code = output.get("error", {}).get("code", "SOCRATA_ERROR")
        if code in _CORRECTABLE_SOQL_ERROR_CODES:
            key = f"{raw_input.get('dataset_id', '')}:{raw_input.get('purpose', '')}"
            corrections = {**state.get("soql_corrections", {})}
            corrections[key] = corrections.get(key, 0) + 1
            result["soql_corrections"] = corrections
            if corrections[key] > MAX_SOQL_CORRECTIONS:
                observations[-1]["correction_exhausted"] = True
            return result
        if code in {"SOCRATA_TIMEOUT", "SOCRATA_ERROR"}:
            result["terminal_error"] = _terminal_error(
                code,
                (
                    "La fuente de datos del Estado no respondió a tiempo. Intenta de nuevo."
                    if code == "SOCRATA_TIMEOUT"
                    else "La fuente de datos del Estado no pudo completar la consulta."
                ),
                output.get("error", {}).get("message", code),
            )
        return result

    return _run


async def _quality_node(deps: GraphDependencies, state: AgentState) -> AgentState:
    pending = state["pending_t5"]
    tool_input, tool_output = pending["input"], pending["output"]
    dataset_id = tool_input["dataset_id"]
    loader = deps.metadata_loader
    if loader is None:
        assert deps.engine is not None
        metadata = await load_dataset_evidence_metadata(deps.engine, dataset_id)
    else:
        metadata = await loader(dataset_id)
    if metadata is None:
        message = f"No se encontraron metadatos para {dataset_id} después de T5"
        step, usages = await _record(
            deps,
            state,
            node="quality_validator",
            display_message="No fue posible validar la fuente consultada.",
            error=message,
        )
        return {
            "steps_used": step,
            "usage": usages,
            "terminal_error": _terminal_error(
                "INTERNAL", "No fue posible validar la evidencia.", message
            ),
        }
    executed_at = datetime.fromisoformat(tool_output["executed_at"].replace("Z", "+00:00"))
    original_rows = list(tool_output.get("rows", []))
    evidence_rows = _bounded_rows(original_rows, EVIDENCE_ROWS_MAX_BYTES)
    draft = EvidenceDraft(
        dataset_id=dataset_id,
        dataset_name=metadata.name,
        publisher=metadata.publisher,
        source_url=tool_output.get("source_url"),
        dataset_pii_risk_level=metadata.pii_risk_level,
        dataset_eligibility_status=metadata.eligibility_status,
        dataset_eligibility_reasons=metadata.eligibility_reasons,
        canonical_soql=tool_output["canonical_soql"],
        selected_columns=_selected_columns(tool_output["canonical_soql"], metadata),
        rows=tuple(evidence_rows),
        row_count=int(tool_output.get("row_count", 0)),
        data_updated_at=metadata.data_updated_at,
        evaluated_at=executed_at,
    )
    started = time.perf_counter()
    quality = validate_evidence(draft, placeholder_min_ratio=deps.placeholder_min_ratio)
    if deps.persist:
        assert deps.engine is not None
        evidence = await persist_evidence_and_quality(
            deps.engine,
            uuid.UUID(state["run_id"]),
            draft,
            quality,
            official_publisher_id=metadata.official_publisher_id,
        )
    else:
        evidence = {
            "evidence_id": str(uuid.uuid4()),
            "dataset_id": draft.dataset_id,
            "dataset_name": draft.dataset_name,
            "publisher": draft.publisher,
            "soql_query": draft.canonical_soql,
            "executed_at": draft.evaluated_at.isoformat(),
            "source_url": draft.source_url,
            "data_updated_at": draft.data_updated_at.isoformat() if draft.data_updated_at else None,
            "rows": list(draft.rows),
            "row_count": draft.row_count,
            "narrative": None,
            "quality": {
                "eligibility_status": quality.eligibility_status,
                "eligibility_reasons": list(quality.eligibility_reasons),
                "score_total": quality.score_total,
                "classification": quality.classification,
                "warnings_user": list(quality.warnings_user),
                "dimensions": json_safe({k: asdict(v) for k, v in quality.dimensions.items()}),
            },
            "citation": {},
        }
    evidence["columns"] = [
        {
            "field": column.field_name,
            "type": metadata.column_types.get(
                column.field_name,
                "number"
                if any(
                    str(row.get(column.field_name, "")).replace(".", "", 1).isdigit()
                    for row in evidence_rows
                )
                else "text",
            ),
        }
        for column in draft.selected_columns
    ]
    evidence["rows_truncated"] = len(evidence_rows) < len(original_rows)
    step, usages = await _record(
        deps,
        state,
        node="quality_validator",
        display_message="Validé la calidad y trazabilidad de los datos.",
        detail={
            "evidence_id": evidence["evidence_id"],
            "classification": quality.classification,
            "eligibility_status": quality.eligibility_status,
        },
        tool_output=evidence["quality"],
        latency_ms=round((time.perf_counter() - started) * 1000),
    )
    if deps.persist and quality.eligibility_status == "eligible":
        assert deps.engine is not None
        await reserve_and_emit_event(
            deps.engine,
            uuid.UUID(state["run_id"]),
            "evidence",
            _evidence_event_payload(evidence),
        )
    evidences = [*state.get("evidences", []), evidence]
    observations = [
        *state.get("observations", []),
        {
            "node": "quality_validator",
            "evidence_id": evidence["evidence_id"],
            "quality": evidence["quality"],
        },
    ]
    return {
        "evidences": evidences,
        "observations": observations,
        "pending_t5": {},
        "steps_used": step,
        "usage": usages,
    }


async def _claim_builder_node(deps: GraphDependencies, state: AgentState) -> AgentState:
    specs_by_id = {
        item["evidence_id"]: item.get("claim_specs", [])
        for item in state.get("claim_specs_by_evidence", [])
    }
    built_records: list[dict[str, Any]] = []
    rejected = [*state.get("rejected_claims", [])]
    for evidence in state.get("evidences", []):
        evidence_id = evidence["evidence_id"]
        quality = evidence.get("quality", {})
        if quality.get("eligibility_status") != "eligible":
            continue
        if quality.get("classification") == "no_recomendada":
            continue
        payloads = specs_by_id.get(evidence_id, [])
        specs = tuple(
            ClaimSpec(
                claim_type=item["claim_type"],
                description=item["description"],
                source_row_indexes=tuple(item["source_row_indexes"]),
                columns=tuple(item["columns"]),
                unit=item.get("unit"),
                rounding=item.get("rounding"),
                formula=item.get("formula"),
            )
            for item in payloads
        )
        result = build_claims(
            EvidenceContext(
                dataset_id=evidence["dataset_id"],
                canonical_soql=evidence["soql_query"],
                rows=tuple(evidence.get("rows", [])),
            ),
            specs,
        )
        rejected.extend(
            {"evidence_id": evidence_id, "description": item.description, "reason": item.reason}
            for item in result.rejected
        )
        if deps.persist:
            assert deps.engine is not None
            records = await persist_claims(
                deps.engine,
                uuid.UUID(state["run_id"]),
                uuid.UUID(evidence_id),
                evidence["dataset_id"],
                result.claims,
            )
        else:
            records = [
                {
                    "claim_id": str(uuid.uuid4()),
                    "claim": f"{item.description.rstrip(' .:')}: {item.display_value}",
                    "claim_type": item.claim_type,
                    "evidence_id": evidence_id,
                    "dataset_id": evidence["dataset_id"],
                    "source_row_indexes": list(item.source_row_indexes),
                    "columns": list(item.columns_used),
                    "formula": item.formula,
                    "raw_value": (
                        int(item.raw_value)
                        if item.raw_value == item.raw_value.to_integral_value()
                        else float(item.raw_value)
                    ),
                    "display_value": item.display_value,
                    "unit": item.unit,
                    "rounding": item.rounding,
                    "source_hash": item.source_hash,
                }
                for item in result.claims
            ]
        built_records.extend(records)
    step, usages = await _record(
        deps,
        state,
        node="claim_builder",
        display_message="Construí las cifras verificables de la respuesta.",
        detail={"accepted": len(built_records), "rejected": len(rejected)},
        tool_output={"claims": built_records, "rejected": rejected},
    )
    return {
        "claims": [*state.get("claims", []), *built_records],
        "rejected_claims": rejected,
        "steps_used": step,
        "usage": usages,
    }


def _orphan_figures(
    output: SynthesisOutput, claims: list[dict[str, Any]]
) -> tuple[str, ...]:
    accepted = [claim["display_value"] for claim in claims]
    texts = [output.summary or "", output.narrative or ""]
    orphans: list[str] = []
    for text in texts:
        orphans.extend(find_orphan_figures(text, accepted))
    claims_by_evidence: dict[str, list[str]] = {}
    for claim in claims:
        claims_by_evidence.setdefault(claim["evidence_id"], []).append(claim["display_value"])
    for narrative in output.evidence_narratives:
        orphans.extend(
            find_orphan_figures(
                narrative.narrative, claims_by_evidence.get(narrative.evidence_id, [])
            )
        )
    return tuple(dict.fromkeys(orphans))


def _reviewed_datasets_from_observations(state: AgentState) -> dict[str, dict[str, Any]]:
    reviewed: dict[str, dict[str, Any]] = {}
    for observation in state.get("observations", []):
        if observation.get("tool") != "buscar_catalogo":
            continue
        output = observation.get("output", {})
        if not output.get("ok"):
            continue
        for result in output.get("results", []):
            dataset_id = result.get("dataset_id")
            if dataset_id:
                reviewed[dataset_id] = result
    return reviewed


async def _synthesizer_node(deps: GraphDependencies, state: AgentState) -> AgentState:
    started = time.perf_counter()
    usages = [*state.get("usage", [])]
    output: SynthesisOutput | None = None
    orphan_feedback: list[str] = []
    attempts = 0
    try:
        for attempt in range(MAX_SYNTHESIS_RETRIES + 1):
            attempts = attempt + 1
            parsed, usage = await _invoke_structured(
                deps,
                deps.synthesizer_model,
                SynthesisOutput,
                "synthesizer",
                {
                    "mode": "completed" if state.get("claims") else "no_evidence",
                    "question": state["question"],
                    "intention": state.get("intention"),
                    "evidences": [
                        {
                            key: value
                            for key, value in evidence.items()
                            if key not in {"rows", "narrative"}
                        }
                        for evidence in state.get("evidences", [])
                    ],
                    "claims": state.get("claims", []),
                    "rejected_claims": state.get("rejected_claims", []),
                    "termination_reason": state.get("termination_reason"),
                    "orphan_feedback": orphan_feedback,
                },
            )
            assert isinstance(parsed, SynthesisOutput)
            output = parsed
            if usage is not None:
                usages.append(usage)
            orphan_feedback = list(_orphan_figures(output, state.get("claims", [])))
            if not orphan_feedback:
                break
    except LLMProviderError as exc:
        step, recorded_usage = await _record(
            deps,
            {**state, "usage": usages},
            node="synthesizer",
            display_message="No fue posible redactar la respuesta.",
            error=str(exc),
        )
        return {
            "steps_used": step,
            "usage": recorded_usage,
            "terminal_error": _terminal_error(
                "LLM_PROVIDER_ERROR",
                "El servicio de inteligencia artificial no pudo redactar la respuesta.",
                str(exc),
            ),
        }
    if output is None or orphan_feedback:
        message = f"Cifras huérfanas tras {attempts} intentos: {orphan_feedback}"
        step, recorded_usage = await _record(
            deps,
            {**state, "usage": usages},
            node="synthesizer",
            display_message="La respuesta fue bloqueada porque contenía cifras sin respaldo.",
            detail={"orphan_figures": orphan_feedback, "attempts": attempts},
            error=message,
        )
        return {
            "steps_used": step,
            "usage": recorded_usage,
            "synthesis_attempts": attempts,
            "terminal_error": _terminal_error(
                "INTERNAL",
                "La respuesta no superó la verificación de cifras y no será entregada.",
                message,
            ),
        }
    narrative_map = {item.evidence_id: item.narrative for item in output.evidence_narratives}
    evidences = [
        {**evidence, "narrative": narrative_map.get(evidence["evidence_id"])}
        for evidence in state.get("evidences", [])
        if evidence.get("quality", {}).get("eligibility_status") == "eligible"
    ]
    if deps.persist:
        assert deps.engine is not None
        await update_evidence_narratives(deps.engine, narrative_map)
    status = "completed" if state.get("claims") else "no_evidence"
    if status == "no_evidence" and output.summary is None:
        output.summary = "No encontré evidencia suficiente en el catálogo para responder."
    if status == "no_evidence" and output.no_evidence_report is None:
        output.no_evidence_report = NoEvidenceReport(
            reason="Las fuentes revisadas no permiten responder la pregunta con precisión.",
            suggestions=["Reformular la pregunta con un territorio o tema más amplio."],
        )
    if output.no_evidence_report is not None:
        actual_datasets = _reviewed_datasets_from_observations(state)
        output.no_evidence_report.datasets_reviewed = [
            ReviewedDataset(
                dataset_id=item.dataset_id,
                name=actual_datasets[item.dataset_id].get("name", item.name),
                why_rejected=item.why_rejected,
            )
            for item in output.no_evidence_report.datasets_reviewed
            if item.dataset_id in actual_datasets
        ]
    final_answer = {
        "run_id": state["run_id"],
        "status": status,
        "intention": state.get("intention"),
        "summary": output.summary,
        "narrative": output.narrative if status == "completed" else None,
        "evidence": evidences if status == "completed" else [],
        "claims": state.get("claims", []) if status == "completed" else [],
        "no_evidence_report": (
            output.no_evidence_report.model_dump()
            if output.no_evidence_report is not None
            else None
        ),
        "usage": {
            "steps_used": state.get("steps_used", 0) + 1,
            **_usage_totals({**state, "usage": usages}),
            "termination_reason": state.get("termination_reason"),
        },
    }
    step, recorded_usage = await _record(
        deps,
        {**state, "usage": usages},
        node="synthesizer",
        display_message=(
            "Preparé una respuesta con evidencia verificable."
            if status == "completed"
            else "No encontré evidencia suficiente para responder con cifras."
        ),
        detail={"status": status, "synthesis_attempts": attempts},
        latency_ms=round((time.perf_counter() - started) * 1000),
    )
    final_answer["usage"]["steps_used"] = step
    return {
        "final_answer": final_answer,
        "steps_used": step,
        "usage": recorded_usage,
        "synthesis_attempts": attempts,
    }


def _after_planner(state: AgentState) -> str:
    return END if state.get("terminal_error") else "router"


def _after_router(state: AgentState) -> str:
    if state.get("terminal_error"):
        return END
    action = state.get("pending_action", {}).get("action", "finish")
    if action == "finish":
        return "claim_builder" if state.get("evidences") else "synthesizer"
    return f"tool__{action}"


def _after_t5(state: AgentState) -> str:
    if state.get("terminal_error"):
        return END
    return "quality_validator" if state.get("pending_t5") else "router"


def _after_quality(state: AgentState) -> str:
    return END if state.get("terminal_error") else "router"


def build_graph(deps: GraphDependencies, checkpointer: Any = None, *, interrupt: bool = True):
    """Compila el grafo real; en producción cada `ainvoke` avanza un nodo."""

    graph = StateGraph(AgentState)
    graph.add_node("planner", partial(_planner_node, deps))
    graph.add_node("router", partial(_router_node, deps))
    for tool_name in TOOL_NAMES:
        graph.add_node(f"tool__{tool_name}", _tool_node(deps, tool_name))
    graph.add_node("quality_validator", partial(_quality_node, deps))
    graph.add_node("claim_builder", partial(_claim_builder_node, deps))
    graph.add_node("synthesizer", partial(_synthesizer_node, deps))
    graph.set_entry_point("planner")
    graph.add_conditional_edges("planner", _after_planner)
    graph.add_conditional_edges("router", _after_router)
    for tool_name in TOOL_NAMES[:-1]:
        graph.add_edge(f"tool__{tool_name}", "router")
    graph.add_conditional_edges("tool__ejecutar_soql", _after_t5)
    graph.add_conditional_edges("quality_validator", _after_quality)
    graph.add_edge("claim_builder", "synthesizer")
    graph.add_edge("synthesizer", END)
    return graph.compile(
        checkpointer=checkpointer,
        interrupt_after=list(GRAPH_NODES) if interrupt else None,
    )
