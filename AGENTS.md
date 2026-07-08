# Instrucciones para agentes

Antes de escribir o modificar código, leer en este orden:

1. `specs/constitution.md`
2. `specs/README.md`
3. `specs/001-cuestion-de-datos-v2/spec.md`
4. `specs/001-cuestion-de-datos-v2/research.md`
5. `specs/001-cuestion-de-datos-v2/plan.md`
6. `specs/001-cuestion-de-datos-v2/contracts/`
7. `specs/001-cuestion-de-datos-v2/data-model.md`
8. `specs/001-cuestion-de-datos-v2/pruebas.md`
9. `specs/001-cuestion-de-datos-v2/tasks.md`
10. `specs/001-cuestion-de-datos-v2/quickstart.md`
11. `specs/001-cuestion-de-datos-v2/checklists/requirements.md`, si existe

Este archivo refleja instrucciones operativas del repositorio. No altera la
jerarquía normativa definida por `specs/constitution.md`.

## Jerarquía

`constitution.md` > `spec.md` > `research.md` > `plan.md` >
`contracts/` > `data-model.md` > `pruebas.md` > `tasks.md` >
`quickstart.md` > código.

Si dos documentos se contradicen:

1. No asumir.
2. No modificar silenciosamente la especificación.
3. Reportar el conflicto.
4. Aplicar el documento de mayor jerarquía.

## Desarrollo

- Toda implementación debe mencionar los requisitos `RF-###` o `RNF-###`
  que satisface.
- Los contratos son la fuente de verdad de las interfaces.
- Las decisiones marcadas como `PENDIENTE` en `research.md` bloquean las
  tareas dependientes; no se deben resolver implícitamente en código.
- No cambiar contratos para adaptar código existente sin autorización.
- Ejecutar las pruebas relacionadas después de cada cambio.
- No marcar una tarea de `tasks.md` como terminada hasta verificar sus
  criterios de aceptación.
- No incluir secretos ni archivos `.env` reales.
- Trabajar en incrementos pequeños y revisables.
