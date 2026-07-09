# Benchmark de embeddings (T-205) — instrucciones

Decide qué modelo de embeddings usa el índice semántico del catálogo (RF-301…304). Es la
decisión `PENDIENTE` de [`specs/001-cuestion-de-datos-v2/research.md`](../specs/001-cuestion-de-datos-v2/research.md)
§1. **Tú tomas la decisión final** (Sección 7 del notebook); este documento y el notebook
solo preparan el entorno reproducible para medirla.

## 0. Prerrequisitos

- Backend instalado (`backend/.venv`) y funcionando según `quickstart.md`.
- Postgres local arriba (`docker compose up -d db`) con **T-201 y T-201A ya corridos**
  (catálogo ingerido) y **T-202 ya corrido** (`divipola_entries` cargado).
- `GOOGLE_API_KEY` en tu entorno (candidato gestionado `gemini-embedding-2`).
- ~3 GB de espacio en disco libre (pesos del modelo local `intfloat/multilingual-e5-large`
  + dependencias de PyTorch).
- Un cliente de notebooks que pueda usar el venv de `backend/` como kernel: la extensión
  Jupyter de VS Code, o `jupyter lab`/`jupyter notebook` instalados aparte (no son
  dependencias del proyecto — ver §3).

## 1. Instalar el entorno del benchmark

Desde `backend/`, con el venv activado:

```powershell
pip install -e ".[dev,benchmark-embeddings]"
```

Instala versiones **fijas** (no rangos, `research.md` §1 lo exige para reproducibilidad):
`sentence-transformers==5.6.0`, `torch==2.13.0`, más `ipykernel`/`pandas`/`psutil` como
herramental del propio notebook. Confirmado compatible con Python 3.12/3.13 en Windows
(wheels `cp312`/`cp313 win_amd64` en PyPI, verificado 2026-07-09). Estas dependencias
**no** son de runtime del backend — quedan fuera de `dependencies` en `pyproject.toml`
hasta que tú decidas el modelo ganador (§6 de este documento).

## 2. Congelar la muestra fija

Con Postgres local arriba y el catálogo/DIVIPOLA ya cargados:

```powershell
python scripts/export_benchmark_fixture.py --catalog-limit 500
```

Escribe `notebooks/fixtures/catalog_sample.json` (muestra de `catalog_datasets`,
`api_active=true`, con `embedding_text` ya construido por T-201) y
`notebooks/fixtures/divipola_master.json` (T-202 completo, ~1.155 filas). El notebook
**nunca** lee Postgres directamente — solo estos dos JSON versionables — para que el
benchmark sea comparable entre corridas aunque el catálogo real siga cambiando.

`--catalog-limit` por defecto es 500. Si el candidato local es demasiado lento en tu
máquina, repite con `--catalog-limit 200` (mismo espíritu que la nota de `quickstart.md`
§8 sobre embeddings lentos en CPU).

> Los archivos de `notebooks/fixtures/*.json` quedan versionados en git a propósito
> (son la "muestra congelada" exigida por `research.md` §1): no los agregues a
> `.gitignore`. Si vuelves a exportar con `--catalog-limit` distinto, el diff del PR
> deja explícito qué cambió.

## 3. Registrar el kernel de Jupyter

`ipykernel` ya quedó instalado en el paso 1. Regístralo para que VS Code / Jupyter lo
vean como opción de kernel:

```powershell
python -m ipykernel install --user --name=cuestion-de-datos-backend --display-name "Python 3 (cuestion-de-datos-backend)"
```

Abre `notebooks/01_benchmark_embeddings.ipynb` (VS Code: `code notebooks/01_benchmark_embeddings.ipynb`,
extensión Jupyter instalada) y selecciona el kernel `cuestion-de-datos-backend`. Si prefieres
`jupyter lab` en vez de VS Code, instálalo aparte (`pip install jupyterlab`, no es
dependencia fijada por este proyecto) y ejecútalo desde `backend/` con el venv activo.

## 4. Correr el notebook, en orden

El notebook (`01_benchmark_embeddings.ipynb`) tiene 7 secciones. Dos de ellas **no se
pueden automatizar** — son trabajo tuyo de dominio, no del modelo:

| Sección | Qué hace | Automatizable |
|---|---|---|
| 0 | Registra versión de Python, librerías, CPU/RAM, dispositivo (CUDA/CPU) | Sí |
| 1 | Carga `notebooks/fixtures/*.json` | Sí |
| **2** | **Consultas de prueba (golden queries)**: ≥ 30 en español, ≥ 10 territoriales, dataset esperado **anotado a mano** | **No — trabajo tuyo** |
| 3 | Embeddings con `intfloat/multilingual-e5-large` (local, CPU) | Sí, celdas comentadas por defecto |
| 4 | Embeddings con `gemini-embedding-2` (REST, requiere `GOOGLE_API_KEY`) | Sí, celdas comentadas por defecto |
| 5 | recall@10 (general y solo territorial) + latencia p50/p95 | Sí |
| 6 | Tamaño de índice + tabla comparativa de los 10 criterios de `research.md` §1 | Parcial — algunos criterios (dependencia de proveedor, reproducibilidad, viabilidad en el servidor del piloto) piden tu juicio, no solo un número |
| **7** | **Decisión razonada, firmada** | **No — trabajo tuyo** |

### 4.1 Anotar las golden queries (Sección 2)

Usa `buscar_por_palabra_clave("término")` (definida en la propia celda) para acortar la
búsqueda en la muestra congelada, pero **confirma a mano** cuál `dataset_id` responde
realmente cada pregunta antes de agregarla a `golden_queries`. Para las ≥ 10 consultas
territoriales, usa nombres reales de `notebooks/fixtures/divipola_master.json` (municipios
o departamentos que sí existen, con su código DIVIPOLA) — no inventes topónimos ni
códigos. Si una pregunta territorial razonable no tiene ningún dataset que la responda en
la muestra, es un resultado legítimo del benchmark (recall bajo en ese caso), no un
motivo para forzar una respuesta falsa (Constitución Art. I).

Las dos entradas de ejemplo en la celda están marcadas `EJEMPLO` — bórralas o
reemplázalas; no cuentan para el mínimo de 30.

### 4.2 Candidato local (Sección 3)

Descomenta las tres líneas al final de la celda. La primera corrida descarga los pesos
de `intfloat/multilingual-e5-large` (~1-2 GB) desde HuggingFace Hub — solo la primera vez,
luego quedan en caché local. Con 500 textos y `batch_size=16` en CPU, cuenta con varios
minutos; si es demasiado lento, vuelve al paso 2 con `--catalog-limit 200`.

### 4.3 Candidato gestionado (Sección 4)

Descomenta las líneas al final de la celda. Requiere `GOOGLE_API_KEY` en el entorno
(`$env:GOOGLE_API_KEY = "..."` en PowerShell, mismo valor que `backend/.env`).
`GEMINI_OUTPUT_DIM` por defecto es 768 (recomendado por Google, compatible con
`vector(<=2000)` sin pasar a `halfvec`); puedes repetir la corrida con 1536 o 3072 para
comparar calidad/tamaño si quieres esa evidencia adicional antes de decidir.

Antes de usar `GEMINI_PRICE_PER_1M_TOKENS_USD` para cualquier cálculo de presupuesto real,
verifica el precio vigente en <https://ai.google.dev/gemini-api/docs/pricing> — el valor
en el notebook quedó verificado el 2026-07-09 (USD 0,20 / 1M tokens de entrada, tier
pagado; el tier gratuito no cobra pero tiene límites de tasa más bajos), y los proveedores
cambian precios sin aviso.

### 4.4 Tabla comparativa (Sección 6)

Antes de rellenar la fila 9 ("tamaño del índice resultante"), pega en
`CATALOG_TOTAL_DATASETS_ACTIVE` el conteo real del catálogo completo (no de la muestra):

```powershell
docker compose exec db psql -U usuario -d cuestion_de_datos -c "SELECT count(*) FROM catalog_datasets WHERE api_active;"
```

Los criterios 6 (viabilidad local), 7 (dependencia de proveedor) y 8 (reproducibilidad) no
salen de una fórmula: complétalos con lo que mediste en la Sección 0 (RAM/CPU usados)
contra el tier de hosting real (`plan.md` §2, Railway/Render básico) y con tu propio
juicio sobre cada proveedor.

## 5. Decidir y firmar (Sección 7)

Completa la plantilla de la última celda con el modelo elegido, la dimensión, el tipo de
columna pgvector (`vector` si `DIM <= 2000`, `halfvec` si no) y la justificación
referenciando los 10 criterios medidos. Fírmala con tu nombre y fecha.

## 6. Propagar la decisión (mismo PR)

Con la decisión firmada, actualiza en el mismo PR:

1. `specs/001-cuestion-de-datos-v2/research.md` §1 — reemplaza `PENDIENTE` por
   `DECIDIDA`, con la justificación y el link/resumen de la evidencia del notebook.
2. `specs/001-cuestion-de-datos-v2/data-model.md` — reemplaza `<DIM>` en
   `catalog_embeddings` por el valor real.
3. `specs/001-cuestion-de-datos-v2/plan.md` — actualiza la fila "Embeddings" de la
   tabla de stack (ya no "DECISIÓN PENDIENTE").
4. `backend/.env.example` y `quickstart.md` — fija `EMBEDDING_MODEL`.
5. `backend/pyproject.toml` — agrega la dependencia definitiva de **runtime** (fuera del
   extra `benchmark-embeddings`, que sigue siendo solo para investigación) si el modelo
   elegido es el local; si es el gestionado, no hace falta ninguna dependencia nueva
   (`langchain-google-genai`/`httpx` ya son runtime).
6. `specs/001-cuestion-de-datos-v2/tasks.md` — marca T-205 hecha con la evidencia real
   (igual patrón que T-201/T-201A/T-202) y confirma que T-104B queda desbloqueada.

Solo después de esto T-104B puede crear la migración definitiva de `catalog_embeddings`.
