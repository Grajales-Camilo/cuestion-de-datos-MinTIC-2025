import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { EvidenceCard } from "../../../components/evidence/EvidenceCard";
import { EvidenceNarrative } from "../../../components/evidence/EvidenceNarrative";
import { ClaimList } from "../../../components/evidence/ClaimList";
import { PresentationWarnings } from "../../../components/evidence/PresentationWarnings";
import { EvidenceTable } from "../../../components/evidence/EvidenceTable";
import { EvidenceChart } from "../../../components/evidence/EvidenceChart";
import { QualityBadge } from "../../../components/evidence/QualityBadge";
import { QualityDetails } from "../../../components/evidence/QualityDetails";
import { CitationBlock } from "../../../components/evidence/CitationBlock";
import { DownloadCsvButton } from "../../../components/evidence/DownloadCsvButton";
import { CopyCitationButton } from "../../../components/evidence/CopyCitationButton";
import { TerminalPanel } from "../../../components/agent/TerminalPanel";
import { RUN_STATUS, createInitialRunState } from "../../../lib/agent/runStates";

import fixture from "../../fixtures/completed-with-claims.json";

/**
 * Doble sintético mínimo de `presentation_warnings`, usado SOLO en este
 * archivo (`frontend/tests/fixtures/README.md`: cero corridas reales
 * producen todavía este campo no vacío — excepción registrada, T-617C
 * pendiente). Nunca se guarda en `tests/fixtures/`, nunca se presenta como
 * fixture real, nunca se usa en las capturas de F4-02.
 */
const SYNTHETIC_PRESENTATION_WARNING = Object.freeze({
  claim_id: "synthetic-claim-warned",
  code: "AMBIGUOUS_LABEL",
  message_user: "No se pudo asociar esta cifra con una etiqueta verificable.",
});

const realEvidence = fixture.answer.evidence[0];
const realClaims = fixture.answer.claims;

describe("EvidenceNarrative", () => {
  it("resalta display_value literal con React, nunca HTML, y no toca el resto del texto", () => {
    render(
      <EvidenceNarrative
        narrative="Nueca: 2.368.705.607. Además, Nueca: 3.375.205.607."
        claims={realClaims}
      />
    );
    const marks = screen.getAllByText((_content, el) => el.tagName === "MARK");
    expect(marks.map((m) => m.textContent)).toEqual(["2.368.705.607", "3.375.205.607"]);
    expect(marks[0]).toHaveAttribute("aria-label", expect.stringContaining("Nueca"));
  });

  it("sin narrativa, no inventa una", () => {
    const { container } = render(<EvidenceNarrative narrative={null} claims={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("narrativa sin coincidencias con claims se muestra tal cual, sin marcas", () => {
    render(<EvidenceNarrative narrative="Texto sin cifras que coincidan." claims={realClaims} />);
    expect(screen.getByText("Texto sin cifras que coincidan.")).toBeInTheDocument();
    expect(document.querySelector("mark")).toBeNull();
  });
});

describe("ClaimList — etiquetas verified/ambiguous", () => {
  it("label_status='verified' muestra el label real", () => {
    render(<ClaimList claims={[{ claim_id: "c1", label: "Nueca", label_status: "verified", display_value: "764" }]} />);
    expect(screen.getByText("Nueca")).toBeInTheDocument();
    expect(screen.getByText("764")).toBeInTheDocument();
  });

  it("label_status='ambiguous' o ausente muestra 'Etiqueta no confirmada', nunca inventa desde el valor/alias", () => {
    render(
      <ClaimList
        claims={[
          { claim_id: "c1", label: null, label_status: "ambiguous", display_value: "42" },
          { claim_id: "c2", display_value: "7" },
        ]}
      />
    );
    expect(screen.getAllByText("Etiqueta no confirmada")).toHaveLength(2);
  });

  it("muestra unit sin modificar display_value, y columnas/filas fuente", () => {
    render(
      <ClaimList
        claims={[
          {
            claim_id: "c1",
            label: "Promedio",
            label_status: "verified",
            display_value: "8,4",
            unit: "%",
            columns: ["matriculados", "desertores"],
            source_row_indexes: [0, 1],
          },
        ]}
      />
    );
    expect(screen.getByText("8,4")).toBeInTheDocument();
    expect(screen.getByText("%")).toBeInTheDocument();
    expect(screen.getByText(/matriculados, desertores/)).toBeInTheDocument();
    expect(screen.getByText(/0, 1/)).toBeInTheDocument();
  });

  it("sin claims, no renderiza nada", () => {
    const { container } = render(<ClaimList claims={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("PresentationWarnings — separado de quality.warnings_user", () => {
  it("muestra message_user, nunca code como mensaje principal (doble sintético, T-617C pendiente)", () => {
    render(<PresentationWarnings warnings={[SYNTHETIC_PRESENTATION_WARNING]} />);
    expect(screen.getByText(SYNTHETIC_PRESENTATION_WARNING.message_user)).toBeInTheDocument();
    expect(screen.queryByText("AMBIGUOUS_LABEL")).not.toBeInTheDocument();
  });

  it("sin advertencias, no renderiza un bloque vacío", () => {
    const { container } = render(<PresentationWarnings warnings={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("EvidenceTable — accesible, 10 filas, ver todas/ver menos, columna no resuelta", () => {
  function evidenceWithRows(count) {
    return {
      dataset_name: "Dataset de prueba",
      columns: ["dim_1"],
      soql_query: "SELECT nombre AS dim_1",
      rows: Array.from({ length: count }, (_, i) => ({ dim_1: `fila-${i}` })),
    };
  }

  it("muestra máximo 10 filas inicialmente y 'Ver todas' las revela; 'Ver menos' restaura", async () => {
    const user = userEvent.setup();
    render(<EvidenceTable evidence={evidenceWithRows(15)} claims={[]} />);

    expect(screen.getAllByRole("row")).toHaveLength(1 + 10); // encabezado + 10 filas
    await user.click(screen.getByRole("button", { name: /Ver todas/ }));
    expect(screen.getAllByRole("row")).toHaveLength(1 + 15);

    await user.click(screen.getByRole("button", { name: "Ver menos" }));
    expect(screen.getAllByRole("row")).toHaveLength(1 + 10);
  });

  it("sin exceso de filas, no muestra 'Ver todas'", () => {
    render(<EvidenceTable evidence={evidenceWithRows(3)} claims={[]} />);
    expect(screen.queryByRole("button", { name: /Ver todas/ })).not.toBeInTheDocument();
  });

  it("columna no resuelta muestra el alias crudo junto a 'Nombre técnico de la consulta', nunca inventa una etiqueta", () => {
    const evidence = {
      dataset_name: "Dataset",
      columns: ["dim_5"],
      soql_query: "SELECT case when a > 1 then a else b end AS dim_5",
      rows: [{ dim_5: "x" }],
    };
    render(<EvidenceTable evidence={evidence} claims={[]} />);
    expect(screen.getByText("dim_5")).toBeInTheDocument();
    expect(screen.getByText("Nombre técnico de la consulta")).toBeInTheDocument();
  });

  it("con el fixture real, ningún dim_N/metric_N queda visible en la superficie primaria", () => {
    render(<EvidenceTable evidence={realEvidence} claims={realClaims} />);
    const headers = screen.getAllByRole("columnheader").map((h) => h.textContent);
    for (const header of headers) {
      expect(header).not.toMatch(/^dim_\d+$/);
      expect(header).not.toMatch(/^metric_\d+$/);
    }
  });

  it("sin filas, no renderiza nada", () => {
    const { container } = render(<EvidenceTable evidence={{ columns: ["dim_1"], rows: [] }} claims={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});

/**
 * Doble sintético mínimo de evidencia elegible con 1 dimensión + 1 métrica
 * + ≥3 filas (F4-03): el ÚNICO fixture real disponible
 * (`completed-with-claims.json`) tiene 8 dimensiones y 0 métricas, así que
 * nunca puede ejercitar la rama en la que `EvidenceChart` SÍ renderiza.
 * Nunca se guarda en `tests/fixtures/`, nunca se presenta como captura o
 * evidencia real.
 */
const SYNTHETIC_CHARTABLE_EVIDENCE = Object.freeze({
  evidence_id: "synthetic-chart-evidence",
  dataset_name: "Dataset sintético",
  publisher: "Publicador sintético",
  columns: ["dim_1", "metric_sum_1"],
  soql_query: "SELECT municipio AS dim_1, sum(valor) AS metric_sum_1 GROUP BY municipio",
  quality: { eligibility_status: "eligible" },
  rows: [
    { dim_1: "Sonsón", metric_sum_1: 12.5 },
    { dim_1: "Rionegro", metric_sum_1: 30 },
    { dim_1: "Marinilla", metric_sum_1: 7 },
  ],
});

describe("EvidenceChart — RF-503 (F4-03)", () => {
  it("con el fixture real (8 dimensiones, 0 métricas), no renderiza nada — sin canvas ni contenedor vacío", () => {
    const { container } = render(<EvidenceChart evidence={realEvidence} claims={realClaims} />);
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("con el doble sintético (1 dimensión + 1 métrica + 3 filas), renderiza con nombre accesible: dataset, dimensión y métrica", () => {
    render(<EvidenceChart evidence={SYNTHETIC_CHARTABLE_EVIDENCE} claims={[]} />);
    const chart = screen.getByRole("img");
    expect(chart).toHaveAccessibleName(/Suma de Valor/);
    expect(chart).toHaveAccessibleName(/Municipio/);
    expect(chart).toHaveAccessibleName(/Dataset sintético/);
    // Nunca dim_N/metric_N crudos en el nombre accesible cuando hay etiqueta resuelta.
    expect(chart.getAttribute("aria-label")).not.toMatch(/dim_\d+|metric_\d+/);
  });

  it("sin evidencia, no renderiza nada", () => {
    const { container } = render(<EvidenceChart evidence={null} claims={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("QualityBadge — cinco clasificaciones, siempre icono + texto", () => {
  it.each([
    ["alta", "Calidad alta"],
    ["media", "Calidad media"],
    ["baja", "Calidad baja"],
    ["no_recomendada", "No recomendada"],
    ["desconocida", "Calidad no clasificada"],
    ["algo-no-reconocido", "Calidad no clasificada"], // fail-safe
  ])("classification=%s muestra '%s' con icono", (classification, expectedText) => {
    render(<QualityBadge classification={classification} />);
    const badge = screen.getByText(expectedText);
    expect(badge.closest("span").querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  });
});

describe("QualityBadge — contraste WCAG 2.2 AA real de las cinco combinaciones (F4-02-R1)", () => {
  // Mismos tokens hexadecimales que `tokens.css`; misma fórmula que
  // `tests/unit/ui/contrast.test.js` (relative luminance WCAG), aplicada
  // aquí a las parejas texto/fondo REALES que `QualityBadge` produce —
  // fondo `blue-100`/texto `blue-900` para "media" no es una pareja ya
  // cubierta por esa suite genérica de F1-01.
  const TOKENS = {
    "blue-900": "#001c40",
    "blue-700": "#002451",
    "blue-100": "#6b91c0",
    white: "#ffffff",
    "slate-600": "#475569",
    warning: "#b45309",
    error: "#b91c1c",
  };

  function hexToRgb(hex) {
    const value = hex.replace("#", "");
    return {
      r: parseInt(value.slice(0, 2), 16),
      g: parseInt(value.slice(2, 4), 16),
      b: parseInt(value.slice(4, 6), 16),
    };
  }
  function channelToLinear(channel) {
    const c = channel / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  }
  function relativeLuminance(hex) {
    const { r, g, b } = hexToRgb(hex);
    return 0.2126 * channelToLinear(r) + 0.7152 * channelToLinear(g) + 0.0722 * channelToLinear(b);
  }
  function contrastRatio(hexA, hexB) {
    const lumA = relativeLuminance(hexA);
    const lumB = relativeLuminance(hexB);
    const lighter = Math.max(lumA, lumB);
    const darker = Math.min(lumA, lumB);
    return (lighter + 0.05) / (darker + 0.05);
  }

  const AA_NORMAL_TEXT = 4.5;

  it.each([
    ["alta", "white", "blue-700"],
    ["media", "blue-900", "blue-100"],
    ["baja", "white", "warning"],
    ["no_recomendada", "white", "error"],
    ["desconocida", "white", "slate-600"],
  ])("%s: texto/%s sobre fondo/%s cumple ≥4.5:1", (_classification, textToken, bgToken) => {
    const ratio = contrastRatio(TOKENS[textToken], TOKENS[bgToken]);
    expect(ratio).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
  });
});

describe("QualityDetails — dimensiones, elegibilidad, datos ausentes sin ceros fabricados", () => {
  it("con quality vacío, muestra 'No disponible' en vez de inventar un 0", () => {
    render(<QualityDetails evidence={{ quality: {} }} />);
    // Las 4 dimensiones (solo texto propio "No disponible") + el puntaje
    // total (texto compuesto "Puntaje: No disponible", verificado aparte).
    expect(screen.getAllByText("No disponible").length).toBeGreaterThanOrEqual(4);
    expect(screen.getByText(/Puntaje:\s*No disponible/)).toBeInTheDocument();
    expect(screen.queryByText("0/100")).not.toBeInTheDocument();
    expect(screen.queryByText(/Puntaje:\s*0\/100/)).not.toBeInTheDocument();
  });

  it("con el fixture real, muestra las 4 dimensiones con su puntaje y la elegibilidad traducida", () => {
    render(<QualityDetails evidence={realEvidence} />);
    // "Esquema"/etc. aparecen dos veces (superficie primaria + Disclosure
    // técnico cerrado, que sigue en el DOM aunque no visible): basta con
    // que exista al menos una aparición.
    expect(screen.getAllByText("Esquema").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Completitud").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Temporalidad").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Trazabilidad").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/Elegible para sustentar la respuesta/)).toBeInTheDocument();
    expect(screen.getByText(/91\/100/)).toBeInTheDocument();
  });

  it("eligibility_reasons se traducen mediante catálogo seguro; un código desconocido usa el mensaje genérico", () => {
    const evidence = {
      quality: {
        score_total: 50,
        classification: "media",
        eligibility_status: "diagnostic_only",
        eligibility_reasons: ["publisher_unknown", "codigo-inventado-no-catalogado"],
        dimensions: {},
      },
    };
    render(<QualityDetails evidence={evidence} />);
    expect(screen.getByText(/No fue posible verificar el publicador oficial/)).toBeInTheDocument();
    expect(screen.getByText("Restricción de elegibilidad no reconocida.")).toBeInTheDocument();
    expect(screen.queryByText("codigo-inventado-no-catalogado")).not.toBeInTheDocument(); // solo en el Disclosure técnico
  });

  it("nombres de check crudos solo aparecen dentro del Disclosure técnico (cerrado por defecto, no visible)", () => {
    render(<QualityDetails evidence={realEvidence} />);
    const rawCheck = screen.getByText(/schema\.columns_present/);
    expect(rawCheck).not.toBeVisible(); // dentro del panel `hidden` del Disclosure
    const button = screen.getByRole("button", { name: /Ver detalle técnico/ });
    expect(button).toHaveAttribute("aria-expanded", "false");
  });
});

describe("CitationBlock — cita completa", () => {
  it("incluye dataset, publicador, fecha de ejecución, URL (enlace seguro), actualización y corte", () => {
    render(<CitationBlock evidence={realEvidence} />);
    expect(screen.getByText(realEvidence.dataset_name)).toBeInTheDocument();
    expect(screen.getByText(realEvidence.publisher)).toBeInTheDocument();
    const link = screen.getByRole("link", { name: realEvidence.source_url });
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(link).toHaveAttribute("target", "_blank");
    expect(screen.getByText(/Corte estadístico desconocido|Corte estadístico:/)).toBeInTheDocument();
  });

  it("la consulta SoQL vive dentro de un Disclosure técnico, no en la superficie primaria", () => {
    render(<CitationBlock evidence={realEvidence} />);
    expect(screen.getByText(realEvidence.soql_query)).not.toBeVisible(); // panel `hidden` cerrado por defecto
    expect(screen.getByRole("button", { name: "Ver consulta SoQL" })).toBeInTheDocument();
  });
});

describe("CitationBlock — URL segura (F4-02-R1)", () => {
  it("https:// absoluta crea un enlace con rel/target seguros", () => {
    render(<CitationBlock evidence={{ ...realEvidence, source_url: "https://www.datos.gov.co/resource/abcd.json" }} />);
    const link = screen.getByRole("link", { name: "https://www.datos.gov.co/resource/abcd.json" });
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(link).toHaveAttribute("target", "_blank");
  });

  it.each([
    ["javascript:", "javascript:alert(1)"],
    ["data:", "data:text/html,<script>alert(1)</script>"],
    ["protocol-relative //", "//evil.example.com/steal"],
    ["ruta relativa", "/ruta/local"],
    ["texto arbitrario", "no es una url"],
    ["cadena vacía", ""],
    ["ausente", undefined],
  ])("%s NUNCA crea un elemento <a>; muestra 'URL no disponible' como texto", (_label, unsafeUrl) => {
    const { container } = render(<CitationBlock evidence={{ ...realEvidence, source_url: unsafeUrl }} />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.getByText("URL no disponible")).toBeInTheDocument();
    expect(container.innerHTML).not.toMatch(/href\s*=\s*["'](javascript:|data:|vbscript:|file:)/i);
  });

  it("file: y vbscript: tampoco crean enlace", () => {
    for (const unsafeUrl of ["file:///etc/passwd", "vbscript:msgbox(1)"]) {
      const { container, unmount } = render(<CitationBlock evidence={{ ...realEvidence, source_url: unsafeUrl }} />);
      expect(screen.queryByRole("link")).not.toBeInTheDocument();
      expect(container.innerHTML).not.toContain(unsafeUrl);
      unmount();
    }
  });

  it("F4-03: https:// con credenciales embebidas (usuario:clave@) se rechaza, aunque el protocolo sea seguro", () => {
    for (const unsafeUrl of [
      "https://usuario:clave@datos.gov.co/resource/abcd.json",
      "https://solo-usuario@datos.gov.co/resource/abcd.json",
    ]) {
      const { container, unmount } = render(<CitationBlock evidence={{ ...realEvidence, source_url: unsafeUrl }} />);
      expect(screen.queryByRole("link")).not.toBeInTheDocument();
      expect(screen.getByText("URL no disponible")).toBeInTheDocument();
      expect(container.innerHTML).not.toContain("usuario");
      expect(container.innerHTML).not.toContain("clave");
      unmount();
    }
  });
});

describe("DownloadCsvButton — CSV con BOM y revocación de object URL", () => {
  let createObjectURLSpy;
  let revokeObjectURLSpy;

  beforeEach(() => {
    createObjectURLSpy = vi.fn(() => "blob:mock-url");
    revokeObjectURLSpy = vi.fn();
    window.URL.createObjectURL = createObjectURLSpy;
    window.URL.revokeObjectURL = revokeObjectURLSpy;
  });

  it("crea, descarga y revoca el object URL exactamente una vez", async () => {
    const user = userEvent.setup();
    render(<DownloadCsvButton evidence={realEvidence} claims={realClaims} />);
    await user.click(screen.getByRole("button", { name: "Descargar CSV" }));

    expect(createObjectURLSpy).toHaveBeenCalledTimes(1);
    const [blob] = createObjectURLSpy.mock.calls[0];
    expect(blob.type).toContain("text/csv");
    expect(revokeObjectURLSpy).toHaveBeenCalledWith("blob:mock-url");
  });

  it("sin evidencia, no renderiza nada", () => {
    const { container } = render(<DownloadCsvButton evidence={null} claims={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("CopyCitationButton — copiar cita: éxito y error", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("éxito: informa en español vía estado accesible, sin escribir HTML", async () => {
    // `userEvent.setup()` instala su propio stub de `navigator.clipboard`:
    // el mock propio debe definirse DESPUÉS de `setup()`, si no queda
    // silenciosamente reemplazado por el stub interno de user-event.
    const user = userEvent.setup();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });

    render(<CopyCitationButton evidence={realEvidence} />);
    await user.click(screen.getByRole("button", { name: "Copiar cita" }));

    expect(writeText).toHaveBeenCalledTimes(1);
    expect(typeof writeText.mock.calls[0][0]).toBe("string");
    expect(writeText.mock.calls[0][0]).not.toContain("<");
    expect(await screen.findByText("Cita copiada.")).toBeInTheDocument();
  });

  it("fallo: informa el error en español, sin lanzar", async () => {
    const user = userEvent.setup();
    const writeText = vi.fn().mockRejectedValue(new Error("denegado"));
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });

    render(<CopyCitationButton evidence={realEvidence} />);
    await user.click(screen.getByRole("button", { name: "Copiar cita" }));

    expect(await screen.findByText("No se pudo copiar la cita.")).toBeInTheDocument();
  });
});

describe("EvidenceCard — contrato de ensamblado", () => {
  it("sin evidencia válida, no renderiza una tarjeta vacía", () => {
    const { container } = render(<EvidenceCard evidence={null} claims={[]} presentationWarnings={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("con el fixture real, aparece la sección de evidencia con encabezado, calidad, claims, tabla y cita", () => {
    render(<EvidenceCard evidence={realEvidence} claims={realClaims} presentationWarnings={[]} />);
    expect(screen.getByRole("region", { name: /Evidencia:/ })).toBeInTheDocument();
    // El nombre del dataset aparece más de una vez (encabezado + caption de
    // la tabla + cita): basta con que exista al menos una aparición.
    expect(screen.getAllByText(realEvidence.dataset_name).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByRole("button", { name: "Descargar CSV" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copiar cita" })).toBeInTheDocument();
  });

  it("solo pasa a ClaimList/PresentationWarnings los claims/advertencias de ESTA evidencia", () => {
    const otherEvidenceClaim = { claim_id: "other", evidence_id: "otra-evidencia", display_value: "999", label_status: "verified", label: "Otro" };
    render(
      <EvidenceCard
        evidence={realEvidence}
        claims={[...realClaims, otherEvidenceClaim]}
        presentationWarnings={[]}
      />
    );
    expect(screen.queryByText("999")).not.toBeInTheDocument();
  });

  it("F4-03: con el fixture real, no incluye ninguna gráfica (no cumple 1 dim + 1 métrica) — sin sección vacía", () => {
    render(<EvidenceCard evidence={realEvidence} claims={realClaims} presentationWarnings={[]} />);
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("F4-03: con evidencia graficable, muestra la gráfica (RF-503) Y conserva la tabla como alternativa textual", () => {
    render(<EvidenceCard evidence={SYNTHETIC_CHARTABLE_EVIDENCE} claims={[]} presentationWarnings={[]} />);
    const chart = screen.getByRole("img");
    expect(chart).toHaveAccessibleName(/Suma de Valor/);
    // La tabla (alternativa textual autoritativa, pruebas.md §5) sigue
    // presente con los mismos valores crudos.
    expect(screen.getByRole("columnheader", { name: "Municipio" })).toBeInTheDocument();
    expect(screen.getByText("Sonsón")).toBeInTheDocument();
  });
});

describe("EvidenceCard — elegibilidad fail-closed (F4-02-R1, contracts/validacion-calidad.md §3.1)", () => {
  function evidenceWithEligibility(eligibilityStatus) {
    return {
      ...realEvidence,
      quality: eligibilityStatus === undefined ? {} : { ...realEvidence.quality, eligibility_status: eligibilityStatus },
    };
  }

  it("eligible: renderiza la tarjeta completa", () => {
    render(<EvidenceCard evidence={evidenceWithEligibility("eligible")} claims={realClaims} presentationWarnings={[]} />);
    expect(screen.getByRole("region", { name: /Evidencia:/ })).toBeInTheDocument();
  });

  it.each([
    ["blocked", "blocked"],
    ["diagnostic_only", "diagnostic_only"],
    ["ausente (quality={})", undefined],
    ["desconocido (valor no reconocido)", "algo-que-no-es-un-estado-valido"],
  ])("%s: no renderiza NADA — sin dataset, filas, claims, cita ni acciones en el DOM", (_label, eligibilityStatus) => {
    const { container } = render(
      <EvidenceCard evidence={evidenceWithEligibility(eligibilityStatus)} claims={realClaims} presentationWarnings={[]} />
    );
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByRole("region", { name: /Evidencia:/ })).not.toBeInTheDocument();
    expect(screen.queryByText(realEvidence.dataset_name)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Descargar CSV" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Copiar cita" })).not.toBeInTheDocument();
    // Ningún contenido bloqueado sobrevive en el HTML serializado.
    expect(container.innerHTML).toBe("");
    expect(container.innerHTML).not.toContain(realEvidence.dataset_name);
    expect(container.innerHTML).not.toContain(realEvidence.soql_query);
  });
});

describe("Integración por estado terminal (TerminalPanel)", () => {
  function stateWithEvidence(status, evidence) {
    const base = createInitialRunState({ question: "¿Pregunta de prueba?" });
    return { ...base, status, evidence, claims: [], presentationWarnings: [] };
  }

  it("completed: muestra la EvidenceCard del fixture real", () => {
    render(<TerminalPanel state={stateWithEvidence(RUN_STATUS.COMPLETED, [realEvidence])} onRestart={() => {}} />);
    expect(screen.getByRole("region", { name: /Evidencia:/ })).toBeInTheDocument();
  });

  it("interrupted: conserva y muestra evidencia parcial ELEGIBLE (doble sintético — el fixture real de interrupted no trae evidence)", () => {
    const partial = {
      dataset_name: "Parcial",
      publisher: "Pub",
      columns: ["dim_1"],
      soql_query: "SELECT nombre AS dim_1",
      rows: [{ dim_1: "x" }],
      quality: { eligibility_status: "eligible" },
    };
    render(<TerminalPanel state={stateWithEvidence(RUN_STATUS.INTERRUPTED, [partial])} onRestart={() => {}} />);
    expect(screen.getByRole("region", { name: /Evidencia: Parcial/ })).toBeInTheDocument();
  });

  it("no_evidence: sin evidencia, no aparece ninguna tarjeta (ni una tabla vacía)", () => {
    render(<TerminalPanel state={stateWithEvidence(RUN_STATUS.NO_EVIDENCE, [])} onRestart={() => {}} />);
    expect(screen.queryByRole("region", { name: /Evidencia:/ })).not.toBeInTheDocument();
  });
});

describe("TerminalPanel — notificación genérica de elegibilidad fail-closed (F4-02-R1)", () => {
  function stateWithEvidence(status, evidence) {
    const base = createInitialRunState({ question: "¿Pregunta de prueba?" });
    return { ...base, status, evidence, claims: [], presentationWarnings: [] };
  }

  const GENERIC_NOTICE = "Parte de la evidencia no puede mostrarse porque no cumple las reglas de elegibilidad.";
  const blockedEvidence = { ...realEvidence, quality: { ...realEvidence.quality, eligibility_status: "blocked" } };
  const eligibleEvidence = realEvidence;

  it("evidencia bloqueada: muestra la notificación genérica, sin código ni motivo ni metadato del contenido bloqueado", () => {
    render(<TerminalPanel state={stateWithEvidence(RUN_STATUS.COMPLETED, [blockedEvidence])} onRestart={() => {}} />);
    expect(screen.getByText(GENERIC_NOTICE)).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: /Evidencia:/ })).not.toBeInTheDocument();
    expect(screen.queryByText("blocked")).not.toBeInTheDocument();
    expect(screen.queryByText(realEvidence.dataset_name)).not.toBeInTheDocument();
    expect(screen.queryByText(realEvidence.soql_query)).not.toBeInTheDocument();
  });

  it("varias evidencias bloqueadas producen UNA sola notificación, nunca duplicada", () => {
    const anotherBlocked = { ...realEvidence, evidence_id: "otra-evidencia-bloqueada", quality: { eligibility_status: "diagnostic_only" } };
    render(
      <TerminalPanel
        state={stateWithEvidence(RUN_STATUS.COMPLETED, [blockedEvidence, anotherBlocked])}
        onRestart={() => {}}
      />
    );
    expect(screen.getAllByText(GENERIC_NOTICE)).toHaveLength(1);
  });

  it("mezcla de elegible + bloqueada: muestra la tarjeta elegible Y la notificación genérica, sin filtrar la bloqueada del todo", () => {
    const blockedOther = { ...realEvidence, evidence_id: "bloqueada-2", dataset_name: "Dataset bloqueado", quality: { eligibility_status: "blocked" } };
    render(
      <TerminalPanel
        state={stateWithEvidence(RUN_STATUS.COMPLETED, [eligibleEvidence, blockedOther])}
        onRestart={() => {}}
      />
    );
    expect(screen.getByRole("region", { name: /Evidencia:/ })).toBeInTheDocument();
    expect(screen.getByText(GENERIC_NOTICE)).toBeInTheDocument();
    expect(screen.queryByText("Dataset bloqueado")).not.toBeInTheDocument();
  });

  it("toda la evidencia elegible: nunca muestra la notificación genérica", () => {
    render(<TerminalPanel state={stateWithEvidence(RUN_STATUS.COMPLETED, [eligibleEvidence])} onRestart={() => {}} />);
    expect(screen.queryByText(GENERIC_NOTICE)).not.toBeInTheDocument();
  });
});

describe("Nunca token, Authorization ni dangerouslySetInnerHTML en components/evidence", () => {
  it("ningún archivo fuente de components/evidence contiene esos patrones", () => {
    const here = path.dirname(fileURLToPath(import.meta.url));
    const evidenceDir = path.resolve(here, "../../../components/evidence");
    const files = fs.readdirSync(evidenceDir).filter((f) => f.endsWith(".jsx") || f.endsWith(".js"));
    expect(files.length).toBeGreaterThan(0);
    for (const file of files) {
      const content = fs.readFileSync(path.join(evidenceDir, file), "utf8");
      // Uso real de la API (prop JSX), no la mención en comentarios que
      // documentan la prohibición.
      expect(content).not.toMatch(/dangerouslySetInnerHTML\s*=/);
      expect(content).not.toMatch(/Authorization/);
      expect(content).not.toMatch(/run_access_token|cdt_rt_/);
    }
  });
});

describe("F4-03 Parte 0: isEligibleEvidence centralizada, sin copias locales", () => {
  it("EvidenceCard.jsx y TerminalPanel.jsx importan la utilidad de lib/evidence, sin redefinirla localmente", () => {
    const here = path.dirname(fileURLToPath(import.meta.url));
    const repoRoot = path.resolve(here, "../../..");
    const files = [
      path.join(repoRoot, "components/evidence/EvidenceCard.jsx"),
      path.join(repoRoot, "components/agent/TerminalPanel.jsx"),
    ];
    for (const file of files) {
      const content = fs.readFileSync(file, "utf8");
      expect(content, `${file} no debe redefinir isEligibleEvidence localmente`).not.toMatch(
        /function\s+isEligibleEvidence\s*\(/
      );
      expect(content, `${file} debe importar isEligibleEvidence`).toMatch(/isEligibleEvidence/);
    }
  });
});
