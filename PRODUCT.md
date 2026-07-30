# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

**Funcionario formulador** (usuario primario): servidor público municipal o
departamental colombiano que redacta propuestas de política pública,
proyectos MGA o planes de desarrollo. Nivel técnico: ofimática básica, sin
conocimientos de SQL ni APIs.

**Analista ciudadano**: veedor, periodista de datos o líder social que audita
afirmaciones gubernamentales con datos abiertos. Nivel técnico: ofimática,
puede leer tablas.

Ambos perfiles están confirmados por `specs/001-cuestion-de-datos-v2/spec.md`
§2 (ACT-01, ACT-02). Existen además actores de sistema/operación
(investigador evaluador, administrador) que usan superficies distintas al
lienzo/copiloto del usuario final y no condicionan el diseño visual de F1+.

## Product Purpose

Permitir que actores gubernamentales subnacionales y organizaciones de la
sociedad civil en Colombia, sin conocimientos de programación, encuentren,
consulten, validen e integren evidencia cuantitativa proveniente del catálogo
de datos abiertos del Estado (datos.gov.co, más de 8.000 datasets) dentro de
documentos de política pública, mediante un asistente de IA que razona en
múltiples pasos y reporta la calidad y trazabilidad de cada dato entregado.

## Positioning

El mecanismo que un producto vecino (un chatbot genérico o un buscador de
datos abiertos crudo) no podría copiar honestamente: el sistema nunca
responde con una cifra sin evidencia trazable y verificable (dataset,
entidad, consulta ejecutada, fecha, URL) y, cuando no encuentra evidencia
elegible, lo dice explícitamente en vez de responder con una estimación.
Confirmado explícitamente por Juan Camilo Grajales B. (2026-07-27), con base
en `specs/constitution.md` Art. I y `spec.md` RF-205/RF-208.

## Operating Context

- **Lienzo de políticas** (Policy Canvas): editor de texto enriquecido por
  secciones, con plantillas del ciclo de política pública colombiano (mínimo:
  libre, MGA, plan de desarrollo).
- **Copiloto lateral**: el usuario dispara una investigación desde una
  sección del documento o hace una pregunta libre; ve los pasos del agente en
  tiempo real en lenguaje claro, con detalle técnico expandible.
- **Inserción de evidencia**: tablas, narrativa citable y botón para insertar
  en el documento con su cita completa (dataset, entidad, consulta, fecha).
- **Autoguardado y exportación**: el documento se autoguarda en el
  dispositivo del usuario (≤5 s) y se exporta a un formato portable de
  ofimática con las citas intactas.
- **Consentimiento previo**: antes de la primera investigación, la interfaz
  informa qué se almacena, para qué y por cuánto tiempo, y cómo se borra.

## Capabilities and Constraints

- Agente multi-paso (razonar → herramienta → observar → decidir) sobre el
  catálogo completo de datos.gov.co vía búsqueda semántica, no una lista fija
  de datasets.
- Cada afirmación cuantitativa nace de un *claim* trazable (filas, columnas,
  fórmula, valor bruto, redondeo); ninguna cifra la "calcula" el LLM en texto
  libre.
- Capa de validación de calidad de 4 dimensiones (esquema, completitud,
  temporalidad, trazabilidad) antes de entregar cualquier evidencia.
- Sin cuentas de usuario: el acceso a una corrida persistida usa un token de
  alcance mínimo y expirable por corrida, nunca en URL.
- Interfaz y mensajes exclusivamente en español claro; los enums y detalles
  técnicos crudos solo pueden verse en un *disclosure* técnico expandible.
- El backend determinista (FastAPI) es el único modelo funcional y de
  aceptación; el frontend legacy (Next.js Pages Router actual) es solo
  andamiaje e inventario, nunca base de aceptación ni *fallback* funcional.
- **Decisión cerrada e implementada:** las estructuras de las plantillas
  "plan de desarrollo" y MGA fueron aprobadas con criterio humano en
  ADR-0004/ADR-0005 e implementadas junto con la plantilla libre. RF-101 está
  verificado mediante los commits `1ddc25f`/`199fa1e` y el CI
  `30543431200`.

## Brand Commitments

Nombre del producto: **Cuestión de Datos** (dominio existente
cuestiondedatos.com). No existe todavía guía de marca, logo formal ni tono de
voz documentado más allá del nombre; confirmado explícitamente por Juan
Camilo Grajales B. (2026-07-27) — no inventar identidad visual de marca más
allá de este hecho. Los tokens visuales normativos (paleta monocromática de
azules, tipografía única, iconografía Lucide) ya están fijados en
`specs/001-cuestion-de-datos-v2/plan.md` §7 y `constitution.md` Art. V; son
requisitos, no decisiones de marca abiertas.

## Evidence on Hand

**No hay evidencia de uso real todavía**, confirmado explícitamente por Juan
Camilo Grajales B. (2026-07-27): el piloto v2 está en desarrollo y no
desplegado; no existen testimonios, casos de éxito ni métricas de adopción de
usuarios reales. Existen sí corridas reales del backend determinista
(`backend/eval/reports/`, `frontend/tests/fixtures/`) usadas como evidencia
técnica de comportamiento del sistema, no como evidencia de producto/marketing.
Trabajo de diseño futuro **no debe fabricar** testimonios, casos de uso,
cifras de adopción o resultados de piloto que no existan.

## Product Principles

1. **Cero fabricación.** Ninguna cifra se presenta sin evidencia trazable; si
   no hay evidencia elegible, el sistema lo dice explícitamente en vez de
   estimar (Constitución Art. I).
2. **Transparencia del razonamiento.** El usuario ve en lenguaje claro qué
   hace el agente (búsqueda, consulta, validación); nunca una caja negra ni
   el "pensamiento interno" del modelo.
3. **Minimalismo funcional en azules.** Paleta monocromática de azules y
   neutros fríos; sin elementos decorativos que no comuniquen información
   (Constitución Art. V).
4. **Accesible para funcionarios sin formación técnica.** Español claro, sin
   jerga sin explicar, WCAG 2.2 AA como mínimo verificable.
5. **Utilidad proporcional, nunca a costa de la integridad.** Prioriza una
   respuesta útil y verificable sobre la consulta técnicamente perfecta, sin
   tolerar fabricación, fuente equivocada, contradicción material o pérdida
   de privacidad (Constitución Art. I.5).

## Accessibility & Inclusion

WCAG 2.2 nivel AA como mínimo: contraste ≥4.5:1 en texto normal, navegación
completa por teclado, foco visible, reflujo sin scroll horizontal a 320 px.
Las auditorías automatizadas (Lighthouse/axe) son una puerta parcial; la
conformidad se verifica además con revisión manual
(`specs/001-cuestion-de-datos-v2/pruebas.md` §5). Público primario sin
formación técnica: RNF-012 exige toda la interfaz en español claro.
