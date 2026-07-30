"""Runtime del agente v2 gobernado por el supervisor determinista.

El runtime coordina I/O mediante dependencias inyectadas; las decisiones de
transición siguen siendo exclusivas de ``decide_next_transition``.
"""

from __future__ import annotations

import re
import time
import unicodedata
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.agent.deterministic_graph import (
    CandidateProgress,
    CandidateStatus,
    StopReason,
    SupervisorBudgets,
    SupervisorNode,
    SupervisorSnapshot,
    SupervisorUsage,
    decide_next_transition,
)
from app.agent.deterministic_pipeline import (
    DeterministicExecutionError,
    DeterministicExecutionResult,
    DeterministicPersistenceCancelled,
)
from app.agent.llm_contracts import (
    EnumeratedPlanSelection,
    FilterChoice,
    GroundedSynthesis,
    IntentExtraction,
    ground_intent_topic_in_question,
    materialize_query_plan,
    normalize_aggregate_intent,
    normalize_budget_snapshot,
    normalize_direct_quantity_lookup,
    normalize_explicit_date_filter,
    normalize_extremum_sort_target,
    normalize_intent_for_observed_schema,
    normalize_lookup_filters,
    normalize_lookup_output_columns,
    normalize_lookup_total_column,
    normalize_ranked_aggregate,
    normalize_sort_references,
    normalize_source_observation_cutoff_filters,
    normalize_system_owned_operation,
    normalize_temporal_year_filters,
    validate_grounded_synthesis,
)
from app.agent.multiquery_retrieval import MultiQueryRetrievalResult
from app.agent.plan_validator import (
    ObservedDatasetSchema,
    PlanValidationCode,
    PlanValidationError,
    ValidatedQueryPlan,
    validate_query_plan,
    validate_requested_output_semantics,
)
from app.agent.query_plan import (
    DatasetOption,
    EnumeratedPlanningContext,
    FilterOperator,
    QueryOperation,
    ScalarType,
)
from app.llm.factory import LLMProviderError
from app.quality.claim_labels import (
    claim_is_relevant_to_narrative,
    fallback_dataset_topically_relevant,
    intent_relevance_tokens,
)
from app.quality.claims import BuiltClaim, ClaimsBuildResult
from app.quality.grounded_facts import GroundedSynthesisPlan
from app.quality.grounded_synthesis import AllowedGroundedFacts


class SynthesisIntegrityError(ValueError):
    """La síntesis sigue violando RNF-003 después del fallback seguro."""


class DeterministicToolInfrastructureError(RuntimeError):
    """Fallo definitivo y tipado de una herramienta externa del runtime."""

    def __init__(self, code: str, message: str) -> None:
        if code not in {"SOCRATA_TIMEOUT", "SOCRATA_ERROR"}:
            raise ValueError(f"código de infraestructura no soportado: {code}")
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class ProfiledCandidate:
    option: DatasetOption
    schema: ObservedDatasetSchema

    @property
    def context(self) -> EnumeratedPlanningContext:
        return EnumeratedPlanningContext(candidates=(self.option,))


@dataclass(frozen=True)
class ExploredColumnValues:
    column_index: int
    search_term: str
    values: tuple[str, ...]
    tool_calls: int = 1


@dataclass(frozen=True)
class RuntimeTraceEntry:
    node: SupervisorNode
    reason: str
    candidate_index: int | None
    diagnostic_code: str | None = None


@dataclass(frozen=True)
class DeterministicRuntimeResult:
    status: str
    stop_reason: StopReason | None
    intent: IntentExtraction
    retrieval: MultiQueryRetrievalResult
    execution: DeterministicExecutionResult | None
    synthesis: GroundedSynthesis | None
    trace: tuple[RuntimeTraceEntry, ...]
    usage: SupervisorUsage


class DeterministicRunCancelled(RuntimeError):
    pass


IntentExtractor = Callable[[str], Awaitable[IntentExtraction]]
Retriever = Callable[[IntentExtraction], Awaitable[MultiQueryRetrievalResult]]
Profiler = Callable[[str], Awaitable[ProfiledCandidate]]
Planner = Callable[
    [
        IntentExtraction,
        EnumeratedPlanningContext,
        tuple[ExploredColumnValues, ...],
        PlanValidationError | None,
    ],
    Awaitable[EnumeratedPlanSelection],
]
Explorer = Callable[
    [
        ProfiledCandidate,
        EnumeratedPlanSelection,
        tuple[ExploredColumnValues, ...],
        int,
    ],
    Awaitable[ExploredColumnValues],
]
Executor = Callable[[ValidatedQueryPlan], Awaitable[DeterministicExecutionResult]]
Synthesizer = Callable[[IntentExtraction, ClaimsBuildResult], Awaitable[GroundedSynthesis]]
SynthesisPlanner = Callable[
    [IntentExtraction, AllowedGroundedFacts],
    Awaitable[GroundedSynthesisPlan],
]
TransitionObserver = Callable[[RuntimeTraceEntry, SupervisorUsage], Awaitable[None]]


@dataclass(frozen=True)
class DeterministicRuntimeDependencies:
    extract_intent: IntentExtractor
    retrieve: Retriever
    profile: Profiler
    plan: Planner
    explore: Explorer
    execute: Executor
    synthesize: Synthesizer
    plan_synthesis: SynthesisPlanner | None = None


def _replace_status(
    candidates: list[CandidateProgress],
    index: int,
    status: CandidateStatus,
    *,
    reason: str | None = None,
) -> None:
    candidates[index] = CandidateProgress(
        dataset_index=index, status=status, rejection_reason=reason
    )


def _text_filter_indexes(selection: EnumeratedPlanSelection) -> tuple[int, ...]:
    return tuple(
        dict.fromkeys(
            item.column_index
            for item in selection.filters
            if item.value_type is ScalarType.TEXT
            and item.operator in {FilterOperator.EQ, FilterOperator.IN}
            and item.values
        )
    )


def _requires_exploration(
    selection: EnumeratedPlanSelection | None,
    explored: tuple[ExploredColumnValues, ...],
) -> bool:
    if selection is None:
        return False
    explored_indexes = {item.column_index for item in explored}
    return any(index not in explored_indexes for index in _text_filter_indexes(selection))


def _validate_explored_filters(
    selection: EnumeratedPlanSelection,
    explored: tuple[ExploredColumnValues, ...],
) -> None:
    """Valida solo filtros categóricos EQ/IN que RF-205 manda observar.

    Comparaciones textuales como NE no usan el diccionario categórico y no
    deben consumir reparaciones ni bloquear una consulta verificable.
    """

    allowed = {item.column_index: {_fold_text(value) for value in item.values} for item in explored}
    for item in selection.filters:
        if (
            item.value_type is not ScalarType.TEXT
            or item.operator not in {FilterOperator.EQ, FilterOperator.IN}
            or not item.values
        ):
            continue
        values = allowed.get(item.column_index)
        if values is None:
            raise ValueError(f"column_index {item.column_index} requiere exploración")
        invalid = [value for value in item.values if _fold_text(value) not in values]
        if invalid:
            raise ValueError(
                f"valores no observados para column_index {item.column_index}: {invalid}"
            )


def _normalize_explored_filter_values(
    selection: EnumeratedPlanSelection,
    explored: tuple[ExploredColumnValues, ...],
) -> EnumeratedPlanSelection:
    allowed = {item.column_index: item.values for item in explored}
    normalized = []
    for item in selection.filters:
        values = allowed.get(item.column_index)
        if item.value_type is not ScalarType.TEXT or not values:
            normalized.append(item)
            continue
        canonical = {
            _fold_text(value): next(
                observed for observed in values if _fold_text(observed) == _fold_text(value)
            )
            for value in item.values
            if any(_fold_text(observed) == _fold_text(value) for observed in values)
        }
        normalized.append(
            item.model_copy(
                update={
                    "values": tuple(
                        canonical.get(_fold_text(value), value) for value in item.values
                    )
                }
            )
        )
    normalized_indexes = {item.column_index for item in normalized}
    normalized.extend(
        FilterChoice(
            column_index=item.column_index,
            operator=FilterOperator.EQ,
            value_type=ScalarType.TEXT,
            values=(item.values[0],),
        )
        for item in explored
        if item.values and item.column_index not in normalized_indexes
    )
    return selection.model_copy(update={"filters": tuple(normalized)})


def _fold_text(value: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(character)
    )


def _entity_confirmed_in_dataset(
    intent_entity: str | None,
    explored: tuple[ExploredColumnValues, ...],
) -> bool:
    """T-617B-C13-D11 (golden-v2, pilot-042-disposicion-final): la compuerta
    de tema de repliegue (`fallback_dataset_topically_relevant`) compara el
    título del dataset contra los tokens de la pregunta completa
    (`ground_intent_topic_in_question`) -- para un LOOKUP anclado en una
    entidad nombrada larga y específica ("SOCIEDAD DE ACUEDUCTO,
    ALCANTARILLADO Y ASEO DE BARRANQUILLA S.A. E.S.P."), esos tokens quedan
    dominados por el nombre propio, que casi nunca aparece en el título
    genérico de NINGÚN dataset, correcto o no. `84tn-nnhf` ("Superservicios
    - Registro de Sitios de Disposición Final") es el dataset correcto —
    `explore_value` ya confirmó la entidad exacta en `nombre_empresa` — pero
    la compuerta de tema lo rechazaba igual.

    Contraejemplo real verificado antes de este cambio (golden-v2,
    pilot-027-paridad-etnica, candidato de repliegue `ji8i-4anb`,
    "deserción escolar"): su exploración también tuvo éxito, pero el valor
    encontrado fue "Antioquia" -- un nombre departamental genérico que
    aparece en casi cualquier dataset territorial colombiano, sin ninguna
    relación con el tema real de la pregunta. Por eso esta señal exige
    coincidencia EXACTA con `intent.entity` (el término institucional ya
    anclado por `_grounded_institutional_term`, que solo se fija para
    términos de al menos dos tokens con cabeza institucional -- "Antioquia"
    nunca calificaría) en vez de aceptar cualquier exploración categórica
    exitosa, que sí habría reabierto ese defecto original."""

    if not intent_entity:
        return False
    folded_entity = _fold_text(intent_entity)
    return any(_fold_text(value) == folded_entity for item in explored for value in item.values)


def _render_claim_clause(claim: BuiltClaim) -> str:
    """Redacta una cláusula etiquetada sin inventar la etiqueta ausente
    (RF-212). `label_status="ambiguous"` se señala explícitamente en vez de
    enumerar la cifra sin contexto."""

    unit_suffix = f" {claim.unit}" if claim.unit else ""
    if claim.label_status == "verified" and claim.label:
        return f"{claim.label}: {claim.display_value}{unit_suffix}"
    return f"{claim.display_value}{unit_suffix} (sin etiqueta verificable)"


def _deterministic_synthesis(
    claims: ClaimsBuildResult, intent: IntentExtraction
) -> GroundedSynthesis:
    """Fallback determinista (sin LLM) con las mismas garantías de
    etiquetado y relevancia que la ruta normal (RF-212): prioriza claims
    relevantes para la intención, excluye auxiliares/temporales no
    solicitados y nunca enumera cifras sin significado."""

    requested_tokens = intent_relevance_tokens(intent.topic, intent.administrative_terms)
    indexed = list(enumerate(claims.claims))
    relevant = [
        (index, claim)
        for index, claim in indexed
        if claim_is_relevant_to_narrative(claim.public_columns, requested_tokens=requested_tokens)
    ]
    pool = relevant if relevant else indexed
    selected = pool[:8]
    values = "; ".join(_render_claim_clause(claim) for _index, claim in selected)
    suffix = (
        " Hay resultados adicionales en la evidencia adjunta." if len(claims.claims) > 8 else ""
    )
    return GroundedSynthesis(
        answer=f"Resultados calculados con la evidencia consultada: {values}.{suffix}",
        cited_claim_indexes=tuple(index for index, _claim in selected),
    )


def _unsupported_question(question: str) -> bool:
    normalized = _fold_text(question)
    exact_prediction = re.search(
        r"\b(exactamente|pronostico|predecir|futuro|abandonaran|caera)\b",
        normalized,
    )
    real_time = re.search(
        r"\b(proximos?\s+\w+\s+minutos?|tiempo real|llegara primero)\b",
        normalized,
    )
    personal_rows = "cada servidor" in normalized and all(
        term in normalized for term in ("nombre", "edad", "salario")
    )
    medical_advice = "tratamiento medico" in normalized and (
        "debe recibir" in normalized or "diagnostico" in normalized
    )
    strong_causal_attribution = _requests_strong_causal_attribution(normalized)
    social_media_sentiment_analysis = _requests_social_media_sentiment_analysis(normalized)
    sub_municipal_causal_attribution = _requests_causal_attribution_below_catalog_granularity(
        normalized
    )
    return bool(
        exact_prediction
        or real_time
        or personal_rows
        or medical_advice
        or strong_causal_attribution
        or social_media_sentiment_analysis
        or sub_municipal_causal_attribution
    )


def _requests_strong_causal_attribution(normalized: str) -> bool:
    """Detecta preguntas que exigen atribución causal fuerte o exclusiva —
    una capacidad analítica que un catálogo estructurado descriptivo no
    puede demostrar sin un diseño causal (RF-205/T-617B-C3). Genérico por
    capacidad, no por tema: nunca se ancla a un dataset, `case_id` ni al
    texto completo de una pregunta concreta.

    No basta con que aparezcan "causa", "efecto" o "relación" sueltos —
    exige un verbo causal explícito combinado con una marca de exclusividad
    en la misma cláusula (p. ej. "causó ... por sí sola"), o una expresión
    de atribución única/exclusiva por sí misma (p. ej. "única causa",
    "responsable exclusivo de", "fue la única causa"). Una asociación,
    comparación o correlación descriptiva sin esa exclusividad explícita no
    activa esta regla.
    """

    causal_verb_with_exclusivity = re.search(
        r"\b(causo|causaron|provoco|provocaron|origino|originaron)\b"
        r"[^.?!]{0,40}\bpor si (sola|solo)\b"
        r"|\bpor si (sola|solo)\b[^.?!]{0,40}"
        r"\b(causo|causaron|provoco|provocaron|origino|originaron)\b",
        normalized,
    )
    exclusive_attribution_phrase = re.search(
        r"\b(unic[oa]|exclusiv[oa])\s+(causa|responsable|factor|explicacion)\b"
        r"|\bresponsable\s+(unic[oa]|exclusiv[oa])(\s+de)?\b"
        r"|\bcausa\s+(exclusiva|unica|determinante)\b"
        r"|\bfue\s+la\s+unica\s+causa\b"
        r"|\batribu(ible|ye|yo)\s+(unicamente|exclusivamente)\b",
        normalized,
    )
    return bool(causal_verb_with_exclusivity or exclusive_attribution_phrase)


def _requests_causal_attribution_below_catalog_granularity(normalized: str) -> bool:
    """Detecta atribución causal a nivel de granularidad territorial que el
    catálogo estructurado no publica (RF-205, pilot-010-negativo-causalidad-
    barrial): datasets oficiales colombianos en este catálogo se agregan a
    lo sumo a nivel de municipio/departamento -- nunca a barrio, vereda o
    manzana. Una pregunta causal ("¿en qué barrio X fue causado por Y?") a
    esa escala no puede demostrarse con evidencia correlacional agregada,
    con independencia de si usa lenguaje de exclusividad explícita (que ya
    cubre `_requests_strong_causal_attribution`). Genérico por capacidad
    territorial, no por tema ni pregunta literal: exige un verbo causal
    (sin requerir exclusividad) combinado con un término de granularidad
    sub-municipal en la misma pregunta.
    """

    causal_verb = re.search(
        r"\b(causo|causada|causaron|causadas|provoco|provocada|provocaron|provocadas"
        r"|origino|originada|originaron|originadas)\b",
        normalized,
    )
    sub_municipal_granularity = re.search(r"\b(barrio|vereda|manzana|cuadra)s?\b", normalized)
    return bool(causal_verb and sub_municipal_granularity)


def _requests_social_media_sentiment_analysis(normalized: str) -> bool:
    """Detecta preguntas de polarización, sentimiento, opinión o análisis
    discursivo de ciudadanía ligadas explícitamente a redes sociales,
    publicaciones o comentarios digitales — capacidad de NLP/análisis de
    discurso no estructurado que el catálogo estructurado no incorpora
    (RF-205/T-617B-C3). Genérico por capacidad: exige la combinación de un
    término de análisis de opinión/sentimiento CON un término de medio
    digital/redes en la misma cláusula; ninguno de los dos por separado
    activa la regla. "red vial" u otras redes de infraestructura no son
    redes sociales, y "social" fuera de ese contexto (p. ej. "gasto
    social") tampoco.
    """

    social_media_terms = (
        r"(redes sociales|publicaciones digitales|publicaciones en redes"
        r"|comentarios digitales|comentarios en redes|discurso digital"
        r"|debate digital)"
    )
    sentiment_terms = r"(polarizacion|polarizada|polarizado|sentimiento|opinion|postura|percepcion)"
    return bool(
        re.search(
            rf"\b{sentiment_terms}\b[^.?!]{{0,60}}\b{social_media_terms}\b"
            rf"|\b{social_media_terms}\b[^.?!]{{0,60}}\b{sentiment_terms}\b",
            normalized,
        )
    )


async def run_deterministic_agent(
    question: str,
    *,
    dependencies: DeterministicRuntimeDependencies,
    budgets: SupervisorBudgets | None = None,
    is_cancelled: Callable[[], bool] | None = None,
    observe_transition: TransitionObserver | None = None,
    defer_synthesis_until_persisted: bool = False,
) -> DeterministicRuntimeResult:
    """Ejecuta el ciclo completo sin permitir que el LLM elija transiciones."""

    limits = budgets or SupervisorBudgets()
    started = time.monotonic()
    if _unsupported_question(question):
        intent = IntentExtraction(topic=question, operation=QueryOperation.LOOKUP)
        retrieval = MultiQueryRetrievalResult(queries=(), candidates=())
        trace_entry = RuntimeTraceEntry(
            SupervisorNode.ABSTAIN,
            "solicitud fuera del alcance verificable",
            None,
        )
        usage = SupervisorUsage()
        if observe_transition is not None:
            await observe_transition(trace_entry, usage)
        return DeterministicRuntimeResult(
            "abstained",
            StopReason.NO_CANDIDATES,
            intent,
            retrieval,
            None,
            None,
            (trace_entry,),
            usage,
        )
    intent = await dependencies.extract_intent(question)
    intent = ground_intent_topic_in_question(intent, question)
    intent = normalize_aggregate_intent(intent, question)
    llm_calls = 1
    retrieval = await dependencies.retrieve(intent)
    candidates = [
        CandidateProgress(dataset_index=index)
        for index, _candidate in enumerate(retrieval.candidates[: limits.max_candidates])
    ]
    current: int | None = None
    profile: ProfiledCandidate | None = None
    selection: EnumeratedPlanSelection | None = None
    validated: ValidatedQueryPlan | None = None
    execution: DeterministicExecutionResult | None = None
    synthesis: GroundedSynthesis | None = None
    validation_error: PlanValidationError | None = None
    explored: tuple[ExploredColumnValues, ...] = ()
    explorations = queries = repairs = 0
    trace: list[RuntimeTraceEntry] = []
    #: T-617B-C13-D6: razón de rechazo del último candidato descartado,
    #: expuesta en el `diagnostic_code` del siguiente `select_candidate`
    #: (se consume una sola vez) para que el evento persistido conserve la
    #: causa exacta -- antes se perdía en cuanto `current` volvía a `None`.
    pending_rejection_reason: str | None = None

    while True:
        if is_cancelled is not None and is_cancelled():
            raise DeterministicRunCancelled("corrida cancelada")
        elapsed_ms = round((time.monotonic() - started) * 1000)
        # T-617B-C2 (RF-205/RF-211): evidencia elegible por calidad puede
        # seguir siendo ajena a la intención de la pregunta. Reutiliza la
        # misma señal estructurada ya aprobada en T-617C (RF-212) que
        # clasifica cada columna fuente de un claim frente a los tokens de
        # la intención — sin heurísticas nuevas, sin `case_id`/`dataset_id`,
        # sin juicio de LLM.
        claims_materially_relevant = True
        textual_result_available = execution is not None and bool(
            getattr(execution, "textual_facts", ())
        )
        if execution is not None:
            requested_tokens = intent_relevance_tokens(intent.topic, intent.administrative_terms)
            if execution.claims.claims:
                claims_materially_relevant = any(
                    claim_is_relevant_to_narrative(
                        getattr(claim, "public_columns", ()), requested_tokens=requested_tokens
                    )
                    for claim in execution.claims.claims
                )
            # T-617B-C13 (RF-205/RF-211): un nombre de columna ("cantidad",
            # "capacidad") casi nunca repite el tema de la pregunta incluso
            # en el candidato correcto -- exigir solapamiento léxico ahí
            # rompería casos legítimos ya aprobados (rank 1). Pero cuando el
            # candidato ACEPTADO no es el mejor rankeado (`current > 0`, ya
            # se agotaron/rechazaron candidatos anteriores), es exactamente
            # el patrón real observado en `pilot-026`/`pilot-027`: repliegue
            # a un dataset de tema no relacionado (`ji8i-4anb`, "deserción
            # escolar") cuyas columnas son léxicamente "primarias" y por eso
            # pasaban el chequeo anterior sin verificar el dataset en sí.
            #
            # T-617B-C13-D9 (golden-v2, pilot-018-transporte-ferreo):
            # `textual_result_available` se calculaba sin este chequeo, así
            # que un candidato de repliegue con claims correctamente
            # descartados (`claims_materially_relevant=False`, columnas
            # `anno_vigencia`/`mes_vigencia`) igual completaba la síntesis
            # con un HECHO TEXTUAL de un dataset sin relación temática
            # (`5r3g-zv5z`, "Tráfico Portuario Marítimo") citando valores de
            # `tipo_carga` ("GRANEL LÍQUIDO", "CONTENEDORES"...) para una
            # pregunta de concesiones ferroviarias: `decide_next_transition`
            # avanza a PERSIST_FACTS con `claims_materially_relevant OR
            # textual_result_available`, y el segundo nunca se apagaba. Se
            # aplica la misma señal a ambos: un candidato de repliegue sin
            # relación temática no aporta evidencia suficiente por ninguna
            # de las dos vías.
            evidence_draft = getattr(execution, "evidence_draft", None)
            dataset_name = getattr(evidence_draft, "dataset_name", None)
            if not fallback_dataset_topically_relevant(
                dataset_name,
                requested_tokens=requested_tokens,
                accepted_candidate_index=current,
            ) and not _entity_confirmed_in_dataset(intent.entity, explored):
                claims_materially_relevant = False
                textual_result_available = False
            # T-617B-C13-D10 (golden-v2, pilot-042-disposicion-final):
            # segunda validación, redundante por diseño, justo antes de
            # persistir/sintetizar -- `validate_requested_output_semantics`
            # ya se exigió en BUILD_PLAN sobre el mismo `validated`, pero se
            # reafirma aquí para que ningún cambio futuro entre la
            # validación del plan y la persistencia pueda dejar pasar
            # evidencia que no responde al sistema de código nombrado sin
            # que este chequeo lo note.
            if validated is not None:
                try:
                    validate_requested_output_semantics(
                        validated, context=profile.context, question=question
                    )
                except PlanValidationError:
                    claims_materially_relevant = False
                    textual_result_available = False
        snapshot = SupervisorSnapshot(
            candidates=tuple(candidates),
            current_candidate_index=current,
            schema_available=profile is not None,
            plan_available=selection is not None,
            plan_valid=validated is not None,
            plan_error_correctable=validation_error is not None,
            exploration_required=_requires_exploration(selection, explored),
            query_executed=execution is not None,
            evidence_eligible=(
                execution is not None and execution.quality.eligibility_status == "eligible"
            ),
            claims_available=execution is not None and bool(execution.claims.claims),
            claims_materially_relevant=claims_materially_relevant,
            # T-617B-C2 (corrección R3): `textual_result_available` señala
            # exclusivamente hechos textuales ACEPTADOS. Un rechazo no es un
            # resultado disponible para persistir — mezclarlos permitía que
            # un rechazo textual puro disfrazara de "hecho pertinente" la
            # persistencia de un claim cuantitativo irrelevante. `textual_
            # rejected` (abajo) es la señal independiente para rechazos.
            textual_result_available=textual_result_available,
            textual_rejected=execution is not None
            and bool(getattr(execution, "textual_rejections", ())),
            synthesis_deferred=defer_synthesis_until_persisted,
            synthesis_valid=synthesis is not None,
            budgets=limits,
            usage=SupervisorUsage(
                candidates=sum(item.status is not CandidateStatus.UNSEEN for item in candidates),
                explorations=explorations,
                queries=queries,
                plan_repairs=repairs,
                llm_calls=llm_calls,
                elapsed_ms=elapsed_ms,
            ),
        )
        transition = decide_next_transition(snapshot)
        trace_reason = transition.reason
        if transition.node is SupervisorNode.BUILD_PLAN and validation_error is not None:
            trace_reason = f"{trace_reason}: {validation_error.code.value}: {validation_error}"
        diagnostic_code = (
            validation_error.code.value
            if transition.node is SupervisorNode.BUILD_PLAN and validation_error is not None
            else None
        )
        if transition.node is SupervisorNode.SELECT_CANDIDATE and pending_rejection_reason:
            diagnostic_code = pending_rejection_reason
            pending_rejection_reason = None
        textual_rejections = (
            getattr(execution, "textual_rejections", ()) if execution is not None else ()
        )
        if transition.node is SupervisorNode.ABSTAIN and textual_rejections:
            diagnostic_code = textual_rejections[0].code
        trace_entry = RuntimeTraceEntry(transition.node, trace_reason, current, diagnostic_code)
        trace.append(trace_entry)
        if observe_transition is not None:
            await observe_transition(trace_entry, snapshot.usage)

        if transition.node is SupervisorNode.COMPLETE:
            return DeterministicRuntimeResult(
                "completed",
                None,
                intent,
                retrieval,
                execution,
                synthesis,
                tuple(trace),
                snapshot.usage,
            )
        if transition.node is SupervisorNode.PERSIST_FACTS:
            assert execution is not None
            assert current is not None
            _replace_status(candidates, current, CandidateStatus.ACCEPTED)
            return DeterministicRuntimeResult(
                "ready_for_synthesis",
                None,
                intent,
                retrieval,
                execution,
                None,
                tuple(trace),
                snapshot.usage,
            )
        if transition.node is SupervisorNode.ABSTAIN:
            return DeterministicRuntimeResult(
                "abstained",
                transition.stop_reason,
                intent,
                retrieval,
                execution,
                None,
                tuple(trace),
                snapshot.usage,
            )
        if transition.node is SupervisorNode.RETRIEVE_CANDIDATES:
            return DeterministicRuntimeResult(
                "abstained",
                StopReason.NO_CANDIDATES,
                intent,
                retrieval,
                None,
                None,
                tuple(trace),
                snapshot.usage,
            )
        if transition.node is SupervisorNode.SELECT_CANDIDATE:
            current = next(
                index
                for index, candidate in enumerate(candidates)
                if candidate.status is CandidateStatus.UNSEEN
            )
            _replace_status(candidates, current, CandidateStatus.SELECTED)
            repairs = 0
            continue
        if transition.node is SupervisorNode.PROFILE_DATASET:
            assert current is not None
            dataset_id = retrieval.candidates[current].item.dataset_id
            try:
                profile = await dependencies.profile(dataset_id)
            except DeterministicToolInfrastructureError:
                raise
            except (LookupError, ValueError):
                # Un esquema no perfilable (sin columnas observadas, o un
                # esquema ancho que excede MAX_COLUMNS_PER_CANDIDATE) es un
                # rechazo controlado de ESTE candidato, no un fallo terminal
                # de la corrida: el supervisor debe intentar el siguiente
                # candidato en vez de propagar la excepción sin clasificar
                # (que el arnés de evaluación termina registrando como un
                # `INTERNAL` opaco).
                _replace_status(
                    candidates, current, CandidateStatus.REJECTED, reason="PROFILING_ERROR"
                )
                pending_rejection_reason = "PROFILING_ERROR"
                current = None
                profile = selection = validated = execution = None
                explored = ()
                validation_error = None
                repairs = 0
                continue
            intent = normalize_intent_for_observed_schema(
                intent,
                question=question,
                context=profile.context,
            )
            _replace_status(candidates, current, CandidateStatus.PROFILED)
            continue
        if transition.node is SupervisorNode.BUILD_PLAN:
            assert profile is not None
            selection = await dependencies.plan(
                intent,
                profile.context,
                explored,
                validation_error,
            )
            llm_calls += 1
            selection = normalize_system_owned_operation(selection, intent)
            selection = normalize_direct_quantity_lookup(
                selection,
                question=question,
                context=profile.context,
            )
            selection = normalize_budget_snapshot(
                selection,
                question=question,
                context=profile.context,
            )
            selection = normalize_lookup_total_column(
                selection,
                question=question,
                context=profile.context,
            )
            selection = normalize_lookup_filters(
                selection,
                question=question,
                context=profile.context,
            )
            selection = normalize_explicit_date_filter(
                selection,
                question=question,
                context=profile.context,
            )
            selection = normalize_source_observation_cutoff_filters(
                selection,
                question=question,
                context=profile.context,
            )
            selection = normalize_lookup_output_columns(
                selection,
                question=question,
                context=profile.context,
            )
            selection = normalize_ranked_aggregate(
                selection,
                question=question,
                context=profile.context,
            )
            selection = normalize_sort_references(selection, profile.context)
            selection = normalize_extremum_sort_target(
                selection,
                question=question,
                context=profile.context,
            )
            selection = normalize_temporal_year_filters(selection, profile.context)
            selection = _normalize_explored_filter_values(selection, explored)
            if _requires_exploration(selection, explored):
                validated = None
                validation_error = None
                continue
            try:
                _validate_explored_filters(selection, explored)
                plan = materialize_query_plan(selection, intent=intent, context=profile.context)
                validated = validate_query_plan(
                    plan,
                    context=profile.context,
                    schema=profile.schema,
                )
                validate_requested_output_semantics(
                    validated,
                    context=profile.context,
                    question=question,
                )
                validation_error = None
                assert current is not None
                _replace_status(candidates, current, CandidateStatus.PLANNED)
            except PlanValidationError as exc:
                if exc.code in {
                    PlanValidationCode.DATASET_MISMATCH,
                    PlanValidationCode.DATASET_NOT_ELIGIBLE,
                    PlanValidationCode.PII_BLOCKED,
                    PlanValidationCode.PII_REQUIRES_AGGREGATION,
                    PlanValidationCode.REQUESTED_OUTPUT_SEMANTICS_MISMATCH,
                }:
                    assert current is not None
                    _replace_status(
                        candidates, current, CandidateStatus.REJECTED, reason=exc.code.value
                    )
                    pending_rejection_reason = exc.code.value
                    current = None
                    profile = selection = validated = execution = None
                    explored = ()
                    validation_error = None
                    repairs = 0
                    continue
                validation_error = exc
                validated = None
                repairs += 1
            except ValueError as exc:
                validation_error = PlanValidationError(
                    PlanValidationCode.UNKNOWN_REFERENCE,
                    str(exc),
                )
                validated = None
                repairs += 1
            continue
        if transition.node is SupervisorNode.EXPLORE_VALUE:
            assert profile is not None
            assert selection is not None
            # RNF-002: el límite es por llamada T4 real, no por transición.
            # El adaptador recibe únicamente el saldo para que una búsqueda
            # con varias variantes nunca pueda rebasar el presupuesto.
            remaining_explorations = limits.max_explorations - explorations
            try:
                item = await dependencies.explore(
                    profile,
                    selection,
                    explored,
                    remaining_explorations,
                )
            except DeterministicToolInfrastructureError:
                raise
            except (LookupError, ValueError):
                assert current is not None
                _replace_status(
                    candidates, current, CandidateStatus.REJECTED, reason="EXPLORATION_ERROR"
                )
                pending_rejection_reason = "EXPLORATION_ERROR"
                current = None
                profile = selection = validated = execution = None
                explored = ()
                validation_error = None
                repairs = 0
                continue
            explored = tuple(
                previous for previous in explored if previous.column_index != item.column_index
            ) + (item,)
            explorations += item.tool_calls
            if not item.values:
                assert current is not None
                _replace_status(
                    candidates,
                    current,
                    CandidateStatus.REJECTED,
                    reason="EXPLORATION_NO_VALUES",
                )
                pending_rejection_reason = "EXPLORATION_NO_VALUES"
                current = None
                profile = selection = validated = execution = None
                explored = ()
                validation_error = None
                continue
            selection = None
            validation_error = None
            continue
        if transition.node is SupervisorNode.EXECUTE_QUERY:
            assert validated is not None
            try:
                execution = await dependencies.execute(validated)
                queries += 1
                assert current is not None
                _replace_status(candidates, current, CandidateStatus.QUERIED)
            except DeterministicPersistenceCancelled as exc:
                raise DeterministicRunCancelled(str(exc)) from exc
            except DeterministicExecutionError as exc:
                queries += 1
                assert current is not None
                execution_error_code = str(exc).split(":", 1)[0].strip()
                _replace_status(
                    candidates,
                    current,
                    CandidateStatus.REJECTED,
                    reason=execution_error_code,
                )
                pending_rejection_reason = execution_error_code
                current = None
                profile = selection = validated = execution = None
                explored = ()
            continue
        if transition.node is SupervisorNode.DERIVE_CLAIMS:
            raise AssertionError("execute ya deriva claims de forma determinista")
        if transition.node is SupervisorNode.SYNTHESIZE:
            assert execution is not None
            if llm_calls >= limits.max_llm_calls:
                synthesis = _deterministic_synthesis(execution.claims, intent)
            else:
                try:
                    synthesis = await dependencies.synthesize(intent, execution.claims)
                    llm_calls += 1
                except LLMProviderError:
                    llm_calls += 1
                    synthesis = _deterministic_synthesis(execution.claims, intent)
            try:
                validate_grounded_synthesis(synthesis, execution.claims.claims)
            except ValueError:
                synthesis = _deterministic_synthesis(execution.claims, intent)
                try:
                    validate_grounded_synthesis(synthesis, execution.claims.claims)
                except ValueError as exc:
                    raise SynthesisIntegrityError(str(exc)) from exc
            assert current is not None
            _replace_status(candidates, current, CandidateStatus.ACCEPTED)
            continue
        if transition.node is SupervisorNode.NEXT_CANDIDATE:
            assert current is not None
            next_candidate_reason = (
                transition.stop_reason.value
                if transition.stop_reason is not None
                else transition.reason
            )
            _replace_status(
                candidates, current, CandidateStatus.REJECTED, reason=next_candidate_reason
            )
            pending_rejection_reason = next_candidate_reason
            current = None
            profile = selection = validated = execution = None
            explored = ()
            validation_error = None
            continue
        raise AssertionError(f"transición sin implementación: {transition.node}")
