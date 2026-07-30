# Acta de revisión manual — RNF-012, idioma y claridad en español (v2.0.0-rc1)

**Versión revisada:** v2.0.0-rc1
**Fecha:** 2026-07-30
**Revisor humano:** Juan Camilo Grajales B.
**Rama / commit base:** `feat/frontend-v2`, commit base `5853251cc593e32008d2afc8ede7201efe19c6b9` + cambios no comiteados de F8-01, F8-01-R1 y F8-02 (worktree real de la sesión)
**Informe automatizado relacionado:** [`docs/frontend-v2/release/f8-01-automated-gates.md`](frontend-v2/release/f8-01-automated-gates.md)
**Acta hermana:** [`docs/release-wcag-v2.0.0-rc1.md`](release-wcag-v2.0.0-rc1.md)

## 1. Entorno

Idéntico al registrado en el acta WCAG (`docs/release-wcag-v2.0.0-rc1.md`
§1): Windows 11 Pro build 10.0.26200, Chrome real 150.0.7871.187→151.0.7922.72,
resolución 1920×1080 @ 96 DPI, rama `feat/frontend-v2` sobre commit `5853251`
+ worktree real de la sesión, aplicación v2.0.0-rc1.

## 2. Alcance

Revisión manual de que toda la interfaz y los mensajes del agente en `/app`
están en español claro (Constitución Art. V.5, RNF-012): etiquetas de
navegación, formularios y validaciones, consentimiento, retención y
almacenamiento local, historial y borrado, estados de conexión, pasos del
agente, los cuatro estados terminales (`completed`, `no_evidence`,
`interrupted`, `failed`), advertencias de calidad, evidencia bloqueada,
fuentes externas sugeridas, aporte manual, persistencia/recuperación/cuota,
exportación DOCX.

## 3. Método

Mismo arnés que el acta WCAG (`scripts/manual-review-harness.mjs`),
recorriendo los escenarios `completed`, `no_evidence`, `interrupted` y
`failed` con lectura directa de cada texto mostrado en pantalla por el
revisor humano (no una revisión de código ni una búsqueda automatizada de
cadenas).

## 4. Política aplicada

- No se aceptan enums crudos en la superficie primaria (p. ej.
  `ALL_CANDIDATES_REJECTED`, `SOCRATA_TIMEOUT`).
- `message_dev` nunca debe exponerse al usuario.
- SoQL y detalle técnico solo dentro de *disclosures* técnicos claramente
  nombrados ("Ver detalle técnico").
- No se exige conocimiento de API, SQL ni modelos de IA para entender la
  acción principal.
- Los hechos y datos de fixtures/producción **no se reformulan** para
  sonar "más bonitos" — un texto incómodo pero factual (p. ej. un nombre de
  dataset con guiones bajos y mayúsculas) se mantiene tal cual; no es un
  defecto de RNF-012 corregirlo inventando una versión "amigable".

## 5. Resultado por superficie

| Superficie | Resultado | Observación del revisor |
|---|---|---|
| Etiquetas de navegación | PASS | — |
| Formularios y validaciones | PASS | — |
| Consentimiento | PASS | — |
| Retención y almacenamiento local | PASS | — |
| Historial y borrado | PASS | — |
| Estados de conexión | PASS | — |
| Pasos del agente (SSE) | PASS | — |
| `completed` | PASS | — |
| `no_evidence` | PASS | — |
| `interrupted` | PASS | — |
| `failed` | PASS | — |
| Advertencias de calidad | PASS | — |
| Evidencia bloqueada | PASS | — |
| Fuentes externas sugeridas | PASS | — |
| Aporte manual | PASS | — |
| Persistencia, recuperación y cuota | PASS | — |
| Exportación DOCX | PASS | — |

**17/17 PASS.**

Cita literal del revisor sobre el conjunto: "Todo PASS. Las etiquetas como
los mensajes son claros. En español claro y sin nombres raros excepto en
los disclosures de los detalles técnicos de cada paso que están en JSON."
— confirma explícitamente que el único lugar con contenido técnico crudo
(JSON de detalle) está correctamente aislado en un *disclosure* técnico,
tal como exige la política (§4).

## 6. Hallazgos

Ningún hallazgo de idioma o claridad durante esta revisión. El único punto
que surgió durante esta parte (nombre de archivo ilegible al exportar
DOCX) se investigó y se determinó que era un artefacto exclusivo del arnés
de revisión (Playwright intercepta las descargas por defecto al abrir una
página con `browser.newPage()`, mostrando un identificador interno en vez
del nombre real), **no un defecto de la aplicación ni de RNF-012** — se
confirmó revisando el código de exportación (`ExportDocumentButton.jsx`,
`exportDocx.js`), que siempre deriva el nombre del título real del
documento (`Documento libre` → `Documento-libre.docx`), y se corrigió el
arnés (`acceptDownloads: false`) para que Chrome maneje la descarga de
forma nativa en revisiones futuras. No se registra como defecto de
producto ni como deuda ambiental: es exclusivamente una corrección de la
herramienta de este mismo incremento.

## 7. Defectos encontrados y correcciones aplicadas

Ninguno propio de esta acta. Los defectos D-1 a D-5 encontrados durante la
sesión de revisión manual (dos de ellos vía observaciones que surgieron
en la Parte 6, color/movimiento) están documentados en el acta hermana
WCAG (`docs/release-wcag-v2.0.0-rc1.md` §5), no aquí, porque ninguno era
un problema de idioma/claridad — eran de anuncio a lector de pantalla
(D-2, D-3), pintura visual (D-4), consentimiento (D-1) y pérdida de
contenido del editor (D-5).

## 8. Pruebas repetidas

No aplica — ningún defecto de idioma/claridad requirió corrección ni
repetición.

## 9. Evidencia automatizada relacionada

`docs/frontend-v2/release/f8-01-automated-gates.md`: `messages.es.test.js`
(catálogo completo de nodos/`StopReason` con traducción, ninguna cadena de
salida en mayúsculas con guion bajo) — evidencia automatizada
complementaria, no sustituta de esta revisión humana.

## 10. Limitaciones

- La revisión cubrió los cuatro estados terminales y las superficies
  enumeradas; no se hizo una lectura palabra por palabra de cada mensaje
  de error posible del sistema (serían decenas) — se revisó una muestra
  representativa por categoría.
- No se revisaron mensajes de error de red/infraestructura reales (fuera
  de alcance: el arnés nunca usa backend real).

## 11. Veredicto

**PASS**

Revisión manual de conformidad RNF-012 dentro del alcance descrito.

T-505 permanece abierto: falta la ejecución real posterior del workflow de
CI antes de cualquier cierre formal (ver acta hermana WCAG,
`docs/release-wcag-v2.0.0-rc1.md` §10, y
`docs/frontend-v2/release/f8-01-automated-gates.md`).
