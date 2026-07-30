/**
 * Reducer puro del estado cliente de una corrida (`docs/frontend-v2/…`
 * §4.5, `frontend/AGENTS.md`: "el reducer debe ser puro, exhaustivo e
 * idempotente. Un `seq` ya observado es un no-op"). Sin `Date.now()`, sin
 * `fetch`, sin almacenamiento, sin mutación de `state`/`action` ni de
 * ninguna estructura anidada (arrays, `Set`, objetos). Toda fecha llega en
 * `action.at`.
 *
 * Acciones soportadas: RUN_REQUESTED, RUN_CREATED, SSE_EVENT,
 * SSE_RECONNECTING, SSE_DISCONNECTED, SSE_HEARTBEAT, RUN_RECONCILED,
 * RUN_DELETED, RUN_DETACHED. Cualquier otra `action.type` devuelve `state`
 * sin cambios, por identidad de referencia — nunca lanza.
 *
 * Guarda de transición: desde un estado terminal (completed/no_evidence/
 * interrupted/failed/deleted) solo se aceptan RUN_DELETED, RUN_RECONCILED
 * (nunca sobre `deleted`) y RUN_REQUESTED (inicia una corrida nueva y
 * restablece el estado por completo). Cualquier otra acción, incluida
 * SSE_HEARTBEAT, es un no-op referencial desde un terminal.
 */
import { RUN_STATUS, createInitialRunState, isTerminalRunStatus } from "./runStates.js";
import { messageForNode } from "./messages.es.js";
import { apiErrorFromEnvelope } from "../api/errors.js";
import { normalizeSectionId } from "./sectionId.js";

/** Acepta número o string; solo entero seguro >= 0, si no, `null`. */
function toSafeSeq(value) {
  if (typeof value === "number") {
    return Number.isSafeInteger(value) && value >= 0 ? value : null;
  }
  if (typeof value === "string" && /^\d+$/.test(value)) {
    const n = Number(value);
    return Number.isSafeInteger(n) ? n : null;
  }
  return null;
}

function asArray(value) {
  return Array.isArray(value) ? value : [];
}

function mapRunStatusToState(status) {
  switch (status) {
    case "completed":
      return RUN_STATUS.COMPLETED;
    case "no_evidence":
      return RUN_STATUS.NO_EVIDENCE;
    case "interrupted":
      return RUN_STATUS.INTERRUPTED;
    case "failed":
      return RUN_STATUS.FAILED;
    default:
      return null; // desconocido: no se asume nada
  }
}

/** Construye una entrada de paso en la MISMA forma para SSE en vivo y
 * reconciliación, para que "reconstruir sin duplicar" produzca objetos
 * indistinguibles entre ambas rutas. */
function buildStepEntry({ seq, stepNumber, node, displayMessageRaw, detail, at }) {
  return {
    seq,
    stepNumber: typeof stepNumber === "number" ? stepNumber : null,
    node: typeof node === "string" ? node : null,
    displayMessageRaw: typeof displayMessageRaw === "string" ? displayMessageRaw : "",
    displayMessage: messageForNode(node),
    detail: detail ?? null,
    at: at ?? null,
  };
}

const HAS_OWN = Object.prototype.hasOwnProperty;

/**
 * RUN_REQUESTED sirve tanto para la primera corrida como para comenzar una
 * nueva explícitamente desde un estado terminal (Parte 2). Siempre
 * restablece por completo `runId`, pasos, `seenSeqs`, `lastSeq`,
 * resultados, `error`, `reconnect` y `timings` — nunca los arrastra del
 * estado anterior. `question`/`contextHint`/`sectionId` vienen de la acción
 * si están presentes; si se omiten, se conservan del estado previo.
 */
function reduceRunRequested(state, action) {
  const question = HAS_OWN.call(action, "question") ? action.question : state.question;
  const contextHint = HAS_OWN.call(action, "contextHint") ? action.contextHint : state.contextHint;
  const sectionId = normalizeSectionId(HAS_OWN.call(action, "sectionId") ? action.sectionId : state.sectionId);

  const fresh = createInitialRunState({ question, contextHint, sectionId });
  return {
    ...fresh,
    status: RUN_STATUS.CREATING,
    timings: { ...fresh.timings, requestedAt: action.at ?? null },
  };
}

/**
 * `sectionId` es opcional en la acción: `start()` ya lo fijó vía
 * RUN_REQUESTED momentos antes (se conserva del estado si se omite).
 * `resume()`, en cambio, SIEMPRE lo trae explícito — reconstruye la
 * asociación runId→sectionId de la corrida que reanuda ANTES de que
 * RUN_RECONCILED la preserve verbatim (`reduceRunReconciled` nunca
 * sobrescribe `sectionId` desde el payload del servidor, que no lo conoce).
 * Sin este reseteo explícito, reanudar una corrida A después de haber
 * iniciado una corrida B dejaría `state.sectionId` apuntando a la sección
 * de B — una asociación falsa (F5-03A-R1).
 */
function reduceRunCreated(state, action) {
  const sectionId = normalizeSectionId(HAS_OWN.call(action, "sectionId") ? action.sectionId : state.sectionId);
  return {
    ...state,
    runId: action.runId ?? state.runId,
    sectionId,
    status: RUN_STATUS.STREAMING,
    timings: {
      ...state.timings,
      firstFeedbackAt: state.timings.firstFeedbackAt ?? action.at ?? null,
    },
  };
}

function reduceStepEvent(state, event, at) {
  const json = event.json;
  if (!json || typeof json !== "object") return state; // sin detalle interpretable: no se fabrica nada

  const stepEntry = buildStepEntry({
    seq: toSafeSeq(event.id),
    stepNumber: json.step_number,
    node: json.node,
    displayMessageRaw: json.display_message,
    detail: json.detail,
    at,
  });

  return {
    ...state,
    steps: [...state.steps, stepEntry],
    timings: {
      ...state.timings,
      firstStepAt: state.timings.firstStepAt ?? at ?? null,
    },
  };
}

function reduceAnswerEvent(state, event, at) {
  const json = event.json;
  if (!json || typeof json !== "object") return state;

  const status = mapRunStatusToState(json.status);
  // Este evento acepta únicamente completed/no_evidence (rule 5); un status
  // distinto (interrupted/failed llegan por evento "error", no "answer")
  // se ignora sin lanzar.
  if (status !== RUN_STATUS.COMPLETED && status !== RUN_STATUS.NO_EVIDENCE) return state;

  return {
    ...state,
    status,
    intention: json.intention ?? state.intention,
    evidence: asArray(json.evidence),
    claims: asArray(json.claims),
    presentationWarnings: asArray(json.presentation_warnings),
    textualFacts: asArray(json.textual_facts),
    noEvidenceReport: json.no_evidence_report ?? null,
    usage: json.usage ?? state.usage,
    timings: { ...state.timings, terminalAt: at ?? state.timings.terminalAt },
  };
}

function reduceErrorEvent(state, event, at) {
  const json = event.json;
  if (!json || typeof json !== "object" || !json.error || typeof json.error !== "object") {
    return state;
  }

  const envelope = json.error;
  const status =
    envelope.status === "interrupted"
      ? RUN_STATUS.INTERRUPTED
      : envelope.status === "failed"
        ? RUN_STATUS.FAILED
        : null;
  if (status === null) return state; // status terminal desconocido: no se asume nada

  // ApiError separa message_user de message_dev y redacta ambos; nunca se
  // expone message_dev al usuario (rule 6).
  const apiError = apiErrorFromEnvelope(null, { error: envelope });

  const next = {
    ...state,
    status,
    error: apiError,
    timings: { ...state.timings, terminalAt: at ?? state.timings.terminalAt },
  };

  // Parciales: solo se sobrescriben los campos que el payload SÍ trae; si
  // un partial_* está ausente, el valor previo del estado se conserva tal
  // cual (nunca se resetea a vacío, a diferencia del evento "answer").
  if (Array.isArray(json.partial_evidence)) next.evidence = json.partial_evidence;
  if (Array.isArray(json.partial_claims)) next.claims = json.partial_claims;
  if (Array.isArray(json.partial_textual_facts)) next.textualFacts = json.partial_textual_facts;

  // narrative no forma parte de este estado y no se fabrica aquí.
  return next;
}

/** Efectos según `event.event`; tipos desconocidos/aditivos (p. ej.
 * "evidence", que el contrato permite pero el runtime actual no emite) se
 * ignoran sin lanzar: su estado autoritativo llega por el terminal o por
 * RUN_RECONCILED, nunca se infiere de un evento intermedio (rule 4). */
function applyEventEffects(state, event, at) {
  if (event.event === "step") return reduceStepEvent(state, event, at);
  if (event.event === "answer") return reduceAnswerEvent(state, event, at);
  if (event.event === "error") return reduceErrorEvent(state, event, at);
  return state;
}

function reduceSseEvent(state, action) {
  const event = action.event;
  if (!event || typeof event !== "object") return state;

  const seq = toSafeSeq(event.id);
  if (seq === null) {
    // Evento normal sin seq válido: no-op referencial. streamRun ya reporta
    // la violación por su cuenta; el reducer no la vuelve a fabricar.
    return state;
  }
  if (state.seenSeqs.has(seq)) {
    return state; // duplicado: exactamente el mismo objeto, por referencia
  }

  const seenSeqs = new Set(state.seenSeqs);
  seenSeqs.add(seq);
  const withSeq = { ...state, seenSeqs, lastSeq: Math.max(state.lastSeq, seq) };

  return applyEventEffects(withSeq, event, action.at);
}

function reduceSseReconnecting(state, action) {
  return {
    ...state,
    status: RUN_STATUS.RECONNECTING,
    reconnect: {
      ...state.reconnect,
      attempts: typeof action.attempt === "number" ? action.attempt : state.reconnect.attempts,
      nextDelayMs: typeof action.delayMs === "number" ? action.delayMs : state.reconnect.nextDelayMs,
    },
  };
}

function reduceSseDisconnected(state) {
  return { ...state, status: RUN_STATUS.DISCONNECTED };
}

/** No cambia `status`, no toca `steps`/`lastSeq`: solo registra la última
 * marca de conexión viva. Sin `at` válido, no-op referencial. */
function reduceSseHeartbeat(state, action) {
  if (action.at === undefined || action.at === null) return state;
  return { ...state, reconnect: { ...state.reconnect, lastPingAt: action.at } };
}

function reduceRunDetached(state) {
  // Parciales, pasos, evidencia y claims se conservan por construcción del
  // spread: "detached" nunca equivale a un estado terminal de error.
  return { ...state, status: RUN_STATUS.DETACHED };
}

function reduceRunDeleted(state) {
  return { ...state, status: RUN_STATUS.DELETED };
}

/** Reconstruye `steps` desde `events[]` (forma `{seq, event, data}` de
 * `contracts/api-rest.md` §7). Reemplaza la lista local por completo: es
 * una reconstrucción autoritativa, no una fusión, así que nunca duplica. */
function stepsFromEvents(events) {
  const steps = [];
  for (const item of asArray(events)) {
    if (!item || item.event !== "step" || !item.data || typeof item.data !== "object") continue;
    steps.push(
      buildStepEntry({
        seq: toSafeSeq(item.seq),
        stepNumber: item.data.step_number,
        node: item.data.node,
        displayMessageRaw: item.data.display_message,
        detail: item.data.detail,
        at: null, // la reconciliación no aporta un timestamp de cliente real
      })
    );
  }
  return steps;
}

function seenSeqsFromEvents(events) {
  const seqs = new Set();
  for (const item of asArray(events)) {
    const seq = toSafeSeq(item?.seq);
    if (seq !== null) seqs.add(seq);
  }
  return seqs;
}

/** Busca en `events[]` el último evento terminal `error` para reconstruir
 * `state.error` en una reconciliación de una corrida interrupted/failed —
 * el `answer` de `GET /runs/{id}` no repite el sobre de error, solo
 * `events[]` lo conserva (`contracts/api-rest.md` §7). */
function errorFromEvents(events) {
  const list = asArray(events);
  for (let i = list.length - 1; i >= 0; i -= 1) {
    const item = list[i];
    if (item && item.event === "error" && item.data && item.data.error) {
      return apiErrorFromEnvelope(null, { error: item.data.error });
    }
  }
  return null;
}

/**
 * `sectionId` (F5-03A-R1) se deriva de la ACCIÓN igual que `runId` se
 * deriva de `run.run_id` — nunca solo de `state.sectionId`. Es
 * indispensable: `resume()` desde un estado terminal ve su `RUN_CREATED`
 * previo descartado por la guarda `ALLOWED_FROM_TERMINAL` (que no incluye
 * `RUN_CREATED`), así que si esta reconciliación no reafirmara `sectionId`
 * por sí sola, reanudar una corrida A justo después de que una corrida B
 * terminara dejaría `state.sectionId` apuntando todavía a B — la
 * asociación falsa que este incremento corrige.
 */
function reduceRunReconciled(state, action) {
  const run = action.run;
  if (!run || typeof run !== "object") return state;

  const sectionId = normalizeSectionId(HAS_OWN.call(action, "sectionId") ? action.sectionId : state.sectionId);
  const hasEvents = Array.isArray(run.events) && run.events.length > 0;
  const steps = hasEvents ? stepsFromEvents(run.events) : state.steps;
  const seenSeqs = hasEvents ? seenSeqsFromEvents(run.events) : state.seenSeqs;
  const lastSeq = typeof run.last_event_seq === "number" ? run.last_event_seq : state.lastSeq;

  if (run.status === "running") {
    return {
      ...state,
      runId: run.run_id ?? state.runId,
      sectionId,
      status: RUN_STATUS.STREAMING,
      steps,
      seenSeqs,
      lastSeq,
      evidence: Array.isArray(run.partial_evidence) ? run.partial_evidence : state.evidence,
      claims: Array.isArray(run.partial_claims) ? run.partial_claims : state.claims,
    };
  }

  const status = mapRunStatusToState(run.status);
  if (status === null) return state; // status desconocido: no se asume nada

  const answer = run.answer && typeof run.answer === "object" ? run.answer : {};
  const isErrorStatus = status === RUN_STATUS.INTERRUPTED || status === RUN_STATUS.FAILED;

  // completed/no_evidence: "sobrescribe campos autoritativos desde answer"
  // (contrato terminal ya vigente) — arrays ausentes se normalizan a [].
  //
  // interrupted/failed: el GET /runs/{id} real para estos dos estados casi
  // nunca repite evidence/claims/presentation_warnings en `answer` (los
  // fixtures reales `interrupted.json`/`failed.json` solo traen
  // textual_facts/partial_textual_facts ahí) — normalizar a [] borraría
  // parciales ya conocidos. Un campo AUSENTE conserva el valor previo del
  // estado; un campo presente (incluso como array vacío) sí reemplaza.
  const evidence = isErrorStatus
    ? Array.isArray(answer.evidence)
      ? answer.evidence
      : state.evidence
    : asArray(answer.evidence);
  const claims = isErrorStatus
    ? Array.isArray(answer.claims)
      ? answer.claims
      : state.claims
    : asArray(answer.claims);
  const presentationWarnings = isErrorStatus
    ? Array.isArray(answer.presentation_warnings)
      ? answer.presentation_warnings
      : state.presentationWarnings
    : asArray(answer.presentation_warnings);
  // Hechos textuales: prioriza partial_textual_facts, después
  // textual_facts; si ambos están ausentes, conserva state.textualFacts.
  const textualFacts = isErrorStatus
    ? Array.isArray(answer.partial_textual_facts)
      ? answer.partial_textual_facts
      : Array.isArray(answer.textual_facts)
        ? answer.textual_facts
        : state.textualFacts
    : asArray(answer.textual_facts);
  const noEvidenceReport = isErrorStatus
    ? HAS_OWN.call(answer, "no_evidence_report")
      ? (answer.no_evidence_report ?? null)
      : state.noEvidenceReport
    : (answer.no_evidence_report ?? null);

  return {
    ...state,
    // `question`/`contextHint` son metadatos locales preservados sin más:
    // `GET /runs/{id}` no los devuelve. `sectionId` es distinto — se
    // calculó arriba a partir de la ACCIÓN (ver comentario de la función).
    question: state.question,
    contextHint: state.contextHint,
    sectionId,
    runId: run.run_id ?? state.runId,
    status,
    steps,
    seenSeqs,
    lastSeq,
    intention: answer.intention ?? state.intention,
    evidence,
    claims,
    presentationWarnings,
    textualFacts,
    noEvidenceReport,
    usage: answer.usage ?? state.usage,
    error: isErrorStatus ? (errorFromEvents(run.events) ?? state.error) : null,
    timings: {
      ...state.timings,
      terminalAt: state.timings.terminalAt ?? action.at ?? null,
    },
  };
}

const HANDLERS = {
  RUN_REQUESTED: reduceRunRequested,
  RUN_CREATED: reduceRunCreated,
  SSE_EVENT: reduceSseEvent,
  SSE_RECONNECTING: reduceSseReconnecting,
  SSE_DISCONNECTED: reduceSseDisconnected,
  SSE_HEARTBEAT: reduceSseHeartbeat,
  RUN_RECONCILED: reduceRunReconciled,
  RUN_DELETED: reduceRunDeleted,
  RUN_DETACHED: reduceRunDetached,
};

/**
 * Desde un estado terminal (completed/no_evidence/interrupted/failed/deleted)
 * solo se permiten estas tres acciones — cualquier otra (incluida
 * SSE_HEARTBEAT) es un no-op referencial. `deleted` nunca se resucita, ni
 * siquiera por RUN_RECONCILED tardío.
 */
const ALLOWED_FROM_TERMINAL = new Set(["RUN_DELETED", "RUN_RECONCILED", "RUN_REQUESTED"]);

export function runReducer(state, action) {
  if (!action || typeof action.type !== "string") return state;
  const handler = HANDLERS[action.type];
  if (!handler) return state; // acción desconocida: mismo objeto, nunca lanza

  if (isTerminalRunStatus(state.status)) {
    if (!ALLOWED_FROM_TERMINAL.has(action.type)) {
      return state; // los terminales no retroceden a estados de transporte
    }
    if (action.type === "RUN_RECONCILED" && state.status === RUN_STATUS.DELETED) {
      return state; // deleted nunca se resucita, ni por reconciliación tardía
    }
  }

  return handler(state, action);
}
