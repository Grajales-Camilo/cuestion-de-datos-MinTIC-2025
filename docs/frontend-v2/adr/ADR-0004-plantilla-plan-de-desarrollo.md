# ADR-0004 — Estructura de contenido de la plantilla "Plan de desarrollo" (D-6)

## Estado

Aceptado (decisión de **estructura de contenido**). **Implementación pendiente** —
este ADR no autoriza por sí solo ningún cambio de código.

## Contexto y fuerzas en tensión

RF-101 exige, como mínimo, tres plantillas de lienzo: libre, MGA y plan de
desarrollo. Hoy (`frontend/lib/document/documentModel.js`) solo existe la
plantilla libre; el validador rechaza explícitamente cualquier otro
`templateId`. La plantilla "plan de desarrollo" es contenido de dominio de
política pública — qué secciones debe tener un plan de desarrollo
territorial colombiano — y por tanto no es una decisión que el agente deba
tomar ni fabricar por su cuenta (mismo caso que T-601, según
`implementation-plan.md` §17, decisión D-6).

En tensión: seguir el mínimo legal estricto (Ley 152 de 1994, art. 31, que
exige explícitamente **parte estratégica** y **plan de inversiones** de
mediano y corto plazo) da una estructura simple pero agrupa demasiado en
cada una; seguir la granularidad operativa del Kit de Planeación Territorial
del DNP da una estructura más guiada pero más extensa (hasta 6 secciones) y
con riesgo de incluir componentes (armonización con POT/PBOT/ODS) que no
siempre aplican. Un diagnóstico previo no es un tercer componente literal
del artículo 31, pero sí es práctica metodológica aprobada por el DNP para
sustentar la parte estratégica con evidencia; se incorpora como decisión
metodológica de este ADR, no como cita textual de la ley.

## Decisión

Se aprueba una estructura **híbrida de cinco secciones planas** (sin
subsecciones ni jerarquía; cabe en `DOCUMENT_MODEL_VERSION = 1` tal como
existe hoy):

| # | `sectionId` propuesto | Título | Descripción/placeholder aprobado |
|---|---|---|---|
| 1 | `diagnostico` | Diagnóstico | "Describe la situación actual, las problemáticas, brechas y líneas base que sustentan el plan." |
| 2 | `vision_articulacion` | Visión y articulación estratégica | "Define la visión de desarrollo, el objetivo general y su articulación con los instrumentos de planeación aplicables." |
| 3 | `programas_metas` | Programas, indicadores y metas | "Formula las líneas estratégicas, programas, objetivos específicos, indicadores de resultado y producto, y sus metas." |
| 4 | `ppi` | Plan plurianual de inversiones (PPI) | "Relaciona los programas con sus fuentes de financiación, recursos estimados y vigencias." |
| 5 | `seguimiento_evaluacion` | Seguimiento y evaluación | "Define los indicadores, responsables, periodicidad y mecanismos para revisar el avance y los resultados." |

Reglas explícitas de la decisión:

- **El PPI permanece incluido** por ser parte del contenido legal del plan
  (Ley 152/1994), aunque algunos de sus datos deban incorporarse como
  aportes manuales (T-506) en vez de evidencia verificada por el agente,
  cuando no existan en datasets abiertos consultables.
- **La articulación con instrumentos superiores se integra dentro de la
  sección 2** ("Visión y articulación estratégica"), no como sección propia.
  **No se afirma que POT/PBOT u ODS sean obligatorios en todos los casos** —
  la descripción de la sección los deja como articulación "aplicable", sin
  forzar su mención cuando no corresponda.
- **Lenguaje:** claro (RNF-012), acompañado de la terminología técnica del
  DNP cuando corresponde (p. ej. "PPI"), no sustituido por ella.
- **Las cinco secciones comienzan vacías** (`content` = documento ProseMirror
  vacío, igual que `createFreeTemplateDocument()`): las descripciones de la
  tabla anterior son las únicas que se fijan en este ADR; no se redacta
  contenido de política pública, ejemplos de programas, metas ni cifras.
- **No se requiere jerarquía ni una nueva versión del esquema de documento**
  para estas cinco secciones planas — encajan en
  `DOCUMENT_MODEL_VERSION = 1` sin cambios de forma.

## Consecuencias

**Positivas**

- Cubre el mínimo legal (Ley 152/1994) y la granularidad operativa del Kit
  de Planeación Territorial sin duplicar ninguna de las dos alternativas
  originalmente presentadas al pie de la letra — es una síntesis deliberada,
  no una tercera fuente inventada.
- No exige ningún cambio de esquema (`documentModel.js` sigue siendo plano),
  lo que reduce el riesgo técnico del futuro incremento de código.
- El PPI y "Seguimiento y evaluación", aunque no siempre alimentables con
  evidencia de datos.gov.co, quedan explícitamente dentro de alcance con
  la salvedad ya resuelta (aporte manual, T-506) en vez de quedar como una
  decisión abierta adicional.

**Negativas**

- Cinco secciones fijas no cubren cada variación municipal/departamental
  real (algunos planes usan más líneas estratégicas o capítulos adicionales
  por ley/ordenanza local); esta plantilla es un mínimo utilizable, no un
  generador exhaustivo de todo plan de desarrollo posible.
- El PPI puede quedar con secciones parcialmente vacías o solo con aportes
  manuales cuando el agente no encuentre evidencia presupuestal en el
  catálogo — riesgo de calidad percibida más bajo que en "Diagnóstico",
  donde la evidencia de datos.gov.co es más abundante.

## Alternativas consideradas

- **Alternativa A — mínimo legal (3 secciones: Diagnóstico, Parte
  estratégica, Plan de inversiones)**, basada en los dos componentes que
  Ley 152/1994 art. 31 exige literalmente (parte estratégica y plan de
  inversiones), con el diagnóstico añadido como decisión metodológica
  previa, no como tercer componente del artículo: descartada por agrupar
  demasiado la parte estratégica en un solo bloque de editor enriquecido,
  poco guiado para un funcionario sin experiencia previa (ACT-01, `spec.md`).
- **Alternativa B — operativa DNP (6 secciones)**, siguiendo el Kit de
  Planeación Territorial con "Armonización" y "Programas y metas" como
  secciones separadas de "Visión y objetivos": descartada tal cual — se
  adoptó una síntesis (la decisión aprobada) que fusiona armonización dentro
  de la sección 2 en vez de dejarla independiente.
- **Reutilizar sin auditar la plantilla legacy** (`frontend/data/policyTemplates.js`,
  que no tiene una entrada de "plan de desarrollo" en absoluto, solo
  MGA/CONPES/Policy Brief): no aplica a esta decisión — no existía contenido
  legacy de "plan de desarrollo" que reutilizar.

## Requisitos, contratos y fases afectados

RF-101. No modifica `contracts/api-rest.md` ni ningún contrato de backend —
es una decisión exclusivamente de estructura documental del frontend. Fase
F5 (`implementation-plan.md`).

**Condición explícita de cierre de RF-101 (no se declara cumplido con este
ADR):** RF-101 exige tres plantillas — libre, MGA y plan de desarrollo. Este
ADR resuelve el contenido de una sola (plan de desarrollo). RF-101 no debe
declararse satisfecho hasta que las **tres** plantillas —libre, MGA y plan
de desarrollo— estén **implementadas y verificadas**. La plantilla MGA para
v2 se audita y propone por separado (documento aparte, no incluido en este
ADR); no se reutiliza automáticamente el contenido legacy de MGA sin esa
auditoría.

## Evidencia y fecha de aprobación humana

Aprobado por Juan Camilo Grajales B. el 2026-07-30, en respuesta directa a
la propuesta de estructura presentada por el agente (dos alternativas,
sin contenido fabricado) para la decisión abierta D-6 registrada en
`implementation-plan.md` §17. Aprobación textual recibida:

> "Apruebo D-6 con una estructura híbrida de cinco secciones planas: (1)
> Diagnóstico, (2) Visión y articulación estratégica, (3) Programas,
> indicadores y metas, (4) Plan plurianual de inversiones (PPI), (5)
> Seguimiento y evaluación" — con los cinco puntos de decisión reproducidos
> en la sección "Decisión" de este ADR.

**Implementación:** ninguna todavía. No se ha tocado
`frontend/lib/document/documentModel.js` ni ningún otro archivo de código
como parte de esta decisión. El incremento de código que declare
`templateId` para esta plantilla, cablee las cinco secciones y añada las
pruebas correspondientes queda pendiente de un encargo separado, posterior
a la auditoría de la plantilla MGA.

## Sucesor

Pendiente: la auditoría y propuesta de estructura de la plantilla MGA para
v2 (documento aparte) precede al incremento de código que implemente las
tres plantillas de RF-101 (libre, MGA, plan de desarrollo) juntas.
