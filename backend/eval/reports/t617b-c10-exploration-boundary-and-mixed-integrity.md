# T-617B-C10 — Frontera T4, terminales Socrata e integridad mixta

## Estado

`READY_FOR_DIRECTED_VALIDATION` / `SMOKE_AND_FULL_BLOCKED`

- Baseline: `bfbde28b25fd1f2762a755088547a22b07dca504`.
- Requisitos: RF-205, RF-211, RF-602 y RNF-003.
- Disparador: validación dirigida
  `54f9e4df-eb31-4f89-9999-7a2eae311aa9`.
- Sin cambios en golden, `expected_facts`, presupuestos, umbrales,
  cardinalidades, contratos, prompts ni migraciones.

## Hallazgos confirmados

1. La exploración T4 usaba como máximo tres términos en este orden: frase
   original, frase sin tildes y tokens de esa segunda forma. El corte impedía
   probar tokens materiales originales:
   - `"Auditoría Regular"` nunca probaba `"Regular"`;
   - `"Alcalá (Valle)"` nunca probaba `"Alcalá"`.
   Los datasets esperados de `pilot-012` y `pilot-021` estaban en primer
   lugar; el falso descarte ocurrió dentro de la exploración de sus valores.
2. Un `SOCRATA_TIMEOUT`/`SOCRATA_ERROR` definitivo de `explorar_valores`
   se convertía en `ValueError`. El supervisor rechazaba el candidato y podía
   terminar como `CANDIDATE_BUDGET_EXCEEDED`, atribuyendo al agente una caída
   real de infraestructura. Esto ocurrió en el dataset esperado
   `s54a-sgyg` de `pilot-038`.
3. La cifra huérfana de la corrida dirigida era `2026`, incluida en el
   `display_value` de un hecho textual persistido y verificable:
   `"Fuente: Función Pública, SIGEP II Marzo 2026"`. El arnés cuantitativo
   solo aceptaba `claims[].display_value`; ignoraba
   `textual_facts[].display_value` y producía un falso positivo.

## Corrección implementada

### Exploración acotada

`_exploration_terms` conserva el máximo existente y prioriza:

1. frase original;
2. tokens Unicode originales de cuatro o más caracteres;
3. frase y tokens sin diacríticos como fallback.

La lista se deduplica de forma estable y se trunca al saldo recibido. No
incrementa llamadas ni contiene `case_id`, `dataset_id`, preguntas, valores
esperados o vocabulario específico de un dataset.

### Frontera de infraestructura

`DeterministicToolInfrastructureError` solo admite los códigos contractuales
`SOCRATA_TIMEOUT` y `SOCRATA_ERROR`. La dependencia real conserva el código;
el runtime no lo captura como rechazo semántico; el runner persiste el mismo
código en el paso T4 y escribe exactamente un terminal `failed`, reintentable,
sin `final_answer`, evidencia ni claims.

Otros errores de exploración siguen siendo `ValueError` y conservan el flujo
de rechazo de candidato. No se amplió la definición de infraestructura.

### Integridad cuantitativa y textual

`eval.metrics._collect_orphan_figures` reconoce como respaldo tanto
`claims[].display_value` como `textual_facts[].display_value`, globalmente y
por `evidence_id`. Una cifra ausente de ambas colecciones continúa siendo
huérfana y bloqueante. No se usan `expected_facts` ni texto libre como fuente
de verdad.

## Prueba fallo → pasa

Worktree temporal sobre `bfbde28`, con solo las pruebas nuevas:

- integridad mixta: `1 failed, 1 passed`; el baseline marcó `2026` como
  huérfano y mantuvo huérfano el control `2027`;
- dependencias T4: error de colección porque `_exploration_terms` no existía;
- aceptación terminal: error de colección porque
  `DeterministicToolInfrastructureError` no existía.

El worktree temporal se eliminó. Con la implementación, las mismas áreas
quedaron verdes.

## Verificación

- Focalizadas `test_deterministic_dependencies.py` + `test_eval_gate.py`:
  `94 passed`.
- Regresión PostgreSQL del terminal Socrata: `1 passed`.
- Suite `-m "not integration"`:
  `1097 passed, 124 deselected`.
- Aceptación determinista PostgreSQL:
  `21 passed, 1200 deselected`.
- Integraciones compartidas:
  `94 passed, 2 skipped, 1125 deselected`.
- Aceptación legacy:
  `7 passed, 1214 deselected`.
- `ruff check .`: limpio con Ruff `0.15.20`.
- Ruff format sobre los siete archivos del incremento: limpio.
- `git diff --check`: limpio; solo advertencias locales LF/CRLF.
- Hashes:
  - golden-v1:
    `ab546062767ce2046508489c169a270ae00ceb1515ff67bf92d472404630ff72`;
  - golden-v2:
    `1c78264cccb0da6a10920b6b212438cc40c2b70d2bbd40265f5794fdc754e483`.

Las pruebas no llamaron Gemini ni Socrata. PostgreSQL local se usó únicamente
para verificar persistencia y unicidad terminal.

## Siguiente puerta

Ejecutar una sola evaluación real `directed` conjunta de:

- `pilot-012-control-fiscal`;
- `pilot-021-sensibilizacion-valle`;
- `pilot-038-precipitacion`.

La corrida debe usar `golden-v2`, runtime determinista, hechos textuales
habilitados y el commit limpio de C10. Si `pilot-038` vuelve a sufrir un fallo
Socrata, debe quedar correctamente tipado como infraestructura y se detiene.
Si algún caso falla semánticamente, se diagnostica sin alterar golden,
presupuestos ni umbrales. Solo una validación útil, verificable y sin bloqueos
reales autoriza repetir el smoke canónico; `full` continúa bloqueado.
