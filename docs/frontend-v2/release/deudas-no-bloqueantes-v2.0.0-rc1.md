# Registro de deudas no bloqueantes — Frontend v2.0.0-rc1

**Fecha de corte:** 2026-07-30
**Rama:** `feat/frontend-v2`
**Estado del candidato:** `READY_FOR_CI`, no liberado
**Fuente de cierre:** F8-01, F8-01-R1, F8-02 y F8-02-R1

Este documento mantiene en un solo lugar las deudas aceptadas que no impiden
versionar ni ejecutar CI. No convierte una deuda en excepción permanente: cada
entrada tiene una condición comprobable de cierre. Siguen siendo bloqueantes
la pérdida de datos, el incumplimiento contractual, la seguridad o privacidad,
la fabricación de evidencia y una prueba esencial no reproducible.

## Prioridad de atención

| ID | Tipo | Prioridad | Estado | Resumen |
|---|---|---:|---|---|
| D-UI-01 | Producto/accesibilidad | P2 | Abierta | NVDA repite parte del modal de consentimiento. |
| D-UI-02 | Producto/visual | P2 | Abierta | El badge de aporte manual puede no pintar su texto en el primer render. |
| D-SEC-01 | Dependencias | P1 | Abierta y monitorizada | `npm audit` no tiene críticas, pero mantiene vulnerabilidades altas y moderadas. |
| D-CI-01 | Release | P1 | Pendiente | T-505 requiere una ejecución real y verde de GitHub Actions. |
| D-ENV-01 | Windows/Playwright | P3 | Mitigada | El Chromium embebido falla por SideBySide en el equipo revisor. |
| D-ENV-02 | Tooling | P3 | Abierta | Browserslist y datos de compatibilidad emiten avisos de actualización. |
| D-ENV-03 | Pruebas DOM | P3 | Abierta | jsdom no implementa por completo canvas, navegación y algunas APIs de Blob. |
| D-ENV-04 | Git local | P3 | Abierta | El archivo global de exclusiones y `.pytest_cache` generan avisos de permisos. |
| D-ENV-05 | Navegador MCP | P3 | Abierta | El panel MCP no siempre compone capturas; Playwright es el respaldo reproducible. |
| D-PERF-01 | Arnés E2E | P3 | Mitigada | RNF-008 puede ser inestable bajo paralelismo alto; tiene suite aislada de 1 worker. |
| D-DOC-01 | Decisión de producto | P2 | Pendiente humana | D-6: contenido de la plantilla de plan de desarrollo no está aprobado. |

## Detalle y condición de cierre

### D-UI-01 — Doble lectura de NVDA en consentimiento

- **Evidencia:** `docs/release-wcag-v2.0.0-rc1.md`, defecto D-1.
- **Impacto:** repetición molesta para usuarios de lector de pantalla; no impide
  comprender ni completar el consentimiento.
- **Descartado:** no depende de `reactStrictMode`; también ocurre en producción.
- **Cierre:** reproducir con un caso mínimo Chrome + NVDA, identificar la relación
  ARIA o el problema de composición y reconfirmar en NVDA real sin duplicación.

### D-UI-02 — Badge de aporte manual no pinta en el primer render

- **Evidencia:** `docs/release-wcag-v2.0.0-rc1.md`, defecto D-4.
- **Impacto:** una señal textual visual puede faltar temporalmente para usuarios
  videntes; NVDA conserva el nombre accesible correcto.
- **Clasificación:** deuda visual de producto, no deuda ambiental.
- **Cierre:** reproducción visual automatizada estable, corrección de pintura y
  comprobación a 1440 px, 320 px y con lector de pantalla.

### D-SEC-01 — Vulnerabilidades altas y moderadas

Captura de `npm audit` del 2026-07-30, sin ejecutar `audit fix` ni `--force`:

| Árbol | Críticas | Altas | Moderadas | Total |
|---|---:|---:|---:|---:|
| Producción (`--omit=dev`) | 0 | 9 | 43 | 52 |
| Completo | 0 | 30 | 48 | 78 |

Dependencias directas señaladas en producción: `next` (alta), Tiptap,
Tailwind y `react-globe.gl` (moderadas). El árbol completo añade principalmente
la cadena de ESLint/Vite y tooling. El gate vigente bloquea cualquier crítica,
pero estas deudas deben revisarse periódicamente; los números pueden cambiar
cuando se actualiza la base de avisos de npm.

- **Cierre:** preparar incrementos separados con actualización compatible,
  pruebas focalizadas, suite completa, build y auditoría posterior. No aplicar
  correcciones mayores automáticas ni retirar dependencias sin verificar uso.

### D-CI-01 — T-505 pendiente de GitHub Actions real

- **Evidencia local:** lint, 899 unitarias, 91 E2E, build, auditor de bundle y
  gates críticos verdes en F8-02-R1.
- **Pendiente:** el workflow `.github/workflows/ci.yml` debe ejecutarse sobre el
  commit publicado; la evidencia local no sustituye esa corrida.
- **Cierre:** workflow real verde y registro de URL, commit SHA y resultado en
  el PR. Solo entonces se puede cerrar T-505.

### D-ENV-01 — Chromium embebido de Playwright en Windows

- **Síntoma:** `spawn UNKNOWN` y error SideBySide del ensamblado del Chrome for
  Testing instalado por Playwright.
- **Mitigación vigente:** canal `chrome` del sistema en Windows local; Chromium
  embebido en CI Linux.
- **Cierre:** una versión futura de Playwright/Chromium inicia de forma
  reproducible en Windows o se identifica y repara el ensamblado requerido.

### D-ENV-02 — Datos de compatibilidad del navegador desactualizados

- **Síntoma:** avisos de Browserslist, `caniuse-lite` o
  `baseline-browser-mapping` durante build.
- **Impacto:** no cambia el bundle servido ni causa un fallo actual.
- **Cierre:** actualización controlada del lockfile, seguida por build y E2E.

### D-ENV-03 — Limitaciones conocidas de jsdom

- **Síntoma:** avisos relacionados con canvas, navegación y
  `Blob.prototype.arrayBuffer()`.
- **Mitigación:** dobles acotados en unitarias y comprobaciones reales en
  Playwright/Chrome; la producción no usa los fallbacks de prueba.
- **Cierre:** actualizar jsdom cuando sea compatible o sustituir cada workaround
  por la API nativa disponible, sin reducir la cobertura en navegador real.

### D-ENV-04 — Avisos de permisos del entorno Git/Python

- **Síntoma:** Git no puede leer `C:\Users\graja\.config\git\ignore` y algunas
  operaciones no pueden inspeccionar `.pytest_cache`.
- **Impacto:** no altera los archivos candidatos ni la selección explícita de
  staging, pero ensucia la salida de diagnóstico.
- **Cierre:** corregir permisos del archivo de exclusiones global y de la caché
  fuera del repositorio, sin cambiar reglas del proyecto para ocultar el fallo.

### D-ENV-05 — Capturas del panel de navegador MCP

- **Síntoma:** en algunas sesiones el panel no compone frames o screenshots.
- **Mitigación:** Playwright con tamaños explícitos y artefactos guardados en
  `docs/frontend-v2/design/`.
- **Cierre:** verificar una actualización del MCP que capture las mismas
  superficies de forma estable; Playwright sigue siendo la evidencia primaria.

### D-PERF-01 — Contención de RNF-008 bajo paralelismo

- **Síntoma histórico:** el umbral de feedback de 500 ms podía superar el límite
  al compartir CPU con varios workers.
- **Mitigación vigente:** `playwright.perf.config.js`, un worker, tres
  repeticiones y ejecución separada en CI.
- **Cierre:** mantener diez corridas consecutivas verdes en el hardware de CI;
  si reaparece, diagnosticar presupuesto causal antes de cambiar el umbral.

### D-DOC-01 — Plantilla de plan de desarrollo (D-6)

- **Estado:** decisión humana pendiente; no se fabricó contenido institucional.
- **Impacto:** bloquea únicamente esa plantilla, no el documento libre ni las
  funciones cerradas hasta F8.
- **Cierre:** aprobación explícita del contenido por una persona con criterio de
  política pública y registro mediante ADR antes de implementarla.

## Deudas cerradas o absorbidas por el diseño vigente

- La vulnerabilidad crítica de Next 14.1.3 se cerró al actualizar dentro de la
  línea 14.x.
- La vulnerabilidad crítica de Vitest 2 se cerró con Vitest 4.1.10 y Vite 6.4.3.
- D-5, pérdida de citas/aportes al seguir escribiendo, quedó cerrada con
  `trailingNode` y cuatro regresiones conductuales de F8-02-R1.
- El flake histórico de RNF-008 ya no comparte el arnés funcional paralelo;
  permanece en seguimiento como D-PERF-01, no como fallo abierto del producto.

## Regla de mantenimiento

Al corregir una deuda, no se elimina su historia: se cambia su estado a
`Cerrada`, se registra el commit/PR y la evidencia de verificación. Las cifras
de `npm audit` se actualizan solo con una nueva ejecución fechada.
