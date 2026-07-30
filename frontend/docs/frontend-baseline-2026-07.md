# Baseline del frontend — F0.1

**Fecha y hora:** 2026-07-27, 04:08–04:09 (hora local de la máquina, zona `HPS`
según `date` del entorno)
**Objetivo.** Registrar el estado medible del frontend legacy (`npm ci` +
`npm run build`) **antes** de instalar cualquier dependencia nueva de F0,
para poder comparar el efecto de los cambios de F0.2/F0.3.

## Entorno

| Campo | Valor |
|---|---|
| Sistema operativo | Windows 10.0.26200.8894 (Windows 11 Pro), shell MINGW64/Git Bash (`MINGW64_NT-10.0-26200`) |
| Node.js | v24.18.0 |
| npm | 11.6.0 |
| Rama Git | `feat/frontend-v2` |
| Commit (`HEAD`) | `5853251cc593e32008d2afc8ede7201efe19c6b9` |
| Estado Git al momento del baseline | Working tree limpio en archivos rastreados; 74 entradas untracked preexistentes (reportes de evaluación y documentación), ninguna tocada |

## Comando 1 — `npm ci`

```text
npm ci
```

- **Resultado:** éxito (exit code 0).
- **Duración:** ≈ 33.8 s (`real 0m33.800s`).
- **Paquetes instalados:** 325 añadidos, 326 auditados.
- **Advertencias:** 1 deprecación (`popper.js@1.16.1` → sugiere `@popperjs/core`, dependencia transitiva del stack legacy, no tocada en F0).
- **Vulnerabilidades reportadas por npm al instalar:** 7 (1 moderada, 5 altas, 1 crítica) — detalle completo en la sección de `npm audit` de F0.7, no se ejecutó `npm audit fix` ni `--force`.

## Comando 2 — Build limpio

Antes de compilar se resolvió la ruta absoluta de `.next` y se eliminó
únicamente ese directorio generado:

```text
Ruta eliminada: D:\Usuario\AppWebs\cuestion-de-datos-MinTIC\frontend\.next
```

```text
npm run build
```

- **Resultado:** éxito (exit code 0). `✓ Compiled successfully`.
- **Duración:** ≈ 24.0 s (`real 0m24.046s`).
- **Next.js:** 14.1.3, Pages Router. `.env.local` detectado (no leído ni impreso su contenido).

### Salida de tamaños producida por Next

```text
Route (pages)                             Size     First Load JS
┌ ○ / (925 ms)                            168 kB          247 kB
├   /_app                                 0 B              79 kB
├ ○ /404                                  181 B          79.2 kB
└ λ /api/consultar_v2                     0 B              79 kB
+ First Load JS shared by all             94.4 kB
  ├ chunks/framework-5429a50ba5373c56.js  45.2 kB
  ├ chunks/main-e257df08911799df.js       31.7 kB
  ├ css/50fe90ef13092647.css              15.4 kB
  └ other shared chunks (total)           2.1 kB

○  (Static)   prerendered as static content
λ  (Dynamic)  server-rendered on demand using Node.js
```

### Tamaño total de `.next`

| Ruta | Tamaño |
|---|---|
| `.next/` (total) | 47 MB |
| `.next/cache/` | 44 MB (caché incremental de Next/Webpack, no se versiona) |
| `.next/static/` | 2.3 MB |
| `.next/trace` | 372 KB |
| `.next/server/` | 169 KB |

El tamaño total está dominado por `.next/cache/` (caché de compilación, no
representa el peso real servido al navegador). El bundle real relevante para
el usuario es `First Load JS shared by all = 94.4 kB` + `168 kB` de la página
`/`, consistente con la tabla de rutas de Next.

### Warnings

- `[baseline-browser-mapping] The data in this module is over two months old.` — sugiere `npm i baseline-browser-mapping@latest -D`. No es un error; no se actúa en F0 (no está en el alcance de dependencias autorizadas).
- `Browserslist: browsers data (caniuse-lite) is 8 months old.` (dos veces) — sugiere `npx update-browserslist-db@latest`. Mismo tratamiento: informativo, fuera del alcance de F0.

### Errores

Ninguno. El build terminó en verde sin errores de compilación, tipos ni
linting integrado de Next.

## Conclusión del baseline

El frontend legacy compila limpio hoy, sin intervención. Este documento es la
línea base contra la cual se compara el resultado de `npm run build` después
de F0.2 (nuevas devDependencies) y F0.3 (configuración de Vitest/Playwright/
ESLint), para detectar cualquier regresión introducida por las herramientas
de calidad añadidas en F0.
