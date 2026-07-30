# F8-01 — Puertas automatizadas de release (E2E, accesibilidad, RNF-008, seguridad)

**Rama:** `feat/frontend-v2`. **Fecha F8-01:** 2026-07-29. **Fecha F8-01-R1:**
2026-07-30. **Alcance:** exclusivamente las puertas automatizables de T-505
(RNF-007, RNF-008, RNF-011). No cierra T-505 ni RNF-007/RNF-012 (exigen
revisión humana con lector de pantalla, zoom real y actas manuales — queda
para F8-02, ver §12).

## 0. F8-01-R1 (2026-07-30) — resumen de la ronda de cierre

Ronda de seguimiento autorizada explícitamente para cerrar los tres defectos
que dejó F8-01 abiertos:

1. **Vulnerabilidad crítica dev-only eliminada** mediante una migración
   acotada y comprobada de Vitest 2.1.9 → **Vitest 4.1.10** (versión exacta,
   sin caret, la misma que `npm audit` reportaba como `fixAvailable`).
   **Corrección sobre la afirmación de la ronda F8-01:** Vitest 4 **no era
   técnicamente incompatible** con el proyecto — el informe anterior lo dejó
   sin aplicar porque era un **salto de versión mayor sin autorización
   explícita**, no por una incompatibilidad real detectada. Con la
   autorización de esta ronda, la migración se ejecutó sin tocar ni una sola
   aserción funcional: las 897 pruebas unitarias pasan sin cambios, `vitest.config.js`
   y `tests/setup.js` no necesitaron ningún ajuste (ver §4.5).
2. **Gate de `npm audit` crítico ahora es bloqueante real en CI** (antes:
   `continue-on-error: true`, no bloqueaba nada). Ver §6.
3. **Axe con el conjunto completo de tags** (`wcag2a`+`wcag2aa`+`wcag22aa`)
   en las dos superficies que antes solo usaban `wcag22aa`
   (`external-sources-f7-02b.spec.js`, `manual-entry-f7-02a.spec.js`). Ver §3.

## 1. Veredicto

**READY** (puertas automatizables de F8-01). **Cero vulnerabilidades
críticas** en `npm audit --audit-level=critical` (árbol completo) ni en
`npm audit --omit=dev --audit-level=critical` (árbol de producción) —
confirmado con ambos comandos en verde (§8, §10) y con un gate bloqueante
real en CI que impedirá que una futura crítica pase desapercibida (§6).

Este veredicto es **exclusivamente sobre las puertas automatizables de
F8-01**. Sigue sin cerrarse T-505 (exige las dos actas manuales), RNF-007 y
RNF-012 siguen requiriendo revisión humana, y F8-02 no comenzó — ver §14.

## 2. Matriz de cobertura E2E real (`tests/e2e/`, `tests/e2e-perf/`, `tests/e2e-prod/`)

| Archivo | Escenario/Requisito | Estados cubiertos | Fixture | Axe | Teclado | Responsive | Seguridad (token) | Reproducibilidad | Hueco detectado antes de F8-01 |
|---|---|---|---|---|---|---|---|---|---|
| `app-esc01-integral.spec.js` **(nuevo)** | ESC-01 íntegro de punta a punta, sin fragmentar | completed | real (`completed-stream.sse.txt`, método 1) | sí (final) | — | — | sí | alta | Ninguna prueba encadenaba escribir→consentimiento→SSE→insertar→persistir→recargar→exportar en una sola corrida |
| `app-terminal-states-f8-01.spec.js` **(nuevo)** | ESC-03 puro (`no_evidence` sin `external_sources`), `interrupted`, `failed`, modal RF-404, skip-link | no_evidence, interrupted, failed | real (`no-evidence.json`/`interrupted.json`/`failed.json`, reconstruidos a SSE desde su `events[]` real) + 1 doble inline (RF-404) | sí (4 estados) | sí (no_evidence, skip-link) | sí (320px ×3) | sí | alta | `interrupted`/`failed`/`no_evidence` sin `external_sources` tenían fixture real capturado pero CERO E2E en `/app`; sin axe en el modal de confirmación RF-404; sin prueba de skip-link |
| `agent-demo.spec.js` (F3-7A, modificado) | flujo simulado, no_evidence, interrupted/failed, reconexión, teclado, axe, 320px, reduced-motion+axe, consola | completed, no_evidence, interrupted, failed | doble determinista en memoria (galería) | sí (+1 nuevo: streaming) | sí | sí | — | alta | Medía RNF-008 dentro de la suite paralela (ver §4) |
| `app-f3-7b.spec.js` | Consentimiento (D-9/RF-802), historial (RF-502), borrado (RF-803), teclado, 320px, axe, token | completed | doble vía `page.route` | sí | sí | sí | sí | alta | — |
| `app-f5-02.spec.js` | Editor/cita Tiptap, RF-404, teclado, axe, 320px | completed | real (`completed-stream.sse.txt`) + doble inline RF-404 | sí | sí | sí | sí | alta | — |
| `app-f5-03.spec.js` | RF-104 contexto de sección, teclado, axe, 320px | completed | real | sí | sí | sí | — | alta | — |
| `app-f6-01.spec.js` | Persistencia RF-102/103, ESC-08, migraciones, corrupción, axe, 320px | completed | real + variante `no_recomendada` (1 campo mutado) | sí | sí | sí | sí | alta | — |
| `app-f6-02b-export.spec.js` | Exportación DOCX real, notas al pie, token, axe, 320/1440px | completed | real | sí | sí | sí | sí | alta | — |
| `evidence-f4-02.spec.js` | EvidenceCard, CSV, copiar cita, teclado, axe, 320px | completed | real (`completed-with-claims.json`) | sí | sí | sí | — | alta | — |
| `evidence-chart-f4-03.spec.js` | RF-503 gráfica + alternativa textual, axe, 320px | completed | doble inline (único fixture real no tiene métricas) | sí | — | sí | — | alta | — |
| `external-sources-f7-02b.spec.js` | ESC-03 con `external_sources`, aporte manual prellenado, DOCX, axe (wcag22aa) | no_evidence | doble (estructura real de `no_evidence_report`, valores inline) | sí (wcag22aa) | sí | sí | sí | alta | Axe del modal solo con tag `wcag22aa`, no el set completo — deuda menor, no bloqueante |
| `manual-entry-f7-02a.spec.js` | Aporte manual visual/persistencia/DOCX, distinción vs. evidencia, axe (wcag22aa) | completed | real + manual | sí (wcag22aa) | sí | sí | sí | alta | — |
| `gallery.spec.js` (F1-01) | Primitivas: axe, teclado, modal (trampa de foco), Disclosure, Tabs, Table, 320/1440px, reduced-motion | — | — | sí | sí | sí | — | alta | — |
| `infra.smoke.spec.js` | Arranque real de Chromium | — | — | — | — | — | — | alta | — |
| `tests/e2e-perf/rnf008.spec.js` **(nuevo)** | RNF-008 aislado, 3 repeticiones | completed | doble determinista (galería) | — | — | — | — | alta (1 worker dedicado) | Medición compartía CPU con la suite paralela (505 ms observados una vez en F7) |
| `tests/e2e-prod/production.spec.js` | `/app`→200, `/_dev/ui`→404, `/`→200, `lang="es"`, cero secretos en HTML | — | build real de producción | — | — | — | sí | alta | — |

**No se duplicó ninguna prueba** que ya demostrara un criterio (p. ej. ESC-03
con `external_sources` ya estaba cubierto por `external-sources-f7-02b.spec.js`
y no se repitió).

## 3. Matriz de accesibilidad automatizada (axe `wcag2a`+`wcag2aa`+`wcag22aa`, salvo donde se indica)

| Estado exigido | Cubierto en | Detalle |
|---|---|---|
| 1. Inicial + consentimiento | `app-f3-7b.spec.js` | Modal de consentimiento abierto |
| 2. Investigación activa con pasos | `agent-demo.spec.js` (ampliado en F8-01) | Escenario "Streaming (sin terminar)" — único punto estable para auditar pasos EN VIVO sin la fragilidad de congelar un stream real a mitad de camino |
| 3. `completed` con evidencia | `evidence-f4-02.spec.js`, `app-f5-02.spec.js`, `app-f6-02b-export.spec.js`, `manual-entry-f7-02a.spec.js`, `app-esc01-integral.spec.js` | Múltiples estados terminales reales |
| 4a. `no_evidence` CON `external_sources` | `external-sources-f7-02b.spec.js` | Set completo de tags **(ampliado en F8-01-R1; antes solo `wcag22aa`)** |
| 4b. `no_evidence` SIN `external_sources` | `app-terminal-states-f8-01.spec.js` **(nuevo)** | Set completo de tags |
| 5. `interrupted` | `app-terminal-states-f8-01.spec.js` **(nuevo)** | Set completo, fixture real reconstruido a SSE |
| 6. `failed` | `app-terminal-states-f8-01.spec.js` **(nuevo)** | Set completo, fixture real reconstruido a SSE |
| 7. Modal de aporte manual | `external-sources-f7-02b.spec.js`, `manual-entry-f7-02a.spec.js` | Set completo de tags **(ampliado en F8-01-R1; antes solo `wcag22aa`)** |
| 7. Modal de confirmación de evidencia (RF-404) | `app-terminal-states-f8-01.spec.js` **(nuevo)** | Set completo, doble inline sobre fixture real |

Criterio en los 9 puntos: **cero violaciones**, con el conjunto **completo**
de tags (`wcag2a`+`wcag2aa`+`wcag22aa`) en las 9. Confirmado con ejecución
real (ver §10). Las dos deudas de tag parcial que dejó F8-01 (§13 de la
ronda anterior) quedan cerradas en F8-01-R1: `external-sources-f7-02b.spec.js`
y `manual-entry-f7-02a.spec.js` se re-ejecutaron focalizadamente con
`--workers=1` tras el cambio — 7/7 passed, cero violaciones.

Consolidado también en este incremento: skip-link funcional (nuevo), teclado
completo del flujo principal (ya existente en múltiples specs), trampa/restauración
de foco de modales (ya existente, `gallery.spec.js`/`app-f5-03.spec.js`), foco
visible (ya existente), nombres accesibles (ya existente), tablas con
encabezados (`evidence-f4-02.spec.js`), gráfica con alternativa textual
(`evidence-chart-f4-03.spec.js`), `prefers-reduced-motion` (ya existente +
ampliado con axe en F8-01), reflujo a 320 CSS px sin overflow horizontal (ya
existente + 3 estados nuevos en F8-01).

**No se usó** `style.zoom`, `deviceScaleFactor` ni transformación CSS como
sustituto de zoom real al 200 % — ese criterio queda **honestamente
pendiente para F8-02** (ya documentado así desde F1-01 en `gallery.spec.js`).
**No se afirma** haber probado NVDA real en esta fase.

## 4. RNF-008 — reproducible y aislado

**Problema origen (F7):** la medición compartía proceso con hasta 6 workers de
la suite funcional paralela; una corrida midió 505 ms contra el límite
contractual <500 ms.

**Solución:** `frontend/tests/e2e-perf/rnf008.spec.js` + `playwright.perf.config.js`
(`workers: 1`, `fullyParallel: false`), ejecutado en un **proceso Playwright
separado** después de la suite funcional. `npm run test:e2e` (comando oficial)
ejecuta ambas partes **secuencialmente**:

```json
"test:e2e:functional": "node scripts/run-e2e.mjs",
"test:e2e:perf": "node scripts/run-e2e.mjs --config=playwright.perf.config.js",
"test:e2e": "npm run test:e2e:functional && npm run test:e2e:perf"
```

Cada sub-comando administra su propio servidor Next (`scripts/run-e2e.mjs`,
ya existente desde F1) y lo cierra siempre en su bloque `finally` — **cero
servidor huérfano** entre ambas fases. El umbral contractual (<500 ms /
<2000 ms) **no se tocó**.

**Tiempos medidos (3 repeticiones, última corrida completa de validación,
1 worker dedicado):**

| Repetición | Feedback visual (<500 ms) | Primer paso visible (<2000 ms) |
|---|---|---|
| 1/3 | 211 ms | 1175 ms |
| 2/3 | 83 ms | 1144 ms |
| 3/3 | 91 ms | 1033 ms |

3/3 verdes, sin contención. Los tres números se imprimen por consola en cada
corrida (`[RNF-008] repetición N/3: feedbackMs=... firstStepMs=...`), no solo
pass/fail.

## 4.5. Migración acotada a Vitest 4 (F8-01-R1)

**Autorización:** explícita y acotada para esta sola migración (Vitest 2→4),
sin extenderse a Vitest 5, Node 22, Next 15/16, React 19 ni ESLint 9/10.

### Cadena crítica antes de migrar (Parte 1)

`npm audit --json` (árbol completo): 1 crítica, directa, en `vitest`.

```
vitest@2.1.9 (directa)
 +-- @vitest/mocker@2.1.9
 |    `-- vite@5.4.21
 |         `-- esbuild@0.21.5
 `-- vite-node@2.1.9
      `-- vite@5.4.21 (deduped)
```

CVE real: **GHSA-5xrq-8626-4rwp** — "When Vitest UI server is listening,
arbitrary file can be read and executed", afecta `@vitest/mocker <3.2.6`.
`fixAvailable`: `{"name":"vitest","version":"4.1.10","isSemVerMajor":true}`
— exactamente la versión que se instaló, sin saltar a `latest` a ciegas.

`npm audit --omit=dev --json` (árbol de producción): **0 críticas** ya antes
de migrar — `vitest` es `devDependency`, nunca llega al árbol de producción
ni al bundle servido. La crítica era 100% de tooling de desarrollo.

### Preflight de compatibilidad (Parte 2)

Verificado con `npm view` contra el registro real, no asumido:

| Requisito | Lo que exige `vitest@4.1.10` | Lo que hay en el proyecto | Compatible |
|---|---|---|---|
| Node | `^20.0.0 \|\| ^22.0.0 \|\| >=24.0.0` | Node 20 (local y CI) | ✅ Sí — **Node 20 es suficiente**, no hace falta Node 22 (corrige una advertencia del encargo que asumía lo contrario sin evidencia) |
| Vite | `^6.0.0 \|\| ^7.0.0 \|\| ^8.0.0` (dependencia propia de `vitest`, no solo peer) | `vite@5.4.21` | ❌ Requiere bump — se fijó `vite@^6.4.3` (la línea más baja que satisface tanto a `vitest@4.1.10` como a `@vitejs/plugin-react@4.7.0`, evitando saltar directo a Vite 7/8) |
| `@vitejs/plugin-react` | — | `peerDependencies.vite` de la versión ya instalada (`4.7.0`) es `^4.2.0 \|\| ^5.0.0 \|\| ^6.0.0 \|\| ^7.0.0` | ✅ **Ya soportaba Vite 6 sin cambios** — no se tocó esta dependencia |
| jsdom | `peerDependencies.jsdom: "*"` (cualquier versión) | `jsdom@26.0.0` | ✅ Sin cambios — **no hacía falta jsdom 30** (corrige otra advertencia del encargo sin evidencia real) |
| `@vitest/mocker` | Se instala junto con `vitest`, versión `4.1.10` exacta | — | ✅ Resuelve automáticamente, cierra el CVE (`>=3.2.6` requerido, `4.1.10` instalado) |

`vitest.config.js` no usa `poolOptions`, `minWorkers` ni reporters
personalizados — **confirmado por inspección directa**, tal como anticipaba
el encargo: solo `plugins: [react()]` y `test: { environment, setupFiles,
include, watch: false }`.

### Cambio de dependencias (Parte 3)

`frontend/package.json`:

```diff
-    "vitest": "^2.1.9"
+    "vite": "^6.4.3",
+    "vitest": "4.1.10"
```

`vitest` se fijó **exacto, sin caret** (instrucción explícita: instalar la
versión que `npm audit` reconoce como corrección, no `^4.1.10`). `vite` se
añadió como `devDependency` **directa** (antes solo transitiva, deduplicada
entre `@vitejs/plugin-react` y `vitest`) para que la resolución sea
determinista y no dependa de qué major elija `npm` por su cuenta entre
`^6||^7||^8`. `@vitejs/plugin-react`, `jsdom`, `@testing-library/*` **no se
tocaron** — el árbol demostró que no hacía falta.

Versiones finales resueltas (`npm ls vitest vite esbuild @vitest/mocker`):

```
+-- @vitejs/plugin-react@4.7.0
|    `-- vite@6.4.3 (deduped)
+-- vite@6.4.3
|    `-- esbuild@0.25.12
`-- vitest@4.1.10
     +-- @vitest/mocker@4.1.10
     |    `-- vite@6.4.3 (deduped)
     `-- vite@6.4.3 (deduped)
```

Efecto colateral positivo: `esbuild` pasó de `0.21.5` (vulnerable) a
`0.25.12` (`vite@6.4.3` exige `esbuild@^0.25.0`), cerrando también su propia
advisory moderate sin ninguna acción adicional.

### Pruebas focalizadas representativas (Parte 3)

Ejecutadas **antes** de la suite completa, en este orden, sin ningún ajuste
de código necesario en ninguna:

| # | Foco | Archivo(s) | Resultado |
|---|---|---|---|
| 1 | Infraestructura jsdom/RTL | `tests/unit/infra.smoke.test.jsx` | ✅ 2/2 |
| 2 | Fake timers + `streamRun` | `tests/unit/streamRun.test.js`, `tests/unit/agentPipeline.test.js`, `tests/unit/hooks/useDocumentAutosave.test.jsx` | ✅ 32/32 (`vi.useFakeTimers()`, `vi.advanceTimersByTimeAsync()`, `vi.advanceTimersByTime()` — API sin cambios en v4) |
| 3 | Tiptap / esquema de documento | `tests/unit/document/**` (17 archivos) | ✅ 276/276 |
| 4 | Hooks React en Strict Mode | `tests/unit/hooks/**` (6 archivos) | ✅ 60/60 |
| 5 | Auditor del bundle | `tests/unit/scripts/auditClientBundle.test.js` | ✅ 11/11 |

**Cero incompatibilidades reales de Vitest 4 encontradas** — ninguna
aserción funcional se tocó. `vi.mock()`, `vi.hoisted` implícito (hoisting de
`vi.mock`), `@testing-library/jest-dom/vitest` y la transformación JSX vía
`@vitejs/plugin-react` funcionan igual bajo Vite 6/Vitest 4.

### Suite completa (Parte 3)

`npx vitest run` → **897/897 passed**, 64/64 archivos, idéntico recuento
al de F8-01 (886 previas a F8-01 + 11 del escáner de bundle añadidas en
F8-01). La única salida distinta en consola es ruido esperado de `jsdom`
(`Not implemented: navigation`, un stub conocido de jsdom al simular clic en
un `<a>`, y el error `Badge: status "inventado" no reconocido` que una
prueba deliberadamente dispara y captura) — ninguno es un fallo.

### Efectos verificados fuera de la suite unitaria

`npm run lint` y `NEXT_PUBLIC_BACKEND_URL=... npm run build` se re-ejecutaron
tras el bump y siguen en verde — `vite`/`vitest` son tooling de pruebas,
ajenos al pipeline de build de Next (que usa su propio bundler, no Vite).

## 5. Estrategia de navegador Playwright — local y CI

- **Windows local:** `channel: "chrome"` (sin cambios; workaround necesario
  por el fallo de resolución WinSxS del Chromium embebido, documentado desde
  F1-01).
- **CI (Ubuntu):** ahora `channel: process.env.CI ? undefined : "chrome"` en
  los tres configs (`playwright.config.js`, `playwright.perf.config.js`,
  `playwright.prod.config.js`) — en CI cae a Chromium embebido normal,
  instalado con `npx playwright install --with-deps chromium` (nuevo paso de
  CI). No se instaló Chrome de sistema: no hace falta, Ubuntu no tiene el
  problema que motivó el canal `chrome`.
- `reuseExistingServer: false` se conserva en los tres configs. Todo sigue en
  el puerto 3101.

**Limitación honesta:** esta rama de `channel: undefined` en CI **no se pudo
verificar ejecutando el job de GitHub Actions real** desde esta sesión (sin
acceso a disparar CI) — el razonamiento y el `npx playwright install
--with-deps chromium` están documentados y son el patrón estándar de
Playwright, pero queda `NO VERIFICADO` hasta la primera corrida real del
workflow.

## 6. `ci.yml` — job `frontend` actualizado

Pasos añadidos/reordenados (el job `backend` queda intacto):

1. `npm ci`
2. Lint (ya existía, sin cambios)
3. Unitarias (ya existía, sin cambios)
4. Build (`NEXT_PUBLIC_BACKEND_URL` ahora fijado a nivel de job:
   `https://backend.ci.cuestiondedatos.invalid` — TLD `.invalid` reservado por
   RFC 2606, nunca resuelve; ningún E2E depende de que resuelva porque todos
   interceptan `**/v2/agent/*` con `page.route`)
5. **Auditoría de bundle** (`npm run audit:bundle`, nuevo en F8-01)
6. **Gate de seguridad BLOQUEANTE** (nuevo en F8-01-R1, reemplaza el paso no
   bloqueante de F8-01) — dos verificaciones explícitas, **sin
   `continue-on-error`, sin `|| true`, sin excluir ningún paquete a mano**:
   - `npm audit --omit=dev --audit-level=critical` (árbol de producción)
   - `npm audit --audit-level=critical` (árbol completo, incluido tooling —
     esto es lo que ahora atraparía en CI una futura crítica de `vitest`,
     `eslint` o cualquier dependencia de desarrollo)

   Cualquiera de los dos con una vulnerabilidad `critical` hace fallar el
   job inmediatamente. Las vulnerabilidades `high`/`moderate` **no** hacen
   fallar el job (siguen solo documentadas, §8) — la puerta bloqueante es
   estrictamente sobre `critical`, tal como pide el encargo.
7. Instalación de Chromium para CI (nuevo en F8-01)
8. **E2E funcional** (`npm run test:e2e:functional`, nuevo nombre en F8-01)
9. **E2E RNF-008 dedicado** (`npm run test:e2e:perf`, nuevo en F8-01, paso
   propio para aislar su diagnóstico)
10. **E2E de producción** (`npm run test:e2e:prod`, ya existía como script,
    cableado en CI desde F8-01)
11. Subida de `test-results/` **solo si algo falla** (`if: failure()`), sin
    tokens/`.env` (los tokens que puedan aparecer en trazas son todos
    sintéticos de prueba, nunca reales)

**Cambio exacto del gate (diff conceptual):**

```diff
-      - name: Audit frontend dependencies
-        continue-on-error: true
-        run: npm audit --omit=dev
+      - name: Auditoría de seguridad — árbol de producción (bloqueante en crítico)
+        run: npm audit --omit=dev --audit-level=critical
+
+      - name: Auditoría de seguridad — árbol completo, incluido tooling (bloqueante en crítico)
+        run: npm audit --audit-level=critical
```

Verificado localmente que ambos comandos terminan con código de salida `0`
sobre el árbol actual (§10) — el gate pasaría hoy en un CI real.

## 7. Auditoría de bundle (RNF-011)

`frontend/scripts/audit-client-bundle.mjs` (nuevo) + `npm run audit:bundle`
(nuevo). Escanea únicamente `.next/static/` (`.js`/`.mjs`/`.css`/`.map`),
nunca `.next/server/` ni el resto del árbol. Detecta por **forma del valor**,
nunca por nombre de variable: claves Google/Gemini (`AIzaSy...`), Anthropic
(`sk-ant-...`), OpenAI (`sk-proj-...`/`sk-...`), cadenas de conexión Postgres
con `usuario:contraseña@` embebidos, valores concretos asignados a
`SOCRATA_APP_TOKEN(S)`, y tokens de corrida concretos (`cdt_rt_...`) —
excluyendo explícitamente el literal de detección de `redact.js`
(`cdt_rt_[A-Za-z0-9_-]+`, que sí aparece en el bundle porque ese módulo se
importa desde código cliente). Salida: solo ruta relativa, código fijo,
etiqueta y conteo — **nunca el valor**.

11 pruebas unitarias (`tests/unit/scripts/auditClientBundle.test.js`, contra
bundles sintéticos temporales, nunca contra `.next/` real): detecta cada tipo
de secreto real, confirma que un nombre de variable sin valor no produce
falso positivo, confirma que el literal de `redact.js` no produce falso
positivo, confirma que nunca imprime el secreto, confirma que un bundle
limpio pasa, confirma que ignora extensiones fuera de alcance (imágenes,
fuentes).

**Hallazgo real durante la verificación (no un defecto de la auditoría del
release, sino del propio script):** la primera corrida contra un build de
producción real encontró 1 hallazgo genuino — `lib/gallery/agentDemoScenarios.js`
usaba el token sintético literal `"cdt_rt_demo_token_no_usar"` en el cliente
falso de la demo `/_dev/ui`. No era un secreto real (nunca sale de memoria,
sufijo `no_usar` explícito), pero SÍ tenía la forma de un token de corrida
concreto embebido — exactamente lo que RNF-011 exige que la auditoría de
bundle detecte. Se corrigió quitándole el prefijo real `cdt_rt_` (ahora
`"demo-token-no-usar-nunca-real"`), sin tocar ningún contrato ni comportamiento
funcional (no está referenciado en ninguna prueba ni renderizado en la UI).
Verificado: 897 unitarias siguen en verde, build limpio, `audit:bundle` ahora
da **0 hallazgos** contra el build de producción real.

## 8. `npm audit` — clasificado

**Antes de F8-01:** 28 vulnerabilidades (2 críticas, 22 altas, 4 moderadas).
**Después de F8-01 / antes de F8-01-R1:** 26 (**1 crítica**, 21 altas, 4
moderadas). **Después de F8-01-R1:** 21 (**0 críticas**, 20 altas, 1
moderada) — árbol completo. Árbol de producción (`--omit=dev`): 7 (0
críticas, 6 altas, 1 moderada).

### Aplicado en F8-01 (actualización exacta, compatible, acotada)

| Paquete | Antes | Después | Motivo |
|---|---|---|---|
| `next` | 14.1.3 | **14.2.35** | Cierra **CVE crítico** "Authorization Bypass in Next.js Middleware" (GHSA-f82v-jwr5-mffw) + varios high/moderate propios de la línea 14.x. `npm audit` confirma `fixAvailable` **no-major**. |
| `eslint-config-next` | ^14.1.3 | **^14.2.35** | Mantiene alineación de versión con `next` (convención del propio paquete) |
| `postcss` (devDependency directa) | ^8.4.21 (resolvía 8.5.6) | **^8.5.25** | Cierra 3 advisories high/moderate de XSS/path-traversal en el `postcss` que controla el proyecto (no el interno de `next`, ver abajo). |

### Aplicado en F8-01-R1 (migración mayor autorizada explícitamente)

| Paquete | Antes | Después | Motivo |
|---|---|---|---|
| `vitest` | ^2.1.9 (resolvía 2.1.9) | **4.1.10 (exacto)** | Cierra **CVE crítico** GHSA-5xrq-8626-4rwp en `@vitest/mocker`. Salto mayor **autorizado explícitamente para esta migración únicamente**. Ver §4.5 para el preflight y la migración completos. |
| `vite` (nueva devDependency directa) | — (transitiva, 5.4.21) | **^6.4.3** | Requerido como `dependencies.vite` de `vitest@4.1.10` (no solo peer). Fijada como directa para resolución determinista; es la línea más baja (6.x) que satisface a la vez a `vitest@4.1.10` (`^6\|\|^7\|\|^8`) y a `@vitejs/plugin-react@4.7.0` (`^4.2\|\|^5\|\|^6\|\|^7`) — no se saltó a Vite 7/8. |
| `esbuild` (transitiva, sin tocar directamente) | 0.21.5 | **0.25.12** | Efecto colateral de `vite@6.4.3` (exige `esbuild@^0.25.0`); cierra su propia advisory moderate sin acción adicional. |

### No aplicado — requiere salto de versión mayor NO autorizado (fuera de política)

| Paquete | Vulnerabilidad | Fix disponible | Por qué no se aplicó |
|---|---|---|---|
| `eslint` + toda la cadena `@eslint/eslintrc`/`minimatch`/`glob`/`rimraf`/`brace-expansion`/etc. (~11 paquetes "high") | Varias (ReDoS, path-traversal) | `eslint@10.8.0` (mayor) | Dev-only. ESLint 9+/10 exige flat config — explícitamente fuera de política, no autorizado en esta ronda. |
| `next` (residual, distinto del crítico ya cerrado en F8-01) + `postcss` interno de `next@14.2.35` (`node_modules/next/node_modules/postcss@8.4.31`) | Varias high/moderate/low solo cerradas en Next 15.5.x+ | `next@16.2.12` (mayor) | Explícitamente fuera de política ("no Next 15/16"). El `postcss` interno de Next es una dependencia propia de Next, no controlable sin ese salto — no es superficie de ataque runtime del bundle servido (es herramienta de build). |
| `eslint-plugin-react`, `linkify-it`, `lodash-es`, `picomatch`, `preact`, `markdown-it` | Varias, `fixAvailable: true` (sin forzar mayor en un padre directo) | resoluble por `npm audit fix` | **No se ejecutó `npm audit fix`** (prohibido explícitamente). Son transitivas de dependencias legacy pesadas (`react-globe.gl`, `reactflow`, `three`, `katex`, etc.) candidatas a retiro masivo en F9. No se usaron `overrides` inseguros. |

Ninguno de los paquetes de esta tabla es `critical` — todos son `high` o
`moderate`, así que **no bloquean** el gate de CI de F8-01-R1 (§6), que solo
falla ante `critical`. Quedan documentados como deuda conocida, no oculta.

### Clasificación de riesgo (post F8-01-R1)

- **Riesgo del artefacto servido** (`npm audit --omit=dev`): **0 críticas, 6
  altas, 1 moderada** — todas por `next`/`postcss` residual (requieren
  Next 15/16, fuera de política) y son herramienta de build de Next, no
  código que llega al navegador más allá de lo que Next ya empaqueta
  (verificado limpio por `audit:bundle`, §7).
- **Riesgo del tooling** (dev-only: `eslint` y su cadena, más las 6
  transitivas de dependencias legacy pesadas): **0 críticas, ~14 altas, 1
  moderada** — ninguna alcanzable desde `/app` en producción.

### Gate de seguridad — RESUELTO

La vulnerabilidad crítica (`vitest`) que dejó F8-01 bloqueada **se eliminó**
en esta ronda. `npm audit --audit-level=critical` (árbol completo) y
`npm audit --omit=dev --audit-level=critical` (árbol de producción) terminan
ambos con código de salida `0` — **cero críticas en cualquiera de los dos
árboles** (§10). El gate de CI ahora bloquea automáticamente si una futura
dependencia introduce una crítica nueva (§6).

## 9. Impeccable — auditoría en `/app`

`node .claude/skills/impeccable/scripts/context.mjs --target frontend/pages/app.js`
ejecutado una vez, seguido de `npx impeccable detect` sobre `pages/app.js` +
todos los subdirectorios de `components/` de v2 (`agent`, `document`,
`evidence`, `canvas`, `consent`, `history`, `ui`) y `styles/`.

**Resultado sobre superficies v2 puras: 0 antipatrones.**

El detector sí encontró 6 antipatrones al escanear `components/` completo,
pero los 6 pertenecen exclusivamente al **frontend legacy** (`components/copilot/CopilotSidebar.js`,
`components/wizard/ApiStep.js`, `components/wizard/IntroStep.js` — ya
documentados como deuda no corregida desde el baseline de F0, fuera de
alcance por `CLAUDE.md`/`AGENTS.md`: "el frontend legacy permanece intacto").
El único hallazgo en un archivo v2 (`styles/tokens.css:9`, patrón
`gray-on-color`) se verificó en contexto y es un **falso positivo**: el
detector coincidió con el texto de un comentario que documenta, a modo de
ejemplo, las clases Tailwind del legacy (`bg-blue-700`, `text-slate-600`) —
no hay ninguna combinación real de esas clases en markup. No se corrigió
nada (nada que corregir dentro del alcance de F8-01); no se rediseñó nada;
no se generaron imágenes; no se agregó ningún ignore.

## 10. Validación final ejecutada (F8-01-R1, una sola vez, tras las focalizadas)

| Comando | Resultado |
|---|---|
| `npm run lint` | ✅ verde (mismas advertencias preexistentes del legacy documentadas en `frontend/README.md`, cero errores) |
| `npm run test` (Vitest **4.1.10**) | ✅ **897/897**, 64/64 archivos — idéntico recuento a F8-01, cero pruebas modificadas por la migración |
| `npm run build` | ✅ verde |
| `npm run audit:bundle` | ✅ 0 hallazgos (24 archivos escaneados en `.next/static/`) |
| `npm audit --omit=dev --audit-level=critical` | ✅ **exit 0 — 0 críticas** |
| `npm audit --audit-level=critical` | ✅ **exit 0 — 0 críticas** |
| `npm run test:e2e` (funcional + RNF-008 dedicado, secuencial) | ✅ **86 + 3 = 89 passed**, 0 failed |
| `npm run test:e2e:prod` | ✅ 2/2 passed |
| `npm ls vitest vite esbuild @vitest/mocker` | `vitest@4.1.10`, `vite@6.4.3` (deduplicado en los 3 consumidores), `esbuild@0.25.12`, `@vitest/mocker@4.1.10` |
| `git diff --check` | ✅ limpio (solo advertencia de fin de línea LF/CRLF en `CLAUDE.md`, archivo preexistente no tocado por esta sesión) |

Además, específicamente para F8-01-R1: `external-sources-f7-02b.spec.js` +
`manual-entry-f7-02a.spec.js` re-ejecutados focalizadamente con
`--workers=1` tras ampliar el set de tags de axe → **7/7 passed**.

Cierre de puerto y procesos: **3101 libre** tras cada corrida (confirmado con
`netstat`, solo conexiones `TIME_WAIT` residuales normales, ninguna
`LISTENING`); **cero `chrome.exe` huérfano**; **3000 intacto**, nunca
inspeccionado ni tocado; `npm ci` (el comando real que usa CI) verificado en
verde contra el `package-lock.json` actualizado.

## 11. Archivos tocados

**Nuevos en F8-01:**
- `frontend/playwright.perf.config.js`
- `frontend/tests/e2e-perf/rnf008.spec.js`
- `frontend/tests/e2e/app-terminal-states-f8-01.spec.js`
- `frontend/tests/e2e/app-esc01-integral.spec.js`
- `frontend/scripts/audit-client-bundle.mjs`
- `frontend/tests/unit/scripts/auditClientBundle.test.js`
- `docs/frontend-v2/release/f8-01-automated-gates.md` (este documento)

**Modificados en F8-01:**
- `frontend/tests/e2e/agent-demo.spec.js` (RNF-008 movido a spec dedicado; axe añadido al estado "streaming")
- `frontend/playwright.config.js` (canal condicional CI/local)
- `frontend/playwright.prod.config.js` (canal condicional CI/local)
- `frontend/package.json` (scripts `test:e2e:*`/`audit:bundle`; `next`→14.2.35; `eslint-config-next`→^14.2.35; `postcss`→^8.5.25)
- `frontend/package-lock.json` (vía `npm install`)
- `frontend/lib/gallery/agentDemoScenarios.js` (token sintético sin prefijo real, hallazgo del propio `audit:bundle`)
- `.github/workflows/ci.yml` (job `frontend`: pasos nuevos; job `backend` intacto)

**Modificados en F8-01-R1:**
- `frontend/package.json` (`vitest` `^2.1.9`→**`4.1.10`** exacto; `vite` **añadida** `^6.4.3`)
- `frontend/package-lock.json` (vía `npm install`, ver §4.5)
- `.github/workflows/ci.yml` (job `frontend`: los dos gates bloqueantes de `npm audit --audit-level=critical` reemplazan el paso `continue-on-error`, ver §6; job `backend` intacto)
- `frontend/tests/e2e/external-sources-f7-02b.spec.js` (axe con set completo de tags)
- `frontend/tests/e2e/manual-entry-f7-02a.spec.js` (axe con set completo de tags)
- `docs/frontend-v2/release/f8-01-automated-gates.md` (este documento)

**Preexistentes, preservados sin tocar:** todo el resto del árbol
`frontend/` (incluidas las ediciones ya presentes en `.github/workflows/ci.yml`
antes de F8-01, `next.config.js`, `pages/_app.js`, `styles/globals.css`,
`tailwind.config.js`, que no pertenecen a este trabajo). `vitest.config.js`
y `tests/setup.js` **no se tocaron** — el preflight de F8-01-R1 confirmó que
no había ninguna opción removida ni deprecada de Vitest 4 en uso (§4.5).

## 12. Limitaciones MCP y ambientales

`codebase-memory-mcp` se consultó al inicio de F8-01-R1 (`index_status`,
`search_code` para localizar todos los consumidores de `from "vitest"`) —
el índice sigue apuntando al commit `5853251` (HEAD real de la rama), así
que no conoce los archivos nuevos creados sin commitear en F8-01 (p. ej.
`app-terminal-states-f8-01.spec.js`, `audit-client-bundle.mjs`); para esos
se usó lectura directa, sin que representara una limitación real dado que
son archivos de esta misma sesión. No se reindexó (la tarea no lo requería).
Sin incidentes de `EPERM` en la caché de npm en Windows durante ninguna de
las instalaciones de esta ronda — no fue necesaria una caché temporal
alterna.

## 13. Deudas y bloqueos reales

Ninguna deuda de F8-01 sigue bloqueando tras F8-01-R1. Quedan documentadas,
no bloqueantes:

1. **No verificado en CI real:** la rama `channel: undefined` en Ubuntu (§5)
   y los dos gates bloqueantes nuevos (§6) — razonamiento sólido y patrón
   estándar, verificados en verde localmente, pero sin una corrida real del
   workflow de GitHub Actions desde esta sesión.
2. **Zoom real al 200%:** declarado explícitamente pendiente para F8-02
   desde F1-01; no se fabricó ninguna prueba sustituta.
3. **Legacy (`/`):** 6 antipatrones de Impeccable sin corregir, documentados
   desde F0, fuera de alcance por instrucción explícita.
4. **`high`/`moderate` residuales documentados** (§8): ninguno crítico,
   ninguno bloquea el gate de CI; requieren saltos de versión mayor no
   autorizados (Next 15/16, ESLint 9/10) o pertenecen a dependencias legacy
   candidatas a retiro en F9.

## 14. Qué queda explícitamente para F8-02

- Revisión manual de accesibilidad WCAG 2.2 AA con teclado real, **lector de
  pantalla real (NVDA/VoiceOver)**, **zoom real al 200%** y reflujo — acta en
  `docs/release-wcag-<version>.md` (no fabricada en este incremento).
- Revisión manual RNF-012 (idioma/claridad en español) — acta en
  `docs/release-rnf-012-<version>.md` (no fabricada en este incremento).
- Cierre formal de T-505 (requiere las dos actas anteriores).

---

**F8-01-R1 cierra el veredicto de las puertas automatizables de F8-01 en
READY** (cero críticas, gate bloqueante real en CI, axe completo). Esta
sesión **no fabricó** revisión manual, **T-505 sigue abierto**, **RNF-007 y
RNF-012 siguen requiriendo revisión humana**, y **F8-02 no comenzó**.

## 15. Adenda de cierre posterior — 2026-07-30

F8-02 produjo y aprobó las actas manuales WCAG 2.2 AA y RNF-012 para
`v2.0.0-rc1`. Después de publicar el candidato, GitHub Actions CI #64 ejecutó
el commit `de4b999fd1d12f54ce6001c9a0c78c8f5acddcfd`: los jobs Backend y
Frontend terminaron en `success`, incluido el E2E funcional, RNF-008 aislado
y E2E de producción. Con esta evidencia remota y las dos actas, **T-505 queda
cerrada**. Esta adenda no reescribe el estado histórico que tenía F8-01-R1 al
momento de emitirse.
