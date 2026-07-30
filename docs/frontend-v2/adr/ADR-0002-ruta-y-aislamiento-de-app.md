# ADR-0002 — Ruta y aislamiento de la aplicación funcional v2

## Estado

Aceptado.

## Contexto y fuerzas en tensión

El frontend legacy en `/` sigue en uso mientras v2 madura. Introducir la
primera superficie funcional real que habla con el backend determinista
(`/v2/agent/query`, `/v2/agent/stream/{run_id}`) exige decidir dónde vive
esa superficie sin arriesgar `/` ni crear una dependencia oculta entre
ambas.

En tensión: reemplazar `/` directamente sería el destino final, pero
elimina la posibilidad de rollback instantáneo mientras `/app` todavía no
está probado contra un backend real, y arrastraría al código nuevo
cualquier deuda o atajo del legacy (fetch a `/api/consultar_v2`,
componentes del agente legacy, un eventual proxy de Next) "para que
compile más rápido".

## Decisión

- La aplicación funcional v2 se implementa temporalmente en `frontend/pages/app.js`.
- `/app` se conecta **exclusiva y directamente** al backend FastAPI
  determinista mediante `NEXT_PUBLIC_BACKEND_URL` y los endpoints `/v2/*`.
- Prohibido en `/app`: llamar a `/api/consultar_v2` o cualquier backend
  legacy de Next.js; importar el agente legacy, sus prompts o utilidades;
  usar componentes legacy como fallback funcional; crear un proxy de
  Next.js hacia FastAPI.
- `/` conserva la interfaz legacy existente, sin modificaciones, y
  completamente aislada de `/app` — es una estrategia de transición y
  rollback, no una dependencia de v2 ni una base de aceptación.
- T-704 decidirá el reemplazo de `/` por la aplicación v2 y la eliminación
  posterior del frontend legacy, una vez que `/app` esté estable y
  verificado contra un backend local real.

## Consecuencias

**Positivas**

- Rollback trivial: revertir es quitar la ruta `/app`; `/` nunca se toca.
- Verificación incremental: `/app` puede probarse en producción (build,
  smoke, accesibilidad) sin arriesgar el tráfico que sigue usando `/`.
- La prohibición explícita de fallback al legacy fuerza que cualquier
  brecha de contrato entre `/app` y el backend real se detecte pronto,
  en vez de esconderse detrás de una ruta legacy que "ya funciona".

**Negativas**

- Duplicación temporal de superficie (dos frontends coexistiendo) hasta
  T-704 — deuda conocida y aceptada, no accidental.
- `/app` no aparece enlazada desde `/` todavía: el acceso es solo por URL
  directa hasta que T-704 decida la transición de navegación.

## Alternativas consideradas

- **Reemplazar `/` directamente**: descartada para este incremento —
  pierde el rollback instantáneo y obliga a que todo lo nuevo esté
  perfecto antes de mergear, en vez de iterar en una ruta aislada.
- **Namespace `/v2/*`** (p. ej. `frontend/pages/v2/index.js`, como
  proponía el surface brief original de Impeccable): descartado por esta
  decisión explícita; el surface brief se corrigió para apuntar a
  `frontend/pages/app.js` sin alterar la composición visual ya aprobada
  (Variante A, DESIGN-01).

## Requisitos, contratos y fases afectados

Fase F3 (F3-7A, F3-7B). No modifica `contracts/api-rest.md`. Afecta la
ruta de lectura de `.impeccable/surfaces/frontend-pages-v2-index-js.md`
(`primary_target` corregido a `frontend/pages/app.js`, contenido y
Variante A preservados).

## Evidencia y fecha de aprobación humana

Aprobado por Juan Camilo Grajales B. como decisión D-7 del encargo
"F3-7B — Consentimiento, historial, borrado y ruta funcional `/app`"
(2026-07-27). Implementado en `frontend/pages/app.js`.

## Sucesor

Pendiente: la decisión que ejecute T-704 (reemplazo de `/` y retiro del
legacy) reemplazará este ADR.
