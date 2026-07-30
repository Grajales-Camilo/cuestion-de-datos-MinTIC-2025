# Frontend — Cuestión de Datos V2

Este directorio contiene el frontend existente de Cuestión de Datos y será la
base del nuevo frontend v2. La aplicación v2 consume directamente el backend
FastAPI del núcleo determinista mediante REST y SSE.

Este README es operativo: explica cómo instalar, ejecutar y verificar el
frontend. El plan completo, la jerarquía documental y el enrutamiento por fases
están en [`docs/frontend-v2/README.md`](../docs/frontend-v2/README.md).

## Estado comprobado del proyecto

Al crear este documento, el andamiaje existente usa:

- Next.js 14.2.35 con Pages Router (actualizado en F8-01 desde 14.1.3: cierra
  una vulnerabilidad crítica de Next.js sin salir de la línea 14.x — ver
  `docs/frontend-v2/release/f8-01-automated-gates.md` §8).
- React 18.2.
- JavaScript.
- Tailwind CSS 3.
- Tiptap 3.
- Chart.js y PapaParse.

El código de aplicación visible en `pages/`, `components/` y `utils/` pertenece
principalmente al frontend legacy. Su existencia no significa que cumpla los
contratos ni los criterios del runtime determinista.

Scripts confirmados en `package.json` (verificados con ejecución real, F0):

| Comando | Uso | Estado |
|---|---|---|
| `npm run dev` | Servidor local de Next.js | Disponible |
| `npm run build` | Build de producción | Disponible; verde (~24 s, ver `docs/frontend-baseline-2026-07.md`) |
| `npm run start` | Ejecutar el build de producción | Disponible |
| `npm run lint` | ESLint (`next lint`, `.eslintrc.json`) | Disponible; verde dentro del alcance aprobado (ver nota de alcance abajo) |
| `npm run test` | Vitest en modo único (`vitest run`, no watch) | Disponible; verde (897 pruebas) |
| `npm run test:e2e:functional` | Suite E2E funcional en paralelo (Playwright, `playwright.config.js`) | Disponible; verde |
| `npm run test:e2e:perf` | RNF-008 dedicado, aislado (Playwright, `playwright.perf.config.js`: 1 worker, sin paralelismo, 3 repeticiones con tiempos registrados por consola) | Disponible; verde. Ver `docs/frontend-v2/release/f8-01-automated-gates.md` §4 |
| `npm run test:e2e` | Ejecuta `test:e2e:functional` y luego `test:e2e:perf`, en secuencia | Disponible; verde. Requiere `npx playwright install chrome` (canal `chrome` local; en CI cae a Chromium embebido normal — ver `playwright.config.js`), una sola vez. El paquete `chromium` embebido de Playwright (Chrome for Testing) puede fallar en Windows por un error de resolución de manifiesto WinSxS ajeno al proyecto (`spawn UNKNOWN`), y `chromium_headless_shell` (el binario headless por defecto) puede faltar según la instalación — `channel: "chrome"` evita ambos, solo fuera de CI. El smoke captura `navigator.userAgent`/`browser.version()` reales como evidencia de que arrancó un navegador de verdad, no solo un exit code. Todo usa el puerto fijo 3101 (nunca 3000) |
| `npm run test:e2e:prod` | Verificación E2E contra build de producción real (`playwright.prod.config.js`) | Disponible; verde |
| `npm run audit:bundle` | Auditoría de secretos en `.next/static/` (RNF-011, `scripts/audit-client-bundle.mjs`) — ejecutar después de `npm run build` | Disponible; verde (0 hallazgos). Ver `docs/frontend-v2/release/f8-01-automated-gates.md` §7 |

**Alcance de lint (F0).** `react/no-danger` es error en todo el código, nuevo y
legacy (cero usos de `dangerouslySetInnerHTML` verificados en el baseline).
`react/no-unescaped-entities` se rebajó a advertencia únicamente en tres
archivos legacy preexistentes con errores de escape de comillas
(`components/common/OnboardingTour.js`, `components/wizard/ApiStep.js`,
`components/wizard/DatabaseStep.js`) — visibles en la salida de `npm run
lint`, no ocultos. No se hizo refactor del legacy para satisfacer lint.

## Requisitos locales

- Windows 11 y PowerShell 7, o un entorno compatible.
- Node.js 20 o superior. CI usa Node 20.
- npm y el `package-lock.json` del repositorio.
- Para integración real: backend local determinista y PostgreSQL según el
  `quickstart.md` del paquete de especificaciones.

Antes de instalar dependencias nuevas, comprueba si ya están presentes y si
son compatibles con las versiones actuales de Next y Node. No uses
actualizaciones masivas ni `npm audit fix --force` como parte de una fase.

## Instalación

Desde PowerShell:

```powershell
Set-Location D:\Usuario\AppWebs\cuestion-de-datos-MinTIC\frontend
npm ci
```

`npm ci` conserva el conjunto fijado por `package-lock.json`. Si falla, registra
el error antes de modificar dependencias.

## Ejecución local

```powershell
Set-Location D:\Usuario\AppWebs\cuestion-de-datos-MinTIC\frontend
npm run dev
```

Por defecto, Next.js queda disponible en `http://localhost:3000`.

El frontend v2 debe usar en desarrollo:

```dotenv
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
```

Ese valor pertenece a `frontend/.env.local.example`. Los valores locales van en
`frontend/.env.local`, que no debe contener claves de proveedores ni
versionarse. No existe fallback silencioso a `localhost` en producción.

Para la integración local, el backend debe ejecutarse con el runtime
determinista, `CORS_ALLOWED_ORIGINS` debe contener el origen exacto del frontend
y no debe activarse `EVAL_MODE` para una sesión normal de usuario.

## Verificación

Conjunto mínimo de verificación, en este orden:

```powershell
npm run lint
npm run test
npm run build
npm run audit:bundle
npm run test:e2e
npm run test:e2e:prod
```

Todos los comandos están verificados en verde con ejecución real (F0/F0-R1;
`audit:bundle` y la separación `test:e2e:functional`/`test:e2e:perf` desde
F8-01, ver `docs/frontend-v2/release/f8-01-automated-gates.md`).
No se debe documentar una fase como terminada porque los scripts existan:
cada criterio de aceptación necesita una ejecución real y su evidencia.

`npm run test:e2e` genera `frontend/test-results/` (artefacto efímero de
Playwright); está en `.gitignore` de la raíz y no debe versionarse.

### Verificación reproducible del `.docx` exportado con Microsoft Word (F6-02B-R1)

`scripts/verify-docx-word.ps1` abre en Word real, en solo lectura y sin
diálogos, el `.docx` generado por el E2E de exportación, y confirma que no
hubo que repararlo. Requiere Word instalado localmente; si el equipo no lo
tiene, este paso queda como verificación humana pendiente (no se simula).

```powershell
# 1. Generar un .docx real desde el E2E de exportación
npm run test:e2e -- tests/e2e/app-f6-02b-export.spec.js --workers=1

# 2. Localizar el .docx descargado (nombre de carpeta variable; buscar el
#    caso "RF-103 completo" para tener notas al pie garantizadas)
Get-ChildItem -Recurse -Filter *.docx test-results | Select-Object -First 1 FullName

# 3. Verificar ese archivo con Word real
pwsh -File scripts/verify-docx-word.ps1 `
  -DocxPath "<ruta devuelta por el paso 2>" `
  -MinimumFootnotes 1
```

El script nunca cierra ni reutiliza una instancia de Word que ya perteneciera
al usuario (se niega con exit code distinto de cero si detecta una antes de
empezar) y nunca imprime texto del documento, citas ni tokens — solo un
resumen JSON con hashes SHA-256, conteo de notas al pie y booleanos de
resultado.

## Arquitectura objetivo

La arquitectura detallada vive en el plan. Las fronteras principales son:

- `lib/config/`: configuración validada del navegador.
- `lib/api/`: cliente REST, errores y redacción de secretos.
- `lib/sse/`: parser incremental y orquestación del stream.
- `lib/agent/`: estados, reducer puro y mensajes en español.
- `lib/evidence/`: presentación determinista de evidencia y calidad.
- `lib/document/`: esquema, migraciones locales y exportación.
- `hooks/`: integración controlada entre React y los módulos puros.
- `components/`: primitivas accesibles y superficies de producto.
- `tests/unit/`, `tests/fixtures/` y `tests/e2e/`: pirámide de pruebas.

Las carpetas se incorporan por fases. No deben crearse anticipadamente para
simular progreso.

## Reglas esenciales del runtime determinista

- El navegador transporta, ordena, deduplica, formatea y presenta; no inventa
  ni completa datos.
- La integración usa `POST /v2/agent/query` y el stream
  `/v2/agent/stream/{run_id}` según los contratos vigentes.
- SSE se consume con `fetch` y `Authorization`; no con `EventSource` ni con un
  proxy de Next.
- El token de corrida nunca aparece en URL, logs, telemetría o estado
  persistente no autorizado.
- Los fixtures se capturan de corridas reales del backend determinista, se
  anonimizan y registran su `run_id` y commit de origen. El fixture de stream
  SSE se captura en vivo contra el endpoint HTTP real
  (`httpx.stream(...).iter_bytes()`), nunca reconstruido desde PostgreSQL —
  ver `tests/fixtures/README.md`.
- Claims, evidencia, hechos textuales, advertencias y aportes manuales mantienen
  identidades y tratamientos visuales diferentes.
- El legacy no es fallback funcional ni base de aceptación.

## Impeccable

Instalado en F0 (2026-07-27) desde la raíz del repositorio con
`npx impeccable install`. La skill vive en `.agents/skills/impeccable/`
(alcance de proyecto, proveedor Codex) y el hook del proyecto en
`.codex/hooks.json` (dispara sobre `Edit|Write|apply_patch`, invoca
`.agents/skills/impeccable/scripts/hook.mjs`).

**Nota de alcance.** El instalador detecta automáticamente todos los
harnesses presentes en la máquina (Claude Code, Codex CLI, GitHub Copilot) e
instala en los tres salvo que se elija "Customize" en el prompt interactivo.
En esta sesión no interactiva se instaló primero en los tres; las copias en
`.github/hooks/` y `.github/skills/` se eliminaron por exceder el alcance
autorizado (project + Codex únicamente). La copia en `.claude/skills/` y las
claves `hooks`/`description` añadidas a `.claude/settings.local.json`
(archivo preexistente desde antes de esta sesión) se dejaron intactas por
decisión explícita de Juan Camilo Grajales B. — no fue necesario para F0 y no
se revirtió. Antes de una futura reinstalación, usar la opción "Customize" y
seleccionar únicamente Codex.

Estado verificado en esta sesión:

- **`PRODUCT.md` creado** en la raíz del repositorio (`/PRODUCT.md`), no
  inventado: se hizo una entrevista real de 3 preguntas a Juan Camilo
  Grajales B. (marca, evidencia de producto, posicionamiento) y el resto se
  tomó de `specs/001-cuestion-de-datos-v2/spec.md`/`constitution.md` con cita
  explícita de la fuente. `node .agents/skills/impeccable/scripts/context.mjs`
  confirma la resolución: `"productPath": "PRODUCT.md"`, `"platform": "web"`.
- `npx impeccable detect frontend/pages frontend/components frontend/styles`
  (el detector determinista de auditoría) corrió como baseline: 7
  antipatrones encontrados en el legacy (colores de bajo contraste sobre
  fondo `bg-cyan-500` en `pages/index.js`, `animate-bounce` en
  `CopilotSidebar.js` y `ApiStep.js`, borde lateral grueso en `ApiStep.js`,
  texto con gradiente en `IntroStep.js`). Ninguno se corrigió en F0/F0-R1.
- **Hook verificado técnicamente**: se validó que `.codex/hooks.json` es JSON
  bien formado, que `.agents/skills/impeccable/scripts/hook.mjs` existe, y se
  ejecutó el comando exacto que Codex dispararía en `PostToolUse`/`Stop`
  (`node .agents/skills/impeccable/scripts/hook.mjs`) — terminó con exit code
  `0` sin errores.
- **Lo que sigue sin poderse verificar desde esta sesión**: la recarga real
  de un agente Codex CLI y la aprobación del hook desde su comando `/hooks`
  son interacciones específicas de esa interfaz — esta sesión corrió como
  Claude Code, no como Codex CLI real. Queda `NO VERIFICADO` hasta la primera
  sesión real de Codex sobre este repositorio; no se simuló ni se dio por
  hecho.

No se debe ignorar toda la carpeta `.impeccable/`: sus artefactos compartidos
de configuración y diseño pueden pertenecer al repositorio, mientras que
capturas, cachés y estado por desarrollador son efímeros. Ningún artefacto en
`.impeccable/` se generó todavía en esta sesión.

## Documentación para desarrollar

| Documento | Propósito |
|---|---|
| [`../AGENTS.md`](../AGENTS.md) | Instrucciones y jerarquía general |
| [`AGENTS.md`](./AGENTS.md) | Reglas obligatorias para este directorio |
| [`../docs/frontend-v2/README.md`](../docs/frontend-v2/README.md) | Índice y enrutamiento por fase |
| [`../docs/frontend-v2/implementation-plan.md`](../docs/frontend-v2/implementation-plan.md) | Plan ejecutable no normativo |
| [`../docs/frontend-v2/architecture-principles.md`](../docs/frontend-v2/architecture-principles.md) | Capítulos arquitectónicos seleccionados |
| [`../specs/README.md`](../specs/README.md) | Entrada al paquete normativo SDD |

## Disciplina de cambios

- Cada incremento identifica sus `RF-###`, `RNF-###` y tarea aplicable.
- Cada sesión protege cambios preexistentes y trabaja con rutas Git explícitas.
- No se modifican contratos, backend, golden data ni documentos normativos para
  acomodar una implementación del frontend sin autorización.
- No se marca una fase como terminada hasta ejecutar todos sus criterios.
- Si cambian comandos, variables o estructura operativa, este README se
  actualiza en el mismo incremento.
