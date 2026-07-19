import inspect

import pytest

from app.agent.deterministic_dependencies import (
    PLANNER_THINKING_BUDGET_TOKENS,
    RuntimeLLMUsage,
    _column_type,
    _model,
    build_real_runtime_dependencies,
)
from app.agent.llm_contracts import (
    EnumeratedPlanSelection,
    GroundedSynthesis,
    IntentExtraction,
    QuantitativePlanSelection,
)
from app.agent.query_plan import ColumnDataType
from app.quality.grounded_facts import GroundedSynthesisPlan
from tests.test_settings import settings


@pytest.mark.parametrize(
    ("catalog_type", "expected"),
    [
        ("Text", ColumnDataType.TEXT),
        ("Number", ColumnDataType.NUMBER),
        ("Calendar date", ColumnDataType.DATE),
        ("Floating timestamp", ColumnDataType.DATETIME),
        ("calendar_date", ColumnDataType.DATE),
        ("Point", ColumnDataType.LOCATION),
    ],
)
def test_column_type_normalizes_real_socrata_catalog_labels(
    catalog_type: str,
    expected: ColumnDataType,
) -> None:
    assert _column_type(catalog_type) is expected


@pytest.mark.parametrize(
    ("enabled", "expected"),
    [
        (False, QuantitativePlanSelection),
        (True, EnumeratedPlanSelection),
    ],
)
def test_feature_flag_changes_the_llm_schema_itself(
    monkeypatch,
    enabled: bool,
    expected: type,
) -> None:
    schemas: list[type] = []

    def fake_model(_settings, schema, *, thinking_budget=None):
        schemas.append(schema)
        return object()

    monkeypatch.setattr("app.agent.deterministic_dependencies._model", fake_model)
    build_real_runtime_dependencies(
        settings=settings(DETERMINISTIC_TEXTUAL_FACTS_ENABLED=enabled),
        engine=object(),  # type: ignore[arg-type]
        http_client=object(),  # type: ignore[arg-type]
        embedding_client=object(),  # type: ignore[arg-type]
        usage=RuntimeLLMUsage(),
    )
    assert schemas[1] is expected


# --- T-617B0-R4: presupuesto de razonamiento acotado del planificador -------
#
# Diagnóstico causal: backend/eval/reports/t617b-d1-pilot005-timeout-diagnosis.md.
# build_plan sin thinking_budget respondió en ~1.4 s o agotó los dos intentos
# de 30 s con 504; con thinking_budget=1024 respondió en ~5.2 s pero con
# salida estructurada inválida; con thinking_budget=4096 respondió en ~2.9 s
# con salida estructurada válida.


@pytest.mark.parametrize("textual_facts_enabled", [False, True])
def test_only_planner_receives_thinking_budget_with_correct_schema(
    monkeypatch, textual_facts_enabled: bool
) -> None:
    """Requisitos 1, 2, 5 y 6: solo el planificador recibe thinking_budget
    (=PLANNER_THINKING_BUDGET_TOKENS); intent, síntesis y plan de síntesis NO
    lo reciben; cada uno de los cuatro roles conserva su schema propio; nada
    en la llamada depende de un case_id/dataset_id/pregunta (build_real_
    runtime_dependencies no recibe ninguno de esos parámetros)."""

    calls: list[dict[str, object]] = []

    def fake_model(_settings, schema, *, thinking_budget=None):
        calls.append({"schema": schema, "thinking_budget": thinking_budget})
        return object()

    monkeypatch.setattr("app.agent.deterministic_dependencies._model", fake_model)
    build_real_runtime_dependencies(
        settings=settings(DETERMINISTIC_TEXTUAL_FACTS_ENABLED=textual_facts_enabled),
        engine=object(),  # type: ignore[arg-type]
        http_client=object(),  # type: ignore[arg-type]
        embedding_client=object(),  # type: ignore[arg-type]
        usage=RuntimeLLMUsage(),
    )

    by_schema = {call["schema"]: call["thinking_budget"] for call in calls}
    planner_schema = EnumeratedPlanSelection if textual_facts_enabled else QuantitativePlanSelection

    assert by_schema[IntentExtraction] is None
    assert by_schema[planner_schema] == PLANNER_THINKING_BUDGET_TOKENS
    assert by_schema[GroundedSynthesis] is None
    if textual_facts_enabled:
        assert by_schema[GroundedSynthesisPlan] is None
    else:
        assert GroundedSynthesisPlan not in by_schema  # no se construye si el flag está apagado

    # Exactamente un rol recibió thinking_budget, sin importar el flag.
    assert sum(1 for value in by_schema.values() if value is not None) == 1


def test_model_signature_has_no_case_or_dataset_specific_parameter() -> None:
    """Requisito 6 (verificable estructuralmente): `_model` no expone ningún
    parámetro por caso/dataset/pregunta que pudiera condicionar
    thinking_budget a `pilot-005`, `h8rs-jxum` ni ningún otro identificador;
    solo `settings`, `schema` y el `thinking_budget` genérico."""

    params = set(inspect.signature(_model).parameters)
    assert params == {"settings", "schema", "thinking_budget"}


def test_planner_thinking_budget_reaches_google_model_without_changing_timeout() -> None:
    """Requisitos 1 y 4: `_model()` real (sin mocks, con clave falsa, sin red)
    para el proveedor google construye un `ChatGoogleGenerativeAI` con
    `thinking_budget=4096`, y `timeout`/`max_retries` permanecen en 30/2."""

    google_settings = settings(LLM_PROVIDER="google", GOOGLE_API_KEY="fake-google-key")
    structured = _model(
        google_settings, QuantitativePlanSelection, thinking_budget=PLANNER_THINKING_BUDGET_TOKENS
    )
    bound = structured.first.steps__["raw"].bound

    assert bound.thinking_budget == PLANNER_THINKING_BUDGET_TOKENS
    assert bound.timeout == 30
    assert bound.max_retries == 2


def test_thinking_budget_never_reaches_anthropic_model() -> None:
    """Requisito 3: incluso si se pide thinking_budget explícitamente, `_model()`
    con proveedor anthropic construye un `ChatAnthropic` que ni siquiera tiene
    el atributo `thinking_budget` (Anthropic no lo expone); `max_retries` se
    conserva en 2 sin cambios."""

    anthropic_settings = settings(LLM_PROVIDER="anthropic", ANTHROPIC_API_KEY="fake-anthropic-key")
    structured = _model(
        anthropic_settings,
        QuantitativePlanSelection,
        thinking_budget=PLANNER_THINKING_BUDGET_TOKENS,
    )
    bound = structured.first.steps__["raw"].bound

    assert not hasattr(bound, "thinking_budget")
    assert bound.max_retries == 2


def test_intent_and_synthesis_models_have_no_thinking_budget_by_default() -> None:
    """Requisito 2, a nivel de `_model()` directo (sin el kwarg opcional):
    intent y síntesis se siguen construyendo exactamente como antes de
    T-617B0-R4 -- `thinking_budget=None` por defecto no agrega nada al
    modelo de Google."""

    google_settings = settings(LLM_PROVIDER="google", GOOGLE_API_KEY="fake-google-key")
    intent_structured = _model(google_settings, IntentExtraction)
    synthesis_structured = _model(google_settings, GroundedSynthesis)

    assert intent_structured.first.steps__["raw"].bound.thinking_budget is None
    assert synthesis_structured.first.steps__["raw"].bound.thinking_budget is None


# Requisito 7 (no duplicar cobertura existente): el flujo productivo aplica
# `normalize_system_owned_operation` sobre CADA selección devuelta por
# `dependencies.plan` (el planner_model construido arriba), incondicionalmente
# y antes de cualquier otra normalización/materialización/validación --
# `app/agent/deterministic_runtime.py:463`, inmediatamente después de
# `selection = await dependencies.plan(...)` en el nodo `BUILD_PLAN`. Este
# archivo no cambia esa llamada ni su ubicación (solo agrega thinking_budget
# a la construcción del modelo, no al post-procesamiento de su salida). La
# normalización en sí ya tiene cobertura unitaria directa y suficiente en
# `tests/test_llm_contracts.py`:
# `test_count_operation_is_owned_by_system_and_always_becomes_count_star` y
# `test_lookup_preserves_metric_columns_as_enumerated_output_dimensions`;
# el punto de integración (que se invoque tras CADA `dependencies.plan` real)
# se ejercita implícitamente en cualquier prueba de
# `tests/test_deterministic_runtime.py` que alcance `BUILD_PLAN` (la llamada
# es incondicional en el nodo, no está detrás de ninguna rama que estas
# pruebas nuevas puedan afectar).
