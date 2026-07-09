# Guía para anotar 30 golden_queries — T-205

Las 30 consultas (≥ 10 territoriales) son **trabajo humano obligatorio** por `research.md` §1, procedimiento (c). Este documento acelera la anotación sin automatizar lo que exige juicio de dominio.

## Estructura de cada query

```python
{
    "query": "pregunta en español, naturalista",
    "expected_dataset_ids": ["id-real-del-dataset", ...],  # uno o más IDs verificados a mano
    "territorial": False,  # True si menciona municipio/departamento real
    "notes": "cómo hallaste el dataset, verificación fuente, etc."
}
```

## Paso 1: Explorar la muestra congelada

La muestra (`notebooks/fixtures/catalog_sample.json`) tiene 200 datasets de T-201 (ingesta real del 2026-07-09).
Usa **en el notebook** la función `buscar_por_palabra_clave(palabra)` para hallar candidatos por texto.

Ejemplo (en el notebook, celda de búsqueda):
```python
buscar_por_palabra_clave("educación")
# → [('fn2v-r4gu', 'Hoja de Ruta Nacional de Datos...'), ...]
```

**NO adivines**: abre cada dataset en https://datos.gov.co y confirma que responde la pregunta.

## Paso 2: Territoriales — Municipios/Departamentos reales

Las ≥ 10 consultas territoriales DEBEN usar topónimos reales de `notebooks/fixtures/divipola_master.json` (1.155 entradas confirmadas de DANE).

Códigos útiles de ejemplo:
- **05148**: El Carmen de Viboral, Antioquia
- **08001**: Medellín, Antioquia
- **11001**: Bogotá D.C., Distrito Capital
- **76520**: Yumbo, Valle del Cauca

**Verifica la existencia del municipio en el fixture ANTES de escribir la query**:
```python
# En el notebook:
[d for d in divipola_fixture.get('rows', []) if d.get('code') == '05148']
# Debe devolver una fila; si no, el código no existe.
```

## Paso 3: Escribir las queries — Ejemplo de formato anotado

```python
golden_queries: list[dict] = [
    # Consultas de educación (general)
    {
        "query": "deserción escolar en Colombia",
        "expected_dataset_ids": ["fn2v-r4gu"],  # "Hoja de Ruta Nacional de Datos..."
        "territorial": False,
        "notes": "Verificado en datos.gov.co: el dataset de MinTIC lista programas de educación abiertos.",
    },
    # Consultas territoriales
    {
        "query": "programas de educación en El Carmen de Viboral (05148), Antioquia",
        "expected_dataset_ids": ["xxxxxx-yyyy"],  # ID real del dataset de Antioquia educación
        "territorial": True,
        "notes": "Código DIVIPOLA 05148 confirmado en divipola_master.json; dataset verificado en datos.gov.co",
    },
    # Consultas generales (no territoriales)
    {
        "query": "presupuesto municipal",
        "expected_dataset_ids": ["id-del-dataset-presupuestos"],
        "territorial": False,
        "notes": "Buscado con buscar_por_palabra_clave('presupuesto')",
    },
    # ... (27 más para llegar a 30)
]
```

## Paso 4: Criterios de calidad

- **Cada `expected_dataset_ids`**: verificar a mano que el dataset existe en la muestra y responde la query.
- **Territoriales**: SOLO municipios/departamentos de DIVIPOLA (`divipola_master.json`); no inventar.
- **Diversidad**: mezcla educación, presupuestos, salud, agricultura, etc.—no todas sobre lo mismo.
- **Anotación honesta**: si un dataset NO está en la muestra, dejar `expected_dataset_ids` vacío o marcar `"notes": "no hallado en la muestra"`. Eso es evidencia legítima de recall bajo.

## Rutas rápidas de búsqueda

En el notebook, prueba estas palabras clave típicas:

```python
# Generales
buscar_por_palabra_clave("educación")
buscar_por_palabra_clave("salud")
buscar_por_palabra_clave("presupuesto")
buscar_por_palabra_clave("agricultura")
buscar_por_palabra_clave("transporte")
buscar_por_palabra_clave("empleo")
buscar_por_palabra_clave("medio ambiente")

# Territoriales (por departamento)
buscar_por_palabra_clave("Bogotá")
buscar_por_palabra_clave("Antioquia")
buscar_por_palabra_clave("Valle del Cauca")
buscar_por_palabra_clave("Medellín")
```

## Bloqueo esperado

Si después de búsquedas razonables **no encuentras 30 queries verificables**, eso es información válida del benchmark:
- Significa que la muestra (200 datasets) es demasiado pequeña para ciertos dominios.
- Documenta el resultado igual: "sólo hallamos 18 queries verificables" es más honesto que inventar 12 falsas.
- En la tabla comparativa (sección 6 del notebook), el recall bajo será una métrica real, no un artefacto.

## Siguiente paso

Una vez completes las 30 queries anotadas en el notebook (reemplazando `golden_queries`), vuelve a ejecutar las celdas 7 en adelante para calcular recall@10, latencia, y tabla comparativa. Escribe en `GOLDEN_QUERIES_COMPLETED.md` que ya terminaste, para que yo pueda ejecutar el benchmark con Gemini + E5 sin bloqueos.
