import { describe, expect, it } from "vitest";
import { isolateCorrupt, removeKeysWithPrefix, safeReadJson, safeRemove, safeWriteJson } from "../../../lib/session/storage.js";

function makeMemoryStorage() {
  const map = new Map();
  return {
    getItem: (key) => (map.has(key) ? map.get(key) : null),
    setItem: (key, value) => {
      map.set(key, value);
    },
    removeItem: (key) => {
      map.delete(key);
    },
    get length() {
      return map.size;
    },
    key: (i) => [...map.keys()][i] ?? null,
    _map: map,
  };
}

function makeThrowingStorage({ onGet, onSet } = {}) {
  return {
    getItem: (key) => {
      if (onGet) throw onGet;
      return null;
    },
    setItem: (key, value) => {
      if (onSet) throw onSet;
    },
    removeItem: () => {
      throw new Error("no disponible");
    },
  };
}

function quotaError() {
  const error = new Error("cuota agotada");
  error.name = "QuotaExceededError";
  return error;
}

describe("safeReadJson", () => {
  it("clave ausente: ok true, value null", () => {
    const storage = makeMemoryStorage();
    expect(safeReadJson(storage, "k")).toEqual({ ok: true, value: null });
  });

  it("JSON válido: ok true con el valor parseado", () => {
    const storage = makeMemoryStorage();
    storage.setItem("k", JSON.stringify({ a: 1 }));
    expect(safeReadJson(storage, "k")).toEqual({ ok: true, value: { a: 1 } });
  });

  it("JSON corrupto: ok false, reason corrupt, conserva el raw", () => {
    const storage = makeMemoryStorage();
    storage.setItem("k", "{no es json");
    const result = safeReadJson(storage, "k");
    expect(result.ok).toBe(false);
    expect(result.reason).toBe("corrupt");
    expect(result.raw).toBe("{no es json");
  });

  it("storage.getItem lanza: ok false, reason unavailable, no propaga la excepción", () => {
    const storage = makeThrowingStorage({ onGet: new Error("bloqueado") });
    expect(() => safeReadJson(storage, "k")).not.toThrow();
    expect(safeReadJson(storage, "k")).toEqual({ ok: false, reason: "unavailable" });
  });

  it("storage ausente (SSR): ok true, value null, no lanza", () => {
    expect(safeReadJson(null, "k")).toEqual({ ok: true, value: null });
  });
});

describe("safeWriteJson", () => {
  it("escritura normal: ok true y el valor queda serializado", () => {
    const storage = makeMemoryStorage();
    expect(safeWriteJson(storage, "k", { a: 1 })).toEqual({ ok: true });
    expect(storage.getItem("k")).toBe(JSON.stringify({ a: 1 }));
  });

  it("QuotaExceededError: ok false, reason quota_exceeded, no lanza", () => {
    const storage = makeThrowingStorage({ onSet: quotaError() });
    expect(() => safeWriteJson(storage, "k", { a: 1 })).not.toThrow();
    expect(safeWriteJson(storage, "k", { a: 1 })).toEqual({ ok: false, reason: "quota_exceeded" });
  });

  it("valor no serializable (referencia circular): ok false, reason unserializable", () => {
    const storage = makeMemoryStorage();
    const circular = {};
    circular.self = circular;
    expect(safeWriteJson(storage, "k", circular)).toEqual({ ok: false, reason: "unserializable" });
  });
});

describe("safeRemove", () => {
  it("elimina la clave existente", () => {
    const storage = makeMemoryStorage();
    storage.setItem("k", "v");
    expect(safeRemove(storage, "k")).toEqual({ ok: true });
    expect(storage.getItem("k")).toBeNull();
  });

  it("storage.removeItem lanza: ok false, no propaga", () => {
    const storage = makeThrowingStorage();
    expect(() => safeRemove(storage, "k")).not.toThrow();
  });
});

describe("isolateCorrupt", () => {
  it("guarda el raw en una clave de diagnóstico con timestamp", () => {
    const storage = makeMemoryStorage();
    const result = isolateCorrupt(storage, "cdd.runs.v1", "{roto", { now: () => 12345 });
    expect(result.ok).toBe(true);
    expect(result.diagnosticKey).toBe("cdd.runs.v1.corrupt.12345");
    expect(storage.getItem("cdd.runs.v1.corrupt.12345")).toBe("{roto");
  });

  it("best-effort: si falla la escritura del diagnóstico, no lanza", () => {
    const storage = makeThrowingStorage({ onSet: quotaError() });
    expect(() => isolateCorrupt(storage, "k", "{roto")).not.toThrow();
    expect(isolateCorrupt(storage, "k", "{roto")).toEqual({ ok: false });
  });

  it("aplica `sanitize` al raw antes de escribir la copia de diagnóstico", () => {
    const storage = makeMemoryStorage();
    const sanitize = (raw) => raw.replace("secreto", "[REDACTADO]");
    isolateCorrupt(storage, "k", "{token: secreto, broken", { now: () => 1, sanitize });
    expect(storage.getItem("k.corrupt.1")).toBe("{token: [REDACTADO], broken");
  });

  it("sin `sanitize`: conserva el comportamiento anterior (raw tal cual)", () => {
    const storage = makeMemoryStorage();
    isolateCorrupt(storage, "k", "{roto tal cual", { now: () => 2 });
    expect(storage.getItem("k.corrupt.2")).toBe("{roto tal cual");
  });
});

describe("removeKeysWithPrefix", () => {
  it("elimina solo las claves que empiezan por el prefijo dado", () => {
    const storage = makeMemoryStorage();
    storage.setItem("cdd.runs.v1", "doc");
    storage.setItem("cdd.runs.v1.corrupt.1", "a");
    storage.setItem("cdd.runs.v1.corrupt.2", "b");
    storage.setItem("cdd.consent.v1", "no debe tocarse");

    const result = removeKeysWithPrefix(storage, "cdd.runs.v1.corrupt.");

    expect(result).toEqual({ ok: true, removed: 2 });
    expect(storage.getItem("cdd.runs.v1")).toBe("doc");
    expect(storage.getItem("cdd.consent.v1")).toBe("no debe tocarse");
    expect(storage.getItem("cdd.runs.v1.corrupt.1")).toBeNull();
    expect(storage.getItem("cdd.runs.v1.corrupt.2")).toBeNull();
  });

  it("storage ausente o que lanza al enumerar: no lanza, ok false", () => {
    expect(() => removeKeysWithPrefix(null, "x")).not.toThrow();
    expect(removeKeysWithPrefix(null, "x")).toEqual({ ok: false, reason: "unavailable" });

    const throwing = {
      get length() {
        throw new Error("bloqueado");
      },
    };
    expect(() => removeKeysWithPrefix(throwing, "x")).not.toThrow();
  });

  it("ninguna clave coincide: ok true, removed 0", () => {
    const storage = makeMemoryStorage();
    storage.setItem("otra.clave", "v");
    expect(removeKeysWithPrefix(storage, "cdd.runs.v1.corrupt.")).toEqual({ ok: true, removed: 0 });
  });
});
