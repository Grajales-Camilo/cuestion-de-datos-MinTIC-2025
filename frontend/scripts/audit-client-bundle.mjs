/**
 * Auditoría de seguridad del bundle CLIENTE (RNF-011): escanea únicamente
 * `.next/static/` — el código que Next.js sirve de verdad al navegador — en
 * busca de claves/credenciales de proveedor incrustadas por accidente.
 * Nunca escanea `.next/server/` ni el resto de `.next/`: ese código corre
 * en el servidor de build/Node y puede legítimamente referenciar variables
 * de entorno sin que eso sea una fuga al cliente.
 *
 * Regla de salida (no negociable): nunca imprime el valor detectado, solo
 * ruta relativa, tipo de patrón, código fijo y conteo. Un nombre de
 * variable de entorno mencionado sin un valor real asignado (p. ej. la
 * cadena literal "GOOGLE_API_KEY" sola) NUNCA es un hallazgo — cada
 * detector exige la FORMA de un valor real, no el nombre.
 */

import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SCAN_EXTENSIONS = new Set([".js", ".mjs", ".css", ".map"]);

// Cada detector exige la FORMA de un secreto real (prefijo de proveedor +
// longitud mínima, o una cadena de conexión con usuario:contraseña
// embebidos) — nunca solo el nombre de una variable de entorno.
const PATTERNS = [
  {
    code: "GOOGLE_GEMINI_KEY_FORMAT",
    label: "Clave de API de Google/Gemini",
    regex: /AIzaSy[0-9A-Za-z_-]{33}/g,
  },
  {
    code: "ANTHROPIC_KEY_FORMAT",
    label: "Clave de API de Anthropic",
    regex: /sk-ant-[A-Za-z0-9_-]{20,}/g,
  },
  {
    code: "OPENAI_KEY_FORMAT",
    label: "Clave de API de OpenAI",
    regex: /sk-(?!ant-)(?:proj-)?[A-Za-z0-9]{20,}/g,
  },
  {
    code: "DB_CONNECTION_CREDENTIALS",
    label: "Cadena de conexión de base de datos con usuario:contraseña embebidos",
    regex: /postgres(?:ql)?:\/\/[^:/\s"'@]+:[^@/\s"']+@[^/\s"']+/g,
  },
  {
    code: "SOCRATA_APP_TOKEN_VALUE",
    label: "Valor asignado a SOCRATA_APP_TOKEN(S) (no solo el nombre)",
    // Exige un `:`/`=` seguido de un valor entre comillas, no la mera
    // presencia del nombre de la variable en el bundle.
    regex: /SOCRATA_APP_TOKENS?["']?\s*[:=]\s*["']([^"'\s]{8,})["']/g,
  },
  {
    code: "RUNTIME_TOKEN_LEAK",
    label: "Token de corrida concreto incrustado en el bundle (RF-801)",
    // `(?!\[)` excluye a propósito el literal de detección de redact.js
    // (`cdt_rt_[A-Za-z0-9_-]+`), que SÍ aparece en el bundle porque
    // redact.js se importa desde código cliente — esa es la fuente del
    // patrón de redacción, no un token filtrado. Un token real nunca va
    // seguido de `[`.
    regex: /cdt_rt_(?!\[)[A-Za-z0-9_-]{6,}/g,
  },
];

function listFilesRecursive(dir) {
  const out = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      out.push(...listFilesRecursive(fullPath));
    } else if (entry.isFile() && SCAN_EXTENSIONS.has(path.extname(entry.name))) {
      out.push(fullPath);
    }
  }
  return out;
}

/**
 * Escanea `staticDir` (se espera `.next/static/`, pero recibe cualquier
 * directorio — así lo pueden usar las pruebas unitarias con un bundle
 * sintético temporal). Devuelve `{ findings, filesScanned }`; `findings` es
 * `[{ file, code, label, count }]`, SIN el texto detectado.
 */
export function scanBundle(staticDir) {
  const files = listFilesRecursive(staticDir);
  const findings = [];

  for (const filePath of files) {
    const content = readFileSync(filePath, "utf8");
    const relativeFile = path.relative(staticDir, filePath).split(path.sep).join("/");
    for (const pattern of PATTERNS) {
      const matches = content.match(pattern.regex);
      if (matches && matches.length > 0) {
        findings.push({ file: relativeFile, code: pattern.code, label: pattern.label, count: matches.length });
      }
    }
  }

  return { findings, filesScanned: files.length };
}

function formatReport({ findings, filesScanned }, staticDir) {
  const lines = [`Auditoría de bundle cliente (RNF-011): ${staticDir}`, `Archivos escaneados: ${filesScanned}`];
  if (findings.length === 0) {
    lines.push("Sin hallazgos. 0 patrones de secreto detectados.");
    return lines.join("\n");
  }
  lines.push(`${findings.length} hallazgo(s) — nunca se imprime el valor detectado:`);
  for (const finding of findings) {
    lines.push(`  - ${finding.file} :: ${finding.code} (${finding.label}) x${finding.count}`);
  }
  return lines.join("\n");
}

function main() {
  const staticDir = path.resolve(process.cwd(), ".next/static");
  try {
    statSync(staticDir);
  } catch {
    console.error(
      `No existe ${staticDir}. Ejecuta "npm run build" antes de "npm run audit:bundle" — este script solo audita el bundle ya construido.`,
    );
    process.exitCode = 2;
    return;
  }

  const result = scanBundle(staticDir);
  console.log(formatReport(result, staticDir));
  if (result.findings.length > 0) {
    process.exitCode = 1;
  }
}

const isDirectCliInvocation = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isDirectCliInvocation) {
  main();
}
