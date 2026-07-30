# Inventario de versionado controlado — Frontend v2.0.0-rc1

**Fecha:** 2026-07-30
**Rama:** `feat/frontend-v2`
**Commit base del trabajo acumulado:** `5853251cc593e32008d2afc8ede7201efe19c6b9`

El worktree se congeló después de F8-02-R1. Este inventario define el alcance
del primer versionado del frontend v2 y evita que un staging amplio mezcle
trabajo de evaluación del backend o documentos históricos independientes.

## Incluido

| Grupo | Alcance | Archivos nuevos al congelar |
|---|---|---:|
| Implementación y pruebas | `frontend/` | 207 |
| Documentación frontend v2 | `docs/frontend-v2/` | 34, incluido este inventario |
| Actas manuales de release | `docs/release-wcag-v2.0.0-rc1.md`, `docs/release-rnf-012-v2.0.0-rc1.md` | 2 |
| Contexto de producto/diseño | `PRODUCT.md`, `DESIGN.md` | 2 |
| Impeccable compartido | `.agents/skills/impeccable/` | 127 |
| Integración Claude Code | `.claude/skills/impeccable/` | 123 |
| Integración Codex | `.codex/hooks.json` | 1 |
| Configuración Impeccable | `.impeccable/` excepto cachés | 3 |
| Archivos rastreados modificados | CI, `.gitignore`, `CLAUDE.md` y configuración/dependencias del frontend | 9 |

La lista efectiva de staging usa rutas explícitas. No se usa `git add -A`.

## Excluido y preservado

| Grupo | Motivo |
|---|---|
| `backend/eval/reports/` (55 archivos nuevos) | Evidencia de evaluaciones del backend preexistente, con propietario y ciclo distintos. |
| Otros documentos nuevos bajo `docs/` (15 al congelar) | Informes, figuras, prompts y entregables históricos no pertenecientes al frontend v2. |
| `.claude/settings.local.json` | Configuración personal del equipo; excluida explícitamente en `.gitignore`. |
| `.impeccable/hook.cache.json` | Caché regenerable del detector; excluida explícitamente en `.gitignore`. |
| `.env*` reales, `.next/`, `node_modules/`, `test-results/`, reportes Playwright | Secretos o artefactos locales/regenerables ya cubiertos por `.gitignore`. |

Excluir no significa borrar. Estos archivos permanecen intactos en el disco y
pueden seguir apareciendo como `untracked` cuando deliberadamente pertenecen a
otro trabajo.

## Commits creados

1. `chore(frontend): establish agent tooling and project guidance`
2. `feat(frontend): implement deterministic evidence workspace`
3. `docs(frontend): record rc1 validation and technical debt`
4. `docs(frontend): record publication constraints`

La validación final se ejecutó sobre el árbol completo después de los tres
commits iniciales. El cuarto commit registra los hallazgos de publicación y no
modifica producto ni pruebas.

## Alcance remoto observado

El PR borrador apunta a `v2` porque el workflow de CI solo escucha esa rama.
El commit base local `5853251` no está contenido en ninguna otra rama remota;
por eso el diff remoto muestra una historia acumulada de más de 149 commits y
706 archivos frente a `v2`, no solo los commits anteriores. Esta diferencia no se ocultó ni se resolvió con
rebase o force-push: queda registrada como D-CI-02 y debe resolverse antes del
merge.
