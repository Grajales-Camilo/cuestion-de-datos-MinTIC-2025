# Prompt: el agente real casi nunca completa una respuesta (0/40 en golden-v1)

Eres una sesión de Claude Code nueva trabajando en el repositorio Cuestión de Datos v2
(D:\Usuario\AppWebs\cuestion-de-datos-MinTIC, rama v2). Otra sesión (auditoría de Fase 6,
2026-07-11/12) verificó el harness de evaluación (T-602: `backend/eval/`) y, una vez que ese
harness quedó correcto y el catálogo local repoblado (antes estaba vacío por una causa ajena),
corrió el conjunto dorado completo (50 casos) y una corrida adicional en vivo para T-402. Los
resultados muestran que **el agente real casi nunca logra completar una respuesta**, incluso
cuando encuentra el dataset correcto. Esto es grave porque toca la funcionalidad central del
producto (RF-201/205, ESC-01), no solo la Fase 6.

No tomes ningún dato de este prompt como definitivo — vuelve a verificar contra el código y la
base de datos real antes de diagnosticar o arreglar nada. Antes de tocar código, lee en el
orden que exige `CLAUDE.md`: `specs/constitution.md`, `specs/001-cuestion-de-datos-v2/spec.md`,
`research.md`, `plan.md`, `contracts/` (especialmente `agent-tools.md` y
`validacion-calidad.md`), `data-model.md`, `pruebas.md`, `tasks.md`.

Entorno: Postgres local Docker en
`postgresql://usuario:clave@localhost:5433/cuestion_de_datos` (exporta `DATABASE_URL`). En
Windows, todo `asyncio.run(...)` contra SQLAlchemy async/psycopg necesita
`loop_factory=asyncio.SelectorEventLoop`. El backend vive en `backend/`; corre pytest, ruff y
los scripts desde ahí (cuidado: el cwd del shell no siempre persiste entre comandos — verifica
con `pwd` antes de lanzar algo largo). El catálogo local ya está poblado (`catalog_datasets`,
`catalog_embeddings` con ~8400 filas, modelo `gemini-embedding-2`) — no hace falta re-ingestar
salvo que lo verifiques y esté vacío otra vez.

## EVIDENCIA — lo que la sesión anterior encontró (verifícalo, no lo asumas)

### 1. Corrida completa del golden set (50 casos, catálogo ya poblado)

`eval_runs.id=3097ac89-564c-4ad0-928d-ee8b627d094f`, seed 601002, `git_commit=0deefae`,
corrida cerrada limpiamente (`finished_at` seteado, sin fallos de infraestructura).

- `success_rate = 18%` (9/50). Casi todo ese 18% son los 9/10 casos **negativos** que se
  abstuvieron correctamente. **0 de los 40 casos positivos llegaron a `status=completed`.**
- `recall_at_10 = 40%` (16/40 positivos) — la búsqueda semántica (T1 `buscar_catalogo`) SÍ
  encuentra el dataset correcto en el top-10 casi la mitad de las veces.
- `fabrication_count = 0`, `orphan_figures_count = 0` — el agente no inventó cifras en ningún
  caso; cuando falla, falla honestamente (`no_evidence` o `failed`), no con alucinaciones.
- De los 40 casos positivos, **solo 13 llegaron a ejecutar `ejecutar_soql`** (verificado
  contando `node='tool:ejecutar_soql'` en `agent_steps` por `agent_run_id`). Los otros 27 se
  quedaron atascados antes de siquiera intentar consultar el dato.
- Desglose de errores encontrados en `agent_steps.error` para los 40 casos positivos de esa
  corrida (repite esta consulta, no confíes en el conteo):
  - `tool:explorar_valores` / `INVALID_INPUT` (3 casos) — el LLM llama la herramienta sin el
    campo requerido `termino_busqueda`.
  - `tool:ejecutar_soql` / `SOQL_FORBIDDEN` (3 casos) — el LLM genera SoQL que la guardia de
    solo-lectura rechaza.
  - `tool:explorar_valores` / `SOCRATA_TIMEOUT` (2 casos).
  - `router` / timeout 504 del proveedor LLM (2 casos).
  - `tool:perfilar_dataset` / `INVALID_INPUT` (1 caso).
  - `router` / **salida estructurada inválida de `RouterOutput`** contra el esquema de
    `claim_specs_by_evidence[].claim_specs[].formula` (3 casos, con 12 a 28 errores de Pydantic
    cada uno). El LLM manda algo como `{"op": "add", "args": [...]}` que no calza con ninguna
    de las variantes del DSL (`ConstFormulaNode`/`ColFormulaNode`/`AggFormulaNode`/
    `OpFormulaNode`) definidas en `app/agent/graph.py`/`app/quality/claims.py`. **Esta es la
    pista más seria**: sugiere que el esquema de la fórmula tal como está expuesto al LLM en el
    prompt del router (`app/agent/prompts/router_v1.md`) no es lo bastante claro o el LLM no
    logra producir el discriminador correcto de forma consistente.
  - `tool:ejecutar_soql` / `EVIDENCE_NOT_ELIGIBLE` (1 caso).

### 2. Corrida en vivo aislada para T-402 (pregunta de vigilancia en salud pública)

Corrida directa contra el grafo real (no vía `eval.run`, sino `create_eval_run` +
`execute_agent_run_async` sobre la pregunta exacta del caso `pilot-003-salud-vigilancia` de
`golden-v1.yaml`, dataset esperado `4hyg-wa9d`). `run_id=fea461c4-ea99-4301-a704-831072824dce`.

Secuencia real (`agent_steps` ordenados por `step_number`):

1. `planner`
2. `router`
3. `tool:buscar_catalogo("eventos de salud pública", k=5)` → **SÍ encontró `4hyg-wa9d`**
   (similitud 0.683, 2° de 5 resultados). La búsqueda semántica funcionó bien.
4. `router`
5. `tool:explorar_valores(dataset_id="4hyg-wa9d", columna="nombre_evento")` → **falló**:
   `INVALID_INPUT`, `"termino_busqueda: Field required"`. El LLM no mandó un campo obligatorio
   de esa herramienta.
6. `router`
7. `synthesizer` → el grafo terminó aquí, `status=no_evidence`, `termination_reason=
   "STEP_BUDGET_EXCEEDED"` con solo 7 pasos usados (de un máximo de 10) — es decir, el grafo
   decidió rendirse temprano, no que se le acabaran los 10 pasos exactos.

**El agente nunca llegó a `ejecutar_soql`, así que `quality_validator` y `claim_builder`
tampoco corrieron.** Esto contradice directamente una nota de cierre que apareció en
`tasks.md` para T-402 citando un `run_id=3606ec48-eb51-4f8d-b95c-e9ef01424878` con resultado
`completed` — la sesión anterior verificó que ese `run_id` **no existe** en `agent_runs` ni en
`technical_metrics` (comparando el hash SHA-256 esperado); la nota se revirtió antes de
comitear. No repitas ese error: si vas a documentar un cierre, cita un `run_id` real y
verificable, no una narrativa plausible.

## QUÉ DEBES INVESTIGAR

1. **Prioridad más alta — el error de esquema de `formula` en `RouterOutput`.** Lee
   `app/agent/prompts/router_v1.md` y compáralo contra el esquema real de `FormulaNode` en
   `app/agent/graph.py`/`app/quality/claims.py` (busca `ConstFormulaNode`, `ColFormulaNode`,
   `AggFormulaNode`, `OpFormulaNode`). ¿El prompt le explica al LLM el formato discriminado
   correcto? ¿Hay ejemplos en el prompt? ¿El LLM tiene alguna vía de reintento cuando la
   validación de Pydantic falla, o el error mata el paso sin más? Reproduce el fallo con un
   caso real (p. ej. corre de nuevo alguno de los casos positivos de `golden-v1.yaml` que
   fallaron con este error — puedes identificarlos repitiendo la consulta de `agent_steps` de
   la sección anterior).
2. **`explorar_valores` con input inválido y sin recuperación.** ¿Por qué el LLM omite
   `termino_busqueda`? ¿El prompt del router documenta bien el contrato de esa herramienta
   (`contracts/agent-tools.md`)? Y más importante: cuando una herramienta falla con
   `INVALID_INPUT`, ¿el grafo reintenta con el LLM corrigiendo el input, o simplemente sigue
   adelante y eventualmente se rinde? Revisa la lógica de reintento en `app/agent/graph.py`
   (busca cómo se maneja `_CORRECTABLE_SOQL_ERROR_CODES` para `ejecutar_soql` — ¿existe un
   mecanismo equivalente para las demás herramientas, o solo T5 tiene reintento?).
3. **`SOQL_FORBIDDEN` en 3/40 casos.** ¿El LLM está generando SoQL de escritura, o la guardia
   de solo-lectura está siendo demasiado estricta con SoQL de lectura legítimo? Revisa
   `app/tools/soql_parser.py` y compara contra los SoQL reales que generó el LLM en esos casos
   (`agent_steps.tool_input` para `node='tool:ejecutar_soql'`).
4. **Por qué solo 13/40 llegan a `ejecutar_soql`.** Cuantifica en qué paso se atasca cada uno
   de los 27 restantes (no asumas que es siempre el mismo patrón — la sesión anterior solo
   miró un subconjunto). Construye una tabla completa de "en qué nodo terminó cada uno de
   los 40 casos positivos" antes de proponer un fix.
5. **`termination_reason="STEP_BUDGET_EXCEEDED"` con `steps_used` muy por debajo de
   `AGENT_MAX_STEPS`.** En el caso de T-402 aislado, terminó en el paso 7 de un máximo de 10,
   etiquetado igual que si hubiera agotado el presupuesto real. Verifica si esa etiqueta es
   correcta o si el grafo se está rindiendo antes de tiempo por alguna otra condición (p. ej.
   un límite de reintentos por nodo que no es lo mismo que el presupuesto total de pasos) y esa
   etiqueta está mal puesta.
6. **Timeouts del proveedor LLM (504) y de Socrata.** ¿Son transitorios (red, cuota) o
   revelan un patrón (p. ej. prompts demasiado largos que tardan más de lo esperado)? Si son
   transitorios, ¿vale la pena una corrida de verificación en otro momento antes de concluir
   nada sobre esos casos específicos?

## QUÉ NO HACER

- No toques `backend/eval/` (loader.py, metrics.py, persistence.py, run.py) — ya fue auditado y
  corregido hoy (commits `0deefae`, `ac326d7`), y las 4 correcciones (validación de
  `expected_facts`, `recall_at_10` real, `orphan_figures_count` real, manejo de fallos por
  caso) ya están verificadas con una corrida real completa. Si sospechas que el harness está
  mal midiendo algo, repórtalo, no lo cambies sin autorización.
- No marques ninguna tarea de `tasks.md` como completada sin un `run_id` real y verificado
  (consulta `agent_runs`/`eval_runs` directamente en Postgres, no confíes en una narrativa).
- No corras los 50 casos completos de nuevo sin necesidad — cada corrida cuesta cuota real de
  Gemini/Socrata. Usa casos individuales o un subconjunto pequeño (`--limit`) para reproducir y
  verificar hipótesis puntuales.
- Antes de mutar cualquier dato en Postgres, revisa `pg_stat_activity` por si hay otra sesión
  activa trabajando en paralelo sobre la misma base local.

## FORMATO DEL REPORTE

Para cada hallazgo: archivo:línea del código real involucrado, qué verificaste y con qué
comando/consulta, y una hipótesis concreta de causa raíz (no solo "el LLM se equivoca" — a qué
parte del prompt, esquema o lógica de reintento se le puede atribuir). Cierra con una
priorización clara de qué arreglar primero para mover la aguja de `success_rate` desde 18%
hacia el umbral de release (≥80%, pruebas.md §4.2), y si crees que ese umbral es alcanzable con
ajustes de prompt/reintento o si requiere un cambio de diseño más grande.
