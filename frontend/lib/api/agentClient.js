/**
 * Cliente REST del agente (`contracts/api-rest.md` §2, §6, §7, §7b).
 * Sin estado, sin I/O propio fuera de `fetchImpl`: no cachea ni registra el
 * token en ningún punto. `Authorization: Bearer` es el único punto de
 * inyección del token; ninguna función de este módulo acepta un token como
 * parámetro de URL.
 *
 * Un `AbortError` (cancelación voluntaria vía `signal`) se relanza tal cual,
 * sin envolverlo en `ApiError`, para que el consumidor pueda distinguirlo de
 * un fallo de red real (RF-209: abortar no interrumpe la corrida).
 */
import { apiErrorFromEnvelope, networkApiError } from "./errors.js";

export function createAgentClient({ baseUrl, fetchImpl = fetch }) {
  async function rawFetch(path, options) {
    let response;
    try {
      response = await fetchImpl(`${baseUrl}${path}`, options);
    } catch (error) {
      if (error && error.name === "AbortError") throw error;
      throw networkApiError(error);
    }
    return response;
  }

  async function readJsonBody(response) {
    try {
      return await response.json();
    } catch {
      return undefined;
    }
  }

  async function fetchJson(path, options) {
    const response = await rawFetch(path, options);
    const parsed = await readJsonBody(response);

    if (!response.ok) {
      if (parsed === undefined) {
        throw networkApiError("respuesta de error no es JSON válido");
      }
      throw apiErrorFromEnvelope(response.status, parsed);
    }
    if (parsed === undefined) {
      throw networkApiError("respuesta 2xx sin cuerpo JSON interpretable");
    }
    return parsed;
  }

  async function startRun({ question, contextHint, signal } = {}) {
    const body = { question };
    if (contextHint !== undefined && contextHint !== null) {
      body.context_hint = contextHint;
    }
    // Deliberado: no se envía `options`/`retention_class`. RF-801 crea
    // siempre retention_class="user" por defecto; los usuarios normales no
    // eligen proveedor ni modelo (solo el runner OE3 con EVAL_MODE=true).

    const parsed = await fetchJson("/v2/agent/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });

    return {
      runId: parsed.run_id,
      token: parsed.run_access_token,
      tokenExpiresAt: parsed.token_expires_at,
      streamUrl: parsed.stream_url,
    };
  }

  async function getRun({ runId, token, signal } = {}) {
    const parsed = await fetchJson(`/v2/agent/runs/${encodeURIComponent(runId)}`, {
      method: "GET",
      headers: { Authorization: `Bearer ${token}` },
      signal,
    });

    // Tolerante a campos aditivos (contrato §10): se devuelve tal cual, sin
    // validación estricta que rompa ante propiedades desconocidas.
    return parsed;
  }

  async function deleteRun({ runId, token, signal } = {}) {
    const response = await rawFetch(`/v2/agent/runs/${encodeURIComponent(runId)}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
      signal,
    });

    // Para el usuario, la corrida ya no existe si el borrado acaba de
    // ocurrir (204). Un 404 es idempotente SOLO cuando el sobre confirma
    // RUN_NOT_FOUND: cualquier otro código en un 404, o un cuerpo que no es
    // JSON interpretable, se trata como el error real que es.
    if (response.status === 204) {
      return true;
    }

    const parsed = await readJsonBody(response);

    if (response.status === 404) {
      if (parsed === undefined) {
        throw networkApiError("respuesta 404 sin cuerpo JSON interpretable");
      }
      const error = apiErrorFromEnvelope(404, parsed);
      if (error.code === "RUN_NOT_FOUND") return true;
      throw error;
    }

    if (!response.ok) {
      if (parsed === undefined) {
        throw networkApiError("respuesta de error no es JSON válido");
      }
      throw apiErrorFromEnvelope(response.status, parsed);
    }

    return true;
  }

  return { startRun, getRun, deleteRun };
}
