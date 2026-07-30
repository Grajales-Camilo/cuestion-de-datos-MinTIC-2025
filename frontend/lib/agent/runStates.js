/**
 * Estado inicial y máquina de estados de una corrida del agente (cliente).
 * Puro: sin React, sin `fetch`, sin almacenamiento, sin `Date.now()` interno.
 * Cualquier fecha entra desde fuera, nunca se genera aquí.
 */

export const RUN_STATUS = Object.freeze({
  IDLE: "idle",
  CREATING: "creating",
  STREAMING: "streaming",
  RECONNECTING: "reconnecting",
  DISCONNECTED: "disconnected",
  DETACHED: "detached",
  COMPLETED: "completed",
  NO_EVIDENCE: "no_evidence",
  INTERRUPTED: "interrupted",
  FAILED: "failed",
  DELETED: "deleted",
});

const TERMINAL_STATUSES = new Set([
  RUN_STATUS.COMPLETED,
  RUN_STATUS.NO_EVIDENCE,
  RUN_STATUS.INTERRUPTED,
  RUN_STATUS.FAILED,
  RUN_STATUS.DELETED,
]);

export function isTerminalRunStatus(status) {
  return TERMINAL_STATUSES.has(status);
}

/**
 * Estado inicial de una corrida. `question` es la única entrada obligatoria;
 * el resto de campos derivados del servidor (`runId`, `intention`, `steps`,
 * evidencia, claims...) empiezan vacíos hasta que llegue una acción real.
 */
export function createInitialRunState({ question, contextHint = null, sectionId = null }) {
  return {
    runId: null,
    status: RUN_STATUS.IDLE,
    question,
    contextHint,
    sectionId,
    intention: null,
    steps: [],
    seenSeqs: new Set(),
    lastSeq: 0,
    evidence: [],
    claims: [],
    presentationWarnings: [],
    textualFacts: [],
    noEvidenceReport: null,
    usage: null,
    error: null,
    reconnect: {
      attempts: 0,
      nextDelayMs: null,
      lastPingAt: null,
    },
    timings: {
      requestedAt: null,
      firstFeedbackAt: null,
      firstStepAt: null,
      terminalAt: null,
    },
  };
}
