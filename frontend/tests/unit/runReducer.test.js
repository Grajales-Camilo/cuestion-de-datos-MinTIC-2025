import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { createSseParser } from "../../lib/sse/parseSseChunk.js";
import { createInitialRunState, isTerminalRunStatus, RUN_STATUS } from "../../lib/agent/runStates.js";
import { runReducer } from "../../lib/agent/runReducer.js";

const TOKEN = "cdt_rt_9f8a7b6c5d4e3f2a1b0c";
const FIXTURES_DIR = path.resolve(process.cwd(), "tests/fixtures");

function loadJsonFixture(name) {
  return JSON.parse(readFileSync(path.join(FIXTURES_DIR, name), "utf-8"));
}

/** Reutiliza el parser real (ya probado en SSE-01) para convertir el
 * fixture crudo en la misma forma de evento que streamRun.js entregaría a
 * onEvent — no se reimplementa el parseo SSE en la prueba. */
function loadSseEvents(name) {
  const raw = readFileSync(path.join(FIXTURES_DIR, name));
  const parser = createSseParser();
  const events = [...parser.push(raw), ...parser.flush()];
  return events.filter((e) => !e.comment && !e.incomplete);
}

function errorEventFromFixture(fixture) {
  const item = fixture.events.at(-1);
  return { id: String(item.seq), event: item.event, data: JSON.stringify(item.data), json: item.data };
}

describe("runReducer · 1. secuencia feliz (fixture real completed-stream.sse.txt)", () => {
  it("procesa el stream completo y llega a completed con claims", () => {
    const events = loadSseEvents("completed-stream.sse.txt");
    expect(events).toHaveLength(10); // 9 step + 1 answer, confirmado contra el fixture

    let state = createInitialRunState({ question: "¿Cuál fue el promedio de deserción escolar…?" });
    state = runReducer(state, { type: "RUN_REQUESTED", at: 1 });
    state = runReducer(state, { type: "RUN_CREATED", runId: "e6ae9a62-3394-4eee-b9e4-c76a3adf9582", at: 2 });

    events.forEach((event, i) => {
      state = runReducer(state, { type: "SSE_EVENT", event, at: 100 + i });
    });

    expect(state.status).toBe(RUN_STATUS.COMPLETED);
    expect(state.steps).toHaveLength(9);
    expect(state.steps[0].node).toBe("start");
    expect(state.steps[0].displayMessage).toBe("Preparando la investigación…");
    expect(state.steps[0].displayMessageRaw).toBe("Preparando la investigación.");
    expect(state.lastSeq).toBe(10);
    expect(state.seenSeqs.size).toBe(10);
    expect(state.claims).toHaveLength(1);
    expect(state.claims[0].label_status).toBe("verified");
    expect(state.timings.firstStepAt).toBe(100);
    expect(state.timings.terminalAt).toBe(109);
  });
});

describe("runReducer · 2-3. secuencia y deduplicación", () => {
  const stepEvent = (id, node) => ({
    id,
    event: "step",
    data: `{"node":"${node}","step_number":0,"display_message":"x"}`,
    json: { node, step_number: 0, display_message: "x" },
  });

  it("2. un evento duplicado (mismo seq) es un no-op por identidad referencial", () => {
    const state0 = createInitialRunState({ question: "x" });
    const event = stepEvent("1", "start");

    const afterFirst = runReducer(state0, { type: "SSE_EVENT", event, at: 1 });
    const afterSecond = runReducer(afterFirst, { type: "SSE_EVENT", event, at: 2 });

    expect(afterSecond).toBe(afterFirst); // misma referencia exacta, no solo igual por valor
    expect(afterFirst.steps).toHaveLength(1);
  });

  it("3. un hueco de seq no fabrica los pasos faltantes", () => {
    let state = createInitialRunState({ question: "x" });
    state = runReducer(state, { type: "SSE_EVENT", event: stepEvent("1", "select_candidate"), at: 1 });
    state = runReducer(state, { type: "SSE_EVENT", event: stepEvent("3", "profile_dataset"), at: 2 }); // salta el 2

    expect(state.steps).toHaveLength(2); // nunca 3: no se inventa el paso 2
    expect(state.steps.map((s) => s.seq)).toEqual([1, 3]);
    expect(state.lastSeq).toBe(3);
    expect([...state.seenSeqs]).toEqual([1, 3]);
  });

  it("evento normal sin seq válido es no-op referencial (streamRun ya reporta la violación)", () => {
    const state0 = createInitialRunState({ question: "x" });
    const badEvent = { event: "step", data: "{}", json: { node: "start" } }; // sin id
    const next = runReducer(state0, { type: "SSE_EVENT", event: badEvent, at: 1 });
    expect(next).toBe(state0);
  });
});

describe("runReducer · 4-7. mapeo de eventos terminales (fixtures reales)", () => {
  it("4. completed mapea claims/evidence/presentationWarnings/textualFacts sin reinterpretarlos", () => {
    const fixture = loadJsonFixture("completed-with-claims.json");
    const answerEvent = {
      id: "15",
      event: "answer",
      data: JSON.stringify(fixture.answer),
      json: fixture.answer,
    };

    let state = createInitialRunState({ question: "x" });
    state = runReducer(state, { type: "SSE_EVENT", event: answerEvent, at: 1 });

    expect(state.status).toBe(RUN_STATUS.COMPLETED);
    expect(state.claims).toEqual(fixture.answer.claims);
    expect(state.evidence).toEqual(fixture.answer.evidence);
    expect(state.presentationWarnings).toEqual(fixture.answer.presentation_warnings);
    expect(state.textualFacts).toEqual(fixture.answer.textual_facts);
    expect(state.intention).toEqual(fixture.answer.intention);
    expect(state.usage).toEqual(fixture.answer.usage);
  });

  it("5. no_evidence conserva su no_evidence_report intacto", () => {
    const fixture = loadJsonFixture("no-evidence.json");
    const answerEvent = {
      id: "25",
      event: "answer",
      data: JSON.stringify(fixture.answer),
      json: fixture.answer,
    };

    let state = createInitialRunState({ question: "x" });
    state = runReducer(state, { type: "SSE_EVENT", event: answerEvent, at: 1 });

    expect(state.status).toBe(RUN_STATUS.NO_EVIDENCE);
    expect(state.noEvidenceReport).toEqual(fixture.answer.no_evidence_report);
    expect(state.claims).toEqual([]);
  });

  it("6. interrupted conserva los parciales previos cuando el payload no trae partial_*", () => {
    const fixture = loadJsonFixture("interrupted.json");
    const errorEvent = errorEventFromFixture(fixture);
    expect(errorEvent.event).toBe("error");
    expect(errorEvent.json.partial_evidence).toBeUndefined();
    expect(errorEvent.json.partial_claims).toBeUndefined();

    let state = createInitialRunState({ question: "x" });
    // Simula evidencia/claims ya validados antes de la interrupción.
    state = { ...state, evidence: [{ dataset_id: "ji8i-4anb" }], claims: [{ claim_id: "c1" }] };

    state = runReducer(state, { type: "SSE_EVENT", event: errorEvent, at: 1 });

    expect(state.status).toBe(RUN_STATUS.INTERRUPTED);
    expect(state.evidence).toEqual([{ dataset_id: "ji8i-4anb" }]); // conservado, no borrado
    expect(state.claims).toEqual([{ claim_id: "c1" }]);
    expect(state.error.code).toBe("RUN_INTERRUPTED");
    expect(state.error.messageUser).toContain("reinicio");
  });

  it("7. failed no fabrica narrativa ni datos ausentes del payload", () => {
    const fixture = loadJsonFixture("failed.json");
    const errorEvent = errorEventFromFixture(fixture);

    let state = createInitialRunState({ question: "x" });
    state = runReducer(state, { type: "SSE_EVENT", event: errorEvent, at: 1 });

    expect(state.status).toBe(RUN_STATUS.FAILED);
    expect(state.error.code).toBe("SOCRATA_TIMEOUT");
    expect(state.error.messageUser).toBe("La fuente de datos no respondió a tiempo.");
    // message_dev nunca llega al usuario tal cual (rule 6):
    expect(state.error.messageUser).not.toContain("Socrata no respondio");
    // El estado no tiene ni fabrica ningún campo de narrativa para failed:
    expect(state.evidence).toEqual([]);
    expect(state.claims).toEqual([]);
  });
});

describe("runReducer · 8-9. reconciliación", () => {
  it("8. RUN_RECONCILED reemplaza el estado con el resultado autoritativo sin duplicar pasos", () => {
    const fixture = loadJsonFixture("completed-with-claims.json");
    const expectedStepCount = fixture.events.filter((e) => e.event === "step").length;

    let state = createInitialRunState({
      question: "pregunta local",
      contextHint: "contexto local",
      sectionId: "sec-1",
    });
    state = runReducer(state, { type: "RUN_RECONCILED", run: fixture, at: 1 });

    expect(state.status).toBe(RUN_STATUS.COMPLETED);
    expect(state.runId).toBe(fixture.run_id);
    expect(state.steps).toHaveLength(expectedStepCount);
    expect(state.lastSeq).toBe(fixture.last_event_seq);
    expect(state.claims).toEqual(fixture.answer.claims);
    // Metadatos locales preservados: GET /runs/{id} no los devuelve.
    expect(state.question).toBe("pregunta local");
    expect(state.contextHint).toBe("contexto local");
    expect(state.sectionId).toBe("sec-1");
  });

  it("RUN_RECONCILED con sectionId en la acción lo reemplaza, igual que ya reemplaza runId desde run.run_id (F5-03A-R1)", () => {
    const fixture = loadJsonFixture("completed-with-claims.json");
    const state = createInitialRunState({ question: "x", sectionId: "sec-viejo" });

    const next = runReducer(state, { type: "RUN_RECONCILED", run: fixture, sectionId: "sec-nuevo", at: 1 });

    expect(next.sectionId).toBe("sec-nuevo");
  });

  it("reanudar tras un terminal: RUN_CREATED queda bloqueado por la guarda, pero RUN_RECONCILED igual corrige sectionId (F5-03A-R1)", () => {
    const fixture = loadJsonFixture("completed-with-claims.json");
    // Estado terminal de una corrida B ya completada, con su propia sección.
    const state = {
      ...createInitialRunState({ question: "x", sectionId: "sec-B" }),
      runId: "run-B",
      status: RUN_STATUS.COMPLETED,
    };

    // `resume()` despacha exactamente esta secuencia. RUN_CREATED es un
    // no-op referencial aquí porque el estado sigue siendo terminal
    // (ALLOWED_FROM_TERMINAL no incluye "RUN_CREATED") — el defecto real
    // que motivó este incremento: sin el fix, `sectionId` se quedaría en
    // "sec-B" porque RUN_RECONCILED solo lo preservaba de `state`.
    const afterCreated = runReducer(state, { type: "RUN_CREATED", runId: "run-A", sectionId: "sec-A", at: 1 });
    expect(afterCreated).toBe(state); // confirma el no-op: sigue siendo el estado de B

    const afterReconciled = runReducer(afterCreated, {
      type: "RUN_RECONCILED",
      run: { ...fixture, run_id: "run-A" },
      sectionId: "sec-A",
      at: 2,
    });

    expect(afterReconciled.runId).toBe("run-A");
    expect(afterReconciled.sectionId).toBe("sec-A");
  });

  it("9. aplicar la misma reconciliación dos veces es idempotente", () => {
    const fixture = loadJsonFixture("completed-with-claims.json");
    let state = createInitialRunState({ question: "x" });

    const once = runReducer(state, { type: "RUN_RECONCILED", run: fixture, at: 1 });
    const twice = runReducer(once, { type: "RUN_RECONCILED", run: fixture, at: 2 });

    expect(twice.steps).toEqual(once.steps);
    expect(twice.claims).toEqual(once.claims);
    expect(twice.lastSeq).toBe(once.lastSeq);
    expect([...twice.seenSeqs].sort()).toEqual([...once.seenSeqs].sort());
    expect(twice.status).toBe(once.status);
  });

  it("una reconciliación 'running' reconstruye steps desde events[] y vuelve a streaming", () => {
    const runningRun = {
      run_id: "r1",
      status: "running",
      last_event_seq: 2,
      events: [
        { seq: 1, event: "step", data: { node: "start", step_number: 0, display_message: "x" } },
        { seq: 2, event: "step", data: { node: "select_candidate", step_number: 1, display_message: "y" } },
      ],
    };
    let state = createInitialRunState({ question: "x" });
    state = runReducer(state, { type: "RUN_RECONCILED", run: runningRun, at: 1 });

    expect(state.status).toBe(RUN_STATUS.STREAMING);
    expect(state.steps).toHaveLength(2);
    expect(state.lastSeq).toBe(2);
  });
});

describe("runReducer · 10-12. detached, deleted y acciones desconocidas", () => {
  it("10. RUN_DETACHED no equivale a interrupted y conserva los parciales", () => {
    let state = createInitialRunState({ question: "x" });
    state = { ...state, status: RUN_STATUS.STREAMING, evidence: [{ a: 1 }], claims: [{ b: 2 }] };

    const detached = runReducer(state, { type: "RUN_DETACHED", at: 1 });

    expect(detached.status).toBe(RUN_STATUS.DETACHED);
    expect(detached.status).not.toBe(RUN_STATUS.INTERRUPTED);
    expect(detached.error).toBeNull();
    expect(detached.evidence).toEqual([{ a: 1 }]);
    expect(detached.claims).toEqual([{ b: 2 }]);
    expect(isTerminalRunStatus(detached.status)).toBe(false);
  });

  it("11. RUN_DELETED lleva a un estado terminal", () => {
    const state = createInitialRunState({ question: "x" });
    const deleted = runReducer(state, { type: "RUN_DELETED", at: 1 });

    expect(deleted.status).toBe(RUN_STATUS.DELETED);
    expect(isTerminalRunStatus(deleted.status)).toBe(true);
  });

  it("12. una acción desconocida (o inválida) devuelve exactamente el mismo objeto state", () => {
    const state = createInitialRunState({ question: "x" });

    expect(runReducer(state, { type: "ALGO_QUE_NO_EXISTE", at: 1 })).toBe(state);
    expect(runReducer(state, null)).toBe(state);
    expect(runReducer(state, {})).toBe(state);
    expect(runReducer(state, { type: 42 })).toBe(state);
  });
});

describe("runReducer · pureza", () => {
  it("no muta state ni action, ni arrays/objetos anidados", () => {
    const state = createInitialRunState({ question: "x" });
    const stateSnapshot = JSON.parse(JSON.stringify({ ...state, seenSeqs: [...state.seenSeqs] }));
    const action = {
      type: "SSE_EVENT",
      event: { id: "1", event: "step", data: "{}", json: { node: "start" } },
      at: 1,
    };
    const actionSnapshot = JSON.parse(JSON.stringify(action));

    runReducer(state, action);

    expect(JSON.parse(JSON.stringify({ ...state, seenSeqs: [...state.seenSeqs] }))).toEqual(stateSnapshot);
    expect(JSON.parse(JSON.stringify(action))).toEqual(actionSnapshot);
  });
});

describe("runReducer · 17. ausencia del token", () => {
  it("el token nunca aparece en ningún estado serializable, tras una secuencia realista completa", () => {
    const events = loadSseEvents("completed-stream.sse.txt");
    let state = createInitialRunState({ question: "x" });
    state = runReducer(state, { type: "RUN_REQUESTED", at: 1 });
    state = runReducer(state, { type: "RUN_CREATED", runId: "r1", at: 2 });
    events.forEach((event, i) => {
      state = runReducer(state, { type: "SSE_EVENT", event, at: 100 + i });
    });

    const reconciledRun = loadJsonFixture("interrupted.json");
    state = runReducer(state, { type: "RUN_RECONCILED", run: reconciledRun, at: 200 });
    state = runReducer(state, { type: "SSE_RECONNECTING", attempt: 1, delayMs: 500, at: 201 });
    state = runReducer(state, { type: "SSE_DISCONNECTED", at: 202 });
    state = runReducer(state, { type: "RUN_DETACHED", at: 203 });
    state = runReducer(state, { type: "RUN_DELETED", at: 204 });

    const serialized = JSON.stringify(state, (key, value) => (value instanceof Set ? [...value] : value));
    expect(/cdt_rt_[A-Za-z0-9_-]+/.test(serialized)).toBe(false);
    expect(serialized).not.toContain(TOKEN);
    expect(serialized.toLowerCase()).not.toContain("authorization");
  });
});

describe("runReducer · reconciliación sin pérdida (interrupted/failed)", () => {
  it("interrupted: answer.evidence/claims/presentation_warnings ausentes conservan los del estado previo", () => {
    const fixture = loadJsonFixture("interrupted.json");
    expect(fixture.answer.evidence).toBeUndefined();
    expect(fixture.answer.claims).toBeUndefined();
    expect(fixture.answer.presentation_warnings).toBeUndefined();

    let state = createInitialRunState({ question: "x" });
    state = {
      ...state,
      evidence: [{ dataset_id: "ji8i-4anb" }],
      claims: [{ claim_id: "c1" }],
      presentationWarnings: [{ claim_id: "c1", reason: "ambiguous" }],
      usage: { steps_used: 3 },
      intention: { topic: "algo" },
    };

    state = runReducer(state, { type: "RUN_RECONCILED", run: fixture, at: 1 });

    expect(state.status).toBe(RUN_STATUS.INTERRUPTED);
    expect(state.evidence).toEqual([{ dataset_id: "ji8i-4anb" }]);
    expect(state.claims).toEqual([{ claim_id: "c1" }]);
    expect(state.presentationWarnings).toEqual([{ claim_id: "c1", reason: "ambiguous" }]);
    expect(state.usage).toEqual({ steps_used: 3 });
    expect(state.intention).toEqual({ topic: "algo" });
    expect(state.error.code).toBe("RUN_INTERRUPTED");
  });

  it("interrupted: textualFacts prioriza partial_textual_facts sobre textual_facts", () => {
    const fixture = loadJsonFixture("interrupted.json");
    // El fixture real trae ambos como [] — se fuerza un caso con contenido
    // para probar la prioridad sin fabricar un fixture nuevo (dato sintético
    // de prueba, no un payload que se declare "real").
    const run = {
      ...fixture,
      answer: { ...fixture.answer, partial_textual_facts: [{ fact: "parcial" }], textual_facts: [{ fact: "final" }] },
    };
    let state = createInitialRunState({ question: "x" });
    state = runReducer(state, { type: "RUN_RECONCILED", run, at: 1 });
    expect(state.textualFacts).toEqual([{ fact: "parcial" }]);
  });

  it("interrupted: sin partial_textual_facts, usa textual_facts; sin ninguno, conserva el previo", () => {
    const fixture = loadJsonFixture("interrupted.json");

    const runOnlyTextualFacts = {
      ...fixture,
      answer: { textual_facts: [{ fact: "final" }] },
    };
    let state1 = createInitialRunState({ question: "x" });
    state1 = runReducer(state1, { type: "RUN_RECONCILED", run: runOnlyTextualFacts, at: 1 });
    expect(state1.textualFacts).toEqual([{ fact: "final" }]);

    // El fixture real siempre trae textual_facts/partial_textual_facts como
    // [] (presentes); para probar "ambos AUSENTES" hace falta un answer que
    // de verdad no declare ninguno de los dos campos.
    const runWithNeither = { ...fixture, answer: { status: fixture.answer.status } };
    let state2 = createInitialRunState({ question: "x" });
    state2 = { ...state2, textualFacts: [{ fact: "previo" }] };
    state2 = runReducer(state2, { type: "RUN_RECONCILED", run: runWithNeither, at: 1 });
    expect(state2.textualFacts).toEqual([{ fact: "previo" }]);
  });

  it("failed: conserva evidence/claims previos y no fabrica narrativa (fixture real failed.json)", () => {
    const fixture = loadJsonFixture("failed.json");
    let state = createInitialRunState({ question: "x" });
    state = { ...state, evidence: [{ dataset_id: "kekd-7v7h" }], claims: [] };

    state = runReducer(state, { type: "RUN_RECONCILED", run: fixture, at: 1 });

    expect(state.status).toBe(RUN_STATUS.FAILED);
    expect(state.evidence).toEqual([{ dataset_id: "kekd-7v7h" }]);
    expect(state.error.code).toBe("SOCRATA_TIMEOUT");
    expect(state.error.messageUser).toBe("La fuente de datos no respondió a tiempo.");
  });

  it("completed/no_evidence conservan el comportamiento vigente: ausentes → []", () => {
    const fixture = loadJsonFixture("no-evidence.json");
    let state = createInitialRunState({ question: "x" });
    state = { ...state, evidence: [{ x: 1 }] }; // no debe sobrevivir: completed/no_evidence sí normalizan a []

    state = runReducer(state, { type: "RUN_RECONCILED", run: fixture, at: 1 });

    expect(state.status).toBe(RUN_STATUS.NO_EVIDENCE);
    expect(state.evidence).toEqual([]);
    expect(state.noEvidenceReport).toEqual(fixture.answer.no_evidence_report);
  });
});

describe("runReducer · guardas de transición desde estados terminales", () => {
  function terminalState(status, extra = {}) {
    const base = createInitialRunState({ question: "x" });
    return { ...base, status, ...extra };
  }

  it("completed + SSE_RECONNECTING → mismo objeto", () => {
    const state = terminalState(RUN_STATUS.COMPLETED);
    const next = runReducer(state, { type: "SSE_RECONNECTING", attempt: 1, delayMs: 500, at: 1 });
    expect(next).toBe(state);
  });

  it("interrupted + RUN_DETACHED → mismo objeto", () => {
    const state = terminalState(RUN_STATUS.INTERRUPTED);
    const next = runReducer(state, { type: "RUN_DETACHED", at: 1 });
    expect(next).toBe(state);
  });

  it("no_evidence + SSE_DISCONNECTED → mismo objeto", () => {
    const state = terminalState(RUN_STATUS.NO_EVIDENCE);
    const next = runReducer(state, { type: "SSE_DISCONNECTED", at: 1 });
    expect(next).toBe(state);
  });

  it("failed + SSE_EVENT (aunque sea un answer válido) → mismo objeto", () => {
    const state = terminalState(RUN_STATUS.FAILED);
    const event = {
      id: "1",
      event: "answer",
      json: { status: "completed", claims: [], evidence: [] },
    };
    const next = runReducer(state, { type: "SSE_EVENT", event, at: 1 });
    expect(next).toBe(state);
  });

  it("deleted + RUN_RECONCILED → mismo objeto (deleted nunca se resucita)", () => {
    const fixture = loadJsonFixture("completed-with-claims.json");
    const state = terminalState(RUN_STATUS.DELETED);
    const next = runReducer(state, { type: "RUN_RECONCILED", run: fixture, at: 1 });
    expect(next).toBe(state);
  });

  it("deleted + SSE_HEARTBEAT → mismo objeto", () => {
    const state = terminalState(RUN_STATUS.DELETED);
    const next = runReducer(state, { type: "SSE_HEARTBEAT", at: 1 });
    expect(next).toBe(state);
  });

  it("un terminal no-deleted SÍ acepta RUN_RECONCILED (p. ej. completed → puede reconciliarse)", () => {
    const fixture = loadJsonFixture("completed-with-claims.json");
    const state = terminalState(RUN_STATUS.COMPLETED);
    const next = runReducer(state, { type: "RUN_RECONCILED", run: fixture, at: 1 });
    expect(next).not.toBe(state);
    expect(next.claims).toEqual(fixture.answer.claims);
  });

  it("terminal + RUN_REQUESTED → nuevo estado limpio en creating, conservando metadatos si se omiten", () => {
    const state = terminalState(RUN_STATUS.FAILED, {
      runId: "run-viejo",
      steps: [{ seq: 1, node: "start" }],
      seenSeqs: new Set([1, 2, 3]),
      lastSeq: 3,
      evidence: [{ x: 1 }],
      claims: [{ y: 2 }],
      error: { code: "SOCRATA_TIMEOUT" },
      reconnect: { attempts: 4, nextDelayMs: 8000, lastPingAt: 99 },
      question: "pregunta original",
      contextHint: "contexto original",
      sectionId: "sec-1",
    });

    const next = runReducer(state, { type: "RUN_REQUESTED", at: 500 });

    expect(next).not.toBe(state);
    expect(next.status).toBe(RUN_STATUS.CREATING);
    expect(next.runId).toBeNull();
    expect(next.steps).toEqual([]);
    expect(next.seenSeqs.size).toBe(0);
    expect(next.lastSeq).toBe(0);
    expect(next.evidence).toEqual([]);
    expect(next.claims).toEqual([]);
    expect(next.error).toBeNull();
    expect(next.reconnect).toEqual({ attempts: 0, nextDelayMs: null, lastPingAt: null });
    expect(next.timings).toEqual({
      requestedAt: 500,
      firstFeedbackAt: null,
      firstStepAt: null,
      terminalAt: null,
    });
    // question/contextHint/sectionId se conservan porque la acción los omitió:
    expect(next.question).toBe("pregunta original");
    expect(next.contextHint).toBe("contexto original");
    expect(next.sectionId).toBe("sec-1");
  });

  it("RUN_REQUESTED puede reemplazar question/contextHint/sectionId si la acción los trae", () => {
    const state = terminalState(RUN_STATUS.COMPLETED, {
      question: "pregunta vieja",
      contextHint: "contexto viejo",
      sectionId: "sec-viejo",
    });
    const next = runReducer(state, {
      type: "RUN_REQUESTED",
      at: 1,
      question: "pregunta nueva",
      contextHint: "contexto nuevo",
      sectionId: "sec-nuevo",
    });
    expect(next.question).toBe("pregunta nueva");
    expect(next.contextHint).toBe("contexto nuevo");
    expect(next.sectionId).toBe("sec-nuevo");
  });
});

describe("runReducer · SSE_HEARTBEAT", () => {
  it("actualiza reconnect.lastPingAt sin tocar status, steps ni lastSeq", () => {
    let state = createInitialRunState({ question: "x" });
    state = { ...state, status: RUN_STATUS.STREAMING, steps: [{ seq: 1 }], lastSeq: 1 };

    const next = runReducer(state, { type: "SSE_HEARTBEAT", at: 42 });

    expect(next.reconnect.lastPingAt).toBe(42);
    expect(next.status).toBe(RUN_STATUS.STREAMING);
    expect(next.steps).toBe(state.steps); // ni siquiera se clona: no se tocó
    expect(next.lastSeq).toBe(1);
  });

  it("sin at válido es un no-op referencial", () => {
    const state = createInitialRunState({ question: "x" });
    expect(runReducer(state, { type: "SSE_HEARTBEAT" })).toBe(state);
    expect(runReducer(state, { type: "SSE_HEARTBEAT", at: null })).toBe(state);
    expect(runReducer(state, { type: "SSE_HEARTBEAT", at: undefined })).toBe(state);
  });

  it("en un estado terminal es un no-op referencial (vía la guarda genérica)", () => {
    const state = { ...createInitialRunState({ question: "x" }), status: RUN_STATUS.COMPLETED };
    expect(runReducer(state, { type: "SSE_HEARTBEAT", at: 1 })).toBe(state);
  });
});

describe("runReducer · F5-03A-R2: sectionId sensible nunca sobrevive, ni siquiera despachado directamente", () => {
  it("RUN_REQUESTED con sectionId sensible produce sectionId:null", () => {
    const state = createInitialRunState({ question: "x" });
    const next = runReducer(state, {
      type: "RUN_REQUESTED",
      question: "y",
      sectionId: "seccion-cdt_rt_secreto",
      at: 1,
    });
    expect(next.sectionId).toBeNull();
    expect(JSON.stringify(next, (k, v) => (v instanceof Set ? [...v] : v))).not.toContain("cdt_rt_secreto");
  });

  it("RUN_CREATED con sectionId sensible produce sectionId:null, incluso sobre un estado con sección previa válida", () => {
    const state = { ...createInitialRunState({ question: "x", sectionId: "sec-legitima" }), status: RUN_STATUS.CREATING };
    const next = runReducer(state, { type: "RUN_CREATED", runId: "r1", sectionId: "seccion-cdt_rt_secreto", at: 1 });
    expect(next.sectionId).toBeNull();
  });

  it("RUN_RECONCILED con sectionId sensible en la acción produce sectionId:null, incluso reanudando tras un terminal", () => {
    const fixture = loadJsonFixture("completed-with-claims.json");
    const state = { ...createInitialRunState({ question: "x", sectionId: "sec-B" }), runId: "run-B", status: RUN_STATUS.COMPLETED };
    const next = runReducer(state, {
      type: "RUN_RECONCILED",
      run: { ...fixture, run_id: "run-A" },
      sectionId: "seccion-cdt_rt_secreto",
      at: 1,
    });
    expect(next.runId).toBe("run-A");
    expect(next.sectionId).toBeNull();
  });

  it("un state.sectionId ya envenenado (por ejemplo, escrito a mano en una prueba) tampoco sobrevive cuando la acción lo omite", () => {
    const state = { ...createInitialRunState({ question: "x" }), sectionId: "seccion-cdt_rt_secreto" };
    const next = runReducer(state, { type: "RUN_CREATED", runId: "r1", at: 1 });
    expect(next.sectionId).toBeNull();
  });
});
