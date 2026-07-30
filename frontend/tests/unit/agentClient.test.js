import { describe, expect, it } from "vitest";
import { createAgentClient } from "../../lib/api/agentClient.js";
import { ApiError } from "../../lib/api/errors.js";

const BASE_URL = "http://localhost:8000";
const TOKEN = "cdt_rt_9f8a7b6c5d4e3f2a1b0c";

function jsonResponse(status, body) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function errorEnvelope(code, retryable = false) {
  return {
    error: {
      code,
      status: "failed",
      message_user: `mensaje seguro para ${code}`,
      message_dev: `detalle técnico ${code}`,
      retryable,
    },
  };
}

/** Doble de prueba simple: registra cada llamada y responde según `handler`. */
function fakeFetch(handler) {
  const calls = [];
  const fn = async (url, options) => {
    calls.push({ url: String(url), options });
    return handler(String(url), options, calls.length - 1);
  };
  fn.calls = calls;
  return fn;
}

describe("createAgentClient · startRun", () => {
  it("hace POST a /v2/agent/query con Content-Type JSON y mapea snake_case → camelCase", async () => {
    const fetchImpl = fakeFetch((url, options) => {
      expect(url).toBe(`${BASE_URL}/v2/agent/query`);
      expect(options.method).toBe("POST");
      expect(options.headers["Content-Type"]).toBe("application/json");
      const sent = JSON.parse(options.body);
      expect(sent).toEqual({
        question: "¿Cuál es la tasa de deserción escolar en Sonsón?",
        context_hint: "Sección: Definición del problema.",
      });
      return jsonResponse(202, {
        run_id: "1f0c-uuid",
        run_access_token: TOKEN,
        token_expires_at: "2026-10-04T14:22:31Z",
        stream_url: "/v2/agent/stream/1f0c-uuid",
      });
    });

    const client = createAgentClient({ baseUrl: BASE_URL, fetchImpl });
    const result = await client.startRun({
      question: "¿Cuál es la tasa de deserción escolar en Sonsón?",
      contextHint: "Sección: Definición del problema.",
    });

    expect(result).toEqual({
      runId: "1f0c-uuid",
      token: TOKEN,
      tokenExpiresAt: "2026-10-04T14:22:31Z",
      streamUrl: "/v2/agent/stream/1f0c-uuid",
    });
  });

  it("no envía context_hint si no se proporciona, y nunca envía options/retention_class", async () => {
    const fetchImpl = fakeFetch((url, options) => {
      const sent = JSON.parse(options.body);
      expect(sent).toEqual({ question: "pregunta mínima" });
      expect(sent.context_hint).toBeUndefined();
      expect(sent.options).toBeUndefined();
      expect(sent.retention_class).toBeUndefined();
      return jsonResponse(202, {
        run_id: "r1",
        run_access_token: TOKEN,
        token_expires_at: "2026-01-01T00:00:00Z",
        stream_url: "/v2/agent/stream/r1",
      });
    });

    const client = createAgentClient({ baseUrl: BASE_URL, fetchImpl });
    await client.startRun({ question: "pregunta mínima" });
  });
});

describe("createAgentClient · getRun y deleteRun", () => {
  it("getRun envía Authorization: Bearer y el token no aparece en la URL capturada", async () => {
    const fetchImpl = fakeFetch((url, options) => {
      expect(options.headers.Authorization).toBe(`Bearer ${TOKEN}`);
      return jsonResponse(200, { run_id: "r1", status: "running" });
    });

    const client = createAgentClient({ baseUrl: BASE_URL, fetchImpl });
    await client.getRun({ runId: "r1", token: TOKEN });

    for (const call of fetchImpl.calls) {
      expect(call.url).not.toContain(TOKEN);
    }
  });

  it("deleteRun envía Authorization: Bearer y el token no aparece en la URL capturada", async () => {
    const fetchImpl = fakeFetch(() => new Response(null, { status: 204 }));

    const client = createAgentClient({ baseUrl: BASE_URL, fetchImpl });
    await client.deleteRun({ runId: "r1", token: TOKEN });

    expect(fetchImpl.calls[0].options.headers.Authorization).toBe(`Bearer ${TOKEN}`);
    for (const call of fetchImpl.calls) {
      expect(call.url).not.toContain(TOKEN);
    }
  });

  it("codifica runId como segmento de ruta", async () => {
    const fetchImpl = fakeFetch((url) => {
      expect(url).toBe(`${BASE_URL}/v2/agent/runs/id%20con%20espacio`);
      return jsonResponse(200, { run_id: "id con espacio", status: "running" });
    });

    const client = createAgentClient({ baseUrl: BASE_URL, fetchImpl });
    await client.getRun({ runId: "id con espacio", token: TOKEN });
  });

  it("getRun tolera campos aditivos desconocidos sin romper", async () => {
    const fetchImpl = fakeFetch(() =>
      jsonResponse(200, {
        run_id: "r1",
        status: "completed",
        campo_futuro_no_documentado: { anidado: true },
      })
    );

    const client = createAgentClient({ baseUrl: BASE_URL, fetchImpl });
    const result = await client.getRun({ runId: "r1", token: TOKEN });

    expect(result.status).toBe("completed");
    expect(result.campo_futuro_no_documentado).toEqual({ anidado: true });
  });

  it("deleteRun devuelve true en 204", async () => {
    const fetchImpl = fakeFetch(() => new Response(null, { status: 204 }));
    const client = createAgentClient({ baseUrl: BASE_URL, fetchImpl });
    await expect(client.deleteRun({ runId: "r1", token: TOKEN })).resolves.toBe(true);
  });

  it("deleteRun devuelve true en 404 RUN_NOT_FOUND (idempotente)", async () => {
    const fetchImpl = fakeFetch(() => jsonResponse(404, errorEnvelope("RUN_NOT_FOUND")));
    const client = createAgentClient({ baseUrl: BASE_URL, fetchImpl });
    await expect(client.deleteRun({ runId: "r1", token: TOKEN })).resolves.toBe(true);
  });

  it("deleteRun lanza ApiError en un 404 con otro código distinto de RUN_NOT_FOUND", async () => {
    const fetchImpl = fakeFetch(() => jsonResponse(404, errorEnvelope("UNAUTHORIZED")));
    const client = createAgentClient({ baseUrl: BASE_URL, fetchImpl });

    await expect(client.deleteRun({ runId: "r1", token: TOKEN })).rejects.toMatchObject({
      code: "UNAUTHORIZED",
      httpStatus: 404,
    });
  });

  it("deleteRun normaliza un 404 con cuerpo no JSON como NETWORK", async () => {
    const fetchImpl = fakeFetch(
      () => new Response("<html>404</html>", { status: 404 })
    );
    const client = createAgentClient({ baseUrl: BASE_URL, fetchImpl });

    await expect(client.deleteRun({ runId: "r1", token: TOKEN })).rejects.toMatchObject({
      code: "NETWORK",
    });
  });
});

describe("createAgentClient · sobre de error normalizado", () => {
  it.each([422, 429, 401, 404])(
    "getRun convierte %i a ApiError con el código del sobre",
    async (httpStatus) => {
      const code = { 422: "VALIDATION_ERROR", 429: "RATE_LIMITED", 401: "UNAUTHORIZED", 404: "RUN_NOT_FOUND" }[
        httpStatus
      ];
      const fetchImpl = fakeFetch(() => jsonResponse(httpStatus, errorEnvelope(code)));
      const client = createAgentClient({ baseUrl: BASE_URL, fetchImpl });

      await expect(client.getRun({ runId: "r1", token: TOKEN })).rejects.toMatchObject({
        code,
        httpStatus,
      });
    }
  );

  it("un cuerpo de error que no es JSON válido se normaliza como NETWORK", async () => {
    const fetchImpl = fakeFetch(
      () => new Response("<html>502 Bad Gateway</html>", { status: 502 })
    );
    const client = createAgentClient({ baseUrl: BASE_URL, fetchImpl });

    await expect(client.getRun({ runId: "r1", token: TOKEN })).rejects.toMatchObject({
      code: "NETWORK",
    });
  });

  it("un fetch() que rechaza (red caída) se normaliza como NETWORK", async () => {
    const fetchImpl = async () => {
      throw new TypeError("Failed to fetch");
    };
    const client = createAgentClient({ baseUrl: BASE_URL, fetchImpl });

    let caught;
    try {
      await client.getRun({ runId: "r1", token: TOKEN });
    } catch (error) {
      caught = error;
    }
    expect(caught).toBeInstanceOf(ApiError);
    expect(caught.code).toBe("NETWORK");
    expect(caught.retryable).toBe(true);
  });

  it("un AbortError se relanza tal cual, sin envolverlo en ApiError", async () => {
    const fetchImpl = async () => {
      const abort = new Error("The operation was aborted");
      abort.name = "AbortError";
      throw abort;
    };
    const client = createAgentClient({ baseUrl: BASE_URL, fetchImpl });

    let caught;
    try {
      await client.getRun({ runId: "r1", token: TOKEN });
    } catch (error) {
      caught = error;
    }
    expect(caught).not.toBeInstanceOf(ApiError);
    expect(caught.name).toBe("AbortError");
  });
});
