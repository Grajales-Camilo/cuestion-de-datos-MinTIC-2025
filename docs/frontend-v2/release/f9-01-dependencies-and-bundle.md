# F9-01 — Limpieza de dependencias y medición de bundle

**Fecha:** 2026-07-30
**Rama:** `feat/frontend-v2`
**Commit inicial:** `4a07894`
**PR:** [#28](https://github.com/Grajales-Camilo/cuestion-de-datos-MinTIC-2026/pull/28) (borrador, contra `v2`)
**Alcance:** exclusivamente F9-01 (limpieza de dependencias, medición de
bundle, preparación documental de T-702, diagnóstico de solo lectura del
fallo de Vercel). No se tocó backend, contratos, D-6, T-702 ni T-704.

**Revisión F9-01-R1 (2026-07-30):** corrección documental exclusiva sobre
esta entrega ya auditada. No se modificó código, `package.json`,
`package-lock.json`, `pages/_app.js`, pruebas, configuración de Vercel ni
estado remoto; no se ejecutó ninguna suite completa, build ni E2E nuevos
para esta revisión (salvo la reproducción aislada registrada en la sección
6.1). Cambios de esta revisión: aclaración de que eran 10 dependencias
candidatas (§2), sustitución de las cifras de bundle por bytes exactos
confirmados por auditoría independiente (§5.2), nueva sección de
diagnóstico Vercel confirmado (§7), precaución adicional sobre versión de
Next / comando de build detectados por Vercel (§8), y corrección de la
lista de archivos propios de F9 (§9).

## 1. Entorno

| Campo | Valor |
|---|---|
| Node.js | v24.18.0 |
| npm | 11.6.0 |
| Rama | `feat/frontend-v2` |
| Commit inicial | `4a07894` |
| Working tree en `frontend/` | Limpio al inicio (sin cambios pendientes) |

## 2. Auditoría de uso real de las 10 dependencias candidatas

**Aclaración (F9-01-R1):** el encargo original nombró 9 paquetes candidatos
a retiro. La verificación de uso real incorporó un décimo caso relevante —
`react-joyride` — porque decidir si se retiraba o se conservaba exigía la
misma auditoría de consumidores que los otros 9. De las 10 dependencias
evaluadas en esta sección, **9 fueron retiradas** y **1 (`react-joyride`)
fue conservada, diferida hasta T-704** (última fila de la tabla).

Metodología por paquete: búsqueda literal de `import` estático, `require()`,
`import()` dinámico, imports CSS, referencias en `pages/api/*`, consumo desde
el frontend legacy y consumo transitivo necesario por otra dependencia
conservada (`npm ls <paquete>`). Ningún hallazgo se basó solo en mirar
`/app`.

| Paquete | Uso encontrado | Evidencia | Resultado | Motivo |
|---|---|---|---|---|
| `@google/generative-ai` | Ninguno | Búsqueda de `from/require/import()` en todo `frontend/` (excl. `node_modules`): 0 coincidencias fuera de `package.json`/`package-lock.json`. `pages/api/consultar_v2.js` (legacy, se conserva hasta T-704) llama a Gemini con `fetch()` directo a la API REST, **no** con el SDK. | **Retirada** | Sin consumidor necesario. Contradice la advertencia del plan F9, que asumía un posible uso desde `consultar_v2.js`: se verificó el archivo línea por línea y no importa el paquete. |
| `three` | Ninguno directo | 0 coincidencias de `import 'three'` en código fuente. Solo aparecía como dependencia transitiva de `react-globe.gl` (`npm ls three` → deduplicado bajo `globe.gl`/`three-globe`). | **Retirada** | Su único consumidor real (`react-globe.gl`) también se retira. |
| `react-globe.gl` | Ninguno | 0 coincidencias de import/require/CSS. | **Retirada** | Sin consumidor. |
| `d3` | Ninguno | 0 coincidencias de `d3.` ni imports. | **Retirada** | Sin consumidor. |
| `reactflow` | Ninguno | 0 coincidencias de `ReactFlow`/imports. | **Retirada** | Sin consumidor. |
| `katex` | Solo un import CSS muerto: `import 'katex/dist/katex.min.css'` en `pages/_app.js:6`. Ningún componente renderiza fórmulas (no hay uso de `react-katex` ni de la API de `katex`). | `pages/_app.js` (antes de editar) | **Retirada** (paquete + línea de import CSS) | Import CSS realmente muerto: nada en el árbol de componentes produce marcado que dependa de esas clases. Retirarlo no altera funcionalidad vigente. |
| `react-katex` | Ninguno | 0 coincidencias de `InlineMath`/`BlockMath`/import. | **Retirada** | Sin consumidor. |
| `@fortawesome/free-solid-svg-icons` | Ninguno | 0 coincidencias de `FontAwesomeIcon`/`fontawesome`. | **Retirada** | Sin consumidor. Plan §7 exige una sola familia de iconos (Lucide), ya en uso. |
| `@fortawesome/react-fontawesome` | Ninguno | Igual que arriba. | **Retirada** | Sin consumidor. |
| `react-joyride` | **Sí**: `components/common/OnboardingTour.js:2` (`import Joyride, { ACTIONS, EVENTS, STATUS } from 'react-joyride'`), cargado con `next/dynamic({ssr:false})` desde `components/canvas/PolicyCanvasMain.js:11`, que a su vez se usa desde `pages/index.js:7,191` (entrada del **frontend legacy**, intacta hasta T-704). | `components/common/OnboardingTour.js`, `components/canvas/PolicyCanvasMain.js`, `pages/index.js` | **Conservada — diferida hasta T-704** | Regla fail-closed: tiene un consumidor necesario mientras `pages/index.js` siga vigente. El plan F9 (implementation-plan.md §14, aceptación de F9) la listaba como "tour fuera de alcance" retirable sin haber verificado este uso; se reporta la discrepancia en la sección 6. |

`framer-motion` (no es una de las 9 candidatas, pero el encargo pide no
tocarla) se confirmó en uso real: `components/wizard/HelpStep.js`,
`ApiStep.js`, `DatabaseStep.js`, `IntroStep.js` y `pages/index.js`. No se
retiró, como indicaba el encargo.

## 3. Limpieza ejecutada

```bash
npm uninstall @google/generative-ai three react-globe.gl d3 reactflow katex react-katex @fortawesome/free-solid-svg-icons @fortawesome/react-fontawesome
```

Además se eliminó la línea muerta `import 'katex/dist/katex.min.css'` de
`pages/_app.js` (sin ese paquete instalado, esa línea rompería el build).

**Archivos tocados:** `frontend/package.json`, `frontend/package-lock.json`,
`frontend/pages/_app.js`.

No se actualizó ninguna versión de dependencias conservadas. No se ejecutó
`npm audit fix` ni `--force`. No se modificó Next, React, Tiptap, Chart.js,
docx, Vitest, Vite, Playwright, Lucide, Tailwind ni Testing Library.

### Confirmación con `npm ls`

Las 9 dependencias retiradas desaparecen por completo del árbol (ni siquiera
quedan transitivas):

```
npm ls d3 three react-globe.gl reactflow katex react-katex @fortawesome/free-solid-svg-icons @fortawesome/react-fontawesome @google/generative-ai
`-- (empty)
```

Las diferidas siguen presentes como se esperaba:

```
npm ls react-joyride framer-motion
+-- framer-motion@12.23.24
`-- react-joyride@2.9.3
```

## 4. Dependencias directas y transitivas — antes/después

| Métrica | Antes (pre-F9) | Después (post-F9) | Diferencia |
|---|---:|---:|---:|
| Dependencias directas (`dependencies`) | 24 | 15 | −9 (−37.5 %) |
| Paquetes resueltos totales (`package-lock.json`, incl. transitivos) | 834 | 717 | −117 (−14.0 %) |

## 5. Comparación de bundle

### 5.1 Baseline F0 (referencia histórica, commit `5853251`, 2026-07-27 — solo legacy, antes de F1–F8)

| Métrica | Valor |
|---|---|
| Ruta `/` | 168 kB / First Load 247 kB |
| First Load JS compartido | 94.4 kB |
| `.next/static` | 2.3 MB |
| `.next` total | 47 MB |

Esta cifra **no es comparable directamente** con las de hoy: entre F0 y F9-01
se implementaron F1–F8 completos (ruta `/app`, sistema de diseño, Tiptap,
export `.docx`, etc.), que añaden peso legítimo por funcionalidad nueva, no
por deuda de dependencias.

### 5.2 Pre-F9-01 vs. post-F9-01 (comparación válida para este incremento, mismo commit base `4a07894`, build limpio antes/después de la limpieza)

**Nota metodológica (F9-01-R1):** las cifras de `.next/static` y `.next`
total publicadas originalmente en F9-01 se midieron con `du -sh`
(redondeadas por el sistema a la décima de MB), lo que produce porcentajes
calculados sobre dos valores ya redondeados. Esta corrección las sustituye
por el conteo exacto de bytes confirmado por auditoría independiente sobre
el mismo build post-limpieza. `First Load JS compartido` y el CSS compartido
se dejan expresados en kB porque esa es la unidad que emite directamente la
salida de `next build`; no se recalculan aquí en bytes exactos valores que
Next no expone con esa precisión.

| Métrica | Pre-F9-01 | Post-F9-01 | Diferencia | % (sobre valor exacto) |
|---|---:|---:|---:|---:|
| Ruta `/` | 54.3 kB / First Load 251 kB | 54.3 kB / First Load 251 kB | Sin cambio | — |
| Ruta `/app` | 22.5 kB / First Load 306 kB | 22.5 kB / First Load 306 kB | Sin cambio | — |
| First Load JS compartido (kB, salida de `next build`) | 99.1 kB | 95.3 kB | −3.8 kB | no recalculado en bytes |
| — de eso, CSS compartido (kB, salida de `next build`) | 18.0 kB | 14.2 kB | −3.8 kB | no recalculado en bytes |
| `.next/static` (bytes exactos, auditoría independiente) | 3,005,178 B | 1,903,495 B | **−1,101,683 B** | **−36.66 %** |
| `.next` total (bytes exactos, auditoría independiente) | 89,799,349 B | 86,394,370 B | **−3,404,979 B** | **−3.79 %** |

**Origen real de la reducción de `.next/static`:** la auditoría independiente
determinó que la mayor parte de la reducción proviene de **60 archivos de
fuentes de KaTeX** (`.woff`/`.woff2`/`.ttf`, referenciados por reglas
`@font-face` dentro de `katex/dist/katex.min.css` y copiados por Next al
resolver ese CSS), con **1,076,572 bytes** en conjunto — no de chunks de
JavaScript de las otras 8 dependencias retiradas, que nunca estuvieron
incluidas en ningún bundle servido (sección 2: cero consumidores reales, por
lo que Webpack nunca las empaquetó). El resto de la reducción de
`.next/static` (1,101,683 − 1,076,572 = 25,111 bytes) corresponde al CSS
global más ligero tras eliminar `import 'katex/dist/katex.min.css'` de
`pages/_app.js`. No se atribuye ninguna parte de esta reducción a `three`,
`d3`, `react-globe.gl`, `reactflow`, `react-katex` ni los paquetes de
`@fortawesome/*`: su retiro reduce la superficie de instalación
(`node_modules`, `package-lock.json`) y la auditoría de dependencias
vulnerables (sección 5.4), no el bundle servido.

**Por qué el JS por ruta no cambió:** las 8 dependencias sin ningún
consumidor real (todas menos `katex`) nunca estuvieron incluidas en el
bundle de ninguna ruta — Next/Webpack solo empaqueta lo que se importa. Eran
peso "fantasma" en `package.json` y `node_modules`, no peso servido al
navegador; su retiro no podía cambiar el tamaño de `/` ni `/app`. `katex` sí
tuvo un efecto real y medible, aunque indirecto vía activos estáticos y no
vía JavaScript por ruta (ver párrafo anterior). La reducción real y medible
de este incremento es, por tanto, de **activos estáticos servidos** (fuentes
muertas de KaTeX) y de **superficie de instalación y auditoría** (−14 % en
paquetes resueltos del lockfile, 2 paquetes vulnerables menos — sección
5.4).

### 5.3 `docx` permanece en chunk dinámico

Confirmado tras el build post-limpieza: `docx` solo aparece en el chunk
numerado `.next/static/chunks/837.<hash>.js` (split dinámico de Webpack) y en
la referencia de `import()` dentro de `pages/app-<hash>.js` — nunca en
`framework-*.js` ni `main-*.js`. Esto coincide con
`lib/document/exportDocx.js`, cuyo comentario documenta la carga perezosa, y
con la llamada real `await import("../../lib/document/exportDocx.js")` en
`components/document/ExportDocumentButton.jsx:69`. Sin cambios respecto al
comportamiento anterior a F9-01.

### 5.4 `npm audit`

| Árbol | Pre-F9-01 | Post-F9-01 |
|---|---|---|
| Producción (`--omit=dev`) | 0 críticas, 6 altas, 1 moderada (7 total) | 0 críticas, 4 altas, 1 moderada (5 total) |
| Completo | 0 críticas, 20 altas, 1 moderada (21 total) | 0 críticas, 18 altas, 1 moderada (19 total) |

Paquetes vulnerables que salieron del árbol completo tras la limpieza:
`lodash-es`, `preact` (transitivos de `react-globe.gl`/`globe.gl`, ya
retirado). El resto de hallazgos (`next`, `eslint*`, `postcss`, `glob`,
`minimatch`, `markdown-it`, etc.) es ajeno a las 9 dependencias de F9-01 y
sigue abierto como D-SEC-01.

**Discrepancia observada, no corregida:** estas cifras (7/21 antes de F9-01)
difieren sustancialmente de las registradas el mismo día en
`docs/frontend-v2/release/deudas-no-bloqueantes-v2.0.0-rc1.md` (52 prod / 78
completo). `npm audit` consulta una base de datos de avisos en línea que
cambia entre ejecuciones sin que el árbol de dependencias local varíe; no se
ejecutó `audit fix` ni se modificó ninguna versión para explicar la
diferencia. Se documenta como deuda ambiental de D-SEC-01, no se investiga
más a fondo en este incremento.

### 5.5 Auditoría de secretos en el bundle (`npm run audit:bundle`)

Ejecutada antes y después de la limpieza:

```
Auditoría de bundle cliente (RNF-011): .next\static
Archivos escaneados: 24
Sin hallazgos. 0 patrones de secreto detectados.
```

Sin tokens, `Authorization` ni claves de proveedor en el bundle cliente, en
ambos estados.

## 6. Discrepancia del plan no normativo frente al alcance vigente

`docs/frontend-v2/implementation-plan.md` §14 (aceptación de F9) lista
`react-joyride` como "tour fuera de alcance" retirable junto con las otras 8
dependencias. La verificación de código (sección 2) muestra que **sí tiene un
consumidor necesario**: `OnboardingTour.js` → `PolicyCanvasMain.js` →
`pages/index.js`, todos parte del frontend legacy que el propio plan (árbol
de archivos objetivo, §4.2) marca como intacto hasta T-704. Se aplicó la
regla fail-closed del encargo: no se retiró. Este documento (no normativo,
según AGENTS.md) queda desalineado con el código real en ese punto; se
reporta aquí en lugar de modificar el plan sin autorización.

## 6.1 Validación final (una sola corrida, orden del encargo)

| Comando | Resultado |
|---|---|
| `npm run lint` | Verde. Solo advertencias preexistentes ya documentadas en `frontend/README.md` (comillas sin escapar en 3 archivos legacy, `<img>` sin `next/image`, una dependencia de hook) |
| `npm run test` | Verde. 899/899 pruebas, 64 archivos |
| `npm run build` | Verde. Ver tamaños en la sección 5.2 (post-F9-01) |
| `npm run audit:bundle` | Verde. 24 archivos escaneados, 0 patrones de secreto |
| `npm audit --omit=dev --audit-level=critical` | Verde. 0 críticas (5 total: 4 altas, 1 moderada — sección 5.4) |
| `npm audit --audit-level=critical` | Verde. 0 críticas (19 total: 18 altas, 1 moderada — sección 5.4) |
| `npm run test:e2e` (funcional + perf) | **Ver nota de flake abajo.** Perf: 3/3 verde (RNF-008, feedback 81–153 ms, primer paso ~1 s). Funcional: 87/88 en la corrida completa paralela; el 1 caso (`app-esc01-integral.spec.js`) se reprodujo **verde en aislamiento con 1 worker** (11.6 s, timeout de 30 s) — ver nota |
| `npm run test:e2e:prod` | Verde. 2/2 (`/_dev/ui` → 404 en producción, `/app` → 200 con `lang="es"` y sin secretos en el HTML) |
| `git diff --check` | Sin errores (solo aviso informativo de conversión LF→CRLF de Git en Windows) |

**Nota sobre el único fallo observado en E2E:** en la corrida completa
(`fullyParallel: true`, 88 pruebas elegibles para ejecución paralela)
`app-esc01-integral.spec.js` superó el timeout de 30 s. Este archivo no
tenía historial de flake documentado (a diferencia de RNF-008/D-PERF-01). Se
ejecutó de forma aislada con `node scripts/run-e2e.mjs
tests/e2e/app-esc01-integral.spec.js --workers=1`, un caso concreto y
barato, no la suite completa: pasó en 11.6 s, muy por debajo del límite.
Ninguna de las 10 dependencias auditadas (sección 2) tiene relación con esta
prueba (RF-802/consentimiento, SSE, evidencia, DOCX). Se atribuye a
contención de paralelismo local, consistente con el patrón ya conocido en
D-PERF-01.

**Reproducción independiente (F9-01-R1):** una segunda ejecución aislada del
mismo caso, realizada por separado como parte de esta corrección
documental, confirma el resultado: `app-esc01-integral.spec.js` →
**1/1 verde**, **12.9 s**, con el puerto 3101 verificado **libre antes y
después** de la corrida. Ninguna de las dos reproducciones modificó
timeouts, `workers`, `retries` ni el contenido de la prueba; se documenta
aquí en vez de repetir la suite completa sin causa nueva.

## 7. Diagnóstico Vercel confirmado (F9-01-R1)

Evidencia adicional revisada en esta corrección documental sobre el mismo
deployment ya referenciado en F9-01, esta vez con acceso a los logs de
build (no disponibles durante la sesión original, que solo tenía el
metadato del comentario del bot en el PR):

| Campo | Valor confirmado |
|---|---|
| Deployment | `dpl_EXv2Wsqsd5ULxAut7m5N9oWGy5kh` |
| Estado | `ERROR` |
| `errorCode` | `missing_pages_app` |
| Directorio de ejecución de `next build` | `/vercel/path0` |
| Error exacto (resumen) | Next.js no encontró un directorio `pages` ni `app` bajo la raíz de ejecución (`/vercel/path0`) |
| Metadato del bot de Vercel (comentario del PR #28) | `isMonorepo: true`, `rootDirectory: null` |
| Estructura real del repositorio | `frontend/pages/` existe; no hay `pages/` ni `app/` en la raíz del repositorio |

**Causa confirmada:** con `rootDirectory: null`, Vercel ejecuta `next build`
en `/vercel/path0` (la raíz del repositorio clonado), donde no existe ni
`pages/` ni `app/` — ambos viven en `frontend/`. Esto coincide exactamente
con `errorCode: missing_pages_app`. Fijar **Root Directory = `frontend/`**
en la configuración del proyecto Vercel es la corrección necesaria para
este error específico, pero es una **remediación pendiente de ejecución**:
no se cambió ninguna configuración remota en este incremento. Su **resultado
posterior sigue sin verificarse** — ver la precaución de la sección 8 antes
de asumir que corrige el despliegue por completo.

## 8. Precaución adicional antes de un futuro redeploy (no ejecutada)

Los mismos logs muestran que Vercel detectó **Next.js 14.1.3** y ejecutó el
script `npm run vercel-build`, mientras que `frontend/package.json` declara
`"next": "14.2.35"` y solo define el script `"build": "next build"` (no
existe `vercel-build`). Esto indica que el proyecto Vercel tiene overrides
de **Build Command** y/o **Install Command**, y posiblemente detectó una
versión de Next distinta de la que hoy vive en el repositorio — no es un
efecto de la limpieza de dependencias de F9-01/F9-01-R1, que no tocó `next`.

Antes de cualquier futuro intento de despliegue, **con autorización previa
del usuario y sin ejecutarlo en este incremento**, se deben:

- Inspeccionar los overrides de **Build Command** / **Install Command** en
  Project Settings del proyecto Vercel y normalizarlos al comportamiento
  por defecto de Next.js (`npm ci` / `next build`), o documentar
  explícitamente por qué difieren si es intencional.
- Decidir de forma explícita si se descarta la caché de build de Vercel
  antes del siguiente intento — una caché asociada a Next 14.1.3 podría
  interferir con un build bajo 14.2.35.

**No se afirma que fijar Root Directory por sí solo resuelva el
despliegue.** Corrige el `errorCode: missing_pages_app` confirmado en la
sección 7, pero el desajuste de versión de Next y de comando de build es una
causa independiente, todavía no verificada, que puede seguir bloqueando el
build incluso después de corregir Root Directory. Ninguna de las dos
correcciones se ejecutó en este incremento; su efecto real solo puede
confirmarse con una nueva prueba (un redeploy), fuera de alcance de
F9-01/F9-01-R1.

## 9. Confirmaciones de alcance

- No se tocó backend, contratos, fixtures reales, golden suites ni
  documentos normativos.
- No se inició T-702, T-704 ni D-6.
- No se modificaron los 55 archivos untracked de `backend/eval/reports/` ni
  documentos históricos untracked de `docs/`.
- No se usó `git add -A`; no hubo `git add`, commit, push, merge ni cambio
  remoto, ni en F9-01 ni en esta corrección F9-01-R1.
- **Archivos propios de F9** (F9-01 + F9-01-R1), completos:
  1. `frontend/package.json`
  2. `frontend/package-lock.json`
  3. `frontend/pages/_app.js`
  4. `frontend/README.md`
  5. `docs/frontend-v2/release/f9-01-dependencies-and-bundle.md`
  6. `docs/frontend-v2/release/t-702-vercel-deployment-checklist.md`

  F9-01-R1 solo modificó los archivos 5 y 6 de esta lista; los archivos 1–4
  no se tocaron en esta corrección documental.
