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
from pydantic import BaseModel, ConfigDict, Field, model_validator
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
    LLMStructuredOutputError,
    ainvoke_structured_chat_model,
    usage_from_message,
)
from app.quality.claims import (
    ClaimSpec,
    EvidenceContext,
    build_claims,
    find_figures,
    find_orphan_figures,
)
from app.quality.external_sources import suggest_external_sources
from app.quality.territorial import comparabilidad_territorial
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
    "territorial_comparability",
    "quality_validator",
    "claim_planner",
    "claim_builder",
    "synthesizer",
)
MAX_SOQL_CALLS = 4
MAX_SOQL_CORRECTIONS = 2
# Hallazgo (2026-07-12, diagnostico real sobre pilot-002/006/008): sin tope,
# el router podia repetir explorar_valores indefinidamente sobre la misma
# dataset_id+columna (p. ej. dos exploraciones vacias consecutivas por
# tildes/nombre real distinto al termino literal), agotando el presupuesto
# de pasos antes de intentar ejecutar_soql. El tope permite el intento
# inicial + UNA reformulacion (misma columna, termino distinto); ver
# `_router_node`.
MAX_EXPLORE_ATTEMPTS_PER_COLUMN = 2
# Hallazgo (2026-07-12, smoke real 8/8 casos contra Gemini tras las
# correcciones anteriores de esta sesion, success_rate=20%): la regla de
# `router_v1.md` que prohibe `finish` prematuro NO bastaba por si sola --
# 4 de los 8 casos originales (pilot-004, 005, 007, 008) mostraron el LLM
# real perfilando o encontrando un dataset elegible y terminando de todas
# formas sin intentar ejecutar_soql. Igual que con `evidence_id`
# (`MAX_CLAIM_EVIDENCE_ID_REPAIR_ATTEMPTS`), la unica correccion confiable
# es determinista dentro del mismo paso: ver `_has_untried_eligible_dataset`
# y `_router_node`.
#
# Hallazgo adicional (mismo smoke, ronda siguiente): con 1 solo intento de
# reparacion, pilot-002/005/007 mostraron un patron mas dificil: el
# `reasoning_summary` del router describia una oracion COMPLETA (no
# truncada por el limite de 500 caracteres) anunciando que iba a ejecutar
# `ejecutar_soql`/`perfilar_dataset`, pero el campo `action` real seguia
# siendo `finish` -- una inconsistencia genuina entre el texto libre y la
# decision estructurada del proveedor, que un solo mensaje de correccion no
# siempre revierte. 2 intentos de reparacion (3 llamadas reales en total,
# todas dentro del mismo paso, sin costo de presupuesto de investigacion)
# da mas resiliencia sin volverse un bucle sin limite.
MAX_ROUTER_FINISH_REPAIR_ATTEMPTS = 2
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
MAX_CLAIM_REPAIR_ATTEMPTS = 1
# Hallazgo (2026-07-12, diagnostico real sobre pilot-003, ejecucion con
# Gemini): `claim_planner` afirmaba `planned=10` y `claim_builder` aceptaba
# 0 sin rechazar nada -- el LLM devolvio un `evidence_id` que no coincidia
# con ningun `state["evidences"][i]["evidence_id"]` real (el esquema de
# `EvidenceClaimPlan.evidence_id` solo exige `str`, no pertenencia al
# estado). `claim_builder` hace `specs_by_id.get(evidence_id, [])`, que
# devuelve `[]` en silencio ante cualquier id desconocido -- ni acepta ni
# rechaza, simplemente pierde el enlace referencial completo. Ver
# `_claim_planner_node`: la validacion semantica (solo puede hacerse contra
# el estado real en tiempo de ejecucion, no en el esquema de Pydantic) se
# repara DENTRO del mismo paso, igual que el repair loop de
# `ainvoke_structured_chat_model`, para no gastar presupuesto de pasos del
# grafo en corregir un error de formato.
MAX_CLAIM_EVIDENCE_ID_REPAIR_ATTEMPTS = 1
LLM_ROWS_MAX = 50
EVIDENCE_ROWS_MAX_BYTES = 1024 * 1024
EVIDENCE_EVENT_MAX_BYTES = 256 * 1024

# Hallazgo T-403 (2026-07-11, ejecucion real, run_id=fea461c4-...): una
# corrida que se detuvo en el paso 7 de 10 quedaba etiquetada igual
# ("STEP_BUDGET_EXCEEDED") que una que de verdad agoto los 10 pasos -- el
# grafo reserva preventivamente los pasos minimos para poder cerrar
# (`_router_force_finish`/`_minimum_after_router`) y ESA decision preventiva
# se confundia con el agotamiento real. Se separan las razones para que
# `agent_runs`/`eval_case_results` reflejen la causa real (RF-703, Art.
# VII.3): "STEP_BUDGET_EXCEEDED" queda reservado para cuando `steps_used` ya
# alcanzo `max_steps` al entrar al router; el resto de paradas preventivas
# usa una etiqueta especifica del recurso que se agoto.
TERMINATION_STEP_BUDGET_EXCEEDED = "STEP_BUDGET_EXCEEDED"
TERMINATION_INSUFFICIENT_BUDGET_FOR_ACTION = "INSUFFICIENT_BUDGET_FOR_ACTION"
TERMINATION_SOQL_CALL_BUDGET_EXCEEDED = "SOQL_CALL_BUDGET_EXCEEDED"
TERMINATION_SOQL_CORRECTION_EXHAUSTED = "SOQL_CORRECTION_EXHAUSTED"
TERMINATION_EXPLORE_BUDGET_EXCEEDED = "EXPLORE_BUDGET_EXCEEDED"

ToolCallable = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
MetadataLoader = Callable[[str], Awaitable[DatasetEvidenceMetadata | None]]
TerritorialLoader = Callable[[list[str]], Awaitable[dict[str, Any]]]


class PlannerOutput(BaseModel):
    intention: str = Field(min_length=1, max_length=500)
    subqueries: list[str] = Field(min_length=1, max_length=5)
    recommended_next_action: str = Field(min_length=1, max_length=200)


# Hallazgo T-403 (2026-07-12, smoke real con Gemini). Dos capas de bug en
# `FormulaNode`, ambas confirmadas contra la API real, no contra
# `convert_to_openai_tool` (el conversor de OpenAI, que nunca se usa en este
# proyecto y da falsa confianza -- ver nota junto a `RouterToolInput`):
#
# 1. La union discriminada original (`ConstFormulaNode`/`ColFormulaNode`/
#    `AggFormulaNode`/`OpFormulaNode`) no revienta al construir el schema
#    (tiene rama `null`), pero `langchain_google_genai._function_utils.
#    _get_properties_from_schema` colapsa un `anyOf` nullable de puros
#    OBJECT a la ULTIMA rama -- Gemini solo veia la forma de `OpFormulaNode`
#    (`op`+`args`), nunca `const`/`col`/`agg`. Se aplano a un unico modelo
#    con los 4 campos como `Optional[X]` (eso si es seguro) + un
#    `model_validator` que exige la combinacion exacta.
# 2. Ese primer aplanado seguia usando `args: list[FormulaNode]` --
#    VERDADERAMENTE recursivo (FormulaNode referenciandose a si mismo). La
#    API real de Gemini lo rechazo con 400 en el primer paso de cada corrida
#    real (confirmado con `execute_agent_run_async` directo, sin mocks):
#    `GenerateContentRequest...properties[formula].properties[args].items:
#    missing field`. Causa: `dereference_refs` (langchain_core) no puede
#    inlinar una auto-referencia genuina y deja `items` vacio; Gemini exige
#    `items` en todo campo ARRAY.
#
# Fix final: `args` usa `FormulaLeaf` (sin `op`/`args`, sin auto-referencia)
# en vez de `FormulaNode`. Esto CIERRA -- no solo documenta -- la regla que
# `router_v1.md` ya pedia en texto ("los nodos 'op' no pueden anidarse
# dentro de otro 'op'"): antes esa regla no se hacia cumplir a nivel de
# Pydantic (`model_validate` aceptaba `op` anidado, ver historial de
# `test_claim_spec_payload_accepts_every_real_dsl_shape`); ahora es
# estructuralmente imposible, en el schema Y en la validacion.
class FormulaLeaf(BaseModel):
    model_config = ConfigDict(extra="forbid")

    const: float | None = None
    col: str | None = None
    # Debe coincidir con app.quality.claims.ALLOWED_AGG_FUNCTIONS.
    agg: Literal["sum", "avg", "count", "min", "max"] | None = None

    @model_validator(mode="after")
    def _forma_reconocida(self) -> FormulaLeaf:
        is_const = self.const is not None
        is_col = self.col is not None
        is_agg = self.agg is not None
        shape_const = is_const and not (is_col or is_agg)
        shape_col = is_col and not is_agg and not is_const
        shape_agg = is_agg and is_col and not is_const
        if not (shape_const or shape_col or shape_agg):
            raise ValueError(
                'un argumento de "args" debe ser EXACTAMENTE una de: '
                '{"const": <numero>} | {"col": "<columna>"} | '
                '{"agg": "sum|avg|count|min|max", "col": "<columna>"}'
            )
        return self


class FormulaNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    const: float | None = None
    col: str | None = None
    agg: Literal["sum", "avg", "count", "min", "max"] | None = None
    # Debe coincidir con app.quality.claims.ALLOWED_OPS.
    op: Literal["add", "sub", "mul", "div", "ratio", "pct_change"] | None = None
    args: list[FormulaLeaf] | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _forma_reconocida(self) -> FormulaNode:
        is_const = self.const is not None
        is_col = self.col is not None
        is_agg = self.agg is not None
        is_op = self.op is not None
        is_args = self.args is not None
        shape_const = is_const and not (is_col or is_agg or is_op or is_args)
        shape_col = is_col and not is_agg and not (is_const or is_op or is_args)
        shape_agg = is_agg and is_col and not (is_const or is_op or is_args)
        shape_op = is_op and is_args and not (is_const or is_col or is_agg)
        if not (shape_const or shape_col or shape_agg or shape_op):
            raise ValueError(
                "formula debe ser EXACTAMENTE una de estas 4 formas, sin mezclar "
                'campos de formas distintas: {"const": <numero>} | '
                '{"col": "<columna>"} | {"agg": "sum|avg|count|min|max", '
                '"col": "<columna>"} | {"op": "add|sub|mul|div|ratio|pct_change", '
                '"args": [<hoja>, <hoja>, ...]} (cada <hoja> es const/col/agg, '
                "NUNCA otro op -- pide los subtotales como claims 'derived' "
                "separados si necesitas mas de un nivel)."
            )
        return self


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

    @model_validator(mode="after")
    def _direct_usa_una_fila_y_una_columna(self) -> ClaimSpecPayload:
        """Hallazgo T-403 (2026-07-11, ejecucion real, run_id=32ad6d77-...):
        con el dataset y el SoQL correctos, T7 (`build_claims`,
        `app/quality/claims.py::_build_direct`) rechazo los 3 claims que el
        router propuso porque cada uno mezclaba la categoria (p. ej.
        `nombre_evento`) y la cifra (p. ej. `total_casos`) como dos columnas
        de un mismo claim `direct` -- ese tipo solo admite exactamente una
        fila y una columna (contracts/agent-tools.md §T7); la investigacion
        completa se perdio en el ultimo paso porque el rechazo llegaba
        DESPUES de gastar el paso de `claim_builder`. Se adelanta la misma
        regla aqui para que sea un error de Pydantic -- corregible por el
        repair loop de `ainvoke_structured_chat_model` sin gastar presupuesto
        de investigacion -- en vez de un rechazo silencioso de T7. La
        categoria/dimension debe ir en `description` (texto), nunca como una
        segunda columna cuantitativa.
        """
        if self.claim_type == "direct" and (
            len(self.source_row_indexes) != 1 or len(self.columns) != 1
        ):
            raise ValueError(
                "un claim_type='direct' debe tener exactamente una fila en "
                "source_row_indexes y una columna numerica en columns; toda "
                "categoria o dimension asociada (p. ej. el nombre de la fila) "
                "va en 'description', no como una segunda columna. Si "
                "necesitas varias cifras, proponlas como claims 'direct' "
                "separados, uno por columna."
            )
        return self


def _validate_formula_dsl(node: object, *, depth: int = 0) -> dict[str, Any]:
    """Valida la DSL contractual completa sin exponer recursión al schema LLM.

    Gemini no puede convertir de forma fiable un JSON Schema recursivo, pero
    T7 sí admite operaciones anidadas. El claim planner entrega la fórmula
    como JSON string y esta función valida recursivamente el contenido antes
    de que llegue al constructor determinista de claims.
    """
    if depth > 8 or not isinstance(node, dict):
        raise ValueError("formula_json contiene un nodo inválido o demasiado profundo")
    keys = set(node)
    if keys == {"const"}:
        value = node["const"]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("formula_json.const debe ser numérico")
        return node
    if keys == {"col"} and isinstance(node["col"], str) and node["col"]:
        return node
    if keys == {"agg", "col"}:
        if node["agg"] not in {"sum", "avg", "count", "min", "max"}:
            raise ValueError("formula_json.agg no está permitido")
        if not isinstance(node["col"], str) or not node["col"]:
            raise ValueError("formula_json.col debe ser un nombre de columna")
        return node
    if keys == {"op", "args"}:
        if node["op"] not in {"add", "sub", "mul", "div", "ratio", "pct_change"}:
            raise ValueError("formula_json.op no está permitido")
        args = node["args"]
        if not isinstance(args, list) or len(args) < 2:
            raise ValueError("formula_json.args debe contener al menos dos nodos")
        for child in args:
            _validate_formula_dsl(child, depth=depth + 1)
        return node
    raise ValueError("formula_json no coincide con ninguna forma de la DSL T7")


class ClaimPlannerSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_type: Literal["direct", "derived"]
    description: str = Field(min_length=1, max_length=500)
    source_row_indexes: list[int] = Field(min_length=1)
    columns: list[str] = Field(min_length=1)
    unit: str | None = None
    rounding: int | None = Field(default=None, ge=0, le=8)
    formula_json: str | None = None

    @model_validator(mode="after")
    def _validate_claim(self) -> ClaimPlannerSpec:
        if self.claim_type == "direct":
            if len(self.source_row_indexes) != 1 or len(self.columns) != 1:
                raise ValueError("un claim direct requiere exactamente una fila y una columna")
            if self.formula_json is not None:
                raise ValueError("un claim direct no usa formula_json")
        else:
            if not self.formula_json:
                raise ValueError("un claim derived requiere formula_json")
            try:
                formula = json.loads(self.formula_json)
            except json.JSONDecodeError as exc:
                raise ValueError(f"formula_json no es JSON válido: {exc.msg}") from exc
            _validate_formula_dsl(formula)
        return self

    def to_claim_payload(self) -> dict[str, Any]:
        return {
            "claim_type": self.claim_type,
            "description": self.description,
            "source_row_indexes": self.source_row_indexes,
            "columns": self.columns,
            "unit": self.unit,
            "rounding": self.rounding,
            "formula": json.loads(self.formula_json) if self.formula_json else None,
        }


class EvidenceClaimPlan(BaseModel):
    evidence_id: str
    claim_specs: list[ClaimPlannerSpec]


class ClaimPlannerOutput(BaseModel):
    reasoning_summary: str = Field(min_length=1, max_length=500)
    claim_specs_by_evidence: list[EvidenceClaimPlan]


class EvidenceClaimSpecs(BaseModel):
    evidence_id: str
    claim_specs: list[ClaimSpecPayload]


# Hallazgo T-403 (2026-07-11, ejecucion real, run_id=fea461c4-...; endurecido
# 2026-07-11 tras evaluacion externa, docs/instrucciones-evaluacion-agente-
# post-ajustes.md puerta 2; REVERTIDO 2026-07-12 tras smoke real con Gemini,
# 0/8 casos -- ver nota mas abajo): el LLM invoco `explorar_valores` sin
# `termino_busqueda` -- campo obligatorio segun contracts/agent-tools.md §T4
# -- porque `RouterToolInput` declara TODOS los campos de TODAS las
# herramientas como opcionales. La solucion "correcta" en teoria era una
# union discriminada por accion (mismo patron que `FormulaNode`, un modelo
# `extra="forbid"` por accion). Se implemento asi el 2026-07-11 y las
# pruebas locales (incluida una que inspeccionaba
# `convert_to_openai_tool(RouterOutput)`, el conversor de OpenAI) pasaron.
#
# PERO ese esquema NUNCA se probo contra el conversor REAL que usa este
# proyecto para Gemini (`langchain_google_genai._function_utils`), que es
# una ruta de codigo completamente distinta de `convert_to_openai_tool`. Un
# smoke real (2026-07-12, 8 casos del golden set, 0/8 completed) revento en
# el primer paso de CADA corrida con
# `ValueError: Unknown field for Schema: anyOf`, reproducible localmente sin
# gastar cuota:
#   `_convert_pydantic_to_genai_function(RouterOutput)` -- con `tool_input`
#   como union de 6 modelos SIN rama `null` -- lanza esa excepcion porque el
#   SDK instalado de `google-generativeai` no soporta un `anyOf` de nivel de
#   propiedad que no tenga una rama `{"type": "null"}` (confirmado leyendo
#   `_get_properties_from_schema`, linea ~336: solo arma el `anyOf` "tal
#   cual" -- y ese `anyOf` no es un campo valido del proto `Schema` -- si
#   NINGUNA rama es `null`; un campo `Optional[X]` corriente SI tiene rama
#   `null` y toma otra ruta que si funciona). Confirmado tambien que
#   `formula: FormulaNode | None` (la union pre-existente, que SI tiene rama
#   `null`) NO dispara este choque -- es un problema especifico de unions
#   "duras" sin `None`, no de unions en general.
#
# Se revierte `tool_input` a un modelo plano unico (sin `anyOf` no-nulo) con
# TODOS los campos opcionales -- exactamente compatible con Gemini -- y se
# recupera la garantia de "campos obligatorios por accion" con un
# `model_validator` de Python (el mismo mecanismo que ya usa el repair loop
# de `ainvoke_structured_chat_model`). Es mas debil que un schema que el
# proveedor respete al generar (la constrained decoding de Gemini no evita
# que intente omitir un campo), pero es la unica opcion que no tumba la
# corrida entera. Regla general para cualquier cambio futuro de schema: NO
# alcanza con probar `convert_to_openai_tool`; hay que probar el conversor
# real de cada proveedor configurado (ver
# `tests/test_agent_router_contracts.py`).
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


_REQUIRED_TOOL_INPUT_FIELDS: dict[str, tuple[str, ...]] = {
    "buscar_catalogo": ("query",),
    "perfilar_dataset": ("dataset_id",),
    "resolver_geografia": ("termino",),
    "explorar_valores": ("dataset_id", "columna", "termino_busqueda"),
    "ejecutar_soql": ("dataset_id", "soql", "purpose"),
}


class RouterOutput(BaseModel):
    """Hallazgo (2026-07-12, investigacion offline sobre 19+ corridas reales
    ya persistidas de pilot-002/005/007/008, sin gastar cuota nueva de
    Gemini): en varias decisiones `action="finish"` inspeccionadas, el
    propio `reasoning_summary` describia una intencion explicita de seguir
    investigando ("voy a ejecutar...", "I will now query...", "procedo
    a...") en vez de justificar por que detenerse. Clasificando las 9
    instancias confirmadas por longitud y puntuacion final:
    - 7 de 9 son oraciones COMPLETAS (terminan en punto/interrogacion),
      muy por debajo de 500 caracteres (266-491): inconsistencia genuina
      del proveedor, no truncamiento. Sigue sin causa aislada -- ver
      research.md #23.
    - 2 de 9 terminan EXACTAMENTE en 500 caracteres Y a mitad de frase
      (`"...e incluyendo el"`, sin sustantivo): el texto real era mas largo
      y `_truncate_overflowing_strings` (`app/llm/factory.py`) lo recorto
      en silencio al limite de Pydantic, perdiendo justo la parte final
      -- que en un campo de razonamiento suele ser la conclusion/decision,
      no contenido intercambiable. Corregido subiendo `max_length` de 500
      a 900: dobla el margen antes de necesitar ese camino de recuperacion
      con perdida. No corrige el otro 78% (inconsistencia genuina), pero
      cierra un artefacto real y confirmado sin ambiguedad.

    Hipotesis probada y DESCARTADA por separado: que declarar
    `reasoning_summary` antes que `action` en este modelo (como ya hace
    `ClaimPlannerOutput`) forzara a Gemini a "razonar antes de decidir", si
    la decodificacion restringida genera JSON en el orden declarado del
    esquema. Verificado directamente contra
    `_convert_pydantic_to_genai_function` (el conversor real que usa este
    proyecto, no `convert_to_openai_tool`): el orden de
    `model_json_schema()['properties']` SI seguia el orden declarado, y
    `dereference_refs` tampoco lo alteraba -- pero el orden final expuesto
    en `FunctionDeclaration.parameters.properties` (comparado antes/despues
    de reordenar los campos) NO coincidia con ninguno de los dos ordenes
    (ni el declarado, ni alfabetico, ni el revertido de forma consistente
    entre `RouterOutput`/`PlannerOutput`/`SynthesisOutput`). El campo
    `properties` de `google.ai.generativelanguage.Schema` es un mapa
    protobuf, sin garantia de orden en su representacion interna/wire --
    reordenar los campos de este modelo Pydantic no tiene ningun efecto
    verificable sobre el orden real que Gemini recibe. La mitigacion real
    para la inconsistencia genuina vive en `router_v1.md` (regla de
    autoconsistencia razonamiento/accion) y en el repair loop de
    `_has_untried_eligible_dataset`, no en el orden de campos del esquema.
    """

    action: str = Field(min_length=1)
    reasoning_summary: str = Field(min_length=1, max_length=900)
    tool_input: RouterToolInput

    @model_validator(mode="after")
    def _tool_input_trae_los_campos_obligatorios(self) -> RouterOutput:
        required = _REQUIRED_TOOL_INPUT_FIELDS.get(self.action.strip())
        if required is None:
            # accion desconocida o "finish": el grafo (`_router_node`) valida
            # accion contra TOOL_NAMES/"finish" por separado; no es
            # responsabilidad de este esquema.
            return self
        # Hallazgo (2026-07-12, smoke real contra Gemini, pilot-003): el LLM
        # envio termino_busqueda="" (string vacio, no None) para
        # explorar_valores -- pasaba esta validacion (solo miraba `is None`)
        # y solo fallaba despues, dentro de la herramienta, con
        # INVALID_INPUT, gastando un paso completo. Un string vacio o solo
        # espacios es tan "ausente" como None para un campo obligatorio.
        missing = [
            field
            for field in required
            if (value := getattr(self.tool_input, field)) is None
            or (isinstance(value, str) and not value.strip())
        ]
        if missing:
            raise ValueError(
                f"tool_input incompleto para action={self.action!r}: "
                f"falta(n) los campos obligatorios {', '.join(missing)}"
            )
        return self


class EvidenceNarrative(BaseModel):
    evidence_id: str
    narrative: str


class ReviewedDataset(BaseModel):
    dataset_id: str
    name: str
    why_rejected: str


class ExternalSourceSuggestion(BaseModel):
    """Poblado SIEMPRE por código determinista (`suggest_external_sources`),
    nunca por el LLM -- ver `_synthesizer_node` y research.md §18."""

    entidad: str
    url: str
    por_que: str


class NoEvidenceReport(BaseModel):
    reason: str
    datasets_reviewed: list[ReviewedDataset] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    external_sources: list[ExternalSourceSuggestion] = Field(default_factory=list)


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
    territorial_checked_codes: list[str]
    territorial_comparability: dict[str, Any] | None
    evidences: list[dict[str, Any]]
    claim_specs_by_evidence: list[dict[str, Any]]
    claims: list[dict[str, Any]]
    rejected_claims: list[dict[str, Any]]
    steps_used: int
    max_steps: int
    t5_calls: int
    soql_corrections: dict[str, int]
    explore_attempts: dict[str, int]
    usage: list[dict[str, Any]]
    termination_reason: str | None
    final_answer: dict[str, Any]
    terminal_error: dict[str, Any]
    synthesis_attempts: int
    claim_repair_attempts: int
    claim_builder_retry_pending: bool


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
    territorial_loader: TerritorialLoader | None = None
    claim_model: Runnable | None = None


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
        "territorial_checked_codes": [],
        "territorial_comparability": None,
        "evidences": [],
        "claims": [],
        "rejected_claims": [],
        "steps_used": 0,
        "max_steps": max_steps,
        "t5_calls": 0,
        "soql_corrections": {},
        "explore_attempts": {},
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


def _llm_terminal_error(
    exc: LLMProviderError, *, provider_message: str, structured_message: str
) -> dict[str, Any]:
    """Distingue una falla real del proveedor (red, cuota, 5xx, timeout) de
    una salida estructurada que sigue invalida tras agotar el repair loop
    (hallazgo del agente evaluador, docs/instrucciones-evaluacion-agente-
    post-ajustes.md puerta 3): antes ambas llegaban como el mismo
    `LLMProviderError` y se mapeaban siempre a `LLM_PROVIDER_ERROR`,
    indistinguibles para diagnostico (RF-703). `STRUCTURED_OUTPUT_INVALID`
    (contracts/api-rest.md §4) es la causa mas especifica; no es
    `retryable` porque reintentar la corrida completa no cambia el
    resultado (es un problema de esquema/prompt, no de red)."""
    if isinstance(exc, LLMStructuredOutputError):
        return _terminal_error("STRUCTURED_OUTPUT_INVALID", structured_message, str(exc))
    return _terminal_error("LLM_PROVIDER_ERROR", provider_message, str(exc))


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
    # router + claim_planner + claim_builder + synthesizer, o router +
    # synthesizer sin evidencia.
    required = 4 if state.get("evidences") else 2
    return remaining_before_router <= required


def _minimum_after_router(action: str) -> int:
    if action == "ejecutar_soql":
        # tool + T6 + router final + claim_planner + T7 + sintetizador
        return 6
    # tool + router final + sintetizador
    return 3


def _has_untried_eligible_dataset(state: AgentState) -> bool:
    """True si el router puede seguir investigando en vez de declarar
    `finish`.

    Dos casos, ambos hallazgos reales del smoke 2026-07-12:
    1. `buscar_catalogo` encontro un dataset elegible y el router nunca
       intento consultarlo (`t5_calls=0`) -- no cuenta `perfilar_dataset`
       como "intentado" porque perfilar no produce evidencia (pilot-004,
       pilot-005: el LLM perfilo un dataset elegible y termino de todas
       formas sin llegar nunca a T5).
    2. Ya se ejecuto `ejecutar_soql` (`t5_calls>0`) pero NINGUNA evidencia
       resultante quedo usable (`blocked`/`no_recomendada`) -- un SoQL
       bloqueado por PII/agregacion insuficiente no es un "no hay evidencia"
       definitivo (pilot-002: el propio router explico en su
       `reasoning_summary` que reintentaria con mejor agregacion para
       superar el bloqueo PII, y aun asi declaro `action=finish`).
    Ninguno de los dos casos se dispara si ya existe evidencia realmente
    usable: en ese punto `finish` puede ser una decision legitima.
    """

    has_usable_evidence = any(
        evidence.get("quality", {}).get("eligibility_status") == "eligible"
        and evidence.get("quality", {}).get("classification") != "no_recomendada"
        for evidence in state.get("evidences", [])
    )
    if has_usable_evidence:
        return False
    if state.get("t5_calls", 0) > 0:
        return bool(state.get("evidences"))
    for observation in state.get("observations", []):
        if observation.get("tool") != "buscar_catalogo":
            continue
        output = observation.get("output", {})
        if not output.get("ok"):
            continue
        if any(
            result.get("eligibility_status") == "eligible"
            for result in output.get("results", [])
        ):
            return True
    return False


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


def _resolved_territory_codes(state: AgentState) -> list[str]:
    """Codigo DIVIPOLA del match de mayor confianza de cada llamada exitosa
    a T3 (`resolver_geografia`) en la corrida, deduplicado en orden de
    aparicion (contracts/agent-tools.md §T8: "T3 resuelve >= 2 territorios
    distintos en la misma corrida")."""

    codes: list[str] = []
    for observation in state.get("observations", []):
        if observation.get("tool") != "resolver_geografia":
            continue
        output = observation.get("output", {})
        matches = output.get("matches") if output.get("ok") else None
        if not matches:
            continue
        code = matches[0].get("code")
        if code and code not in codes:
            codes.append(code)
    return codes


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
            "terminal_error": _llm_terminal_error(
                exc,
                provider_message=(
                    "El servicio de inteligencia artificial no está disponible en este momento."
                ),
                structured_message=(
                    "El agente no logró organizar la pregunta en un formato válido."
                ),
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
    max_steps = state.get("max_steps", deps.max_steps)
    if state.get("steps_used", 0) >= max_steps:
        # Agotamiento real: no queda ni un paso para invocar al LLM. A
        # diferencia de las paradas preventivas de mas abajo, aqui no tiene
        # sentido ni siquiera intentar la llamada (ahorra costo real).
        return {
            "pending_action": {"action": "finish", "tool_input": {}},
            "termination_reason": TERMINATION_STEP_BUDGET_EXCEEDED,
            "steps_used": state.get("steps_used", 0),
            "usage": state.get("usage", []),
        }
    force_finish = _router_force_finish(state)
    messages = [
        SystemMessage(content=load_prompt("router")),
        HumanMessage(
            content=json.dumps(
                json_safe(
                    {
                        "question": state["question"],
                        "intention": state.get("intention"),
                        "plan": state.get("plan", []),
                        "observations": _llm_observations(state),
                        "evidences": [
                            {**evidence, "rows": evidence.get("rows", [])[:LLM_ROWS_MAX]}
                            for evidence in state.get("evidences", [])
                        ],
                        "rejected_claims": state.get("rejected_claims", []),
                        "budget": {
                            "steps_used": state.get("steps_used", 0),
                            "max_steps": state.get("max_steps", deps.max_steps),
                            "t5_calls": state.get("t5_calls", 0),
                            "max_t5_calls": MAX_SOQL_CALLS,
                            "soql_corrections": state.get("soql_corrections", {}),
                            "explore_attempts": state.get("explore_attempts", {}),
                            "max_explore_attempts_per_column": MAX_EXPLORE_ATTEMPTS_PER_COLUMN,
                        },
                        "force_finish": force_finish,
                    }
                ),
                ensure_ascii=False,
            )
        ),
    ]
    usages = [*state.get("usage", [])]
    output: RouterOutput | None = None
    try:
        for attempt in range(MAX_ROUTER_FINISH_REPAIR_ATTEMPTS + 1):
            result = await ainvoke_structured_chat_model(
                deps.router_model, messages, schema=RouterOutput
            )
            parsed = RouterOutput.model_validate(result.parsed)
            if result.raw_message is not None:
                usages.append(
                    asdict(
                        usage_from_message(deps.llm_provider, deps.llm_model, result.raw_message)
                    )
                )
            output = parsed
            premature_finish = (
                not force_finish
                and parsed.action.strip() == "finish"
                and _has_untried_eligible_dataset(state)
            )
            if not premature_finish or attempt == MAX_ROUTER_FINISH_REPAIR_ATTEMPTS:
                break
            messages = [
                *messages,
                HumanMessage(
                    content=(
                        "buscar_catalogo ya encontró un dataset con "
                        "eligibility_status='eligible' en esta corrida y todavía no "
                        "intentaste perfilar_dataset ni ejecutar_soql sobre ninguno "
                        "(t5_calls=0, evidences=[]). No puedes declarar finish sin "
                        "intentarlo primero -- elige perfilar_dataset o ejecutar_soql "
                        "sobre ese dataset, o si de verdad no sirve para esta "
                        "pregunta, vuelve a responder finish pero explica en "
                        "reasoning_summary por qué ese dataset específico se "
                        "descarta."
                    )
                ),
            ]
    except LLMProviderError as exc:
        step, usages = await _record(
            deps,
            {**state, "usage": usages},
            node="router",
            display_message="No fue posible decidir el siguiente paso.",
            error=str(exc),
        )
        return {
            "steps_used": step,
            "usage": usages,
            "terminal_error": _llm_terminal_error(
                exc,
                provider_message=(
                    "El servicio de inteligencia artificial no está disponible en este momento."
                ),
                structured_message=(
                    "El agente no logró producir una decisión con el formato esperado, "
                    "incluso después de intentar corregirla."
                ),
            ),
        }
    assert output is not None
    requested_action = output.action.strip()
    action = requested_action
    termination_reason = state.get("termination_reason")
    # Hallazgo del agente evaluador (2026-07-11,
    # docs/instrucciones-evaluacion-agente-post-ajustes.md puerta 7,
    # test_termination_records_requested_action_remaining_and_required_steps):
    # `budget_detail` acumula que accion pidio realmente el LLM y por que
    # presupuesto especifico se le nego, para que quede en `agent_steps`
    # (RF-703) y no solo en el `termination_reason` final. Todas las
    # decisiones de presupuesto se resuelven ANTES de `_record` (antes vivian
    # despues, con el resultado de que el detalle persistido para 3 de las 4
    # causas mostraba la accion original en vez de la anulacion real).
    budget_detail: dict[str, Any] = {}
    if force_finish and requested_action != "finish":
        # Parada preventiva: no queda presupuesto para otra accion completa,
        # con o sin que el LLM ya haya devuelto "finish" por su cuenta -- en
        # ambos casos la causa es el presupuesto, no una decision "natural".
        remaining_before_router = state.get("max_steps", deps.max_steps) - state.get(
            "steps_used", 0
        )
        required = 4 if state.get("evidences") else 2
        budget_detail = {
            "requested_action": requested_action,
            "remaining_steps": remaining_before_router,
            "required_steps": required,
        }
        action = "finish"
        termination_reason = TERMINATION_INSUFFICIENT_BUDGET_FOR_ACTION
    if action not in {*TOOL_NAMES, "finish"}:
        step, recorded_usages = await _record(
            deps,
            {**state, "usage": usages},
            node="router",
            display_message="La acción solicitada no es válida.",
            detail={"requested_action": action},
            error=f"Herramienta fuera de T1-T5: {action}",
            latency_ms=round((time.perf_counter() - started) * 1000),
        )
        return {
            "steps_used": step,
            "usage": recorded_usages,
            "terminal_error": _terminal_error(
                "INTERNAL",
                "El agente solicitó una acción que no está permitida.",
                f"Herramienta fuera de T1-T5: {action}",
            ),
        }
    next_step_number = state.get("steps_used", 0) + 1
    remaining = state.get("max_steps", deps.max_steps) - next_step_number
    if action != "finish" and remaining < _minimum_after_router(action):
        budget_detail = {
            "requested_action": requested_action,
            "remaining_steps": remaining,
            "required_steps": _minimum_after_router(action),
        }
        action = "finish"
        termination_reason = TERMINATION_INSUFFICIENT_BUDGET_FOR_ACTION
    if action == "ejecutar_soql" and state.get("t5_calls", 0) >= MAX_SOQL_CALLS:
        budget_detail = {
            "requested_action": requested_action,
            "t5_calls": state.get("t5_calls", 0),
            "max_t5_calls": MAX_SOQL_CALLS,
        }
        action = "finish"
        termination_reason = TERMINATION_SOQL_CALL_BUDGET_EXCEEDED
    if action == "ejecutar_soql":
        tool_input = output.tool_input.model_dump(exclude_none=True)
        correction_key = (
            f"{tool_input.get('dataset_id', '')}:{tool_input.get('purpose', '')}"
        )
        corrections_used = state.get("soql_corrections", {}).get(correction_key, 0)
        if corrections_used > MAX_SOQL_CORRECTIONS:
            budget_detail = {
                "requested_action": requested_action,
                "correction_key": correction_key,
                "corrections_used": corrections_used,
                "max_corrections": MAX_SOQL_CORRECTIONS,
            }
            action = "finish"
            termination_reason = TERMINATION_SOQL_CORRECTION_EXHAUSTED
    if action == "explorar_valores":
        tool_input = output.tool_input.model_dump(exclude_none=True)
        explore_key = f"{tool_input.get('dataset_id', '')}:{tool_input.get('columna', '')}"
        explore_attempts_used = state.get("explore_attempts", {}).get(explore_key, 0)
        if explore_attempts_used >= MAX_EXPLORE_ATTEMPTS_PER_COLUMN:
            budget_detail = {
                "requested_action": requested_action,
                "explore_key": explore_key,
                "explore_attempts_used": explore_attempts_used,
                "max_explore_attempts_per_column": MAX_EXPLORE_ATTEMPTS_PER_COLUMN,
            }
            action = "finish"
            termination_reason = TERMINATION_EXPLORE_BUDGET_EXCEEDED
    step, recorded_usages = await _record(
        deps,
        {**state, "usage": usages},
        node="router",
        display_message=(
            "Ya reuní lo necesario para preparar la respuesta."
            if action == "finish"
            else "Elegí el siguiente paso de verificación."
        ),
        detail={"action": action, "reason": output.reasoning_summary, **budget_detail},
        latency_ms=round((time.perf_counter() - started) * 1000),
    )
    return {
        "pending_action": {
            "action": action,
            "tool_input": output.tool_input.model_dump(exclude_none=True),
        },
        # exclude_none=True: FormulaNode es un modelo aplanado (ver comentario
        # junto a su definicion) -- sin esto, el dict tendria las 5 claves
        # posibles (la mayoria en None) y _eval_node (app/quality/claims.py)
        # rechazaria la forma por no coincidir exactamente con {"const"}/
        # {"col"}/{"agg","col"}/{"op","args"}.
        "termination_reason": termination_reason,
        "steps_used": step,
        "usage": recorded_usages,
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
        if tool_name == "explorar_valores":
            key = f"{raw_input.get('dataset_id', '')}:{raw_input.get('columna', '')}"
            attempts = {**state.get("explore_attempts", {})}
            attempts[key] = attempts.get(key, 0) + 1
            result["explore_attempts"] = attempts
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


async def _territorial_node(deps: GraphDependencies, state: AgentState) -> AgentState:
    """T8 `comparabilidad_territorial` (contracts/agent-tools.md §T8). Nodo
    determinista: no usa LLM. Se ejecuta automaticamente tras T3 cuando el
    conjunto de territorios resueltos en la corrida crece a >= 2 (ver
    `_after_resolver_geografia`)."""

    started = time.perf_counter()
    codes = _resolved_territory_codes(state)
    if deps.territorial_loader is not None:
        output = await deps.territorial_loader(codes)
    else:
        assert deps.engine is not None
        output = await comparabilidad_territorial(codes, engine=deps.engine)
    step, usages = await _record(
        deps,
        state,
        node="territorial_comparability",
        display_message="Verifiqué si los territorios consultados son comparables entre sí.",
        detail={"divipola_codes": codes, "comparable": output.get("comparable")},
        tool_output=output,
        latency_ms=round((time.perf_counter() - started) * 1000),
    )
    observations = [
        *state.get("observations", []),
        {"node": "territorial_comparability", "output": output},
    ]
    return {
        "territorial_comparability": output,
        "territorial_checked_codes": codes,
        "observations": observations,
        "steps_used": step,
        "usage": usages,
    }


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
    rejected_before = len(rejected)
    planned_evidence_ids = set(specs_by_id)
    eligible_evidence_ids: set[str] = set()
    for evidence in state.get("evidences", []):
        evidence_id = evidence["evidence_id"]
        quality = evidence.get("quality", {})
        if quality.get("eligibility_status") != "eligible":
            continue
        if quality.get("classification") == "no_recomendada":
            continue
        eligible_evidence_ids.add(evidence_id)
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
    attempts = state.get("claim_repair_attempts", 0)
    total_claims = len(state.get("claims", [])) + len(built_records)
    rejected_this_attempt = len(rejected) > rejected_before
    uncovered_evidence = bool(eligible_evidence_ids - planned_evidence_ids)
    has_eligible_evidence = any(
        evidence.get("quality", {}).get("eligibility_status") == "eligible"
        and evidence.get("quality", {}).get("classification") != "no_recomendada"
        for evidence in state.get("evidences", [])
    )
    # Hallazgo del agente evaluador (2026-07-11,
    # docs/instrucciones-evaluacion-agente-post-ajustes.md puerta 6,
    # test_valid_high_quality_evidence_cannot_silently_finish_with_zero_claims):
    # antes, si T7 rechazaba TODOS los claims propuestos (o el router
    # simplemente no proponia ninguno) para evidencia elegible, la corrida
    # pasaba derecho al sintetizador con `claims=[]` y terminaba
    # `no_evidence` sin que el router tuviera ninguna oportunidad de
    # corregirse -- pese a que la evidencia en si era buena. Se acota a
    # `MAX_CLAIM_REPAIR_ATTEMPTS` (via `claim_repair_attempts`) para que esto
    # no se convierta en un bucle: solo se reintenta si TODAVIA no se ha
    # aceptado ningun claim en toda la corrida (no solo en este paso) y
    # queda evidencia elegible sin cubrir.
    #
    # Hallazgo propio (2026-07-12, prueba
    # test_steps_used_never_exceeds_configured_max_on_every_route): el primer
    # diseno de este retry no reservaba presupuesto para la vuelta extra
    # router+claim_builder+synthesizer, y `steps_used` podia superar
    # `max_steps` (violando el invariante que el resto del grafo si respeta
    # via `_router_force_finish`/`_minimum_after_router`). Se agrega la misma
    # reserva minima aqui: sin espacio para las 3 pasos restantes, no se
    # reintenta aunque queden intentos de reparacion disponibles.
    next_step_number = state.get("steps_used", 0) + 1
    remaining_after_this_step = state.get("max_steps", deps.max_steps) - next_step_number
    retry_pending = (
        has_eligible_evidence
        and (total_claims == 0 or rejected_this_attempt or uncovered_evidence)
        and attempts < MAX_CLAIM_REPAIR_ATTEMPTS
        and remaining_after_this_step >= 3  # router + claim_builder + synthesizer
    )
    step, usages = await _record(
        deps,
        state,
        node="claim_builder",
        display_message="Construí las cifras verificables de la respuesta.",
        detail={
            "accepted": len(built_records),
            "rejected": len(rejected),
            "retry_pending": retry_pending,
        },
        tool_output={"claims": built_records, "rejected": rejected},
    )
    return {
        "claims": [*state.get("claims", []), *built_records],
        "rejected_claims": rejected,
        "claim_repair_attempts": attempts + 1 if retry_pending else attempts,
        "claim_builder_retry_pending": retry_pending,
        "steps_used": step,
        "usage": usages,
    }


async def _claim_planner_node(deps: GraphDependencies, state: AgentState) -> AgentState:
    """Planifica claims después de que el router terminó la investigación.

    La navegación y la forma matemática dejan de compartir el mismo output
    estructurado. `formula_json` mantiene el schema de Gemini no recursivo y
    se convierte a la DSL recursiva contractual solo después de validarse.
    """
    started = time.perf_counter()
    model = deps.claim_model
    if model is None:
        return {
            "terminal_error": _terminal_error(
                "INTERNAL",
                "No fue posible preparar las cifras verificables.",
                "GraphDependencies.claim_model no está configurado",
            )
        }
    usable_evidences = [
        evidence
        for evidence in state.get("evidences", [])
        if evidence.get("quality", {}).get("eligibility_status") == "eligible"
        and evidence.get("quality", {}).get("classification") != "no_recomendada"
    ]
    known_evidence_ids = {evidence["evidence_id"] for evidence in usable_evidences}
    messages = [
        SystemMessage(content=load_prompt("claim_planner")),
        HumanMessage(
            content=json.dumps(
                json_safe(
                    {
                        "question": state["question"],
                        "evidences": [
                            {**evidence, "rows": evidence.get("rows", [])[:LLM_ROWS_MAX]}
                            for evidence in usable_evidences
                        ],
                        "accepted_claims": state.get("claims", []),
                        "rejected_claims": state.get("rejected_claims", []),
                    }
                ),
                ensure_ascii=False,
            )
        ),
    ]
    usages = [*state.get("usage", [])]
    output: ClaimPlannerOutput | None = None
    unknown_ids: list[str] = []
    try:
        for attempt in range(MAX_CLAIM_EVIDENCE_ID_REPAIR_ATTEMPTS + 1):
            result = await ainvoke_structured_chat_model(model, messages, schema=ClaimPlannerOutput)
            parsed = ClaimPlannerOutput.model_validate(result.parsed)
            if result.raw_message is not None:
                usages.append(
                    asdict(
                        usage_from_message(deps.llm_provider, deps.llm_model, result.raw_message)
                    )
                )
            output = parsed
            unknown_ids = [
                item.evidence_id
                for item in parsed.claim_specs_by_evidence
                if item.evidence_id not in known_evidence_ids
            ]
            if not unknown_ids or attempt == MAX_CLAIM_EVIDENCE_ID_REPAIR_ATTEMPTS:
                break
            messages = [
                *messages,
                HumanMessage(
                    content=(
                        "Los siguientes evidence_id no corresponden a ninguna evidencia "
                        f"disponible en esta corrida: {unknown_ids}. Los evidence_id "
                        "válidos son EXACTAMENTE estos, ningún otro: "
                        f"{sorted(known_evidence_ids)}. Corrige tu respuesta usando "
                        "solo esos IDs; no inventes, combines ni modifiques ningún otro campo."
                    )
                ),
            ]
    except LLMProviderError as exc:
        step, recorded_usages = await _record(
            deps,
            {**state, "usage": usages},
            node="claim_planner",
            display_message="No fue posible preparar las cifras verificables.",
            error=str(exc),
        )
        return {
            "steps_used": step,
            "usage": recorded_usages,
            "terminal_error": _llm_terminal_error(
                exc,
                provider_message="El servicio de inteligencia artificial no está disponible.",
                structured_message="El agente no logró proponer claims con el formato esperado.",
            ),
        }
    assert output is not None
    plans: list[dict[str, Any]] = []
    rejected_unknown_evidence: list[dict[str, Any]] = []
    for item in output.claim_specs_by_evidence:
        if item.evidence_id not in known_evidence_ids:
            rejected_unknown_evidence.append(
                {
                    "evidence_id": item.evidence_id,
                    "description": "(plan de claim_planner con evidence_id inválido)",
                    "reason": (
                        f"evidence_id {item.evidence_id!r} no corresponde a ninguna "
                        "evidencia elegible de esta corrida tras "
                        f"{MAX_CLAIM_EVIDENCE_ID_REPAIR_ATTEMPTS} intento(s) de "
                        "corrección; se descarta explícitamente en vez de perderse en "
                        "silencio"
                    ),
                }
            )
            continue
        plans.append(
            {
                "evidence_id": item.evidence_id,
                "claim_specs": [spec.to_claim_payload() for spec in item.claim_specs],
            }
        )
    step, recorded_usages = await _record(
        deps,
        {**state, "usage": usages},
        node="claim_planner",
        display_message="Preparé las cifras verificables de la respuesta.",
        detail={
            "planned": sum(len(item["claim_specs"]) for item in plans),
            "evidence_ids": [item["evidence_id"] for item in plans],
            "invalid_evidence_ids": sorted(set(unknown_ids)),
            "reason": output.reasoning_summary,
        },
        latency_ms=round((time.perf_counter() - started) * 1000),
    )
    return {
        "claim_specs_by_evidence": plans,
        "rejected_claims": [*state.get("rejected_claims", []), *rejected_unknown_evidence],
        "claim_builder_retry_pending": False,
        "steps_used": step,
        "usage": recorded_usages,
    }


def _orphan_figures(
    output: SynthesisOutput,
    claims: list[dict[str, Any]],
    evidences: list[dict[str, Any]] | None = None,
) -> tuple[str, ...]:
    """Hallazgo real (2026-07-12, pilot-001-educacion-magdalena, run_ids
    eb702c23-.../919c44f6-...): dos corridas terminaron `failed` (no solo
    con el valor equivocado) porque el sintetizador escribió "2024" en el
    resumen/narrativa -- el propio año que la pregunta pide y que el
    `canonical_soql` real filtra (`WHERE a_o = 2024`), visible en el
    `evidences` que se le pasa como contexto -- y `find_orphan_figures` lo
    rechazó 3 veces por no aparecer en ningún `claim.display_value` (los
    claims solo llevan la tasa, nunca el año-filtro). Un año que aparece
    literal en la consulta SoQL ya ejecutada contra la fuente es tan
    verificado como un `claim`: Art. I exige la consulta SoQL como parte de
    la trazabilidad obligatoria, así que sus valores literales cuentan como
    respaldados.
    """
    accepted = [claim["display_value"] for claim in claims]
    accepted.extend(
        figure
        for evidence in evidences or []
        for figure in find_figures(evidence.get("soql_query") or "")
    )
    texts = [output.summary or "", output.narrative or ""]
    orphans: list[str] = []
    for text in texts:
        orphans.extend(find_orphan_figures(text, accepted))
    claims_by_evidence: dict[str, list[str]] = {}
    for claim in claims:
        claims_by_evidence.setdefault(claim["evidence_id"], []).append(claim["display_value"])
    soql_by_evidence = {
        evidence["evidence_id"]: find_figures(evidence.get("soql_query") or "")
        for evidence in evidences or []
        if evidence.get("evidence_id")
    }
    for narrative in output.evidence_narratives:
        orphans.extend(
            find_orphan_figures(
                narrative.narrative,
                [
                    *claims_by_evidence.get(narrative.evidence_id, []),
                    *soql_by_evidence.get(narrative.evidence_id, ()),
                ],
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
                    "territorial_comparability": state.get("territorial_comparability"),
                },
            )
            assert isinstance(parsed, SynthesisOutput)
            output = parsed
            if usage is not None:
                usages.append(usage)
            orphan_feedback = list(
                _orphan_figures(output, state.get("claims", []), state.get("evidences", []))
            )
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
            "terminal_error": _llm_terminal_error(
                exc,
                provider_message=(
                    "El servicio de inteligencia artificial no pudo redactar la respuesta."
                ),
                structured_message=(
                    "El agente no logró redactar la respuesta con el formato esperado, "
                    "incluso después de intentar corregirla."
                ),
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
        # Determinista, NUNCA del LLM (research.md §18): entidad/url/por_que
        # salen integros de external_sources.yaml, sobrescribiendo lo que el
        # LLM haya podido producir en este campo.
        output.no_evidence_report.external_sources = [
            ExternalSourceSuggestion(**item) for item in suggest_external_sources(state["question"])
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
        return "claim_planner" if state.get("evidences") else "synthesizer"
    return f"tool__{action}"


def _after_t5(state: AgentState) -> str:
    if state.get("terminal_error"):
        return END
    return "quality_validator" if state.get("pending_t5") else "router"


def _after_resolver_geografia(state: AgentState) -> str:
    if state.get("terminal_error"):
        return END
    codes = _resolved_territory_codes(state)
    already_checked = set(state.get("territorial_checked_codes", []))
    if len(codes) >= 2 and set(codes) != already_checked:
        return "territorial_comparability"
    return "router"


def _after_quality(state: AgentState) -> str:
    return END if state.get("terminal_error") else "router"


def _after_claim_builder(state: AgentState) -> str:
    if state.get("terminal_error"):
        return END
    return "claim_planner" if state.get("claim_builder_retry_pending") else "synthesizer"


def build_graph(deps: GraphDependencies, checkpointer: Any = None, *, interrupt: bool = True):
    """Compila el grafo real; en producción cada `ainvoke` avanza un nodo."""

    graph = StateGraph(AgentState)
    graph.add_node("planner", partial(_planner_node, deps))
    graph.add_node("router", partial(_router_node, deps))
    for tool_name in TOOL_NAMES:
        graph.add_node(f"tool__{tool_name}", _tool_node(deps, tool_name))
    graph.add_node("territorial_comparability", partial(_territorial_node, deps))
    graph.add_node("quality_validator", partial(_quality_node, deps))
    graph.add_node("claim_planner", partial(_claim_planner_node, deps))
    graph.add_node("claim_builder", partial(_claim_builder_node, deps))
    graph.add_node("synthesizer", partial(_synthesizer_node, deps))
    graph.set_entry_point("planner")
    graph.add_conditional_edges("planner", _after_planner)
    graph.add_conditional_edges("router", _after_router)
    for tool_name in TOOL_NAMES[:-1]:
        if tool_name == "resolver_geografia":
            continue
        graph.add_edge(f"tool__{tool_name}", "router")
    graph.add_conditional_edges("tool__resolver_geografia", _after_resolver_geografia)
    graph.add_edge("territorial_comparability", "router")
    graph.add_conditional_edges("tool__ejecutar_soql", _after_t5)
    graph.add_conditional_edges("quality_validator", _after_quality)
    graph.add_edge("claim_planner", "claim_builder")
    graph.add_conditional_edges("claim_builder", _after_claim_builder)
    graph.add_edge("synthesizer", END)
    return graph.compile(
        checkpointer=checkpointer,
        interrupt_after=list(GRAPH_NODES) if interrupt else None,
    )
