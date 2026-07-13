"""Puerta 2 de la evaluación externa (docs/instrucciones-evaluacion-agente-
post-ajustes.md), REESCRITO 2026-07-12 tras un smoke real con Gemini (0/8
casos) que reventó en el primer paso de CADA corrida con
`ValueError: Unknown field for Schema: anyOf`.

Historia: el primer intento de esta puerta (2026-07-11) reemplazó
`RouterToolInput` -- un modelo único con todos los campos opcionales -- por
una unión discriminada de 6 modelos `extra="forbid"` (uno por acción). Las
pruebas de ese momento verificaban el schema contra
`convert_to_openai_tool(RouterOutput)` y pasaban. **Ese conversor es el de
OpenAI y nunca se usa en este proyecto**; el proveedor real configurado
(`LLM_PROVIDER=google`) usa `langchain_google_genai._function_utils`, una
ruta de código totalmente distinta que NO soporta un `anyOf` de nivel de
propiedad sin rama `null` -- revienta la construcción del `FunctionDeclaration`
antes de cualquier llamada de red, tumbando el 100% de las corridas.

Lección aplicada aquí: cualquier prueba de "schema real" debe pasar por el
conversor del proveedor REALMENTE configurado (`app.llm.factory.
get_structured_chat_model`), no por un conversor genérico que da falsa
confianza. `tool_input` volvió a ser un modelo único con todos los campos
opcionales (`Optional[X]` individuales SÍ son seguros: tienen rama `null`),
con un `model_validator` que exige los campos correctos por acción a nivel
de Python -- más débil que un schema que el proveedor respete al generar,
pero la única opción que no tumba la corrida.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agent.graph import (
    ClaimPlannerOutput,
    ClaimSpecPayload,
    FormulaNode,
    PlannerOutput,
    RouterOutput,
    SynthesisOutput,
)
from app.llm.factory import get_structured_chat_model

_VALID_TOOL_INPUT_BY_ACTION: dict[str, dict] = {
    "buscar_catalogo": {"query": "cooperación internacional", "k": 5},
    "perfilar_dataset": {"dataset_id": "abcd-1234"},
    "resolver_geografia": {"termino": "Sonsón"},
    "explorar_valores": {
        "dataset_id": "abcd-1234",
        "columna": "nombre_evento",
        "termino_busqueda": "varicela",
    },
    "ejecutar_soql": {
        "dataset_id": "abcd-1234",
        "soql": "SELECT sector, sum(monto) AS total GROUP BY sector",
        "purpose": "Recursos por sector",
    },
}


def _router_payload(action: str, tool_input: dict, **extra) -> dict:
    payload = {
        "action": action,
        "reasoning_summary": "Elijo el siguiente paso",
        "tool_input": tool_input,
    }
    payload.update(extra)
    return payload


# --- Regresión del incidente: el schema real debe construirse sin reventar -


@pytest.mark.parametrize(
    "schema",
    [
        PlannerOutput,
        RouterOutput,
        SynthesisOutput,
        ClaimSpecPayload,
        FormulaNode,
        ClaimPlannerOutput,
    ],
)
def test_structured_output_schema_builds_for_the_real_configured_provider(schema) -> None:
    """LA prueba que habría atrapado el incidente de 2026-07-12: construye
    el `FunctionDeclaration` real de Gemini (`get_structured_chat_model`, el
    mismo camino que usa `app/agent/runner.py` en producción) para cada
    schema de salida estructurada del grafo. No hace falta una API key real
    ni red -- la conversión de schema ocurre en el cliente, antes de
    cualquier llamada. Si esto pasa pero un smoke real revienta, el problema
    ya no es de schema; si esto falla, ni vale la pena intentar el smoke."""
    get_structured_chat_model(
        "google", "gemini-2.5-flash", schema, google_api_key="fake-key-solo-para-construir-schema"
    )


# --- Validación por acción (Python, no a nivel de schema del proveedor) ----


def test_each_router_action_requires_its_own_fields() -> None:
    for action, valid_input in _VALID_TOOL_INPUT_BY_ACTION.items():
        parsed = RouterOutput.model_validate(_router_payload(action, valid_input))
        assert parsed.action == action


def test_explorar_valores_requires_termino_busqueda_before_tool_execution() -> None:
    """Hallazgo T-403 en vivo (run_id=fea461c4-...): el LLM omitió
    `termino_busqueda`. Antes esto pasaba la validación del router y solo
    fallaba dentro de la herramienta (`INVALID_INPUT`); ahora es un error de
    Pydantic anterior a cualquier llamada a la herramienta."""
    incomplete = _router_payload(
        "explorar_valores", {"dataset_id": "abcd-1234", "columna": "nombre_evento"}
    )
    with pytest.raises(ValidationError, match="termino_busqueda"):
        RouterOutput.model_validate(incomplete)


@pytest.mark.parametrize("missing_field", ["dataset_id", "soql", "purpose"])
def test_ejecutar_soql_requires_dataset_soql_and_purpose(missing_field: str) -> None:
    tool_input = {**_VALID_TOOL_INPUT_BY_ACTION["ejecutar_soql"]}
    del tool_input[missing_field]
    with pytest.raises(ValidationError, match=missing_field):
        RouterOutput.model_validate(_router_payload("ejecutar_soql", tool_input))


def test_finish_does_not_require_tool_input() -> None:
    ok = RouterOutput.model_validate(_router_payload("finish", {}))
    assert ok.action == "finish"
    assert ok.tool_input.model_dump(exclude_none=True) == {}


def test_reasoning_summary_allows_900_characters() -> None:
    """Regresión real (2026-07-12, investigación offline sobre corridas
    persistidas, research.md #23): con el límite anterior de 500, al menos
    2 de 9 decisiones `finish` inconsistentes terminaban EXACTAMENTE en 500
    caracteres y a mitad de frase (`"...e incluyendo el"`) -- el texto real
    era más largo y `_truncate_overflowing_strings` lo recortaba en
    silencio, perdiendo la conclusión. 900 no elimina la inconsistencia
    genuina (la mayoría de los casos no eran truncamiento), pero cierra este
    artefacto confirmado sin ambigüedad."""
    long_reason = "x" * 900
    parsed = RouterOutput.model_validate(
        _router_payload("finish", {}, reasoning_summary=long_reason)
    )
    assert parsed.reasoning_summary == long_reason
    with pytest.raises(ValidationError):
        RouterOutput.model_validate(
            _router_payload("finish", {}, reasoning_summary="x" * 901)
        )


# --- Schema real de FormulaNode: las 4 formas deben ser visibles, no solo --
# --- la de "op" (hallazgo del 2026-07-12, ver comentario junto a          --
# --- FormulaNode en graph.py)                                             --


def test_claim_planner_exposes_formula_as_non_recursive_json_string() -> None:
    """Gemini recibe un string, mientras Python valida después la DSL T7
    recursiva completa. Así el schema real no pierde formas ni arrays.items."""
    from langchain_google_genai._function_utils import _convert_pydantic_to_genai_function

    declaration = _convert_pydantic_to_genai_function(ClaimPlannerOutput)
    formula_props = (
        declaration.parameters.properties["claim_specs_by_evidence"]
        .items.properties["claim_specs"]
        .items.properties
    )
    assert "formula_json" in formula_props


# --- Regresión general: ningun ARRAY sin `items` en ningun schema real -----


def _find_arrays_missing_items(schema, path="root") -> list[str]:
    """Recorre un `gapic.Schema` (o cualquier objeto proto con `.type_`/
    `.properties`/`.items`) buscando propiedades ARRAY sin sub-schema
    `items` -- exactamente la forma del bug real de 2026-07-12 (`args` de
    `FormulaNode` cuando era recursivo): la API de Gemini rechaza esa
    combinación con 400 en el primer paso de cada corrida, algo que
    construir el schema localmente (sin red) NO detecta por sí solo."""
    import google.ai.generativelanguage as glm

    problems: list[str] = []
    type_ = getattr(schema, "type_", None)
    if type_ == glm.Type.ARRAY:
        items = getattr(schema, "items", None)
        if items is None or getattr(items, "type_", None) in (None, 0):
            problems.append(path)
        else:
            problems.extend(_find_arrays_missing_items(items, f"{path}.items"))
    properties = getattr(schema, "properties", None)
    if properties:
        for key, value in properties.items():
            problems.extend(_find_arrays_missing_items(value, f"{path}.{key}"))
    return problems


@pytest.mark.parametrize(
    "schema",
    [
        PlannerOutput,
        RouterOutput,
        SynthesisOutput,
        ClaimSpecPayload,
        FormulaNode,
        ClaimPlannerOutput,
    ],
)
def test_no_array_property_is_missing_items_in_the_real_schema(schema) -> None:
    from langchain_google_genai._function_utils import _convert_pydantic_to_genai_function

    declaration = _convert_pydantic_to_genai_function(schema)
    problems = _find_arrays_missing_items(declaration.parameters, path=schema.__name__)
    assert problems == [], f"propiedades ARRAY sin 'items' (Gemini las rechaza con 400): {problems}"
