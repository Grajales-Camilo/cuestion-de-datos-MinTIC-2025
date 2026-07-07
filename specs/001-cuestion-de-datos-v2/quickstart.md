# Quickstart — Ejecutar y Comprobar Cuestión de Datos v2.0

**Versión:** 1.0.0 · Describe el sistema COMPLETO implementado (todas las fases de tasks.md, incluida la migración T-104B). Durante fases intermedias, sigue la tarea correspondiente en tasks.md en lugar de esta guía.

> Guía para levantar el sistema completo en local y comprobar que funciona. Si algo falla, revisa §8 (problemas frecuentes).

---

## 1. Prerrequisitos

| Herramienta | Versión mínima | Verificar con |
|---|---|---|
| Node.js | 18 | `node -v` |
| Python | 3.12 | `python --version` |
| Git | 2.40 | `git --version` |
| Docker Desktop (PostgreSQL local vía `compose.yaml`) | Compose v2 | `docker compose version` |
| `GOOGLE_API_KEY`, `SOCRATA_APP_TOKEN` | — | tasks.md T-002 |

> **Nota:** el desarrollo local NO requiere Supabase ni Neon. Los servicios gestionados son solo para **despliegue** (tasks.md T-701); si vas a probar contra una base remota, usa `DATABASE_URL=postgresql://usuario:clave@host-remoto:5432/base`.

## 2. Clonar y configurar

```bash
git clone https://github.com/Grajales-Camilo/cuestion-de-datos-MinTIC-2025.git
cd cuestion-de-datos-MinTIC-2025
git checkout v2
```

**Backend:**
```bash
cd backend
python -m venv .venv
# Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
# Windows (cmd):
.venv\Scripts\activate.bat
# Linux/Mac:
source .venv/bin/activate
pip install -e ".[dev]"
copy .env.example .env        # (cp en Linux/Mac)
```
Edita `backend/.env` con tus valores reales:
```env
DATABASE_URL=postgresql://usuario:clave@localhost:5432/cuestion_de_datos   # local (compose.yaml); en despliegue: host remoto
GOOGLE_API_KEY=...                  # T-002
SOCRATA_APP_TOKEN=...               # T-002
LLM_PROVIDER=google
LLM_MODEL=gemini-2.5-flash
EMBEDDING_MODEL=<el decidido en T-205 — ver research.md §1>
AGENT_MAX_STEPS=10
RUN_MAX_DURATION_S=600
RUN_HEARTBEAT_TIMEOUT_S=120
RETENTION_USER_DAYS=90                             # el token de corrida expira junto con esta retención
CATALOG_STALE_AFTER_DAYS=8                         # marca index_stale si un dataset no se sincroniza en esta ventana
CORS_ALLOWED_ORIGINS=http://localhost:3000         # producción: dominios de cuestiondedatos.com; previews: origen exacto, sin comodines
ADMIN_TOKEN=elige-un-token-largo-aleatorio
EVAL_MODE=false
```

**Frontend:**
```bash
cd ../frontend
npm install
copy .env.example .env.local
# NEXT_PUBLIC_BACKEND_URL=http://localhost:8000   (el navegador se conecta directo al backend; CORS ya permite localhost:3000)
```

## 3. Base de datos e índice del catálogo

Primero levanta PostgreSQL local (desde la raíz del repo; extensiones `vector` y `pg_trgm` incluidas en la imagen/init):
```bash
docker compose up -d db
docker compose ps                         # espera el healthcheck "healthy"
```
Luego:
```bash
cd backend
alembic upgrade head                      # crea todas las tablas (la de embeddings existe tras T-104B)
python scripts/ingest_catalog.py          # ~15-30 min: descarga metadatos del catálogo
python scripts/load_divipola.py           # maestro de municipios
python scripts/build_embeddings.py        # genera el índice semántico
```
**Comprobación:**
```bash
python -c "from app.db.session import quick_counts; quick_counts()"
# Esperado: catalog_datasets >= 7000, catalog_embeddings == datasets activos, divipola >= 1100
```
> Atajo: para probar sin ingesta completa, `python scripts/ingest_catalog.py --limit 200` indexa una muestra (suficiente para desarrollo, insuficiente para RNF-010).

## 4. Levantar los servicios

Terminal 1 — backend:
```bash
cd backend && uvicorn app.main:app --reload --port 8000
```
Terminal 2 — frontend:
```bash
cd frontend && npm run dev
```
Abre `http://localhost:3000`.

## 5. Comprobaciones de humo (en orden)

1. **Salud:** `curl http://localhost:8000/v2/health` → `"status": "ok"` con los 3 checks en `ok`.
2. **Búsqueda semántica:** `curl "http://localhost:8000/v2/catalog/search?q=desercion%20escolar&k=5"` → datasets del sector educación en el top.
3. **Agente por API:**
   ```bash
   curl -X POST http://localhost:8000/v2/agent/query \
     -H "Content-Type: application/json" \
     -d '{"question": "¿Cuántos programas de educación para el trabajo hay registrados en Antioquia?"}'
   # → {"run_id": "...", "run_access_token": "cdt_rt_...", "token_expires_at": "...", "stream_url": "..."}
   # GUARDA el token: solo se entrega esta vez.
   curl -N -H "Authorization: Bearer <run_access_token>" http://localhost:8000/v2/agent/stream/<run_id>
   # → eventos id:/step ... y un evento answer final con evidence[], claims[] y quality
   ```
3b. **Autorización y reconexión:** el mismo stream SIN el header → `401 UNAUTHORIZED`. Corta el `curl` a mitad de corrida y reconecta añadiendo `-H "Last-Event-ID: <último id recibido>"` → recibes los eventos faltantes sin duplicados (RF-209). Para borrar la corrida: `curl -X DELETE -H "Authorization: Bearer <token>" http://localhost:8000/v2/agent/runs/<run_id>` → `204`.
4. **Honestidad:** pregunta algo sin respuesta en el catálogo (p. ej. "¿Cuál es el precio promedio del arriendo en Marte?") → `status: "no_evidence"`, sin cifras inventadas. Verifica además que toda cifra del `summary` de la comprobación 3 aparece como `display_value` en `claims[]` (RF-208).
5. **UI completa (ESC-01):** en el navegador, elige la plantilla MGA, escribe un problema en "Identificación del Problema", presiona **Investigar** y verifica: línea de tiempo de pasos en vivo → tarjeta de evidencia con badge de calidad → botón insertar → la cita aparece en el documento.
6. **Persistencia (ESC-08):** recarga el navegador; el documento y sus citas siguen ahí.

## 6. Ejecutar las pruebas

```bash
cd backend
ruff check . && pytest                    # unitarias + contrato (rápidas, sin red)
pytest -m integration                     # integración real con Socrata (requiere red)
python -m eval.run --suite golden-v1 --limit 10   # smoke de evaluación (usa LLM: consume cuota)
cd ../frontend
npm run test:e2e                          # Playwright (requiere ambos servicios arriba)
```
Detalle completo de suites y umbrales: [`pruebas.md`](./pruebas.md).

## 7. Verificar credenciales sueltas (si algo falla)

```bash
# Gemini
curl "https://generativelanguage.googleapis.com/v1beta/models?key=$GOOGLE_API_KEY" | head -c 200
# Socrata
curl -H "X-App-Token: $SOCRATA_APP_TOKEN" "https://www.datos.gov.co/resource/2d3i-f9wd.json?\$limit=1"
# Postgres
psql "$DATABASE_URL" -c "SELECT 1;"
```

## 8. Problemas frecuentes

| Síntoma | Causa probable | Solución |
|---|---|---|
| `/v2/health` → `catalog_index: degraded` | Ingesta no ejecutada | §3. |
| Embeddings lentísimos en local | Modelo local en CPU | Usa `--batch-size 16` con una muestra (`--limit 200`); el trade-off local vs gestionado es parte de la decisión de T-205 (research.md §1). |
| `docker compose up` falla o el healthcheck nunca pasa | Docker Desktop apagado o puerto 5432 ocupado | Arranca Docker Desktop; cambia el puerto en `.env` del compose. |
| `429` de Gemini en pruebas | Cuota del tier gratuito agotada | Espera la ventana o reduce `--limit` del eval. |
| SSE no muestra pasos en el navegador | URL del backend o CORS mal configurados | Revisa `NEXT_PUBLIC_BACKEND_URL` en `frontend/.env.local` y que el origen `http://localhost:3000` esté permitido en el CORS del backend; recuerda que el consumo es con `fetch()` streaming, no `EventSource`. |
| Socrata responde 403 | App token ausente/incorrecto | §7, segunda línea. |
| `alembic upgrade` falla con `type "vector" does not exist` | Extensión no habilitada | T-001 paso 3. |
