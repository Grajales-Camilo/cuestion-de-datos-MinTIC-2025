# Plan de arranque y desarrollo — Frontend v2 (Cuestión de Datos)

**Tipo de documento:** planificación técnica ejecutable · **NO normativo**
**Fecha:** 2026-07-25 · **Autor:** sesión de auditoría y planificación (Claude Code)
**Rama observada:** `feat/t617-gate-preflight` · **HEAD observado:** `fa08ee5`
**Jerarquía:** este documento se subordina a `specs/constitution.md` > `spec.md` > `research.md` > `plan.md` > `contracts/` > `data-model.md` > `pruebas.md` > `tasks.md`. Donde este plan y un documento normativo discrepen, **gana el normativo** y la discrepancia queda anotada aquí como decisión abierta.

> **Alcance de la sesión que produjo este documento:** solo auditoría y planificación. No se modificó ningún archivo del proyecto, no se instaló ninguna dependencia, no se creó rama ni commit, no se ejecutó el backend ni el frontend. El único archivo nuevo es este.

---

## 1. Resumen ejecutivo

### 1.1 Qué se va a construir

Un frontend v2 **nuevo**, construido desde cero sobre el proyecto Next.js existente (`frontend/`, Pages Router, React 18, Tailwind 3, Tiptap 3), que consume **directamente desde el navegador** el backend FastAPI del **núcleo determinista** vía `NEXT_PUBLIC_BACKEND_URL`, sin proxy en Next.js (plan.md §11, research.md §6). El frontend v2 implementa ESC-01…05 y ESC-08; RF-101…104, RF-204, RF-209, RF-401…404, RF-501…503, RF-801…804; RNF-007, RNF-008, RNF-011, RNF-012.

"Desde cero" significa: **código de aplicación nuevo** (cliente REST/SSE, estado, copiloto, evidencia, canvas, citas, aporte manual). Se reutiliza el **andamiaje** (proyecto Next, Tailwind, Tiptap, Chart.js, PapaParse) porque tirarlo violaría Art. III (YAGNI) sin ganancia; se reutiliza **muy poco código legacy** (§3).

### 1.2 Los cinco hallazgos que cambian el plan

La auditoría del código real (no solo de los contratos) encontró cinco divergencias entre `contracts/api-rest.md` y lo que el runtime determinista **realmente emite hoy**. Ninguna estaba documentada como riesgo de frontend. Las cinco condicionan el diseño:

| # | Hallazgo | Evidencia en código | Impacto en el frontend |
|---|---|---|---|
| **H1** | `evidence[].columns` y las **claves de `evidence[].rows` son los alias internos de SoQL** (`dim_1`, `metric_sum_1`, `group_count`), no los nombres de columna reales. El mapeo alias→nombre real existe pero **no se persiste ni se expone**. | `deterministic_pipeline.py:122` (`_selected_columns` usa `field_name=alias`); `soql_renderer.py:116-121`; `persistence.py:280-281`; mapeo interno en `deterministic_pipeline.py:138` (`_column_field_names`, no expuesto) | La tabla de evidencia y el CSV mostrarían encabezados `dim_1 / metric_sum_1`. Rompe RF-501 ("tablas legibles"), Art. V.5 y RNF-012. **Requiere un módulo de resolución de alias en el cliente** (§4.7) y, idealmente, un cambio aditivo del backend (decisión abierta D-3). |
| **H2** | El runtime determinista **no emite eventos SSE `evidence`**; solo `step` y el terminal (`answer`/`error`). El grafo *legacy* sí los emite (`graph.py:1389`). | `grep "reserve_and_emit_event"` → solo `graph.py` (legacy), `toy_graph.py`, `main.py` (paso 0) | La UI de evidencia **no puede ser incremental**: la evidencia aparece toda junta en el evento terminal. Diseñar la línea de tiempo y las tarjetas asumiendo esto; no prometer streaming de evidencia. |
| **H3** | `display_message` de cada paso es la `reason` interna de la máquina de estados: mezcla español telegráfico ("falta esquema observado", "hay candidato no intentado") con **enums crudos** ("LLM_BUDGET_EXCEEDED", "ALL_CANDIDATES_REJECTED"). | `runner.py:404` (`display_message=entry.reason`); `deterministic_graph.py:135-223` | Mostrarlo tal cual viola Art. V.5 / RNF-012 / RF-204 ("lenguaje claro"). El frontend **debe** traducir `node`+`stop_reason` a español claro y relegar la cadena cruda al detalle técnico expandible. |
| **H4** | `evidence[].narrative` y `evidence[].chart_suggestion` son **siempre `null`** en el pipeline determinista. | `persistence.py:283-284` | RF-503 (gráfica) **no tiene insumo del backend**. La narrativa citable solo existe a nivel de corrida (`answer.narrative`). Decisión abierta D-4. |
| **H5** | En `no_evidence`, `no_evidence_report` trae `reason` = enum crudo (`ALL_CANDIDATES_REJECTED`), y `datasets_reviewed: []` y `external_sources: []` **siempre vacíos** en el determinista. | `runner.py:817-828` | ESC-03 ("lista los datasets que sí revisó") queda incompleto y **T-506 pierde su prellenado** desde `external_sources`. El frontend debe degradar con elegancia y **no inventar** listas. Decisión abierta D-5. |

Divergencias menores adicionales: `answer.intention` es un **objeto** `{topic, operation, territory, entity, period, administrative_terms}` (`llm_contracts.py:39`), no el string del contrato §4 — es una **ventaja** de UX (permite el bloque "así entendí tu pregunta") pero el cliente debe aceptar `string | object`. `usage` trae `input_tokens`/`output_tokens` extra (aditivo, inofensivo). `evidence[].columns` es `string[]`, no `[{field,type}]`.

### 1.3 Estado de bloqueo

**El desarrollo del frontend NO está bloqueado por T-617.** `tasks.md:637` lo autoriza explícitamente: *"la planificación/desarrollo de frontend puede avanzar en una sesión separada, con fixtures y el backend local, sin depender del cierre de T-617"*. Lo prohibido hasta cerrar T-617 es **T-701** (despliegue del backend) y afirmar backend certificado. Como **T-702 (frontend en Vercel) depende de T-701**, el despliegue del frontend queda fuera de alcance hasta que T-617 cierre; todo lo demás (F0…F9) se puede hacer ya.

### 1.4 Recomendación de arranque (una sola)

**Empezar por F0 + F2 en el mismo primer bloque de trabajo, y dentro de F2 el primer incremento debe ser el parser SSE puro (`lib/sse/parseSseChunk.js`) con su suite de pruebas.** Razón: es el único componente que (a) no depende de decisiones de diseño visual pendientes, (b) no depende del backend real, (c) es la fuente #1 de bugs silenciosos en este tipo de app (eventos partidos entre chunks, duplicados tras reconexión), y (d) desbloquea todo lo demás. Detalle en §19.

---

## 2. Diagnóstico: el frontend determinista que hay que diseñar

### 2.1 Arquitectura y flujo real del núcleo (verificado en código)

```
Navegador                                   Backend FastAPI (un worker)
   │
   │ 1. POST /v2/agent/query {question, context_hint?}
   │    → 202 {run_id, run_access_token, token_expires_at, stream_url}
   │       ⚠ el token se entrega UNA vez y nunca más (main.py:955-963)
   │
   │ 2. GET /v2/agent/stream/{run_id}
   │    Authorization: Bearer <token>          [obligatorio]
   │    Last-Event-ID: <último seq>            [en reconexión]
   │    → text/event-stream
   │       id: <seq>
   │       event: step | evidence | answer | error
   │       data: {...}
   │       : ping    (heartbeat)
   │
   │    El servidor hace polling a la BD y reenvía eventos con seq > since;
   │    corta al primer evento terminal (main.py:986-1008).
   │
   │ 3. GET /v2/agent/runs/{run_id}   (recuperación / reconciliación)
   │    → RunStatusResponse (running) | RunResultResponse (terminal)
   │
   │ 4. DELETE /v2/agent/runs/{run_id} → 204 (RF-803, irreversible)
   ▼
```

Pipeline interno (plan.md §13.1), del que el usuario ve **solo pasos y el resultado**:

```
pregunta → intención estructurada → recuperación multiquery → candidatos ordenados
→ perfilado → QueryPlan → validación determinista → exploración categórica
→ render SoQL determinista → ejecución Socrata → calidad T6 → claims T7
→ síntesis fundamentada o abstención → persistencia + evento terminal único
```

Nodos que aparecen como `step.node` (`deterministic_graph.py:15-29`): `retrieve_candidates`, `select_candidate`, `profile_dataset`, `build_plan`, `explore_value`, `validate_plan`, `execute_query`, `validate_quality`, `derive_claims`, `persist_facts`, `synthesize`, `next_candidate`, `abstain`, `complete`. **Estos 14 nombres son el vocabulario que el frontend debe traducir a español claro** (H3).

Razones de parada (`StopReason`): `NO_CANDIDATES`, `CANDIDATE_BUDGET_EXCEEDED`, `EXPLORATION_BUDGET_EXCEEDED`, `QUERY_BUDGET_EXCEEDED`, `PLAN_REPAIR_BUDGET_EXCEEDED`, `LLM_BUDGET_EXCEEDED`, `DURATION_BUDGET_EXCEEDED`, `ALL_CANDIDATES_REJECTED`, `EVIDENCE_NOT_ELIGIBLE`, `CLAIMS_NOT_AVAILABLE`. **También hay que traducirlas.**

Forma real de `answer` (`runner.py:787-838`): `{run_id, status, intention:{...}, summary, narrative, evidence:[0..1], claims:[], presentation_warnings:[], textual_facts:[], partial_textual_facts:[], no_evidence_report, usage}`.

Forma real de una evidencia (`persistence.py:265-294`): `evidence_id, dataset_id, dataset_name, publisher, soql_query, executed_at, source_url, data_updated_at, data_cutoff_at, data_cutoff_method, data_cutoff_column, data_cutoff_confidence, data_cutoff_basis, data_cutoff_inferred_at, columns(string[] = alias), rows(dict[] con claves alias), row_count, narrative(null), chart_suggestion(null), quality{eligibility_status, eligibility_reasons, score_total, classification, warnings_user, dimensions}, citation{dataset_id, dataset_name, publisher, official_publisher_id, soql_query, executed_at, source_url, data_updated_at, data_cutoff_at}`.

Forma real de un claim (RF-212 ya implementado en T-617C): `claim_id, claim, claim_type, evidence_id, dataset_id, source_row_indexes, columns (nombre real, ya no alias), formula?, raw_value, display_value, unit, rounding, source_hash, label, label_status`.

**Observación clave:** una corrida determinista produce **como máximo una evidencia** (`runner.py:767`, `evidence = [persisted.evidence]`). La UI debe funcionar bien con 0 y con 1, y no romperse si algún día llegan N.

### 2.2 Estado del frontend legacy (auditoría archivo por archivo)

15 archivos JS, ~1.500 líneas. Todo en `frontend/`.

| Archivo | Líneas | Qué es | Veredicto v2 |
|---|---|---|---|
| `pages/index.js` | 216 | Landing + wizard de 4 pasos con animaciones `framer-motion` | **Conservar intacto** hasta T-704; el app v2 vive en `/app`. No refactorizar. |
| `pages/_app.js` | 23 | Head global + CSS + KaTeX | **Refactor mínimo** (quitar KaTeX, añadir `lang="es"`, skip-link) |
| `pages/api/consultar_v2.js` | 146 | Endpoint legacy: bucle ReAct con `@google/generative-ai` + Socrata, usa `GOOGLE_API_KEY`/`SOCRATA_APP_TOKEN` server-side | **Lo retira T-704.** No tocar en v2; no consumirlo desde código nuevo. |
| `utils/systemPrompt.js` | 199 | Prompt del agente v1 | **Lo retira T-704** |
| `utils/maestro_divipola.js` | 133 | Tabla DIVIPOLA hardcodeada | **Lo retira T-704** (el backend resuelve territorios) |
| `components/copilot/CopilotSidebar.js` | 202 | Chat que hace `fetch('/api/consultar_v2')`; estado solo en memoria | **Reemplazar por completo.** Sin SSE, sin token, sin consentimiento, sin historial persistido, sin `aria-live`. |
| `components/copilot/InsightCard.js` | 50 | Tarjeta de un registro | **Reemplazar** (no tiene calidad, cita, ni claims) |
| `components/canvas/PolicyCanvasMain.js` | 172 | Orquestador del canvas; estado en `useState`, sin persistencia | **Reemplazar** (base conceptual reutilizable: secciones + sidebar) |
| `components/canvas/RichTextEditor.js` | 73 | Tiptap StarterKit; serializa a **HTML string** vía `getHTML()`; `setContent(html)` desde el padre | **Reemplazar.** Ver riesgo R-06 (HTML persistido). |
| `components/canvas/SectionCard.js` | 41 | Tarjeta de sección con botones "Investigar" / "Auditar (Riesgos)" | **Refactor profundo** (colores fuera de paleta: `indigo-600`, `red-600`; sin roles ARIA) |
| `components/canvas/CanvasLayout.js` | 21 | Layout 2/3 + 1/3 | **Refactor:** el aside es `hidden lg:flex` → **el copiloto no existe bajo 1024 px**. Rompe RNF-007 (reflujo 320 px) y ESC-04 en móvil. |
| `components/canvas/CanvasHeader.js` | 13 | Encabezado | **Reutilizable con ajustes menores** |
| `components/canvas/TemplateSelector.js` | 62 | Selector de plantilla | **Refactor** (a11y + paleta) |
| `components/common/OnboardingTour.js` | 151 | Tour con `react-joyride` | **Fuera de alcance v2.0**; retirar dependencia (§15) |
| `components/wizard/*.js` | 653 | 4 pasos del wizard legacy | **Conservar intacto** hasta T-704 |
| `data/policyTemplates.js` | 95 | Plantillas MGA / CONPES / Policy Brief | **Reutilizable como datos**, pero **incompleto frente a RF-101**: falta "plan de desarrollo". Se conserva CONPES y Policy Brief como extras. |
| `styles/globals.css` | 85 | Estilos globales | **Refactor:** `:focus { outline: 2px solid #9b2c2c }` es **rojo**, fuera de la paleta azul (Art. V.1). Lo bueno: ya respeta `prefers-reduced-motion` y evita zoom iOS. |
| `tailwind.config.js` | 35 | Config Tailwind | **Reescribir:** no define **ningún** token de plan.md §7. Solo animaciones decorativas. |

**Resumen de reutilización real:** `data/policyTemplates.js` (datos), `CanvasHeader.js`, dos bloques de `globals.css` (reduced-motion, font-size iOS ≥16 px), y el andamiaje del proyecto (Next+Tailwind+PostCSS+Tiptap+Chart.js+PapaParse). Todo lo demás es nuevo.

### 2.3 Pruebas, accesibilidad, persistencia y errores: estado actual

| Área | Estado real | Evidencia |
|---|---|---|
| **Pruebas** | **Cero.** No hay Jest/Vitest/Playwright, ni carpeta `frontend/tests/`, ni script `test`. `pruebas.md` §1 exige suite E2E bloqueante por PR y `quickstart.md:212` documenta `npm run test:e2e` — **el comando no existe**. | `frontend/package.json` (solo `dev`/`build`/`start`) |
| **CI** | El job `frontend` de `.github/workflows/ci.yml` solo hace `npm ci` + `npm run build`. Sin lint, sin tests, sin axe/Lighthouse. | `ci.yml:88-111` |
| **Accesibilidad** | Parcial y accidental: hay `prefers-reduced-motion` y font-size 16 px móvil. En contra: foco rojo fuera de paleta, copiloto oculto <1024 px, botones sin `aria-label` donde el texto es un icono, sin `aria-live`, sin `lang` en `<html>`, sin skip-link, `reactStrictMode: false`. | `globals.css`, `CanvasLayout.js:14`, `next.config.js:3` |
| **Persistencia** | **Ninguna.** Todo el canvas vive en `useState`; recargar pierde el documento. ESC-08 y RF-102 **no se cumplen hoy**. | `PolicyCanvasMain.js:22-47` |
| **Manejo de errores** | `try/catch` con `console.error` + mensaje genérico "Error de conexión con el Agente". Sin códigos, sin `message_user`, sin distinción reintentable. | `CopilotSidebar.js:61-68` |
| **Secretos en cliente** | Correcto hoy: las claves están en `frontend/.env.local` (no versionado, confirmado en `.gitignore`) y solo las usa el endpoint server-side. **Pero** `@google/generative-ai` está en `dependencies`, no en `devDependencies`: si algún día se importa desde un componente, la clave viaja al bundle. En v2 el frontend **no debe tener ninguna clave de proveedor** (RNF-011). | `frontend/.env.local`, `package.json` |

### 2.4 Dependencias: presentes, faltantes, innecesarias

**Presentes y útiles (reutilizar, sin instalar nada):**

| Paquete | Versión instalada | Uso en v2 | Requisito |
|---|---|---|---|
| `next` | 14.1.3 | Framework, Pages Router (plan.md §2: no migrar a App Router) | — |
| `react` / `react-dom` | 18.2.0 | — | — |
| `tailwindcss` + `postcss` + `autoprefixer` | 3.x | Sistema de diseño (tokens §7) | T-501 |
| `@tailwindcss/typography` | 0.5.19 | Prosa del canvas | RF-101 |
| `@tiptap/react` `@tiptap/starter-kit` `@tiptap/core` `@tiptap/pm` | 3.11.0 (los cuatro ya instalados) | Editor + extensiones de cita | RF-101/103, T-504 |
| `chart.js` + `react-chartjs-2` | 4.5.1 / 5.3.0 | Gráfica simple | RF-503 |
| `papaparse` | 5.5.3 | `Papa.unparse` para CSV | RF-501 |

**Faltantes (instalar — justificación en §15):** `lucide-react`, `docx`, `vitest`, `@vitejs/plugin-react`, `jsdom`, `@testing-library/react`, `@testing-library/user-event`, `@testing-library/jest-dom`, `@playwright/test`, `@axe-core/playwright`, `eslint` + `eslint-config-next`.

**Innecesarias / a retirar:** `@google/generative-ai` (riesgo RNF-011), `react-globe.gl` + `three` (no importadas, ~600 KB), `d3` (no importada), `reactflow` (no importada), `katex` + `react-katex` (solo CSS global), `@fortawesome/*` (plan.md §7 exige **una** familia de iconos: Lucide), `react-joyride` (tour fuera de alcance), `framer-motion` (usada solo en el wizard legacy; se retira con T-704, no antes).

### 2.5 Riesgos técnicos identificados

| ID | Riesgo | Probabilidad | Impacto | Dónde se mitiga |
|---|---|---|---|---|
| R-01 | **Token de corrida filtrado** (URL, log, telemetría, mensaje de error, `sessionStorage` leído por XSS) | Media | Crítico (RNF-011, RF-801) | §10.1, F2 |
| R-02 | **SSE fragmentado entre chunks** → eventos perdidos o JSON roto | **Alta** (es el modo de fallo por defecto de un parser ingenuo) | Alto | Parser incremental probado, F2 |
| R-03 | **Duplicación de eventos tras reconexión** con `Last-Event-ID` | Alta | Alto (línea de tiempo duplicada, RNF-008) | Dedupe por `seq`, F2 |
| R-04 | **Pérdida del historial**: token en `sessionStorage` → cerrar pestaña impide borrar la corrida (RF-803) | Alta | Medio | Opt-in explícito + aviso en consentimiento, §7 |
| R-05 | **Inserción de evidencia sin cita completa** (viola Art. I.2 de forma dura) | Media | Crítico | Nodo Tiptap con `citation` obligatoria y validación previa, F5 |
| R-06 | **HTML persistido / XSS**: guardar `getHTML()` y reinyectarlo con `setContent(html)` | Media | Alto | Persistir **JSON de ProseMirror**, nunca HTML; nodos construidos programáticamente, F5/F6 |
| R-07 | **Exposición accidental de secretos**: reintroducir claves en el cliente | Baja | Crítico | Auditoría de bundle en CI (`pruebas.md` §6), F8 |
| R-08 | **Descargas CSV/DOCX**: encabezados `dim_1`, cifras reformateadas, cita ausente | **Alta** (por H1) | Alto | Módulo de resolución de alias + pruebas, F4/F6 |
| R-09 | **Accesibilidad de contenido dinámico**: `aria-live` saturando al lector con 14 pasos | Alta | Alto (RNF-007) | Región `polite` con agrupación/throttle, F1/F3 |
| R-10 | **320 px**: layout 2/3+1/3 con aside `hidden lg:flex` | **Certeza** (ya ocurre) | Alto | Copiloto como panel colapsable/drawer, F1 |
| R-11 | **`dim_N`/`metric_N` visibles al usuario** | **Certeza** (H1) | Alto | §4.7 + D-3 |
| R-12 | **Mensajes técnicos sin explicación** (`ALL_CANDIDATES_REJECTED`, `EVIDENCE_NOT_ELIGIBLE`) | **Certeza** (H3/H5) | Alto (RNF-012) | Diccionario es-CO, F3 |
| R-13 | **Contrato vs. código divergente** (H1–H5): construir contra el contrato y romper contra el runtime | Alta | Alto | Fixtures capturados de corridas reales, no inventados, F0 |
| R-14 | Deriva del backend mientras T-617 avanza | Media | Medio | Cliente tolerante a campos desconocidos (contract §10) + prueba de contrato contra fixtures reales |

---

## 3. Matriz requisito → estado → brecha → componente

| Tarea/requisito | Estado actual | Archivo implicado | Brecha | Dependencia | Evidencia necesaria |
|---|---|---|---|---|---|
| **RF-101** Lienzo por secciones, plantillas (libre, MGA, plan de desarrollo) + editor enriquecido | Parcial: hay canvas y plantillas MGA/CONPES/Policy Brief | `components/canvas/*`, `data/policyTemplates.js` | Falta plantilla **plan de desarrollo**; falta plantilla **libre** explícita; editor sin extensiones de v2 | F1, F5 | Captura de las 3 plantillas mínimas + prueba de render |
| **RF-102** Autoguardado ≤5 s + exportación ofimática | **No existe** | ninguno | Autoguardado, esquema versionado, migración, export `.docx` | F6 | Prueba de temporizador ≤5 s; `.docx` abierto en Word |
| **RF-103** Cita completa preservada + exportada | **No existe** | ninguno | Nodo Tiptap `evidenceCitation` con los 6 campos de Art. I.2 | F5, F6 | Prueba: nodo sin cita → inserción rechazada; `.docx` con nota al pie |
| **RF-104** Investigar desde una sección con su contexto | Parcial: `handleAskCopilot` arma un prompt gigante | `PolicyCanvasMain.js:63-87` | Debe mapear a `context_hint` ≤1000 chars, no a un prompt | F3 | Prueba unitaria de truncado + payload real |
| **RF-204** Pasos en vivo, lenguaje claro + detalle técnico | **No existe** | — | Cliente SSE + diccionario es-CO (H3) | F2, F3 | E2E: timeline en español, `detail` expandible |
| **RF-209** Reanudación `Last-Event-ID`, terminales | **No existe** | — | Reconexión con backoff, dedupe, estados `interrupted`/`failed` | F2 | Prueba de corte de red sin duplicados |
| **RF-401/402** Calidad visible (score + clasificación) | **No existe** | — | Badge + panel de 4 dimensiones | F4 | E2E ESC-05 |
| **RF-403** Informe en dos niveles | **No existe** | — | Resumen claro + detalle expandible | F4 | Revisión manual + E2E |
| **RF-404** `no_recomendada` requiere confirmación | **No existe** | — | Diálogo modal con foco gestionado | F4, F5 | E2E ESC-05 |
| **RF-501** Tabla legible + CSV + narrativa citable | Tabla cruda de 5 filas, sin CSV | `CopilotSidebar.js:82-117` | **Encabezados alias (H1)**, sin CSV, sin narrativa | F4 | CSV con nombres reales == tabla visible |
| **RF-502** Historial + re-ejecutar/refinar | Solo memoria | `CopilotSidebar.js:7` | Historial persistido en sesión + acciones | F3 | E2E: reejecutar crea `run_id` nuevo |
| **RF-503** Gráfica cuando aplique | **No existe** y **sin insumo backend (H4)** | `persistence.py:284` | Derivación determinista en cliente o tarea backend | F4 + **D-4** | Gráfica solo con 1 dim + 1 métrica + ≥3 filas |
| **RF-801** Token por corrida, nunca en URL | **No existe** | — | Almacén de tokens + interceptor de encabezados | F2 | Prueba: `grep` de token en URLs/logs = 0 |
| **RF-802** Consentimiento previo | **No existe** | — | Modal versionado antes del primer `POST` | F3 | E2E: sin consentimiento no hay `POST` |
| **RF-803** Borrado por corrida | **No existe** | — | Acción `DELETE` + limpieza local | F3 | E2E: 204 → desaparece del historial |
| **RF-804** Retención informada | **No existe** | — | Texto "90 días" en el consentimiento | F3 | Acta RNF-012 |
| **RNF-007** WCAG 2.2 AA, 320 px | Muy parcial | `CanvasLayout.js`, `globals.css` | Contraste, foco, teclado, reflujo, `aria-live` | F1, F8 | axe ≥95 + acta manual |
| **RNF-008** ≤500 ms feedback, ≤2 s primer paso | **No existe** | — | Optimistic UI + instrumentación | F3, F8 | E2E instrumentada |
| **RNF-011** 0 credenciales en cliente | Cumple hoy, frágil | `package.json` | Auditoría de bundle en CI | F0, F8 | Job de CI en verde |
| **RNF-012** Todo en español claro | Parcial | todos | Traducción de nodos/stop reasons/códigos (H3/H5) | F3, F8 | Acta `docs/release-rnf-012-*.md` |
| **T-506** Aporte manual | **No existe** | — | Nodo Tiptap distinto + badge | F7 | Captura: distinguible a simple vista |
| **T-704** Retiro de legacy | Pendiente | `pages/api/consultar_v2.js`, `utils/*` | No consumir legacy desde código nuevo | F9 | — |

---

## 4. Arquitectura objetivo

### 4.1 Principio rector

> **El navegador nunca interpreta, calcula ni completa un dato.** Solo transporta, deduplica, ordena, formatea (es-CO) y presenta lo que el backend afirmó. Cualquier cifra mostrada proviene de `claims[].display_value` o de `evidence[].rows`; cualquier etiqueta proviene de `claims[].label`, del nombre de columna real o del alias crudo con advertencia. **Nunca de una inferencia del cliente.**

### 4.2 Árbol de archivos objetivo

```
frontend/
├── pages/
│   ├── _app.js                    (refactor: lang es, skip-link, providers)
│   ├── _document.js               (NUEVO: <html lang="es">)
│   ├── index.js                   (legacy intacto hasta T-704)
│   ├── app.js                     (NUEVO: entrada del Policy Canvas v2)
│   └── api/consultar_v2.js        (legacy; T-704 lo elimina)
│
├── lib/                           (NUEVO — lógica pura, sin React, 100% testeable)
│   ├── config/backendUrl.js       validación de NEXT_PUBLIC_BACKEND_URL
│   ├── api/
│   │   ├── errors.js              ApiError + parseo del sobre §6
│   │   ├── agentClient.js         startRun/getRun/deleteRun
│   │   ├── catalogClient.js       searchCatalog, health
│   │   └── redact.js              redacción de token en cualquier salida
│   ├── sse/
│   │   ├── parseSseChunk.js       parser incremental puro
│   │   └── streamRun.js           fetch+reader+backoff+dedupe+AbortController
│   ├── agent/
│   │   ├── runReducer.js          reducer puro (evento → estado)
│   │   ├── runStates.js           máquina de estados de la corrida
│   │   └── messages.es.js         node/stopReason/errorCode → español claro
│   ├── evidence/
│   │   ├── resolveColumns.js      alias → nombre real (H1)
│   │   ├── humanizeField.js       snake_case → etiqueta legible
│   │   ├── toCsv.js               PapaParse + bloque de cita
│   │   ├── chartSpec.js           decide si hay gráfica y cuál
│   │   └── quality.js             score/clasificación → texto y color
│   ├── document/
│   │   ├── schema.js              esquema versionado del documento
│   │   ├── migrate.js             migraciones v0→v1→…
│   │   ├── storage.js             localStorage con namespace y cuota
│   │   └── exportDocx.js          generación .docx con notas al pie
│   ├── session/
│   │   ├── tokenStore.js          sessionStorage (opt-in localStorage)
│   │   ├── historyStore.js        historial de corridas de la sesión
│   │   └── consent.js             estado de consentimiento versionado
│   └── format/
│       ├── number.js              formato es-CO (nunca recalcula)
│       └── date.js                fechas es-CO + zonas
│
├── hooks/                         (NUEVO)
│   ├── useAgentRun.js             orquesta un run: start→stream→terminal
│   ├── useRunHistory.js
│   ├── useAutosave.js             debounce ≤5 s + flush en unload
│   ├── useConsent.js
│   └── usePolitePolite.js         cola de anuncios aria-live agrupados
│
├── components/
│   ├── ui/                        (NUEVO: primitivas accesibles)
│   │   ├── Button.jsx  IconButton.jsx  Badge.jsx  Card.jsx
│   │   ├── Disclosure.jsx  Modal.jsx  Tabs.jsx  Table.jsx
│   │   ├── LiveRegion.jsx  Skeleton.jsx  VisuallyHidden.jsx
│   │   └── Toast.jsx
│   ├── agent/                     (NUEVO)
│   │   ├── CopilotPanel.jsx       contenedor colapsable/responsive
│   │   ├── QuestionComposer.jsx
│   │   ├── IntentSummary.jsx      "así entendí tu pregunta" (usa intention)
│   │   ├── RunTimeline.jsx        pasos en español claro
│   │   ├── StepItem.jsx           + detalle técnico expandible
│   │   ├── ConnectionStatus.jsx   reconectando / interrumpido / timeout
│   │   ├── TerminalPanel.jsx      completed | no_evidence | interrupted | failed
│   │   ├── NoEvidenceReport.jsx   ESC-03
│   │   ├── ConsentDialog.jsx      RF-802
│   │   ├── RunHistoryList.jsx     RF-502
│   │   └── DeleteRunButton.jsx    RF-803
│   ├── evidence/                  (NUEVO)
│   │   ├── EvidenceCard.jsx
│   │   ├── EvidenceTable.jsx
│   │   ├── EvidenceChart.jsx
│   │   ├── QualityBadge.jsx  QualityDetails.jsx
│   │   ├── ClaimList.jsx          claims + label/label_status
│   │   ├── PresentationWarnings.jsx
│   │   ├── CitationBlock.jsx
│   │   ├── DownloadCsvButton.jsx
│   │   └── InsertEvidenceButton.jsx (+ confirmación no_recomendada)
│   ├── canvas/                    (reescritura)
│   │   ├── PolicyCanvas.jsx  CanvasShell.jsx  SectionCard.jsx
│   │   ├── TemplatePicker.jsx  ExportMenu.jsx
│   │   ├── editor/
│   │   │   ├── Editor.jsx
│   │   │   ├── extensions/EvidenceCitationNode.js
│   │   │   ├── extensions/ManualEntryNode.js
│   │   │   └── serialize/toDocx.js
│   │   └── ManualDataEntry.jsx    T-506
│   └── wizard/, common/           (legacy intacto hasta T-704)
│
├── styles/
│   ├── globals.css                (refactor)
│   └── tokens.css                 (NUEVO: variables de plan.md §7)
├── tests/
│   ├── unit/                      Vitest
│   ├── fixtures/                  payloads REALES capturados
│   └── e2e/                       Playwright + mock del backend
├── tailwind.config.js             (reescritura: tokens)
├── vitest.config.js               (NUEVO)
├── playwright.config.js           (NUEVO)
├── .eslintrc.json                 (NUEVO)
└── .env.local.example             (NUEVO: NEXT_PUBLIC_BACKEND_URL)
```

### 4.3 Cliente del backend — contrato interno

```js
// lib/config/backendUrl.js
export function resolveBackendUrl(env = process.env) // → string
// Valida: presente; http/https; sin credenciales embebidas; sin path; sin barra final.
// En desarrollo, si falta → lanza error visible en pantalla con instrucciones.
// En producción, si falta → la app arranca en "modo sin backend" y explica el problema
// en español, sin stack trace (Art. V.5). Nunca hace fallback silencioso a localhost.
```

```js
// lib/api/agentClient.js
createAgentClient({ baseUrl, fetchImpl = fetch })
  .startRun({ question, contextHint, signal })
      // POST /v2/agent/query  → { runId, token, tokenExpiresAt, streamUrl }
      // ⚠ el token se devuelve al llamador y NO se registra en ningún log
  .getRun({ runId, token, signal })
      // GET /v2/agent/runs/{id} → RunStatus | RunResult (discriminado por status)
  .deleteRun({ runId, token, signal })
      // DELETE → true (204) | lanza ApiError(404 RUN_NOT_FOUND) — idempotente
```

Reglas transversales del cliente:
1. **`Authorization: Bearer` siempre por encabezado.** El módulo no expone ninguna función que acepte un token como parámetro de URL (imposible por construcción, no por convención).
2. **Sobre de error §6**: toda respuesta no-2xx se convierte a `ApiError{code, status, messageUser, messageDev, retryable, httpStatus}`. Si el cuerpo no es JSON válido (proxy, CORS, 502 de infraestructura), se sintetiza `code: "NETWORK"` con `messageUser` en español. **`messageDev` nunca se muestra al usuario**, solo se expone tras el disclosure técnico.
3. **`redact.js`** se aplica a cualquier objeto antes de `console.*` o de un `Error.message`: sustituye el patrón `cdt_rt_[A-Za-z0-9_-]+` y cualquier valor de un campo `token`/`authorization`.
4. **Tolerancia a campos nuevos** (contract §10): nunca validación estricta que rompa ante campos desconocidos.
5. **Sin telemetría de terceros.** Ningún Sentry/analytics en v2.0 (Art. III + RNF-011). Si se añade después, el token debe estar en la lista de redacción antes.

### 4.4 Parser SSE incremental

```js
// lib/sse/parseSseChunk.js — puro, sin I/O, sin estado global
createSseParser() → { push(chunkString) → Event[], flush() → Event[] }
// Event = { id?: string, event?: string, data: string, retry?: number, comment?: boolean }
```

Requisitos verificables (cada uno es una prueba):
- Separador de evento: línea en blanco. Acepta `\n`, `\r\n` y `\r`.
- Campos: `id`, `event`, `data`, `retry`. `data:` múltiple se concatena con `\n`.
- `: ping` produce un evento marcado `comment: true` (**no** se pasa al reducer, pero **sí** actualiza el reloj de "conexión viva").
- Un evento partido en cualquier byte entre dos chunks se ensambla correctamente (prueba: partir un payload de 4 KB en chunks de 1 byte y verificar 1 evento).
- Un `data:` que no es JSON válido produce un evento de error tipado, **no** una excepción no controlada.
- BOM inicial y espacio tras `:` se manejan según la especificación de `text/event-stream`.

### 4.5 Orquestador del stream

```js
// lib/sse/streamRun.js
streamRun({ baseUrl, runId, token, lastEventId, onEvent, onStatus, signal, fetchImpl, now })
```

Comportamiento normativo:

| Aspecto | Decisión |
|---|---|
| Transporte | `fetch()` + `response.body.getReader()` + `TextDecoder('utf-8', {stream:true})`. **Nunca `EventSource`** (no admite `Authorization` — plan.md §11). |
| Encabezados | `Authorization: Bearer <token>`, `Accept: text/event-stream`, `Last-Event-ID: <n>` solo si `n>0`. |
| Secuencia | Se lleva `lastSeq`. Un evento con `id <= lastSeq` **se descarta silenciosamente** (dedupe, R-03). Un salto (`id > lastSeq+1`) se registra como hueco y **dispara reconciliación** por `GET /runs/{id}` al terminar, sin romper la UI. |
| Heartbeat | Si no llega **ningún** byte (ni `: ping`) en `45 s` (3× el intervalo de 15 s del contrato), se considera conexión muerta y se reconecta. |
| Reconexión | Backoff exponencial con jitter: 0,5 s · 1 s · 2 s · 4 s · 8 s · 8 s… Máximo **6** intentos consecutivos; después, estado `disconnected` con botón **"Reintentar"** manual. Cada reintento reenvía `Last-Event-ID`. |
| Errores no reintentables | `401`, `404`, `422` **no** se reintentan: son terminales del lado del cliente. |
| Cancelación | `AbortController`. Abortar **NO** borra la corrida y la UI lo dice explícitamente: *"Dejaste de seguir esta investigación. Sigue ejecutándose en el servidor; puedes volver a conectarte o borrarla."* (RF-209: la desconexión no interrumpe). |
| Recuperación | Al montar la app con un `runId` en el historial y estado no terminal → `GET /runs/{id}`; si `running`, se reconstruye la línea de tiempo desde `events[]` y se reengancha el stream con `Last-Event-ID = last_event_seq`. |
| Fin | El primer evento `answer`/`error` cierra el stream y el lector. **Siempre** se hace un `GET /runs/{id}` de reconciliación tras el terminal si hubo al menos una reconexión (defensa contra huecos). |
| Doble corrida | Un `runId` solo puede tener **un** stream activo (guardia en el hook). Evita duplicación por doble montaje de React. |

### 4.6 Estados terminales y su UI

| `status` | Origen | Qué muestra la UI | Acciones ofrecidas |
|---|---|---|---|
| `completed` | `answer` | Resumen + narrativa + evidencia + claims + advertencias de presentación | Insertar, descargar CSV, ver detalle, borrar, reejecutar |
| `no_evidence` | `answer` | Explicación honesta + `datasets_reviewed` (si viene) + sugerencias + `external_sources` (si viene) | Reformular, **Agregar manualmente** (T-506), borrar |
| `interrupted` | `error` (`RUN_INTERRUPTED`/`WORKER_LOST`/`HEARTBEAT_EXPIRED`) | *"La investigación se interrumpió en el servidor. Esto es lo que alcanzó a verificar."* + parciales | Volver a ejecutar (corrida nueva), borrar |
| `failed` | `error` (`RUN_TIMEOUT`, `LLM_PROVIDER_ERROR`, `STRUCTURED_OUTPUT_INVALID`, `SOCRATA_*`, `INTERNAL`) | `message_user` del sobre + parciales de diagnóstico | Reintentar si `retryable`, borrar |

**Regla:** ningún estado terminal muestra una pantalla vacía. `interrupted` y `failed` **muestran los parciales** si existen, siempre etiquetados como *"resultado parcial, no verificado como respuesta completa"*.

### 4.7 Resolución de alias → nombres reales (H1) — módulo crítico

```js
// lib/evidence/resolveColumns.js
resolveEvidenceColumns(evidence) → {
  columns: [{ key, fieldName|null, label, kind: 'dimension'|'metric'|'count'|'unknown',
              operation?: 'sum'|'avg'|'min'|'max'|'count', resolved: boolean }],
  unresolved: string[]
}
```

Estrategia en cascada, **determinista y auditable**:
1. **Si el backend expone el mapeo** (campo aditivo futuro, D-3) → usarlo y terminar.
2. **Parseo del `soql_query` canónico.** El renderer produce siempre la forma `select <campo> as dim_N, <op>(<campo>) as metric_<op>_N[, count(*) as group_count]` en minúsculas (`soql_renderer.py:110-160`). Se extraen pares `(expresión, alias)` de la cláusula `select` con un tokenizador acotado —no una regex ingenua— probado contra fixtures reales.
3. **Refuerzo con `claims[].columns`** (que desde T-617C-R1 sí trae nombres reales): si un claim referencia el alias y el nombre real, se cruza.
4. **Si no se resuelve:** se muestra el **alias crudo** con un icono de advertencia y el texto *"nombre técnico de la consulta"*. **Jamás se inventa** un nombre.

`humanizeField.js` transforma el nombre real en etiqueta legible con reglas **puramente tipográficas** (guiones bajos → espacios, capitalización de la primera letra) y **una tabla explícita y corta** de correcciones de mojibake de Socrata verificadas contra el catálogo (p. ej. `a_o` → "Año", `descripci_n` → "Descripción"). Regla dura: **la tabla solo corrige codificación, nunca traduce ni reinterpreta semántica**, y el nombre técnico original queda siempre visible en el detalle expandible y en el CSV. Toda entrada nueva de la tabla exige una prueba.

Para métricas, la etiqueta se compone del operador del alias + el campo: `metric_sum_1` sobre `valor_contrato` → **"Suma de Valor contrato"**. Es una descripción de la operación que la propia consulta declara, no una interpretación.

---

## 5. Modelo de estados y secuencias

### 5.1 Máquina de estados de una corrida (cliente)

```
                 ┌──────────┐
                 │   idle   │
                 └────┬─────┘
       usuario envía  │  (feedback visual < 500 ms: RNF-008)
                      ▼
                 ┌──────────┐  error 4xx/5xx en POST
                 │ creating │──────────────────────────┐
                 └────┬─────┘                          │
        202 recibido  │                                │
                      ▼                                ▼
                 ┌──────────┐   corte de red     ┌───────────┐
                 │streaming │◀──────────────────▶│reconnecting│
                 └────┬─────┘   backoff+LEID     └─────┬─────┘
                      │                                │ 6 intentos
       evento terminal│                                ▼
                      │                          ┌──────────────┐
                      │                          │ disconnected │──▶ (reintento manual)
                      ▼                          └──────────────┘
        ┌────────────┬─────────────┬─────────────┬────────────┐
        ▼            ▼             ▼             ▼            ▼
   completed   no_evidence   interrupted      failed      deleted
        └────────────┴─────────────┴─────────────┴────────────┘
                                │
                     reejecutar → nueva corrida (idle)
```

Estado auxiliar `detached` (el usuario canceló el seguimiento con `AbortController`): **no es terminal**, no borra nada, y ofrece "volver a conectar".

### 5.2 Forma del estado (reducer puro)

```js
// lib/agent/runReducer.js — sin React, sin fetch, sin Date.now() interno
{
  runId, status,            // ver §5.1
  question, contextHint, sectionId,
  intention: null | { topic, operation, territory, entity, period, administrativeTerms },
  steps: [{ seq, stepNumber, node, displayMessageRaw, displayMessage, detail, at }],
  seenSeqs: Set<number>,    // dedupe
  lastSeq: number,
  evidence: [],             // se puebla en el terminal (H2); array por contrato
  claims: [],
  presentationWarnings: [],
  textualFacts: [],
  noEvidenceReport: null,
  usage: null,
  error: null,              // ApiError normalizado
  reconnect: { attempts, nextDelayMs, lastPingAt },
  timings: { requestedAt, firstFeedbackAt, firstStepAt, terminalAt }  // RNF-008
}
```

El reducer es **puro y exhaustivo**: `(state, action) → state`, acciones `RUN_REQUESTED`, `RUN_CREATED`, `SSE_EVENT`, `SSE_RECONNECTING`, `SSE_DISCONNECTED`, `RUN_RECONCILED`, `RUN_DELETED`, `RUN_DETACHED`. Un `SSE_EVENT` con `seq` ya visto es un **no-op que devuelve el mismo objeto de estado** (comprobable por identidad referencial en la prueba).

### 5.3 Secuencia ESC-01 completa

```
Usuario                UI                     Cliente                 Backend
  │  clic "Investigar"  │                        │                       │
  ├────────────────────▶│                        │                       │
  │                     │ ¿consentimiento? ──no──▶ ConsentDialog (RF-802)│
  │                     │        │sí                                     │
  │                     │ skeleton + "Preparando…"  (< 500 ms, RNF-008)  │
  │                     ├───────────────────────▶│ POST /v2/agent/query  │
  │                     │                        ├──────────────────────▶│
  │                     │                        │◀───── 202 {run_id,…}  │
  │                     │  token → sessionStorage│ (nunca a log/URL)     │
  │                     │                        ├─ GET /stream (Bearer)▶│
  │                     │◀── step seq=0 "Preparando la investigación"    │
  │  ve el primer paso  │      (< 2 s, RNF-008)                          │
  │                     │◀── step seq=1..n  (traducidos a español claro) │
  │                     │◀── answer (terminal): evidencia + claims       │
  │                     │  render tarjeta de evidencia + calidad          │
  │  clic "Insertar"    │                                                │
  ├────────────────────▶│ ¿clasificación == no_recomendada? → confirmar   │
  │                     │ inserta nodo Tiptap con citation completa       │
  │                     │ autoguardado ≤ 5 s → localStorage               │
```

---

## 6. Flujo REST/SSE completo (referencia de implementación)

| Paso | Método | Ruta | Encabezados | Éxito | Errores manejados |
|---|---|---|---|---|---|
| Salud (opcional, al arrancar) | GET | `/v2/health` | — | 200/503 `HealthResponse` | Banner "servicio degradado", no bloquea |
| Crear corrida | POST | `/v2/agent/query` | `Content-Type` | 202 | 422 (pregunta <10 chars → validar antes en cliente), 429 (`RATE_LIMITED` → "hay muchas investigaciones en curso, intenta en un momento"), red |
| Stream | GET | `/v2/agent/stream/{run_id}` | `Authorization`, `Last-Event-ID?`, `Accept` | 200 `text/event-stream` | 401 (token inválido → limpiar del almacén local y explicar), 404 (`RUN_NOT_FOUND`, incluye vencida → sacar del historial) |
| Recuperar | GET | `/v2/agent/runs/{run_id}` | `Authorization` | 200 status/result | 401, 404 |
| Borrar | DELETE | `/v2/agent/runs/{run_id}` | `Authorization` | 204 | 401, 404 (idempotente: se trata como éxito para la UI) |
| Catálogo (opcional, F9) | GET | `/v2/catalog/search?q&k` | — | 200 | 422 si `k>25` |

**Validación previa en cliente (evita 422 innecesarios):** `question` 10–2000 caracteres tras `trim`; `context_hint` ≤1000 (se trunca por límite de palabra, no a mitad de palabra, y se avisa visualmente que se recortó).

**CORS:** el backend permite `GET, POST, DELETE` y los encabezados `Authorization, Content-Type, Last-Event-ID, X-Admin-Token` (`main.py:321-325`), con origen `http://localhost:3000` por defecto (`config.py:61`). El frontend **no debe** enviar encabezados personalizados fuera de esa lista: cualquier encabezado extra provoca un preflight fallido.

---

## 7. Modelo de persistencia local

| Dato | Dónde | Clave | Justificación |
|---|---|---|---|
| **Documento del canvas** (JSON de ProseMirror + metadatos) | `localStorage` | `cdd.doc.v1` | ESC-08 exige sobrevivir al cierre del navegador; es contenido propio del usuario y nunca sale del equipo (Art. VI.4) |
| **Preferencias de UI** (panel colapsado, plantilla) | `localStorage` | `cdd.prefs.v1` | Inocuo |
| **Consentimiento RF-802** (versión + fecha) | `localStorage` | `cdd.consent.v1` | Debe sobrevivir la sesión para no re-preguntar; se vuelve a pedir si cambia la versión del texto |
| **`run_access_token`** | **`sessionStorage`** (por defecto) | `cdd.runs.v1` | **Decisión de privacidad:** es un secreto (RNF-011). `sessionStorage` limita la ventana de exposición a la pestaña abierta y reduce el radio de impacto de un XSS |
| **Historial de corridas de la sesión** (id, pregunta, estado, resumen) | `sessionStorage` | `cdd.runs.v1` | RF-502 dice explícitamente *"durante la sesión"* |
| **Última `seq` por corrida** | `sessionStorage` (en el registro de la corrida) | — | Necesaria para `Last-Event-ID` tras recargar |
| **Cita insertada en el documento** | dentro del documento (`localStorage`) | — | RF-103: la cita viaja con el fragmento, no con la corrida |
| **Aporte manual (T-506)** | dentro del documento | — | Requisito explícito: **nunca** en tablas backend |

**Consecuencia asumida y comunicada (R-04):** al cerrar el navegador se pierden los tokens, y con ellos la posibilidad de borrar esas corridas manualmente. Mitigación en tres capas: (1) el texto de consentimiento dice que las corridas se borran solas a los 90 días (`RETENTION_USER_DAYS`, data-model.md §7); (2) botón "Borrar esta investigación" siempre visible durante la sesión; (3) casilla **opt-in, desmarcada por defecto**, *"Recordar mis investigaciones en este equipo"* que mueve el registro a `localStorage` con un aviso claro de qué implica. Alternativa descartada: `localStorage` por defecto — más cómodo, pero deja un secreto persistente en disco sin que el usuario lo pida (contradice el espíritu de "alcance mínimo" de RF-801).

**Esquema versionado y migración:**

```js
{ schemaVersion: 1, createdAt, updatedAt, templateId,
  sections: [{ id, title, placeholder, doc /* JSON ProseMirror */ }] }
```
`migrate.js` aplica migraciones **encadenadas e idempotentes** (`v0→v1`, `v1→v2`, …). Un documento con versión **mayor** que la soportada (usuario que volvió a una versión anterior de la app) **no se abre ni se sobrescribe**: se conserva intacto, se muestra un aviso y se ofrece descargarlo. Antes de cada migración se guarda una copia en `cdd.doc.backup.<version>`. Un `JSON.parse` fallido nunca borra: se aísla en `cdd.doc.corrupt.<timestamp>` y se abre un documento nuevo. Se maneja `QuotaExceededError` con aviso explícito y opción de exportar.

---

## 8. Diseño de componentes

### 8.1 Copiloto (RF-204, RF-502, RNF-008, ESC-04)

- **`CopilotPanel`**: `≥1024 px` panel lateral fijo (1/3) **colapsable**; `<1024 px` **drawer** a pantalla completa con foco atrapado y botón de cierre; en `320 px` el contenido fluye en una columna sin scroll horizontal. Sustituye a `hidden lg:flex` (R-10).
- **`IntentSummary`**: renderiza `answer.intention` como *"Entendí: **tema** en **territorio**, periodo **X**, operación **suma**"*, con botón "No es lo que quería → reformular". Aprovecha una divergencia del contrato (§1.2) convertida en ventaja de UX.
- **`RunTimeline`** + **`StepItem`**: por paso, un icono de estado, el mensaje **traducido**, y un `<Disclosure>` "Ver detalle técnico" con `node`, `display_message` crudo, `dataset_id`, `candidate_index`, códigos de validación y `usage`. Sin animaciones bajo `prefers-reduced-motion`.
- **`ConnectionStatus`**: cuatro estados visibles con **texto + icono** (nunca solo color): *En vivo* · *Reconectando (intento 2 de 6)* · *Sin conexión — Reintentar* · *Dejaste de seguirla*.
- **`LiveRegion`** (`aria-live="polite"`): **no** anuncia cada paso. Anuncia (a) el arranque, (b) un resumen agrupado cada ≥5 s del tipo *"Paso 4 de la investigación: consultando el dataset"*, (c) el estado terminal. Cola con throttle (R-09).

### 8.2 Evidencia (RF-401…404, RF-501, RF-503)

`EvidenceCard` con secciones fijas y orden estable:

1. **Encabezado**: nombre del dataset + publicador + `QualityBadge`.
2. **Respuesta**: narrativa/resumen de la corrida con los `display_value` de los claims **resaltados** y vinculados a su claim (Art. I: la cifra mostrada es exactamente la del claim, nunca reformateada por el cliente).
3. **`ClaimList`**: por claim, `label` (o *"Etiqueta no confirmada"* si `label_status === "ambiguous"`), `display_value`, `unit`, columnas fuente reales y filas de origen.
4. **`PresentationWarnings`**: bloque propio, con el `message_user` textual del backend. **Nunca fusionado** con `quality.warnings_user` (contrato §4c lo prohíbe explícitamente).
5. **`EvidenceTable`**: encabezados resueltos (§4.7); `<caption>`, `<th scope="col">`, contenedor con `overflow-x:auto` y `tabindex="0"` para que sea alcanzable por teclado; máximo 10 filas visibles + "ver todas".
6. **`EvidenceChart`** (RF-503): solo si `chart_suggestion` existe **o** (fallback D-4) hay exactamente 1 dimensión + 1 métrica y ≥3 filas. La gráfica **replica** los valores de la tabla, no calcula nada; la tabla es la alternativa textual (`pruebas.md` §5).
7. **`QualityDetails`**: resumen en lenguaje claro + `<Disclosure>` con las 4 dimensiones (esquema, completitud, temporalidad, trazabilidad), `score_total`, `eligibility_status` y `eligibility_reasons` traducidos.
8. **`CitationBlock`**: dataset, publicador, consulta SoQL, fecha de ejecución, URL, `data_updated_at` y corte estadístico. **Regla dura del contrato §5:** si `data_cutoff_basis === "data_updated_at_fallback"`, el texto dice *"fecha de actualización del portal; corte estadístico desconocido"* y **nunca** la palabra "corte".
9. **Acciones**: Insertar en sección · Descargar CSV · Copiar cita.

**RF-404:** si `quality.classification === "no_recomendada"`, el botón Insertar abre un `Modal` con el motivo, exige un clic de confirmación explícito, y el nodo insertado lleva marca visual permanente de advertencia.

### 8.3 Traducción de valores internos (respuesta directa a "dim_N, metric_N y mensajes técnicos")

| Interno | Mostrado al usuario | Dónde vive el original |
|---|---|---|
| `dim_1` (resuelto a `municipio`) | **Municipio** | detalle técnico + CSV (columna "nombre técnico") |
| `metric_sum_1` (sobre `valor`) | **Suma de Valor** | ídem |
| `group_count` | **Número de registros del grupo** | ídem |
| alias no resoluble | el alias crudo + ⚠ *"nombre técnico de la consulta"* | — |
| `retrieve_candidates` | "Buscando conjuntos de datos relacionados…" | detalle |
| `select_candidate` | "Eligiendo el conjunto de datos más pertinente…" | detalle |
| `profile_dataset` | "Revisando qué columnas tiene ese conjunto…" | detalle |
| `build_plan` / `validate_plan` | "Preparando la consulta…" / "Verificando que la consulta sea válida…" | detalle |
| `explore_value` | "Buscando cómo está escrito ese valor en la fuente…" | detalle |
| `execute_query` | "Consultando datos.gov.co…" | detalle |
| `validate_quality` | "Evaluando la calidad de los datos…" | detalle |
| `derive_claims` | "Verificando cada cifra contra los datos de origen…" | detalle |
| `persist_facts` / `synthesize` / `complete` | "Guardando lo verificado…" / "Redactando la respuesta…" / "Listo" | detalle |
| `next_candidate` | "Ese conjunto no servía; probando con otro…" | detalle |
| `abstain` | "No encontré datos que respondan la pregunta" | detalle |
| `ALL_CANDIDATES_REJECTED` | "Revisé varios conjuntos de datos, pero ninguno respondía la pregunta." | detalle |
| `EVIDENCE_NOT_ELIGIBLE` | "Los datos encontrados no cumplen los criterios mínimos para citarse." | detalle |
| `NO_CANDIDATES` | "No encontré ningún conjunto de datos relacionado con tu pregunta." | detalle |
| `*_BUDGET_EXCEEDED` | "La investigación alcanzó su límite de tiempo/pasos antes de encontrar una respuesta." | detalle |
| `CLAIMS_NOT_AVAILABLE` | "Encontré datos, pero no pude verificar ninguna cifra con la precisión exigida." | detalle |
| `RUN_TIMEOUT` | "La investigación tardó demasiado y se detuvo." | detalle |
| `SOCRATA_TIMEOUT` / `SOCRATA_ERROR` | `message_user` del backend (ya viene en español) | `message_dev` en detalle |

**Regla:** el diccionario es un **mapa exhaustivo con caso por defecto seguro**. Una clave desconocida muestra un texto genérico honesto (*"Paso de la investigación"* / *"La investigación se detuvo por una razón técnica"*) y el valor crudo en el detalle. **Nunca** se muestra un enum crudo en la superficie primaria, ni se inventa un significado.

---

## 9. Estrategia Tiptap / citas

### 9.1 Extensiones

```js
// EvidenceCitationNode — nodo de bloque, atomic, no editable en su interior
Node.create({
  name: 'evidenceCitation',
  group: 'block', atom: true, draggable: false, selectable: true,
  addAttributes: () => ({
    citationId, runId, evidenceId, datasetId, datasetName, publisher,
    soqlQuery, executedAt, sourceUrl, dataUpdatedAt, dataCutoffAt, dataCutoffBasis,
    claims: [{ claimId, label, displayValue, unit, sourceHash }],
    qualityScore, qualityClassification, insertedAt
  }),
  parseHTML / renderHTML  // atributos serializados como data-*, contenido como texto plano
})
```

```js
// ManualEntryNode — visual y semánticamente distinto (T-506, Art. I + V)
Node.create({ name: 'manualEntry', group: 'block', atom: true,
  addAttributes: () => ({ value, text, source /* obligatorio */, url, date, createdAt }) })
```

**Invariante de inserción (RF-103, Art. I.2), verificado por prueba unitaria:** un comando `insertEvidenceCitation` **rechaza** el nodo si falta cualquiera de `datasetId`, `datasetName`, `publisher`, `soqlQuery`, `executedAt`, `sourceUrl`. No hay ruta de inserción alternativa: el `NodeView` no acepta edición manual de atributos.

**Prevención de HTML inseguro (R-06):**
1. Se persiste **JSON de ProseMirror**, nunca HTML (`editor.getJSON()`).
2. Los nodos se construyen **programáticamente** (`editor.commands.insertContent({type:'evidenceCitation', attrs})`), nunca por concatenación de strings HTML.
3. El texto de narrativa insertado entra como **nodos de texto**, no como HTML parseado.
4. `EvidenceCitation` es `atom: true`: su contenido no es editable ni parseable desde el portapapeles.
5. Pegar contenido externo pasa por el esquema restringido de Tiptap; se limita el `StarterKit` a los nodos necesarios (párrafo, encabezados 2–4, listas, negrita, cursiva, cita). Sin `HTMLNode`, sin `iframe`, sin `Link` con `javascript:`.

### 9.2 Exportación DOCX

Biblioteca **`docx`** (MIT, funciona en navegador, soporta notas al pie). Recorrido del JSON de ProseMirror → nodos `docx`:

| Nodo ProseMirror | Salida DOCX |
|---|---|
| `heading`/`paragraph`/listas/`blockquote` | equivalentes nativos |
| `evidenceCitation` | Párrafo con la cifra y su etiqueta + **`FootnoteReference`**; la nota al pie contiene dataset, publicador, consulta SoQL, fecha de consulta, corte y URL (RF-103) |
| `manualEntry` | Párrafo con prefijo literal **"Aporte manual — no verificado por el agente"** + nota al pie con la fuente declarada por el usuario |

La exportación ocurre **100 % en el cliente** (`Packer.toBlob` + descarga por `Blob` + `<a download>`; no hace falta `file-saver`). Alternativa evaluada y descartada: exportación en el backend — añadiría un endpoint, enviaría el documento del usuario al servidor y chocaría con Art. VI.4.

### 9.3 Plantillas (RF-101)

Mínimo normativo: **libre**, **MGA**, **plan de desarrollo**. Se conservan CONPES y Policy Brief del legacy como extras opcionales. La plantilla "plan de desarrollo" **no existe** y hay que redactarla — es contenido de dominio: **decisión abierta D-6** (requiere criterio del responsable, politólogo).

---

## 10. Seguridad y privacidad

### 10.1 Token de corrida (RF-801, RNF-011)

| Regla | Implementación verificable |
|---|---|
| Nunca en URL | El cliente no expone ninguna API que acepte token como query param; prueba que recorre todas las llamadas de fixtures E2E y falla si `cdt_rt_` aparece en cualquier URL registrada |
| Nunca en logs | `redact.js` aplicado antes de todo `console.*`; prueba que espía `console` durante un flujo completo |
| Nunca en mensajes de error | `ApiError.toString()` pasa por redacción |
| Nunca en telemetría | No hay telemetría de terceros en v2.0 |
| Solo por `Authorization: Bearer` | Único punto de inyección, en `agentClient` |
| Almacenamiento mínimo | `sessionStorage` por defecto (§7) |
| Limpieza | Al recibir `401`/`404` sobre una corrida, su token se elimina del almacén |

### 10.2 Otros

- **Cero claves de proveedor en el cliente.** Ninguna variable `NEXT_PUBLIC_*` distinta de `NEXT_PUBLIC_BACKEND_URL`. Job de CI que hace `grep` de patrones de claves sobre `.next/` (`pruebas.md` §6). Retirar `@google/generative-ai` de `dependencies`.
- **XSS:** sin `dangerouslySetInnerHTML` en todo el código nuevo (regla ESLint que lo prohíbe). Todo el contenido del backend se renderiza como texto. Las URLs de `source_url`/`external_sources` se validan (`https:` únicamente) antes de renderizar un `<a>`, siempre con `rel="noopener noreferrer"`.
- **Consentimiento (RF-802):** modal **antes del primer `POST`** de la sesión, con: qué se guarda (pregunta, contexto acotado, trazas y evidencias), para qué (funcionamiento y evaluación técnica), cuánto (90 días, `RETENTION_USER_DAYS`) y cómo borrarlo (botón por corrida). Versionado: `consentVersion` en el almacén; si sube, se vuelve a pedir.
- **Borrado (RF-803):** confirmación explícita ("esta acción no se puede deshacer"), `DELETE`, y limpieza del registro local **solo tras** 204 o 404.
- **Privacidad del documento:** el documento del usuario **nunca** se envía al backend. `context_hint` es un extracto acotado (≤1000 chars) y el usuario puede **ver exactamente qué se va a enviar** antes de confirmar, con opción de editarlo.

---

## 11. Accesibilidad (T-501 + T-505, RNF-007)

### 11.1 Tokens (plan.md §7 — valores exactos, no aproximados)

```css
:root{
  --cdd-blue-900:#0C2D57; --cdd-blue-700:#1D4E89; --cdd-blue-500:#2E7CD6;
  --cdd-blue-100:#DBEAFE; --cdd-blue-50:#EFF6FF;  --cdd-white:#FFFFFF;
  --cdd-slate-900:#0F172A; --cdd-slate-600:#475569; --cdd-slate-400:#94A3B8;
  --cdd-success:#15803D; --cdd-warning:#B45309; --cdd-error:#B91C1C;
}
```

Se exponen en `tailwind.config.js` como `cdd-blue-900`, etc. **Regla de erradicación progresiva:** el código nuevo solo usa `cdd-*`; una regla de ESLint/una prueba de estilo detecta clases `indigo-*`, `red-*`, `emerald-*`, `cyan-*`, `violet-*`, `amber-*` fuera de `pages/index.js` y `components/wizard/` (legacy congelado hasta T-704).

Contraste verificado por cálculo, no por intuición: `blue-700` (#1D4E89) sobre blanco = **8,2:1**; `blue-500` (#2E7CD6) sobre blanco = **3,9:1** → **`blue-500` NO se usa para texto normal**, solo para bordes, foco, iconos ≥24 px y fondos. `slate-400` sobre blanco = 2,8:1 → solo para elementos deshabilitados/decorativos, nunca para texto informativo.

### 11.2 Reglas obligatorias

| Regla | Cómo se cumple |
|---|---|
| Iconografía única | `lucide-react`; se retira `@fortawesome` |
| Foco visible | Anillo `2px` `--cdd-blue-500` + `offset 2px` en **todos** los interactivos; se elimina el `outline` rojo actual |
| Teclado completo | Sin trampas; modales con foco atrapado y retorno al disparador; drawer del copiloto cerrable con `Escape` |
| Semántica | `<main>`, `<aside>`, `<nav>`, encabezados jerárquicos sin saltos; `<html lang="es">` en `_document.js`; skip-link a `#contenido` |
| Reflujo 320 px | Sin scroll horizontal en el documento; solo las tablas y bloques de código SoQL scrollean dentro de su propio contenedor |
| Zoom 200 % | Unidades relativas; sin alturas fijas en píxeles para contenido de texto |
| Movimiento | `prefers-reduced-motion` respetado (se conserva el bloque de `globals.css`) |
| No solo color | Calidad, estado de conexión y advertencias siempre con **icono + texto** |
| Tablas | `<caption>`, `<th scope>`, contenedor scrollable enfocable |
| SSE | `aria-live="polite"` agrupado (§8.1); **jamás** `assertive` |
| Formularios | `<label>` explícito, `aria-describedby` para ayuda, errores asociados y anunciados |
| `reactStrictMode` | **Volver a `true`** en el proyecto v2 y arreglar lo que aflore (efectos duplicados en el stream: ya cubierto por la guardia de un solo stream por `runId`) |

Revisión manual obligatoria (`pruebas.md` §5) además de axe/Lighthouse: lector de pantalla NVDA en ESC-01 completo, orden de foco, contraste medido, reflujo real a 320 px.

---

## 12. Estrategia de pruebas

### 12.1 Herramientas: alternativas y recomendación

| Necesidad | Alternativas | **Recomendación** | Por qué |
|---|---|---|---|
| Unitarias + componentes | Jest+SWC · **Vitest** · node:test | **Vitest + @testing-library/react + jsdom** | ESM nativo (el código de `lib/` es ESM puro), arranque rápido, API compatible con Jest, no necesita `next/jest`. Riesgo: no es "el" default de Next 14 — mitigado porque no probamos rutas de Next, sino módulos puros y componentes. |
| E2E | **Playwright** · Cypress | **Playwright** | Ya es lo prescrito (plan.md §2, T-505); soporta `route.fulfill` para mockear SSE de forma determinista y trae emulación de red y de `prefers-reduced-motion`. |
| Accesibilidad en CI | axe-core CLI · **@axe-core/playwright** · Lighthouse CI | **@axe-core/playwright** (puerta) + **Lighthouse** manual/nightly | axe dentro del E2E evalúa el DOM real en cada estado (incluido `no_evidence` y modales), no solo la carga inicial |
| Lint | **ESLint + eslint-config-next** | ESLint | Detecta problemas de a11y básicos (`jsx-a11y` viene incluido) y permite la regla anti-`dangerouslySetInnerHTML` |
| Formato | Prettier | **Opcional, no bloqueante** | Evitar ruido de diffs; decisión del equipo |

**No instalar:** MSW (Playwright `route` basta y no añade un service worker al bundle de pruebas), Storybook (Art. III), Zustand/Redux (§13).

### 12.2 Pirámide y archivos

**Base — unitarias (Vitest), rápidas y sin red:**

| Archivo | Qué prueba | Casos mínimos |
|---|---|---|
| `tests/unit/parseSseChunk.test.js` | Parser SSE | evento simple; `data` multi-línea; `\r\n`; comentario `: ping`; **payload de 4 KB partido byte a byte**; JSON inválido; BOM; flush con resto incompleto |
| `tests/unit/streamRun.test.js` | Orquestador | dedupe por `seq`; `Last-Event-ID` en el reintento; backoff creciente con reloj falso; abort no marca error; 401/404 no reintentan; heartbeat vencido reconecta; terminal cierra el lector |
| `tests/unit/agentClient.test.js` | Contrato HTTP | encabezado `Bearer` presente; **token ausente de toda URL**; 422/429/401/404 → `ApiError` correcto; cuerpo no-JSON → `NETWORK`; DELETE 404 tratado como éxito |
| `tests/unit/runReducer.test.js` | Estado | secuencia feliz; evento duplicado = no-op referencial; hueco de `seq`; `interrupted` conserva parciales; `failed` sin narrativa; reconciliación sobrescribe sin duplicar |
| `tests/unit/resolveColumns.test.js` | H1 | `select a as dim_1, sum(b) as metric_sum_1 …`; `count(*) as group_count`; alias sin correspondencia → `resolved:false`; SoQL no parseable → todos crudos, sin excepción |
| `tests/unit/messages.es.test.js` | RNF-012 | los 14 nodos y las 10 `StopReason` tienen traducción; clave desconocida → texto genérico; **ninguna cadena de salida contiene `_` en MAYÚSCULAS** |
| `tests/unit/toCsv.test.js` | RF-501 | encabezados = los visibles; filas idénticas; comas/comillas/saltos escapados; bloque de cita presente; BOM UTF-8 para Excel |
| `tests/unit/documentMigrate.test.js` | Persistencia | v0→v1 idempotente; versión futura no se sobrescribe; JSON corrupto se aísla; cuota excedida avisa |
| `tests/unit/exportDocx.test.js` | RF-103 | cada `evidenceCitation` genera una nota al pie con los 6 campos; `manualEntry` lleva el prefijo literal |
| `tests/unit/citationNode.test.js` | Art. I.2 | inserción sin `soqlQuery` → rechazada; sin `sourceUrl` → rechazada; round-trip JSON conserva atributos |
| `tests/unit/manualEntry.test.js` | T-506 | `source` obligatorio; nunca produce llamadas de red; distinguible por atributos |
| `tests/unit/quality.test.js` | RF-402/404 | `no_recomendada` → requiere confirmación; `data_updated_at_fallback` **no** usa la palabra "corte" |

**Medio — componentes (Vitest + Testing Library):** `EvidenceCard`, `RunTimeline`, `ConsentDialog`, `Modal` (foco), `CopilotPanel` (responsive), `LiveRegion` (throttle). Cada uno con su aserción de a11y (`toHaveAccessibleName`, roles, `aria-*`).

**Cima — E2E (Playwright, backend mockeado por fixtures):**

| Archivo | Escenario | Criterio |
|---|---|---|
| `e2e/esc01-happy.spec.js` | ESC-01 completo | consentimiento → pasos → insertar → cita visible; **feedback <500 ms y primer paso <2 s medidos** (RNF-008) |
| `e2e/esc03-no-evidence.spec.js` | `no_evidence` | reporte + sugerencias, sin tabla vacía rota |
| `e2e/esc05-no-recomendada.spec.js` | RF-404 | inserción exige confirmación |
| `e2e/esc08-persistence.spec.js` | ESC-08 | recarga conserva documento y citas |
| `e2e/reconnect.spec.js` | RF-209 | corte de red a mitad → reconexión → **cero pasos duplicados** |
| `e2e/interrupted.spec.js` | `interrupted` | mensaje correcto + parciales |
| `e2e/failed.spec.js` | `failed` | `message_user`, botón reintentar solo si `retryable` |
| `e2e/delete-run.spec.js` | RF-803 | DELETE → desaparece del historial |
| `e2e/keyboard.spec.js` | RNF-007 | flujo completo solo con teclado; foco visible en cada parada |
| `e2e/a11y-axe.spec.js` | Puerta parcial | axe sin errores críticos en 5 estados (inicial, streaming, completed, no_evidence, modal) |
| `e2e/mobile-320.spec.js` | Reflujo | viewport 320×568 sin scroll horizontal del `body` |

**Fuera de la pirámide:** una prueba E2E **local, manual, no en CI** contra el backend real (`quickstart.md`) para el flujo principal — verifica que los fixtures no divergieron del runtime (R-13).

### 12.3 Fixtures: la regla más importante

> **Los fixtures se capturan de corridas reales, nunca se escriben a mano desde el contrato.**

Motivo: H1–H5 demuestran que el contrato y el runtime divergen. Un fixture inventado desde `api-rest.md` produciría un frontend que funciona en pruebas y falla contra el backend real. Procedimiento en F0: correr 3–4 corridas locales (o extraer los `final_answer` ya persistidos en Postgres / en los reportes de `backend/eval/reports/`), anonimizar, y guardar en `tests/fixtures/` con un `README` que registre **de qué corrida y de qué commit** salió cada uno. Casos mínimos: `completed` con claims y `label` verificado; `completed` con `presentation_warnings`; `no_evidence`; `interrupted`; `failed`; un stream SSE completo grabado.

---

## 13. Estrategia de estado (sin biblioteca nueva)

**Recomendación: React nativo — `useReducer` + `useContext` + hooks propios. Sin Zustand, Redux, Jotai ni React Query.**

Justificación contra Art. III (cada dependencia debe justificarse contra un RF/RNF):
- El estado del servidor **no es caché**: es un stream de eventos monotónico con dedupe por `seq`. React Query resuelve un problema distinto (invalidación/caché de peticiones) y no aporta aquí.
- El árbol de estado compartido es **pequeño y de un solo dueño** (la corrida activa + historial + documento). Tres `Context` bastan: `AgentRunContext`, `DocumentContext`, `SessionContext`.
- El reducer puro es **más fácil de probar** que cualquier store, y las pruebas del reducer son la mitad del valor de la suite.
- Riesgo asumido: re-renders. Se mitigan con `Context` separados por dominio y `React.memo` en los componentes de lista. Si medimos un problema real, **entonces** se justifica una biblioteca — con datos, no por adelantado.

---

## 14. Fases e incrementos

Cada fase es un bloque revisable e independiente. `⚑ T-617` indica si puede empezar con T-617 abierta.

---

### F0 — Baseline, deuda técnica y herramientas · `⚑ puede empezar ya`

**Objetivo.** Dejar el terreno medido y las herramientas listas, sin escribir una línea de la app.
**Satisface.** Prerrequisito de T-501…T-506; Art. IV.3; `pruebas.md` §1.
**Archivos.** `frontend/package.json`, `.eslintrc.json`, `vitest.config.js`, `playwright.config.js`, `.env.local.example`, `tests/fixtures/**`, `docs/frontend-baseline-2026-07.md`, `.github/workflows/ci.yml` (job frontend), `.agents/skills/impeccable/`, `.codex/hooks.json` y artefactos compartidos aplicables de `.impeccable/` (skill Impeccable para Codex).
**Dependencias.** Node 20+ (local: v24.18.0, CI: 20). Instalación de devDependencies (§15).
**Contratos.** Ninguno todavía.
**Riesgos.** R-13 (fixtures divergentes) — se ataca aquí y solo aquí.
**Pruebas.** `npm run build` verde (baseline); `npm run test` ejecuta al menos una prueba trivial; `npx playwright test` arranca.
**Aceptación medible.**
1. `npm run build` verde con el código actual, tiempo y tamaño de bundle registrados en `docs/frontend-baseline-2026-07.md`.
2. `npm run lint`, `npm run test`, `npm run test:e2e` existen y corren (aunque casi vacíos) — cierra la brecha de `quickstart.md:212`.
3. CI ejecuta lint + unitarias + build en el job `frontend`.
4. ≥6 fixtures capturados de corridas **reales** con su procedencia documentada.
5. **Impeccable instalado y funcionando**: `npx impeccable install` con alcance local del proyecto y proveedor Codex, verificado cargando `$impeccable` y ejecutando su auditoría sobre una página; la instalación se documenta en el `README` del frontend. Se versionan la skill, el hook y los artefactos compartidos que correspondan; solo cachés, capturas y estado por desarrollador se añaden a `.gitignore` según la guía de la herramienta. Alternativa si `npx` falla: `git submodule add https://github.com/pbakaus/impeccable .impeccable` y enlazar el build de Codex siguiendo la documentación oficial.
6. Auditoría de dependencias: `npm audit` registrado; lista de paquetes a retirar aprobada.
**Rollback.** Revertir el commit; no toca código de la app.
**Fuera de alcance.** Cualquier componente, cualquier estilo, retirar dependencias legacy (eso es F1/F9).

---

### F1 — Sistema de diseño y primitivas accesibles · `⚑ puede empezar ya`

**Objetivo.** Tokens exactos de plan.md §7 + una librería mínima de primitivas accesibles, con página de demostración interna.
**Satisface.** T-501, RNF-007, Art. V.1/V.2.
**Archivos.** `tailwind.config.js` (reescritura), `styles/tokens.css`, `styles/globals.css` (refactor), `pages/_document.js`, `pages/_app.js`, `components/ui/*`, `pages/_dev/ui.js` (galería, excluida de producción).
**Dependencias.** `lucide-react`.
**Contratos.** —
**Riesgos.** R-09, R-10 (se resuelven estructuralmente aquí, antes de que haya contenido).
**Pruebas.** Componentes con Testing Library (roles, nombres accesibles, foco de `Modal`, `Disclosure` con `aria-expanded`); axe sobre la galería; prueba de contraste calculada sobre los tokens.
**Aceptación medible.** Los 12 tokens de plan.md §7 existen en Tailwind con sus hex exactos; `Modal` atrapa y devuelve el foco; galería sin errores críticos de axe; la galería a 320 px no produce scroll horizontal; `blue-500` no aparece como color de texto normal en ninguna primitiva.
**Rollback.** Los componentes nuevos no los usa nadie todavía; revertir es seguro.
**Fuera de alcance.** Refactorizar el legacy (`pages/index.js`, wizard) — queda congelado hasta T-704.

---

### F2 — Cliente REST/SSE aislado · `⚑ puede empezar ya (fixtures)`

**Objetivo.** Todo `lib/api`, `lib/sse`, `lib/agent` funcionando y probado, **sin un solo componente React**.
**Satisface.** RF-204, RF-209, RF-801, RNF-011.
**Archivos.** `lib/config/backendUrl.js`, `lib/api/{errors,agentClient,catalogClient,redact}.js`, `lib/sse/{parseSseChunk,streamRun}.js`, `lib/agent/{runReducer,runStates,messages.es}.js`, sus pruebas.
**Dependencias.** Ninguna nueva.
**Contratos consumidos.** `api-rest.md` §2, §3, §4, §6, §7, §7b.
**Riesgos.** R-01, R-02, R-03, R-12.
**Pruebas.** Toda la sección "base" de §12.2 relativa a SSE/cliente/reducer/mensajes.
**Aceptación medible.**
1. Un payload SSE de 4 KB partido byte a byte produce exactamente 1 evento.
2. Reconexión con 3 eventos repetidos → 0 duplicados en el estado.
3. `grep -r "cdt_rt_"` sobre las URLs registradas en todas las pruebas = 0 coincidencias.
4. Los 14 nodos y las 10 `StopReason` tienen traducción; ninguna salida de usuario contiene un `ENUM_EN_MAYUSCULAS`.
5. Cobertura ≥90 % de `lib/sse` y `lib/agent`.
**Rollback.** Módulos aislados sin consumidores; borrar la carpeta.
**Fuera de alcance.** UI, estado global, persistencia.

---

### F3 — Copiloto, consentimiento e historial · `⚑ puede empezar ya (fixtures); verificación final requiere backend local`

**Objetivo.** El flujo vivo: preguntar → ver pasos → estados terminales → historial → borrar.
**Satisface.** T-502; RF-104, RF-204, RF-209, RF-502, RF-802, RF-803, RF-804, RNF-008, RNF-012.
**Archivos.** `pages/app.js`, `hooks/{useAgentRun,useRunHistory,useConsent,usePolitePolite}.js`, `lib/session/*`, `components/agent/*`.
**Dependencias.** Ninguna nueva.
**Contratos.** §2, §3, §4 (parcial), §6, §7, §7b.
**Riesgos.** R-01, R-04, R-09, R-12; H3 (traducción).
**Pruebas.** Componentes + E2E `esc01-happy`, `reconnect`, `interrupted`, `failed`, `delete-run` contra mocks.
**Aceptación medible.**
1. Feedback visual <500 ms y primer paso <2 s, **medidos** en E2E (RNF-008).
2. Sin consentimiento no se emite ningún `POST` (prueba que espía la red).
3. Corte de red a mitad → la línea de tiempo continúa sin duplicados.
4. `DELETE` → 204 → desaparece del historial y del almacén local.
5. Ninguna cadena visible en inglés ni enum crudo (revisión con checklist RNF-012).
**Rollback.** La ruta `/app` es nueva; `/` legacy sigue intacta. Revertir = quitar la ruta.
**Fuera de alcance.** Tarjetas de evidencia (F4), canvas y citas (F5+).

---

### F4 — Evidencia, calidad y estados terminales · `⚑ puede empezar ya (fixtures)`

**Objetivo.** Presentar evidencia de forma comprensible, verificable y descargable.
**Satisface.** T-503; RF-401…404, RF-501, RF-503, RF-212 (visualización de `label`/`presentation_warnings`).
**Archivos.** `components/evidence/*`, `lib/evidence/*`.
**Dependencias.** Reutiliza `chart.js` + `react-chartjs-2` + `papaparse` (ya instaladas).
**Contratos.** §4, §4c, §5; `contracts/validacion-calidad.md`.
**Riesgos.** R-08, R-11 (**el módulo de alias es el corazón de esta fase**), H4 (gráfica sin insumo).
**Pruebas.** `resolveColumns`, `toCsv`, `quality`, componentes de evidencia; E2E `esc05-no-recomendada`.
**Aceptación medible.**
1. Ningún `dim_N`/`metric_N` visible en la superficie primaria con fixtures reales; si no se resuelve, aparece la advertencia explícita.
2. El CSV descargado tiene exactamente las columnas y filas visibles + bloque de cita, y abre correctamente en Excel (BOM).
3. `no_recomendada` exige confirmación.
4. `data_updated_at_fallback` nunca muestra la palabra "corte".
5. Sin `chart_suggestion` y sin condiciones del fallback → **no aparece contenedor vacío** (`pruebas.md` §5).
6. `presentation_warnings` se muestra separado de `quality.warnings_user`.
**Rollback.** Componentes aislados; el copiloto de F3 puede renderizar sin ellos.
**Fuera de alcance.** Inserción en el documento (F5).

---

### F5 — Canvas, inserción de evidencia y citas Tiptap · `⚑ puede empezar ya`

**Objetivo.** El lienzo v2 y la inserción de evidencia con cita completa e inviolable.
**Satisface.** T-504 (parte de citas); RF-101, RF-103, RF-104, ESC-01.
**Archivos.** `components/canvas/*`, `components/canvas/editor/extensions/EvidenceCitationNode.js`, `lib/document/schema.js`.
**Dependencias.** Tiptap ya instalado (`@tiptap/core` y `@tiptap/pm` presentes).
**Contratos.** §5 (`citation`).
**Riesgos.** R-05, R-06.
**Pruebas.** `citationNode.test.js`; E2E ESC-01 con inserción y cita visible.
**Aceptación medible.** Insertar sin cualquiera de los 6 campos obligatorios es **imposible** (prueba que lo intenta y falla); el documento serializa a JSON de ProseMirror, **no** a HTML; "Investigar" desde una sección envía `context_hint` derivado y el usuario ve exactamente qué se envía.
**Rollback.** El nodo es aditivo; documentos sin él siguen abriendo.
**Fuera de alcance.** Autoguardado y exportación (F6).

---

### F6 — Autoguardado, migración y exportación DOCX · `⚑ puede empezar ya`

**Objetivo.** Que el trabajo del usuario no se pierda y salga en un formato oficial.
**Satisface.** T-504 (resto); RF-102, RF-103, ESC-08.
**Archivos.** `hooks/useAutosave.js`, `lib/document/{storage,migrate,exportDocx}.js`, `components/canvas/ExportMenu.jsx`.
**Dependencias.** **`docx`** (nueva, §15).
**Riesgos.** Cuota de `localStorage`, corrupción, versión futura.
**Pruebas.** `documentMigrate`, `exportDocx`; E2E `esc08-persistence`.
**Aceptación medible.** Autoguardado ≤5 s desde el último cambio (medido con reloj falso y en E2E); cerrar/reabrir conserva documento y citas; el `.docx` abre en Word con las notas al pie completas; un documento de versión futura no se sobrescribe.
**Rollback.** Desactivar el autoguardado deja el comportamiento actual (memoria); los documentos ya guardados siguen leyéndose.
**Fuera de alcance.** Exportación a PDF (no la pide ningún RF).

---

### F7 — Aporte manual · `⚑ puede empezar ya`

**Objetivo.** Permitir datos externos **sin contaminar** la evidencia verificada.
**Satisface.** T-506; research.md §18; Art. I + V.
**Archivos.** `components/canvas/ManualDataEntry.jsx`, `components/canvas/editor/extensions/ManualEntryNode.js`.
**Riesgos.** Confusión visual con evidencia verificada (riesgo constitucional, no cosmético).
**Pruebas.** `manualEntry.test.js`; prueba de que el módulo **no realiza ninguna llamada de red**; captura comparativa en el PR.
**Aceptación medible.** `source` obligatorio; badge literal **"Aporte manual — no verificado por el agente"**; color semántico propio y sin el icono de evidencia; distinguible a simple vista en la misma sección (captura); persiste tras cerrar y reabrir; el prellenado desde `external_sources` funciona **cuando el campo viene poblado** y el botón **no se muestra** cuando llega vacío (H5) — sin inventar entidades.
**Rollback.** Nodo aditivo.
**Fuera de alcance.** Cualquier escritura en tablas backend (prohibido por diseño).

---

### F8 — E2E, accesibilidad, RNF-012 y endurecimiento · `⚑ puede empezar ya`

**Objetivo.** Cerrar las puertas de calidad.
**Satisface.** T-505; RNF-007, RNF-011, RNF-012; `pruebas.md` §5 y §6.
**Archivos.** `tests/e2e/*`, `ci.yml`, `docs/release-wcag-<version>.md`, `docs/release-rnf-012-<version>.md`.
**Dependencias.** `@playwright/test`, `@axe-core/playwright`.
**Aceptación medible.** Suite E2E completa verde en CI con backend mockeado; axe sin errores críticos en 5 estados; **acta manual WCAG 2.2 AA** archivada (teclado, NVDA, zoom 200 %, 320 px, contraste medido, no-solo-color, `aria-live` sin saturación); **acta RNF-012** archivada; `grep` de patrones de claves sobre `.next/` = 0; `npm audit` sin críticas.
**Rollback.** Las puertas de CI se pueden marcar no bloqueantes temporalmente **con justificación escrita**; nunca borrarlas.
**Fuera de alcance.** Lighthouse como puerta dura (queda como medición nightly).

---

### F9 — Limpieza de dependencias y preparación de T-702 · `⚑ empieza ya; T-702 requiere T-701 (backend certificado)`

**Objetivo.** Dejar el proyecto listo para desplegarse el día que T-617 → T-701 cierren.
**Satisface.** Preparación de T-702; Art. III; RNF-011.
**Archivos.** `package.json` (retiros), `README` del frontend, `.env.local.example`, checklist de despliegue en `docs/`.
**Aceptación medible.** Bundle reducido (comparación contra el baseline de F0); `@google/generative-ai`, `three`, `react-globe.gl`, `d3`, `reactflow`, `katex`, `react-katex`, `@fortawesome/*`, `react-joyride` retiradas **sin romper el build** del legacy (verificar: `framer-motion` sigue en uso por el wizard → **no retirar hasta T-704**); documento de despliegue con: variable `NEXT_PUBLIC_BACKEND_URL`, exigencia de añadir el origen **exacto** del preview de Vercel a `CORS_ALLOWED_ORIGINS` (prohibido `*.vercel.app`, plan.md §11), y checklist de verificación en preview.
**Rollback.** Reinstalar el paquete retirado.
**Fuera de alcance.** **El despliegue en sí (T-702) — bloqueado por T-701, bloqueado por T-617.**

---

### F10 (opcional) — Explorador de catálogo · `⚑ requiere backend local con índice`

`GET /v2/catalog/search` expone RF-302 "para el explorador de catálogo del frontend" (contrato §8), pero **ningún RF del grupo 100/500 lo exige**. Se planifica como incremento opcional posterior a F8, no como parte del alcance mínimo de v2.0 (Art. III).

### 14.1 ¿Por qué este orden?

Se conserva el orden propuesto por el usuario con **dos ajustes derivados de dependencias reales**:
1. **F2 antes que F3** (ya estaba): el cliente aislado debe existir antes que cualquier UI que lo consuma. Confirmado.
2. **La captura de fixtures se adelanta a F0** (originalmente implícita en F2): por H1–H5, construir contra el contrato en lugar de contra el runtime real es el riesgo más caro del proyecto. Los fixtures son un prerrequisito, no un subproducto.
3. **F1 puede solaparse con F2** (equipos/agentes distintos): no comparten archivos. Es la única paralelización segura.

---

## 15. Dependencias nuevas propuestas

| Paquete | Tipo | Justificación (RF/RNF) | Alternativas evaluadas | Riesgo |
|---|---|---|---|---|
| `lucide-react` | prod | plan.md §7 exige **una** familia de iconos (Lucide, literal). Reemplaza `@fortawesome/*` | Heroicons (no es la prescrita); SVG a mano (inconsistente) | Bajo; tree-shakeable |
| `docx` | prod | RF-102/RF-103: `.docx` con **notas al pie** generado en el cliente (Art. VI.4: el documento no sale del equipo) | `docxtemplater` (módulo de footnotes es comercial); `html-docx-js` (sin footnotes, sin mantenimiento); backend (viola Art. VI.4 y añade endpoint) | Medio: ~500 KB → **cargar con `next/dynamic`** solo al exportar |
| `vitest`, `@vitejs/plugin-react`, `jsdom` | dev | Art. IV: sin pruebas no hay entrega | Jest+`next/jest` (más lento, fricción con ESM) | Bajo |
| `@testing-library/react`, `@testing-library/user-event`, `@testing-library/jest-dom` | dev | Pruebas de componentes centradas en accesibilidad | Enzyme (obsoleto) | Bajo |
| `@playwright/test` | dev | Prescrito por plan.md §2 y T-505 | Cypress | Bajo |
| `@axe-core/playwright` | dev | `pruebas.md` §5: puerta parcial automatizada | axe CLI, Lighthouse CI | Bajo |
| `eslint`, `eslint-config-next` | dev | Art. IV.3 (lint en CI) + reglas `jsx-a11y` + prohibición de `dangerouslySetInnerHTML` | Biome (no estándar aquí) | Bajo |

**Reutilizadas sin instalar nada:** Tiptap (4 paquetes ya presentes), Chart.js + react-chartjs-2, PapaParse, Tailwind + typography.

**Retiros propuestos (F9):** `@google/generative-ai` (RNF-011), `three` + `react-globe.gl`, `d3`, `reactflow`, `katex` + `react-katex`, `@fortawesome/free-solid-svg-icons` + `@fortawesome/react-fontawesome`, `react-joyride`.
**No retirar todavía:** `framer-motion` (la usa `pages/index.js` legacy; sale con T-704).

---

## 16. Riesgos y mitigaciones (consolidado)

| ID | Mitigación concreta | Fase | Verificación |
|---|---|---|---|
| R-01 | `redact.js` + único punto de inyección de `Authorization` + `sessionStorage` | F2 | Prueba de `grep` sobre URLs/logs |
| R-02 | Parser incremental probado byte a byte | F2 | 8 pruebas del parser |
| R-03 | Dedupe por `seq` + no-op referencial | F2 | Prueba de reconexión |
| R-04 | Aviso en consentimiento + opt-in explícito | F3 | Revisión RNF-012 |
| R-05 | Comando de inserción que rechaza citas incompletas | F5 | Prueba que intenta y falla |
| R-06 | JSON de ProseMirror + nodos programáticos + esquema restringido | F5/F6 | Prueba de round-trip y de pegado |
| R-07 | Auditoría de bundle en CI | F0/F8 | Job en verde |
| R-08 | `resolveColumns` + CSV con nombre real y técnico | F4 | Prueba de CSV vs. tabla |
| R-09 | `LiveRegion` con agrupación y throttle | F1/F3 | Revisión manual con NVDA |
| R-10 | Drawer responsive, sin `hidden lg:flex` | F1 | E2E a 320 px |
| R-11 | Igual que R-08 + advertencia si no resuelve | F4 | Fixtures reales |
| R-12 | Diccionario exhaustivo con default seguro | F2/F3 | Prueba de cobertura de claves |
| R-13 | **Fixtures capturados de corridas reales** + E2E local contra backend real | F0/F8 | `README` de procedencia |
| R-14 | Cliente tolerante a campos desconocidos + prueba de contrato | F2 | Prueba con payload extendido |

---

## 17. Decisiones abiertas que requieren autorización humana

> Ninguna de estas bloquea F0–F2. Se listan por orden de urgencia real.

| ID | Decisión | Por qué necesita al humano | Recomendación | Bloquea |
|---|---|---|---|---|
| **D-1** | **Almacenamiento del token**: `sessionStorage` (privado) vs. `localStorage` (cómodo) | Compromiso privacidad ↔ usabilidad con implicación constitucional (Art. VI.2, RF-801) | `sessionStorage` por defecto + opt-in explícito | F3 |
| **D-2** | **Rama base y aislamiento del worktree** frente al agente de T-617 | Coordinación entre agentes; riesgo de pisar trabajo ajeno | `git worktree` separado, base `fa08ee5` (§18) | F0 |
| **D-3** | **H1 — alias `dim_N`**: ¿parcheo solo en el cliente, o se pide un campo aditivo al backend (`columns: [{alias, field_name, display_name}]`)? | Cambiar el backend exige enmendar `contracts/api-rest.md` §5 y coordinar con T-617 | **Ambas**: cliente ya (no bloquea), y **proponer** la tarea backend para retirar el parseo después | F4 (parcialmente) |
| **D-4** | **H4 — RF-503 sin `chart_suggestion`**: ¿el cliente deriva la gráfica o se difiere RF-503? | RF-503 es un requisito de spec.md; derivar en cliente roza la frontera de Art. I | Derivar **solo** con 1 dimensión + 1 métrica + ≥3 filas, replicando valores sin calcular nada nuevo; y abrir tarea backend | F4 |
| **D-5** | **H5 — `datasets_reviewed` y `external_sources` vacíos** en el determinista: ESC-03 queda incompleto y T-506 pierde el prellenado | Es una brecha funcional del backend, no del frontend | Frontend degrada con elegancia y **no inventa**; abrir tarea backend con prioridad, porque ESC-03 es un escenario normativo | F4/F7 (degradado) |
| **D-6** | **Contenido de la plantilla "plan de desarrollo"** (RF-101) | Requiere criterio de politólogo (mismo caso que T-601) | El humano redacta las secciones; el agente las cablea | F5 |
| **D-7** | **Ruta del app v2**: `/app` nueva vs. reemplazar `/` | Afecta a usuarios actuales de cuestiondedatos.com | `/app` hasta T-704; luego decidir el cambio de landing | F3 |
| **D-8** | **Alcance del explorador de catálogo (F10)** | No lo exige ningún RF de frontend | Fuera del alcance mínimo de v2.0 | — |
| **D-9** | **Texto exacto del consentimiento RF-802** | Tiene efectos legales/de privacidad | Borrador del agente, **aprobación literal del humano** | F3 |

---

## 18. Git, coordinación y propuesta de PRs

### 18.1 Situación observada (2026-07-25)

- Rama actual `feat/t617-gate-preflight`, HEAD `fa08ee5`, **60 commits por delante de `v2`**; `v2` es ancestro directo (0 commits divergentes).
- Worktree: **solo `CLAUDE.md` modificado** entre los rastreados + **72 archivos untracked** (reportes de `backend/eval/reports/` y docs). Nada del frontend está tocado.
- `frontend/` no se modifica desde `c84264c` (T-101). Es **completamente independiente** del trabajo de T-617.

### 18.2 Estrategia recomendada

1. **No tocar** `CLAUDE.md` ni los 72 untracked. No hacer `git add -A` jamás en este repositorio; usar siempre rutas explícitas (`git add frontend/...`).
2. **Usar un `git worktree` separado** para que los dos agentes no compartan directorio de trabajo:
   ```bash
   git worktree add ../cdd-frontend-v2 -b feat/t501-frontend-v2 fa08ee5
   ```
   Base **`fa08ee5`** (no `v2`): así el worktree del frontend contiene también el backend determinista actual, y se puede levantar el backend local sin depender del otro agente. Alternativa: base `v2` (44b2e98) — más limpia históricamente, pero el backend de ese árbol es viejo y no sirve para integración local.
3. **Ninguna rama, ningún commit en esta sesión.** El primer commit lo hace la sesión de implementación, en su worktree.
4. Integración: PRs pequeños **hacia `v2`** (la rama de integración del proyecto, coherente con "PR hacia `v2`" que usan las tareas cerradas). Cuando T-617 se fusione a `v2`, rebasar la rama del frontend.
5. Todo commit menciona su `RF-###`/`RNF-###`/`T-5xx` (specs/README.md regla 3) y declara los artículos constitucionales tocados.

### 18.3 PRs propuestos, en orden

| # | PR | Fase | Contenido | Tamaño |
|---|---|---|---|---|
| 1 | `chore(frontend): baseline, tooling y fixtures reales` | F0 | scripts, Vitest, Playwright, ESLint, CI, fixtures, Impeccable | M |
| 2 | `feat(frontend): tokens de diseño y primitivas accesibles (T-501, RNF-007)` | F1 | Tailwind, tokens, `components/ui`, galería | M |
| 3 | `feat(frontend): parser SSE incremental (RF-204)` | F2 | `parseSseChunk` + 8 pruebas | **S** |
| 4 | `feat(frontend): cliente HTTP del agente y sobre de error (RF-801, §6)` | F2 | `agentClient`, `errors`, `redact`, `backendUrl` | S |
| 5 | `feat(frontend): stream con reconexión y deduplicación (RF-209)` | F2 | `streamRun` | M |
| 6 | `feat(frontend): reducer de corrida y mensajes en español (RNF-012)` | F2 | `runReducer`, `messages.es` | M |
| 7 | `feat(frontend): copiloto con pasos en vivo y consentimiento (T-502, RF-802)` | F3 | hooks + `components/agent` + `/app` | **L** → dividir en 7a (copiloto+timeline) y 7b (consentimiento+historial+borrado) |
| 8 | `feat(frontend): resolución de columnas y descarga CSV (RF-501)` | F4 | `resolveColumns`, `humanizeField`, `toCsv` | M |
| 9 | `feat(frontend): tarjetas de evidencia, calidad y claims (T-503, RF-401…404)` | F4 | `components/evidence` | L → dividir si supera ~600 líneas |
| 10 | `feat(frontend): gráfica simple de evidencia (RF-503)` | F4 | `chartSpec`, `EvidenceChart` | S |
| 11 | `feat(frontend): canvas v2 y nodo de cita de evidencia (T-504a, RF-103)` | F5 | canvas + extensión Tiptap | L |
| 12 | `feat(frontend): autoguardado y migración del documento (RF-102, ESC-08)` | F6 | storage + migrate + hook | M |
| 13 | `feat(frontend): exportación DOCX con citas al pie (RF-103)` | F6 | `exportDocx` | M |
| 14 | `feat(frontend): aporte manual del usuario (T-506)` | F7 | nodo + formulario | M |
| 15 | `test(frontend): suite E2E, axe y actas de accesibilidad (T-505)` | F8 | E2E + CI + actas | L |
| 16 | `chore(frontend): retirar dependencias no usadas y preparar despliegue` | F9 | limpieza + doc de despliegue | S |

Regla: si un PR supera ~600 líneas de diff efectivo (sin fixtures ni lockfile), se parte.

---

## 19. Recomendación única sobre el primer incremento

> **Implementar el PR #3: `lib/sse/parseSseChunk.js` con sus 8 pruebas**, dentro de un bloque que primero cierre el PR #1 (F0) para tener Vitest y los fixtures reales.

Por qué este y no otro:
- **Es el punto de falla más caro y más silencioso.** Un parser que no maneja eventos partidos entre chunks funciona en desarrollo local (chunks grandes, red rápida) y falla en producción de forma intermitente e irreproducible. Empezar por aquí compra la mayor reducción de riesgo por línea escrita.
- **No depende de nada:** ni del backend, ni de T-617, ni de decisiones de diseño, ni de las decisiones abiertas D-1…D-9.
- **Es puro y pequeño** (~120 líneas + pruebas): el primer PR real del frontend v2 es revisable en 15 minutos y establece el estándar de calidad del resto.
- **Desbloquea todo:** `streamRun` → `runReducer` → copiloto → evidencia → canvas. Es la raíz del grafo de dependencias.

Lo que **no** conviene hacer primero: empezar por el diseño visual (bonito pero no reduce riesgo), o por el canvas (depende de decisiones abiertas), o por conectar el copiloto de una (mezcla cinco problemas en un PR imposible de revisar).

---

## 20. Checklist "listo para comenzar F0"

**Entorno**
- [ ] Node ≥20 disponible (local verificado: v24.18.0; CI usa 20).
- [ ] `npm ci` corre en `frontend/` sin errores.
- [ ] PostgreSQL local arriba (`compose.yaml`, normalmente `localhost:5433`) — necesario solo para capturar fixtures reales e integración local.
- [ ] Backend local arrancable (`quickstart.md`) con `AGENT_RUNTIME=deterministic`, `CORS_ALLOWED_ORIGINS` incluyendo `http://localhost:3000`, y **sin** `EVAL_MODE`.
- [ ] `frontend/.env.local` con `NEXT_PUBLIC_BACKEND_URL=http://localhost:8000` y **ninguna** clave de proveedor nueva.

**Coordinación**
- [ ] Confirmado con el agente de T-617 que no trabajará en `frontend/`.
- [ ] `git worktree` creado según §18.2 (D-2 decidida).
- [ ] Confirmado que no se harán `git add -A`, ni commits de los 72 untracked, ni de `CLAUDE.md`.

**Insumos de decisión**
- [ ] D-1 (almacenamiento del token) decidida.
- [ ] D-9 (texto de consentimiento) con borrador listo para aprobación.
- [ ] D-3, D-4, D-5 discutidas; si se aprueban tareas de backend, quedan registradas en `tasks.md` por quien corresponda (no por la sesión de frontend).

**Herramientas**
- [ ] Impeccable instalado localmente (`npx impeccable install`), `$impeccable` está disponible y su auditoría responde.
- [ ] Playwright con navegadores descargados (`npx playwright install`).

**Fixtures (lo más importante)**
- [ ] ≥6 payloads reales capturados: `completed` con claims etiquetados, `completed` con `presentation_warnings`, `no_evidence`, `interrupted`, `failed`, y un stream SSE grabado.
- [ ] Cada fixture documenta corrida de origen y commit.
- [ ] Ningún fixture contiene tokens ni datos personales.

---

## 21. Anexos

### 21.1 Discrepancias contrato ↔ código que conviene reportar (AGENTS.md, regla de conflictos)

| # | Contrato dice | Código hace | Recomendación |
|---|---|---|---|
| 1 | §5: `columns: [{field, type}]` con nombres reales | `string[]` con **alias** | Reportar; proponer campo aditivo (D-3) |
| 2 | §4: `intention` es string | objeto `IntentExtraction` | Reportar; el objeto es **mejor** → actualizar el contrato |
| 3 | §3: evento `evidence` "cada evidencia validada lista" | el determinista no lo emite | Reportar; o bien emitirlo, o bien acotar el contrato al runtime real |
| 4 | §5: `chart_suggestion` `null` "si no aplica" | siempre `null` | Reportar (D-4) |
| 5 | §4: `no_evidence_report.reason` es prosa; `datasets_reviewed` poblado | enum crudo; lista vacía | Reportar (D-5); afecta ESC-03 y T-506 |
| 6 | §3/§4: `display_message` "en español claro" | `reason` interna mezclada con enums | Reportar; el frontend traduce mientras tanto |

*(Reportar = anotarlo en el canal de coordinación del proyecto y, si procede, en `tasks.md`/`research.md` por quien tenga el encargo. Esta sesión no modifica documentos normativos.)*

### 21.2 Qué puede desarrollarse con fixtures y qué exige backend real

| Con fixtures (sin backend) | Requiere backend local | Requiere backend **certificado** (T-617→T-701) |
|---|---|---|
| F0, F1, F2 completos | Verificación real de SSE, heartbeat, CORS y `Last-Event-ID` | **T-702** (despliegue en Vercel) |
| F3, F4, F5, F6, F7 completos (mocks Playwright) | E2E local del flujo principal (`pruebas.md` §5) | Cualquier afirmación de "listo para producción" |
| F8 (suite E2E y axe en CI) | Comprobación de `DELETE` real y `404` tras borrado | Medición de RNF-001/009 con tráfico real (T-703) |
| F9 (limpieza de dependencias) | Captura de fixtures nuevos | — |

### 21.3 Qué bloquea T-702 pero no el desarrollo local

`AGENT_RUNTIME=deterministic` desplegado (T-701), dominio `api.cuestiondedatos.com`, `CORS_ALLOWED_ORIGINS` con el origen **exacto** del preview de Vercel (prohibido el comodín), cron de retención con `ADMIN_TOKEN` y `RETENTION_HASH_SALT`, y el cierre de T-617. Nada de eso impide F0–F9 en local.

---

**Fin del documento.** Producido sin modificar código, sin instalar dependencias, sin crear ramas ni commits y sin ejecutar los servicios.
