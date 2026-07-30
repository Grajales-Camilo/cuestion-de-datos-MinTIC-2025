import { describe, expect, it } from "vitest";
import { RUN_STATUS, createInitialRunState, isTerminalRunStatus } from "../../lib/agent/runStates.js";

describe("createInitialRunState", () => {
  it("crea un estado idle con los metadatos locales y el resto vacío", () => {
    const state = createInitialRunState({
      question: "¿Cuál es la tasa de deserción escolar en Sonsón?",
      contextHint: "Sección: Definición del problema.",
      sectionId: "sec-1",
    });

    expect(state.status).toBe(RUN_STATUS.IDLE);
    expect(state.runId).toBeNull();
    expect(state.question).toBe("¿Cuál es la tasa de deserción escolar en Sonsón?");
    expect(state.contextHint).toBe("Sección: Definición del problema.");
    expect(state.sectionId).toBe("sec-1");
    expect(state.steps).toEqual([]);
    expect(state.seenSeqs).toBeInstanceOf(Set);
    expect(state.seenSeqs.size).toBe(0);
    expect(state.lastSeq).toBe(0);
    expect(state.evidence).toEqual([]);
    expect(state.claims).toEqual([]);
    expect(state.presentationWarnings).toEqual([]);
    expect(state.textualFacts).toEqual([]);
    expect(state.noEvidenceReport).toBeNull();
    expect(state.usage).toBeNull();
    expect(state.error).toBeNull();
    expect(state.reconnect).toEqual({ attempts: 0, nextDelayMs: null, lastPingAt: null });
    expect(state.timings).toEqual({
      requestedAt: null,
      firstFeedbackAt: null,
      firstStepAt: null,
      terminalAt: null,
    });
  });

  it("contextHint y sectionId son opcionales y por defecto null", () => {
    const state = createInitialRunState({ question: "pregunta mínima" });
    expect(state.contextHint).toBeNull();
    expect(state.sectionId).toBeNull();
  });

  it("no llama Date.now ni ninguna fuente de tiempo interna", () => {
    const state = createInitialRunState({ question: "x" });
    expect(state.timings.requestedAt).toBeNull();
  });
});

describe("isTerminalRunStatus", () => {
  it("los cinco estados terminales devuelven true", () => {
    for (const status of [
      RUN_STATUS.COMPLETED,
      RUN_STATUS.NO_EVIDENCE,
      RUN_STATUS.INTERRUPTED,
      RUN_STATUS.FAILED,
      RUN_STATUS.DELETED,
    ]) {
      expect(isTerminalRunStatus(status)).toBe(true);
    }
  });

  it("los estados no terminales devuelven false", () => {
    for (const status of [
      RUN_STATUS.IDLE,
      RUN_STATUS.CREATING,
      RUN_STATUS.STREAMING,
      RUN_STATUS.RECONNECTING,
      RUN_STATUS.DISCONNECTED,
      RUN_STATUS.DETACHED,
    ]) {
      expect(isTerminalRunStatus(status)).toBe(false);
    }
  });

  it("un valor desconocido devuelve false sin lanzar", () => {
    expect(isTerminalRunStatus("algo_inventado")).toBe(false);
    expect(isTerminalRunStatus(undefined)).toBe(false);
    expect(isTerminalRunStatus(null)).toBe(false);
  });
});
