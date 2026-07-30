import { describe, expect, it } from "vitest";
import { ApiError, apiErrorFromEnvelope, networkApiError } from "../../lib/api/errors.js";

const TOKEN = "cdt_rt_9f8a7b6c5d4e3f2a1b0c";

describe("apiErrorFromEnvelope", () => {
  it.each([
    ["VALIDATION_ERROR", 422],
    ["RATE_LIMITED", 429],
    ["UNAUTHORIZED", 401],
    ["RUN_NOT_FOUND", 404],
  ])("normaliza %s (%i) con sus campos del sobre", (code, httpStatus) => {
    const error = apiErrorFromEnvelope(httpStatus, {
      error: {
        code,
        status: "failed",
        message_user: "mensaje seguro para el usuario",
        message_dev: `detalle técnico de ${code}`,
        retryable: httpStatus === 429,
      },
    });

    expect(error).toBeInstanceOf(ApiError);
    expect(error.code).toBe(code);
    expect(error.httpStatus).toBe(httpStatus);
    expect(error.status).toBe("failed");
    expect(error.messageUser).toBe("mensaje seguro para el usuario");
    expect(error.retryable).toBe(httpStatus === 429);
  });

  it("usa valores por defecto seguros si el sobre viene incompleto", () => {
    const error = apiErrorFromEnvelope(500, {});
    expect(error.code).toBe("UNKNOWN");
    expect(typeof error.messageUser).toBe("string");
    expect(error.messageUser.length).toBeGreaterThan(0);
  });
});

describe("ApiError y el token", () => {
  it("el token nunca aparece en .message, .messageDev ni .toString()", () => {
    const error = apiErrorFromEnvelope(500, {
      error: {
        code: "INTERNAL",
        message_user: "Ocurrió un error interno.",
        message_dev: `fallo procesando Authorization: Bearer ${TOKEN}`,
        retryable: false,
      },
    });

    expect(error.message).not.toContain(TOKEN);
    expect(error.messageDev).not.toContain(TOKEN);
    expect(error.toString()).not.toContain(TOKEN);
    expect(error.messageDev).toContain("[REDACTADO]");
  });

  it("messageUser también pasa por redact() y nunca expone el token ni claves sensibles", () => {
    const error = apiErrorFromEnvelope(500, {
      error: {
        code: "INTERNAL",
        message_user: `Contacta a soporte con este token: ${TOKEN}`,
        message_dev: "detalle interno sin secretos",
        retryable: false,
      },
    });

    expect(error.messageUser).not.toContain(TOKEN);
    expect(error.messageUser).toContain("[REDACTADO]");
  });

  it("ninguno de los campos expuestos por ApiError contiene el valor real del token, venga del campo que venga", () => {
    // Los nombres de campo "token"/"access_token"/"run_access_token" son los
    // que redact() reconoce por clave dentro de un objeto (ver redact.test.js);
    // dentro de un string plano como message_user/message_dev, la única
    // protección aplicable es el patrón cdt_rt_*, que es lo que se verifica
    // aquí exhaustivamente sobre cada campo expuesto por ApiError.
    const error = apiErrorFromEnvelope(401, {
      error: {
        code: "UNAUTHORIZED",
        message_user: `token=${TOKEN} access_token=${TOKEN} run_access_token=${TOKEN}`,
        message_dev: `Authorization: Bearer ${TOKEN}`,
        retryable: false,
      },
    });

    const exposed = JSON.stringify({
      messageUser: error.messageUser,
      messageDev: error.messageDev,
      message: error.message,
      toString: error.toString(),
      code: error.code,
      httpStatus: error.httpStatus,
      status: error.status,
      retryable: error.retryable,
    });

    expect(exposed).not.toContain(TOKEN);
  });

  it("networkApiError produce code NETWORK y no expone el error nativo sin redactar", () => {
    const nativeError = new Error(`fetch falló con token cdt_rt_zzzz1111`);
    const error = networkApiError(nativeError);

    expect(error.code).toBe("NETWORK");
    expect(error.retryable).toBe(true);
    expect(error.messageDev).not.toContain("cdt_rt_zzzz1111");
  });
});
