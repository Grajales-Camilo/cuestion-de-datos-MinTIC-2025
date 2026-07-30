# Fixtures reales — F0.5 (corregido en F0-R1, 2026-07-27)

Todos los fixtures de este directorio proceden de corridas **reales** del
runtime determinista (`AGENT_RUNTIME=deterministic`) del backend FastAPI.
**Ninguno fue escrito a mano desde el contrato.**

Hay dos métodos de captura distintos, cada uno etiquetado explícitamente en
la matriz de procedencia:

1. **Captura HTTP en vivo** (`completed-stream.sse.txt`, y el `completed.json`
   de la misma corrida): se inició el backend real, se envió
   `POST /v2/agent/query` real y se leyeron los **bytes crudos** que devuelve
   `GET /v2/agent/stream/{run_id}` con `httpx.stream(...).iter_bytes()`,
   volcados a disco sin reformatear. Es la captura literal del endpoint HTTP,
   no una reconstrucción.
2. **Serialización real desde PostgreSQL** (los demás `.json`): se
   reutilizaron las funciones reales de serialización del backend
   (`app.main._get_run_detail_async`, `_step_response`, `_event_response`,
   `app.schemas.materialize_textual_fact_fields`) para producir exactamente
   el mismo JSON que devolvería `GET /v2/agent/runs/{run_id}` sobre una
   corrida ya persistida. Es válido para los cinco escenarios de estado
   (`completed`, `no_evidence`, `interrupted`, `failed`) porque lo que exige
   el encargo original es fidelidad al contrato de esa respuesta, no una
   captura HTTP en vivo — esa exigencia aplica específicamente al fixture de
   **stream SSE**, que es el único que usa el método 1.

## Corrección aplicada en F0-R1 (2026-07-27)

La auditoría anterior encontró que `interrupted-stream.sse.txt` se había
reconstruido desde `agent_run_events` en vez de capturarse del endpoint HTTP
real, lo cual no se acepta como sustituto. Se reemplazó por
**`completed-stream.sse.txt`**, capturado en vivo con el método 1 contra
`GET /v2/agent/stream/{run_id}` real (ver matriz abajo). El archivo anterior
se eliminó del directorio.

## Comprobación de ausencia de secretos y datos personales

Se ejecutó una búsqueda explícita sobre los seis archivos de este directorio
para los siguientes patrones, con **cero coincidencias** en todos los casos:
`cdt_rt_`, encabezados `Authorization`, `Bearer`, cualquier literal
`token`/`access_token`/`run_access_token`, y direcciones de correo
(`[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}`). Los `run_id` se conservan
porque no son secretos (RF-801: el `run_id` identifica pero no autoriza) y no
revelan identidad de usuario.

Ninguno de los seis escenarios contiene datos personales: las preguntas y la
evidencia versan sobre entidades públicas (empresas de servicios públicos,
estaciones de monitoreo ambiental, agregados departamentales y educativos),
no sobre personas naturales identificables. No fue necesaria ninguna
transformación de anonimización; solo se omite el `run_access_token`, que
nunca se persiste en claro y por tanto no puede filtrarse desde estos
fixtures.

## Matriz de procedencia

| Archivo | Escenario | `run_id` | Commit del backend | Fecha de la corrida | Método de captura | SHA-256 |
|---|---|---|---|---|---|---|
| `completed-with-claims.json` | `completed` con `claims[]` y `label_status="verified"` | `41f11aa2-56d0-403c-81a2-6f80551c5d72` | `bb0e2a293b34edb3a3612b674c8b1e35f32b49aa` | 2026-07-24 22:48 UTC | Método 2 (serialización real desde PostgreSQL), caso `pilot-041-eca` de la evaluación golden-v2 `e638aff9-2a02-4078-98b9-56de8d01dbb3` | `9f35580f6bf8308669cc2fa517af95329dce77497eff1aa6a3e95a0573774123` |
| `no-evidence.json` | `no_evidence` (presupuesto agotado, `LLM_BUDGET_EXCEEDED`) | `0c63affd-8e8c-4f9c-b56f-0a83696d1e74` | `bb0e2a293b34edb3a3612b674c8b1e35f32b49aa` | 2026-07-24 22:51 UTC | Método 2, caso negativo `pilot-050-negativo-dato-inexistente` de la misma evaluación golden-v2 | `da47197a35e05de9f3075ed1abc1bf8efe71e26fb30d8d7003be3d46e5f7052c` |
| `failed.json` | `failed` (`SOCRATA_TIMEOUT`) | `677719d8-b448-4c10-8c77-198676e3f7d9` | `bb0e2a293b34edb3a3612b674c8b1e35f32b49aa` | 2026-07-24 22:46 UTC | Método 2, caso `pilot-039-temperatura` de la misma evaluación golden-v2 | `3816aaed2fadd977a35110bead79c9bde32b850d1f59392f25dd5ff2e0f49203` |
| `interrupted.json` | `interrupted` (`RUN_INTERRUPTED`, arranque idempotente) | `8c915e85-6d7f-4d1d-9eeb-b1f175308936` | `5853251cc593e32008d2afc8ede7201efe19c6b9` | 2026-07-27 09:22 UTC | Método 2. Producida en vivo: backend real → `POST /v2/agent/query` real → 2 eventos SSE reales leídos → `Popen.kill()` real (`TerminateProcess`, sin *shutdown* limpio, mismo mecanismo que `tests/integration/test_t300_durability.py`) → espera de lease (33 s) → reinicio → arranque idempotente confirmado | `efce879c44cc3f3f01e13c841dc3a45176a0dcd342fed2a3fe15560bb8adf9ad` |
| **`completed-stream.sse.txt`** | **Stream SSE completo, captura HTTP en vivo** (9 eventos `step` + 1 `answer` terminal) | `e6ae9a62-3394-4eee-b9e4-c76a3adf9582` | `5853251cc593e32008d2afc8ede7201efe19c6b9` | 2026-07-27 10:14 UTC | **Método 1**: `POST /v2/agent/query` real → `httpx.stream("GET", ".../v2/agent/stream/{run_id}", headers={"Authorization": "Bearer <token>"}).iter_bytes()` volcado directo a disco, `Content-Type: text/event-stream; charset=utf-8`, `200 OK`, 8.907 bytes exactos | `f94724aeed42bc5542b0ed159bda4fcf1cff16d943175d088299743e77bf959b` |

La corrida `e6ae9a62-…` terminó `completed` de verdad (confirmado también con
`GET /v2/agent/runs/{run_id}` real en la misma sesión de captura): pregunta
"¿Cuál fue el promedio de deserción escolar en el departamento de Antioquia
entre 2018 y 2022?", dataset `ji8i-4anb` (Ministerio de Educación Nacional),
1 claim (`avg`), `label_status=verified`, `presentation_warnings=[]`.

## Excepción temporal registrada: `completed` con `presentation_warnings`

**No existe ningún fixture para este escenario. Esta es una excepción
temporal registrada, no un caso pendiente de captura.**

Verificado de nuevo en F0-R1 (2026-07-27, incluida la corrida nueva
`e6ae9a62-…`): de **565** corridas `completed` persistidas en PostgreSQL
local, **cero** tienen `answer.presentation_warnings` no vacío:

```sql
SELECT count(*) FROM agent_runs WHERE status='completed';
-- 565
SELECT count(*) FROM agent_runs
WHERE status = 'completed'
  AND jsonb_array_length(COALESCE(final_answer->'presentation_warnings', '[]'::jsonb)) > 0;
-- 0
```

**Causa (normativa, no operativa):** `specs/001-cuestion-de-datos-v2/plan.md`
§15 documenta que el contrato de `presentation_warnings` (T-617C-A) está
**aprobado**, pero su **implementación en el runtime (T-617C) sigue
pendiente**. El campo existe en el esquema de respuesta — se ve como `[]` en
los seis fixtures de este directorio — pero ningún camino de código lo puebla
todavía. No es posible producir este escenario desde una corrida real sin
fabricar el campo, algo prohibido explícitamente.

**Condición de cierre de la excepción:** este fixture se recaptura (siguiendo
el método 2 de este README) tan pronto T-617C quede implementado y una
corrida real produzca al menos una advertencia de presentación no vacía.
Hasta entonces, cualquier trabajo de F1+ que consuma `presentation_warnings`
debe tratarlo como "siempre `[]` en el estado actual del sistema", sin asumir
que el campo nunca se puebla.

## Preguntas de origen (referencia, no PII)

| `run_id` | Pregunta real |
|---|---|
| `41f11aa2-56d0-403c-81a2-6f80551c5d72` | ¿Qué códigos NUECA corresponden a la empresa 78, EMPRESA DE SERVICIOS DE EL RETIRO - RETIRAR S.A. E.S.P.? |
| `0c63affd-8e8c-4f9c-b56f-0a83696d1e74` | ¿Cuál es el precio promedio de vivienda en Marte para 2026? *(caso negativo deliberado del golden set)* |
| `677719d8-b448-4c10-8c77-198676e3f7d9` | ¿Qué valor de temperatura ambiente registró la estación 0026195501 con el sensor 0068 el 21 de enero de 2020 a las 03:35? |
| `8c915e85-6d7f-4d1d-9eeb-b1f175308936` | ¿Cuál fue el promedio de deserción escolar en el departamento de Antioquia entre 2018 y 2022? |
| `e6ae9a62-3394-4eee-b9e4-c76a3adf9582` | ¿Cuál fue el promedio de deserción escolar en el departamento de Antioquia entre 2018 y 2022? *(misma pregunta que la corrida `interrupted`, ejecutada de nuevo hasta completarse — ver `completed-stream.sse.txt`)* |

Todas versan sobre entidades públicas, estaciones de monitoreo o agregados
departamentales/educativos — ninguna sobre personas naturales.
