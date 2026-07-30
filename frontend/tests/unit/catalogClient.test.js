import { describe, expect, it } from "vitest";
import { createCatalogClient } from "../../lib/api/catalogClient.js";
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

function fakeFetch(handler) {
  const calls = [];
  const fn = async (url, options) => {
    calls.push({ url: String(url), options });
    return handler(String(url), options);
  };
  fn.calls = calls;
  return fn;
}

describe("createCatalogClient · health", () => {
  it("200 ok devuelve { ok:true, httpStatus:200, payload }", async () => {
    const body = {
      status: "ok",
      checks: { database: "ok", catalog_index: { status: "ok" }, llm_provider: { status: "ok" } },
      version: "2.0.0",
    };
    const fetchImpl = fakeFetch((url, options) => {
      expect(url).toBe(`${BASE_URL}/v2/health`);
      expect(options.headers ?? {}).not.toHaveProperty("Authorization");
      return jsonResponse(200, body);
    });

    const client = createCatalogClient({ baseUrl: BASE_URL, fetchImpl });
    const result = await client.health();

    expect(result).toEqual({ ok: true, httpStatus: 200, payload: body });
  });

  it("503 degraded conserva los checks, no se convierte en ApiError", async () => {
    const body = {
      status: "degraded",
      checks: {
        database: "ok",
        catalog_index: { status: "degraded", detail: "not_initialized" },
        llm_provider: { status: "ok" },
      },
      version: "2.0.0",
    };
    const fetchImpl = fakeFetch(() => jsonResponse(503, body));

    const client = createCatalogClient({ baseUrl: BASE_URL, fetchImpl });
    const result = await client.health();

    expect(result.ok).toBe(false);
    expect(result.httpStatus).toBe(503);
    expect(result.payload).toEqual(body); // checks completos, nada perdido
  });

  it("500 con sobre de error se convierte en ApiError", async () => {
    const fetchImpl = fakeFetch(() => jsonResponse(500, errorEnvelope("INTERNAL")));
    const client = createCatalogClient({ baseUrl: BASE_URL, fetchImpl });

    await expect(client.health()).rejects.toMatchObject({ code: "INTERNAL", httpStatus: 500 });
  });

  it("cuerpo no JSON se normaliza como NETWORK", async () => {
    const fetchImpl = fakeFetch(() => new Response("<html>bad gateway</html>", { status: 502 }));
    const client = createCatalogClient({ baseUrl: BASE_URL, fetchImpl });

    await expect(client.health()).rejects.toMatchObject({ code: "NETWORK" });
  });

  it("un fetch() que rechaza se normaliza como NETWORK, salvo AbortError", async () => {
    const fetchImpl = async () => {
      throw new TypeError("Failed to fetch");
    };
    const client = createCatalogClient({ baseUrl: BASE_URL, fetchImpl });
    await expect(client.health()).rejects.toMatchObject({ code: "NETWORK" });

    const abortFetch = async () => {
      const err = new Error("aborted");
      err.name = "AbortError";
      throw err;
    };
    const client2 = createCatalogClient({ baseUrl: BASE_URL, fetchImpl: abortFetch });
    let caught;
    try {
      await client2.health();
    } catch (error) {
      caught = error;
    }
    expect(caught).not.toBeInstanceOf(ApiError);
    expect(caught.name).toBe("AbortError");
  });

  it("nunca envía Authorization ni token", async () => {
    const fetchImpl = fakeFetch((url, options) => {
      expect(options).not.toHaveProperty("Authorization");
      expect(JSON.stringify(options.headers ?? {})).not.toContain(TOKEN);
      return jsonResponse(200, { status: "ok", checks: {}, version: "2.0.0" });
    });
    const client = createCatalogClient({ baseUrl: BASE_URL, fetchImpl });
    await client.health();
    for (const call of fetchImpl.calls) expect(call.url).not.toContain(TOKEN);
  });
});

describe("createCatalogClient · searchCatalog", () => {
  it("codifica tildes, espacios y caracteres especiales vía URLSearchParams", async () => {
    const fetchImpl = fakeFetch((url) => {
      const parsed = new URL(url);
      expect(parsed.searchParams.get("q")).toBe("deserción escolar & niños");
      expect(parsed.searchParams.get("k")).toBe("10");
      return jsonResponse(200, { query: "deserción escolar & niños", results: [] });
    });

    const client = createCatalogClient({ baseUrl: BASE_URL, fetchImpl });
    const result = await client.searchCatalog({ query: "deserción escolar & niños" });

    expect(result.results).toEqual([]);
  });

  it("k=1 y k=25 se aceptan", async () => {
    for (const k of [1, 25]) {
      const fetchImpl = fakeFetch((url) => {
        expect(new URL(url).searchParams.get("k")).toBe(String(k));
        return jsonResponse(200, { query: "x", results: [] });
      });
      const client = createCatalogClient({ baseUrl: BASE_URL, fetchImpl });
      await expect(client.searchCatalog({ query: "x", k })).resolves.toBeTruthy();
    }
  });

  it("k inválido (0, 26, decimal, NaN, string) se rechaza antes del fetch, con un error seguro", async () => {
    for (const badK of [0, 26, 1.5, NaN, "10", null, -1]) {
      const fetchImpl = fakeFetch(() => {
        throw new Error("no debía llamarse a fetch con un k inválido");
      });
      const client = createCatalogClient({ baseUrl: BASE_URL, fetchImpl });

      let caught;
      try {
        await client.searchCatalog({ query: "x", k: badK });
      } catch (error) {
        caught = error;
      }
      expect(caught).toBeInstanceOf(ApiError);
      expect(caught.code).toBe("INVALID_PARAMS");
      expect(fetchImpl.calls).toHaveLength(0); // nunca llegó a la red
    }
  });

  it("422 (VALIDATION_ERROR) se normaliza como ApiError", async () => {
    const fetchImpl = fakeFetch(() => jsonResponse(422, errorEnvelope("VALIDATION_ERROR")));
    const client = createCatalogClient({ baseUrl: BASE_URL, fetchImpl });

    await expect(client.searchCatalog({ query: "x" })).rejects.toMatchObject({
      code: "VALIDATION_ERROR",
      httpStatus: 422,
    });
  });

  it("campos aditivos desconocidos en la respuesta no rompen el cliente", async () => {
    const fetchImpl = fakeFetch(() =>
      jsonResponse(200, {
        query: "x",
        results: [{ dataset_id: "d1", campo_futuro: { anidado: true } }],
        campo_raiz_futuro: 42,
      })
    );
    const client = createCatalogClient({ baseUrl: BASE_URL, fetchImpl });

    const result = await client.searchCatalog({ query: "x" });
    expect(result.results[0].campo_futuro).toEqual({ anidado: true });
    expect(result.campo_raiz_futuro).toBe(42);
  });

  it("cuerpo no JSON y fetch() rechazado se normalizan como NETWORK", async () => {
    const fetchImpl1 = fakeFetch(() => new Response("no soy json", { status: 200 }));
    const client1 = createCatalogClient({ baseUrl: BASE_URL, fetchImpl: fetchImpl1 });
    await expect(client1.searchCatalog({ query: "x" })).rejects.toMatchObject({ code: "NETWORK" });

    const fetchImpl2 = async () => {
      throw new TypeError("Failed to fetch");
    };
    const client2 = createCatalogClient({ baseUrl: BASE_URL, fetchImpl: fetchImpl2 });
    await expect(client2.searchCatalog({ query: "x" })).rejects.toMatchObject({ code: "NETWORK" });
  });

  it("AbortError se conserva sin envolver", async () => {
    const fetchImpl = async () => {
      const err = new Error("aborted");
      err.name = "AbortError";
      throw err;
    };
    const client = createCatalogClient({ baseUrl: BASE_URL, fetchImpl });

    let caught;
    try {
      await client.searchCatalog({ query: "x" });
    } catch (error) {
      caught = error;
    }
    expect(caught).not.toBeInstanceOf(ApiError);
    expect(caught.name).toBe("AbortError");
  });

  it("nunca envía Authorization ni token en la URL ni en los headers", async () => {
    const fetchImpl = fakeFetch((url, options) => {
      expect(url).not.toContain(TOKEN);
      expect(options).not.toHaveProperty("Authorization");
      expect(JSON.stringify(options.headers ?? {})).not.toContain(TOKEN);
      return jsonResponse(200, { query: "x", results: [] });
    });
    const client = createCatalogClient({ baseUrl: BASE_URL, fetchImpl });
    await client.searchCatalog({ query: "x" });
  });
});
