/**
 * `ApiError`: forma única de error que expone el cliente del agente.
 * Traduce el sobre de error normativo (`contracts/api-rest.md` §6) y
 * cualquier fallo de red/transporte a la misma forma, para que el código
 * consumidor nunca tenga que distinguir entre un `Response` no-2xx y un
 * `fetch()` que rechazó.
 *
 * `messageUser`, `messageDev` y `toString()` pasan siempre por `redact()`:
 * aunque ni el `message_user` ni el `message_dev` del backend deberían traer
 * secretos, el cliente no confía ciegamente en eso.
 */
import { redact } from "./redact.js";

export class ApiError extends Error {
  constructor({
    code,
    httpStatus = null,
    status = null,
    messageUser,
    messageDev,
    retryable = false,
  }) {
    const safeUser = redact(messageUser ?? "Ocurrió un error inesperado.");
    const safeDev = redact(messageDev ?? messageUser ?? code ?? "Error desconocido");
    super(safeDev);
    this.name = "ApiError";
    this.code = code;
    this.httpStatus = httpStatus;
    this.status = status;
    this.messageUser = safeUser;
    this.messageDev = safeDev;
    this.retryable = Boolean(retryable);
  }

  toString() {
    return redact(`ApiError[${this.code}]: ${this.messageDev}`);
  }
}

const DEFAULT_MESSAGE_USER =
  "Ocurrió un error inesperado. Intenta de nuevo en unos minutos.";

/**
 * Construye un `ApiError` a partir del sobre de error normativo
 * (`{ error: { code, status, message_user, message_dev, retryable } }`) y
 * el `httpStatus` real de la respuesta.
 */
export function apiErrorFromEnvelope(httpStatus, envelope) {
  const body =
    envelope && typeof envelope === "object" && envelope.error
      ? envelope.error
      : {};

  return new ApiError({
    code: typeof body.code === "string" ? body.code : "UNKNOWN",
    httpStatus,
    status: typeof body.status === "string" ? body.status : null,
    messageUser:
      typeof body.message_user === "string"
        ? body.message_user
        : DEFAULT_MESSAGE_USER,
    messageDev:
      typeof body.message_dev === "string" ? body.message_dev : `HTTP ${httpStatus}`,
    retryable: Boolean(body.retryable),
  });
}

/**
 * `ApiError` sintético para cuando no hubo respuesta interpretable: el
 * cuerpo no era JSON válido, o `fetch()` rechazó (red caída, CORS, DNS...).
 */
export function networkApiError(reason) {
  const detail =
    reason instanceof Error && typeof reason.message === "string"
      ? reason.message
      : String(reason ?? "fallo de red");

  return new ApiError({
    code: "NETWORK",
    httpStatus: null,
    status: null,
    messageUser:
      "No se pudo conectar con el servicio. Revisa tu conexión e intenta de nuevo.",
    messageDev: `Fallo de red o respuesta no interpretable: ${detail}`,
    retryable: true,
  });
}
