import { spawn } from "node:child_process";
import path from "node:path";
import process from "node:process";

const frontendRoot = process.cwd();
const nextCli = path.join(frontendRoot, "node_modules", "next", "dist", "bin", "next");
const playwrightCli = path.join(frontendRoot, "node_modules", "@playwright", "test", "cli.js");
const serverUrl = "http://localhost:3101";

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function isServerAvailable() {
  try {
    const response = await fetch(serverUrl, { signal: AbortSignal.timeout(1_000) });
    return response.status >= 200 && response.status < 500;
  } catch {
    return false;
  }
}

async function waitForServer(serverProcess) {
  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    if (serverProcess.exitCode !== null) {
      throw new Error(`Next terminó antes de escuchar en 3101 (código ${serverProcess.exitCode}).`);
    }
    if (await isServerAvailable()) return;
    await delay(150);
  }
  throw new Error("Next no estuvo disponible en 3101 dentro de 60 segundos.");
}

async function stopServer(serverProcess) {
  if (!serverProcess || serverProcess.exitCode !== null) return;
  const closed = new Promise((resolve) => serverProcess.once("close", resolve));
  serverProcess.kill();
  await Promise.race([closed, delay(5_000)]);
  if (serverProcess.exitCode === null) {
    serverProcess.kill("SIGKILL");
    await Promise.race([closed, delay(5_000)]);
  }
}

if (await isServerAvailable()) {
  console.error("El puerto 3101 ya está ocupado; no se reutilizará un servidor existente.");
  process.exit(1);
}

const serverProcess = spawn(process.execPath, [nextCli, "dev", "-p", "3101"], {
  cwd: frontendRoot,
  env: process.env,
  stdio: "inherit",
  windowsHide: true,
});

let interrupted = false;
async function interrupt(signal) {
  if (interrupted) return;
  interrupted = true;
  await stopServer(serverProcess);
  process.kill(process.pid, signal);
}
process.once("SIGINT", () => void interrupt("SIGINT"));
process.once("SIGTERM", () => void interrupt("SIGTERM"));

let exitCode = 1;
try {
  await waitForServer(serverProcess);
  exitCode = await new Promise((resolve, reject) => {
    const testProcess = spawn(process.execPath, [playwrightCli, "test", ...process.argv.slice(2)], {
      cwd: frontendRoot,
      env: { ...process.env, CDT_E2E_SERVER_MANAGED: "1" },
      stdio: "inherit",
      windowsHide: true,
    });
    testProcess.once("error", reject);
    testProcess.once("close", (code) => resolve(code ?? 1));
  });
} catch (error) {
  console.error(error instanceof Error ? error.message : "No se pudo ejecutar Playwright.");
} finally {
  await stopServer(serverProcess);
}

process.exit(exitCode);
