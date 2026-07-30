# T-702 — Checklist de despliegue en Vercel (preparación documental, F9-01)

**Estado:** preparación documental únicamente. **T-702 no se ejecuta en este
incremento** — bloqueada por T-701 (backend certificado con
`AGENT_RUNTIME=deterministic`), que a su vez depende del cierre de T-617.
Este documento no despliega, no promueve producción ni cambia configuración
remota.

## 0. Bloqueos de entrada (no promocionar mientras estén abiertos)

- [ ] T-617 cerrada (deriva de contrato del backend resuelta).
- [ ] T-701 cerrada: backend determinista certificado y accesible en el
      dominio de producción, sin `AGENT_RUNTIME` distinto de
      `deterministic` y sin `EVAL_MODE` activo.
- [ ] D-CI-02 resuelta o explícitamente aceptada por quien apruebe el merge
      (alcance acumulado del PR #28 frente a `v2`; ver
      `docs/frontend-v2/release/deudas-no-bloqueantes-v2.0.0-rc1.md`).

## 1. Configuración del proyecto Vercel

- [ ] **Root Directory** del proyecto Vercel = `frontend/` (monorepo). Ver
      `docs/frontend-v2/release/f9-01-dependencies-and-bundle.md` §7
      ("Diagnóstico Vercel confirmado", F9-01-R1): `rootDirectory: null` es
      la **causa confirmada** de `errorCode: missing_pages_app` en el
      deployment `dpl_EXv2Wsqsd5ULxAut7m5N9oWGy5kh` del PR #28 (Vercel
      ejecuta `next build` en `/vercel/path0`, donde no existe `pages/` ni
      `app/`). Fijar Root Directory es la **remediación pendiente de
      ejecución**; su **resultado posterior sigue sin verificarse** — ver
      también el ítem siguiente antes de asumir que basta por sí solo.
- [ ] Revisar y normalizar (con autorización previa, no como parte de este
      checklist) los overrides de **Build Command** / **Install Command**
      del proyecto Vercel: los mismos logs muestran Next.js 14.1.3 y
      `npm run vercel-build`, que no coinciden con `next@14.2.35` ni con el
      único script `build` de `frontend/package.json`. Decidir de forma
      explícita si se descarta la caché de build antes del siguiente
      intento. Ver
      `docs/frontend-v2/release/f9-01-dependencies-and-bundle.md` §8.
- [ ] **Rama objetivo de producción/preview relevante:** `v2`, únicamente
      cuando la estrategia de integración de D-CI-02 esté acordada y
      ejecutada. No apuntar Vercel a `feat/frontend-v2` como rama de
      producción.
- [ ] Framework detectado: Next.js (Pages Router). Comando de build/instalar
      = los por defecto de Next.js (`next build` / `npm ci`) salvo que el
      Root Directory ya los resuelva correctamente al fijarlo a `frontend/`.

## 2. Variables de entorno

- [ ] `NEXT_PUBLIC_BACKEND_URL=https://api.cuestiondedatos.com` configurada
      en el entorno de Preview (y Producción cuando aplique). No usar
      `localhost` ni un valor por defecto silencioso.
- [ ] `CORS_ALLOWED_ORIGINS` del **backend** incluye el origen **exacto** del
      preview de Vercel para esta rama/proyecto (por ejemplo, el dominio de
      preview real que Vercel asigna al desplegar desde `v2`). **Prohibido
      usar el comodín `*.vercel.app`** (plan.md §11 / implementation-plan.md
      §21.3).
- [ ] Ninguna clave de proveedor de IA (`GOOGLE_API_KEY` u otra) presente en
      variables de entorno del frontend. El frontend v2 no debe declarar
      credenciales de proveedor — solo el backend las usa.
- [ ] Confirmar que ninguna variable con secretos se marcó como
      `NEXT_PUBLIC_*` por error (esas se exponen en el bundle cliente).

## 3. Verificación funcional en el preview desplegado

- [ ] `/app` carga sin errores de consola y sin 404 de assets.
- [ ] El modal de consentimiento aparece antes de cualquier `POST` a
      `/v2/agent/query`; sin aceptar consentimiento, no hay `POST` (RF-802).
- [ ] El stream SSE conecta contra el backend real (`fetch` + `Authorization`,
      no `EventSource`), muestra pasos en español claro y llega a un estado
      terminal (`completed`, `no_evidence`, `interrupted` o `failed`).
- [ ] Reconexión con `Last-Event-ID` tras un corte de red no duplica ni
      pierde eventos (RF-209, R-03).
- [ ] El token de corrida no aparece en la URL, el DOM, la consola del
      navegador ni el bundle servido — repetir `npm run audit:bundle` contra
      el build de ese despliegue si es posible, o inspeccionar manualmente
      Network/Elements del preview.
- [ ] Persistencia local del documento: autoguardado ≤5 s, recarga de página
      restaura el documento (RF-102).
- [ ] Descarga `.docx` funciona en el preview real y el archivo generado
      abre sin reparación en Word (o queda registrado como verificación
      humana pendiente si no hay Word disponible en ese momento).
- [ ] `axe` sin violaciones críticas en `/app` contra el preview real;
      reflujo verificado a 320 px de ancho (RNF-007).

## 4. Rollback

- [ ] **Opción preferida:** promover el despliegue anterior conocido-bueno
      desde el panel de Vercel (`Promote` de un deployment previo). No se
      ejecuta como parte de este documento, solo se deja documentado el
      mecanismo.
- [ ] Si el rollback necesario es específicamente el de la limpieza de
      dependencias de F9-01: revertir el **commit completo** de F9-01, o si
      no es posible aislar un solo commit, **restaurar conjuntamente** los
      tres archivos que cambiaron juntos —
      `frontend/package.json`, `frontend/package-lock.json` **y**
      `frontend/pages/_app.js` (ver
      `docs/frontend-v2/release/f9-01-dependencies-and-bundle.md` §3 para el
      detalle exacto). Un `npm install <paquete>@<versión previa>` aislado
      **no es suficiente**: no restaura por sí solo la línea de import CSS
      de `katex` eliminada de `pages/_app.js`, y dejaría
      `package-lock.json` inconsistente con `package.json` si solo se
      reinstala un paquete suelto.

## 5. Condición de no promoción

- [ ] **No promocionar a producción** mientras T-617 y/o T-701 permanezcan
      abiertas, independientemente de que el preview técnico funcione.
- [ ] No marcar T-702 como iniciada ni cerrada desde este documento: es
      preparación, no ejecución.

## 6. Verificación previa de dependencias (heredado de F9-01)

- [ ] `npm run build` limpio, `npm run audit:bundle` sin hallazgos y
      `npm audit --omit=dev --audit-level=critical` sin críticas — ejecutados
      localmente antes de cada intento de despliegue (ver
      `docs/frontend-v2/release/f9-01-dependencies-and-bundle.md`).
- [ ] Confirmar que `react-joyride` y `framer-motion` (diferidas hasta
      T-704) no generan advertencias de build nuevas en el entorno de
      Vercel — su comportamiento en Next.js local no garantiza paridad
      exacta con el entorno de build de Vercel.

## 7. No inventado en este documento

No se registran dominios, tokens, IDs de proyecto sensibles ni estados de
infraestructura no verificados. El identificador de proyecto Vercel
(`prj_ImHZSLC1HRh9kSya5JBtjsh201my`) y el de equipo
(`team_XLkYbGuSMsHfoCaJBikTrhkf`) provienen del comentario público del bot de
Vercel en el PR #28 (integración GitHub, metadato `[vc]:` codificado en
base64), no de una fuente inventada.

## 8. Referencia — diagnóstico del fallo actual del preview

Ver `docs/frontend-v2/release/f9-01-dependencies-and-bundle.md` §7
("Diagnóstico Vercel confirmado") y §8 ("Precaución adicional antes de un
futuro redeploy") para el detalle completo, incluida la evidencia de
`errorCode: missing_pages_app`, el directorio de ejecución
`/vercel/path0`, el metadato `isMonorepo: true` / `rootDirectory: null`, y
el desajuste detectado entre la versión de Next (14.1.3 en los logs de
Vercel vs. `14.2.35` en `frontend/package.json`) y el comando de build
(`npm run vercel-build` vs. el único script `build` declarado).

Resumen: Root Directory = `frontend/` es la **causa confirmada** del error
`missing_pages_app` actual; la corrección (Project Settings → General →
Root Directory) es una **remediación pendiente de ejecución**; y su
**resultado posterior sigue sin verificarse** — no se afirma que resuelva el
despliegue por sí sola mientras el desajuste de versión de Next / comando de
build (sección 1 de este documento) no se revise también.
