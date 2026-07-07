# Registro de Investigación y Decisiones Técnicas — Cuestión de Datos v2.0

**Versión:** 1.0.0 · **Fecha:** 2026-07-06
**Propósito:** documentar decisiones técnicas que requieren evaluación experimental o análisis de alternativas, con su estado (`PENDIENTE` / `DECIDIDA`). Ningún documento del paquete SDD debe presentar como definitiva una decisión que aquí figure como pendiente.

---

## 1. Decisión pendiente: modelo de embeddings — `PENDIENTE`

**Problema.** El índice semántico del catálogo (RF-301…304) necesita un modelo de embeddings multilingüe con buen desempeño en español administrativo colombiano (títulos y descripciones de datasets estatales, topónimos DIVIPOLA). La elección fija la dimensión vectorial de `catalog_embeddings`, por lo que la migración definitiva de esa tabla (T-104B) NO puede crearse antes de esta decisión.

**Alternativas.**

| Candidato | Tipo | Dimensión | Notas |
|---|---|---|---|
| `intfloat/multilingual-e5-large` | Local (sentence-transformers) | 1024 | Citado en la propuesta de maestría; sin costo por consulta; exige CPU/RAM del servidor. |
| `gemini-embedding-2` | Gestionado (API Google) | según configuración del proveedor | Sin carga en el servidor; costo por token; dependencia de proveedor. |
| Otro modelo multilingüe actual | Local o gestionado | — | PUEDE incorporarse al benchmark si se justifica aquí por desempeño en español o eficiencia (documentar antes de evaluar). |

**Criterios de selección (todos se miden en el benchmark):**
1. Recuperación en español (recall@10 sobre consultas de prueba).
2. Calidad sobre consultas territoriales colombianas (municipios, departamentos, jerga administrativa).
3. Dimensión de los vectores (impacto en almacenamiento e índice HNSW).
4. Latencia (embedding de consulta en caliente, p95).
5. Costo (por 1.000 consultas y por reindexación completa del catálogo).
6. Capacidad de ejecución local (¿corre en el servidor del piloto?).
7. Dependencia de proveedor (lock-in, riesgo de deprecación).
8. Reproducibilidad (¿un tercero puede regenerar el índice idéntico?).
9. Tamaño del índice resultante (~8.000 vectores × dimensión).
10. Compatibilidad con PostgreSQL + pgvector (límites de dimensión del índice HNSW).

**Procedimiento de benchmark (T-205, reproducible):** notebook `notebooks/01_benchmark_embeddings.ipynb` versionado, con: (a) muestra fija de metadatos ya ingeridos (T-201), congelada como fixture; (b) ≥ 30 consultas de prueba en español con dataset esperado anotado a mano (incluidas ≥ 10 territoriales); (c) las mismas consultas contra cada candidato; (d) tabla comparativa contra los 10 criterios; (e) decisión razonada firmada por el responsable del proyecto.

**Decisión:** _pendiente de T-205._

**Consecuencias de la decisión (cuando se tome):**
- Fija `<DIM>` en `data-model.md` §`catalog_embeddings` y en la migración de T-104B.
- Fija `EMBEDDING_MODEL` en `.env.example` y quickstart.md.
- NO se mezclan embeddings de modelos o dimensiones distintas en un mismo índice; cambiar de modelo después exige regenerar el índice completo o versionar índices separados (tabla por modelo).
- Si el elegido es gestionado, el cron de ingesta (T-206) necesita la API key correspondiente como secret.

## 2. Decisión registrada: durabilidad de corridas y SSE — `DECIDIDA (piloto)`

**Problema.** El contrato promete `202` + stream + recuperación tras desconexión: eso exige que las corridas sobrevivan a cortes de red y reinicios del proceso, sin depender de la memoria de FastAPI.

**Alternativas consideradas:** (a) cola externa con workers (Celery/Redis, RQ) — descartada para el piloto por Art. III (máximo 2 servicios; complejidad no justificada a ~500 corridas/mes); (b) todo en memoria — descartada por violar RF-209; (c) **elegida:** un único worker + estado y eventos en PostgreSQL + secuencia de eventos por corrida + reconexión `Last-Event-ID` (detalle normativo en plan.md §11).

**Semántica única (revisión 2):** la desconexión del navegador NO interrumpe la ejecución; los eventos se reanudan con `Last-Event-ID`; un reinicio del proceso SÍ interrumpe la corrida activa, que queda en estado TERMINAL `interrupted` con eventos y resultados parciales disponibles; el usuario vuelve a ejecutar la consulta. Se descartó la reanudación automática del trabajo del agente: prometer resurrección del grafo tras matar el único worker es frágil y deshonesto para un piloto; el checkpointer de LangGraph queda solo para inspección/diagnóstico.

**Condición de revisión:** si el piloto supera ~2.000 corridas/mes o se necesita más de un worker, esta decisión se reabre aquí (la cola externa pasa a ser candidata) y requiere enmienda de plan.md §11 y Constitución Art. III.3.

## 3. Decisión registrada: acceso a corridas persistidas — `DECIDIDA (piloto)`

**Problema.** Un `run_id` adivinable o filtrado no debe dar acceso a preguntas, contexto y trazas de otra persona. El piloto no tiene cuentas de usuario (fuera de alcance v2.0).

**Alternativas consideradas:** (a) UUID como capacidad implícita — descartada: un identificador no es autorización; (b) autenticación completa de usuarios — descartada en v2.0 por alcance; (c) **elegida:** token secreto por corrida (`run_access_token`, ≥ 256 bits) entregado una sola vez, hash SHA-256 en servidor, transmisión exclusiva por `Authorization: Bearer` (nunca URL). Normativo en RF-801 y contracts/api-rest.md.

**Alineación TTL–retención (revisión 2):** el token expira exactamente cuando vence la retención de los datos (`RUN_TOKEN_TTL = RETENTION_USER_DAYS`). Se descartó un TTL más corto que la retención (dejaría datos retenidos pero inaccesibles e imborrables por su dueño) y también la renovación de tokens (sin cuentas de usuario no hay forma segura de demostrar quién puede renovar).

**Condición de revisión:** si v2.x introduce cuentas de usuario, el token por corrida se subordina a la identidad (las corridas pasan a pertenecer a un usuario) — enmienda de spec.md Grupo 800.

## 4. Decisión registrada: política de retención — `DECIDIDA (valores provisionales)`

**Problema.** Retener todo 12 meses trataba igual datos de usuarios reales y corridas de evaluación, sin base de minimización.

**Decisión (revisada en revisión 2):** dos clases de corrida (`user` 90 días, `eval` 24 meses), valores **configurables** por entorno. Al vencer la retención (o ante borrado por solicitud, que tiene prioridad): **borrado completo** de la corrida y todas sus relaciones, tras copiar métricas agregadas no identificables a la tabla independiente `technical_metrics` (12 meses). Se descartó la anonimización fila a fila: era incompatible con los campos `NOT NULL` del modelo (p. ej. `question`) y dejaba copias residuales en `final_answer`, `tool_input/output`, eventos, narrativas y citas; el borrado total + tabla de métricas separada es ejecutable literalmente. Los valores son provisionales del piloto: la validación aplicada (OE4) con las alcaldías puede exigir ajustarlos; cualquier cambio se registra aquí.

## 5. Decisión registrada: modelo de afirmaciones cuantitativas — `DECIDIDA`

**Problema.** Verificar groundedness por coincidencia literal de cifras (regex sobre `rows`) falla con porcentajes calculados, sumas, promedios, tasas, redondeos, conversiones de unidades, formatos de miles y fechas: ni valida lo derivado ni impide que el LLM "calcule" mal en la narrativa.

**Decisión:** toda cifra presentada nace de un **claim** estructurado (`quantitative_claims`, RF-208): filas fuente + columnas + fórmula + valor bruto + valor presentado + unidad + redondeo + hash reproducible. Los claims `derived` los computa un evaluador determinista (herramienta T7), no el LLM; el sintetizador solo cita `display_value`. El verificador de groundedness re-ejecuta la cadena completa (pruebas.md §4.2); la regex sobrevive únicamente como detector auxiliar de cifras huérfanas.

**Alternativa descartada:** regex + normalización numérica como mecanismo principal — insuficiente por las razones del problema; se documenta para no reintroducirla.

## 6. Decisión registrada: conexión frontend→backend para SSE — `DECIDIDA`

**Problema.** El diseño inicial hacía pasar todo el tráfico (incluido el stream SSE de hasta 75 s) por un proxy serverless en Next.js/Vercel. Un proxy serverless introduce límites de duración, posible buffering y un comportamiento dependiente del runtime y del plan contratado, por lo que no es una ruta confiable para una conexión SSE durable como la que exigen RNF-008 (feedback en vivo) y RF-209 (reanudación); además, "ocultar la URL interna" no aporta: `api.cuestiondedatos.com` es pública.

**Alternativas consideradas:** (a) mantener el proxy y configurar streaming en Vercel — descartada: frágil, dependiente de límites del plan; (b) **elegida:** conexión directa del navegador a FastAPI con `CORSMiddleware` restringido a los orígenes del frontend, consumiendo el SSE con `fetch()` + stream de lectura — nunca `EventSource` nativo, que no admite el encabezado `Authorization` requerido por RF-801. Normativo en plan.md §11 y contracts/api-rest.md.

**Consecuencias:** variable `NEXT_PUBLIC_BACKEND_URL` en el frontend; CORS con orígenes de producción, preview y `localhost:3000`; se elimina el catch-all `pages/api/v2/[...path].js` del diseño (T-502/T-702 actualizadas).

---

*Para añadir una nueva decisión: sección numerada, estado, problema, alternativas, criterios, decisión y consecuencias. Las decisiones `PENDIENTE` bloquean las tareas que dependan de ellas (ver tasks.md).*
