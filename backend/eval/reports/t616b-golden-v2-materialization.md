# Cierre T-616B: materialización de `golden-v2`

## Resultado

T-616 queda cerrada el 2026-07-18 para RF-601/RF-602. La instrucción humana
«Continúa con la siguiente tarea» autorizó el incremento posterior a la puerta
T-616A-R. Se materializó una suite normativa nueva sin modificar
`golden-v1.yaml`, los contratos públicos, `eval/metrics.py` ni los umbrales de
aceptación.

La suite resultante contiene:

- 50 casos: 40 positivos y 10 negativos.
- 23 casos determinados, 10 multi-respuesta, 7 agregados y 10 de abstención.
- 59 `acceptable_facts` tipados.
- 128 proyecciones `expected_facts` compatibles con el evaluador existente.
- 31 preguntas reescritas, 4 aclaradas y 15 retenidas.

## Decisiones normativas materializadas

Se aprobaron las decisiones abiertas de T-616A-R:

- `pilot-003`: top-1 por `argmax`, sin empate, con corte explícito.
- `pilot-004`: total agregado del sector al cierre de diciembre de 2023.
- `pilot-011`: conjunto canónico completo de intervenciones.
- `pilot-012`: auditoría regular de la vigencia 2019.
- `pilot-014`: registro consolidado identificado explícitamente con `#TODOS`.
- `pilot-024`: ETC departamental literal `Antioquia (ETC)`.
- `pilot-029`: conjunto canónico de las dos fuentes de financiación.
- `pilot-033`: conteo de registros de septiembre de 2025.
- `pilot-036`: conteo agregado por departamento, sin exponer filas sensibles.
- `pilot-038` y `pilot-039`: estación, sensor y hora se incorporan literalmente
  a cada pregunta; dejan de ser filtros ocultos.

Para `pilot-016`, la fuente Socrata conserva los valores publicados
`153.42`/`153.427`, mientras que el CSV nacional oficial de 4-72 fija las formas
canónicas de seis dígitos `153420` (urbano) y `153427` (rural). La suite exige
reportar ambas representaciones y persiste la huella de la fuente canónica.

## Implementación y validadores

- `eval/golden/golden-v2.yaml`: contrato congelado `golden-v2`, versión 2.0.0.
- `scripts/t616b_materialize.py`: generación determinista, comprobación local y
  reproducción viva por HTTPS.
- `eval/loader.py`: solo admite `golden-v1` y `golden-v2`; para v2 valida
  esquema, vocabularios cerrados, cardinalidad, reglas de selección, empates,
  fuentes, fechas y huellas canónicas.
- `eval/run.py`: registra el nombre real de la suite en el informe.
- `scripts/t616a_audit.py`: mantiene sus invariantes históricos y, si v2 ya
  existe, exige que el loader estricto la reconozca.

## Evidencia ejecutada

```text
uv run python scripts/t616a_audit.py --check
OK: golden-v1 50/40/10, SHA-256 intacto, JSON válido y manifiesto consistente

uv run python scripts/t616b_materialize.py --check
OK: golden-v2 coincide con la auditoría aprobada y pasa sus validadores

uv run python scripts/t616b_materialize.py --verify-live
OK: 40/40 positivos y 128 proyecciones esperadas reproducidos
    en 44 consultas oficiales únicas

uv run pytest tests/test_eval_loader.py tests/test_eval_run_error_handling.py -q
14 passed

uv run pytest -m "not integration" -q
869 passed, 121 deselected
```

Huellas SHA-256 de cierre:

```text
golden-v1.yaml                     ab546062767ce2046508489c169a270ae00ceb1515ff67bf92d472404630ff72
golden-v2.yaml                     1c78264cccb0da6a10920b6b212438cc40c2b70d2bbd40265f5794fdc754e483
t616a-case-audit.json              688420f0e2e0e67a073cbd60201dd7365e9a27cb36a327eb168dc90dbc4cc225
t616a-evidence-manifest.json       8f760ec36b684ec348ae887ff313a14392698375561bd89fa2f0eecd350b7b78
CSV oficial de códigos postales     fdfd886f58b904ff29236eaf24acabdc999cc4fd2992493a8c3d0bc2b52241c7
```

T-402 permanece abierta como cierre formal separado. T-617 no se inició y no
se cambió el runtime por defecto ni se retiró el rollback legado.
