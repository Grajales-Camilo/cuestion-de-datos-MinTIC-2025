Tu misión es dejar el sistema realmente listo para integrar en v2 y avanzar al despliegue del backend y frontend.

No buscamos que cada consulta sea técnicamente perfecta ni que cada piloto coincida literalmente con un expected_fact histórico. Buscamos respuestas:

- útiles para la pregunta;
- respaldadas por datos y fuentes consultables;
- suficientemente correctas;
- sin cifras inventadas;
- transparentes sobre ambigüedades, limitaciones o cobertura parcial.

BLOQUEOS REALES

- cifras fabricadas;
- fuente, dataset o entidad incorrectos;
- contradicciones materiales;
- pérdida o alteración sustantiva de valores;
- ausencia de evidencia;
- asociación incorrecta entre cifra y etiqueta;
- privacidad;
- fallos sistemáticos;
- integridad o reproducibilidad rota.

ADVERTENCIAS NO BLOQUEANTES

- consulta mejorable;
- resultado incompleto pero correcto;
- selección temporal no óptima;
- presentación poco elegante;
- existencia de otra consulta potencialmente superior;
- expected_fact histórico desalineado con una respuesta útil y respaldada;
- ambigüedad explicada claramente al usuario.

No conviertas advertencias no bloqueantes en no_evidence. Tampoco relajes un bloqueo real para mejorar métricas.

ESTADO DEL REPOSITORIO

Directorio:

D:\Usuario\AppWebs\cuestion-de-datos-MinTIC

Rama esperada:

feat/t617-gate-preflight

HEAD esperado:

4fa8d23b165641fedea5cc05771e8ab5b3744535

Últimos commits relevantes:

- 4fa8d23 chore(backend): add reproducible dependency lock
- 1e4bbb5 docs(eval): certify identifier validation
- 715bafd fix(agent): scope requested identifiers
- e8c31af fix(agent): preserve identifiers as exact text
- 94c7795 fix(agent): scope entity constraint to grounded values
- 4bd70cd fix(eval): trust only reproducible structural labels
- ef9cde0 fix(agent): preserve single-row group labels
- 95ecb5d fix(eval): require textual capability for formal gates
- e54ef20 fix(agent): resolve direct quantities and Socrata terminals

backend/uv.lock está rastreado y `uv lock --check` debe pasar.

Hashes congelados:

golden-v1:
ab546062767ce2046508489c169a270ae00ceb1515ff67bf92d472404630ff72

golden-v2:
1c78264cccb0da6a10920b6b212438cc40c2b70d2bbd40265f5794fdc754e483

Existen informes y archivos de docs no rastreados. Presérvalos exactamente. No los edites, borres, muevas, agregues a Git ni incluyas en commits.

REGLAS DE TRABAJO: 

1. Lee AGENTS.md y la documentación normativa en el orden indicado allí antes de modificar código.
2. Usa codebase-memory-mcp primero para descubrir código y relaciones.
3. El worktree real prevalece sobre el índice MCP.
4. Trabaja con PowerShell 7 y Windows 11.
5. PostgreSQL local está normalmente en localhost:5433.
6. Nunca imprimas secretos, DATABASE_URL ni claves de proveedores.
7. No cambies:
   - golden-v1;
   - golden-v2;
   - expected_facts;
   - preguntas;
   - umbrales;
   - cardinalidades;
   - presupuestos;
   - contratos.
8. No agregues reglas por case_id, dataset_id, pregunta o cifra literal.
9. No hagas push, PR, merge ni despliegue.
10. No hagas amend de commits existentes.
11. Haz commits locales pequeños, solo de código/configuración/pruebas fundamentales.
12. No comitees informes ni documentos en este encargo.
13. No ejecutes automáticamente dos veces una misma corrida real.
14. Usa EVAL_MODE=true solo en el proceso de evaluación y retírala en finally.
15. Verifica al final que no queden agent_runs en running.

EVIDENCIA ACTUAL

Último full de golden-v1:

UUID:
1b405332-aa8c-4870-a35c-a62875ecd599

Commit de esa corrida:
ef9cde0

Resultados:

- 50 casos exactos;
- positivos: 15/40;
- negativos: 10/10;
- recall@10: 100%;
- Socrata: 36/36 llamadas observables;
- fabricación: 0;
- costo promedio dentro del umbral;
- tres fallos de infraestructura;
- nueve budget_exceeded;
- cuatro evidence_not_eligible;
- ocho expected_fact_not_found;
- un structured_output_invalid;
- latencias p95 sobre los umbrales.

Los dos orphan_figures reportados originalmente ya fueron demostrados como falsos positivos del arnés: eran 5 y 16 dentro de la etiqueta estructural tasa_matriculacion_5_16.

Después de C10D:

- 2.530/2.530 claims reproducibles;
- cobertura 100%;
- cifras huérfanas reales: 0.

No reabras ese defecto.

El smoke antiguo C5 de 0/8 y Socrata 0/0 también quedó superado. C6 corrigió las fronteras de presupuesto y la observabilidad T5.

CORRECCIONES YA VALIDADAS

C11 corrigió rechazos incorrectos de entidades territoriales y proyectos.

C11A/C11B corrigieron identificadores tratados como cantidades:

- 05 permanece 05;
- 05001 permanece 05001;
- 153.42 y 153.427 permanecen exactos;
- no se muestran identificadores ajenos a la intención;
- duplicados exactos por columna se eliminan.

Validación real final:

UUID:
17e8f034-f05e-4b10-a00f-05fd9e5595fb

Resultados:

- pilot-016:
  Codigo postal: 153.42. Además, Zona postal: 1.534. Además, Codigo postal: 153.427.
- pilot-020:
  Cod dpto: 05. Además, Cod mpio: 05001.
- integridad textual: 100%;
- fabricación: 0;
- cifras huérfanas: 0;
- infraestructura: 0.

pilot-016 puede seguir fallando mecánicamente porque su expected_fact histórico no responde a la pregunta postal. No lo corrijas ni lo conviertas en un defecto del runtime.

RUTA CRÍTICA

Tu trabajo debe avanzar directamente por estas fases:

1. Corregir el defecto material de precisión conocido.
2. Validarlo con una corrida dirigida.
3. Ejecutar el smoke canónico.
4. Ejecutar golden-v1.
5. Auditar solo los bloqueos reales encontrados.
6. Si no hay bloqueos reales pendientes, ejecutar golden-v2.
7. Entregar READY_FOR_V2_INTEGRATION_AND_DEPLOYMENT_PREP.

No hagas una auditoría exhaustiva de todos los pilotos antes de correr los golden. Investiga casos individuales únicamente cuando revelen un bloqueo real, un patrón sistémico o un defecto del evaluador.

FASE 1 — PREFLIGHT

Verifica:

- rama y HEAD exactos;
- ningún cambio rastreado;
- untracked preservados;
- `uv lock --check`;
- PostgreSQL accesible;
- cero agent_runs running;
- hashes golden;
- runtime deterministic;
- pruebas recientes disponibles.

Si HEAD o hashes no coinciden, detente.

FASE 2 — CORREGIR LA PÉRDIDA DE PRECISIÓN DE CLAIMS DIRECTOS

Defecto real:

Pregunta de pilot-034:

¿Qué capacidad instalada se reporta para el proyecto eólico Jepirachi?

Evidencia real:

- dataset: vy9n-w6hc;
- proyecto: JEPIRACHI;
- raw_value: 18.42;
- rounding: 0;
- display_value: 18;
- narrativa: Capacidad: 18.

La fuente es correcta, pero 18 contradice materialmente 18.42.

Hipótesis causal:

`app/quality/claims.py::_build_one_claim` usa rounding=0 cuando `ClaimSpec.rounding` es None. El pipeline determinista produce claims directos sin una regla explícita y pierde la escala decimal observada.

Implementa una solución genérica y mínima, solo después de verificar la causa.

Comportamiento esperado:

- claim directo con valor fuente 18.42 y rounding=None:
  - raw_value = 18.42;
  - rounding inferido = 2;
  - display_value es-CO = 18,42.
- claim directo entero:
  - rounding = 0.
- claim con rounding explícito:
  - conserva exactamente el override.
- claim derivado sin rounding:
  - conserva el comportamiento contractual vigente; no infieras silenciosamente una nueva precisión.
- identificadores/códigos:
  - siguen excluidos del camino cuantitativo por C11A/C11B.
- source_hash:
  - incluye el rounding efectivo;
  - claims históricos continúan reverificándose con su rounding persistido;
  - no invalides evidencia histórica.
- no infieras precisión desde case_id, dataset o nombre de una cifra concreta.

Pruebas obligatorias:

1. Directo 18.42 sin rounding explícito → 18,42.
2. Directo entero sin rounding explícito → entero.
3. Directo 18.42 con rounding=0 → 18.
4. Directo con ceros decimales fuente, por ejemplo 18.4200, conserva una política determinista y documentada.
5. Claim derivado no cambia.
6. Source hash cambia cuando cambia el rounding efectivo.
7. Identificadores continúan sin convertirse en claims cuantitativos.
8. Reverificación histórica continúa verde.

Ejecuta:

- pruebas focalizadas de claims;
- pipeline determinista;
- persistencia/reverificación;
- síntesis;
- `pytest -m "not integration" -q`;
- deterministic_agent_acceptance con PostgreSQL real;
- integración relacionada;
- `ruff check .`;
- `ruff format --check` en archivos modificados;
- `git diff --check`;
- hashes golden.

Demuestra fallo contra el baseline anterior y éxito después del cambio, usando un worktree temporal si es viable.

Si todo pasa, crea un commit local nuevo. No incluyas informes, tasks.md ni otros documentos.

FASE 3 — SMOKE CANÓNICO

Solo si pilot-034 queda materialmente correcto.

Casos exactos:

- pilot-002-seguridad-homicidios
- pilot-003-salud-vigilancia
- pilot-005-empleo-publico
- pilot-012-control-fiscal
- pilot-013-app-dnp
- pilot-021-sensibilizacion-valle
- pilot-022-red-vial
- pilot-038-precipitacion
- pilot-045-negativo-dato-personal
- pilot-046-negativo-tiempo-real

Ejecuta el runner formal con:

- suite golden-v1;
- gate smoke;
- seed 601000;
- google/gemini-2.5-flash;
- textual facts enabled;
- los 10 case_id exactos.

Condiciones:

- 10 resultados únicos;
- negativos 2/2;
- cero retrocesos de sólidos;
- cero infraestructura;
- cero fabricación;
- cero huérfanas;
- integridad completa;
- fallos completamente clasificados.

Si el smoke falla por un bloqueo real o causa incierta, detente.

Si falla únicamente por un defecto demostrado del arnés, diagnostícalo y detente; no hagas bypass.

No ejecutes full si el smoke no es aceptable.

FASE 4 — GOLDEN-V1 COMPLETO

Después del smoke aceptable:

uv run python eval/run.py --suite golden-v1 --gate full --seed 601000 --provider google --model gemini-2.5-flash --textual-facts-enabled

Una sola ejecución.

Audita:

- 50 resultados;
- 40 positivos y 10 negativos;
- cardinalidad única;
- fabricación;
- huérfanas;
- integridad;
- recall;
- Socrata;
- infraestructura;
- costo;
- latencia;
- terminales;
- failure codes;
- cero running;
- hashes.

INTERPRETACIÓN DE GOLDEN-V1

Golden-v1 es una regresión histórica congelada. Un gate_passed=false no implica automáticamente que debas corregir todos los casos.

Clasifica únicamente sus fallos en:

A. REAL_BLOCKER
- falso;
- fuente equivocada;
- cifra materialmente incorrecta;
- privacidad;
- ausencia de evidencia;
- fallo sistemático.

B. GOLDEN_MISALIGNMENT
- expected_fact exige algo que la pregunta no determina;
- desempate oculto;
- fila arbitraria;
- corte temporal no solicitado;
- representación histórica desalineada.

C. NON_BLOCKING_WARNING
- respuesta parcial pero correcta;
- consulta no óptima;
- menor detalle;
- presentación mejorable.

D. INFRASTRUCTURE
- proveedor, timeout, worker o arnés no evaluable.

E. EVAL_DEFECT
- el runtime es correcto, pero el evaluador lo clasifica mal.

No investigues exhaustivamente todos los detalles si no cambian la decisión.

Detente antes de golden-v2 solamente si ocurre alguno:

- fabricación;
- cifra huérfana real;
- fuente/entidad equivocada;
- contradicción material;
- privacidad;
- integridad rota;
- negativos incorrectos;
- patrón sistémico;
- resultado incierto que no pueda clasificarse con la evidencia persistida.

Si los fallos restantes son exclusivamente golden_misalignment o non_blocking_warning, documéntalos y continúa a golden-v2.

Si hay un fallo aislado de infraestructura, no lo llames regresión. Evalúa si impide una medición válida; no reintentes automáticamente.

FASE 5 — GOLDEN-V2 COMPLETO

Solo si golden-v1 no deja bloqueos reales pendientes.

uv run python eval/run.py --suite golden-v2 --gate full --seed 601000 --provider google --model gemini-2.5-flash --textual-facts-enabled

Una sola ejecución.

Condiciones normativas:

- 50 casos exactos;
- positivos >=80%;
- negativos 100%;
- fabricación 0;
- huérfanas 0;
- integridad/reproducibilidad 100%;
- cero fallos de infraestructura;
- latencia y costo completos;
- terminal único;
- persistencia correcta.

Si golden-v2 falla por un bloqueo real, detente.

No cambies golden-v2 para hacerlo pasar.

Si falla solo por expected facts desalineados, demuestra cada discrepancia con evidencia antes de recomendar una decisión coordinadora.

CI Y UV.LOCK

El cambio para que CI consuma uv.lock es importante antes del despliegue, pero no bloquea la ejecución local de golden-v1/v2.

Después de los golden, propone o implementa en commit separado:

- uv con versión fija;
- `uv sync --locked --extra dev`;
- `uv run ruff check .`;
- `uv run pytest -m "not integration"`;
- auditoría de dependencias desde el entorno bloqueado;
- Python 3.12;
- PostgreSQL y extensiones actuales.

No inventes una versión de GitHub Action. Usa una fuente oficial y reproducible.

COMMITS

Puedes crear commits locales para:

- corrección genérica de precisión;
- correcciones reales adicionales encontradas por golden;
- frontend, si existe un defecto material;
- adopción de uv.lock en CI.

Cada commit debe:

- ser pequeño;
- tener pruebas proporcionales;
- no incluir documentos ni informes;
- no incluir archivos untracked preexistentes;
- no hacer amend;
- no hacer push.

FORMATO DE ENTREGA

Entrega:

1. Preflight.
2. Commit de precisión y archivos exactos.
3. Pruebas exactas.
4. Corrida dirigida pilot-034.
5. Smoke: UUID, reporte y veredicto.
6. Golden-v1: UUID, métricas y clasificación de fallos.
7. Decisión de continuar o detenerse.
8. Golden-v2, si fue autorizado por los resultados.

- READY_FOR_V2_INTEGRATION_AND_DEPLOYMENT_PREP
- GOLDEN_V1_BLOCKED_BY_REAL_DEFECT
- GOLDEN_V2_BLOCKED_BY_REAL_DEFECT
- BLOCKED_BY_INFRASTRUCTURE
- AWAITING_COORDINATOR_AUDIT