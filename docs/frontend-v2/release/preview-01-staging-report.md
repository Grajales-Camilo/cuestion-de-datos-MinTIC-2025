# Informe reconciliado PREVIEW-01 — R1

## Veredicto

**Staging operativo; PREVIEW-01 ejecutado con hallazgos y conciliación R1.** No es certificación del backend, no cierra T-617 y no habilita T-701, T-702 ni T-703. PREVIEW-01I queda pendiente de PASS hasta que esta R1 se valide y se acepte en Git.

## Revalidación

- `origin/v2`: `34b3473112fbd0f6dd6e187cb4182e64960d60db`.
- PR #28: fusionado mediante ese merge commit.
- CI `30548219279`: Backend y Frontend `success`.
- T-617: abierta/BLOCKED; T-701, T-702 y T-703: abiertas.
- Backend Render: `srv-d9m4cfb7uimc739jpnlg`, `https://cdd-preview01-stg-api.onrender.com`.
- PostgreSQL Render: `dpg-d9m475tg1s2s73f7vi9g-a`, PostgreSQL 16, Virginia.
- Vercel: `cdd-preview01-staging` (`prj_r5viLyiWhaHdnSQpixvtUzvoOnrp`).
- Destrucción prevista: 2026-08-14 01:41:27 COT.

Health respondió HTTP 200 con `database=ok`, `llm_provider=ok`, `catalog_index=ok`, 8.366 datasets indexados y `last_ingest_at=null`. El preflight CORS para el origen Preview devolvió HTTP 200 y el origen exacto `https://cdd-preview01-staging-b4kspr0a5.vercel.app`.

## Frontend Vercel

El Preview Ready es `dpl_9UMFKVdVv5zWAfG7mBAkZTAAWP5j` en `https://cdd-preview01-staging-b4kspr0a5.vercel.app`. Está protegido con Vercel Authentication y no usa dominios productivos. El proyecto usa framework Next.js, Node 20, defaults compatibles con `npm run build` y `NEXT_PUBLIC_BACKEND_URL=https://cdd-preview01-stg-api.onrender.com` limitado al Preview.

El proyecto no está conectado a Git. El Preview fue creado mediante `vercel deploy`; por tanto, Vercel no certifica un SHA. Aunque los archivos rastreados de `frontend/` coincidían con `origin/v2`, el upload incluyó `.impeccable/`, `test-results/`, `next-dev.log` y `next-dev.err.log` locales. No es un artefacto limpio ni un deployment exacto del commit. El deployment `dpl_GbGv4nctot8iwnqCBFban8aBStow` falló por Output Directory `dist` inexistente dentro del proyecto aislado; no afectó dominios ni producción de Cuestión de Datos.

El panel autenticado confirmó el proyecto, su ID, la ausencia de Git y la protección. El conector API de Vercel no resolvió este proyecto ni los deployment IDs, por lo que esa vía no certifica los IDs en R1; no se realizó ninguna modificación para resolver esa discrepancia.

## Corridas controladas y costos

La fuente primaria fue `preview_01g_results.json`; el detalle sanitario está en [el manifiesto](./preview-01-runs-manifest.json).

| Resultado | Conteo |
|---|---:|
| `completed` | 3 |
| `no_evidence` | 2 |
| `failed` | 4 |

`pilot-023` esperaba `2pnw-mmge` y observó `gdxc-w37w`. `pilot-004` terminó con 23 pasos y `LLM_BUDGET_EXCEEDED`; `pilot-033`, con 33 y el mismo motivo. El runtime determinista aplica presupuestos internos; no se afirma que `AGENT_MAX_STEPS=14` limitara esas corridas.

La suma observable de `estimated_cost_usd` de las nueve corridas es **USD 0.127938**. Es un límite inferior porque las fallidas no reportan uso completo. El smoke queda separado y el costo de embeddings no estuvo disponible.

## Huecos y limpieza

Faltan `stage_times_ms`, `calls_and_cost` y consultas Socrata persistidas; los errores terminales de varias fallidas están incompletos. No se infiere tiempo de transporte SSE comparando `total_time_ms` con `latency_ms`. Los fallos no se atribuyen solo a Socrata, pues hay reparaciones y planificación antes de algunos terminales.

La evidencia ejecutada conserva DELETE 204 y GET posterior 404: cero corridas persistidas en backend según la verificación ejecutada. Esto no implica cero residuo general; el navegador puede conservar documentos y citas locales.

Todos los `run_id` del manifiesto están excluidos explícitamente de T-703. No se realizaron cambios en Render, Vercel, CORS, dominios o variables durante R1.

## Recomendación

Autorizar en un incremento separado conectar `cdd-preview01-staging` a Git y desplegar futuras ramas desde commits verificables. Esta recomendación no autoriza nuevas corridas, despliegues, infraestructura ni promoción.
