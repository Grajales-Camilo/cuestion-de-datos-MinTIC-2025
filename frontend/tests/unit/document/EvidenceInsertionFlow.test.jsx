import { createRef, useRef, useState } from "react";
import { readFileSync } from "node:fs";
import path from "node:path";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { DocumentEditor } from "../../../components/canvas/editor";
import { EvidenceCard } from "../../../components/evidence/EvidenceCard";
import { LiveRegion } from "../../../components/ui/LiveRegion";

const fixture = JSON.parse(
  readFileSync(path.resolve(process.cwd(), "tests/fixtures/completed-with-claims.json"), "utf8"),
);

function fixtureEvidence() {
  return structuredClone(fixture.answer.evidence[0]);
}

function fixtureClaims() {
  return structuredClone(fixture.answer.claims);
}

function InsertionHarness({ evidence, claims, editorRef: externalEditorRef }) {
  const localEditorRef = useRef(null);
  const editorRef = externalEditorRef ?? localEditorRef;
  const [feedback, setFeedback] = useState("");

  function handleInsert({ evidence: selectedEvidence, claims: allClaims }) {
    const inserted =
      editorRef.current?.insertEvidenceCitation({
        runId: fixture.run_id,
        evidence: selectedEvidence,
        claims: allClaims,
      }) ?? false;
    setFeedback(
      inserted
        ? "La evidencia se insertó en el documento."
        : "No pudimos insertar la evidencia. El documento no cambió.",
    );
    return inserted;
  }

  return (
    <div className="cdt-v2">
      <LiveRegion message={feedback} visuallyHidden={false} />
      <DocumentEditor ref={editorRef} />
      <EvidenceCard
        evidence={evidence}
        claims={claims}
        presentationWarnings={[]}
        onInsertEvidence={handleInsert}
      />
    </div>
  );
}

function citationNodes(editorRef) {
  return editorRef.current.getJSON().content.filter((node) => node.type === "evidenceCitation");
}

describe("EvidenceCard → Tiptap → JSON — F5-02", () => {
  it("no muestra una acción muerta cuando falta callback funcional", () => {
    render(
      <EvidenceCard
        evidence={fixtureEvidence()}
        claims={fixtureClaims()}
        presentationWarnings={[]}
      />,
    );
    expect(screen.queryByRole("button", { name: "Insertar en el documento" })).not.toBeInTheDocument();
  });

  it("EvidenceCard entrega evidencia y la lista completa de claims al callback", async () => {
    const user = userEvent.setup();
    const callback = vi.fn(() => true);
    const claims = fixtureClaims();
    claims.push({
      claim_id: "claim-ajeno",
      evidence_id: "evidence-ajena",
      label: "No debe persistir",
      display_value: "999",
      unit: null,
      source_hash: "sha256:ajeno",
    });
    render(
      <EvidenceCard
        evidence={fixtureEvidence()}
        claims={claims}
        presentationWarnings={[]}
        onInsertEvidence={callback}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Insertar en el documento" }));
    expect(callback).toHaveBeenCalledTimes(1);
    expect(callback.mock.calls[0][0].claims).toEqual(claims);
  });

  it("inserta una cita con los seis campos RF-103 y solo los claims permitidos", async () => {
    const user = userEvent.setup();
    const editorRef = createRef();
    const claims = fixtureClaims();
    claims.push({
      claim_id: "claim-ajeno",
      evidence_id: "evidence-ajena",
      label: "No debe persistir",
      display_value: "999",
      unit: null,
      source_hash: "sha256:ajeno",
    });
    render(<InsertionHarness evidence={fixtureEvidence()} claims={claims} editorRef={editorRef} />);
    await screen.findByRole("textbox", { name: "Documento de trabajo" });

    await user.click(screen.getByRole("button", { name: "Insertar en el documento" }));
    await waitFor(() => expect(citationNodes(editorRef)).toHaveLength(1));

    const attrs = citationNodes(editorRef)[0].attrs;
    expect(attrs).toMatchObject({
      runId: fixture.run_id,
      datasetId: fixture.answer.evidence[0].citation.dataset_id,
      datasetName: fixture.answer.evidence[0].citation.dataset_name,
      publisher: fixture.answer.evidence[0].citation.publisher,
      soqlQuery: fixture.answer.evidence[0].citation.soql_query,
      executedAt: fixture.answer.evidence[0].citation.executed_at,
      sourceUrl: fixture.answer.evidence[0].citation.source_url,
    });
    expect(attrs.claims.map((claim) => claim.claimId)).toEqual(
      fixture.answer.claims.map((claim) => claim.claim_id),
    );
    expect(JSON.stringify(attrs)).not.toContain("claim-ajeno");
    expect(screen.getByText("La evidencia se insertó en el documento.")).toBeInTheDocument();
  });

  it("un error de inserción conserva el documento y produce feedback seguro", async () => {
    const user = userEvent.setup();
    const editorRef = createRef();
    const evidence = fixtureEvidence();
    delete evidence.source_url;
    delete evidence.citation.source_url;
    evidence.message_dev = "INTERNAL_DATABASE_TRACE";
    render(<InsertionHarness evidence={evidence} claims={fixtureClaims()} editorRef={editorRef} />);
    await screen.findByRole("textbox", { name: "Documento de trabajo" });
    const before = editorRef.current.getJSON();

    await user.click(screen.getByRole("button", { name: "Insertar en el documento" }));
    await waitFor(() =>
      expect(
        screen.getByText("No pudimos insertar la evidencia. El documento no cambió."),
      ).toBeInTheDocument(),
    );
    expect(editorRef.current.getJSON()).toEqual(before);
    expect(document.body.textContent).not.toContain("INTERNAL_DATABASE_TRACE");
  });

  it("no_recomendada abre confirmación; cancelar no cambia el documento", async () => {
    const user = userEvent.setup();
    const editorRef = createRef();
    const evidence = fixtureEvidence();
    evidence.quality.classification = "no_recomendada";
    evidence.quality.warnings_user = ["Advertencia sintética destinada al usuario."];
    render(<InsertionHarness evidence={evidence} claims={fixtureClaims()} editorRef={editorRef} />);
    await screen.findByRole("textbox", { name: "Documento de trabajo" });
    const before = editorRef.current.getJSON();

    await user.click(screen.getByRole("button", { name: "Insertar en el documento" }));
    const dialog = screen.getByRole("dialog", { name: "Insertar evidencia no recomendada" });
    expect(dialog).toBeVisible();
    expect(dialog).toHaveTextContent("puede usarse, pero requiere cautela");
    expect(dialog).toHaveTextContent("Advertencia sintética destinada al usuario.");
    expect(editorRef.current.getJSON()).toEqual(before);

    await user.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(screen.queryByRole("dialog", { name: "Insertar evidencia no recomendada" })).not.toBeInTheDocument();
    expect(editorRef.current.getJSON()).toEqual(before);
  });

  it("confirmar no_recomendada persiste warningRequired:true y muestra la advertencia", async () => {
    const user = userEvent.setup();
    const editorRef = createRef();
    const evidence = fixtureEvidence();
    evidence.quality.classification = "no_recomendada";
    evidence.quality.warnings_user = ["Advertencia sintética destinada al usuario."];
    render(<InsertionHarness evidence={evidence} claims={fixtureClaims()} editorRef={editorRef} />);
    await screen.findByRole("textbox", { name: "Documento de trabajo" });

    await user.click(screen.getByRole("button", { name: "Insertar en el documento" }));
    await user.click(screen.getByRole("button", { name: "Insertar con advertencia" }));
    await waitFor(() => expect(citationNodes(editorRef)).toHaveLength(1));

    expect(citationNodes(editorRef)[0].attrs.warningRequired).toBe(true);
    expect(screen.getByText("Evidencia no recomendada: úsala con cautela.")).toBeVisible();
  });

  it("el documento serializado no contiene token ni Authorization", async () => {
    const user = userEvent.setup();
    const editorRef = createRef();
    const evidence = fixtureEvidence();
    const claims = fixtureClaims();
    evidence.run_access_token = "cdt_rt_TOKEN_DOCUMENTO";
    evidence.Authorization = "Bearer AUTH_DOCUMENTO";
    claims[0].Authorization = "Bearer AUTH_CLAIM";
    render(<InsertionHarness evidence={evidence} claims={claims} editorRef={editorRef} />);
    await screen.findByRole("textbox", { name: "Documento de trabajo" });

    await user.click(screen.getByRole("button", { name: "Insertar en el documento" }));
    await waitFor(() => expect(citationNodes(editorRef)).toHaveLength(1));
    const serialized = JSON.stringify(editorRef.current.getJSON());
    expect(serialized).not.toContain("cdt_rt_TOKEN_DOCUMENTO");
    expect(serialized).not.toContain("AUTH_DOCUMENTO");
    expect(serialized).not.toContain("AUTH_CLAIM");
    expect(serialized).not.toContain("Authorization");
  });
});
