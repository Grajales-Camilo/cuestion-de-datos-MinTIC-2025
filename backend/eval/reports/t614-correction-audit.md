# Corrección de revisión T-614

**Fecha:** 2026-07-16
**Alcance:** atribución de fallos y puerta RNF-010. No modifica `golden-v1` ni relaja métricas.

## `failure_owner`

`expected_fact_not_found` prueba una discrepancia, pero no identifica por sí mismo al responsable. El clasificador pasa a persistir `failure_owner=undetermined` hasta una auditoría sustantiva. Un golden formalmente mal formado conserva `ambiguous_golden` y propietario `golden`.

Los reportes de smoke ya emitidos se conservan como artefactos históricos y muestran la clasificación anterior; este documento y las corridas futuras corrigen su interpretación sin reescribir resultados pasados.

### `pilot-021-sensibilizacion-valle`

- Consulta del agente: `SELECT count(*) AS metric_count_1 WHERE municipio = 'ALCALÁ' AND mes = 'Enero' AND a_o = 2018`.
- Resultado: `1`, que es el número de registros.
- Golden reproducible: la fila publicada tiene `cantidad=65`.
- Diagnóstico manual: **agente**; el plan confundió conteo de filas con la medida publicada.

### `pilot-038-precipitacion`

- La consulta del agente devolvió múltiples estaciones válidas del 11 de febrero de 2019.
- Golden: estación `0054050010`, sensor `0240`, hora `13:50`.
- La hora no está expresada en la pregunta.
- Diagnóstico manual: **golden ambiguo**; existe una restricción oculta en `source_url`. Se conserva `golden-v1` intacto y se registra para T-616.

## RNF-010

```text
uv run pytest -q -s tests/integration/test_catalog_search_rnf010.py::test_search_meets_rnf010_latency_and_coverage_budget
```

| Métrica | Observado | Puerta |
|---|---:|---:|
| Consultas | 100 | ≥ 100 |
| Cobertura | 100,00 % (8394/8394) | ≥ 90 % |
| p50 | 1302,8 ms | informativa |
| p95 | 1828,8 ms | ≤ 1000 ms |
| p99 | 2061,3 ms | informativa |

La prueba falla correctamente por latencia. Mide el endpoint con `k=10`, no la ventana interna `per_query=25`; confirma una deuda RNF-010 existente y bloquea el cierre formal de T-614.

## Estado

- Mejora de recall: conservada.
- T-614: abierta por RNF-010.
- T-615/T-616: no iniciadas; `pilot-038` queda únicamente como entrada futura de auditoría.
