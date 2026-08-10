# Cuestión de Datos v2

**Del catálogo abierto de Colombia a evidencia verificable, comprensible y lista para usar en decisiones públicas.**

[![CI](https://github.com/Grajales-Camilo/cuestion-de-datos-MinTIC-2026/actions/workflows/ci.yml/badge.svg?branch=v2)](https://github.com/Grajales-Camilo/cuestion-de-datos-MinTIC-2026/actions/workflows/ci.yml)
[![Sitio](https://img.shields.io/badge/Explorar-cuestiondedatos.com-002451)](https://www.cuestiondedatos.com/)
[![Aplicación](https://img.shields.io/badge/Abrir_aplicación-preview.cuestiondedatos.com-0F766E)](https://preview.cuestiondedatos.com/app)
[![Datos](https://img.shields.io/badge/Fuente-datos.gov.co-F4B41A)](https://www.datos.gov.co/)

Cuestión de Datos transforma una pregunta en lenguaje natural en una investigación auditable sobre datos abiertos del Estado colombiano. No es un chatbot que responde desde la memoria del modelo: es un copiloto de política pública que busca fuentes, construye consultas de solo lectura, evalúa la calidad de los resultados y vincula cada cifra con la evidencia que la produjo.

La propuesta cambia la relación habitual con los portales de datos. En lugar de exigir que una persona conozca de antemano el dataset, sus columnas y la sintaxis SoQL, permite empezar por el problema público y terminar con una tabla, una narrativa, una cita y una cadena de trazabilidad inspeccionable.

> **Principio rector:** evidencia verificable o nada. Si el sistema no encuentra una fuente pertinente y elegible, se abstiene de estimar cifras.

## De una pregunta a una decisión informada

La experiencia reúne en un mismo espacio el trabajo que normalmente ocurre entre buscadores, hojas de cálculo, scripts, documentos y revisiones manuales:

- un lienzo de redacción con plantillas Libre, MGA y Plan de Desarrollo;
- investigación libre o iniciada desde una sección del documento;
- pasos del agente visibles mientras la consulta avanza;
- resultados en tablas, gráficas y archivos CSV;
- calidad, publicador, consulta SoQL, fecha y limitaciones junto a la evidencia;
- inserción de narrativa y citas en el documento;
- autoguardado local, importación DOCX y exportación a Word.

La innovación no consiste en añadir un chat a un portal. La ruptura está en convertir un catálogo pensado para buscar datasets en un recorrido guiado desde el problema público hasta una afirmación reproducible. Para lograrlo, la solución separa la capacidad lingüística de la IA de las decisiones que requieren control: el modelo ayuda a comprender la pregunta y redactar, mientras el backend gobierna la selección de fuentes, la sintaxis permitida, los cálculos, la calidad y la trazabilidad.

## Prueba la experiencia publicada

1. Entra a [cuestiondedatos.com](https://www.cuestiondedatos.com/) y selecciona **Ir a la app**, o abre directamente el [lienzo de políticas](https://preview.cuestiondedatos.com/app).
2. Elige una plantilla: **Libre**, **MGA** o **Plan de desarrollo**, y crea el documento.
3. Escribe una pregunta o redacta una sección y solicita evidencia relacionada con ese contenido.
4. Sigue la investigación paso a paso. Antes de aceptar una cifra, revisa la fuente, la consulta, el resultado y las advertencias de calidad.
5. Inserta únicamente la evidencia que necesites y exporta el documento a Word cuando esté listo.

No se requiere una cuenta. El documento se conserva en el navegador y cada investigación persistida se protege con un token de alcance mínimo. Antes de la primera consulta, la interfaz informa qué contenido se guarda, durante cuánto tiempo y cómo borrarlo.

> El sitio principal presenta la propuesta y su arquitectura. La aplicación enlazada actualmente es un entorno público de demostración en staging; no equivale por sí solo a una certificación de producción.

## Datos abiertos con propósito

El sistema trabaja sobre [datos.gov.co](https://www.datos.gov.co/), no sobre una colección privada de respuestas precalculadas. El catálogo se sincroniza mediante la Discovery API y las consultas se ejecutan contra la API SODA/Socrata con SoQL de solo lectura. Así, la persona puede volver a la fuente pública y reproducir la consulta.

La recuperación combina dos perspectivas:

- **significado:** embeddings de los metadatos permiten encontrar datasets aunque la pregunta y el título no usen exactamente las mismas palabras;
- **precisión léxica:** la búsqueda de texto completo en español refuerza siglas, nombres institucionales y términos exactos.

Esta búsqueda híbrida cubre los datasets tabulares con API activa que han sido incorporados al índice y evita depender de una lista fija dentro del prompt.

### Alineación con las Hojas de Ruta de Datos Abiertos Estratégicos

El proyecto toma como referencia la [Hoja de Ruta Nacional](https://www.datos.gov.co/stories/en/s/0-Introducci-n-Hoja-de-Ruta-Nacional-y-Sectorial-d/bciw-mfud/) y las [Hojas de Ruta Sectoriales](https://www.datos.gov.co/stories/en/s/2-Hojas-de-Ruta-Sectoriales-2025/ccu8-xqer/) publicadas en el marco del Plan Nacional de Infraestructura de Datos. Estas hojas orientan la apertura y el aprovechamiento de datos de alto valor para la toma de decisiones.

La integración es concreta: el dataset nacional de MinTIC [`fn2v-r4gu`](https://www.datos.gov.co/resource/fn2v-r4gu.json) se utilizó como fuente de procedencia para cruzar 86 enlaces del portal, verificar entidades responsables y fortalecer el registro versionado de publicadores oficiales. El motor no presenta esta referencia como un ranking algorítmico automático: en cada investigación, la elección final también exige pertinencia, publicador verificable, calidad suficiente y cumplimiento de privacidad.

## El backend es el producto diferencial

El flujo combina IA, recuperación híbrida y controles deterministas. La IA propone dentro de contratos estructurados; el código decide las transiciones y puede rechazar planes, consultas o evidencias que no cumplan las reglas.

```mermaid
flowchart TD
    Client["Cliente Frontend / API REST"] -->|POST /v2/agent/query| Main["app/main.py<br/>(FastAPI Entrypoint)"]
    Client -->|GET /v2/catalog/search| SearchEndpoint["app/main.py"]

    Main -->|Orquesta ejecución| Runner["app/agent/runner.py<br/>(Dispatcher)"]
    SearchEndpoint -->|Búsqueda híbrida| CatalogSearch["app/catalog/search.py<br/>(Hybrid FTS + Embeddings)"]

    Runner -->|Inicializa dependencias| Deps["app/agent/deterministic_dependencies.py"]
    Runner -->|Ejecuta ciclo paso a paso| Runtime["app/agent/deterministic_runtime.py"]

    Runtime -->|Orquesta las 6 etapas (T1-T6)| Pipeline["app/agent/deterministic_pipeline.py"]
    Runtime -->|Persiste streaming y eventos| Durability["app/agent/durability.py"]

    subgraph Pipeline6Stages ["Pipeline Determinista (6 Etapas T1 - T6)"]
        T1["T1: Análisis de Intención<br/>(app/agent/llm_contracts.py)"]
        T2["T2: Recuperación de Catálogo<br/>(app/agent/multiquery_retrieval.py)"]
        T3["T3: Planificación SOQL<br/>(app/agent/query_plan.py & soql_renderer.py)"]
        T4["T4: Ejecución SODA/SOQL<br/>(app/tools/ejecutar_soql.py & soda_client.py)"]
        T5["T5: Evaluación de Calidad y Hechos<br/>(app/quality/grounded_facts.py & validator.py)"]
        T6["T6: Síntesis Fundamentada<br/>(app/quality/grounded_synthesis.py)"]

        T1 --> T2 --> T3 --> T4 --> T5 --> T6
    end

    Pipeline --> Pipeline6Stages

    T3 -->|Valida sintaxis y límites| Validator["app/agent/plan_validator.py"]
    T4 -->|API Externa SODA| SODA["datos.gov.co API Socrata"]
    T5 -->|Filtro PII & Geo| QualityUtils["app/quality/pii_classifier.py & territorial.py"]
    T6 -->|Generación guiada| LLMFactory["app/llm/factory.py"]

    Pipeline -->|Guarda pasos y evidencias| Persistence["app/agent/persistence.py"]
    Persistence -->|ORM Async| PostgresDB[("Base de Datos PostgreSQL<br/>(Catalog, Runs, Facts, DIVIPOLA)")]
```

La ejecución no es un bucle libre del modelo. Un supervisor con presupuestos explícitos recorre candidatos, perfila columnas, valida un plan, ejecuta la consulta y decide si la evidencia puede continuar. Los eventos se persisten para que el progreso pueda transmitirse por SSE y retomarse después de una desconexión del navegador.

## Inteligencia artificial dentro de límites verificables

La solución utiliza tecnologías emergentes allí donde aportan valor y las retira de las decisiones que deben ser reproducibles:

| Componente | Papel en la solución | Límite deliberado |
|---|---|---|
| Modelos de lenguaje | Interpretan intención, proponen planes estructurados y redactan una síntesis desde hechos autorizados. | No eligen libremente las transiciones ni pueden introducir cifras por conocimiento paramétrico. |
| Embeddings semánticos | Representan metadatos del catálogo para recuperar fuentes relacionadas por significado. | La similitud no vuelve elegible una fuente ni reemplaza la validación. |
| Búsqueda híbrida | Combina distancia vectorial con texto completo en PostgreSQL. | El resultado es una lista de candidatos, no una respuesta. |
| LangGraph y supervisor determinista | Organizan una investigación multi-paso durable, observable y acotada. | Pasos, consultas y reparaciones tienen presupuestos máximos. |
| Síntesis fundamentada | Convierte claims y hechos verificados en lenguaje claro. | Si una cifra no está respaldada, la respuesta se bloquea o se abstiene. |

La versión actual no implementa pronósticos ni inferencia causal. Su uso de machine learning se concentra en modelos de lenguaje y embeddings para comprensión y recuperación. Esta frontera es intencional: primero garantiza procedencia, calidad y reproducibilidad; sobre esa base, futuros módulos predictivos podrían evaluarse por separado sin confundir predicción con evidencia observada.

## Una metodología que puede ser auditada

Cada respuesta atraviesa controles complementarios:

- **Plan estructurado:** operaciones, dimensiones, métricas y filtros se representan en contratos tipados antes de renderizar SoQL.
- **Guardia de solo lectura:** el parser restringe sintaxis, columnas, funciones, límites y operaciones; `SELECT *`, escrituras e intentos de inyección se rechazan antes de llegar a Socrata.
- **Elegibilidad de fuente:** el publicador se contrasta con un registro versionado y el riesgo de datos personales se evalúa antes de consultar.
- **Calidad en cuatro dimensiones:** esquema, completitud, temporalidad del corte estadístico y trazabilidad producen un puntaje y advertencias visibles.
- **Claims reproducibles:** cada cifra conserva dataset, consulta canónica, filas y columnas de origen, fórmula, valor bruto, unidad y redondeo. Una huella SHA-256 cambia si cambia el contenido que sostiene el hecho.
- **Síntesis cerrada:** el texto final sólo puede referenciar hechos autorizados; un detector de cifras huérfanas impide entregar números sin respaldo.
- **Evaluación reproducible:** pruebas unitarias, integración con PostgreSQL y Socrata, contratos, casos dorados, accesibilidad y métricas de latencia/costo permiten comparar versiones sin depender de una demostración aislada.

La documentación normativa está en [`specs/`](specs/). Los requisitos que estructuran este flujo incluyen RF-201–RF-212, RF-301–RF-304, RF-401–RF-404, RF-501–RF-503 y RF-601–RF-603.

## Evidencia que se puede comunicar

El resultado no termina en una respuesta conversacional. La interfaz presenta la evidencia en capas para distintos niveles de lectura:

- una conclusión breve para orientar la decisión;
- tabla o gráfica para comprender el patrón;
- advertencias de calidad y cobertura en lenguaje claro;
- detalle técnico expandible con dataset, entidad, SoQL y fecha;
- CSV para análisis adicional;
- cita completa y narrativa lista para insertar en el documento.

Esta combinación busca reducir la distancia entre ciudadanía, equipos técnicos y responsables de política pública. Quien no programa puede formular la pregunta y revisar la fuente; quien audita puede reproducir la consulta y seguir la procedencia de cada cifra.

## Diseñado para crecer sin perder trazabilidad

El potencial de impacto proviene de reutilizar una misma infraestructura verificable en diferentes problemas públicos. Educación, salud, contratación, ambiente o desarrollo territorial pueden recorrer el mismo núcleo sin crear un chatbot ni una base de respuestas diferente para cada sector.

En el plano social, facilita que más personas conviertan datos públicos en argumentos revisables. En el económico, puede reducir tiempo de búsqueda, limpieza inicial y documentación de fuentes. En el ambiental, el mismo flujo puede aplicarse a datasets oficiales del sector siempre que superen los controles de pertinencia, calidad y privacidad; no se atribuyen resultados ambientales hasta realizar esa implementación y medirlos.

La sostenibilidad técnica se apoya en componentes reemplazables y procesos repetibles: proveedor LLM configurable, catálogo reingerible de forma idempotente, PostgreSQL como núcleo de búsqueda y persistencia, contratos versionados, consultas en vivo al portal y baterías de evaluación. La réplica a otro territorio o catálogo compatible requiere adaptar la ingesta y los contratos de fuente, no reconstruir la experiencia completa.

## Arquitectura y tecnologías

- **Frontend:** Next.js 14, React 18, Tailwind CSS, Tiptap y Pages Router.
- **Backend:** FastAPI, Python 3.12, LangGraph y runtime determinista.
- **Datos:** Discovery API, SODA y SoQL sobre datos.gov.co.
- **Búsqueda:** PostgreSQL 16, `pgvector`, texto completo en español y `pg_trgm`.
- **IA:** proveedor configurable desde el backend, salidas estructuradas y embeddings del catálogo.
- **Experiencia en tiempo real:** REST, SSE autenticado y reanudación mediante `Last-Event-ID`.
- **Integridad:** Pydantic, claims, hechos textuales, validación de calidad y huellas SHA-256.

El navegador consume `/v2/*` mediante `NEXT_PUBLIC_BACKEND_URL`. Las claves de proveedores permanecen en el servidor y no existe un proxy del agente dentro de Next.js.

## Estructura del repositorio

```text
backend/    API, agente determinista, calidad, evaluación y pruebas
db/         inicialización y extensiones PostgreSQL
frontend/   lienzo de políticas y experiencia de investigación
specs/      constitución, requisitos, contratos, datos y plan de pruebas
docs/       arquitectura, decisiones y evidencia de release
.github/    integración continua
```

La fuente normativa empieza en [`specs/constitution.md`](specs/constitution.md). El orden de lectura completo está en [`AGENTS.md`](AGENTS.md) y [`specs/README.md`](specs/README.md).

## Ejecución local

### Requisitos

- Windows 11 y PowerShell 7, o un entorno equivalente.
- Docker Desktop para PostgreSQL local.
- Python compatible con [`backend/pyproject.toml`](backend/pyproject.toml) y `uv`.
- Node.js 20 o superior y npm.
- Claves propias configuradas únicamente en archivos `.env` no versionados.

### Base de datos

```powershell
docker compose up -d db
docker compose ps
```

### Backend

```powershell
Set-Location backend
uv sync --frozen --no-dev
uv run alembic upgrade head
uv run python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Frontend

```powershell
Set-Location frontend
npm ci
Copy-Item .env.local.example .env.local
npm run dev
```

Configura en `frontend/.env.local`:

```dotenv
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
```

Consulta el [`quickstart`](specs/001-cuestion-de-datos-v2/quickstart.md) y la [guía del frontend](frontend/README.md) para el procedimiento completo.

## Verificación

```powershell
Set-Location frontend
npm run lint
npm run test
npm run build
npm run audit:bundle
```

El workflow [`.github/workflows/ci.yml`](.github/workflows/ci.yml) valida backend y frontend en cada PR. Las evaluaciones con servicios reales tienen presupuestos y puertas independientes; una compilación verde no sustituye la evaluación funcional del agente.

## Seguridad, privacidad y estado

- No se versionan secretos ni archivos `.env` reales.
- Las consultas SoQL son de solo lectura y pasan validación estructural.
- Los documentos permanecen en el navegador; la importación y exportación DOCX se ejecutan localmente.
- Cada corrida persistida usa un token de acceso propio enviado por `Authorization: Bearer`.
- Las corridas pueden borrarse de forma irreversible desde la aplicación.
- La interfaz v2 y el staging público están operativos; la promoción y certificación de producción siguen sujetas a las puertas abiertas documentadas en [`tasks.md`](specs/001-cuestion-de-datos-v2/tasks.md).

## Licencia

MIT.
