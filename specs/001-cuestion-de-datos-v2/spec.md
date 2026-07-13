# Especificación Funcional — Cuestión de Datos v2.0

**Feature:** Evolución del asistente v1.0 (orquestación single-turn) a v2.0 (agente multi-paso + índice semántico + validación de calidad)
**Estado:** Aprobada para planeación · **Versión:** 1.0.0 · **Fecha:** 2026-07-06
**Documentos padre:** [`constitution.md`](../constitution.md) · Propuesta de investigación MinCiencias (OE2, OE3)

> Este documento define **QUÉ** hace el sistema. No prescribe tecnologías ni implementación (eso está en `plan.md`). Todos los requisitos tienen identificadores estables que no se reutilizan ni renumeran.

---

## 1. Propósito

Permitir que actores gubernamentales subnacionales y organizaciones de la sociedad civil en Colombia, **sin conocimientos de programación**, encuentren, consulten, validen e integren evidencia cuantitativa proveniente del catálogo de datos abiertos del Estado (datos.gov.co, más de 8.000 datasets) dentro de documentos de política pública, mediante un asistente de IA que razona en múltiples pasos y reporta la calidad y trazabilidad de cada dato entregado.

## 2. Actores

| ID | Actor | Descripción | Nivel técnico asumido |
|----|-------|-------------|----------------------|
| ACT-01 | **Funcionario formulador** | Servidor público municipal/departamental que redacta propuestas de política, proyectos MGA o planes de desarrollo. Usuario primario. | Ofimática básica. Sin SQL ni APIs. |
| ACT-02 | **Analista ciudadano** | Veedor, periodista de datos o líder social que audita afirmaciones gubernamentales con datos abiertos. | Ofimática. Puede leer tablas. |
| ACT-03 | **Investigador evaluador** | El responsable del proyecto (u otro investigador) que mide el desempeño técnico del sistema (OE3) y ejecuta la validación aplicada (OE4). | Avanzado: Python, estadística. |
| ACT-04 | **Administrador del sistema** | Quien opera la infraestructura: actualiza el índice del catálogo, rota claves, monitorea costos y errores. | Avanzado. |
| ACT-05 | **Agente de datos** (actor de sistema) | El agente de IA que ejecuta el ciclo razonar→buscar→consultar→validar→responder. Sus obligaciones se especifican como requisitos. | — |

## 3. Escenarios de usuario

Formato: *Given / When / Then*. Cada escenario referencia los requisitos que lo satisfacen.

### ESC-01 — Solicitar evidencia desde el lienzo de políticas
**Given** un funcionario (ACT-01) redactando la sección "Definición del problema" de una propuesta sobre deserción escolar en Sonsón,
**When** presiona "Investigar" sobre esa sección,
**Then** el sistema formula automáticamente una pregunta de investigación a partir del texto, ejecuta el ciclo del agente, y devuelve: (a) tabla(s) de datos reales, (b) un párrafo en tono de política pública citando fuente y año, (c) el informe de calidad de cada dato, y (d) un botón para insertar la evidencia en la sección con su cita.
*(RF-101, RF-201, RF-301, RF-401, RF-501)*

### ESC-02 — Pregunta libre en lenguaje natural
**Given** un analista ciudadano (ACT-02) en el copiloto,
**When** escribe "¿Cuántos recursos de cooperación internacional recibió el Oriente antioqueño desde 2020 y en qué sectores?",
**Then** el agente descompone la pregunta, identifica los datasets pertinentes en el catálogo completo (no solo los 5 precargados de v1.0), ejecuta las consultas necesarias en varios pasos y responde con datos, fuentes y limitaciones explícitas de los datos.
*(RF-201, RF-202, RF-203, RF-301, RF-302)*

### ESC-03 — El catálogo no tiene la respuesta
**Given** una pregunta cuya evidencia no existe en datos.gov.co (p. ej. cifras municipales que ninguna entidad publica),
**When** el agente agota su presupuesto de pasos sin hallar datos pertinentes,
**Then** responde explícitamente que no encontró evidencia, lista los datasets más cercanos que sí revisó y sugiere reformulaciones — sin inventar cifras.
*(RF-205, RNF-005; Constitución Art. I.3)*

### ESC-04 — Transparencia del razonamiento
**Given** cualquier consulta en curso,
**When** el agente trabaja,
**Then** el usuario ve en tiempo real los pasos en lenguaje claro ("Buscando en el catálogo…", "Consultando dataset X de MinSalud…", "Validando calidad…") y, al finalizar, puede expandir el detalle técnico de cada paso (consulta SoQL, filas obtenidas, puntaje de calidad).
*(RF-204, RF-403, RNF-008)*

### ESC-05 — Datos de calidad dudosa
**Given** una consulta que retorna datos de un dataset desactualizado (última actualización > 24 meses) o con columnas mayormente vacías,
**When** la capa de validación los evalúa,
**Then** la evidencia se entrega con una advertencia visible que explica el problema en lenguaje claro (p. ej. "Este dato tiene corte 2021; puede estar desactualizado"; o, si no hay corte inferible, "El portal actualizó este dataset en 2024, pero no fue posible inferir el corte estadístico") y el puntaje de calidad; si el puntaje es inferior al umbral mínimo, la evidencia se marca como "no recomendada para citar".
*(RF-401, RF-402, RF-404)*

### ESC-06 — Evaluación técnica del sistema (OE3)
**Given** el investigador (ACT-03) con el conjunto dorado de preguntas de evaluación,
**When** ejecuta la batería de evaluación contra una configuración de modelo determinada,
**Then** el sistema produce un reporte reproducible con: recuperación sobre el catálogo (recall@k), fundamentación (groundedness), tasa de éxito de consultas Socrata, latencia y costo por pregunta, comparable entre configuraciones de modelos.
*(RF-601, RF-602, RF-603)*

### ESC-07 — Actualización del índice del catálogo
**Given** el administrador (ACT-04),
**When** ejecuta el proceso de ingesta programada,
**Then** el índice semántico incorpora datasets nuevos y metadatos actualizados de datos.gov.co sin dejar el servicio fuera de línea, y registra fecha, número de datasets indexados y fallos.
*(RF-701, RF-702)*

### ESC-08 — Continuidad del trabajo del usuario
**Given** un funcionario que cierra el navegador con un documento a medias,
**When** regresa a la aplicación en el mismo dispositivo,
**Then** recupera su documento con las evidencias insertadas y sus citas intactas.
*(RF-102, RF-103)*

## 4. Requisitos funcionales

### Grupo 100 — Lienzo de políticas (Policy Canvas)

- **RF-101** — El sistema DEBE ofrecer un lienzo de redacción por secciones basado en plantillas del ciclo de política pública colombiano (mínimo: plantilla libre, MGA y plan de desarrollo), con editor de texto enriquecido.
- **RF-102** — El sistema DEBE persistir automáticamente el documento en el dispositivo del usuario (autoguardado ≤ 5 segundos tras el último cambio) y permitir exportarlo a un formato portable de ofimática.
- **RF-103** — Toda evidencia insertada en el documento DEBE conservar su cita completa (dataset, entidad, consulta, fecha) y ésta DEBE incluirse en la exportación.
- **RF-104** — El sistema DEBE permitir al usuario disparar la investigación del agente desde una sección específica, usando el contenido de esa sección como contexto.

### Grupo 200 — Agente multi-paso

- **RF-201** — El agente DEBE ejecutar un ciclo iterativo de razonamiento y acción (planificar → usar herramienta → observar → decidir) con un presupuesto máximo de pasos configurable (por defecto 14; research.md §19) y terminación explícita.
- **RF-202** — El agente DEBE poder descomponer preguntas complejas en sub-consultas encadenadas cuyos resultados intermedios alimentan pasos posteriores (p. ej. resolver el código DIVIPOLA de un municipio antes de filtrar un dataset por ese código).
- **RF-203** — El agente DEBE seleccionar datasets mediante búsqueda semántica sobre el índice del catálogo completo (RF-301), sin depender de una lista fija embebida en el prompt.
- **RF-204** — Cada paso del agente DEBE emitirse al cliente en tiempo real como evento estructurado (tipo de paso, descripción en lenguaje claro, detalle técnico).
- **RF-205** — Si el agente agota el presupuesto de pasos o no encuentra datos pertinentes, DEBE devolver una respuesta de "sin evidencia" que incluya los datasets evaluados y sugerencias de reformulación. Está PROHIBIDO responder con cifras no provenientes de una herramienta.
- **RF-206** — El agente DEBE operar sobre una capa de abstracción de modelos que permita cambiar de proveedor LLM (mínimo: Gemini como defecto y al menos otro proveedor) mediante configuración, sin cambios de código.
- **RF-207** — Las consultas generadas por el agente DEBEN limitarse a operaciones de lectura (`SELECT`); toda otra operación se rechaza antes de ejecutarse (Constitución Art. VI.3).
- **RF-208** — Toda cifra presentada al usuario (en resumen, narrativa o tarjetas) DEBE provenir de una **afirmación cuantitativa trazable** (*claim*) registrada según `data-model.md` §"quantitative_claims": con filas de origen, columnas, fórmula, valor bruto, valor presentado, unidad y regla de redondeo. Las cifras derivadas (porcentajes, sumas, promedios, tasas) DEBEN calcularse por un módulo determinista, NUNCA por el LLM en texto libre. Una cifra sin claim asociado es un defecto bloqueante.
- **RF-209** — Las corridas del agente DEBEN ser durables con esta semántica única: (a) la desconexión del cliente NO interrumpe la ejecución y el stream se reanuda desde el último evento recibido (`Last-Event-ID`); (b) un reinicio real del servidor SÍ interrumpe la corrida activa, que transiciona al estado TERMINAL `interrupted` conservando eventos y resultados parciales accesibles; (c) NO existe reanudación automática del trabajo del agente — el usuario puede volver a ejecutar la consulta; (d) al arrancar, cada instancia del backend DEBE cerrar de forma idempotente como `interrupted` solo las corridas `running` cuya instancia dueña ya no tenga lease vigente; (e) un heartbeat vencido o worker desaparecido también termina como `interrupted`; (f) la duración máxima excedida termina como `failed` con código `RUN_TIMEOUT`; (g) nunca puede quedar una corrida `running` huérfana indefinidamente.

### Grupo 300 — Índice semántico del catálogo

- **RF-301** — El sistema DEBE mantener un índice semántico (embeddings) de los metadatos del catálogo de datos.gov.co — nombre, descripción, publicador oficial normalizado, categoría, columnas y fecha de actualización publicada por el portal — que cubra como mínimo los datasets de tipo tabular con API activa.
- **RF-302** — La búsqueda semántica DEBE aceptar consultas en español y devolver los *k* datasets más pertinentes con su puntaje de similitud y metadatos suficientes para que el agente decida: columnas, filas aproximadas, `metadata_synced_at`, `data_updated_at` y una pista opcional `latest_observed_cutoff_at` si el sistema ha observado cortes en evidencias previas. El índice NO DEBE presentar `data_updated_at` ni `latest_observed_cutoff_at` como corte estadístico de una evidencia concreta; el corte normativo vive en `evidence_results.data_cutoff_at` y se calcula sobre las filas de esa evidencia.
- **RF-303** — El índice DEBE almacenar la fecha de última sincronización por dataset y exponer datasets "obsoletos en índice" (no sincronizados en la ventana definida en plan.md).
- **RF-304** — El proceso de ingesta DEBE ser idempotente: re-ejecutarlo no duplica registros ni corrompe embeddings existentes.

### Grupo 400 — Capa de validación de calidad de datos

- **RF-401** — Antes de entregar evidencia al usuario, el sistema DEBE ejecutar la validación formal de 4 dimensiones definida en `contracts/validacion-calidad.md`: **esquema** (tipos y columnas esperadas), **completitud** (proporción de valores nulos/vacíos), **temporalidad** (antigüedad del corte de datos de la evidencia, no del dataset completo) y **trazabilidad** (metadatos de fuente completos). Además, DEBE calcular una elegibilidad separada (`eligible`, `diagnostic_only`, `blocked`) que no se compensa con puntaje. La elegibilidad de fuente oficial se valida de forma determinista contra el registro versionado de publicadores oficiales; texto libre de `publisher` no basta. Datasets/columnas con PII `unknown` o `high` se bloquean antes de consultar Socrata; PII `medium` solo puede usarse con agregación mínima y sin filas individuales.
- **RF-402** — Cada evidencia DEBE recibir un puntaje de calidad (0–100) y una clasificación (`alta`, `media`, `baja`, `no_recomendada`), con los criterios y umbrales del contrato de validación.
- **RF-403** — El informe de validación DEBE ser visible para el usuario en dos niveles: resumen en lenguaje claro y detalle técnico expandible.
- **RF-404** — Evidencias clasificadas `no_recomendada` NUNCA se insertan automáticamente en el documento; requieren confirmación explícita del usuario con advertencia visible.

### Grupo 500 — Copiloto y presentación de resultados

- **RF-501** — Los resultados tabulares DEBEN presentarse como tablas legibles con posibilidad de descarga (CSV) y con la narrativa técnica lista para citar en un documento oficial.
- **RF-502** — El copiloto DEBE mantener el historial de la conversación durante la sesión y permitir re-ejecutar o refinar una consulta anterior.
- **RF-503** — Cuando la evidencia sea una serie temporal o comparación entre categorías, el sistema DEBE ofrecer una visualización gráfica simple (barras o líneas) además de la tabla.

### Grupo 600 — Módulo de evaluación (OE3)

- **RF-601** — El sistema DEBE incluir una batería de evaluación reproducible ejecutable por línea de comandos que corra el conjunto dorado de preguntas contra una configuración de modelo dada.
- **RF-602** — La batería DEBE calcular como mínimo: recall@k de recuperación sobre el catálogo, integridad de claims (cobertura, reproducibilidad y cifras huérfanas según RNF-003), tasa de éxito de consultas Socrata (HTTP 200 con filas > 0 cuando debía haberlas), latencia p50/p95 y costo estimado por pregunta.
- **RF-603** — Los resultados de cada corrida DEBEN persistirse con: fecha, versión del código (commit), configuración de modelo, métricas y detalle por pregunta, para comparación entre configuraciones.

### Grupo 700 — Administración y operación

- **RF-701** — La ingesta del catálogo DEBE poder ejecutarse manualmente y de forma programada (mínimo semanal), con reporte de resultado (datasets nuevos, actualizados, fallidos).
- **RF-702** — El sistema DEBE exponer un endpoint de salud que verifique: base de datos accesible, índice con datos, y proveedor LLM configurado.
- **RF-703** — El sistema DEBE registrar cada ejecución del agente como traza estructurada persistente (pasos, herramientas, latencias, tokens, resultado) según `data-model.md`.

### Grupo 800 — Privacidad, acceso y control de datos del usuario

- **RF-801** — El acceso a una corrida persistida (lectura, streaming, reanudación y borrado) DEBE requerir un **token de acceso por corrida** (`run_access_token`): aleatorio, secreto, entregado UNA sola vez al crear la corrida, transmitido por encabezado `Authorization: Bearer` (NUNCA en parámetros de URL), almacenado en servidor solo como hash con comparación en tiempo constante, y con fecha de expiración derivada de `retention_class` (`user`: `created_at + RETENTION_USER_DAYS`; `eval`: `created_at + RETENTION_EVAL_MONTHS`). Como el token vive exactamente lo que viven los datos, una corrida vencida se borra oportunistamente y responde `404 RUN_NOT_FOUND`, no un estado público separado de token expirado. El endpoint público `POST /v2/agent/query` crea exclusivamente corridas `user`; las corridas `eval` solo pueden crearse por el runner OE3 mediante una interfaz interna de servicio, nunca por JSON público. El `run_id` es un identificador público y NO constituye autorización.
- **RF-802** — Antes de persistir la pregunta o el contexto de una investigación, la interfaz DEBE informar al usuario: qué contenido se almacena, para qué, durante cuánto tiempo (según su clase de retención) y cómo puede borrarse.
- **RF-803** — DEBE existir un mecanismo de borrado por corrida (contrato `DELETE /v2/agent/runs/{run_id}`, protegido por el token de acceso) que elimine de forma completa e irreversible la corrida operativa y sus relaciones: pregunta, contexto, pasos, eventos, evidencias, informes de calidad, claims, checkpoints y hash del token. No se permite anonimización fila a fila de corridas.
- **RF-804** — La retención DEBE ser diferenciada por clase de corrida (`retention_class`: normales de usuarios vs evaluación OE3), con valores **configurables** definidos en `data-model.md` §7. Al vencer la retención (o ante RF-803), la corrida operativa y sus relaciones con contenido de usuario se BORRAN por completo; solo sobreviven métricas agregadas no identificables copiadas previamente a `technical_metrics` y, para OE3, instantáneas no identificables en `eval_case_results` suficientes para comparar el reporte de evaluación aunque `agent_run_id` quede `NULL`. NO DEBE usarse anonimización fila a fila de corridas.

## 5. Requisitos no funcionales

Cada RNF tiene métrica y método de verificación. "Rápido" o "usable" sin número no cuentan.

| ID | Categoría | Requisito medible | Verificación |
|----|-----------|-------------------|--------------|
| RNF-001 | Latencia | Una consulta simple (1 dataset, 1 consulta SoQL) responde en ≤ 20 s p95; una investigación multi-paso completa en ≤ 75 s p95. | Métricas de RF-703 sobre el golden set. |
| RNF-002 | Eficacia del agente | Tasa de éxito ≥ 80% sobre el conjunto dorado (respuesta con evidencia válida cuando la evidencia existe en el catálogo). | Tres puertas: cada PR ejecuta pruebas deterministas con LLM guionado y smoke reducido si no introduce costo/inestabilidad; semanalmente corre golden set con LLM real y abre alerta/issue si hay regresión; antes de release corre golden set completo y `success_rate < 80%` bloquea el release. |
| RNF-003 | Fundamentación | Integridad de cifras del 100% — coherente con Constitución Art. I y RF-208: cobertura de claims = 100% (toda cifra presentada tiene claim), claims reproducibles = 100% (procedencia, operandos existentes, fórmula reproducible, valor bruto coincidente, redondeo correcto, texto igual a `display_value`), cifras huérfanas permitidas = 0. Una respuesta que incumpla se bloquea en runtime (re-síntesis o `failed`), no se entrega degradada. | Batería RF-601 (verificación de claims, pruebas.md §4.2) + bloqueo en runtime (T-403). |
| RNF-004 | Recuperación | Recall@10 ≥ 85% sobre el golden set de pares pregunta↔dataset esperado. | Batería RF-601. |
| RNF-005 | Honestidad | 0 cifras fabricadas en las respuestas "sin evidencia" del golden set negativo. | Batería RF-601 (casos negativos). |
| RNF-006 | Disponibilidad | Servicio disponible ≥ 99% mensual medido en el endpoint de salud. | Monitor externo de uptime. |
| RNF-007 | Accesibilidad | WCAG 2.2 nivel AA: contraste ≥ 4.5:1, navegación por teclado completa, foco visible, reflujo a 320 px. Las auditorías automatizadas (Lighthouse/axe ≥ 95, cero errores críticos) son puerta de calidad parcial: NO demuestran conformidad por sí solas. | Auditoría automatizada en CI + revisión manual obligatoria según pruebas.md §5. |
| RNF-008 | Claridad UX | Los pasos del agente visibles ≤ 2 s después de iniciada la investigación; primer feedback visual ≤ 500 ms tras el clic. | Prueba E2E instrumentada. |
| RNF-009 | Costo | Costo de LLM ≤ USD 0,05 promedio por investigación completa con la configuración por defecto. | Métricas de RF-703. |
| RNF-010 | Escala del índice | El índice cubre ≥ 90% de los datasets tabulares con API activa del catálogo; búsqueda semántica responde ≤ 1 s p95. | Reporte de ingesta + métricas. |
| RNF-011 | Seguridad | 0 credenciales **de proveedor** (API keys de LLM/Socrata/DB) en el cliente; 100% de consultas SoQL validadas contra lista blanca de lectura; sanitización de input verificada por pruebas; 100% de accesos a corridas persistidas autenticados con token de corrida (RF-801 — único secreto que el cliente maneja: por corrida, de alcance mínimo y expirable); 0 tokens en URLs o logs. | Pruebas de seguridad en `pruebas.md` §6. |
| RNF-012 | Idioma | Toda la interfaz y mensajes del agente en español. | Revisión manual. |

## 6. Fuera de alcance (v2.0)

- Autenticación completa de usuarios (cuentas, roles) y colaboración multiusuario en un mismo documento. El acceso a corridas persistidas SÍ se protege, pero mediante token por corrida (RF-801), no mediante identidad de usuario.
- Edición o publicación de datasets en datos.gov.co (solo lectura).
- Fuentes de datos distintas de datos.gov.co (otras APIs estatales quedan para v2.x).
- Análisis estadístico avanzado (regresiones, proyecciones) generado por el agente: v2.0 entrega datos descriptivos y agregaciones.
- Aplicación móvil nativa (la web debe ser responsive, pero no hay app).
- Los componentes de investigación social (entrevistas OE1, validación aplicada OE4) son actividades del proyecto de maestría, no funcionalidades del software.

## 7. Supuestos y dependencias

- **SUP-01:** datos.gov.co mantiene su API Socrata (SODA 2.1) y su API de descubrimiento de metadatos públicamente accesibles con app token gratuito.
- **SUP-02:** los límites de tarifas del proveedor LLM por defecto soportan el uso del piloto (≤ 500 investigaciones/mes estimadas en fase de validación).
- **SUP-03:** el catálogo contiene metadatos suficientes (título + descripción) para búsqueda semántica útil en la mayoría de los datasets; la heterogeneidad de calidad de metadatos se mitiga en el preprocesamiento (plan.md §5).
- **DEP-01:** PostgreSQL 15+ con extensión `pgvector`, local (`compose.yaml`) o gestionado (ver tasks.md, Fase 0). El servicio gestionado solo es necesario para el despliegue.
- **DEP-02:** API keys de los proveedores LLM elegidos (ver tasks.md, Fase 0).

## 8. Glosario

- **SoQL:** dialecto SQL de solo lectura de la API Socrata (SODA).
- **DIVIPOLA:** codificación oficial DANE de departamentos y municipios de Colombia.
- **Groundedness (fundamentación):** grado en que las afirmaciones cuantitativas de la respuesta tienen un claim trazable y reproducible que las respalda (no basta la coincidencia literal de cifras).
- **Afirmación cuantitativa (claim):** registro estructurado que vincula una cifra presentada con sus filas de origen, columnas, fórmula, valor bruto, unidad y regla de redondeo (RF-208).
- **Golden set (conjunto dorado):** colección versionada de preguntas con respuesta/dataset esperado, usada para evaluar el agente.
- **Evidencia:** resultado de datos validado + narrativa citable + metadatos de trazabilidad.
