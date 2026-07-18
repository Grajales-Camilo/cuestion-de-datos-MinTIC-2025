# Acta de aceptación final T-615

Fecha: 2026-07-17

Rama: `v2`
HEAD base de esta sesión: `94857ee43743d67ed67982e92399b16316f978c9`

## Incrementos de cierre

- T-615I-C: `a20d814` — `fix(eval): fully verify textual integrity snapshots`.
- T-615I-R: `1fcce2b` — `test(integration): isolate legacy catalog fixtures`.
- T-615J: este documento y el cierre mínimo en `tasks.md`.

## Matriz T-615B…I

| Incremento | Evidencia principal | Estado |
|---|---|---|
| T-615B | `7646dee`, dominio textual tipado | Cerrado |
| T-615C | `7c0fc76`, persistencia aislada | Cerrado |
| T-615D | `786fefa` + `2fbb702`, operaciones y grafía fuente | Cerrado |
| T-615E | `6c43768`, constructor y verificador | Cerrado |
| T-615F | `2ad96f9`, integración determinista interna | Cerrado |
| T-615G | `32f7a58` + `9b34f10`, API aditiva y corrección cuantitativa | Cerrado |
| T-615H | `46628ef` + `ecaadd2`, renderer persistido y certificado de orden | Cerrado |
| T-615I | `94857ee` + `a20d814`, métricas y snapshots privados completos | Cerrado |

## Evidencia T-615I-C

La aplicabilidad reúne tres superficies estructuradas: hechos públicos,
referencias textuales del plan y hechos persistidos/reverificados. La
reproducibilidad compara identidad, evidencia, dataset, operación, filas,
columnas, valores, texto factual, presentación, perfil, versión, parámetros y
hash. Un conjunto permitido vacío, inconsistente o inválido produce métricas
fallidas y no un error de infraestructura.

- Pruebas dirigidas de la corrección y contratos: `98 passed`.
- Suite completa sin integración al cerrar el incremento: `865 passed`.
- Integraciones focalizadas: `47 passed, 1 xfailed`.
- Privacidad: serialización JSON recursiva del modelo destinado a
  `eval_case_results`; no conserva texto, presentación, valores, filas,
  narrativa, resumen ni warnings libres.

## Evidencia T-615I-R

Los módulos que requieren controlar catálogos, publicadores, DIVIPOLA o
tipologías usan una base PostgreSQL temporal por prueba. Cada base:

1. usa nombre aleatorio con prefijo `t615ir_`;
2. instala `vector` y `pg_trgm`;
3. aplica `alembic upgrade head`;
4. se elimina explícitamente al terminar, incluso ante error.

Una fila centinela inactiva y bloqueada se crea en la base compartida antes de
las pruebas aisladas, se verifica antes y después de cada caso y solo se borra
en el teardown final de su propia fixture.

- Módulos saneados juntos: `41 passed`.
- Marca `integration`, ejecución 1:
  `119 passed, 1 skipped, 865 deselected, 1 xfailed`.
- Marca `integration`, ejecución 2:
  `119 passed, 1 skipped, 865 deselected, 1 xfailed`.
- Resultado final:
  `temporary_databases=0`, `sentinel_residue=0`, cero tablas
  `_test_backup_*`.
- `backend/uv.lock` conservó SHA-256
  `41798724A9AF5EF8029F193BFC29BAE50868091BE971BF596D1CF83E6B0B283C`.

El skip corresponde a RNF-010 real cuando falta configuración/índice apto. El
`xfail(strict=True)` continúa siendo el defecto documentado por el cual el
octavo candidato se selecciona pero no llega a perfilarse.

## Puerta T-615J

- Dominio, builder, contratos, runtime, renderer, API y evaluación:
  `265 passed`.
- Suite completa sin integración: `865 passed, 121 deselected`.
- Aceptación determinista, legacy, retención y persistencia textual focal:
  `51 passed, 1 xfailed`.
- La marca completa de integración fue verde dos veces, como se registra
  arriba.
- Rollback: flag textual apagado, aceptación legacy y forma cuantitativa
  permanecen cubiertos por las suites dirigidas y de integración.
- API REST, SSE, replay, aislamiento por `run_id`, retención y borrado están
  incluidos en las suites sin integración/integración verdes.

## OpenAPI y superficies congeladas

- SHA-256 canónico antes de T-615J:
  `d1627ed9394bb729ec98aa4d9d818db054efdd1ff4ce78654c37789ed651d89b`.
- SHA-256 canónico después de T-615J:
  `d1627ed9394bb729ec98aa4d9d818db054efdd1ff4ce78654c37789ed651d89b`.
- Diff semántico: vacío.
- `golden-v1.yaml` SHA-256:
  `ab546062767ce2046508489c169a270ae00ceb1515ff67bf92d472404630ff72`.
- No cambiaron API, contratos públicos, esquema relacional, prompts,
  recuperación, ranking, runtime predeterminado, comportamiento legacy,
  métricas cuantitativas ni umbrales.

## No ejecutado y riesgos

- No se ejecutaron Gemini, golden-v1 de 50 casos ni golden-v2.
- Las dos pruebas live históricas de Socrata sí formaron parte de la marca
  `integration`; no usan LLM ni generan costo de modelo.
- Permanece el `xfail(strict=True)` del octavo candidato, fuera del alcance de
  T-615.
- T-616 y T-617 permanecen sin iniciar.

## Decisión

**Puerta T-615 aprobada.** T-615B…I y las correcciones T-615I-C/T-615I-R
cumplen sus criterios. T-615J puede marcarse completa. Este cierre no autoriza
iniciar T-616 ni T-617.
