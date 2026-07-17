# T-614 — smoke determinista y diagnóstico de recuperación

**Requisitos:** RF-601, RF-602, RF-603, RNF-002, RNF-004
**Fecha:** 2026-07-16
**Runtime:** `deterministic`
**Modelo:** `google/gemini-2.5-flash`
**Embeddings:** `gemini-embedding-2`
**Semilla:** `614010`

## Corridas comparadas

| Momento | eval_run_id | Reporte | Éxito | Recall@10 positivos | Negativos |
|---|---|---|---:|---:|---:|
| Línea base reproducible, antes de recuperación | `c40191ef-a095-448a-a357-e6b88c7ec784` | `c40191ef-a095-448a-a357-e6b88c7ec784.md` | 6/10 | 7/8 | 2/2 |
| Tras ampliar la ventana por variante | `6b53a592-f87f-4740-825e-dc534cdfd93d` | `6b53a592-f87f-4740-825e-dc534cdfd93d.md` | 6/10 | 8/8 | 2/2 |

La tasa de utilidad no cambió porque recuperar el dataset no garantiza que el
planificador lo resuelva. La mejora medida se limita a recuperación: recall@10
subió de 87,5 % a 100 % sin regresiones en los cuatro positivos sólidos ni en
los dos negativos.

## Comparación por caso

| Caso | Antes | Después | Rango esperado antes/después | Diagnóstico final |
|---|---:|---:|---|---|
| pilot-002-seguridad-homicidios | pasa | pasa | 1 / 1 | sin regresión |
| pilot-003-salud-vigilancia | pasa | pasa | 1 / 1 | sin regresión |
| pilot-005-empleo-publico | pasa | pasa | 1 / 1 | sin regresión |
| pilot-013-app-dnp | pasa | pasa | 1 / 1 | sin regresión |
| pilot-012-control-fiscal | falla | falla | fuera de top 10 / 1 | recuperación corregida; ahora falla después, por presupuesto de candidatos |
| pilot-021-sensibilizacion-valle | falla | falla | 1 / 1 | fallo posterior a recuperación; planificación/proveedor en la corrida final |
| pilot-022-red-vial | falla | falla | 1 / 1 | fallo posterior: `expected_fact_not_found`, propietario golden |
| pilot-038-precipitacion | falla | falla | 1 / 1 | fallo posterior: `expected_fact_not_found`, propietario golden |
| pilot-045-negativo-dato-personal | pasa | pasa | no aplica | abstención segura, cero evidencia/claims |
| pilot-046-negativo-tiempo-real | pasa | pasa | no aplica | abstención segura, cero evidencia/claims |

## Causa de recuperación: pilot-012

Intención observada: tema `hallazgos`, entidad `Contraloría General de
Antioquia`, términos `auditoría regular` y `administrativos`, operación
`lookup`. Dataset esperado normativo: `wasc-xi4h`.

| Variante | Posición esperada en top 25 | Similitud vectorial |
|---|---:|---:|
| `hallazgos Contraloría General de Antioquia` | no aparece | — |
| `hallazgos` | 15 | 0.596425 |
| `hallazgos auditoría regular administrativos` | 14 | 0.698936 |
| `hallazgos lookup` | 18 | 0.539393 |

Con ventana 10, el esperado desaparecía antes de la fusión. Con ventana 25,
aparece en tres variantes y el consenso lo eleva al puesto 3 combinado en el
diagnóstico aislado (score combinado 1.7296501); en el smoke posterior quedó
en el puesto 1. Las columnas relevantes observadas son
`hallazgos_administrativos`, `modalidad_de_auditor_a`, `sujeto_auditado` y
`vigencia`.

## Incremento implementado

`retrieve_candidates_multiquery` solicita 25 resultados por variante y
conserva el límite combinado de 10 candidatos. No cambia el presupuesto de 8
candidatos intentados, las consultas, exploraciones o llamadas LLM; no usa
IDs, facts ni URLs del golden. La prueba unitaria demuestra que un candidato
profundo con consenso entre variantes puede sobrevivir al truncado y que la
salida final sigue limitada a 10.

## Fallos restantes

- `pilot-012`: el esperado ya se recupera e intenta primero, pero el agente
  agota el presupuesto de candidatos tras fallos de perfil/plan; no es ya un
  fallo de recall.
- `pilot-021`: el esperado se recupera en rango 1; la corrida posterior terminó
  antes de evidencia por un fallo de planificación asociado a la ejecución
  real del proveedor.
- `pilot-022` y `pilot-038`: producen evidencia y claims, pero no satisfacen los
  `expected_facts`; el clasificador los asigna al contrato golden. No se cambió
  `golden-v1` ni `eval/metrics.py`.

T-615 no fue iniciada. No se diseñaron claims textuales ni se creó
`golden-v2.yaml`.
