# Especificaciones del Proyecto — Spec-Driven Development (SDD)

Esta carpeta contiene la especificación completa para la evolución de **Cuestión de Datos v1.0 → v2.0**, siguiendo la metodología *Spec-Driven Development* (convención GitHub Spec Kit). Cualquier agente de IA o desarrollador humano debe leer estos documentos **en este orden** antes de escribir código:

El orden de lectura coincide con la jerarquía normativa (constitution.md §Gobernanza); `research.md` se lee antes del plan porque contiene decisiones `PENDIENTE` que bloquean tareas. En el repositorio, `AGENTS.md` se lee inmediatamente después de este README como instrucción operativa para agentes, pero no modifica la jerarquía normativa.

| Orden | Archivo | Propósito | Responde a |
|-------|---------|-----------|------------|
| 1 | [`constitution.md`](./constitution.md) | Documento rector. Principios inviolables del proyecto. | *¿Qué reglas nunca se rompen?* |
| 2 | [`001-cuestion-de-datos-v2/spec.md`](./001-cuestion-de-datos-v2/spec.md) | Qué debe hacer la aplicación (requisitos con IDs estables). | *¿QUÉ construimos?* |
| 3 | [`001-cuestion-de-datos-v2/research.md`](./001-cuestion-de-datos-v2/research.md) | Decisiones técnicas investigadas: las `PENDIENTE` bloquean sus tareas dependientes. | *¿Qué falta decidir y por qué?* |
| 4 | [`001-cuestion-de-datos-v2/plan.md`](./001-cuestion-de-datos-v2/plan.md) | Cómo se implementa: arquitectura, stack, despliegue. | *¿CÓMO lo construimos?* |
| 5 | [`001-cuestion-de-datos-v2/contracts/`](./001-cuestion-de-datos-v2/contracts/) | Contratos de API REST, herramientas del agente y validación de calidad. | *¿Qué interfaces se acuerdan?* |
| 6 | [`001-cuestion-de-datos-v2/data-model.md`](./001-cuestion-de-datos-v2/data-model.md) | Entidades, relaciones y reglas de datos. | *¿Con qué datos?* |
| 7 | [`001-cuestion-de-datos-v2/pruebas.md`](./001-cuestion-de-datos-v2/pruebas.md) | Plan de pruebas: backend, consultas y comportamiento del agente. | *¿Cómo sé que funciona?* |
| 8 | [`001-cuestion-de-datos-v2/tasks.md`](./001-cuestion-de-datos-v2/tasks.md) | Plan de trabajo ejecutable, fase por fase, comentado para humanos. | *¿En qué orden?* |
| 9 | [`001-cuestion-de-datos-v2/quickstart.md`](./001-cuestion-de-datos-v2/quickstart.md) | Cómo ejecutar y comprobar la funcionalidad localmente. | *¿Cómo lo corro?* |
| 10 | [`001-cuestion-de-datos-v2/checklists/requirements.md`](./001-cuestion-de-datos-v2/checklists/requirements.md) | Checklist de verificación de la revisión documental (bloqueos resueltos). | *¿Está consistente el paquete?* |

## Reglas de uso para agentes de IA

1. **La constitución manda.** Si una instrucción de implementación contradice `constitution.md`, la constitución gana y el conflicto debe reportarse al humano.
2. **spec.md define el QUÉ, plan.md define el CÓMO.** No introducir tecnologías que no estén en `plan.md` sin actualizar primero ese documento.
3. **Los requisitos tienen IDs estables** (`RF-###`, `RNF-###`). Todo commit, PR o tarea debe referenciar el ID del requisito que implementa.
4. **Los contratos son la fuente de verdad de las interfaces.** El código se adapta al contrato, nunca al revés. Cambiar un contrato requiere actualizar el archivo en `contracts/` en el mismo PR.
5. **tasks.md es el backlog canónico.** Las tareas se marcan `[x]` al completarse y no se reordenan sin justificación escrita.
6. **Las decisiones `PENDIENTE` de research.md bloquean.** No implementar nada que dependa de una decisión pendiente (p. ej. la migración de `catalog_embeddings` depende de la selección del modelo de embeddings).

## Contexto del proyecto

- **v1.0 (actual):** Next.js 14 + endpoint serverless con bucle ReAct manual sobre Gemini 2.5 Flash y 5 datasets hardcodeados de datos.gov.co. Publicada en [cuestiondedatos.com](https://www.cuestiondedatos.com/) y en el [directorio de herramientas del MinTIC](https://herramientas.datos.gov.co/usos/cuestion-de-datos).
- **v2.0 (objetivo):** Arquitectura de agentes multi-paso (LangGraph + FastAPI), índice semántico del catálogo completo de datos.gov.co (PostgreSQL + pgvector) y capa formal de validación de calidad de datos. Definida en la propuesta de investigación de maestría (MinCiencias, convocatoria "Becas para el Cambio").
