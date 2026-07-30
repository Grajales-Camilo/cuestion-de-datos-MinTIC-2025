# Línea base de desarrollo — migración al núcleo determinista (T-610)

**Implementa:** RF-603, Constitución Art. II.3/IV · **Gobierna:** `research.md` §25, `plan.md` §13, `pruebas.md` §4.4, `tasks.md` T-610…T-617

**Fecha y zona horaria:** 2026-07-16, America/Bogota (UTC-5).
**Propósito:** congelar el estado reproducible del repositorio inmediatamente antes de T-611, sin cambiar comportamiento. Este documento distingue explícitamente, en cada sección, "el runner terminó" (el proceso concluyó sin excepción y persistió un estado terminal) de "el agente resolvió" (la respuesta coincidió con lo esperado).

---

## 1. Rama y commit

- **Rama:** `feat/deterministic-agent-core`
- **Commit inicial (HEAD al empezar esta sesión):** `be37dc33f10f52b73894cc2e985e0ca913ed50f4`
  (`fix(agent): reject irreparable privacy plans`, 2026-07-13 03:48:45 -0500)
- Verificado con `git rev-parse HEAD` al inicio de la sesión. Ningún commit propio se creó antes de este reporte.

## 2. Estado del worktree

Al iniciar la sesión, `git status --short` mostraba:

```
 M CLAUDE.md
 M specs/001-cuestion-de-datos-v2/plan.md
 M specs/001-cuestion-de-datos-v2/pruebas.md
 M specs/001-cuestion-de-datos-v2/research.md
 M specs/001-cuestion-de-datos-v2/tasks.md
?? docs/capitulos-css-politicas-publicas.md
?? docs/cuestion-de-datos-v2-langgraph-informe.docx
?? docs/figura-langgraph-grafo.png
?? docs/figura-langgraph-grafo.svg
?? docs/figura-langgraph-secuencia.png
?? docs/figura-langgraph-secuencia.svg
?? docs/indice-semantico-catalogo-v2.md
?? docs/indice-semantico-catalogo-v3-con-figura.docx
?? docs/indice-semantico-catalogo-v3.docx
?? docs/indice_semantico_catalogo.pptx
?? docs/informe-langgraph-cuestion-de-datos-v2.md
?? docs/prompt-claude-code-nucleo-determinista-t610-t612.md
?? docs/prompt-t303.md
?? docs/prompt-t304.md
?? docs/prompt-t306.md
```

**Todos estos cambios son preexistentes a esta sesión** (documentación y specs, ninguno bajo `backend/`). No se modificó ni se descartó ninguno de ellos al preparar esta línea base. Los únicos archivos que esta sesión crea o modifica bajo `backend/` se declaran en el informe de cierre de T-610/T-611/T-612 (fuera de este documento).

## 3. Runtime y default observados

- `backend/app/config.py` declara literalmente:
  ```python
  AgentRuntime = Literal["deterministic", "legacy"]
  agent_runtime: AgentRuntime = Field(default="deterministic", alias="AGENT_RUNTIME")
  ```
  **Confirmado por lectura directa del código**, no por inferencia.
- `backend/.env` local **no define `AGENT_RUNTIME`** (confirmado leyendo el archivo), por lo que el runtime efectivo en este checkout es `deterministic` por el default de `config.py`.
- Esto reproduce exactamente la **desviación conocida** documentada en `research.md` §25 y `tasks.md` ("Estado para el siguiente agente"): la política aprobada exige que los entornos de usuario/producción fijen `AGENT_RUNTIME=legacy` explícitamente mientras la puerta normativa esté abierta, pero el default de código ya es `deterministic`. Esta enmienda documental no autoriza corregir el default en este incremento (solo pruebas); se deja registrado, no corregido.
- `execute_agent_run_async` (`backend/app/agent/runner.py:505-512`) es el despachador real: enruta a `execute_legacy_agent_run_async` si `settings.agent_runtime == "legacy"`, o a `execute_deterministic_agent_run_async` en cualquier otro caso. No existe fallback automático entre runtimes dentro de una corrida (confirmado leyendo el cuerpo completo de ambas funciones).

## 4. Versión de Python y herramientas

- **Python del entorno virtual (`backend/.venv`):** 3.13.14 — dentro del rango `>=3.12,<3.14` declarado en `pyproject.toml` (`requires-python`).
- **Gestor de entorno:** `uv 0.11.24` (`uv run ...`).
- **pytest:** ejecutado vía `uv run pytest`, configuración en `[tool.pytest.ini_options]` de `backend/pyproject.toml`:
  ```toml
  markers = [
      "integration: pruebas que requieren red, PostgreSQL real o servicios externos",
  ]
  asyncio_mode = "auto"
  testpaths = ["tests"]
  ```
  **Solo existe el marcador `integration` hoy.** Ni `legacy_agent_acceptance` ni `deterministic_agent_acceptance` están registrados todavía — T-612 los añade.
- **ruff:** ejecutado vía `uv run ruff check .`.
- **Base de datos:** contenedor Docker `pgvector/pgvector:0.8.0-pg16` (`cuestion-de-datos-db`), healthy, puerto publicado `5433→5432`, siete días de antigüedad al momento de esta verificación (no levantado por esta sesión).

## 5. Conteo de pruebas recolectadas

Comando: `uv run pytest --collect-only -q` (desde `backend/`).

| Subconjunto | Comando | Resultado |
|---|---|---|
| Total | `pytest --collect-only -q` | **703 pruebas recolectadas** |
| No integración | `pytest --collect-only -q -m "not integration"` | **628/703** (75 deselected) |
| Integración | `pytest --collect-only -q -m "integration"` | **75/703** (628 deselected) |

Coincide exactamente con la evidencia histórica citada en `tasks.md` T-610 ("628 pruebas no integración verdes"): el número no cambió respecto a la última vez que se registró, y se reconfirma aquí con una recolección real, no copiada.

## 6. Resultado no integración

Comando: `uv run pytest -m "not integration" -q` (desde `backend/`).

```
628 passed, 75 deselected, 5 warnings in 15.69s
```

**0 fallos.** Las advertencias son `LangChainPendingDeprecationWarning` (serializador de `langgraph`) y `StarletteDeprecationWarning` (uso de `httpx` con `TestClient` y el código HTTP `422` renombrado) — no relacionadas con el núcleo determinista, preexistentes.

**Distinción runner/agente:** esta suite es enteramente determinista y mockeada (sin LLM real, sin Socrata real). "El runner terminó" y "la aserción pasó" coinciden aquí porque cada prueba fija su propio resultado esperado; no hay ambigüedad sobre si "el agente resolvió" un caso real.

## 7. Subconjunto determinista dirigido

Comando (equivalente al de la secuencia normativa del prompt de sesión):

```powershell
uv run pytest -q `
  tests/test_query_plan.py `
  tests/test_plan_validator.py `
  tests/test_soql_renderer.py `
  tests/test_llm_contracts.py `
  tests/test_multiquery_retrieval.py `
  tests/test_deterministic_graph.py `
  tests/test_deterministic_dependencies.py `
  tests/test_deterministic_pipeline.py `
  tests/test_deterministic_runtime.py `
  tests/test_runner_runtime_selection.py
```

```
123 passed, 1 warning in 5.09s
```

**0 fallos.** Coincide con la evidencia histórica citada ("subconjunto determinista verde"): reconfirmado con ejecución real.

## 8. Lint

Comando: `uv run ruff check .` (desde `backend/`).

```
All checks passed!
```

## 9. Integración — disponible, verificada

- Docker Desktop y el contenedor `cuestion-de-datos-db` (`pgvector/pgvector:0.8.0-pg16`) estaban ya arriba y `healthy` (`docker compose ps`), no fue necesario levantarlos.
- Las pruebas de integración de este repositorio (p. ej. `tests/integration/test_deterministic_pipeline_persistence.py`, `tests/integration/test_agent_redesign_acceptance.py`) leen `os.environ["DATABASE_URL"]` **directamente**, no `Settings()`/`backend/.env` — PowerShell/Bash no cargan `.env` automáticamente (documentado en `quickstart.md`). Fue necesario exportar `DATABASE_URL=postgresql://usuario:clave@localhost:5433/cuestion_de_datos` en la sesión de shell antes de ejecutar cualquier prueba de integración.
- Verificación dirigida: `uv run pytest -q tests/integration/test_deterministic_pipeline_persistence.py` con `DATABASE_URL` exportado →
  ```
  1 passed, 1 warning in 1.01s
  ```
- **Conclusión:** integración **disponible** en esta máquina/sesión. No se ejecutó la suite completa de integración (`pytest -m integration`) en este incremento porque T-610 solo exige congelar la línea base sin cambiar comportamiento; ejecutarla por completo no aporta evidencia adicional para esta puerta y consumiría tiempo no solicitado. Se deja como parte de la secuencia de pruebas de T-611/T-612 en el informe de cierre correspondiente.

## 10. Última corrida completa de 50 casos (golden-v1)

- **`eval_run_id`:** `2f2a4e7f-6aab-4576-8277-1f3088a1d692`
- **Reporte:** `backend/eval/reports/2f2a4e7f-6aab-4576-8277-1f3088a1d692.md` (también citado como evidencia en `backend/eval/golden/GOLDEN_V2_PROPOSAL.md`)
- **Suite:** `golden-v1` (50 casos: 40 positivos, 10 negativos) · **Modelo:** `google/gemini-2.5-flash`
- **Iniciada:** 2026-07-13 08:23:54 UTC · **Terminada:** 2026-07-13 08:43:10 UTC (~19 min)
- **`success_rate`:** 0.5 (**25/50**, 50%)
- **`config_snapshot` persistido** (consultado directamente en `eval_runs` vía Postgres real):
  ```json
  {
    "agent_max_steps": 14,
    "embedding_model": "gemini-embedding-2",
    "run_max_duration_s": 600,
    "placeholder_min_ratio": 0.3
  }
  ```
  **Limitación de diagnóstico confirmada aquí, no asumida:** `config_snapshot` **no incluye `agent_runtime`**. `eval/run.py` invoca `execute_agent_run_async(settings, agent_run_id)` (el despachador), por lo que el runtime efectivo de esa corrida dependía de `Settings().agent_runtime` en el momento de ejecutarla. Dado que el default de código es `deterministic` y no hay evidencia de que `.env` fijara `AGENT_RUNTIME=legacy` en esa fecha (`.env` no está versionado y no puede reconstruirse desde git), **se infiere, sin poder probarlo con evidencia persistida directa, que esta corrida usó el runtime `deterministic`** — consistente con la lectura de `GOLDEN_V2_PROPOSAL.md` ("demuestra la mejora del runtime" frente a "la línea anterior de 13/50"). Esta ambigüedad es exactamente el tipo de vacío que la matriz diagnóstica de T-613 (`pruebas.md` §4.4) debe cerrar registrando el runtime por corrida; no se resuelve en este incremento.

### Distribución de fallos (tabulada desde el reporte real, no estimada)

| Resultado | Casos | Motivo |
|---|---:|---|
| Aprobó | 25 | — |
| No aprobó | 15 | El dataset esperado apareció pero `expected_facts` no coincide (tolerancia excedida). |
| No aprobó | 10 | No completó con un dataset esperado como evidencia. |
| **Total** | **50** | |

**Distinción explícita "el runner terminó" vs. "el agente resolvió" para esta corrida:** las 50 preguntas completaron su ciclo (el runner llegó a un estado terminal persistido por caso — no se registran corridas `running` huérfanas ni `failed` por excepción no controlada en este reporte). De esas 50, **25 "resolvieron"** en el sentido estricto del harness (`status=completed` + dataset esperado + hecho verificado dentro de tolerancia). Los 15 casos "dataset apareció pero no coincide" son corridas donde **el runner sí terminó y el agente sí llegó al dataset correcto**, pero el valor/fila seleccionado no coincidió con el hecho congelado del golden — no es un fallo de ejecución, es un desacuerdo sobre el hecho resultante. Los 10 casos "no completó" son corridas donde el runner terminó (sin excepción) pero el agente nunca llegó a usar el dataset esperado como evidencia (abstención honesta o dataset distinto).

## 11. Limitaciones ambientales

- No se ejecutó ninguna corrida nueva contra Gemini/Socrata reales en este incremento (T-610 es exclusivamente de congelamiento documental; no se autorizó ni se justificó gastar cuota para esta puerta).
- No se ejecutó `pytest -m integration` completo (ver §9) — limitación de alcance, no de disponibilidad: el servicio está arriba y una prueba dirigida contra él fue exitosa.
- El repositorio no tiene un `tests/integration/conftest.py` compartido; cada archivo de integración define su propia fixture `engine` local leyendo `DATABASE_URL` de variables de entorno del proceso, no de `backend/.env` — limitación operativa a tener en cuenta en T-611 (debe exportarse `DATABASE_URL` antes de correr esa suite, igual que aquí).

## 12. Puerta T-610

- `pytest --collect-only` reproducible: ✅ (703 total, 628 no integración, 75 integración — coincide con la evidencia histórica).
- No integración y subconjunto determinista reproducibles: ✅ (628 passed / 123 passed, 0 fallos en ambos).
- Cero cambios de comportamiento: ✅ (este documento es la única adición de esta puerta; no se tocó código de `backend/app/`).
- El reporte distingue "el runner terminó" de "el agente resolvió": ✅ (§6, §7, §10).

**T-610: completa.**
