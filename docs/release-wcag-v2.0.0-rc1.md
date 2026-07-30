# Acta de revisión manual — WCAG 2.2 AA (v2.0.0-rc1)

**Versión revisada:** v2.0.0-rc1
**Fecha:** 2026-07-29 / 2026-07-30
**Revisor humano:** Juan Camilo Grajales B.
**Rama / commit base:** `feat/frontend-v2`, commit base `5853251cc593e32008d2afc8ede7201efe19c6b9` + cambios no comiteados de F8-01, F8-01-R1 y F8-02 (worktree real de la sesión)
**Informe automatizado relacionado:** [`docs/frontend-v2/release/f8-01-automated-gates.md`](frontend-v2/release/f8-01-automated-gates.md)

Esta acta es la revisión manual obligatoria que T-505 exige además de las
puertas automatizadas de F8-01/F8-01-R1 (axe, 897 pruebas unitarias, 89
pruebas E2E). **No sustituye ni se fabrica a partir de esas puertas
automatizadas** — cada resultado de este documento proviene de una
observación humana real, con las excepciones explícitamente marcadas como
verificación automatizada aceptada por el revisor (ver §7).

> **Adenda F8-02-R1 (2026-07-30).** Se añadieron 4 pruebas conductuales
> dedicadas que reproducen D-5 de forma explícita y nombrada (§5, D-5) —
> antes solo se citaba el total de la suite. D-4 se reclasificó
> explícitamente como deuda visual de producto, distinta de D-1 (§5, §9).
> No se tocó nada más: sin avance a F8-02 adicional ni a F9.

## 1. Entorno de la revisión

| Campo | Valor |
|---|---|
| Sistema operativo | Windows 11 Pro, build 10.0.26200 |
| Navegador | Chrome real (canal `chrome`, nunca el Chromium embebido de Playwright): `150.0.7871.187` al inicio de la sesión; se observó una actualización automática a `151.0.7922.72` durante la sesión (Chrome se autoactualiza en segundo plano) — la revisión con NVDA se realizó ya con esa versión |
| Lector de pantalla | NVDA `2026.1.1` (build `2026.1.1.55980`), instalado en `C:\Program Files\NVDA` durante esta misma sesión |
| Resolución / escala | 1920×1080, 96 DPI (100% de escala del sistema) |
| Node.js (equipo revisor) | v24.18.0 — nota: CI usa Node 20 (`ci.yml`); es una diferencia de entorno de *build*, no afecta esta revisión de UI/accesibilidad, que corre contra `next dev`/`next build` reales |
| Rama / commit | `feat/frontend-v2` / `5853251` + worktree real de la sesión (F8-01, F8-01-R1, F8-02) |
| Versión de la aplicación | v2.0.0-rc1 |
| Zona horaria | Hora local del equipo revisor (Colombia) |

No se registró nombre de usuario de Windows ni rutas privadas del equipo.

## 2. Alcance

Revisión manual de conformidad WCAG 2.2 AA sobre `/app` real (nunca `/`,
frontend legacy, fuera de alcance): navegación completa por teclado, lector
de pantalla real (NVDA, sin emulación), zoom real de Chrome al 200% (sin
`style.zoom`, `deviceScaleFactor` ni transformaciones CSS), reflujo a 320 CSS
px, y percepción de color/movimiento. Estados cubiertos: inicial,
consentimiento, investigación activa (streaming con ritmo real, no
instantáneo), `completed` con evidencia (incluida una gráfica RF-503 con
datos sintéticos declarados — ningún fixture real capturado hasta hoy
produce una gráfica), `no_evidence`, `interrupted`, `failed`, aporte manual,
historial y borrado, exportación DOCX.

## 3. Método

Arnés dedicado `frontend/scripts/manual-review-harness.mjs` (nuevo en
F8-02): Chrome real en modo headed sobre `/app` real, backend interceptado
por un servidor local mínimo que reproduce fixtures reales ya existentes
(`no-evidence.json`, `interrupted.json`, `failed.json`,
`completed-stream.sse.txt`) más un doble sintético declarado para la
gráfica RF-503 (ningún fixture real la produce). Nunca backend real, nunca
servicios externos, nunca una ruta de producto nueva. Streaming con pasos
reales entregados con ritmo controlado (~1.3 s entre pasos), nunca
instantáneo, para poder evaluar los anuncios de `aria-live` en condiciones
reales.

## 4. Matriz PASS/FAIL

### 4.1 Teclado completo (sin ratón, sin `.focus()` programático)

| # | Control | Resultado |
|---|---|---|
| 1 | Skip-link primer control alcanzable; entra al contenido principal | PASS |
| 2 | Editor del documento y su barra de herramientas | PASS |
| 3 | "Investigar esta sección" | PASS |
| 4 | "Agregar dato manual" | PASS |
| 5 | Pregunta libre + botón "Investigar" | PASS |
| 6 | Consentimiento: foco inicial, recorrido, checkbox (Espacio), Escape, restauración de foco | PASS |
| 7 | Copiloto alcanzable en escritorio y móvil | PASS |
| 8 | Línea de tiempo (timeline) navegable/legible | PASS |
| 9 | Evidencia: tabla, detalle, CSV, copiar cita, insertar | PASS |
| 10 | Confirmación RF-404 (evidencia no recomendada) navegable y accionable | PASS |
| 11 | Historial: Reejecutar, Refinar, Borrar (con confirmación) | PASS |
| 12 | Exportar a Word alcanzable y accionable | PASS |
| 13 | Ningún modal deja escapar el foco al fondo de la página | PASS |
| 14 | Foco vuelve al control que abrió el modal, al cancelar o confirmar | PASS |
| 15 | Sin trampas de foco fuera de los modales | PASS |

**16/16 PASS** (los puntos 1–2 del checklist original de teclado se
verificaron juntos en el ítem 1 de esta tabla).

### 4.2 Lector de pantalla real (NVDA 2026.1.1)

| # | Control | Resultado | Observación |
|---|---|---|---|
| 1 | Título de página | PASS | — |
| 2 | Landmarks y encabezados | PASS | — |
| 3 | Editor y barra de herramientas | PASS | — |
| 4 | Compositor (etiquetas de campos) | PASS | — |
| 5 | Consentimiento completo | PASS con salvedad no bloqueante | Ver defecto D-1, §5 |
| 6 | Investigación activa: anuncio inicial, pasos agrupados, foco hablado = foco visual | PASS | — |
| 7 | Terminal `completed`: anuncia el resultado | **PASS tras corrección** | Ver defecto D-2 (corregido y reconfirmado), §5 |
| 8 | Badge de calidad con texto (no solo color) | PASS (comportamiento esperado) | Solo se lee en exploración por texto, no con Tab — es contenido estático normal, no un control; ver §6 |
| 9 | EvidenceCard: nombre del dataset se lee literal | PASS | Nombres de dataset reales pueden ser poco amigables (p. ej. `Min_Ed_Cal_DESR_26`) — es dato real, no se "embellece" (RNF-012) |
| 10 | Tabla: caption, encabezados, navegación por celdas | PASS | — |
| 11 | Gráfica (RF-503, doble sintético declarado): nombre accesible, alternativa textual | PASS | No es alcanzable con `Tab` (correcto: es una imagen `role="img"`, no un control); sí se lee con flecha abajo / lista de elementos de NVDA — confirmado por el revisor |
| 12 | `no_evidence`: desenlace honesto, sin jerga sin explicar | PASS | — |
| 13 | `interrupted` / `failed`: claros, sin códigos crudos | PASS | — |
| 14 | Aporte manual: etiquetas de campos, distinción de evidencia verificada | PASS | — |
| 15 | Errores de formulario anunciados con claridad | PASS | — |
| 16 | Historial y borrado: confirmación anunciada y borrado exitoso anunciado | **PASS tras corrección** | Ver defecto D-3 (corregido y reconfirmado), §5 |

**16/16 PASS** (2 tras corrección real, reconfirmados por el revisor con
NVDA real después de la corrección).

Preguntas de cierre de la Parte 3, respuesta del revisor:
- *¿El propósito de cada control se entiende sin mirar la pantalla?* — "Más o menos. NVDA lee absolutamente todo, incluso lo que no se ve. Le dice 'región' al cuadro de texto donde se escribe la investigación" (confirmado como comportamiento correcto de landmark, no un defecto — ver §6).
- *¿Se distingue evidencia verificada de aporte manual?* — "Sí, el NVDA lee textual lo que aparece en pantalla y las evidencias van acompañadas de esa etiqueta 'verificada' y 'aportada por el usuario'."
- *¿Algún texto técnico aparece sin explicación en la superficie primaria?* — "No."

### 4.3 Zoom real de Chrome al 200% (`Ctrl`+`+`, sin CSS/emulación)

| # | Estado | Resultado |
|---|---|---|
| 1 | Inicio | PASS |
| 2 | Consentimiento | PASS |
| 3 | Streaming | PASS |
| 4 | `completed` con evidencia | PASS |
| 5 | `no_evidence` | PASS |
| 6 | Modal de aporte manual | PASS |
| 7 | Historial | PASS |
| 8 | Exportación | PASS |

**8/8 PASS.** Sin pérdida de contenido, sin controles inalcanzables, sin
superposición de texto, foco visible, sin scroll horizontal de página.

### 4.4 Reflujo a 320 CSS px

Revisión visual manual complementaria a la cobertura automatizada
extensa ya existente (F8-01: 320px en 12+ specs E2E). **PASS general**
confirmado por el revisor sobre el flujo completo (drawer del copiloto,
editor, cita insertada, modales, historial) sin scroll horizontal de
página; el scroll interno de la tabla de evidencia se confirmó como
correcto, no como defecto.

### 4.5 Color, movimiento y percepción

| # | Control | Resultado |
|---|---|---|
| 1 | Errores con icono/texto, nunca solo color | PASS |
| 2 | Badges con icono y texto | PASS |
| 3 | Foco perceptible en cualquier fondo | PASS |
| 4 | Evidencia vs. aporte manual distinguibles sin depender solo del color | PASS con salvedad no bloqueante | Ver defecto D-4, §5 |
| 5 | Contraste legible en estados deshabilitados | PASS |
| 6 | `prefers-reduced-motion` no elimina información | PASS |
| 7 | Timeline comprensible sin animación | PASS |
| 8 | Sin parpadeos que impidan leer | PASS |

**8/8 PASS.**

## 5. Defectos encontrados y su tratamiento

### D-1 — Doble lectura de NVDA en el modal de consentimiento (no bloqueante, causa raíz no confirmada)

**Observación literal:** "En el cuadro de inicio de investigación, NVDA
repite dos veces el nombre del cuadro y el contexto que se enviará."
Reproducido también en un build de producción real (`--prod`), descartando
que fuera un artefacto de `reactStrictMode` en desarrollo. Se intentó el
arreglo estándar de Chromium para "pintura obsoleta" (`translateZ(0)`) sin
éxito. **Clasificación explícita del revisor: "no bloqueante, es molesto
pero no bloqueante."** Sin corrección aplicada. Pasa a la lista de deudas
ambientales/técnicas (§9).

### D-2 — El anuncio en vivo al completar no decía el resultado (corregido, reconfirmado)

**Hallazgo:** `hooks/usePolitePolite.js` anunciaba solo "Investigación
completada." al terminar, sin decir el desenlace — distinto del texto
visible ("La investigación terminó con evidencia verificada."). Quien usa
lector de pantalla no tenía forma de saber el resultado sin explorar el
panel a mano.
**Corrección:** el anuncio en vivo ahora coincide exactamente con el texto
visible.
**Pruebas:** focalizada (`usePolitePolite.test.jsx`, 6/6) + suite completa
(897/897).
**Reconfirmación del revisor con NVDA real, tras la corrección:** PASS
("NVDA llega hasta 'Terminó investigación con evidencia verificada'").

### D-3 — El borrado exitoso de una investigación no se anunciaba (corregido, reconfirmado)

**Hallazgo:** al confirmar el borrado, `HistoryList.jsx` solo tenía anuncio
para el error (`role="alert"`) — el camino de éxito era completamente
silencioso para lector de pantalla.
**Corrección:** `pages/app.js` ahora anuncia "La investigación se borró de
forma irreversible." por el mismo canal `aria-live` que ya usa el aporte
manual.
**Pruebas:** prueba E2E existente ampliada con esta aserción (`app-f3-7b.spec.js`,
12/12) + suite completa (897/897).
**Reconfirmación del revisor con NVDA real, tras la corrección:** PASS.

### D-4 — Badge "Escrito por el usuario" no pinta en el primer render (deuda visual de producto, no bloqueante)

**Observación literal:** "el botón que distingue 'Escrito por el usuario',
al principio está en azul, luego de darle clic a ese botón es que aparece
el texto blanco." Reproducido de forma aislada e independiente
(automatizada, sin clic ni foco): el fondo del badge pinta correctamente
pero el texto no, de forma persistente (se probó esperar, forzar `reflow`
por JavaScript y disparar `resize`, sin éxito); solo una recarga completa
lo pinta bien desde el inicio. `getComputedStyle` confirma que el color,
la visibilidad y el tamaño del texto son correctos — el navegador "sabe"
que el texto debería estar ahí, pero no lo pinta en el primer render tras
la inserción en vivo del nodo. Se intentó el arreglo estándar de Chromium
(`translateZ(0)` para forzar una capa de composición): no funcionó, se
revirtió. **El lector de pantalla SÍ lee el contenido correctamente**
(confirmado en la Parte 3, punto 9: "las evidencias van acompañadas de esa
etiqueta... 'aportada por el usuario'") — es puramente un defecto de
pintura visual para usuarios videntes, no de accesibilidad para lector de
pantalla. **Reclasificado en F8-02-R1, por instrucción explícita del
revisor, como deuda VISUAL DE PRODUCTO no bloqueante** (distinta de D-1,
que es de comportamiento de NVDA): afecta la percepción visual de
personas videntes, no la accesibilidad para lector de pantalla. Se
conserva la aceptación humana original de F8-02; **no se intentó
corregir de nuevo en esta ronda** (F8-02-R1 acotó el alcance
explícitamente a D-5). Pasa a la lista de deudas ambientales/técnicas
(§9), bajo la subcategoría de deuda visual de producto.

### D-5 — CRÍTICO: pérdida de contenido — citas/aportes manuales se borraban al escribir después de ellos (corregido)

**Cómo se detectó:** a partir de una observación del revisor durante la
Parte 6 ("revisar comportamiento de la inserción de las citas que se
borran al tratar de escribir texto debajo de ellas").
**Causa raíz confirmada:** `lib/document/schema.js` tenía
`trailingNode: false`, deshabilitando explícitamente la extensión de
Tiptap (ya incluida en `@tiptap/starter-kit`, sin dependencias nuevas) que
garantiza un párrafo de texto después de cualquier nodo atómico
(`evidenceCitation`, `manualEntry`) al final del documento. Sin ese
párrafo, el cursor terminaba seleccionando la cita como **nodo completo**
en vez de posicionarse en texto, y escribir en esas condiciones la
**reemplazaba por completo** — pérdida de contenido real, reproducida
técnicamente antes de corregir nada (`doc structure` pasaba de
`["paragraph","evidenceCitation"]` a `["paragraph","paragraph"]`, la cita
desaparecía).
**Corrección:** se reactivó `trailingNode` en `createBaseDocumentExtensions()`.
**Efecto en cadena corregido:** 2 pruebas unitarias que asumían la cita
como último nodo del documento se ajustaron (`at(-2)`, no `at(-1)`, ahora
que hay un párrafo real después); 7 archivos de pruebas E2E preexistentes
tenían un selector ambiguo por la corrección D-2 (el texto visible y el de
`aria-live` ahora coinciden) y se corrigieron de forma uniforme.
**Pruebas (F8-02):** 897/897 unitarias, 86/86 E2E funcionales completas.
**Verificación aceptada por el revisor en F8-02:** solo automatizada — el
revisor confirmó explícitamente que acepta la corrección sin repetirla en
vivo con el arnés ("Acepto la corrección").

**Pruebas conductuales dedicadas añadidas en F8-02-R1 (identificadas por
nombre, no solo por el total de la suite — reproducen la interacción real
con el editor, buscan el nodo por tipo/atributo, nunca por índice fijo, y
se confirmó que fallan si `trailingNode` se deshabilita de nuevo):**

- `tests/unit/document/DocumentEditor.test.jsx`:
  - `"D-5: escribir con el editor real justo después de insertar una cita al final conserva la cita y el texto en un párrafo posterior"`
  - `"D-5: escribir con el editor real justo después de insertar un aporte manual al final conserva el aporte y el texto en un párrafo posterior"`
- `tests/e2e/app-d5-content-loss-regression.spec.js` (puerto 3101, 1 worker):
  - `"cita de evidencia al final + texto escrito con teclado real después: ambos sobreviven en memoria y tras recargar"`
  - `"aporte manual al final + texto escrito con teclado real después: ambos sobreviven en memoria y tras recargar"`

Las 4 pruebas se verificaron explícitamente en ambos sentidos: **fallan**
con `trailingNode: false` restaurado temporalmente (reproducen D-5 de
verdad, no solo confirman que existe un párrafo final) y **pasan** con la
corrección real aplicada. Las E2E además confirman la persistencia real:
recargan la página y leen el documento serializado en `localStorage`
directamente, no solo el DOM.

## 6. Comportamientos confirmados como correctos (no son defectos)

- **"Región" anunciada al entrar al campo de pregunta:** el compositor está
  dentro de un `<section aria-labelledby="composer-heading">` — una
  `<section>` con nombre accesible es, por especificación, un landmark
  `region`. Es el comportamiento correcto de navegación por landmarks.
- **Badge de calidad solo se lee explorando, no con `Tab`:** es contenido
  estático normal (no un control interactivo); se descubre igual que
  cualquier párrafo de texto, con el mismo mecanismo con el que NVDA lee
  cualquier contenido no interactivo de la página.
- **Gráfica no alcanzable con `Tab`, sí con flecha abajo:** correcto —
  es una imagen (`role="img"`, `<canvas>` de Chart.js), y las imágenes
  nunca son paradas de tabulación (esa reserva es para controles). Se
  confirmó explícitamente que sí se lee con navegación de exploración.
- **Nombres de dataset poco amigables leídos literalmente:** son datos
  reales; RNF-012 prohíbe "embellecer" o reformular hechos/datos de
  fixtures — leerlos tal cual es el comportamiento correcto.

## 7. Evidencia automatizada relacionada

- `docs/frontend-v2/release/f8-01-automated-gates.md`: axe (`wcag2a`+`wcag2aa`+`wcag22aa`)
  sin violaciones en 9 estados/modales, RNF-008 reproducible, bundle sin
  secretos, `npm audit` sin críticas.
- Esta sesión (F8-02): 897/897 pruebas unitarias, 86/86 E2E funcionales,
  ambas suites re-ejecutadas completas después de los defectos D-2, D-3 y
  D-5.
- F8-02-R1: 4 pruebas conductuales dedicadas de D-5, identificadas por
  nombre en §5, verificadas explícitamente en ambos sentidos (fallan sin
  la corrección, pasan con ella) — no solo un total de suite.

## 8. Limitaciones

- El zoom real al 200% y el reflujo a 320 px no se cruzaron sistemáticamente
  con NVDA activo al mismo tiempo (se revisaron por separado).
- La revisión de 320 px (§4.4) se registró como PASS general del recorrido
  completo, no punto por punto como las demás partes — la cobertura
  automatizada existente (F8-01) sí es exhaustiva punto por punto.
- D-5 se aceptó con verificación exclusivamente automatizada, por decisión
  explícita del revisor, no con una repetición en vivo del arnés. F8-02-R1
  reforzó esa verificación con 4 pruebas conductuales dedicadas y
  nombradas (§5, §7), pero sigue sin existir una repetición humana en vivo
  de este punto específico.
- No se registró audio ni transcripción de NVDA; solo observaciones
  literales escritas por el revisor.

## 9. Deudas ambientales / técnicas (no bloqueantes, por decisión explícita del revisor)

**Deuda de comportamiento de lector de pantalla:**

1. **D-1** — Doble lectura de NVDA en el modal de consentimiento. Causa
   raíz no confirmada (no es `reactStrictMode`, persiste en producción).

**Deuda visual de producto** (reclasificada explícitamente en F8-02-R1,
distinta de D-1 — afecta percepción visual de usuarios videntes, no
lectores de pantalla):

2. **D-4** — Badge "Escrito por el usuario" no pinta en el primer render
   tras insertar un aporte manual en vivo (se corrige solo o al recargar).
   Sin impacto en lector de pantalla, solo impacto visual para usuarios
   videntes. Aceptación humana original (F8-02) conservada; no se intentó
   corregir de nuevo en F8-02-R1 (fuera de alcance de esa ronda, acotada a
   D-5).

## 10. Veredicto

**PASS**

Revisión manual de conformidad WCAG 2.2 AA dentro del alcance descrito.

Este veredicto no es una certificación WCAG ni una afirmación de
conformidad AAA. T-505 permanece abierto: falta la ejecución real posterior
del workflow de CI (ver `f8-01-automated-gates.md` y el acta RNF-012,
`docs/release-rnf-012-v2.0.0-rc1.md`) antes de cualquier cierre formal.
