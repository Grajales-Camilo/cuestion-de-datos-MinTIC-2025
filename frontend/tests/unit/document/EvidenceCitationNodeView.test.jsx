import { createRef } from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { DocumentEditor } from "../../../components/canvas/editor";
import { validateEvidenceCitationDocumentJson } from "../../../lib/document/evidenceCitation";

const fixture = JSON.parse(
  readFileSync(path.resolve(process.cwd(), "tests/fixtures/completed-with-claims.json"), "utf8"),
);

function fixturePayload(overrides = {}) {
  const evidence = structuredClone(fixture.answer.evidence[0]);
  const payload = {
    runId: fixture.run_id,
    evidence,
    claims: structuredClone(fixture.answer.claims),
    citationId: "citation-node-view-001",
    insertedAt: "2026-07-28T15:00:00.000Z",
  };
  return Object.assign(payload, overrides);
}

function syntheticNotRecommendedPayload() {
  const payload = fixturePayload({
    runId: "run-sintetico-rf404-inline",
    citationId: "citation-sintetica-rf404-inline",
  });
  payload.evidence.quality.classification = "no_recomendada";
  payload.evidence.quality.score_total = 42;
  payload.evidence.quality.warnings_user = ["La actualización disponible requiere cautela."];
  return payload;
}

async function insertPayload(payload) {
  const ref = createRef();
  const result = render(<DocumentEditor ref={ref} />);
  await screen.findByRole("textbox", { name: "Documento de trabajo" });
  await waitFor(() => expect(ref.current).not.toBeNull());
  act(() => {
    expect(ref.current.insertEvidenceCitation(payload)).toBe(true);
  });
  return { ref, ...result };
}

describe("EvidenceCitationNodeView — F5-02", () => {
  it("representa el nodo atómico con nombre accesible y los campos RF-103", async () => {
    const { ref } = await insertPayload(fixturePayload());
    const citation = await screen.findByRole("group", { name: /Cita de evidencia:/ });

    expect(citation).toHaveTextContent(fixture.answer.evidence[0].citation.dataset_name);
    expect(citation).toHaveTextContent(fixture.answer.evidence[0].citation.publisher);
    expect(citation).toHaveTextContent("Consulta de origen");
    expect(citation).toHaveTextContent("Fecha de consulta");
    expect(citation).toHaveTextContent("Actualización del portal");
    expect(citation).toHaveTextContent("Calidad alta");
    expect(citation).toHaveTextContent("2.368.705.607");
    expect(citation).toHaveAttribute("contenteditable", "false");
    expect(ref.current.getJSON().content.find((node) => node.type === "evidenceCitation")).toBeTruthy();
  });

  it("no expone atributos persistidos completos ni campos sensibles", async () => {
    const payload = fixturePayload();
    payload.runAccessToken = "TOKEN_SENSIBLE_NODEVIEW";
    payload.Authorization = "Bearer AUTH_SENSIBLE_NODEVIEW";
    payload.evidence.message_dev = "DETALLE_INTERNO_NODEVIEW";
    payload.evidence.raw_payload = { secreto: "PAYLOAD_INTERNO_NODEVIEW" };

    const { container, ref } = await insertPayload(payload);
    const html = container.innerHTML;
    for (const forbidden of [
      "TOKEN_SENSIBLE_NODEVIEW",
      "AUTH_SENSIBLE_NODEVIEW",
      "DETALLE_INTERNO_NODEVIEW",
      "PAYLOAD_INTERNO_NODEVIEW",
      "sourceHash",
      "citationId",
      "runId",
    ]) {
      expect(html).not.toContain(forbidden);
    }
    expect(JSON.stringify(ref.current.getJSON())).not.toContain("TOKEN_SENSIBLE_NODEVIEW");
  });

  it("muestra cadenas con HTML como texto y nunca crea elementos arbitrarios", async () => {
    const payload = fixturePayload();
    const hostile = '<img src="x" onerror="alert(1)"><script>globalThis.__xss=true</script>';
    payload.evidence.dataset_name = hostile;
    payload.evidence.citation.dataset_name = hostile;

    const { container } = await insertPayload(payload);
    expect(screen.getByText(hostile)).toBeInTheDocument();
    expect(container.querySelector("img, script, iframe")).toBeNull();
    expect(globalThis.__xss).toBeUndefined();
  });

  it("solo crea enlace para la sourceUrl HTTPS ya validada", async () => {
    await insertPayload(fixturePayload());
    const link = screen.getByRole("link", { name: /Abrir fuente original/ });
    expect(link).toHaveAttribute("href", fixture.answer.evidence[0].citation.source_url);
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("round-trip JSON conserva warningRequired:true y la advertencia visible", async () => {
    const first = await insertPayload(syntheticNotRecommendedPayload());
    expect(screen.getByText("Evidencia no recomendada: úsala con cautela.")).toBeVisible();
    const json = first.ref.current.getJSON();
    const citation = json.content.find((node) => node.type === "evidenceCitation");
    expect(citation.attrs.warningRequired).toBe(true);
    expect(validateEvidenceCitationDocumentJson(json)).toEqual({ ok: true });

    first.unmount();
    render(<DocumentEditor initialContent={json} />);
    expect(await screen.findByText("Evidencia no recomendada: úsala con cautela.")).toBeVisible();
  });
});
