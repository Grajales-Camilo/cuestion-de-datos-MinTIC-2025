/**
 * Arnés de revisión manual F8-02 (WCAG 2.2 AA / RNF-012, T-505). Abre
 * Chrome REAL en modo headed sobre `/app` real, con el backend interceptado
 * por un servidor local mínimo que reproduce las respuestas exactas de los
 * fixtures reales ya existentes (`tests/fixtures/README.md`) — nunca un
 * backend real ni servicios externos, nunca una ruta de producto nueva.
 *
 * Uso:
 *   node scripts/manual-review-harness.mjs --scenario=<nombre>
 *
 * Escenarios:
 *   consent      — alias de `completed`; el modal de consentimiento
 *                  aparece igual en cualquier escenario (es un gate
 *                  puramente cliente antes del primer POST).
 *   streaming    — pasos reales del fixture `completed`, entregados con
 *                  ritmo controlado (≈1.3 s entre pasos) y SIN enviar
 *                  nunca el evento terminal — se queda "investigando" a
 *                  propósito, para revisar el anuncio de aria-live en
 *                  vivo sin la carrera de alcanzar el terminal.
 *   completed    — fixture real `completed-stream.sse.txt` (método 1,
 *                  captura HTTP literal), con pasos re-emitidos con ritmo
 *                  controlado (no de una sola vez). Su evidencia real tiene
 *                  1 fila / 1 columna (un solo valor agregado): SÍ produce
 *                  tabla, NUNCA gráfica (RF-503 exige ≥1 dimensión + ≥3
 *                  filas — regla D-4 — y este fixture no tiene dimensión).
 *   completed_chart — DOBLE SINTÉTICO declarado, mismo patrón ya usado y
 *                  autorizado en `tests/e2e/evidence-chart-f4-03.spec.js`
 *                  (ningún fixture real capturado cumple hoy la condición
 *                  de RF-503): 1 dimensión + 1 métrica + 3 filas, para
 *                  poder revisar con NVDA una gráfica realmente presente
 *                  junto a su tabla como alternativa textual.
 *   no_evidence  — fixture real `no-evidence.json` (método 2), eventos
 *                  reconstruidos a SSE con el mismo ritmo controlado.
 *   interrupted  — fixture real `interrupted.json`, ídem.
 *   failed       — fixture real `failed.json`, ídem.
 *
 * El token de acceso es un valor sintético fijo por escenario, NUNCA
 * impreso en consola (regla de F8-02). Cierra siempre el navegador, el
 * servidor Next y el servidor mock al recibir Ctrl+C — cero proceso
 * huérfano.
 */

import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";
import process from "node:process";
import { chromium } from "@playwright/test";

const STEP_DELAY_MS = 1300;
const FRONTEND_ROOT = process.cwd();
const FIXTURES_DIR = path.join(FRONTEND_ROOT, "tests", "fixtures");
const APP_PORT = 3101;
const MOCK_BACKEND_PORT = 3199;

const scenarioArg = process.argv.find((arg) => arg.startsWith("--scenario="));
const requestedScenario = scenarioArg ? scenarioArg.split("=")[1] : null;
// `--prod`: build real (`next build`) + `next start`, en vez de `next dev`.
// Existe para diagnosticar si algo observado con NVDA es un artefacto de
// `reactStrictMode` (`next.config.js`), que SOLO duplica el montaje/efectos
// de React en modo desarrollo (nunca en producción) — nunca para servir un
// bundle de producción "alterado": es exactamente el mismo build que usa
// `npm run test:e2e:prod`.
const useProdBuild = process.argv.includes("--prod");

const SCENARIOS = new Set([
  "consent",
  "streaming",
  "completed",
  "completed_chart",
  "no_evidence",
  "interrupted",
  "failed",
]);

if (!requestedScenario || !SCENARIOS.has(requestedScenario)) {
  console.error(
    `Uso: node scripts/manual-review-harness.mjs --scenario=<${[...SCENARIOS].join("|")}>`,
  );
  process.exit(1);
}
// `consent` reutiliza exactamente el backend de `completed` — el modal de
// consentimiento no depende del desenlace de la corrida.
const effectiveScenario = requestedScenario === "consent" ? "completed" : requestedScenario;

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function loadJsonFixture(name) {
  return JSON.parse(readFileSync(path.join(FIXTURES_DIR, name), "utf8"));
}

function sseBlocksFromRealEvents(events) {
  return events.map((entry) =>
    [`id: ${entry.seq}`, `event: ${entry.event}`, `data: ${JSON.stringify(entry.data)}`, "", ""].join("\n"),
  );
}

function sseBlocksFromRawStream(rawText) {
  return rawText
    .split(/\r?\n\r?\n/)
    .filter((block) => block.trim() !== "")
    .map((block) => `${block}\n\n`);
}

const TOKEN = `cdt_rt_manual_review_${effectiveScenario}`;

function buildScenario() {
  if (effectiveScenario === "completed") {
    const rawStream = readFileSync(path.join(FIXTURES_DIR, "completed-stream.sse.txt"), "utf8");
    const answerBlock = rawStream.split(/\r?\n\r?\n/).find((block) => block.includes("event: answer"));
    const dataLine = answerBlock.split(/\r?\n/).find((line) => line.startsWith("data: "));
    const answer = JSON.parse(dataLine.slice(6));
    return { runId: answer.run_id, blocks: sseBlocksFromRawStream(rawStream), runDetail: { run_id: answer.run_id, status: "completed", answer } };
  }
  if (effectiveScenario === "streaming") {
    const rawStream = readFileSync(path.join(FIXTURES_DIR, "completed-stream.sse.txt"), "utf8");
    const allBlocks = sseBlocksFromRawStream(rawStream);
    const stepBlocksOnly = allBlocks.filter((block) => block.includes("event: step"));
    return { runId: "manual-review-streaming-0001", blocks: stepBlocksOnly, runDetail: null };
  }
  if (effectiveScenario === "completed_chart") {
    const runId = "manual-review-chart-demo-0001";
    // Doble sintético declarado (ver comentario de cabecera): réplica del
    // mismo payload ya autorizado en evidence-chart-f4-03.spec.js.
    const answer = {
      run_id: runId,
      status: "completed",
      intention: { topic: "¿Cuál es la suma de valor por municipio en el conjunto sintético de prueba?" },
      summary: "Suma de valor por municipio (doble sintético declarado, arnés F8-02).",
      narrative: null,
      evidence: [
        {
          evidence_id: "ev-manual-review-chart-0001",
          dataset_id: "synthetic-manual-review-0001",
          dataset_name: "Dataset sintético declarado (arnés F8-02, sin fixture real con dimensión)",
          publisher: "Publicador sintético",
          soql_query: "SELECT municipio AS dim_1, sum(valor) AS metric_sum_1 GROUP BY municipio",
          executed_at: new Date().toISOString(),
          source_url: "https://www.datos.gov.co/resource/synthetic0001.json",
          data_updated_at: "2026-07-01T00:00:00Z",
          data_cutoff_at: "2026-07-01T00:00:00Z",
          data_cutoff_basis: "data_cutoff_at",
          columns: ["dim_1", "metric_sum_1"],
          rows: [
            { dim_1: "Sonsón", metric_sum_1: 12.5 },
            { dim_1: "Rionegro", metric_sum_1: 30 },
            { dim_1: "Marinilla", metric_sum_1: 7 },
          ],
          row_count: 3,
          narrative: null,
          chart_suggestion: null,
          quality: {
            eligibility_status: "eligible",
            eligibility_reasons: [],
            score_total: 80,
            classification: "alta",
            warnings_user: [],
            dimensions: {},
          },
        },
      ],
      claims: [],
      no_evidence_report: null,
      textual_facts: [],
      partial_textual_facts: [],
      presentation_warnings: [],
      usage: { steps_used: 1 },
    };
    const blocks = [
      [
        "id: 0",
        "event: step",
        `data: ${JSON.stringify({ step_number: 1, node: "execute_query", display_message: "Consultando datos.gov.co…", detail: null })}`,
        "",
        "",
      ].join("\n"),
      ["id: 1", "event: answer", `data: ${JSON.stringify(answer)}`, "", ""].join("\n"),
    ];
    return { runId, blocks, runDetail: { run_id: runId, status: "completed", answer } };
  }
  const fixtureByScenario = {
    no_evidence: "no-evidence.json",
    interrupted: "interrupted.json",
    failed: "failed.json",
  };
  const fixture = loadJsonFixture(fixtureByScenario[effectiveScenario]);
  return { runId: fixture.run_id, blocks: sseBlocksFromRealEvents(fixture.events), runDetail: fixture };
}

const scenario = buildScenario();

function withCors(res) {
  res.setHeader("Access-Control-Allow-Origin", `http://localhost:${APP_PORT}`);
  res.setHeader("Access-Control-Allow-Headers", "Authorization, Content-Type, Last-Event-ID");
  res.setHeader("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS");
}

const mockBackend = createServer(async (req, res) => {
  withCors(res);
  if (req.method === "OPTIONS") {
    res.writeHead(204);
    res.end();
    return;
  }

  if (req.method === "POST" && req.url === "/v2/agent/query") {
    let body = "";
    req.on("data", (chunk) => (body += chunk));
    req.on("end", () => {
      res.writeHead(202, { "Content-Type": "application/json" });
      res.end(
        JSON.stringify({
          run_id: scenario.runId,
          run_access_token: TOKEN,
          token_expires_at: new Date(Date.now() + 3_600_000).toISOString(),
          stream_url: `/v2/agent/stream/${scenario.runId}`,
        }),
      );
    });
    return;
  }

  if (req.method === "GET" && req.url === `/v2/agent/stream/${scenario.runId}`) {
    res.writeHead(200, {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    });
    for (const block of scenario.blocks) {
      if (res.writableEnded) return;
      res.write(block);
      await delay(STEP_DELAY_MS);
    }
    // `streaming` nunca llega aquí con un bloque terminal: la conexión
    // queda abierta a propósito hasta que el humano cierre la pestaña.
    if (effectiveScenario === "streaming") return;
    res.end();
    return;
  }

  if (req.url === `/v2/agent/runs/${scenario.runId}`) {
    if (req.method === "DELETE") {
      res.writeHead(204);
      res.end();
      return;
    }
    if (req.method === "GET") {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify(scenario.runDetail ?? { run_id: scenario.runId, status: "streaming" }));
      return;
    }
  }

  res.writeHead(404, { "Content-Type": "application/json" });
  res.end(JSON.stringify({ error: { code: "NOT_FOUND", message_user: "No encontrado (arnés de revisión)." } }));
});

function waitForHttp(url, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  return (async function poll() {
    while (Date.now() < deadline) {
      try {
        const response = await fetch(url, { signal: AbortSignal.timeout(1000) });
        if (response.status < 500) return;
      } catch {
        // sigue esperando
      }
      await delay(150);
    }
    throw new Error(`Tiempo de espera agotado esperando ${url}`);
  })();
}

let nextProcess;
let browser;

async function cleanup() {
  console.log("\nCerrando arnés de revisión…");
  await browser?.close().catch(() => {});
  if (nextProcess && nextProcess.exitCode === null) {
    nextProcess.kill();
    await new Promise((resolve) => {
      nextProcess.once("close", resolve);
      setTimeout(resolve, 5000);
    });
  }
  await new Promise((resolve) => mockBackend.close(resolve));
  console.log("Arnés cerrado: navegador, Next y servidor mock detenidos.");
}

process.once("SIGINT", async () => {
  await cleanup();
  process.exit(0);
});

function runBuild(env) {
  return new Promise((resolve, reject) => {
    const nextCli = path.join(FRONTEND_ROOT, "node_modules", "next", "dist", "bin", "next");
    const build = spawn(process.execPath, [nextCli, "build"], {
      cwd: FRONTEND_ROOT,
      env,
      stdio: "inherit",
      windowsHide: true,
    });
    build.once("close", (code) => (code === 0 ? resolve() : reject(new Error(`next build salió con código ${code}`))));
  });
}

async function main() {
  await new Promise((resolve) => mockBackend.listen(MOCK_BACKEND_PORT, resolve));
  console.log(`Backend simulado (F8-02, escenario "${requestedScenario}") escuchando en :${MOCK_BACKEND_PORT}`);

  const nextCli = path.join(FRONTEND_ROOT, "node_modules", "next", "dist", "bin", "next");
  const sharedEnv = { ...process.env, NEXT_PUBLIC_BACKEND_URL: `http://localhost:${MOCK_BACKEND_PORT}` };

  if (useProdBuild) {
    console.log("Construyendo build de producción real (next build)…");
    await runBuild(sharedEnv);
    nextProcess = spawn(process.execPath, [nextCli, "start", "-p", String(APP_PORT)], {
      cwd: FRONTEND_ROOT,
      env: sharedEnv,
      stdio: "inherit",
      windowsHide: true,
    });
  } else {
    nextProcess = spawn(process.execPath, [nextCli, "dev", "-p", String(APP_PORT)], {
      cwd: FRONTEND_ROOT,
      env: sharedEnv,
      stdio: "inherit",
      windowsHide: true,
    });
  }

  await waitForHttp(`http://localhost:${APP_PORT}`, 60_000);
  console.log(`Next real listo en http://localhost:${APP_PORT}`);

  browser = await chromium.launch({ headless: false, channel: "chrome" });
  // `acceptDownloads: false` (Playwright intercepta descargas por defecto
  // en `browser.newPage()`, guardándolas con un nombre interno propio en
  // vez de dejar que Chrome haga su descarga nativa real): hallazgo de
  // revisión manual F8-02 — con la interceptación por defecto, exportar el
  // DOCX se veía en Chrome con un nombre UUID sin extensión en vez de
  // `Documento-libre.docx`. Confirmado que es un artefacto exclusivo del
  // arnés (las pruebas E2E automatizadas, que sí manejan el evento
  // `download` explícitamente con `download.saveAs()`, siempre obtienen el
  // nombre correcto) — con esto, la descarga real de Chrome queda intacta,
  // igual que la vería cualquier persona usando la app de verdad.
  const context = await browser.newContext({ acceptDownloads: false });
  const page = await context.newPage();
  await page.goto(`http://localhost:${APP_PORT}/app`);

  console.log("\n=== Arnés de revisión manual F8-02 listo ===");
  console.log(`Escenario activo: ${requestedScenario}`);
  console.log("Chrome real abierto sobre /app. Interactúa normalmente (teclado, NVDA, zoom).");
  console.log("Presiona Ctrl+C en esta terminal cuando termines este escenario.\n");

  await new Promise(() => {}); // permanece abierto hasta Ctrl+C
}

main().catch(async (error) => {
  console.error("Error en el arnés de revisión:", error.message);
  await cleanup();
  process.exit(1);
});
