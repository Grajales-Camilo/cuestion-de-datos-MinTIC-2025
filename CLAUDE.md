# Guía estable para Claude Code

Este archivo es una puerta de entrada operativa para Claude Code. **No define
una misión, fase, rama, commit ni corrida de evaluación permanentes.** El
alcance vigente siempre proviene del encargo más reciente del usuario.

## Fuente de instrucciones

1. Lee y aplica `AGENTS.md` de la raíz.
2. Respeta la jerarquía normativa y el orden de lectura definidos allí.
3. Si el trabajo toca `frontend/`, continúa con `frontend/AGENTS.md` y el
   enrutamiento documental que ese archivo establece.
4. Este `CLAUDE.md` no sustituye `AGENTS.md`, la constitución, la
   especificación, los contratos ni `tasks.md`.

Ante una contradicción:

- la jerarquía normativa de `AGENTS.md` gobierna requisitos y contratos;
- el encargo explícito más reciente del usuario gobierna el alcance de la
  sesión;
- el worktree real gobierna rama, commit y archivos existentes;
- una descripción histórica incluida en informes o conversaciones anteriores
  no reemplaza ninguna de las anteriores.

No detengas el trabajo solo porque una sesión anterior trató otra fase o rama.
Detente y consulta únicamente si la discrepancia actual implica pérdida de
datos, incumplimiento contractual, seguridad, privacidad, fabricación de
evidencia o una prueba esencial no reproducible para el incremento concreto.

## Estado Git y propiedad de cambios

- No existe una rama ni un `HEAD` fijados por este archivo. Comprueba al inicio
  `git status --short --branch` y trabaja sobre la rama real, salvo que el
  usuario ordene cambiarla.
- El repositorio puede contener muchos cambios rastreados y archivos
  `untracked` de otros incrementos o agentes. Presérvalos.
- No limpies el worktree para hacerlo coincidir con una descripción antigua.
- No hagas `git add`, commit, amend, push, merge, PR ni despliegue sin
  autorización explícita del usuario para esa acción.
- Nunca uses `git add -A` sobre un worktree compartido.

## Descubrimiento y uso de contexto

- Usa primero `codebase-memory-mcp` con el proyecto canónico:
  `D-Usuario-AppWebs-cuestion-de-datos-MinTIC`.
- Prioriza `search_graph`, `trace_path` y `get_code_snippet`.
- Consulta el estado del índice y actualízalo solamente si está
  desactualizado.
- El worktree prevalece si el índice no contiene archivos nuevos o contradice
  el código real. Registra esa limitación una sola vez y usa lectura directa
  focalizada.
- Lee la documentación obligatoria una sola vez por sesión; después consulta
  solo las secciones pertinentes. No releas capturas o documentos ya
  inspeccionados sin una razón concreta.

## Trabajo en frontend v2

- El frontend v2 se desarrolla de forma incremental en `/app`; la ruta `/` y
  el frontend legacy permanecen intactos hasta la tarea que autorice su
  retirada.
- El backend determinista FastAPI es el único modelo funcional y de
  aceptación. El frontend legacy puede orientar un inventario, pero no es un
  fallback funcional.
- No modifiques backend, contratos, fixtures reales, golden suites ni
  documentos normativos durante un incremento frontend salvo autorización
  expresa.
- Las decisiones marcadas `PENDIENTE` bloquean únicamente el trabajo que
  dependa de ellas. No deben paralizar incrementos independientes.
- Si la tarea modifica UI, interacción, responsive o accesibilidad, usa la
  skill Impeccable instalada en el repositorio sin permitir que contradiga los
  requisitos normativos.
- El puerto `3000` está reservado para el usuario. Usa `3101` o, si está
  ocupado, `3100`, y libera los procesos propios al terminar.

## Seguridad y evidencia

- Nunca imprimas ni introduzcas secretos, tokens de corrida, credenciales,
  archivos `.env` reales o datos personales.
- No pongas tokens en URL, DOM, logs, mensajes de error, telemetría ni estado
  serializable.
- No inventes fixtures, payloads, resultados, capturas, métricas ni evidencia
  de ejecución. Distingue expresamente los dobles sintéticos de los datos
  reales.
- No cambies contratos, golden data, `expected_facts`, preguntas, umbrales,
  cardinalidades o presupuestos para hacer pasar una implementación.
- Una deuda ambiental o documental reconocida no bloquea trabajo
  independiente. Sí bloquean pérdida de datos, incumplimiento contractual,
  seguridad, privacidad, fabricación de evidencia y pruebas esenciales no
  reproducibles.

## Ejecución y reporte

- Trabaja en incrementos pequeños y respeta literalmente lo que queda fuera de
  alcance.
- Durante el desarrollo ejecuta pruebas focalizadas. Deja lint, suite completa
  y build para una sola validación final, en proporción al riesgo del cambio.
- No repitas automáticamente corridas reales costosas ni suites completas por
  un flake ambiental ya aislado y documentado.
- El reporte final debe resumir resultados y archivos tocados; no reproduzcas
  salidas completas de comandos.
- No declares cerrada una fase completa cuando solo quedó cerrado un
  incremento. Indica un único siguiente incremento concreto y no lo empieces
  sin autorización.

## Orientación para el inicio de una sesión

Antes de actuar, responde internamente estas preguntas con evidencia actual:

1. ¿Cuál es el último encargo explícito del usuario?
2. ¿Qué fase, incremento y requisitos `RF-###`/`RNF-###` cubre?
3. ¿Cuál es la rama y el estado real del worktree?
4. ¿Qué decisiones pendientes bloquean realmente este alcance y cuáles no?
5. ¿Qué archivos pertenecen al incremento y cuáles deben preservarse?

Si esas respuestas son coherentes, continúa. No solicites una confirmación
adicional solo porque `CLAUDE.md` anteriormente describía otro trabajo.
