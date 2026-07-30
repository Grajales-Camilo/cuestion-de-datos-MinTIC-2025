# Registro de deudas no bloqueantes — Frontend v2.0.0-rc1

**Fecha de corte:** 2026-07-30
**Rama:** `feat/frontend-v2`
**Estado del candidato:** `CI_VERIFIED`, no liberado
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
| D-SEC-01 | Dependencias | P1 | Abierta y monitorizada | `npm audit` no tiene críticas; el árbol vigente mantiene 4 altas y 1 moderada en producción, y 18 altas y 1 moderada en total. |
| D-CI-01 | Release | P1 | Cerrada | T-505 se verificó nuevamente en GitHub Actions CI `30545873307` sobre el HEAD actual. |
| D-CI-02 | Versionado | P1 | **Cerrada 2026-07-30** | PR #29 integró primero el backend; contra el nuevo `origin/v2`, PR #28 contiene 14 commits y 518 archivos, sin `backend/`, y su merge limpio produce exactamente el árbol frontend. |
| D-ENV-01 | Windows/Playwright | P3 | Mitigada | El Chromium embebido falla por SideBySide en el equipo revisor. |
| D-ENV-02 | Tooling | P3 | Abierta | Browserslist y datos de compatibilidad emiten avisos de actualización. |
| D-ENV-03 | Pruebas DOM | P3 | Abierta | jsdom no implementa por completo canvas, navegación y algunas APIs de Blob. |
| D-ENV-04 | Git local | P3 | Abierta | El archivo global de exclusiones y `.pytest_cache` generan avisos de permisos. |
| D-ENV-05 | Navegador MCP | P3 | Abierta | El panel MCP no siempre compone capturas; Playwright es el respaldo reproducible. |
| D-PERF-01 | Arnés E2E | P3 | Mitigada | RNF-008 puede ser inestable bajo paralelismo alto; tiene suite aislada de 1 worker. |
| D-DOC-01 | Decisión de producto | P2 | **Cerrada 2026-07-30** | Las estructuras aprobadas en ADR-0004/ADR-0005 fueron implementadas y verificadas; RF-101 queda cumplido. |

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

Captura de `npm audit --json` del 2026-07-30 sobre el árbol post-F9, sin
ejecutar `audit fix` ni `--force`; las mismas cifras aparecen en CI
`30545873307` sobre `1945648f`:

| Árbol | Críticas | Altas | Moderadas | Total |
|---|---:|---:|---:|---:|
| Producción (`--omit=dev`) | 0 | 4 | 1 | 5 |
| Completo | 0 | 18 | 1 | 19 |

La única dependencia directa señalada en producción es `next`; el árbol
completo añade como directas `eslint` y `eslint-config-next`, además de sus
cadenas transitivas de tooling. Las dependencias retiradas en F9 no se
atribuyen a esta deuda. El gate vigente bloquea cualquier crítica, pero estos
hallazgos altos y moderados deben revisarse periódicamente; los números pueden
cambiar cuando se actualiza la base de avisos de npm.

- **Cierre:** preparar incrementos separados con actualización compatible,
  pruebas focalizadas, suite completa, build y auditoría posterior. No aplicar
  correcciones mayores automáticas ni retirar dependencias sin verificar uso.

### D-CI-01 — T-505 verificada en GitHub Actions real

- **Evidencia local/archivada:** lint, 930 unitarias, 95 E2E, build, auditor
  de bundle y gates críticos verdes.
- **Evidencia remota vigente:** GitHub Actions CI `30545873307`, commit
  `1945648f011570e87676140be604aab477c70a7d`, con jobs Backend y Frontend en
  `success`. El frontend completó lint, unitarias, build, RNF-011, auditorías
  críticas, E2E funcional, RNF-008 aislado y E2E de producción.
- **Estado:** cerrada el 2026-07-30. El alcance acumulado del PR sigue separado
  en D-CI-02 y no invalida el resultado del workflow.

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

### D-CI-02 — Alcance acumulado del PR

- **Estado:** cerrada técnicamente el 2026-07-30. PR #29 integró primero el
  backend determinista en `v2`; su merge commit es
  `5b138a74d91eac98ec7cf3bed943364f1940fd2d`.
- **Evidencia Git autoritativa:** HEAD de `feat/frontend-v2`
  `1945648f011570e87676140be604aab477c70a7d`; base `origin/v2`
  `5b138a74d91eac98ec7cf3bed943364f1940fd2d`; merge-base
  `fa08ee5bc2ab2ac728cab4173a9430e1fc8497e5`; diferencia de 14 commits y
  518 archivos, ninguno bajo `backend/`.
- **Prueba de integración:** `git merge-tree --write-tree origin/v2
  origin/feat/frontend-v2` terminó sin conflicto y produjo el árbol
  `acc638e708a77aea84ad5ec520aa125c2299fa0a`, exactamente igual al árbol de
  `origin/feat/frontend-v2`.
- **Resultado:** desapareció la historia acumulada que motivaba la deuda; el
  alcance restante de PR #28 es frontend, documentación e instrucciones
  asociadas. El PR permanece borrador por decisión de proceso, no por D-CI-02.

### D-PERF-01 — Contención de RNF-008 bajo paralelismo

- **Síntoma histórico:** el umbral de feedback de 500 ms podía superar el límite
  al compartir CPU con varios workers.
- **Mitigación vigente:** `playwright.perf.config.js`, un worker, tres
  repeticiones y ejecución separada en CI.
- **Cierre:** mantener diez corridas consecutivas verdes en el hardware de CI;
  si reaparece, diagnosticar presupuesto causal antes de cambiar el umbral.

### D-DOC-01 — Plantillas MGA y plan de desarrollo (RF-101)

- **Estado:** **cerrada el 2026-07-30**. Las estructuras aprobadas por Juan
  Camilo Grajales B. en ADR-0004 (plan de desarrollo, cinco secciones) y
  ADR-0005 (MGA, siete secciones) se implementaron junto con la plantilla
  libre en `frontend/lib/document/documentModel.js`; la selección accesible
  para documentos nuevos quedó integrada mediante `TemplatePicker.jsx`.
- **Evidencia de cierre:** núcleo, validación, persistencia y exportación en
  commit `1ddc25f`; selector visual, restauración no destructiva y regresiones
  E2E en `199fa1e`; 930 pruebas unitarias y 95 E2E funcionales verdes; build,
  auditoría de bundle y CI remoto `30543431200` en verde para Backend y
  Frontend.
- **Resultado:** RF-101 queda **implementado y verificado**. Un documento
  restaurado se abre intacto y no ofrece cambio de plantilla. El futuro flujo
  “Nuevo documento” con respaldo y confirmación no forma parte de RF-101 ni
  reabre D-DOC-01.

## Deudas cerradas o absorbidas por el diseño vigente

- D-DOC-01 se cerró al implementar y verificar las plantillas libre, MGA y
  plan de desarrollo exigidas por RF-101 (`1ddc25f`, `199fa1e`, CI
  `30543431200`).
- D-CI-02 se cerró después de que PR #29 integrara primero el backend: 14
  commits, 518 archivos, cero `backend/` y árbol de merge idéntico al de
  `feat/frontend-v2`.
- La vulnerabilidad crítica de Next 14.1.3 se cerró al actualizar dentro de la
  línea 14.x.
- La vulnerabilidad crítica de Vitest 2 se cerró con Vitest 4.1.10 y Vite 6.4.3.
- D-5, pérdida de citas/aportes al seguir escribiendo, quedó cerrada con
  `trailingNode` y cuatro regresiones conductuales de F8-02-R1.
- El flake histórico de RNF-008 ya no comparte el arnés funcional paralelo;
  permanece en seguimiento como D-PERF-01, no como fallo abierto del producto.
- D-ENV-06 se cerró al eliminar los dos índices duplicados y reconstruir uno
  solo desde cero: 12.646 nodos, 43.590 aristas y símbolos F7/F8 verificables.
- TEST-01, el timeout observado en
  `tests/unit/document/DocumentSections.test.jsx`, se cerró como
  `NOT_REPRODUCED`: 83 corridas de comandos (caso aislado, archivo, suite
  documental, suite completa y contención moderada) terminaron sin fallos. Los
  dos timeouts previos coincidieron con una saturación artificial de cinco
  procesos Vitest pesados ejecutados simultáneamente. No se modificaron código,
  pruebas, timeouts ni retries. Se reabrirá únicamente si reaparece durante un
  `npm run test` normal, sin carga externa, o en CI real.

## Regla de mantenimiento

Al corregir una deuda, no se elimina su historia: se cambia su estado a
`Cerrada`, se registra el commit/PR y la evidencia de verificación. Las cifras
de `npm audit` se actualizan solo con una nueva ejecución fechada.
