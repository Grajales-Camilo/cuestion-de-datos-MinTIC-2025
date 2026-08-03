# PREVIEW-01 — Plan reconciliado de staging diagnóstico

**Estado:** staging operativo; PREVIEW-01 ejecutado con hallazgos y conciliación documental R1 cerrada mediante la PR #30. No certifica el backend ni cierra tareas de producción.

Este documento reemplaza afirmaciones de cierre absoluto por la evidencia reconciliada en [el informe](./preview-01-staging-report.md) y el [manifiesto sanitizado](./preview-01-runs-manifest.json).

## Estado por incremento

| Incremento | Estado reconciliado | Evidencia o límite |
|---|---|---|
| PREVIEW-01A–E | Ejecutados | Infraestructura aislada y Preview protegida. |
| PREVIEW-01F | Verificación técnica ejecutada | REST/SSE técnico y evidencia de borrado; no es certificación productiva. |
| PREVIEW-01G | Ejecutado con hallazgos | 9 casos: 3 `completed`, 2 `no_evidence`, 4 `failed`. |
| PREVIEW-01H | Diagnóstico complementario | Aporta evidencia; no cierra T-617. |
| PREVIEW-01I | PASS documental | R1 versionada, validada e integrada mediante la PR #30; no equivale a certificación técnica o productiva. |

T-617 permanece **abierta/BLOCKED**. T-701, T-702 y T-703 permanecen abiertas y no están autorizadas ni iniciadas por este plan. PREVIEW-01 no es una promoción ni tráfico real.

## Inventario reconciliado

| Recurso | Identificador | Estado documentado |
|---|---|---|
| Servicio web Render | `srv-d9m4cfb7uimc739jpnlg` | `cdd-preview01-stg-api`, Virginia, backend temporal. |
| PostgreSQL Render | `dpg-d9m475tg1s2s73f7vi9g-a` | `cdd-preview01-stg-pg`, PostgreSQL 16, Virginia. |
| Proyecto Vercel | `prj_r5viLyiWhaHdnSQpixvtUzvoOnrp` | `cdd-preview01-staging`, aislado del proyecto productivo. |
| Preview Vercel inicial | `dpl_9UMFKVdVv5zWAfG7mBAkZTAAWP5j` | Fotografía histórica de R1: `https://cdd-preview01-staging-b4kspr0a5.vercel.app`. |
| Deployment Git vigente al cierre R1 | `dpl_5GLi5bai8yAd74UtSQF3pzUypQV2` | `READY`, fuente `git`, rama `v2`, commit `90ddbf01b10caa48e6dc243e784048dd24d6a175`. |
| Dominio estable de staging | — | `https://preview.cuestiondedatos.com`, alias del deployment Git anterior. |
| Deployment Vercel fallido | `dpl_GbGv4nctot8iwnqCBFban8aBStow` | Producción del proyecto aislado; falló por Output Directory `dist` inexistente; sin dominio productivo afectado. |

La destrucción sigue prevista para **2026-08-14 01:41:27 COT**. No se interpreta la etiqueta Production de un deployment del proyecto aislado como producción de Cuestión de Datos.

## Procedencia del frontend y límites de reproducibilidad

En la fotografía original de R1, el Preview Ready se había creado mediante `vercel deploy`, no por una integración Git. Ese deployment histórico no podía certificar el SHA desplegado y su upload contenía artefactos locales ajenos al commit: `.impeccable/`, `test-results/`, `next-dev.log` y `next-dev.err.log`. En consecuencia, no se reinterpreta retroactivamente como un artefacto limpio ni como deployment exacto de un commit.

La revalidación de Git sí confirmó que los archivos **rastreados** bajo `frontend/` del checkout usado coincidían con `origin/v2` `34b3473112fbd0f6dd6e187cb4182e64960d60db`; existía además un `frontend/.gitignore` local no rastreado. Esta coincidencia limitada no elimina la diferencia entre un checkout y un upload local.

La configuración documentada durante la fotografía original de R1 era framework Next.js, Node 20 y defaults de build compatibles con `npm run build`. `NEXT_PUBLIC_BACKEND_URL=https://cdd-preview01-stg-api.onrender.com` se limitaba al Preview. La Preview usaba Vercel Authentication. El origen CORS verificado entonces era exactamente `https://cdd-preview01-staging-b4kspr0a5.vercel.app`; no se documentaron comodines ni dominios productivos. Esta R1 no afirma que esa comprobación histórica certifique por sí sola los alias creados después.

Durante R1, el panel autenticado confirmó el nombre del proyecto, su ID, la ausencia de conexión Git y Vercel Authentication. El conector API de Vercel no resolvió entonces el proyecto ni los dos deployment IDs; esta discrepancia se conserva como límite histórico de aquella revalidación.

Al cierre documental del 2026-08-03, el mismo proyecto aislado ya está conectado a Git. La API de Vercel confirmó un deployment `READY` originado en Git para la rama `v2` y el commit `90ddbf01b10caa48e6dc243e784048dd24d6a175`, con los alias `preview.cuestiondedatos.com` y `cdd-preview01-git-3154eb-juan-camilo-grajales-bedoyas-projects.vercel.app`. Este estado vigente reemplaza únicamente la recomendación operativa de conectar Git; no cambia ni borra las limitaciones del deployment manual inicial.

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

## Operación posterior

La conexión Git del proyecto staging ya fue realizada. Los deployments posteriores deben conservar procedencia verificable desde ramas y commits, y el dominio estable debe seguir separado de producción. Este cierre documental no autoriza T-701, T-702, T-703, consultas nuevas, promoción ni cambios adicionales de infraestructura.
