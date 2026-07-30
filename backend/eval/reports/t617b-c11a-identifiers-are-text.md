# T-617B-C11A — Códigos e identificadores preservados como texto exacto

**Fecha:** 2026-07-19 (America/Bogota)
**Baseline:** `94c77955a8388284c5c6682eb552a01b3e733a2e`
**Estado:** `READY_FOR_DIRECTED_REAL_VALIDATION / FULL_GATE_BLOCKED`

## 1. Evidencia que originó el incremento

La validación real dirigida posterior a C11
(`4d77e605-cb70-4e3b-b26b-4c8201ce4780`) ejecutó cinco casos:

- `pilot-008` y `pilot-020` superaron la aceptación mecánica;
- `pilot-016` y `pilot-034` produjeron evidencia del dataset esperado, pero
  no coincidieron con sus anclas históricas;
- `pilot-036` agotó presupuesto y requiere diagnóstico separado.

La auditoría humana encontró un bloqueo material que la aceptación mecánica no
detectaba:

- en `pilot-020`, Socrata devolvió `cod_dpto="05"` y
  `cod_mpio="05001"`, pero la respuesta los presentó como `5` y `5.001`;
- en `pilot-016`, la fuente devolvió los códigos postales textuales
  `"153.42"` y `"153.427"`, pero fueron tratados como magnitudes y
  redondeados.

La fuente y la consulta eran correctas, pero la representación pública no:
ceros iniciales, puntuación y longitud forman parte del identificador. Esto es
una contradicción material según RF-211/RNF-003, no una advertencia estética.

## 2. Causa raíz

Para operaciones `LOOKUP`, `_claim_specs` intentaba construir un claim
cuantitativo para toda dimensión cuyo valor pudiera convertirse a número. La
clasificación Socrata `NUMBER` no basta para inferir que una columna sea una
magnitud: muchos catálogos publican códigos territoriales, postales,
institucionales o consecutivos con ese tipo.

El DSL cuantitativo normaliza y formatea números correctamente para cantidades,
pero esa operación destruye información cuando se aplica a identificadores.

## 3. Corrección genérica

Se añadió una clasificación estructural, basada únicamente en tokens del
nombre real de columna (`codigo`, `cod`, `id`, `identificador`, `postal`,
`divipola`, `nit`, `sigep`, `consecutivo`, `radicado`, etc.):

1. una dimensión identificadora nunca se convierte en claim cuantitativo;
2. si la pregunta solicita el identificador y la capacidad textual está
   habilitada, se crea un hecho `DIRECT_TEXT` por fila (máximo 12), usando el
   valor exacto de la evidencia;
3. al recargar el hecho persistido, el nombre real se reconstruye desde el
   SoQL con el parser existente y se deriva una etiqueta verificable;
4. el renderer presenta `Etiqueta: valor` sin normalizar el valor textual;
5. si la capacidad textual está apagada y no existe otro claim válido, el
   pipeline falla de forma segura: no fabrica un surrogate `count=1` ni
   presenta el código como una cantidad.

No se inspeccionan valores para decidir el tipo, ni existen reglas por
`case_id`, dataset, pregunta o cifra. Las magnitudes ordinarias conservan el
camino cuantitativo.

## 4. Compatibilidad y límites

- Los hechos textuales históricos sin etiqueta identificadora conservan su
  redacción anterior.
- No cambia el hash ni el DSL de claims cuantitativos.
- No cambia el contrato público, las migraciones, los presupuestos, los
  umbrales, golden ni `expected_facts`.
- Si el proveedor entrega un identificador como JSON numérico, no es posible
  reconstruir ceros ya eliminados por la fuente. La corrección preserva
  exactamente la representación recibida; nunca inventa una distinta.

## 5. Pruebas

Regresiones añadidas:

- `cod_mpio`, `codigo_postal`, `zona_postal`, `divipola` y NIT se clasifican
  genéricamente como identificadores; cantidades ordinarias no;
- `05001` deja de producir un claim numérico y genera un hecho textual exacto;
- dos códigos postales conservan filas separadas;
- con capacidad textual apagada, el identificador no se degrada a
  `count=1`;
- el renderer produce `Cod mpio: 05001.`;
- PostgreSQL real confirma que el hecho persistido se reverifica, conserva
  `display_value="05001"` y recupera `label="Cod mpio"` desde el SoQL.

Resultados:

- focalizadas de pipeline/texto/renderer/etiquetas: **88 aprobadas**;
- `pytest -m "not integration" -q`: **1.127 aprobadas**, 125 deseleccionadas;
- integración de persistencia textual con PostgreSQL real: **17 aprobadas**;
- aceptación determinista con PostgreSQL real: **21 aprobadas**;
- Ruff en los archivos modificados: limpio.

Los hashes de `golden-v1` y `golden-v2` permanecen intactos.

## 6. Siguiente paso

Ejecutar una única validación real dirigida de `pilot-016` y `pilot-020` con
hechos textuales habilitados. La aceptación no se limitará al resultado
mecánico: los códigos deben conservarse byte a byte y aparecer con etiquetas
consultables. `pilot-034` (precisión decimal/selección de tipo) y `pilot-036`
(intención de salida y múltiples filas) permanecen en diagnósticos separados.
No repetir `smoke` ni `full` antes de cerrar esos bloqueos materiales.
