# Constitución del Proyecto — Cuestión de Datos

**Versión:** 1.2.0 · **Ratificada:** 2026-07-06 · **Última enmienda:** 2026-07-06 (revisión documental focalizada de backend: `research.md` incorporado a la jerarquía normativa, Art. IV.2 alineado con puertas RNF-002 por PR/semanal/release, y obligación de configuración completa antes de implementar backend)

Este documento define los principios que **ninguna funcionalidad, refactor ni decisión técnica puede violar**. Aplica a todo el código del repositorio (frontend, backend, scripts de datos, pruebas y documentación) y a todo agente de IA o humano que contribuya.

---

## Artículo I — Evidencia verificable o nada

1. **Prohibido inventar cifras.** Ningún dato cuantitativo mostrado al usuario puede provenir del conocimiento paramétrico del LLM. Toda cifra debe originarse en una consulta real ejecutada contra las APIs de datos.gov.co (u otra fuente oficial declarada en `plan.md`).
2. **Trazabilidad completa obligatoria.** Toda evidencia insertada en un documento debe llevar adjuntos, como mínimo: `dataset_id`, nombre del dataset, entidad publicadora, consulta SoQL ejecutada, fecha/hora de ejecución y URL de la fuente. Si falta alguno de estos campos, la evidencia **no se inserta**.
3. **Si el agente no encuentra datos, lo dice.** La respuesta "no encontré evidencia suficiente en el catálogo" es un resultado válido y preferible a una respuesta especulativa. Está prohibido rellenar vacíos con estimaciones del modelo.
4. **La capa de validación de calidad no es opcional.** Ningún resultado llega al usuario sin pasar por la validación formal (esquema, completitud, temporalidad, trazabilidad) definida en `contracts/validacion-calidad.md`.

## Artículo II — Código abierto y reproducibilidad

1. El proyecto se publica bajo licencia libre (MIT). Ninguna dependencia de runtime puede exigir licencias privativas o pagos obligatorios para ejecutar la funcionalidad esencial.
2. Todos los **componentes propios del proyecto** (frontend, backend, base de datos, scripts) DEBEN poder ejecutarse localmente con instrucciones documentadas en `quickstart.md`. PostgreSQL no requiere proveedor gestionado: se provee localmente mediante contenedores (`compose.yaml` en la raíz del repositorio); Supabase, Neon, Railway y similares son opciones de despliegue, no requisitos de desarrollo. Las fuentes de datos externas (datos.gov.co/Socrata) y los proveedores de modelos declarados en `plan.md` continúan siendo dependencias remotas inevitables. Un tercero con las API keys adecuadas debe poder reproducir el sistema completo sin contacto con el autor.
3. Los experimentos de evaluación (OE3 de la propuesta) deben ser reproducibles: datasets de evaluación, semillas, versiones de modelos y resultados se versionan en el repositorio.
4. Los secretos (API keys, cadenas de conexión) **jamás** se commitean. Viven en variables de entorno y existe un `.env.example` actualizado por cada servicio.

## Artículo III — Simplicidad primero (YAGNI)

1. No se agrega infraestructura para necesidades hipotéticas. Cada dependencia, servicio o abstracción nueva debe justificarse contra un requisito con ID (`RF-###` / `RNF-###`) de `spec.md`.
2. Se prefiere la solución estándar de la industria sobre la solución novedosa: LangGraph antes que un orquestador propio, pgvector antes que una base vectorial exótica, FastAPI antes que un framework propio.
3. Máximo dos servicios desplegados (frontend y backend de agente) más la base de datos gestionada. Ampliar esto requiere enmienda constitucional.

## Artículo IV — Calidad verificada por pruebas

1. **Toda lógica de negocio del backend tiene pruebas.** Los módulos de validación de calidad, construcción de SoQL, herramientas del agente y endpoints REST no se consideran terminados sin pruebas automatizadas (ver `pruebas.md`).
2. Las pruebas de comportamiento del agente se verifican en tres niveles compatibles con RNF-002: (a) cada PR ejecuta pruebas deterministas con LLM guionado y un smoke reducido sin costo ni inestabilidad excesiva, y estas pruebas sí bloquean el merge; (b) semanalmente se ejecuta el conjunto dorado con LLM real y se abre alerta o issue ante regresión; (c) antes de cada release se ejecuta el conjunto dorado completo con LLM real y una tasa de éxito inferior al umbral definido en `spec.md` bloquea el release. Esta enmienda reemplaza la regla anterior que hacía depender todo merge de la batería completa con LLM real, porque no era viable ni estable para cada PR.
3. CI obligatorio: lint + pruebas unitarias + pruebas de contrato se ejecutan en cada PR. Un PR con CI en rojo no se mergea.
4. Los errores de las APIs externas (Socrata, LLM) se manejan explícitamente: timeout, reintento acotado y mensaje de error claro al usuario. Nunca un `500` sin contexto.

## Artículo V — Experiencia de usuario: minimalista, clara y en azules

1. **Paleta monocromática azul.** Toda la interfaz usa exclusivamente la escala de azules definida en `plan.md` (§ Diseño visual), con neutros (blanco, grises fríos) para fondos y texto. Colores fuera de la paleta solo se permiten para estados semánticos (error, advertencia, éxito) definidos como *tokens* en el mismo documento.
2. **Minimalismo funcional.** Cada pantalla tiene un propósito dominante. Se prohíben elementos decorativos que no comuniquen información (carruseles, animaciones no funcionales, degradados llamativos).
3. **Accesibilidad WCAG 2.2 nivel AA** como mínimo: contraste ≥ 4.5:1 en texto normal, navegación completa por teclado, textos alternativos y estados de foco visibles. Las herramientas automáticas (Lighthouse, axe) son puertas de calidad parciales; la conformidad se verifica además con revisión manual (pruebas.md §5).
4. **El usuario siempre sabe qué hace el agente.** Las acciones, fuentes, consultas y validaciones observables (búsqueda en catálogo, consulta ejecutada, validación de calidad) se muestran en la interfaz en lenguaje claro, nunca como caja negra. No se presenta el "razonamiento interno" del modelo, sino sus acciones verificables.
5. Público objetivo primario: funcionarios municipales **sin formación técnica**. Toda etiqueta, mensaje de error y texto de ayuda se escribe en español claro, sin jerga técnica sin explicar.

## Artículo VI — Seguridad y datos personales

1. El sistema consulta únicamente **datos abiertos y anonimizados**. Está prohibido incorporar fuentes con datos personales identificables o construir funcionalidades de reidentificación.
2. Las API keys de proveedores (LLM, Socrata, base de datos) operan exclusivamente del lado del servidor; el navegador nunca las recibe ni almacena. Única excepción permitida: el `run_access_token` por corrida (spec.md RF-801), un secreto de alcance mínimo, expirable y revocable por borrado, que el cliente necesita para acceder a sus propias corridas.
3. Todo input del usuario que participe en la construcción de consultas SoQL se sanitiza; las consultas generadas por el LLM se validan contra una lista blanca de operaciones de solo lectura (`SELECT`). Cualquier otra operación se rechaza.
4. Los documentos de política redactados por los usuarios son de su propiedad; si se persisten en servidor, debe existir mecanismo de borrado y no se usan para entrenar modelos.

## Artículo VII — Observabilidad y honestidad técnica

1. Cada ejecución del agente genera una traza estructurada (pasos, herramientas invocadas, latencias, tokens, errores) persistida según `data-model.md`. Estas trazas alimentan la evaluación técnica (OE3).
2. Los logs no contienen secretos ni contenido completo de documentos de usuarios.
3. Las métricas comprometidas en `spec.md` (§ Requisitos no funcionales) se miden de verdad, con instrumentación real, no se estiman.

---

## Gobernanza

- **Jerarquía normativa:** constitution.md > spec.md > research.md > plan.md > contracts/ > data-model.md > pruebas.md > tasks.md > quickstart.md > código.
- **Enmiendas:** cualquier cambio a esta constitución requiere (a) justificación escrita en el PR, (b) incremento de versión semántica del documento, y (c) revisión de impacto sobre spec.md y plan.md en el mismo PR.
- **Verificación de cumplimiento:** todo PR debe declarar en su descripción qué artículos constitucionales toca. El revisor (humano o agente) verifica el cumplimiento antes de aprobar.
- **Conflictos:** ante ambigüedad entre documentos, gana el de mayor jerarquía; ante ambigüedad dentro de un documento, se pregunta al responsable del proyecto (Juan Camilo Grajales) antes de asumir.
