# ADR-0005 — Estructura de contenido de la plantilla "MGA" (RF-101)

## Estado

Aceptado (decisión de **estructura de contenido**). **Implementación pendiente** —
este ADR no autoriza por sí solo ningún cambio de código.

## Contexto y fuerzas en tensión

RF-101 exige, como mínimo, tres plantillas de lienzo: libre, MGA y plan de
desarrollo (ver también ADR-0004 para plan de desarrollo). La plantilla
legacy (`frontend/data/policyTemplates.js`, entrada `mga`: Identificación
del Problema, Análisis de Involucrados, Objetivo General, Alternativas de
Solución) fue auditada frente a la Metodología General Ajustada (MGA)
oficial del DNP. Resultado de la auditoría: **la plantilla legacy cubre
solo contenidos del módulo de Identificación** de la MGA — no constituye
una plantilla MGA completa y aprobada para v2. La MGA oficial tiene cuatro
módulos secuenciales:

| Módulo oficial | Contenido (fuente DNP) |
|---|---|
| 1. Identificación | Problema central (árbol de problemas/causas), participantes/población/zona afectada, árbol de objetivos, alternativas de solución |
| 2. Preparación | Capítulos aplicables según la tipología del proyecto: Necesidades, Análisis Técnico, Localización, Cadena de Valor, Riesgos, Ingresos y beneficios, Préstamos |
| 3. Evaluación (ex ante) | Indicadores de evaluación financiera/económica/social, decisión de la alternativa |
| 4. Programación | Productos, indicadores de producto y gestión, metas, fuentes de financiación y resumen del proyecto |

Fuentes: [Manual conceptual MGA, DNP](https://colaboracion.dnp.gov.co/CDT/MGA/Tutoriales%20de%20funcionamiento/Manual%20conceptual.pdf) ·
[Formulación e identificación, DNP](https://mgaayuda.dnp.gov.co/Recursos/Formulacion_identificacion.pdf) ·
[Instructivo Cadena de Valor, DNP](https://antioquia.gov.co/images/PDF2/Planeacion/BancoProyectos/InstructivosMGAWEB/Instructivo%20Cap%C3%ADtulo%20Cadena%20de%20valor.pdf) ·
[DNP — presentación comparativa de metodologías vigentes](https://colaboracion.dnp.gov.co/CDT/Inversiones%20y%20finanzas%20pblicas/Pres_comparac_metodologias_vigentes_ajustada.pdf).

En tensión: los módulos de Preparación, Evaluación ex ante y Programación
piden datos técnicos, financieros y de ingeniería interna de la entidad,
que rara vez están disponibles como datasets abiertos consultables en
datos.gov.co; el módulo de Identificación (población afectada, indicadores
de línea base) sí encaja naturalmente con la evidencia que el agente puede
aportar (RF-104).

## Decisión

Se aprueba una estructura **plana de siete secciones** (sin subsecciones ni
jerarquía; cabe en `DOCUMENT_MODEL_VERSION = 1` tal como existe hoy):

| # | `sectionId` propuesto | Título | Descripción/placeholder aprobado |
|---|---|---|---|
| 1 | `problematica` | Problemática | "Describe el problema central, sus causas, efectos y la situación que se busca transformar." |
| 2 | `participantes_poblacion_localizacion` | Participantes, población y localización | "Identifica los actores involucrados, la población afectada y objetivo, y la localización del proyecto." |
| 3 | `objetivos` | Objetivos | "Define el objetivo general y los objetivos específicos relacionados con las causas del problema." |
| 4 | `alternativas` | Alternativas de solución | "Formula y compara las alternativas consideradas para alcanzar los objetivos." |
| 5 | `preparacion` | Preparación | "Desarrolla las necesidades, análisis técnico, localización, cadena de valor, costos, riesgos, ingresos y beneficios aplicables." |
| 6 | `evaluacion_ex_ante` | Evaluación ex ante | "Presenta el flujo de caja, los indicadores de evaluación financiera, económica o social aplicables y la justificación de la alternativa seleccionada." |
| 7 | `programacion` | Programación | "Define productos, indicadores de producto y gestión, metas, fuentes de verificación, supuestos y fuentes de financiación." |

Reglas explícitas de la decisión:

- **Secciones 1–4** corresponden al módulo oficial de Identificación, con
  mayor granularidad que la agrupación legacy pero manteniendo el mismo
  contenido reconocible (problema, participantes/población/localización,
  objetivos, alternativas).
- **Secciones 5–7** (Preparación, Evaluación ex ante, Programación) no
  existían en la plantilla legacy; se añaden para cubrir los otros tres
  módulos oficiales de la MGA, cada una como una sola sección agregada —
  no se desagregan aquí los capítulos internos de cada módulo (p. ej. los
  capítulos aplicables de Preparación, según la tipología del proyecto,
  quedan dentro de una sola sección).
- **Los aportes presupuestales, técnicos o internos de la entidad** (costos,
  cronogramas, fuentes de financiación, indicadores de gestión) **pueden
  incorporarse como aporte manual** (T-506) y **nunca deben presentarse
  como evidencia verificada por el agente**: el agente no tiene forma de
  verificar cifras de ingeniería o presupuesto interno contra datos.gov.co.
- **Las siete secciones comienzan vacías** (`content` = documento
  ProseMirror vacío): las descripciones de la tabla anterior son las únicas
  que se fijan en este ADR; no se redacta contenido de proyecto, ejemplos
  de alternativas, indicadores ni cifras.
- **No se requiere jerarquía ni una nueva versión del esquema de documento**
  para estas siete secciones planas.

## Consecuencias

**Positivas**

- Cubre los cuatro módulos oficiales de la MGA, corrigiendo el vacío
  detectado en la auditoría de la plantilla legacy (que cubría solo
  contenidos del módulo de Identificación).
- Mantiene contenido reconocible para quien ya usó el legacy (secciones 1–4
  son una versión más granular y con nombres más cercanos al vocabulario
  oficial del DNP de las 4 secciones legacy).
- No exige ningún cambio de esquema.

**Negativas**

- Siete secciones es más ambicioso que las cuatro del legacy; Preparación,
  Evaluación ex ante y Programación quedarán mayormente dependientes de
  aporte manual, con menor densidad de evidencia verificada por el agente
  que las secciones de Identificación.
- Cada uno de los tres módulos añadidos se representa como una sola sección
  agregada pese a tener múltiples capítulos oficiales internos (p. ej.
  Preparación agrupa varios capítulos aplicables según la tipología del
  proyecto, conforme al manual del DNP) — mismo tipo de riesgo ya aceptado
  en la Alternativa A de ADR-0004 (bloque de editor enriquecido extenso y
  menos guiado).

## Alternativas consideradas

- **Alternativa A — los 4 módulos oficiales, una sección por módulo (4
  secciones)**: descartada por agrupar demasiado el módulo de
  Identificación en una sola sección.
- **Alternativa C — "MGA — Identificación" (4 secciones, alcance reducido
  explícito, sin Preparación/Evaluación/Programación)**: descartada — no
  cubriría los cuatro módulos exigidos por la metodología oficial y dejaría
  sin resolver si una MGA parcial satisface RF-101.
- **Reutilizar la plantilla legacy sin cambios**: descartada por la
  auditoría — cubre solo contenidos del módulo de Identificación, no una
  MGA completa.

## Requisitos, contratos y fases afectados

RF-101. No modifica `contracts/api-rest.md` ni ningún contrato de backend.
Fase F5 (`implementation-plan.md`).

**Condición explícita de cierre de RF-101 (no se declara cumplido con este
ADR):** RF-101 exige tres plantillas — libre, MGA y plan de desarrollo. Este
ADR resuelve el contenido de una sola (MGA). RF-101 no debe declararse
satisfecho hasta que las **tres** plantillas —libre, MGA (este ADR) y plan
de desarrollo (ADR-0004)— estén **implementadas y verificadas**.

## Evidencia y fecha de aprobación humana

Aprobado por Juan Camilo Grajales B. el 2026-07-30, en respuesta directa a
la auditoría de la plantilla MGA legacy frente a la MGA oficial del DNP
presentada por el agente. Aprobación textual recibida:

> "Apruebo para la plantilla MGA una estructura plana de siete secciones:
> Problemática, Participantes/población y localización, Objetivos,
> Alternativas de solución, Preparación, Evaluación ex ante, Programación"
> — con las siete descripciones reproducidas literalmente en la tabla de la
> sección "Decisión" de este ADR.

**Implementación:** ninguna todavía. No se ha tocado
`frontend/lib/document/documentModel.js`, `frontend/data/policyTemplates.js`
ni ningún otro archivo de código como parte de esta decisión. El incremento
de código que declare `templateId` para esta plantilla, cablee las siete
secciones y añada las pruebas correspondientes queda pendiente de un
encargo separado.

## Sucesor

Ninguno todavía. El incremento de código que implemente las tres plantillas
de RF-101 (libre, MGA — este ADR, plan de desarrollo — ADR-0004) juntas
queda pendiente de un encargo separado.
