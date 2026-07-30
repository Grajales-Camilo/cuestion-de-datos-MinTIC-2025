# DESIGN-01 — Composiciones de "Pulso por lo Público"

Este directorio contiene las 3 composiciones estructurales de alta fidelidad
exigidas por el incremento DESIGN-01, antes de cualquier implementación de
F1. Son documentación visual: HTML/CSS/SVG estático, sin React, sin
Tailwind, sin dependencias — pensado para decidir con el usuario, no para
integrarse en el código de producción.

## Nota sobre hallazgos del hook de diseño de Impeccable (F1-R1)

Los 3 archivos HTML de este directorio son **anteriores** al sistema real
de tokens (`frontend/styles/tokens.css`, `DESIGN.md` con su escala
tipográfica definitiva) que F1-01 construyó después. El detector de
Impeccable, al comparar estos comps congelados contra la escala tipográfica
de `DESIGN.md` que hoy existe, marca decenas de `design-system-font-size` /
`design-system-color` porque los valores literales de estos 3 archivos no
coinciden con una escala que, cuando se escribieron, todavía no existía.

Esto es un hallazgo histórico esperado, no un defecto: la Variante A ya fue
aprobada por el usuario (2026-07-27) y estos archivos deben permanecer
intactos como registro de esa decisión — no se editan para hacerlos
coincidir retroactivamente con `DESIGN.md`. La única excepción persistida en
`.impeccable/config.json` para estos archivos es `single-font` (autorizada
explícitamente por el usuario en el incremento F1-01, porque la tipografía
única es un requisito normativo del proyecto, no una omisión de diseño). El
resto de los hallazgos de tipografía/color de estos 3 archivos **no** están
silenciados — `/impeccable audit` los seguirá mostrando, a propósito, para
no ocultar reglas futuras completas sobre archivos nuevos.

## Qué comparten las 3 variantes (no exploratorio)

- Layout de 3 zonas fijado por `plan.md` §7 / `constitution.md` Art. V:
  navegación mínima superior, lienzo central, copiloto lateral.
- Paleta azul monocromática y semánticos fijados (ver `DESIGN.md`).
- Tipografía única sans-serif del sistema, sin sombras duras ni degradados,
  sin glassmorphism.
- Exactamente el mismo contenido real: la pregunta, los 9 pasos, y la
  evidencia provienen de `frontend/tests/fixtures/completed-stream.sse.txt`
  (corrida real `e6ae9a62-3394-4eee-b9e4-c76a3adf9582`, dataset `ji8i-4anb`,
  Ministerio de Educación Nacional). El párrafo del lienzo cita el mismo
  `display_value` real (`3,9660000000000000`) devuelto por esa corrida — no
  se redondeó ni se inventó una cifra "más bonita".
- Cero burbujas de chat, cero gamificación, cero grid de dashboard
  genérico, cero estética futurista/neón/IA mágica.

## Qué varía (el objeto real de la decisión)

Cómo se organiza la investigación *dentro* del copiloto — la relación entre
la ruta de pasos y la evidencia final.

### Variante A — Ruta central
[`variant-a-ruta-central.html`](./variant-a-ruta-central.html) · [captura desktop](./screenshots/a-ruta-central-desktop.png) · [captura 320px](./screenshots/a-ruta-central-mobile-320.png)

Los 9 pasos son una **ruta vertical continua** con línea conectora: cada
paso es un punto de la ruta, y la tarjeta de evidencia es literalmente el
**destino final** de esa ruta, fundida como el último punto. La
investigación completa —desde "Preparando la investigación" hasta la
cifra verificada— se lee como un solo recorrido de arriba abajo.

### Variante B — Franja de seguimiento
[`variant-b-franja-seguimiento.html`](./variant-b-franja-seguimiento.html) · [captura desktop](./screenshots/b-franja-seguimiento-desktop.png) · [captura 320px](./screenshots/b-franja-seguimiento-mobile-320.png)

El estado de avance vive en una **franja horizontal compacta** (glanceable,
tipo barra segmentada) desacoplada de la bitácora detallada y de la tarjeta
de evidencia, que son bloques independientes debajo. Se puede saber "vamos
bien / ya terminó" de un vistazo a la franja sin leer la bitácora completa.

### Variante C — Trayectoria lateral
[`variant-c-trayectoria-lateral.html`](./variant-c-trayectoria-lateral.html) · [captura desktop](./screenshots/c-trayectoria-lateral-desktop.png) · [captura 320px](./screenshots/c-trayectoria-lateral-mobile-320.png)

Los pasos se reducen a un **riel de puntos periférico**, pegado al borde
izquierdo del copiloto, sin texto (wayfinding mínimo). El espacio liberado
se dedica por completo a un panel de contenido dominante: la evidencia
ocupa el protagonismo visual, no la ruta.

## Evaluación comparativa

| Criterio | A — Ruta central | B — Franja de seguimiento | C — Trayectoria lateral |
|---|---|---|---|
| **Progreso comprobable** | Alto: cada paso es visible y nombrado, nada se oculta. | Alto a nivel resumen (franja), medio en detalle (hay que leer la bitácora aparte). | Bajo en detalle: el riel no tiene texto; solo el último paso se describe. |
| **Cadena de confianza** (dataset→entidad→consulta→validación→cifra) | Alta: la cadena se recorre en el mismo eje que los pasos, sensación de continuidad causal. | Alta pero fragmentada en dos bloques (bitácora + evidencia). | Alta pero implícita: la trayectoria no explica la cadena, solo la tarjeta de evidencia la documenta. |
| **Recompensa útil** (la evidencia como destino, no accesorio) | Muy alta: la evidencia es literalmente el final de la ruta. | Alta: bloque propio, pero visualmente al mismo nivel que la bitácora. | Muy alta: la evidencia domina el espacio disponible. |
| **Lectura compartida** (funcionario sin formación técnica y analista) | Buena para ambos: la narrativa paso a paso no requiere inferencias. | Buena: la franja sirve al lector apurado, la bitácora al lector detallista — dos velocidades de lectura. | Requiere que el usuario confíe en el riel sin texto; el analista puede querer más detalle del proceso, no solo el resultado. |
| **Calma en reposo** | Media: 9 elementos de ruta compiten visualmente incluso en estado terminal. | Alta: la franja resuelta es un bloque corto y quieto; la bitácora es texto secundario de bajo contraste. | Muy alta: el riel es discreto (puntos de 10px), casi silencioso una vez completado. |
| **Cumplimiento de restricciones fijas** | Cumple. | Cumple. | Cumple. |
| **Accesibilidad / reflujo a 320 px** | Verificado sin overflow horizontal a 320 px (ver captura). `claim-valor` con `clamp()` + `overflow-wrap`. | Verificado sin overflow horizontal a 320 px. | Verificado sin overflow horizontal a 320 px; el valor pasa a 2 líneas por su tamaño mayor (28px→clamp), comportamiento esperado y legible. |
| **Escalabilidad a estados intermedios** (investigación en curso, sin evidencia, error) | Natural: un paso "activo" es simplemente el último punto de la ruta sin fusionar aún con la evidencia. | Natural: la franja ya está diseñada para mostrar progreso parcial (segmentos sin completar); el patrón visual no cambia en reposo vs. en curso. | Requiere criterio adicional: con la ruta reducida a puntos, "en curso" depende del texto de `paso-actual`, que hoy es la única señal textual del estado. |
| **Densidad / uso del espacio del copiloto** | Media-alta: la ruta consume la mayor parte de la altura. | Media: tres bloques (franja, bitácora, evidencia) compiten por espacio vertical. | Baja en el riel (40px fijos), alta en el panel de contenido — la más eficiente en dedicar espacio a lo que el usuario realmente necesita leer al final. |

## Lectura de conjunto

Ninguna variante es "más simple" que fabricar sombras o color nuevos: las
tres heredan exactamente el mismo mundo visual y el mismo contenido real;
difieren solo en cuánto protagonismo le dan al *proceso* frente al
*resultado*.

- **A** cuenta la historia completa — útil si "ver cómo se llegó a la
  cifra" es en sí mismo parte de la confianza que el producto quiere
  construir (Principio 2 de `PRODUCT.md`: transparencia del razonamiento).
- **B** separa la vigilancia rápida del detalle — útil si el usuario típico
  dispara varias investigaciones y quiere monitorear de reojo sin leer cada
  paso.
- **C** apuesta por la calma y el resultado — útil si la ansiedad de
  "quedarse mirando el proceso" es un riesgo real para un funcionario sin
  formación técnica, y lo que más importa es llegar rápido a una cifra
  verificable y accionable.

No hay una variante técnicamente incorrecta; la diferencia es de énfasis
de producto. Esta decisión queda para el usuario.

## Decisión

**Aprobada la Variante A — Ruta central**, por Juan Camilo Grajales B.
(2026-07-27). Queda registrada en
`.impeccable/surfaces/frontend-pages-v2-index-js.md`, incluyendo qué partes
del comp estático son ilustrativas (contenido de una sola corrida real,
tiempos estáticos) y no deben literalizarse al construir el componente
funcional `RunTimeline`.

DESIGN-01 se cierra con esta decisión. F1-01 (2026-07-27) implementó, a
partir de ella, el sistema de tokens, los fundamentos globales accesibles y
la biblioteca de primitivas (`frontend/components/ui/`) — ver `DESIGN.md`.
La implementación funcional de dominio (`CopilotPanel`, `RunTimeline`,
`EvidenceCard` reales, con datos en vivo, SSE, REST y reducer) sigue siendo
un incremento aparte, no cubierto por F1-01, que requiere autorización
explícita independiente; no se dispara automáticamente por esta aprobación.
