import { readFileSync } from "node:fs";
import path from "node:path";
import { useCallback, useEffect, useRef, useState } from "react";
import { act, render, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useAgentRun } from "../../../hooks/useAgentRun";
import { useRunHistory } from "../../../hooks/useRunHistory";
import { DocumentSections } from "../../../components/document";
import { EMPTY_DOCUMENT_JSON } from "../../../lib/document/documentSchema";

/**
 * Prueba obligatoria de F5-03A-R1: la asociación runId→sectionId debe
 * sobrevivir a reanudar una corrida anterior después de haber iniciado
 * otra. Ejercita la MISMA composición de hooks que `pages/app.js`
 * (`useAgentRun` + `useRunHistory` + el puente `onLifecycle`), no un doble
 * artificial — la única simplificación es omitir `useConsent` real
 * (`consentGranted: true` fijo), ortogonal a lo que se prueba aquí.
 */

// ProseMirror mide la selección al desplazar el cursor; jsdom no la
// implementa (mismo doble que `DocumentEditor.test.jsx`).
if (typeof Range !== "undefined" && typeof Range.prototype.getClientRects !== "function") {
  Range.prototype.getClientRects = () => [];
}
if (typeof Range !== "undefined" && typeof Range.prototype.getBoundingClientRect !== "function") {
  Range.prototype.getBoundingClientRect = () => ({ bottom: 0, height: 0, left: 0, right: 0, top: 0, width: 0 });
}
if (typeof document !== "undefined" && typeof document.elementFromPoint !== "function") {
  document.elementFromPoint = () => document.querySelector('[role="textbox"]') ?? document.body;
}

const fixture = JSON.parse(
  readFileSync(path.resolve(process.cwd(), "tests/fixtures/completed-with-claims.json"), "utf8"),
);

function evidenceFor(label) {
  const evidence = structuredClone(fixture.answer.evidence[0]);
  evidence.evidence_id = `${evidence.evidence_id}-${label}`;
  evidence.dataset_name = `${evidence.dataset_name} — ${label}`;
  evidence.citation.dataset_name = evidence.dataset_name;
  return evidence;
}

function claimsFor(evidence) {
  return structuredClone(fixture.answer.claims).map((claim) => ({ ...claim, evidence_id: evidence.evidence_id }));
}

function terminalAnswerEvent({ runId, evidence, claims, seq }) {
  return {
    id: String(seq),
    event: "answer",
    json: {
      run_id: runId,
      status: "completed",
      intention: null,
      evidence: [evidence],
      claims,
      presentation_warnings: [],
      textual_facts: [],
      no_evidence_report: null,
      usage: null,
    },
  };
}

function twoSectionDocument() {
  return {
    version: 1,
    templateId: "libre",
    title: "Documento libre",
    sections: [
      { sectionId: "s1", title: "Sección Uno", content: structuredClone(EMPTY_DOCUMENT_JSON) },
      { sectionId: "s2", title: "Sección Dos", content: structuredClone(EMPTY_DOCUMENT_JSON) },
    ],
  };
}

function citationNodes(json) {
  return (json?.content ?? []).filter((node) => node.type === "evidenceCitation");
}

async function flush() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

function Harness({ agentClient, streamRunner, onReady }) {
  const [documentModel, setDocumentModel] = useState(() => twoSectionDocument());
  const documentSectionsRef = useRef(null);
  const historyLifecycleRef = useRef(() => {});
  const stableOnLifecycle = useCallback((event) => historyLifecycleRef.current(event), []);

  const agentRun = useAgentRun({
    baseUrl: "http://x",
    consentGranted: true,
    agentClient,
    streamRunner,
    onLifecycle: stableOnLifecycle,
  });
  const history = useRunHistory({
    baseUrl: "http://x",
    agentClient,
    startRun: agentRun.start,
    resumeRunTransport: agentRun.resume,
  });

  useEffect(() => {
    historyLifecycleRef.current = history.handleAgentLifecycle;
  }, [history.handleAgentLifecycle]);

  const handleSectionChange = useCallback((sectionId, json) => {
    setDocumentModel((previous) => ({
      ...previous,
      sections: previous.sections.map((section) => (section.sectionId === sectionId ? { ...section, content: json } : section)),
    }));
  }, []);

  // Réplica mínima de `handleInsertEvidence` de `pages/app.js`: la sección
  // de destino sale de `agentRun.state.sectionId`, nunca de un estado
  // aparte de este componente.
  const insertEvidence = useCallback(
    (payload) => {
      const sectionId = agentRun.state.sectionId;
      if (!sectionId) return false;
      const inserted = documentSectionsRef.current?.insertEvidenceCitation(sectionId, payload) ?? false;
      if (inserted) {
        const updated = documentSectionsRef.current.getSectionJSON(sectionId);
        if (updated) handleSectionChange(sectionId, updated);
      }
      return inserted;
    },
    [agentRun.state.sectionId, handleSectionChange]
  );

  onReady?.({
    agentRun,
    history,
    insertEvidence,
    getSectionJSON: (sectionId) => documentSectionsRef.current?.getSectionJSON(sectionId) ?? null,
  });

  return (
    <div className="cdt-v2">
      <DocumentSections
        ref={documentSectionsRef}
        document={documentModel}
        onSectionChange={handleSectionChange}
        onInvestigateSection={() => {}}
      />
    </div>
  );
}

describe("Asociación runId→sectionId con dos secciones (F5-03A-R1)", () => {
  it("A desde s1, B desde s2, reanudar A, insertar → la evidencia de A aparece EXCLUSIVAMENTE en s1", async () => {
    const evidenceA = evidenceFor("corrida-A");
    const evidenceB = evidenceFor("corrida-B");

    const startRunImpl = vi
      .fn()
      .mockResolvedValueOnce({ runId: "run-A", token: "token-A", tokenExpiresAt: null, streamUrl: "/a" })
      .mockResolvedValueOnce({ runId: "run-B", token: "token-B", tokenExpiresAt: null, streamUrl: "/b" });

    const getRunImpl = vi.fn(async ({ runId }) => ({
      run_id: runId,
      status: "completed",
      answer: {
        evidence: [runId === "run-A" ? evidenceA : evidenceB],
        claims: runId === "run-A" ? claimsFor(evidenceA) : claimsFor(evidenceB),
        presentation_warnings: [],
        textual_facts: [],
        usage: null,
      },
    }));

    const client = { startRun: startRunImpl, getRun: getRunImpl, deleteRun: vi.fn(async () => true) };

    const streamRunner = vi
      .fn()
      .mockImplementationOnce(async () => ({
        finalStatus: "terminal",
        terminalEvent: terminalAnswerEvent({ runId: "run-A", evidence: evidenceA, claims: claimsFor(evidenceA), seq: 1 }),
        lastEventId: 1,
        reconciliation: null,
      }))
      .mockImplementationOnce(async () => ({
        finalStatus: "terminal",
        terminalEvent: terminalAnswerEvent({ runId: "run-B", evidence: evidenceB, claims: claimsFor(evidenceB), seq: 1 }),
        lastEventId: 1,
        reconciliation: null,
      }));

    let api;
    render(<Harness agentClient={client} streamRunner={streamRunner} onReady={(r) => { api = r; }} />);
    await flush();

    // 1. Corrida A desde s1.
    await act(async () => {
      await api.agentRun.start({ question: "¿Pregunta A con longitud suficiente?", sectionId: "s1" });
    });
    await waitFor(() => expect(api.agentRun.state.runId).toBe("run-A"));
    expect(api.agentRun.state.sectionId).toBe("s1");
    // `history.runs` se actualiza un tick de React después de `agentRun.state`
    // (el listener de `onLifecycle` vive en un `useEffect` de `useAgentRun`
    // que reacciona AL cambio de estado ya confirmado). Esperar el registro
    // público con sectionId "s1" antes de continuar evita una condición de
    // carrera en la prueba misma — no del código bajo prueba.
    await waitFor(() => expect(api.history.runs.find((r) => r.runId === "run-A")?.sectionId).toBe("s1"));

    // 2. Corrida B desde s2 — sobrescribe el estado presentado.
    await act(async () => {
      await api.agentRun.start({ question: "¿Pregunta B con longitud suficiente?", sectionId: "s2" });
    });
    await waitFor(() => expect(api.agentRun.state.runId).toBe("run-B"));
    expect(api.agentRun.state.sectionId).toBe("s2");
    await waitFor(() => expect(api.history.runs.find((r) => r.runId === "run-B")?.sectionId).toBe("s2"));

    // 3. Reanudar A a través del mismo camino que usa la UI real
    // (`history.resumeRun`, que lee token y sectionId de su propio store).
    await act(async () => {
      api.history.resumeRun("run-A");
    });
    await waitFor(() => expect(api.agentRun.state.runId).toBe("run-A"));
    expect(api.agentRun.state.sectionId).toBe("s1");
    expect(api.agentRun.state.evidence[0].evidence_id).toBe(evidenceA.evidence_id);

    // 4. Insertar la evidencia de la corrida ACTUALMENTE presentada (A).
    let inserted;
    act(() => {
      inserted = api.insertEvidence({
        runId: api.agentRun.state.runId,
        evidence: api.agentRun.state.evidence[0],
        claims: api.agentRun.state.claims,
      });
    });
    expect(inserted).toBe(true);

    // 5. Exclusivamente en s1, nunca en s2.
    await waitFor(() => expect(citationNodes(api.getSectionJSON("s1"))).toHaveLength(1));
    expect(citationNodes(api.getSectionJSON("s1"))[0].attrs.datasetId).toBe(evidenceA.dataset_id);
    expect(citationNodes(api.getSectionJSON("s2"))).toHaveLength(0);
  });

  it("rerun(runId) desde el historial también conserva sectionId — la evidencia de la corrida reejecutada va a la sección original", async () => {
    const evidence = evidenceFor("rerun");
    const startRunImpl = vi
      .fn()
      .mockResolvedValueOnce({ runId: "run-orig", token: "token-orig", tokenExpiresAt: null, streamUrl: "/x" })
      .mockResolvedValueOnce({ runId: "run-nuevo", token: "token-nuevo", tokenExpiresAt: null, streamUrl: "/y" });

    const client = { startRun: startRunImpl, getRun: vi.fn(), deleteRun: vi.fn(async () => true) };
    const streamRunner = vi.fn().mockImplementation(async ({ runId }) => ({
      finalStatus: "terminal",
      terminalEvent: terminalAnswerEvent({ runId, evidence, claims: claimsFor(evidence), seq: 1 }),
      lastEventId: 1,
      reconciliation: null,
    }));

    let api;
    render(<Harness agentClient={client} streamRunner={streamRunner} onReady={(r) => { api = r; }} />);
    await flush();

    await act(async () => {
      await api.agentRun.start({ question: "¿Pregunta original con longitud suficiente?", sectionId: "s2" });
    });
    await waitFor(() => expect(api.agentRun.state.runId).toBe("run-orig"));
    await waitFor(() => expect(api.history.runs.find((r) => r.runId === "run-orig")?.sectionId).toBe("s2"));

    await act(async () => {
      api.history.rerun("run-orig");
      await Promise.resolve();
    });
    await waitFor(() => expect(api.agentRun.state.runId).toBe("run-nuevo"));
    expect(api.agentRun.state.sectionId).toBe("s2");
  });

  it("pregunta libre (sin sección de origen explícita): sectionId ausente/null nunca se inventa", async () => {
    const evidence = evidenceFor("libre");
    const client = {
      startRun: vi.fn(async () => ({ runId: "run-libre", token: "token-libre", tokenExpiresAt: null, streamUrl: "/z" })),
      getRun: vi.fn(),
      deleteRun: vi.fn(async () => true),
    };
    const streamRunner = vi.fn(async () => ({
      finalStatus: "terminal",
      terminalEvent: terminalAnswerEvent({ runId: "run-libre", evidence, claims: claimsFor(evidence), seq: 1 }),
      lastEventId: 1,
      reconciliation: null,
    }));

    let api;
    render(<Harness agentClient={client} streamRunner={streamRunner} onReady={(r) => { api = r; }} />);
    await flush();

    await act(async () => {
      await api.agentRun.start({ question: "¿Pregunta libre con longitud suficiente?" });
    });
    await waitFor(() => expect(api.agentRun.state.runId).toBe("run-libre"));
    expect(api.agentRun.state.sectionId).toBeNull();

    let inserted;
    act(() => {
      inserted = api.insertEvidence({ runId: "run-libre", evidence, claims: claimsFor(evidence) });
    });
    // Sin sección de destino: falla cerrado, nunca inserta "en algún lado".
    expect(inserted).toBe(false);
  });

  it("sección de origen inexistente (registrada pero ya no montada) falla cerrado, nunca inserta en otra", async () => {
    const evidence = evidenceFor("huerfana");
    const client = {
      startRun: vi.fn(async () => ({ runId: "run-huerfano", token: "token-huerfano", tokenExpiresAt: null, streamUrl: "/w" })),
      getRun: vi.fn(),
      deleteRun: vi.fn(async () => true),
    };
    const streamRunner = vi.fn(async () => ({
      finalStatus: "terminal",
      terminalEvent: terminalAnswerEvent({ runId: "run-huerfano", evidence, claims: claimsFor(evidence), seq: 1 }),
      lastEventId: 1,
      reconciliation: null,
    }));

    let api;
    render(<Harness agentClient={client} streamRunner={streamRunner} onReady={(r) => { api = r; }} />);
    await flush();

    await act(async () => {
      await api.agentRun.start({ question: "¿Pregunta huérfana con longitud suficiente?", sectionId: "seccion-eliminada" });
    });
    await waitFor(() => expect(api.agentRun.state.runId).toBe("run-huerfano"));
    expect(api.agentRun.state.sectionId).toBe("seccion-eliminada");

    let inserted;
    act(() => {
      inserted = api.insertEvidence({ runId: "run-huerfano", evidence, claims: claimsFor(evidence) });
    });
    expect(inserted).toBe(false);
    expect(citationNodes(api.getSectionJSON("s1"))).toHaveLength(0);
    expect(citationNodes(api.getSectionJSON("s2"))).toHaveLength(0);
  });
});
