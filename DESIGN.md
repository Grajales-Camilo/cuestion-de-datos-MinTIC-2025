---
name: Cuestión de Datos — Pulso por lo Público
description: Sala de seguimiento de políticas públicas y sistema de orientación cívica; la investigación de datos abiertos se recorre como una ruta verificable, no se conversa con ella.
colors:
  blue-900: "#004E8C"
  blue-700: "#0068A8"
  blue-500: "#1F7EE0"
  blue-100: "#CDE8FF"
  blue-50: "#F3F9FF"
  white: "#FFFFFF"
  slate-900: "#0F172A"
  slate-600: "#475569"
  slate-400: "#94A3B8"
  success: "#15803D"
  warning: "#B45309"
  error: "#B91C1C"
typography:
  display:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans', Ubuntu, Cantarell, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "26px"
    fontWeight: 700
    lineHeight: 1.25
  title:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans', Ubuntu, Cantarell, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "20px"
    fontWeight: 700
    lineHeight: 1.25
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans', Ubuntu, Cantarell, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.7
  label:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans', Ubuntu, Cantarell, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "13px"
    fontWeight: 700
    lineHeight: 1.5
rounded:
  sm: "4px"
  md: "6px"
  lg: "10px"
  full: "9999px"
spacing:
  1: "4px"
  2: "8px"
  3: "12px"
  4: "16px"
  5: "20px"
  6: "24px"
  8: "32px"
  10: "40px"
  12: "48px"
  16: "64px"
components:
  button-primary:
    backgroundColor: "{colors.blue-700}"
    textColor: "{colors.white}"
    rounded: "{rounded.md}"
    padding: "0 16px"
  button-primary-hover:
    backgroundColor: "{colors.blue-900}"
  button-destructive:
    backgroundColor: "{colors.error}"
    textColor: "{colors.white}"
    rounded: "{rounded.md}"
    padding: "0 16px"
  badge-verified:
    backgroundColor: "{colors.success}"
    textColor: "{colors.white}"
    rounded: "{rounded.full}"
    padding: "4px 12px"
  badge-no-evidence:
    backgroundColor: "{colors.blue-50}"
    textColor: "{colors.blue-900}"
    rounded: "{rounded.full}"
    padding: "4px 12px"
---

# Design System: Cuestión de Datos — Pulso por lo Público

## Overview

**Creative North Star: "Pulso por lo Público"**

Cuestión de Datos no es un chatbot que responde preguntas: es una sala de
seguimiento de políticas públicas con un sistema de orientación cívica
integrado. El funcionario o el analista ciudadano no abre una conversación,
abre una investigación — y esa investigación se muestra como una **ruta
verificable**: un recorrido con pasos observables, cada uno respaldado por
una fuente que se puede auditar, no un intercambio de mensajes con una
inteligencia que "sabe cosas". El modo es **Operate**: la expresión nunca
puede oscurecer la tarea, el estado o la afordancia conocida; el lienzo de
políticas y el copiloto lateral existen para que el usuario termine su
documento con evidencia trazable, no para entretenerlo.

La superficie rechaza activamente cuatro categorías por defecto que el
mundo de "asistente de IA" produce automáticamente: **burbujas de chat**
(esto no es una conversación, es una investigación con estructura), la
**gamificación** (no hay insignias, rachas ni puntuación — el "progreso" es
evidencia acumulada, no un juego), el **grid de dashboard genérico**
(paneles intercambiables sin jerarquía no comunican una ruta de
investigación), y la **estética futurista/neón/glass/IA mágica** (glassmorphism,
resplandores violeta, partículas — cualquier cosa que sugiera magia en vez
de método verificable). Al mismo tiempo, la superficie rechaza la
**rigidez burocrática**: no es un formulario gubernamental gris ni una
tabla Excel disfrazada de web; es clara, con jerarquía y con momentos de
calma, pero nunca fría ni intimidante para un funcionario sin formación
técnica.

Dirección aprobada por el usuario en DESIGN-01 (2026-07-27): **Variante A —
Ruta central** (`docs/frontend-v2/design/design-01/`). F1-01 (2026-07-27)
implementó el sistema de tokens, los fundamentos globales accesibles y la
biblioteca de primitivas (`frontend/components/ui/`) que materializan este
mundo; este documento ya no es un seed — describe código real.

**Key Characteristics:**
- Investigación como ruta recorrible con pasos observables, no como hilo de chat.
- Evidencia como destino del recorrido, no como adorno lateral.
- Calma en reposo: la interfaz no reclama atención cuando no está trabajando.
- Cadena de confianza visible en cada cifra: dataset → entidad → consulta → validación → cifra.
- Paleta monocromática de azules ya fijada por la constitución; la exploración vive en la estructura, no en el color.

## Colors

Paleta ya fijada por `constitution.md` Art. V y `plan.md` §7 — no es una
decisión de marca abierta. Fuente de verdad única en
`frontend/styles/tokens.css`; Tailwind consume esas variables con el
prefijo `cdt-` (`bg-cdt-blue-700`, etc.) para no chocar con la paleta por
defecto de Tailwind que el frontend legacy sigue usando con otros valores.

**Revisión de matices (posterior a DESIGN-01, aprobada explícitamente por
el usuario):** los cinco tonos de azul se recalibraron con una paleta
inspirada en el azul característico de VS Code, conservando exactamente la
misma estructura monocromática (5 pasos, mismo rol de cada uno).
`blue-900`, `blue-100` y `blue-50` son el valor VS Code sin ajustar;
`blue-700` y `blue-500` se oscurecieron un paso frente al valor VS Code
literal (`#007ACC`/`#3794FF`) porque fallaban contraste WCAG como
texto/anillo de foco sobre `blue-50`/`blue-100` — ver
`frontend/tests/unit/ui/contrast.test.js`, que hace cumplir esto en CI.

### Primary
- **Azul profundo** (`#004E8C`, `blue-900`): titulares, navegación, hover del botón primario. Es el ancla de autoridad — donde el ojo debe leer "esto es serio y verificado".
- **Azul medio** (`#0068A8`, `blue-700`): botones primarios, enlaces. El color de la acción disponible.
- **Azul acento** (`#1F7EE0`, `blue-500`): foco, elementos activos del agente mientras investiga — el color del "esto está pasando ahora".

### Neutral
- **Fondo tarjeta de evidencia** (`#CDE8FF`, `blue-100`): fondos de tarjetas de evidencia y chips — nunca para texto.
- **Fondo de sección** (`#F3F9FF`, `blue-50`): separación de zonas sin bordes duros.
- **Blanco** (`#FFFFFF`): fondo base, el lienzo en reposo.
- **Slate 900/600/400**: texto principal / secundario / deshabilitado.

### Semánticos (solo estados de validación/errores)
- **Éxito** (`#15803D`): evidencia validada, claim verificado (`completed`).
- **Advertencia** (`#B45309`): advertencia de presentación, cobertura parcial (`interrupted`).
- **Error** (`#B91C1C`): fallo real del sistema o dato rechazado (`failed`) — **nunca** ausencia de evidencia.

### Named Rules
**La Regla del Acento Escaso.** `blue-500` marca exactamente una cosa a la
vez — el paso activo del agente o el elemento con foco de teclado. Si dos
elementos compiten por `blue-500` en la misma vista, uno de los dos está
mal jerarquizado. `blue-500` nunca es color de texto normal (falla
contraste AA en texto pequeño).

**La Regla de los Semánticos Cerrados.** Verde/ámbar/rojo existen
únicamente para estado de validación de evidencia. Nunca se usan como
acento decorativo ni para jerarquía genérica.

**La Regla del `no_evidence` Neutral.** La ausencia de evidencia elegible
(`no_evidence`) es un resultado honesto del sistema, no un error — se
representa en **azul profundo sobre fondo azul claro** (`blue-900` sobre
`blue-50`), con icono informativo, nunca en rojo. Corrección aplicada en
F1-01: una versión anterior de este documento listaba "ausencia de
evidencia" bajo el token de error; era incorrecta y contradecía
`Badge.jsx`, que ya implementaba el tratamiento neutral correctamente.

## Typography

**Familia:** sans-serif única de sistema
(`-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans", Ubuntu, Cantarell, "Helvetica Neue", Arial, sans-serif`),
fijada por `plan.md` §7 y `frontend/styles/tokens.css` (`--cdt-font-sans`).

**Character:** una sola voz tipográfica, sin serifa, funcional — máximo dos
pesos por pantalla. La tipografía nunca es el vehículo de personalidad de
esta superficie; ese trabajo lo hace la estructura de la ruta y la cadena
de confianza, no el tipo de letra.

### Hierarchy
- **Display** (700, 26px, línea 1.25): título de página (`h1`).
- **Title** (700, 20px, línea 1.25): título de sección (`h2`).
- **Lg** (400, 17px, línea 1.5): encabezados menores.
- **Body** (400, 15px, línea 1.7): cuerpo de párrafo, el tamaño más usado.
- **Sm** (700, 13px, línea 1.5): etiquetas, botones, pestañas.
- **Xs** (400, 12px, línea 1.5): metadatos, pie, badges.

### Named Rules
**La Regla de los Dos Pesos.** Ninguna pantalla usa más de dos pesos de
fuente: 400 (normal, `--cdt-weight-normal`) y 700 (bold,
`--cdt-weight-bold`). No existe un peso intermedio en el sistema — la
jerarquía se construye con color (`slate-900/600/400`) y tamaño, no con una
escalera de grosores.

## Layout

Layout de 3 zonas, ya fijado por `plan.md` §7: navegación mínima superior,
lienzo central (documento de política), copiloto lateral (investigación en
curso). El límite entre lienzo y copiloto es un divisor arrastrable y
operable por teclado (`CopilotPanel.jsx`, RF-105-02) — el ancho del
copiloto ya no es fijo. Responsive y reflujo sin scroll horizontal a 320 px
son invariantes de aceptación, verificadas en F1-01 sobre la galería de
primitivas (`frontend/pages/_dev/ui.js`).

**Revisión RF-105-02 sobre DESIGN-01 (Variante A — Ruta central):** la
implementación original organizaba los pasos como un recorrido vertical
continuo con línea conectora, un `<li>` por paso. Con investigaciones
largas obligaba a desplazarse hasta el final para ver el estado actual.
Ahora `RunTimeline` muestra una sola tarjeta condensada con el ÚLTIMO paso
recibido (icono de actividad sutil, sin contador de pasos ni porcentaje
inventado); el historial completo con su detalle técnico sigue disponible,
sin perder nada, en `StepDetailModal` ("Ver detalle técnico") — un
selector donde el usuario elige QUÉ paso desplegar, actualizado en vivo
mientras la investigación sigue corriendo. La evidencia final ya no se
funde como último punto de la ruta: es un bloque propio (`TerminalPanel`)
debajo de la tarjeta de estado. La idea de "investigación como ruta
verificable" se conserva a nivel de producto (cada paso sigue siendo
observable y auditable); lo que cambia es que la ruta completa se consulta
bajo demanda en vez de estar siempre expandida.

Espaciado: escala 4/8 px (`--cdt-space-1` … `--cdt-space-16`, de 4px a
64px). Tamaño táctil mínimo: 44×44 px (`--cdt-tap-min`), aplicado a todo
control interactivo (`Button`, `IconButton`, pestañas de `Tabs`).

## Elevation & Depth

Sin sombras duras ni degradados (constitución Art. V). La profundidad se
transmite con diferencias de fondo (`white` / `blue-50` / `blue-100`) y con
bordes de 1px (`--cdt-border-width` sobre `blue-100`) — nunca con
`box-shadow` pronunciada ni efectos de vidrio/blur. Es un sistema plano por
decisión, no por omisión. Ningún componente implementado en F1-01 usa
`box-shadow`.

### Named Rules
**La Regla Anti-Glass.** Ningún panel usa `backdrop-filter`, transparencia
translúcida sobre contenido, ni bordes brillantes — eso pertenece a la
estética "IA mágica" que este mundo rechaza explícitamente. El único uso de
opacidad en F1-01 es el velo (`bg-black/50`) detrás de `Modal`, un patrón
funcional estándar, no decorativo.

## Shapes

Radios pequeños y coherentes, sin esquinas muy redondeadas: `sm` (4px, uso
interno/Skeleton), `md` (6px, botones/tarjetas de evidencia), `lg` (10px,
`Card`/`Modal`), `full` (9999px, `Badge`). Bordes de 1px sobre `blue-100`
donde se necesita separar contenido sin sombra.

## Components

Biblioteca mínima real, implementada en `frontend/components/ui/` (F1-01).
Todas requieren renderizarse dentro de un contenedor `.cdt-v2` (aplica
tipografía, foco visible y `prefers-reduced-motion` sin afectar al frontend
legacy).

### Buttons (`Button.jsx`, `IconButton.jsx`)
- **Shape:** radio `md` (6px), alto mínimo 44px.
- **Variantes (exactas, sin ampliar):** primaria (`blue-700`/blanco),
  secundaria (`blue-50`/`blue-700` con borde `blue-100` — fondo propio a
  propósito: sobre el lienzo blanco en reposo, un botón sin relleno era
  indistinguible), silenciosa (transparente/`blue-700`, uso reservado a
  contextos ya tonalizados como la barra de formato), destructiva
  (`error`/blanco).
- **Estados:** hover (oscurece o `brightness-90`), focus-visible (anillo
  `blue-500` heredado de `.cdt-v2`), active, disabled (opacidad 50%,
  `pointer-events: none`), loading (`aria-busy`, ícono `Loader2` girando).
- **IconButton** exige `label` (nombre accesible); el icono siempre
  `aria-hidden`.

### Badge (`Badge.jsx`)
- **Estilo:** píldora (radio `full`), fondo sólido + texto blanco (o
  `blue-900` sobre `blue-50` para `no_evidence`), siempre con icono +
  texto — nunca solo color.
- **Conjunto cerrado:** `verified`, `warning`, `no_evidence`, `interrupted`,
  `failed` (ver corrección semántica arriba).

### Cards / Containers (`Card.jsx`)
- **Corner Style:** radio `lg` (10px).
- **Background:** `white`.
- **Shadow Strategy:** ninguna — borde 1px `blue-100`.
- **Border:** 1px `blue-100`.
- **Internal Padding:** `CardHeader`/`CardBody`/`CardFooter` en `space-4`.

### Disclosure (`Disclosure.jsx`)
- Control con `<button>` real, `aria-expanded`/`aria-controls`, icono
  `ChevronDown` que rota 180° al abrir.

### Modal (`Modal.jsx`)
- `role="dialog"`, `aria-modal`, `aria-labelledby` sobre el título
  obligatorio. Radio `lg`, borde `blue-100`, sin sombra. Trampa de foco
  Tab/Mayús+Tab, cierre con Escape, restauración de foco, bloqueo de
  scroll del body, portal a `document.body` desmontado por completo al
  cerrar.

### Tabs (`Tabs.jsx`)
- `tablist`/`tab`/`tabpanel`, tabindex progresivo (roving tabindex),
  activación automática con flechas/Home/End. Pestaña activa: borde
  inferior `blue-700` + texto `blue-900`.

### Table (`Table.jsx`)
- Encabezados `<th scope="col">` sobre `blue-50`. Contenedor con
  `overflow-x-auto` propio — nunca desborda la página. Exige `caption` o
  nombre accesible.

### MenuBar / Menu (`Menu.jsx`)
- Patrón Menubar de WAI-ARIA APG (RF-105): `role="menubar"` con menús de
  nivel superior (`role="menuitem"`, `aria-haspopup`/`aria-expanded`) y un
  panel `role="menu"` por menú abierto, uno a la vez. Flechas
  izquierda/derecha mueven el foco entre menús (tabindex progresivo);
  arriba/abajo, Home/End navegan las opciones; Escape cierra y devuelve el
  foco a su disparador; un clic fuera cierra sin mover el foco.
- Tres tipos de opción: `MenuItem` (acción simple), `MenuCheckboxItem`
  (`role="menuitemcheckbox"`, alterna un formato binario) y `MenuRadioItem`
  (`role="menuitemradio"`, mutuamente excluyente dentro de un `MenuGroup`).
  El estado marcado siempre refleja `editor.isActive(...)` real, nunca un
  estado local propio del menú.
- Primer uso real: menú "Archivo/Editar/Formato" de `/app`
  (`DocumentMenuBar.jsx`), sobre el editor Tiptap de la sección con el foco
  más reciente.

### LiveRegion (`LiveRegion.jsx`)
- `role="status"` + `aria-live="polite"` + `aria-atomic="true"`, mensaje
  único sustituido (no acumulado), visualmente oculto por defecto.

### Skeleton (`Skeleton.jsx`)
- `aria-hidden`, pulso suave (`animate-pulse`) sobre `blue-100`, sin
  shimmer ni degradado; respeta `prefers-reduced-motion` vía la regla de
  `.cdt-v2`.

### VisuallyHidden (`VisuallyHidden.jsx`)
- Utilidad `sr-only` del núcleo de Tailwind (sin valores arbitrarios
  propios).

## Do's and Don'ts

### Do:
- **Do** presentar el paso actual del agente en español claro, con acceso a
  su historial completo y detalle técnico bajo demanda (`StepDetailModal`),
  nunca como un mensaje de chat entrante ni como una lista que obligue a
  desplazarse para ver el estado más reciente.
- **Do** mostrar la cadena dataset → entidad → consulta → validación → cifra
  de forma visible y citable en cada pieza de evidencia.
- **Do** dejar la interfaz visualmente en reposo cuando no hay investigación
  activa — sin animación de fondo, sin parpadeo, sin reclamar atención.
- **Do** usar `aria-live="polite"` agrupado para el progreso del agente; el
  usuario debe poder ignorarlo sin perder información crítica si no quiere
  seguirlo en tiempo real.
- **Do** representar `no_evidence` en azul profundo/neutral, nunca en rojo.

### Don't:
- **Don't** usar burbujas de chat, avatares conversacionales ni un input
  de "escribe tu mensaje" como metáfora principal de interacción.
- **Don't** introducir gamificación: puntuación, insignias, rachas, barras
  de "nivel" o cualquier mecánica que recompense el uso en sí en vez de la
  evidencia obtenida.
- **Don't** usar un grid de dashboard genérico e intercambiable; cada
  superficie tiene una jerarquía de lectura intencional, no paneles
  equivalentes.
- **Don't** usar estética futurista, neón, glassmorphism o cualquier señal
  visual de "magia de IA" (resplandores, partículas, gradientes vibrantes
  fuera de la paleta azul).
- **Don't** caer en rigidez burocrática (formulario gris, tabla cruda sin
  jerarquía) — la claridad funcional no es excusa para la frialdad.
- **Don't** tratar la ausencia de evidencia como un fallo (rojo); es un
  resultado honesto (neutral azul).
