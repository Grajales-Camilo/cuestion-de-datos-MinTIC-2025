/**
 * Cliente del catálogo (`contracts/api-rest.md` §1, §8). Ambos endpoints son
 * públicos y de solo lectura: nunca llevan `Authorization` ni ningún token.
 * Sin caché, sin `console.*`, sin almacenamiento.
 */
import { ApiError, apiErrorFromEnvelope, networkApiError } from "./errors.js";

const MIN_K = 1;
const MAX_K = 25;

function isAbortError(error) {
  return Boolean(error) && error.name === "AbortError";
}

async function tryParseJson(response) {
  try {
    return await response.json();
  } catch {
    return undefined;
  }
}

export function createCatalogClient({ baseUrl, fetchImpl = fetch }) {
  async function rawFetch(url, options) {
    try {
      return await fetchImpl(url, options);
    } catch (error) {
      if (isAbortError(error)) throw error;
      throw networkApiError(error);
    }
  }

  /**
   * `GET /v2/health`. Excepción normativa: `200` y `503` comparten el mismo
   * esquema `HealthResponse` y NUNCA se convierten en `ApiError` — `503`
   * es degradación parcial legible, no un error del sobre estándar. Se
   * devuelve `{ ok, httpStatus, payload }` para no perder el detalle de
   * `checks` aunque `ok` sea `false`.
   */
  async function health({ signal } = {}) {
    const response = await rawFetch(`${baseUrl}/v2/health`, { signal });
    const parsed = await tryParseJson(response);

    if (response.status === 200 || response.status === 503) {
      if (parsed === undefined) {
        throw networkApiError("respuesta de /v2/health sin cuerpo JSON interpretable");
      }
      return { ok: response.status === 200, httpStatus: response.status, payload: parsed };
    }

    // Cualquier otro estado (fuera de la excepción normativa) sí usa el
    // sobre de error estándar.
    if (parsed === undefined) {
      throw networkApiError(`respuesta ${response.status} sin cuerpo JSON interpretable`);
    }
    throw apiErrorFromEnvelope(response.status, parsed);
  }

  /**
   * `GET /v2/catalog/search?q=...&k=...`. `k` se valida ANTES del fetch —
   * nunca se recorta en silencio, y un `k` inválido nunca llega a la red.
   */
  async function searchCatalog({ query, k = 10, signal } = {}) {
    if (!Number.isInteger(k) || k < MIN_K || k > MAX_K) {
      throw new ApiError({
        code: "INVALID_PARAMS",
        httpStatus: null,
        status: null,
        messageUser: "El número de resultados solicitados no es válido (debe ser un entero entre 1 y 25).",
        messageDev: `k inválido antes de la solicitud: ${JSON.stringify(k)}`,
        retryable: false,
      });
    }

    const url = new URL(`${baseUrl}/v2/catalog/search`);
    url.searchParams.set("q", query ?? "");
    url.searchParams.set("k", String(k));

    const response = await rawFetch(url.toString(), { signal });
    const parsed = await tryParseJson(response);

    if (!response.ok) {
      if (parsed === undefined) {
        throw networkApiError(`respuesta ${response.status} sin cuerpo JSON interpretable`);
      }
      throw apiErrorFromEnvelope(response.status, parsed);
    }
    if (parsed === undefined) {
      throw networkApiError("respuesta 2xx sin cuerpo JSON interpretable");
    }

    // Tolerante a campos aditivos (contrato §10): se devuelve tal cual.
    return parsed;
  }

  return { health, searchCatalog };
}
