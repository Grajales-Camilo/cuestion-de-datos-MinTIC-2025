/**
 * Traducción a español claro de los nodos del grafo determinista
 * (`backend/app/agent/deterministic_graph.py::SupervisorNode`, 14 valores) y
 * de los motivos de terminación sin evidencia
 * (`StopReason`, 10 valores), más el evento operativo aditivo `start` que
 * emite el runtime antes del primer paso real.
 *
 * Regla dura: esta tabla solo traduce un ENUM cerrado y conocido a una
 * frase fija. Nunca interpreta `detail`, `dataset_id`, alias de columnas ni
 * claims — eso sigue siendo dato técnico, nunca texto de UI (ver
 * `runReducer.js`). Una clave desconocida nunca se muestra cruda: cae en un
 * mensaje genérico seguro.
 */

const NODE_MESSAGES = Object.freeze({
  start: "Preparando la investigación…",
  retrieve_candidates: "Buscando datasets relevantes en el catálogo…",
  select_candidate: "Eligiendo el siguiente dataset candidato…",
  profile_dataset: "Revisando la estructura del dataset…",
  build_plan: "Preparando la consulta…",
  explore_value: "Verificando valores posibles en los datos…",
  validate_plan: "Validando la consulta antes de ejecutarla…",
  execute_query: "Consultando datos.gov.co…",
  validate_quality: "Evaluando la calidad de los datos obtenidos…",
  derive_claims: "Verificando cada cifra contra los datos de origen…",
  persist_facts: "Guardando la evidencia validada…",
  synthesize: "Redactando la respuesta…",
  next_candidate: "Buscando otro dataset candidato…",
  abstain: "No se encontró evidencia suficiente para responder…",
  complete: "Investigación completada.",
});

const STOP_REASON_MESSAGES = Object.freeze({
  NO_CANDIDATES: "No se encontraron datasets candidatos para esta pregunta.",
  CANDIDATE_BUDGET_EXCEEDED: "Se agotó el número de datasets que se podían revisar.",
  EXPLORATION_BUDGET_EXCEEDED: "Se agotó el número de exploraciones permitidas sobre los datos.",
  QUERY_BUDGET_EXCEEDED: "Se agotó el número de consultas permitidas a la fuente de datos.",
  PLAN_REPAIR_BUDGET_EXCEEDED: "No fue posible corregir la consulta dentro del límite de intentos.",
  LLM_BUDGET_EXCEEDED: "Se agotó el presupuesto de razonamiento disponible para esta investigación.",
  DURATION_BUDGET_EXCEEDED: "La investigación superó el tiempo máximo permitido.",
  ALL_CANDIDATES_REJECTED: "Ningún dataset candidato resultó válido para responder la pregunta.",
  EVIDENCE_NOT_ELIGIBLE:
    "Los datos encontrados no cumplen los criterios de elegibilidad para usarse como evidencia.",
  CLAIMS_NOT_AVAILABLE: "No fue posible construir una cifra verificable a partir de los datos encontrados.",
});

const GENERIC_NODE_MESSAGE = "Procesando un paso de la investigación…";
const GENERIC_STOP_REASON_MESSAGE = "La investigación se detuvo por una condición no reconocida.";

export function messageForNode(node) {
  if (typeof node === "string" && Object.prototype.hasOwnProperty.call(NODE_MESSAGES, node)) {
    return NODE_MESSAGES[node];
  }
  return GENERIC_NODE_MESSAGE;
}

export function messageForStopReason(reason) {
  if (
    typeof reason === "string" &&
    Object.prototype.hasOwnProperty.call(STOP_REASON_MESSAGES, reason)
  ) {
    return STOP_REASON_MESSAGES[reason];
  }
  return GENERIC_STOP_REASON_MESSAGE;
}
