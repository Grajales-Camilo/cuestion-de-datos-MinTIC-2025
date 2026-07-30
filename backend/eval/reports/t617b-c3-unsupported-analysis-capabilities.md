# T-617B-C3 — Guard determinista de capacidades analíticas no respaldadas

- Rama: `feat/t617-gate-preflight`
- HEAD base: `597ef73e4e018ddba1a9d61faee6dcad97edce26`
- Precede a: T-617B-C2 aprobado dentro de su alcance (`backend/eval/reports/t617b-c2-deterministic-relevance-abstention.md`); modo eval `directed` autorizado por Juan Camilo; validación real dirigida `2b6183b6-0ccc-482e-8efd-16c01c0c092a` (pilot-044 pasó por abstención, pilot-048 falló con dataset de deserción escolar y 200 claims ante una pregunta sobre polarización en redes).
- No se ejecutó Gemini, Socrata ni ninguna evaluación real. No se modificaron specs, contratos, `golden-v1.yaml`, `golden-v2.yaml`, `expected_facts`, métricas ni umbrales. No se creó commit, push ni PR.

## `git status --short` inicial (registrado antes de tocar código)

```
 M backend/app/agent/deterministic_graph.py
 M backend/app/agent/deterministic_runtime.py
 M backend/eval/gate.py
 M backend/eval/run.py
 M backend/tests/test_deterministic_graph.py
 M backend/tests/test_deterministic_runtime.py
 M backend/tests/test_eval_gate.py
?? backend/eval/reports/... (16 reportes preexistentes de T-617B/T-617C, incluida la validación dirigida 2b6183b6-...)
?? backend/uv.lock
?? docs/... (documentos internos preexistentes)
```

Todos los cambios rastreados corresponden a T-617B-C2 (rondas R1–R3), ya aprobado dentro de su alcance; todos los archivos no rastreados se conservaron intactos.

## Revisión R2 — corrección de sobrebloqueo (`CHANGES_REQUIRED — REMOVE "PRINCIPAL CAUSA" FALSE POSITIVE`)

Auditoría independiente reprodujo un falso positivo: `"¿Cuál fue la principal causa de accidentes registrada por la entidad en 2024?"` activaba `_unsupported_question`, pese a ser una pregunta perfectamente descriptiva (identificar la categoría más frecuente de una columna de causa, sin exigir atribución exclusiva). La causa era la alternativa `\bfue\s+la\s+(unica|principal)\s+causa\b`: "principal" no es sinónimo de "única"/"exclusiva" — "principal causa" describe la categoría dominante por frecuencia, compatible con una consulta estructurada normal (`GROUP BY causa ORDER BY count DESC`), mientras que "única causa" afirma que no existe ninguna otra causa posible, una atribución causal fuerte que el catálogo no puede sostener.

**Corrección aplicada**: se eliminó `principal` de esa alternativa, dejando únicamente `\bfue\s+la\s+unica\s+causa\b`. El resto de las cinco alternativas de `exclusive_attribution_phrase` no se tocó — ninguna contenía "principal".

Se añadieron los dos controles exigidos al parametrize de `test_unsupported_capability_guard_does_not_block_descriptive_questions`:
- `"¿Cuál fue la principal causa de accidentes registrada por la entidad?"` → no bloqueada.
- `"¿Qué causa aparece con mayor frecuencia en el registro?"` → no bloqueada.

**Reproducción baseline → cambio**: se reintrodujo temporalmente `principal` en el regex (edición dirigida, sin usar `git stash` para no perder el resto del incremento), se ejecutaron los dos controles nuevos, y `"...principal causa..."` falló exactamente como se reportó (`assert 'abstained' == 'completed'`); el segundo control (`"mayor frecuencia"`) ya pasaba porque no contiene ninguna de las expresiones cubiertas por el regex, confirmando que el sobrebloqueo era específico de la alternativa `principal`. Se restauró la corrección y ambos controles pasan.

Verificado explícitamente que los verdaderos positivos existentes siguen intactos tras el cambio: `"¿Qué política causó por sí sola la reducción de la pobreza en cada barrio de Colombia?"` y `"¿Qué intervención fue la única causa del descenso en la tasa de mortalidad infantil?"` continúan activando el guard (la segunda usa "única", no "principal", así que no se vio afectada por la eliminación).

Suite final tras esta corrección: **1055 passed, 122 deselected** (1053 + 2 pruebas nuevas), Ruff y formato limpios, `git diff --check` exit 0, hashes de golden intactos.

## Causa y alcance

`pilot-048` (validación dirigida `2b6183b6-...`) confirmó con datos reales el límite ya documentado del gate de relevancia de T-617B-C2: la columna `c_digo_departamento` (tilde saneada por Socrata) clasifica léxicamente `primary`, no `auxiliary`, así que al menos un claim del dataset de deserción escolar (`ji8i-4anb`) pasa el filtro de relevancia narrativa aunque el dataset entero responda una pregunta distinta ("polarización de la ciudadanía en redes sociales frente a políticas de educación"). Un parche dirigido a `c_digo_departamento` sería inútil: `departamento` (sin tilde que sanear) también clasifica `primary` y produciría el mismo resultado.

El objetivo de este incremento **no es** parchear esa clasificación léxica ni resolver `pilot-024–027` (que depende del mismo mecanismo de columnas). Es abstenerse **antes de intentar recuperación** cuando la propia pregunta pide una capacidad analítica que ningún dataset del catálogo estructurado puede sostener por diseño: atribución causal fuerte/exclusiva, o análisis de sentimiento/polarización/discurso en redes sociales. Si la pregunta pide esa capacidad, ningún dataset recuperado —sea cual sea su calidad o la clasificación léxica de sus columnas— respondería materialmente la pregunta; intentar recuperación sería trabajo desperdiciado que, además, es precisamente el punto donde T-617B-C2 no puede intervenir (actúa después de tener evidencia, no antes de buscarla).

Se extendió el guard determinista **ya existente** `_unsupported_question` (`backend/app/agent/deterministic_runtime.py:284-301`), que corre en `run_deterministic_agent` **antes** de `dependencies.extract_intent(question)` (línea 337 tras el cambio) — es decir, antes de cualquier llamada LLM, recuperación, candidato, evidencia o claim. Este guard ya cubría predicción exacta, tiempo real, filas personales y consejo médico; el patrón (regex sobre `_fold_text(question)`, sin I/O, puro) se reutilizó sin alterarlo.

## Reglas genéricas incorporadas

Dos funciones nuevas, ambas puras y basadas exclusivamente en el texto normalizado de la pregunta (nunca en `case_id`, `dataset_id` ni listas de pilotos):

### `_requests_strong_causal_attribution(normalized)`

Detecta **capacidad**, no tema: exige o bien (a) un verbo causal explícito (`causó`, `causaron`, `provocó`, `provocaron`, `originó`, `originaron`) combinado con una marca de exclusividad (`por sí sola`/`por sí solo`) en la misma cláusula, o (b) una expresión de atribución única/exclusiva por sí sola (`única causa`, `causa exclusiva`, `responsable exclusivo/único de`, `causa determinante`, `fue la única causa`, `atribuible única/exclusivamente`). La mera aparición suelta de "causa", "efecto" o "relación" **no** activa la regla — verificado explícitamente (prueba 8, control anti-sobrebloqueo).

### `_requests_social_media_sentiment_analysis(normalized)`

Exige la combinación, en la misma cláusula, de un término de análisis de opinión/sentimiento (`polarización`, `polarizada/o`, `sentimiento`, `opinión`, `postura`, `percepción`) **con** un término de medio digital/redes (`redes sociales`, `publicaciones digitales/en redes`, `comentarios digitales/en redes`, `discurso digital`, `debate digital`). Ninguno de los dos grupos por separado activa la regla. "Red vial" y otras redes de infraestructura no contienen ninguno de los términos de medio digital exigidos; "social" fuera de ese contexto (p. ej. "gasto social") tampoco activa nada porque no hay término de sentimiento/opinión emparejado.

Ambas reglas se integran en `_unsupported_question` junto a las cuatro existentes; el guard retorna `True` si cualquiera dispara, sin cambiar el comportamiento de las cuatro reglas previas.

## Matriz de verdaderos positivos y controles anti-sobrebloqueo

| # | Categoría | Pregunta de prueba (genérica, no copia literal de ningún piloto) | Resultado esperado |
|---|---|---|---|
| 1 | Causalidad exclusiva explícita | "¿Qué política causó por sí sola la reducción de la pobreza en cada barrio de Colombia?" | Abstención |
| 2 | Paráfrasis genérica de atribución causal fuerte | "¿Qué intervención fue la única causa del descenso en la tasa de mortalidad infantil?" | Abstención |
| 3 | Polarización en redes sociales | "¿Cuál es la polarización de la ciudadanía en redes sociales frente a las políticas de educación en Antioquia?" | Abstención |
| 4 | Sentimiento en publicaciones/comentarios digitales | "¿Cuál es el sentimiento ciudadano expresado en los comentarios digitales sobre la reforma tributaria?" | Abstención |
| 5 | Descriptiva sobre política pública | "¿Qué política de vivienda aplica el municipio de Pasto?" | No bloqueada |
| 6 | Tasa educativa en Antioquia | "¿Cuál fue la tasa de deserción escolar en Antioquia en 2011?" | No bloqueada |
| 7 | "Red vial" (no es red social) | "¿Cuántos kilómetros de la red vial secundaria están pavimentados en el departamento?" | No bloqueada |
| 8 | Asociación/comparación descriptiva sin atribución causal | "¿Cómo se relaciona la tasa de deserción escolar con el nivel de pobreza municipal?" | No bloqueada |
| 9 | "Social" fuera de redes sociales | "¿Cuál es el gasto social ejecutado por el municipio en 2023?" | No bloqueada |
| 10 | Dobles explosivos | Preguntas 1–4 con dependencias que lanzan `AssertionError` si `extract_intent`/`retrieve`/pasos posteriores se invocan | `extract_intent`/`retrieve` nunca invocados |
| 11 (R2) | "Principal causa" = categoría dominante, no atribución exclusiva | "¿Cuál fue la principal causa de accidentes registrada por la entidad?" | No bloqueada |
| 12 (R2) | Frecuencia descriptiva sobre una columna de causa | "¿Qué causa aparece con mayor frecuencia en el registro?" | No bloqueada |

Nota #3, #4 no son el texto literal de `pilot-048` (que dice "frente a las políticas de educación en Antioquia" combinando ambos); se construyeron de forma independiente combinando los mismos términos de capacidad genéricos, sin copiar la pregunta exacta del caso golden.

## Resultado baseline → cambio

Se guardó el diff de `deterministic_runtime.py` (`git diff` → parche), se revirtió el archivo a `597ef73e...` (`git checkout --`) y se ejecutaron las pruebas nuevas contra ese baseline; luego se reaplicó el parche (`git apply`) y se re-ejecutaron.

### Baseline (sin el guard nuevo)

```
$ uv run pytest tests/test_deterministic_runtime.py -k "unsupported_capability" -q
4 failed, 5 passed, 42 deselected

FAILED test_unsupported_capability_guard_never_invokes_dependencies[...causó por sí sola...]
  AssertionError: extract_intent no debe invocarse tras el guard de T-617B-C3
FAILED test_unsupported_capability_guard_never_invokes_dependencies[...única causa...]
  AssertionError: extract_intent no debe invocarse tras el guard de T-617B-C3
FAILED test_unsupported_capability_guard_never_invokes_dependencies[...polarización...redes sociales...]
  AssertionError: extract_intent no debe invocarse tras el guard de T-617B-C3
FAILED test_unsupported_capability_guard_never_invokes_dependencies[...sentimiento...comentarios digitales...]
  AssertionError: extract_intent no debe invocarse tras el guard de T-617B-C3
```

```
$ uv run pytest tests/test_deterministic_runtime.py -k "abstains_early_for_unverifiable" -q
4 failed, 5 passed, 42 deselected

FAILED test_runtime_abstains_early_for_unverifiable_or_sensitive_requests[...causó por sí sola...]
  AssertionError: assert False -- intent.topic.startswith("¿Cuál es el total") (no llegó a abstenerse, siguió el flujo normal)
FAILED ... (mismo patrón para los otros 3 casos nuevos)
```

Las 5 preguntas preexistentes del parametrize (predicción exacta, tiempo real, filas personales, consejo médico) **ya pasaban** en el baseline — correcto: esas reglas no se tocaron. Los controles anti-sobrebloqueo (5–9) no se probaron contra este baseline reducido porque no dependen del guard nuevo (nunca debieron bloquearse, con o sin el cambio); se verificaron directamente contra el código final (sección siguiente).

### Con el cambio R1 aplicado (parche reaplicado)

```
$ uv run pytest tests/test_deterministic_graph.py tests/test_deterministic_runtime.py -q
70 passed, 1 warning in 5.88s
```

### R2 — Reproducción del sobrebloqueo "principal causa" contra el baseline intermedio

Se reintrodujo temporalmente `principal` en la alternativa `\bfue\s+la\s+(unica|principal)\s+causa\b` (edición dirigida, manteniendo intacto el resto del incremento) y se ejecutaron los dos controles nuevos:

```
$ uv run pytest tests/test_deterministic_runtime.py -k "unsupported_capability_guard_does_not_block_descriptive_questions" -q
1 failed, 6 passed, 46 deselected

FAILED test_unsupported_capability_guard_does_not_block_descriptive_questions[...principal causa...]
  AssertionError: assert 'abstained' == 'completed'
```

`"¿Qué causa aparece con mayor frecuencia en el registro?"` **ya pasaba** contra este baseline — correcto: no contiene ninguna expresión cubierta por el regex, así que nunca dependió de la palabra `principal`. Con la corrección restaurada (`principal` eliminado):

```
$ uv run pytest tests/test_deterministic_graph.py tests/test_deterministic_runtime.py -q
72 passed, 1 warning in 6.51s
```

## Resultados exactos de pruebas

- `tests/test_deterministic_runtime.py::test_runtime_abstains_early_for_unverifiable_or_sensitive_requests` — parametrize extendido de 5 a 9 preguntas (pruebas 1–4 añadidas); asserts sin cambios: `status=="abstained"`, `usage.llm_calls==0`, `retrieval.candidates==()`, `trace==[ABSTAIN]`.
- `tests/test_deterministic_runtime.py::test_unsupported_capability_guard_never_invokes_dependencies` — 4 casos parametrizados (prueba 10), dobles que lanzan `AssertionError` en `extract`/`retrieve`/`profile`/`plan`/`explore`/`execute`/`synthesize`; asserts: `status=="abstained"`, `stop_reason is StopReason.NO_CANDIDATES`, `execution is None`, `synthesis is None`, `trace==[ABSTAIN]`.
- `tests/test_deterministic_runtime.py::test_unsupported_capability_guard_does_not_block_descriptive_questions` — 7 casos parametrizados (pruebas 5–9 + 11–12 de R2); asserts: `status=="completed"`, `usage.llm_calls>0`, `retrieval.candidates != ()`.
- Dos pruebas **preexistentes de T-617B-C2** (`test_runtime_causal_question_without_causal_evidence_abstains_cleanly`, `test_runtime_network_analysis_question_without_network_evidence_abstains_cleanly`) usaban preguntas que, sin buscarlo, coincidían con las nuevas reglas de capacidad ("causó por sí sola", "polarización...redes sociales"). Su `stop_reason` esperado cambió de `CLAIMS_NOT_AVAILABLE` (vía la puerta de relevancia post-recuperación) a interceptado por el guard nuevo — **antes** de llegar siquiera a esa puerta. Se reformularon mínimamente (sin tocar la aserción `status=="abstained"`) para seguir ejercitando específicamente la puerta de relevancia de T-617B-C2 con frases que no activan el guard nuevo ("qué factores explican la reducción de un fenómeno social"; "uso de redes sociales por parte de la ciudadanía frente a una política"), preservando cobertura independiente de ambas capas de defensa. No se debilitó ninguna aserción: el resultado observable (`abstained`) es idéntico; sólo cambió el mecanismo, que ahora es estrictamente anterior y más barato (cero llamadas LLM).

### Suite completa

```
uv run pytest tests/test_deterministic_graph.py tests/test_deterministic_runtime.py -q   → 72 passed
uv run pytest -m "not integration" -q                                                     → 1055 passed, 122 deselected
uv run ruff check app/agent/deterministic_runtime.py tests/test_deterministic_runtime.py  → All checks passed
uv run ruff format --check <mismos 2 archivos>                                            → 2 files already formatted
git diff --check                                                                          → exit 0 (sólo avisos LF/CRLF preexistentes de autocrlf)
```

Antes de T-617B-C3 (sólo T-617B-C2): 1040 passed. Después de R1: 1053 passed. Después de R2 (estado final): **1055 passed** (15 pruebas nuevas: 4 añadidas al parametrize de disparadores + 4 de dobles explosivos + 7 de controles negativos), cero regresiones.

## Diff (`backend/app/agent/deterministic_runtime.py`, sólo la porción de T-617B-C3)

```diff
@@ -297,7 +297,78 @@ def _unsupported_question(question: str) -> bool:
     medical_advice = "tratamiento medico" in normalized and (
         "debe recibir" in normalized or "diagnostico" in normalized
     )
-    return bool(exact_prediction or real_time or personal_rows or medical_advice)
+    strong_causal_attribution = _requests_strong_causal_attribution(normalized)
+    social_media_sentiment_analysis = _requests_social_media_sentiment_analysis(normalized)
+    return bool(
+        exact_prediction
+        or real_time
+        or personal_rows
+        or medical_advice
+        or strong_causal_attribution
+        or social_media_sentiment_analysis
+    )
+
+
+def _requests_strong_causal_attribution(normalized: str) -> bool:
+    ...(ver código fuente completo en el archivo; docstring explica el diseño)...
+    causal_verb_with_exclusivity = re.search(
+        r"\b(causo|causaron|provoco|provocaron|origino|originaron)\b"
+        r"[^.?!]{0,40}\bpor si (sola|solo)\b"
+        r"|\bpor si (sola|solo)\b[^.?!]{0,40}"
+        r"\b(causo|causaron|provoco|provocaron|origino|originaron)\b",
+        normalized,
+    )
+    exclusive_attribution_phrase = re.search(
+        r"\b(unic[oa]|exclusiv[oa])\s+(causa|responsable|factor|explicacion)\b"
+        r"|\bresponsable\s+(unic[oa]|exclusiv[oa])(\s+de)?\b"
+        r"|\bcausa\s+(exclusiva|unica|determinante)\b"
+        r"|\bfue\s+la\s+unica\s+causa\b"
+        r"|\batribu(ible|ye|yo)\s+(unicamente|exclusivamente)\b",
+        normalized,
+    )
+    return bool(causal_verb_with_exclusivity or exclusive_attribution_phrase)
+
+
+def _requests_social_media_sentiment_analysis(normalized: str) -> bool:
+    ...
+    social_media_terms = (
+        r"(redes sociales|publicaciones digitales|publicaciones en redes"
+        r"|comentarios digitales|comentarios en redes|discurso digital"
+        r"|debate digital)"
+    )
+    sentiment_terms = r"(polarizacion|polarizada|polarizado|sentimiento|opinion|postura|percepcion)"
+    return bool(
+        re.search(
+            rf"\b{sentiment_terms}\b[^.?!]{{0,60}}\b{social_media_terms}\b"
+            rf"|\b{social_media_terms}\b[^.?!]{{0,60}}\b{sentiment_terms}\b",
+            normalized,
+        )
+    )
```

Estado final tras R2: la línea `r"|\bfue\s+la\s+unica\s+causa\b"` mostrada arriba ya refleja la corrección — R1 originalmente decía `r"|\bfue\s+la\s+(unica|principal)\s+causa\b"`, y la revisión R2 (descrita al inicio de este informe) eliminó `principal` de esa alternativa. El resto del diff del archivo corresponde íntegramente a T-617B-C2, ya aprobado; no se modificó en este incremento.

## Riesgos y limitaciones

1. **Cobertura léxica, no semántica.** Igual que el gate de relevancia de T-617B-C2, esto es reconocimiento de patrones sobre texto normalizado, no comprensión del lenguaje. Paráfrasis de causalidad/sentimiento que no usen ninguna de las expresiones cubiertas (p. ej. "¿fue X el origen del problema?" sin "único"/"exclusivo"/"por sí sola") no se detectan. Esto es una limitación aceptada, no un defecto: el diseño exige evidencia léxica explícita de exclusividad para evitar sobrebloqueo de asociaciones/correlaciones legítimas.
2. **`pilot-024–027` siguen fuera de alcance — confirmado explícitamente.** Este incremento no toca la clasificación de columnas (`classify_column_relevance`) ni el gate de relevancia de T-617B-C2. El repliegue a un dataset de calidad alta pero temáticamente ajeno cuando sus columnas clasifican `primary` (el caso de `pilot-024–027`, y el de `pilot-048` en la validación dirigida) no tiene relación con preguntas de causalidad exclusiva o sentimiento en redes — sigue siendo el mismo hueco estructural ya documentado en T-617B-C2 (sección "Condición de parada"), que requiere una decisión normativa separada (nuevo metadato de tema por dataset, juicio LLM validable, o aceptación del riesgo residual).
3. **No se resuelve la causa de `pilot-048` en la validación dirigida real.** La pregunta de `pilot-048` combina "polarización...redes sociales" (sí cubierto por esta regla, y hubiera abstenido si la ejecución dirigida se repitiera hoy) — pero eso demuestra que esta regla habría bloqueado ese caso específico por la vía de capacidad, no que resuelve el problema estructural más amplio de repliegue a datasets `primary`-clasificados mal alineados temáticamente (que persiste para preguntas sin marcador de causalidad/redes explícito).
4. **Interacción con T-617B-C2 verificada, no modificada.** Las dos pruebas preexistentes de T-617B-C2 afectadas se reformularon (no se debilitaron) para mantener cobertura independiente de la puerta de relevancia post-recuperación; se confirmó que el resto de la suite de T-617B-C2 (54 pruebas restantes) sigue verde sin cambios.
5. **No se validó contra una corrida real** (prohibido por el encargo). El efecto exacto de esta regla sobre una futura corrida real de `pilot-044`/`pilot-048` (o sobre el resto de la suite) queda sin confirmar hasta que se autorice una nueva validación `directed`.

## Hashes de golden intactos

```
golden-v1.yaml   ab546062767ce2046508489c169a270ae00ceb1515ff67bf92d472404630ff72
golden-v2.yaml   1c78264cccb0da6a10920b6b212438cc40c2b70d2bbd40265f5794fdc754e483
```

Idénticos a los valores congelados de referencia.

## `git status --short` final

```
 M backend/app/agent/deterministic_graph.py
 M backend/app/agent/deterministic_runtime.py
 M backend/eval/gate.py
 M backend/eval/run.py
 M backend/tests/test_deterministic_graph.py
 M backend/tests/test_deterministic_runtime.py
 M backend/tests/test_eval_gate.py
?? backend/eval/reports/... (17 reportes, incluido este)
?? backend/uv.lock
?? docs/... (documentos internos preexistentes)
```

Sólo `backend/app/agent/deterministic_runtime.py` y `backend/tests/test_deterministic_runtime.py` recibieron cambios de T-617B-C3; el resto de archivos rastreados modificados pertenece íntegramente a T-617B-C2 (ya aprobado). Ningún archivo no rastreado fue tocado. **No hay commit, push ni PR.**

## Declaración explícita

No hubo llamadas reales a Gemini, Socrata ni ningún proveedor externo. Toda verificación se realizó con Pytest (dobles locales, funciones puras) y lectura de código; no se ejecutó `eval/run.py` en esta sesión (ni en la ronda R1 ni en la corrección R2).

## Estado tras revisión R2

El sobrebloqueo reportado ("principal causa" tratado como atribución exclusiva) quedó corregido eliminando `principal` de la alternativa `\bfue\s+la\s+(unica|principal)\s+causa\b`, reproducido contra un baseline intermedio (falla sin la corrección, pasa con ella) y cubierto por los dos controles exigidos. Los verdaderos positivos existentes (causalidad exclusiva explícita y su paráfrasis con "única causa") se verificaron intactos. Suite final: 72/72 pruebas focalizadas, 1055 passed/122 deselected, Ruff y formato limpios, `git diff --check` exit 0, hashes de golden intactos, sin commit.

Con esta corrección, T-617B-C3 queda autorizable para la validación `directed` de `pilot-044`/`pilot-048`, sujeta a tu autorización explícita para esa nueva corrida real.

Me detengo aquí, conforme al encargo. Una nueva validación `directed` de `pilot-044`/`pilot-048` para confirmar el efecto real de este guard requiere autorización posterior.
