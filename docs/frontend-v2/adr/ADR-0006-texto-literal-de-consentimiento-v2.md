# ADR-0006 — Texto literal de consentimiento v2

## Estado

Aceptado.

## Contexto y fuerzas en tensión

[ADR-0003](./ADR-0003-texto-literal-de-consentimiento-v1.md) fijó el texto
legal de consentimiento (RF-802, RNF-012) con `consentVersion: 1`,
incluyendo la cifra "máximo 1.000 caracteres" para describir el límite de
`context_hint` (RF-104). Ese límite —replicado en el contrato
(`contracts/api-rest.md` §2), en `backend/app/schemas.py`
(`AgentQueryRequest.context_hint`) y en el frontend
(`SECTION_CONTEXT_HINT_MAX_LENGTH`, `MAX_CONTEXT_HINT_LENGTH` en
`QuestionComposer.jsx`/`ConsentDialog.jsx`)— sube de 1.000 a 2.000
caracteres para que el lienzo de documento libre permita compartir más
contexto real de una sección con el copiloto.

El texto de consentimiento es contenido legal/de producto: el propio
ADR-0003 exige que cualquier corrección, "por menor que sea", pase por un
nuevo ADR (o una actualización explícita de este) y una nueva versión — no
un cambio silencioso de una cifra en el código.

## Decisión

Se aprueba como versión 2 (`consentVersion: 2`) el mismo texto de
ADR-0003, con la única cifra afectada actualizada:

**Título** (sin cambios)

> Antes de iniciar tu primera investigación

**Cuerpo**

> Cuestión de Datos enviará y almacenará tu pregunta y, si la incluyes, un
> fragmento editable de contexto de máximo 2.000 caracteres. También
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

**Opt-in, desmarcado por defecto** (sin cambios)

> Recordar mis investigaciones en este equipo. Si activas esta opción, las
> credenciales de acceso permanecerán guardadas en este navegador después
> de cerrar la pestaña. Úsala solo en un equipo personal o de confianza.

**Acciones** (sin cambios)

- Primaria: `Aceptar e investigar`
- Secundaria: `Cancelar`

El modal sigue mostrando, junto a este texto fijo, la pregunta exacta y el
contexto exacto (editable) que se enviarán — contenido dinámico de la
corrida, no parte del texto legal versionado.

## Consecuencias

**Positivas**

- El texto vuelve a describir con exactitud el límite real de
  `context_hint`; ningún usuario ve una cifra falsa en un aviso legal.
- `CURRENT_CONSENT_VERSION` sube de 1 a 2 (`lib/session/consent.js`): todo
  usuario que ya había aceptado la versión 1 deberá aceptar de nuevo antes
  de su próxima investigación — comportamiento ya previsto por el propio
  mecanismo de versionado, no un caso especial.

**Negativas**

- Mismo costo de fricción que anticipaba ADR-0003: cualquier corrección
  futura, por menor que sea, requerirá otro ADR sucesor y otra versión.
- Todo usuario recurrente que ya había aceptado la v1 vuelve a ver el
  modal de consentimiento una vez más.

## Alternativas consideradas

- **Dejar el texto en "1.000" como cifra conservadora** (el usuario nunca
  vería menos de lo prometido, solo potencialmente más): descartada — un
  texto legal que subestima deliberadamente el límite real dejaría de ser
  una descripción exacta de qué se envía, aunque el error fuera "seguro".
- **No versionar y editar el texto en el sitio**: descartada por el mismo
  motivo que en ADR-0003 — el consentimiento ya aceptado debe seguir
  reflejando el texto que el usuario realmente vio.

## Requisitos, contratos y fases afectados

RF-104, RF-802, RNF-012. Fase F3 (F3-7B) y el incremento que sube el
límite de `context_hint` en `contracts/api-rest.md` §2,
`backend/app/schemas.py` y el frontend. No introduce ningún requisito
nuevo — es la propagación de una decisión técnica ya aprobada (subir
`context_hint` a 2.000 caracteres) al único texto legal que la citaba.

## Evidencia y fecha de aprobación humana

Aprobado por Juan Camilo Grajales B. en la sesión que autorizó subir el
límite de `context_hint` de 1.000 a 2.000 caracteres (2026-08-03), tras
confirmarse explícitamente que el cambio implicaba actualizar este texto y
subir `consentVersion`. Implementado en
`frontend/components/consent/ConsentDialog.jsx` (`CONSENT_TITLE`, párrafos
y etiqueta del opt-in reproducidos literalmente, sin cambios salvo la
cifra) y `frontend/lib/session/consent.js`
(`CURRENT_CONSENT_VERSION = 2`), con prueba de texto literal en
`frontend/tests/unit/consent/ConsentDialog.test.jsx`.

## Sucesor

Ninguno. Una futura versión 3 del texto reemplazará este ADR o se
registrará como ADR sucesor, según corresponda cuando se apruebe.
