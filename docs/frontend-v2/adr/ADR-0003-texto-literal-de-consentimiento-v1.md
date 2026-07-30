# ADR-0003 — Texto literal de consentimiento v1

## Estado

Aceptado.

## Contexto y fuerzas en tensión

RF-802 exige un aviso de consentimiento antes de la primera investigación
que explique qué se guarda, para qué, por cuánto tiempo y cómo borrarlo,
en español claro y sin jerga técnica (RNF-012). El texto es contenido
legal/de producto, no una decisión que el código deba redactar por su
cuenta: necesita aprobación humana explícita y quedar versionado
(`consentVersion`) para poder volver a pedirse si cambia.

## Decisión

Se aprueba el siguiente texto como versión inicial (`consentVersion: 1`)
del modal de consentimiento (`components/consent/ConsentDialog.jsx`):

**Título**

> Antes de iniciar tu primera investigación

**Cuerpo**

> Cuestión de Datos enviará y almacenará tu pregunta y, si la incluyes, un
> fragmento editable de contexto de máximo 1.000 caracteres. También
> conservará los pasos de la investigación, las trazas técnicas, las
> evidencias y el resultado para prestar el servicio y evaluar
> técnicamente su funcionamiento.
>
> Las investigaciones de usuario se conservan hasta 90 días y después se
> eliminan. Mientras una investigación aparezca en tu historial, puedes
> borrarla de forma completa e irreversible con la opción «Borrar esta
> investigación».
>
> El documento completo en el que trabajas no se envía al servidor.

**Opt-in, desmarcado por defecto**

> Recordar mis investigaciones en este equipo. Si activas esta opción, las
> credenciales de acceso permanecerán guardadas en este navegador después
> de cerrar la pestaña. Úsala solo en un equipo personal o de confianza.

**Acciones**

- Primaria: `Aceptar e investigar`
- Secundaria: `Cancelar`

El modal muestra además, junto a este texto fijo, la pregunta exacta y el
contexto exacto (editable) que se enviarán — contenido dinámico de la
corrida, no parte del texto legal versionado.

## Consecuencias

**Positivas**

- Texto aprobado explícitamente por el responsable del producto antes de
  mostrarse a usuarios reales; el código nunca lo parafrasea.
- Versionado (`consentVersion: 1` en `lib/session/consent.js`): un cambio
  futuro de texto sube la versión y vuelve a pedir consentimiento
  automáticamente, sin lógica ad hoc.

**Negativas**

- Cualquier corrección de redacción, por menor que sea, requiere un nuevo
  ADR (o una actualización explícita de este) y una nueva versión —
  fricción deliberada para evitar cambios silenciosos a un texto legal.

## Alternativas consideradas

- **Resumen genérico sin mención de los 90 días ni del borrado explícito**:
  descartada — RF-802 exige explícitamente "por cuánto tiempo" y "cómo
  borrarlo"; un resumen los omitiría.
- **Opt-in marcado por defecto**: descartada por D-1 (alcance mínimo del
  secreto por defecto).

## Requisitos, contratos y fases afectados

RF-802, RNF-012. Fase F3 (F3-7B). No modifica `contracts/api-rest.md`.

## Evidencia y fecha de aprobación humana

Aprobado por Juan Camilo Grajales B. como decisión D-9 del encargo
"F3-7B — Consentimiento, historial, borrado y ruta funcional `/app`"
(2026-07-27). Implementado en `frontend/components/consent/ConsentDialog.jsx`
(`CONSENT_TITLE`, párrafos y etiqueta del opt-in reproducidos literalmente)
y `frontend/lib/session/consent.js` (`CURRENT_CONSENT_VERSION = 1`), con
prueba de texto literal en `frontend/tests/unit/consent/ConsentDialog.test.jsx`.

## Sucesor

Ninguno. Una futura versión 2 del texto reemplazará este ADR o se
registrará como ADR sucesor, según corresponda cuando se apruebe.
