import { describe, expect, it } from "vitest";
import { messageForNode, messageForStopReason } from "../../lib/agent/messages.es.js";

// Lista independiente de la implementación (backend/app/agent/deterministic_graph.py
// SupervisorNode) — si el mapa real pierde una clave, esta prueba debe fallar.
const REAL_NODES = [
  "start",
  "retrieve_candidates",
  "select_candidate",
  "profile_dataset",
  "build_plan",
  "explore_value",
  "validate_plan",
  "execute_query",
  "validate_quality",
  "derive_claims",
  "persist_facts",
  "synthesize",
  "next_candidate",
  "abstain",
  "complete",
];

// Lista independiente de StopReason (deterministic_graph.py).
const REAL_STOP_REASONS = [
  "NO_CANDIDATES",
  "CANDIDATE_BUDGET_EXCEEDED",
  "EXPLORATION_BUDGET_EXCEEDED",
  "QUERY_BUDGET_EXCEEDED",
  "PLAN_REPAIR_BUDGET_EXCEEDED",
  "LLM_BUDGET_EXCEEDED",
  "DURATION_BUDGET_EXCEEDED",
  "ALL_CANDIDATES_REJECTED",
  "EVIDENCE_NOT_ELIGIBLE",
  "CLAIMS_NOT_AVAILABLE",
];

const SHOUTY_ENUM_PATTERN = /\b[A-Z][A-Z0-9]*(_[A-Z0-9]+)+\b/;

describe("messageForNode", () => {
  it("13a. cubre los 14 SupervisorNode reales más el evento operativo start", () => {
    expect(REAL_NODES).toHaveLength(15); // 14 nodos + start
    for (const node of REAL_NODES) {
      const message = messageForNode(node);
      expect(typeof message).toBe("string");
      expect(message.length).toBeGreaterThan(0);
    }
  });

  it("start produce exactamente el mensaje operativo esperado", () => {
    expect(messageForNode("start")).toBe("Preparando la investigación…");
  });

  it("derive_claims describe verificación determinista, nunca cálculo del frontend/LLM", () => {
    const message = messageForNode("derive_claims");
    expect(message).toBe("Verificando cada cifra contra los datos de origen…");
    expect(message.toLowerCase()).not.toContain("calculando");
    expect(message.toLowerCase()).not.toContain("calcula");
  });

  it("15a. una clave de nodo desconocida nunca se muestra literalmente", () => {
    const message = messageForNode("un_nodo_que_no_existe");
    expect(message).not.toContain("un_nodo_que_no_existe");
    expect(message.length).toBeGreaterThan(0);
  });

  it("valores no-string (null, undefined, número) caen al genérico sin lanzar", () => {
    expect(() => messageForNode(null)).not.toThrow();
    expect(() => messageForNode(undefined)).not.toThrow();
    expect(() => messageForNode(42)).not.toThrow();
    expect(messageForNode(null)).toBe(messageForNode("un_nodo_que_no_existe"));
  });
});

describe("messageForStopReason", () => {
  it("14a. cubre los 10 StopReason reales", () => {
    expect(REAL_STOP_REASONS).toHaveLength(10);
    for (const reason of REAL_STOP_REASONS) {
      const message = messageForStopReason(reason);
      expect(typeof message).toBe("string");
      expect(message.length).toBeGreaterThan(0);
    }
  });

  it("15b. una clave de StopReason desconocida nunca se muestra literalmente", () => {
    const message = messageForStopReason("UN_MOTIVO_INVENTADO");
    expect(message).not.toContain("UN_MOTIVO_INVENTADO");
    expect(message.length).toBeGreaterThan(0);
  });
});

describe("16. ninguna salida visible contiene un ENUM_EN_MAYÚSCULAS con guion bajo", () => {
  it("mensajes de nodo", () => {
    for (const node of [...REAL_NODES, "clave_desconocida"]) {
      expect(messageForNode(node)).not.toMatch(SHOUTY_ENUM_PATTERN);
    }
  });

  it("mensajes de StopReason", () => {
    for (const reason of [...REAL_STOP_REASONS, "OTRO_DESCONOCIDO"]) {
      expect(messageForStopReason(reason)).not.toMatch(SHOUTY_ENUM_PATTERN);
    }
  });
});
