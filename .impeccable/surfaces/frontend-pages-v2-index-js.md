---
version: 1
slug: "frontend-pages-v2-index-js"
primary_target: "frontend/pages/app.js"
related_targets: []
---

## Alcance y modo

Ruta objetivo: `frontend/pages/v2/index.js` — el lienzo de políticas con
copiloto lateral, **aún no implementado como aplicación funcional**. Modo:
**Operate**. Este brief cubre la superficie completa lienzo+copiloto;
DESIGN.md fija el mundo visual (Pulso por lo Público), este documento fija
cómo se estructura *esta* superficie dentro de ese mundo.

F1-01 (2026-07-27) implementó el sistema de tokens, los fundamentos
globales accesibles y la biblioteca de primitivas
(`frontend/components/ui/`) que este documento y DESIGN.md ya describen
como código real. F1-01 **no** implementó `frontend/pages/v2/index.js`, el
lienzo, el copiloto funcional, `CopilotPanel`, `RunTimeline`,
`EvidenceCard`, ni ninguna conexión a SSE/REST/reducer — eso pertenece a un
incremento funcional posterior, todavía sin autorizar.

## Audiencia, tarea, acción, prueba

- **Audiencia primaria:** funcionario formulador municipal/departamental,
  ofimática básica, sin SQL ni APIs.
- **Audiencia secundaria:** analista ciudadano (veedor, periodista de
  datos), puede leer tablas.
- **Tarea:** redactar o auditar un documento de política pública insertando
  evidencia cuantitativa trazable desde datos.gov.co.
- **Acción principal:** disparar una investigación desde una sección del
  documento (o pregunta libre) y, al terminar, insertar la evidencia
  resultante con su cita completa en el documento.
- **Prueba real disponible:** corridas deterministas reales capturadas en
  `frontend/tests/fixtures/` (stream SSE de 10 eventos sobre deserción
  escolar en Antioquia, dataset `ji8i-4anb`; casos completado / sin
  evidencia / interrumpido / fallido). No hay evidencia de producto/uso
  real todavía (confirmado en PRODUCT.md) — las composiciones usan datos
  técnicos reales, nunca testimonios o métricas de adopción inventadas.

## Restricciones duras (no negociables en este incremento)

- Paleta azul monocromática, tipografía única, iconografía Lucide, 3 zonas
  (nav superior / lienzo central / copiloto lateral colapsable) — fijadas
  por `constitution.md` Art. V y `plan.md` §7.
- WCAG 2.2 AA: contraste ≥4.5:1, teclado completo, foco visible, reflujo
  sin scroll horizontal a 320 px.
- Sin burbujas de chat, sin gamificación, sin grid de dashboard genérico,
  sin estética futurista/neón/glass/IA mágica, sin rigidez burocrática.
- Ningún dato, cifra o testimonio fabricado en las composiciones; solo
  contenido derivado de los fixtures reales listados arriba.
- El agente nunca "calcula" en la UI — cada cifra se presenta como claim
  trazable con su cadena dataset→entidad→consulta→validación.

## Dirección elegida y momento memorable

Investigación como ruta verificable dentro de una sala de seguimiento de
políticas, no como conversación. El momento que debe recordarse: el
usuario puede señalar cualquier cifra en el documento y trazarla, paso a
paso, hasta el dato crudo de datos.gov.co — sin que la interfaz reclame
atención mientras tanto (calma en reposo).

## Composición aprobada — Variante A: Ruta central

Aprobada explícitamente por Juan Camilo Grajales B. (2026-07-27) entre las
3 composiciones de DESIGN-01
(`docs/frontend-v2/design/design-01/variant-a-ruta-central.html`,
capturas en `docs/frontend-v2/design/design-01/screenshots/`).

**Patrón estructural a llevar a la implementación funcional de
`RunTimeline`** (incremento posterior, no F1-01): los pasos de la
investigación forman una ruta vertical continua con línea conectora dentro
del copiloto; cada paso es un punto de esa ruta (icono de verificación +
mensaje en español claro + tiempo transcurrido); la tarjeta de evidencia
final se funde como el último punto de la ruta — el destino, no un bloque
aparte. La ruta y la evidencia comparten un solo eje visual continuo de
arriba a abajo. F1-01 ya construyó las primitivas visuales que ese
componente usará (`Card`, `Badge`, tokens de espaciado/color), pero
`RunTimeline` en sí — con estado, datos en vivo y conexión al agente — no
existe todavía.

**Qué NO debe literalizarse del comp estático al construir `RunTimeline`:**
- El contenido (pregunta, 8 pasos concretos, cifra `3,9660000000000000`,
  dataset `ji8i-4anb`) es de una sola corrida real capturada, usada para
  probar la composición — no es un guion de copy fijo. El componente real
  debe generalizar a cualquier pregunta, cualquier cantidad de pasos
  (incluye reintentos/reparaciones de plan) y cualquier claim. La galería
  de F1-01 (`frontend/pages/_dev/ui.js`) reutiliza el mismo contenido real
  únicamente como muestra estática del sistema — tampoco es `RunTimeline`.
- Los tiempos "transcurridos" por paso se mostraron como texto estático;
  en la implementación funcional deben derivarse en vivo de los eventos
  SSE reales (no hay reloj fabricado). F1-01 no deriva ningún tiempo en
  vivo — solo muestra los valores `elapsed_ms` reales y fijos del fixture.
- El estado mostrado es el terminal `completed`; la implementación
  funcional debe definir cómo se ve la ruta en pasos intermedios (paso
  activo/pulsante) y en los otros estados terminales (`no_evidence`,
  `interrupted`, `failed`, `detached`) — el patrón de "punto por paso" debe
  extenderse a esos casos, no se decidió aún cómo.
- El borde de acento lateral (`border-left`) de la cita insertada en el
  lienzo fue retirado tras revisión del hook de diseño de Impeccable
  (patrón "side-tab", tell reconocible de UI genérica de IA); la versión
  vigente usa fondo tintado + subrayado — ese es el tratamiento a preservar,
  no el borde original de las primeras capturas.
- Radios de borde, pesos tipográficos y espaciado ya quedaron resueltos en
  F1-01 (ver DESIGN.md, sección Typography/Shapes/Layout) — no siguen
  pendientes.

## Decisiones sin resolver (para un incremento funcional posterior)

- Tratamiento de la ruta en estados no terminales/no-completados (ver
  arriba) — no cubierto por DESIGN-01 ni por F1-01, queda para el
  incremento funcional que implemente `RunTimeline` con datos en vivo.
