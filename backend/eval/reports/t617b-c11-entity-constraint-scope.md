# T-617B-C11 — Alcance semántico de la restricción de entidad

**Fecha:** 2026-07-19 (America/Bogota)
**Baseline:** `4bd70cd9b5d818c181a6c0ce1b14a1cd629a83d6`
**Estado:** `READY_FOR_DIRECTED_REAL_VALIDATION / FULL_GATE_BLOCKED`

## 1. Hallazgo del full

La auditoría de los nueve casos `budget_exceeded` del full
`1b405332-aa8c-4870-a35c-a62875ecd599` mostró que varios presupuestos se
consumieron después de que T4 ya había encontrado el valor solicitado:

- `pilot-008`: T4 encontró `VILLAMARIA`;
- `pilot-016`: encontró `BOYACA`, `RONDON` y `RONDÓN`;
- `pilot-020`: encontró `MEDELLÍN`;
- `pilot-034`: encontró `JEPIRACHI`.

El planificador volvió a intentarlo o cambió de candidato porque
`_require_entity_constraint_preserved` rechazó el plan con
`UNKNOWN_REFERENCE`: afirmaba que la entidad no estaba filtrada en una columna
de entidad o identificador.

## 2. Causa raíz

La protección R5/R5A nació para impedir que una consulta sobre el Ministerio
de Relaciones Exteriores perdiera su filtro y devolviera la primera fila de
INPEC. Su activación tenía dos señales:

1. una columna institucional (`entidad`, `empresa`, `institucion`, etc.);
2. cualquier columna de identificador (`codigo`, `id`, etc.).

La segunda señal era demasiado amplia. Un dataset municipal puede publicar
`codigo_municipio`; uno de proyectos, `codigo_departamento`. La sola existencia
de esas columnas hacía que `Villamaría`, `Rondón`, `Medellín` o `Jepirachi`
fueran tratados como si debieran aparecer en el campo de código. Incluso cuando
el plan los filtraba correctamente en `municipio` o `nombre_proyecto`, la
protección no reconocía ese anclaje.

Esto no protegía contra una respuesta falsa: rechazaba una consulta
materialmente correcta y consumía presupuesto intentando reemplazarla.

## 3. Corrección genérica

La frontera conserva tres reglas:

1. cualquier filtro `EQ/IN` cuyo valor corresponda inequívocamente a
   `intent.entity` preserva la entidad, cualquiera que sea el nombre de la
   columna;
2. si no hay ese anclaje, una columna institucional sigue haciendo obligatorio
   el filtro y continúa bloqueando sustituciones como INPEC;
3. una columna `codigo/id` solo activa por sí misma la obligación cuando la
   entidad contiene un identificador explícito, como `PRY00062` o `código 123`.

Un `IN` mezclado continúa sin ser grounding: todos sus valores deben
corresponder a la misma entidad. No se infieren filtros ni se cambian valores;
solo se evita rechazar un filtro ya presente y verificable.

## 4. Regresiones

Pruebas nuevas:

- un dataset con `codigo`, `nombre_empresa`, `municipio` y `cantidad` acepta
  `municipio = VILLAMARÍA` para la entidad `Villamaría`;
- `APP PRY00062` sin filtro de identificador continúa siendo rechazado.

Se conservan los controles R5/R5A existentes:

- omitir el Ministerio continúa fallando;
- filtrar INPEC en su lugar continúa fallando;
- un `IN` Ministerio+INPEC continúa fallando;
- una variante normalizada y específica de la misma entidad continúa pasando;
- un identificador `PRY00062` correctamente filtrado continúa pasando;
- un identificador no sustituye el filtro institucional del Ministerio.

Resultados:

- antes del cambio, el control territorial reproducía el defecto;
- `pytest tests/test_llm_contracts.py -q`: 58 aprobadas;
- `pytest -m "not integration" -q`: 1.121 aprobadas, 124 deseleccionadas;
- aceptación determinista con PostgreSQL local: 21 aprobadas;
- Ruff y `git diff --check`: limpios.

Dos invocaciones preliminares de la aceptación no evaluaron código: una usó
una contraseña de ejemplo incorrecta y la siguiente no exportó `DATABASE_URL`
al proceso, requisito directo del fixture. La tercera cargó la URL efectiva
desde `get_settings()` sin imprimirla y aprobó 21/21.

Golden-v1 y golden-v2 permanecen intactos. No se cambiaron presupuestos,
umbrales, `expected_facts`, contratos ni cardinalidades.

## 5. Alcance y siguiente paso

Esta corrección no pretende resolver los nueve casos de presupuesto. Los casos
textuales con múltiples filas (`pilot-019`, `pilot-031`, `pilot-032`) y la
selección temporal de `pilot-033` muestran fronteras distintas que deben
auditarse por separado.

Siguiente paso: validación real dirigida de `pilot-008`, `pilot-016`,
`pilot-020`, `pilot-034` y `pilot-036`. Solo los casos que produzcan una
respuesta útil, verificable y materialmente correcta se contarán como
recuperados. Smoke/full y golden-v2 permanecen bloqueados.
