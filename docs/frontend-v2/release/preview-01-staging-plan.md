# PREVIEW-01 — Plan reconciliado de staging diagnóstico

**Estado:** staging operativo; PREVIEW-01 ejecutado con hallazgos y en conciliación documental R1. No certifica el backend ni cierra tareas de producción.

Este documento reemplaza afirmaciones de cierre absoluto por la evidencia reconciliada en [el informe](./preview-01-staging-report.md) y el [manifiesto sanitizado](./preview-01-runs-manifest.json).

## Estado por incremento

| Incremento | Estado reconciliado | Evidencia o límite |
|---|---|---|
| PREVIEW-01A–E | Ejecutados | Infraestructura aislada y Preview protegida. |
| PREVIEW-01F | Verificación técnica ejecutada | REST/SSE técnico y evidencia de borrado; no es certificación productiva. |
| PREVIEW-01G | Ejecutado con hallazgos | 9 casos: 3 `completed`, 2 `no_evidence`, 4 `failed`. |
| PREVIEW-01H | Diagnóstico complementario | Aporta evidencia; no cierra T-617. |
| PREVIEW-01I | Pendiente de PASS | Requiere que R1 esté versionada y validada. |

T-617 permanece **abierta/BLOCKED**. T-701, T-702 y T-703 permanecen abiertas y no están autorizadas ni iniciadas por este plan. PREVIEW-01 no es una promoción ni tráfico real.

## Inventario reconciliado

| Recurso | Identificador | Estado documentado |
|---|---|---|
| Servicio web Render | `srv-d9m4cfb7uimc739jpnlg` | `cdd-preview01-stg-api`, Virginia, backend temporal. |
| PostgreSQL Render | `dpg-d9m475tg1s2s73f7vi9g-a` | `cdd-preview01-stg-pg`, PostgreSQL 16, Virginia. |
| Proyecto Vercel | `prj_r5viLyiWhaHdnSQpixvtUzvoOnrp` | `cdd-preview01-staging`, aislado del proyecto productivo. |
| Preview Vercel | `dpl_9UMFKVdVv5zWAfG7mBAkZTAAWP5j` | `https://cdd-preview01-staging-b4kspr0a5.vercel.app`. |
| Deployment Vercel fallido | `dpl_GbGv4nctot8iwnqCBFban8aBStow` | Producción del proyecto aislado; falló por Output Directory `dist` inexistente; sin dominio productivo afectado. |

La destrucción sigue prevista para **2026-08-14 01:41:27 COT**. No se interpreta la etiqueta Production de un deployment del proyecto aislado como producción de Cuestión de Datos.

## Procedencia del frontend y límites de reproducibilidad

El Preview Ready se creó mediante `vercel deploy`, no por una integración Git. El panel de Vercel confirma que el proyecto no está conectado a un repositorio; por ello Vercel no puede certificar el SHA desplegado. El upload contenía artefactos locales ajenos al commit: `.impeccable/`, `test-results/`, `next-dev.log` y `next-dev.err.log`. En consecuencia, no se describe como un artefacto limpio ni como deployment exacto de un commit.

La revalidación de Git sí confirmó que los archivos **rastreados** bajo `frontend/` del checkout usado coincidían con `origin/v2` `34b3473112fbd0f6dd6e187cb4182e64960d60db`; existía además un `frontend/.gitignore` local no rastreado. Esta coincidencia limitada no elimina la diferencia entre un checkout y un upload local.

La configuración documentada del proyecto aislado es framework Next.js, Node 20 y defaults de build compatibles con `npm run build`. `NEXT_PUBLIC_BACKEND_URL=https://cdd-preview01-stg-api.onrender.com` se limita al Preview. La Preview usa Vercel Authentication. El origen CORS permitido exactamente es `https://cdd-preview01-staging-b4kspr0a5.vercel.app`; no se documentan comodines ni dominios productivos.

Durante R1, el panel autenticado confirmó el nombre del proyecto, su ID, la ausencia de conexión Git y Vercel Authentication. El conector API de Vercel no resolvió este proyecto ni los dos deployment IDs; esta discrepancia de acceso se conserva como límite de revalidación, no como autorización para cambiar Vercel.

## Resultados de PREVIEW-01G

La fuente primaria es el artefacto local de resultados indicado en R1. El manifiesto contiene únicamente campos sanitizados por caso.

| Terminal | Casos | Conteo |
|---|---|---:|
| `completed` | `pilot-023`, `pilot-002`, `pilot-011` | 3 |
| `no_evidence` | `pilot-004`, `pilot-033` | 2 |
| `failed` | `pilot-017`, `pilot-029`, `pilot-038`, `pilot-039` | 4 |

`pilot-023-eva-agricultura` esperaba `2pnw-mmge` y terminó usando `gdxc-w37w`. `pilot-004` registró 23 pasos y `LLM_BUDGET_EXCEEDED`; `pilot-033`, 33 pasos y el mismo motivo. No se atribuyen esos resultados a que `AGENT_MAX_STEPS=14` haya limitado las corridas: el runtime determinista desplegado usa presupuestos internos que no aplican directamente `agent_max_steps`.

## Costos y observabilidad

La suma observable de las nueve corridas, recalculada desde `full_run_detail.answer.usage.estimated_cost_usd`, es **USD 0.127938**. Es un límite inferior: las cuatro fallidas no exponen uso completo. El smoke se mantiene separado. El costo de embeddings no quedó disponible.

Los huecos documentados son: `stage_times_ms` vacío, `calls_and_cost` vacío, `persisted_socrata_query=null`, errores terminales incompletos en varias fallidas y `last_ingest_at=null` en health. La diferencia entre tiempo total y `latency_ms` no demuestra por sí sola tiempo de transporte SSE. Los fallos no se atribuyen exclusivamente a Socrata: también pueden intervenir reparaciones o errores anteriores de planificación.

La revalidación de health registró HTTP 200, base de datos `ok`, proveedor LLM `ok`, índice de catálogo `ok`, 8.366 datasets indexados y `last_ingest_at=null`.

## Exclusión de T-703 y limpieza

Cada `run_id` del manifiesto lleva el motivo fijo `PREVIEW-01 synthetic controlled staging; not real traffic`; debe excluirse de T-703 aunque el endpoint público persista `retention_class=user`. No cuenta en tráfico, muestras, percentiles ni costo de T-703.

Se conserva evidencia de DELETE HTTP 204 y GET posterior HTTP 404: **cero corridas persistidas en backend según la verificación ejecutada**. No se afirma "zero residue" general: el navegador puede conservar documentos y citas por persistencia local incluso después de eliminar una corrida backend.

## Siguiente acción separada

Antes de desplegar frontend adicional, autorizar por separado conectar el proyecto staging a Git y usar deployments desde ramas/commits verificables. No autoriza T-701, T-702, T-703, consultas nuevas ni cambios de infraestructura.
