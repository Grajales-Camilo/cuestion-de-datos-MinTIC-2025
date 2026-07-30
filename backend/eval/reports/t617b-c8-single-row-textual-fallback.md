# T-617B-C8 — Preservación de LOOKUP textual verificable de una sola fila

## Estado

`READY_FOR_DIRECTED_PILOT013` / `FULL_GATE_BLOCKED`

- Rama: `feat/t617-gate-preflight`
- Baseline: `ac7c5894ce3b04a660ef861ce408f0747b7bbed1`
- Corrida que expuso el defecto:
  `e22d108c-fab5-44be-bb81-b7bd1420d441`
- No se ejecutó Gemini, Socrata ni una nueva corrida real en este incremento.

## Causa raíz

La evaluación dirigida recuperó el dataset correcto de `pilot-013-app-dnp`,
ejecutó un `LOOKUP` filtrado por el código solicitado y obtuvo exactamente una
fila con el tipo y el nombre del proyecto. Sin embargo, el planificador no
incluyó `textual_requests`. Con los hechos textuales habilitados, el pipeline
intentó construir claims cuantitativos a partir de dimensiones de texto,
rechazó todos los operandos y terminó agotando candidatos. La evidencia correcta
y material se perdió por la omisión de una instrucción auxiliar del LLM.

Esto contradice RF-211: una respuesta respaldada y suficientemente correcta no
debe convertirse en `no_evidence` por una imperfección no material. También
impide la aceptación de `pilot-013` definida en `pruebas.md` §4.5, que exige
responder con valores textuales verificables, no con un conteo.

## Corrección

Se añadió un fallback determinista de `direct_text` con activación conservadora:

1. la operación debe ser `LOOKUP`;
2. el plan no debe contener solicitudes textuales explícitas;
3. la consulta debe devolver exactamente una fila;
4. solo se consideran dimensiones `TEXT` seleccionadas;
5. el nombre real de cada columna debe solaparse léxicamente con la intención
   vigente;
6. se excluyen aliases que ya produjeron un claim cuantitativo.

El fallback no elige entre filas, no inspecciona valores para decidir qué
publicar y no usa `case_id`, `dataset_id`, preguntas, códigos ni respuestas
golden. Con varias filas o con texto no solicitado, la respuesta sigue siendo
rechazada. Las solicitudes textuales explícitas conservan la ruta existente.

Los hechos derivados usan la operación cerrada y reproducible `direct_text`;
persistencia, reverificación y síntesis continúan por la infraestructura T-615
existente.

## Regresiones

- Un `LOOKUP` de una fila con intención “tipo y nombre” y cuatro columnas de
  texto genera únicamente los dos hechos pedidos.
- Un `LOOKUP` de una fila con intención vaga no promueve columnas no pedidas.
- Un `LOOKUP` sin solicitud textual y con dos filas continúa rechazado y nunca
  se degrada a un conteo ficticio.
- La aceptación con PostgreSQL local demuestra persistencia antes de síntesis,
  sin usar la ruta legacy.

La prueba principal falla contra el baseline `ac7c589` con
`CLAIMS_REJECTED: operando no numérico` para las cuatro dimensiones y pasa con
la corrección. Durante la construcción de la aceptación, una pregunta que no
pedía el municipio fue rechazada correctamente; la fixture se corrigió para que
la pregunta real sí solicitara ese campo. Esto confirma que el fallback no
expone texto solo porque esté presente en la fila.

## Verificación

- Pruebas focalizadas: `60 passed`.
- Aceptación focalizada con PostgreSQL local: `1 passed`.
- `pytest -m "not integration" -q`: `1085 passed, 122 deselected`.
- `pytest -m deterministic_agent_acceptance -q`: `19 passed, 1188 deselected`.
- Integraciones compartidas: `95 passed, 1 skipped, 1111 deselected`.
- `pytest -m legacy_agent_acceptance -q`: `7 passed, 1200 deselected`.
- `ruff check .`: limpio.
- `ruff format --check` sobre los cuatro archivos modificados: limpio.
- `git diff --check`: limpio; solo advertencias locales LF/CRLF.
- SHA-256 `golden-v1`:
  `ab546062767ce2046508489c169a270ae00ceb1515ff67bf92d472404630ff72`.
- SHA-256 `golden-v2`:
  `1c78264cccb0da6a10920b6b212438cc40c2b70d2bbd40265f5794fdc754e483`.

No se cambiaron golden, `expected_facts`, presupuestos, umbrales, contratos,
migraciones ni cardinalidades.

## Siguiente puerta

Ejecutar una sola evaluación real `directed` de `pilot-013-app-dnp`, con hechos
textuales habilitados. Debe recuperar el dataset y la fila correctos, persistir
hechos reproducibles para tipo y nombre, producir una respuesta útil y no
registrar fabricación, huérfanos ni infraestructura. El `full` permanece
bloqueado; solo una validación dirigida satisfactoria permite repetir el smoke
canónico.

## C8A — auditoría de la primera validación real

La corrida dirigida `80d4bbec-2ea7-4d71-ba21-d22bb86218dd` sobre `c9009ae`
volvió a terminar en `no_evidence`, sin infraestructura ni fabricación. La
consulta real sí recuperó la misma fila correcta de `tmk8-iihq`, pero expuso un
defecto en la condición 4 original: `render_soql` produce la consulta interna
sin `OFFSET`, mientras `ejecutar_soql` devuelve para persistencia la misma
consulta normalizada por el parser (keywords en mayúsculas y `OFFSET 0`). La
comparación literal siempre era falsa en producción aunque la consulta fuera
semánticamente idéntica; el doble unitario devolvía el payload sin normalizar y
ocultó el defecto.

Se retiró esa igualdad de cadenas. No se relaja la procedencia de la consulta:
el ejecutor interno continúa recibiendo exclusivamente
`rendered.canonical_soql`, y la forma canónica que devuelve sigue siendo la
fuente de verdad para evidencia, persistencia, hash y reverificación. La
regresión ahora imita explícitamente la salida real normalizada con `OFFSET 0`.

Verificación posterior:

- Pruebas focalizadas: `60 passed`.
- `pytest -m "not integration" -q`: `1085 passed, 122 deselected`.
- Aceptación determinista con PostgreSQL local:
  `19 passed, 1188 deselected`.
- El primer intento de esa aceptación sin `DATABASE_URL` exportada produjo 19
  errores de setup (`KeyError`) antes de ejecutar las pruebas; al cargar la URL
  local desde `.env` solo para el proceso, pasó completa. No es un fallo de la
  implementación.
- Ruff check/formato y `git diff --check`: limpios.

Estado: `READY_FOR_DIRECTED_PILOT013_RETRY` / `FULL_GATE_BLOCKED`.

## C8B — revalidación real satisfactoria

La única revalidación dirigida posterior, eval
`e57d5421-017e-4f54-972e-3ae7b9e3dc9d` sobre `d16b1e1`, pasó:

- `agent_run_id=3a52133f-b776-4118-8da2-e724d71c963b`;
- estado terminal `completed`, sin código terminal;
- dataset correcto `tmk8-iihq`;
- SoQL con `WHERE codigo = 'PRY00062'`;
- exactamente una fila: nombre `IP Ibagué - Cajamarca` y tipo
  `Iniciativa Privada sin Recursos Públicos`;
- dos hechos `direct_text`, uno por cada campo pedido, persistidos y
  reproducibles;
- integridad textual total: cobertura, reproducibilidad y presentación al
  100%, sin segmentos huérfanos ni operaciones inválidas;
- `fabrication_count=0`, `orphan_figures_count=0`, sin infraestructura;
- latencia 12.654 s y costo estimado USD 0,005642.

La narrativa es verificable aunque estilísticamente genérica (“El valor
observado es…”); no intercambia ni inventa valores y la evidencia/fuente queda
consultable. Conforme a RF-211, es una advertencia de presentación no
bloqueante, no motivo para convertir la respuesta en `no_evidence`.

Estado: `READY_FOR_CANONICAL_SMOKE` / `FULL_GATE_BLOCKED`.
