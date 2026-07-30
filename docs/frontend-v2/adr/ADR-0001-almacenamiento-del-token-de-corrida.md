# ADR-0001 — Almacenamiento del token de corrida y del historial de sesión

## Estado

Aceptado.

## Contexto y fuerzas en tensión

`run_access_token` (RF-801, RNF-011) es un secreto de corta duración que
autoriza leer el stream SSE, recuperar (`GET`) y borrar (`DELETE`) una
corrida concreta. El frontend necesita conservarlo el tiempo suficiente
para:

- seguir el stream tras crear la corrida (`POST /v2/agent/query`);
- reconectar tras un corte de red o una recarga de página;
- ofrecer "Borrar esta investigación" (RF-803) sin pedir de nuevo la
  corrida al usuario.

En tensión: `localStorage` sobrevive al cierre de la pestaña (comodidad,
permite reconectar y borrar corridas incluso días después) pero dejaría
un secreto persistente en disco sin que el usuario lo pidiera — contradice
el principio de alcance mínimo de RF-801. `sessionStorage` limita la
ventana de exposición a la pestaña abierta (menor radio de impacto ante un
XSS) pero pierde la posibilidad de borrar manualmente una corrida en
cuanto se cierra la pestaña.

## Decisión

- `sessionStorage` es el almacenamiento **predeterminado** para el
  historial de investigaciones y sus credenciales (`cdd.runs.v1`).
- Se ofrece un opt-in **desmarcado por defecto**: "Recordar mis
  investigaciones en este equipo". Solo si el usuario lo activa
  explícitamente, el registro (incluida su credencial) se guarda en
  `localStorage`.
- El historial público que React consume (`useRunHistory().runs`) **nunca**
  expone el token. La credencial solo se recupera de forma transitoria y
  acotada a un `runId` explícito, para GET, reconexión (`resume`) o
  `DELETE` — nunca en un volcado masivo.
- Al desactivar el opt-in, los registros persistentes migran de vuelta a
  `sessionStorage` cuando es posible y se eliminan de `localStorage` (nunca
  quedan duplicados en ambos almacenes).
- Un registro vencido (`tokenExpiresAt` pasado) nunca reutiliza su token:
  se marca inaccesible (`credentialExpired`) en la superficie pública.
- Un `401` sobre una corrida limpia solo la credencial (la corrida no se
  declara borrada); un `404 RUN_NOT_FOUND` elimina el registro local por
  completo.

## Consecuencias

**Positivas**

- El caso por defecto (mayoría de usuarios) minimiza la superficie de
  exposición del secreto: se pierde al cerrar la pestaña.
- El usuario que sí quiere persistencia entre sesiones la obtiene de forma
  explícita e informada, con aviso literal de la implicación (D-9).
- La separación estricta entre almacén con token (`lib/session/runsStore.js`,
  acceso acotado por `runId`) y vista pública sin token (`useRunHistory().runs`)
  hace verificable por prueba que el token nunca llega a React, al DOM, a
  logs ni a errores serializados.

**Negativas**

- Cerrar la pestaña sin haber activado el opt-in impide borrar
  manualmente esa corrida más adelante desde ese navegador — mitigado por
  la purga automática a los 90 días (`RETENTION_USER_DAYS`) y por el
  texto de consentimiento que lo advierte explícitamente.
- Togglear el opt-in exige lógica de migración (`runsStore.migrate`) en
  vez de una sola fuente de verdad fija — complejidad adicional acotada y
  cubierta por prueba.

## Alternativas consideradas

- **`localStorage` por defecto**: descartada — más cómoda, pero deja un
  secreto persistente sin que el usuario lo pida, contra RF-801.
- **Cookie `httpOnly`**: descartada — requeriría que el backend la fije y
  la valide, cambiando el contrato REST/SSE vigente (autorización por
  encabezado `Authorization: Bearer`) sin autorización para tocar
  contratos en este incremento.
- **Mantener el token únicamente en memoria (sin persistencia)**: descartada
  — pierde la reconexión tras recargar la página (RF-209, "recuperación
  segura ante recarga"), un criterio de aceptación explícito de F3-7B.

## Requisitos, contratos y fases afectados

RF-801, RNF-011, RF-502, RF-803, RF-804. Fase F3 (F3-7B). No modifica
`contracts/api-rest.md`.

## Evidencia y fecha de aprobación humana

Aprobado por Juan Camilo Grajales B. como decisión D-1 del encargo
"F3-7B — Consentimiento, historial, borrado y ruta funcional `/app`"
(2026-07-27). Implementado en `frontend/lib/session/runsStore.js`,
`frontend/lib/session/rememberPreference.js` y `frontend/hooks/useRunHistory.js`,
con cobertura de prueba en `frontend/tests/unit/session/runsStore.test.js`
y `frontend/tests/unit/hooks/useRunHistory.test.jsx`.

## Sucesor

Ninguno.
