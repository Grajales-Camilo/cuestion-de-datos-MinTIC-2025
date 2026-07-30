# T-617C-A — Enmienda documental del contrato de presentación

**Alcance: solo documentación.** No se implementó código, pruebas ni
migraciones. No se ejecutó Gemini, Socrata ni PostgreSQL real. T-617C
permanece abierta para implementación; T-617 y T-701 siguen bloqueadas.

- Repositorio: `D:\Usuario\AppWebs\cuestion-de-datos-MinTIC`
- Rama: `feat/t617-gate-preflight`
- HEAD de partida: `becac0ffcf7d3e1e376fc34b9f6dd9e0df7f4940`
- Informe diagnóstico base: `backend/eval/reports/t617c-semantic-claim-labels.md`
  (Fase A de T-617C, bloqueada en `BLOCKED_BY_PRESENTATION_WARNING_CONTRACT`)
- Decisión aprobada por Juan Camilo (este prompt): persistir la advertencia
  de presentación dentro de `agent_runs.final_answer` (JSONB existente, sin
  migración) y exponerla en la respuesta pública con campos opcionales y
  retrocompatibles.

## 1. Documentos modificados y su cambio exacto

Los 8 documentos ya tenían cambios previos del coordinador (incluido
`tasks.md`); esta ronda integró la enmienda **sobre** ellos, sin revertir ni
reescribir ninguna decisión previa.

| Documento | Qué se añadió |
|---|---|
| `spec.md` | **RF-212** (nuevo, tras RF-211): asociación de etiquetas verificables, priorización de claims relevantes, exclusión de auxiliares no solicitados, prohibición de inventar etiquetas, advertencia de presentación no bloqueante, `columns_used` = nombre real. Dos términos de glosario: "Etiqueta verificable" y "Advertencia de presentación". |
| `research.md` | Sección nueva **§29**: problema comprobado (evidencia T-617B0-A2, causa raíz de la Fase A), 3 alternativas evaluadas (reutilizar `warnings_user` — rechazada; migrar `quantitative_claims` — rechazada para este incremento; ampliar `final_answer` JSONB — elegida), decisión aprobada completa, consecuencias. |
| `plan.md` | Sección nueva **§15**: flujo de etiquetas objetivo (`ValidatedQueryPlan` → alias SoQL → claims → advertencia), persistencia sin migración, relación con calidad de evidencia. |
| `contracts/api-rest.md` | Sección nueva **§4c**: esquema público exacto (`claims[].label`, `claims[].label_status`, `presentation_warnings[]`), dos ejemplos JSON válidos, reglas del contrato, invariante reforzado sobre `columns`/`columns_used`. |
| `data-model.md` | Aclaración en la fila `columns_used` de `quantitative_claims` (nombre real, nunca alias `dim_N`/`metric_N`) y nota nueva tras la tabla: los 3 campos nuevos NO tocan `quantitative_claims`, viven solo en `agent_runs.final_answer`, sin migración. |
| `contracts/validacion-calidad.md` | Párrafo nuevo al final de §6: separación explícita entre `warnings_user` (calidad de evidencia agregada) y `presentation_warnings` (etiquetado por claim individual); prohíbe fusionarlos o modificar este documento para producir advertencias de presentación. |
| `pruebas.md` | Sección nueva **§4.6**: matriz de pruebas obligatorias — derivación de etiqueta, no intercambio, ambigüedad, no invención, relevancia semántica genérica, generalidad (sin literales de `pilot-005`), compatibilidad de contrato, fallback determinista, no regresión (5 puntos). |
| `tasks.md` | Sub-entrada **T-617C-A** dentro del bloque de T-617C existente (T-617C sigue con `- [ ]`, sin marcar), documentando la enmienda aprobada, remitiendo a este informe. |

**No modificados:** `constitution.md` (no hay contradicción normativa
demostrable; RF-208/RF-211 ya dan fundamento suficiente, tal como exigía la
instrucción) ni `checklists/requirements.md` (fuera de la lista de
documentos a mantener consistentes en esta ronda). Ambos conservan
exactamente los cambios previos del coordinador, sin ninguna edición mía.

## 2. Coherencia entre documentos (verificación cruzada)

- `spec.md` RF-212 remite a `data-model.md` para la definición de etiqueta y
  a `contracts/api-rest.md` §4c para `presentation_warnings` — ambos
  documentos usan exactamente el mismo nombre de campo y semántica.
- `research.md` §29 es la única fuente de la decisión; `plan.md` §15,
  `contracts/api-rest.md` §4c, `data-model.md` y
  `contracts/validacion-calidad.md` la referencian por número de sección en
  vez de duplicar la justificación.
- Los tres campos nuevos (`label`, `label_status`, `presentation_warnings`)
  tienen la misma forma (`string | null`, `"verified" | "ambiguous"`,
  `array` de objetos con `claim_id`/`code`/`message_user`) en `research.md`
  §29, `plan.md` §15 y `contracts/api-rest.md` §4c.
- `pruebas.md` §4.6 prueba exactamente los campos y reglas definidos en
  `contracts/api-rest.md` §4c (ningún caso de prueba inventa un campo no
  documentado en el contrato).
- `tasks.md` T-617C-A enlaza a este informe y a todos los documentos
  tocados; T-617C conserva su aceptación mínima original sin alterarla.

## 3. Verificación técnica

- **Ejemplos JSON válidos**: los dos bloques JSON nuevos de
  `contracts/api-rest.md` §4c (claim con `label`/`label_status` y
  `presentation_warnings`) se parsearon con `json.loads` sin error.
- **Ausencia de migraciones/código**: `git status --porcelain` confirma que
  ningún archivo bajo `backend/app/`, `backend/alembic/` (si existe) o
  `backend/tests/` fue tocado; los únicos cambios de esta ronda están en
  `specs/001-cuestion-de-datos-v2/*.md` y este informe.
- **`git diff --check`**: sin errores de espacios en blanco/conflictos (solo
  advertencias inocuas de normalización CRLF de Git en Windows).
- **Hashes golden antes y después** (sin cambio, no se tocaron):
  - `golden-v1.yaml`: `ab546062767ce2046508489c169a270ae00ceb1515ff67bf92d472404630ff72`
  - `golden-v2.yaml`: `1c78264cccb0da6a10920b6b212438cc40c2b70d2bbd40265f5794fdc754e483`

## 4. Estado del worktree antes del commit

`git status --porcelain` mostraba exactamente:
- `M` en los 8 documentos listados en §1 (coordinador + esta enmienda,
  mezclados en el mismo archivo sin poder separarse por autor a nivel de
  `git diff`, tal como esperaba la instrucción de "integrar sobre ellos sin
  revertir").
- `M` en `checklists/requirements.md` y `constitution.md` (solo cambios
  previos del coordinador, sin ninguna edición mía).
- Archivos no rastreados preexistentes (reportes previos de `backend/eval/reports/`,
  `backend/uv.lock`, `docs/*`), preservados intactos.
- Este informe nuevo, no rastreado hasta el commit.

## 5. Riesgos residuales

1. **Implementación pendiente (T-617C).** Esta ronda aprueba el contrato,
   no lo implementa. El código sigue produciendo alias `dim_N` en
   `columns_used` y no emite `label`/`label_status`/`presentation_warnings`
   hasta que T-617C se implemente y audite.
2. **Alternativa de migración descartada, no eliminada.** `research.md` §29
   deja registrada la alternativa de una columna `label_status` en
   `quantitative_claims` como opción futura si se decide mayor granularidad
   transaccional; no se cierra esa puerta, solo se difiere.
3. **Commit mixto con ediciones del coordinador.** Al integrar la enmienda
   sobre archivos ya modificados sin commitear, el commit de esta ronda
   incluirá también los cambios previos del coordinador en esos mismos 8
   archivos (imposible de separar a nivel de línea sin arriesgar
   reescribirlos). Esto fue instruido explícitamente ("integrar la enmienda
   sobre ellos, sin revertir ni reescribir decisiones previas"); se señala
   aquí para que la auditoría posterior lo tenga en cuenta al revisar el
   diff del commit.
4. **`checklists/requirements.md` no revisado por consistencia.** Al quedar
   fuera del alcance explícito de esta ronda, no se verificó si necesita una
   entrada para T-617C-A; queda pendiente para quien audite antes de cerrar
   T-617C.

## 6. Estado final

**READY_FOR_T617C_IMPLEMENTATION_AUDIT**
