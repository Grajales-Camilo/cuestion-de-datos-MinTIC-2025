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
4. el SoQL ejecutado debe coincidir con el SoQL canónico renderizado;
5. solo se consideran dimensiones `TEXT` seleccionadas;
6. el nombre real de cada columna debe solaparse léxicamente con la intención
   vigente;
7. se excluyen aliases que ya produjeron un claim cuantitativo.

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
