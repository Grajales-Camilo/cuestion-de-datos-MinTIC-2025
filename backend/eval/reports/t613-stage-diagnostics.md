# Cierre T-613 — matriz de etapas y motivos de fallo

**Fecha:** 2026-07-16
**Requisitos:** RF-602, RF-603; Constitución Art. I, IV y VII
**Alcance:** evaluación, persistencia diagnóstica, reporte y observabilidad estructurada. No incluye el smoke T-614 ni cambios de recuperación.

## Resultado

T-613 queda completa. Cada resultado OE3 persiste una estructura `stage_diagnostics` versión `1.0` dentro de `EvalCaseResult.metrics`, columna JSONB existente. No se añadió ni modificó una migración relacional.

La estructura contiene las etapas y campos exigidos por `pruebas.md` §4.4: última etapa exitosa, etapa/código de fallo, responsable `agent|golden`, motivo de parada, datasets recuperados/intentados/aceptado, rango esperado, errores de validación, consumos, conteos de evidencia/claims, verificación de hechos, latencia y costo.

## Implementación

- `backend/eval/diagnostics.py`: enums `EvalStage` y `FailureCode`, observaciones normalizadas y clasificador puro.
- `backend/eval/run.py`: recolección de `agent_steps`, persistencia JSONB y tablas Markdown de casos, etapas, códigos y recuperación.
- `backend/app/agent/runner.py`: añade exclusivamente metadatos diagnósticos a las trazas deterministas: IDs recuperados, intentados, candidato actual y errores tipados del plan.
- `backend/app/agent/deterministic_runtime.py`: expone `diagnostic_code` opcional en la traza; no altera transiciones ni resultados.
- Pruebas ampliadas en `test_eval_metrics.py`, `test_eval_persistence.py` y `test_eval_run_error_handling.py`.

## Casos cubiertos

- dataset esperado no recuperado;
- recuperado pero no intentado;
- fallo de perfilado;
- plan inválido con errores canónicos;
- consulta con cero filas;
- evidencia rechazada;
- claims rechazados;
- golden ambiguo y responsabilidad `golden`;
- caso aprobado sin código de fallo;
- error de infraestructura sin abortar los demás casos;
- persistencia JSONB versionada;
- renderizado de tablas Markdown.

## Evidencia ejecutada

```text
uv run pytest -q tests/test_eval_metrics.py tests/test_eval_persistence.py tests/test_eval_run_error_handling.py
29 passed

uv run pytest -q -m "not integration"
643 passed, 90 deselected

uv run pytest -q -m deterministic_agent_acceptance
14 passed, 1 xfailed

uv run pytest -q -m legacy_agent_acceptance
7 passed

uv run ruff check .
All checks passed
```

El `xfail(strict=True)` conserva visible el defecto conocido de presupuesto de candidatos. No se ejecutó una evaluación con LLM real ni el smoke de diez casos: ambos pertenecen a T-614.

## Integridad

- `golden-v1.yaml`: intacto.
- Contratos y modelo relacional: intactos.
- Recuperación, planificación, ejecución, calidad, claims y síntesis: sin cambios de decisión.
- Runtime legacy: intacto.
- T-614, T-615 y T-616: no iniciadas.
