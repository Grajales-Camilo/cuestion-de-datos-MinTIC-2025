import { describe, expect, it } from "vitest";
import { createRunsStore } from "../../../lib/session/runsStore.js";

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

function quotaError() {
  const error = new Error("cuota agotada");
  error.name = "QuotaExceededError";
  return error;
}

/** `setItem`/`removeItem` siempre lanzan `QuotaExceededError`; `getItem`
 * sirve datos pre-sembrados. Modela un almacén que ya no acepta
 * escrituras (cuota agotada de forma persistente) — usado para el paso
 * de limpieza de `migrate()`. */
function makeWriteThrowingStorage(seedEntries = {}) {
  const map = new Map(Object.entries(seedEntries));
  return {
    getItem: (key) => (map.has(key) ? map.get(key) : null),
    setItem: () => {
      throw quotaError();
    },
    removeItem: () => {
      throw quotaError();
    },
    get length() {
      return map.size;
    },
    key: (i) => [...map.keys()][i] ?? null,
  };
}

function baseRecord(overrides = {}) {
  return {
    runId: "run-1",
    token: "cdt_rt_secreto",
    tokenExpiresAt: null,
    question: "¿Cuál es la cobertura educativa en Antioquia?",
    contextHint: null,
    status: "streaming",
    summary: null,
    lastEventId: 3,
    ...overrides,
  };
}

function makeStore(overrides = {}) {
  return createRunsStore({
    sessionStorage: makeMemoryStorage(),
    localStorage: makeMemoryStorage(),
    now: () => Date.parse("2026-07-27T12:00:00.000Z"),
    ...overrides,
  });
}

describe("runsStore — historial público sin token", () => {
  it("listPublic nunca incluye el campo token", () => {
    const store = makeStore();
    store.upsert(false, baseRecord());
    const [record] = store.listPublic(false);
    expect(record.token).toBeUndefined();
    expect(JSON.stringify(record)).not.toContain("cdt_rt_secreto");
  });
});

describe("runsStore — token solo por getCredential, acotado a runId", () => {
  it("getCredential(runId) devuelve el token; listPublic no", () => {
    const store = makeStore();
    store.upsert(false, baseRecord());
    expect(store.getCredential(false, "run-1")).toEqual({
      token: "cdt_rt_secreto",
      lastEventId: 3,
      tokenExpiresAt: null,
    });
    expect(store.getCredential(false, "run-inexistente")).toBeNull();
  });
});

describe("runsStore — opt-in desmarcado: solo sessionStorage", () => {
  it("upsert con rememberRuns=false escribe en sessionStorage, no en localStorage", () => {
    const sessionStorage = makeMemoryStorage();
    const localStorage = makeMemoryStorage();
    const store = createRunsStore({ sessionStorage, localStorage, now: () => 0 });

    store.upsert(false, baseRecord());

    expect(sessionStorage.getItem("cdd.runs.v1")).not.toBeNull();
    expect(localStorage.getItem("cdd.runs.v1")).toBeNull();
  });
});

describe("runsStore — opt-in activado: migración controlada a localStorage", () => {
  it("migrate(true) mueve los registros de sessionStorage a localStorage y limpia sessionStorage", () => {
    const sessionStorage = makeMemoryStorage();
    const localStorage = makeMemoryStorage();
    const store = createRunsStore({ sessionStorage, localStorage, now: () => 0 });

    store.upsert(false, baseRecord());
    const result = store.migrate(true);

    expect(result.ok).toBe(true);
    expect(result.records).toHaveLength(1);
    expect(result.records[0].runId).toBe("run-1");
    expect(JSON.parse(sessionStorage.getItem("cdd.runs.v1")).records).toEqual([]);
    expect(JSON.parse(localStorage.getItem("cdd.runs.v1")).records).toHaveLength(1);
    expect(store.getCredential(true, "run-1")).not.toBeNull();
    expect(store.getCredential(false, "run-1")).toBeNull();
  });
});

describe("runsStore — desactivar opt-in: elimina el registro persistente de localStorage", () => {
  it("migrate(false) mueve de vuelta a sessionStorage y limpia localStorage", () => {
    const sessionStorage = makeMemoryStorage();
    const localStorage = makeMemoryStorage();
    const store = createRunsStore({ sessionStorage, localStorage, now: () => 0 });

    store.upsert(true, baseRecord());
    store.migrate(false);

    expect(JSON.parse(localStorage.getItem("cdd.runs.v1")).records).toEqual([]);
    expect(JSON.parse(sessionStorage.getItem("cdd.runs.v1")).records).toHaveLength(1);
  });
});

describe("runsStore — recarga: historial saneado y lastEventId recuperados", () => {
  it("un nuevo store sobre el mismo storage recupera question/status/lastEventId", () => {
    const sessionStorage = makeMemoryStorage();
    const localStorage = makeMemoryStorage();
    const store1 = createRunsStore({ sessionStorage, localStorage, now: () => 0 });
    store1.upsert(false, baseRecord({ lastEventId: 7 }));

    const store2 = createRunsStore({ sessionStorage, localStorage, now: () => 0 });
    const [record] = store2.listPublic(false);
    expect(record.lastEventId).toBe(7);
    expect(record.status).toBe("streaming");
  });
});

describe("runsStore — registro vencido", () => {
  it("credencial vencida: getCredential devuelve null, listPublic marca credentialExpired", () => {
    const store = makeStore({ now: () => Date.parse("2026-07-27T12:00:00.000Z") });
    store.upsert(false, baseRecord({ tokenExpiresAt: "2026-07-27T11:00:00.000Z" }));

    expect(store.getCredential(false, "run-1")).toBeNull();
    const [record] = store.listPublic(false);
    expect(record.credentialExpired).toBe(true);
  });
});

describe("runsStore — 401 elimina la credencial pero conserva el registro", () => {
  it("clearCredential deja token en null sin borrar el registro", () => {
    const store = makeStore();
    store.upsert(false, baseRecord());
    store.clearCredential(false, "run-1");

    expect(store.getCredential(false, "run-1")).toBeNull();
    const [record] = store.listPublic(false);
    expect(record.runId).toBe("run-1"); // el registro sigue existiendo
  });
});

describe("runsStore — 404 RUN_NOT_FOUND elimina el registro local", () => {
  it("remove borra el registro por completo", () => {
    const store = makeStore();
    store.upsert(false, baseRecord());
    store.remove(false, "run-1");

    expect(store.listPublic(false)).toEqual([]);
    expect(store.getCredential(false, "run-1")).toBeNull();
  });
});

describe("runsStore — JSON corrupto no se convierte silenciosamente en historial vacío persistido", () => {
  it("aísla el raw corrupto y no sobrescribe la clave original antes de una escritura real", () => {
    const sessionStorage = makeMemoryStorage();
    const localStorage = makeMemoryStorage();
    sessionStorage.setItem("cdd.runs.v1", "{esto no es json valido");
    const store = createRunsStore({ sessionStorage, localStorage, now: () => 12345 });

    expect(store.listPublic(false)).toEqual([]);
    // La clave original sigue siendo el JSON corrupto: no se sobrescribió
    // solo por leerla.
    expect(sessionStorage.getItem("cdd.runs.v1")).toBe("{esto no es json valido");
    // Existe una copia de diagnóstico.
    const diagnosticKeys = [...sessionStorage._map.keys()].filter((k) => k.startsWith("cdd.runs.v1.corrupt."));
    expect(diagnosticKeys).toHaveLength(1);
  });
});

describe("runsStore — QuotaExceededError no pierde el registro previamente válido", () => {
  it("un upsert fallido por cuota no borra un registro anterior ya persistido", () => {
    const validData = new Map();
    let shouldThrow = false;
    const storage = {
      getItem: (k) => (validData.has(k) ? validData.get(k) : null),
      setItem: (k, v) => {
        if (shouldThrow) {
          const error = new Error("cuota agotada");
          error.name = "QuotaExceededError";
          throw error;
        }
        validData.set(k, v);
      },
      removeItem: (k) => validData.delete(k),
    };
    const store = createRunsStore({ sessionStorage: storage, localStorage: makeMemoryStorage(), now: () => 0 });

    store.upsert(false, baseRecord({ runId: "run-1" }));
    shouldThrow = true;
    const result = store.upsert(false, baseRecord({ runId: "run-2" }));

    expect(result.persisted).toBe(false);
    // El almacén real conserva el último estado que sí se pudo escribir
    // (run-1), no queda vacío ni corrupto.
    const persisted = JSON.parse(storage.getItem("cdd.runs.v1"));
    expect(persisted.records.map((r) => r.runId)).toEqual(["run-1"]);
  });
});

// F3-7B-R1 — dos defectos reales reportados en revisión: (1) migrate()
// podía borrar el historial si la escritura en destino fallaba, porque
// nunca comprobaba el resultado antes de limpiar el origen; (2) una copia
// de diagnóstico de JSON corrupto podía dejar un token en texto plano en
// una segunda clave persistente, nunca barrida por migrate/clearAll.

describe("F3-7B-R1 — migrate() nunca pierde datos si falla la escritura en destino", () => {
  it("migrate(true) con QuotaExceededError en localStorage: sessionStorage queda intacto, credencial recuperable", () => {
    const sessionStorage = makeMemoryStorage();
    const localStorage = makeWriteThrowingStorage(); // destino que nunca acepta escrituras
    const store = createRunsStore({ sessionStorage, localStorage, now: () => 0 });

    store.upsert(false, baseRecord());
    const before = store.listPublic(false).length;

    const result = store.migrate(true);

    expect(result.ok).toBe(false);
    expect(result.reason).toBe("quota_exceeded");
    const after = store.listPublic(false).length;
    expect(after).toBe(before); // nunca 0: el origen no se tocó
    expect(store.getCredential(false, "run-1")).not.toBeNull(); // credencial sigue accesible
    expect(store.getCredential(true, "run-1")).toBeNull(); // nunca se "migró a medias"
  });

  it("migrate(false) con QuotaExceededError en sessionStorage: localStorage queda intacto, credencial recuperable", () => {
    const sessionStorage = makeWriteThrowingStorage();
    const localStorage = makeMemoryStorage();
    const store = createRunsStore({ sessionStorage, localStorage, now: () => 0 });

    store.upsert(true, baseRecord());
    const result = store.migrate(false);

    expect(result.ok).toBe(false);
    expect(result.reason).toBe("quota_exceeded");
    expect(store.listPublic(true)).toHaveLength(1);
    expect(store.getCredential(true, "run-1")).not.toBeNull();
    expect(store.getCredential(false, "run-1")).toBeNull();
  });

  it("migrate(true) con localStorage no disponible (SSR-like, storage null): no lanza, no pierde datos", () => {
    const sessionStorage = makeMemoryStorage();
    const store = createRunsStore({ sessionStorage, localStorage: null, now: () => 0 });

    store.upsert(false, baseRecord());
    let result;
    expect(() => {
      result = store.migrate(true);
    }).not.toThrow();

    expect(result.ok).toBe(false);
    expect(store.listPublic(false)).toHaveLength(1);
  });

  it("cleanup_failed: destino escribió y verificó con éxito, pero el borrado del origen falló — los datos no se pierden, pero no se declara éxito", () => {
    const localStorage = makeMemoryStorage(); // destino: escribe bien
    const seedDoc = JSON.stringify({
      schemaVersion: 1,
      records: [{ ...baseRecord(), createdAt: "2026-07-27T00:00:00.000Z", updatedAt: "2026-07-27T00:00:00.000Z" }],
    });
    // origen: ya tiene el registro, pero cualquier escritura (incluida la
    // limpieza final de migrate) lanza — simula una cuota que se agotó
    // justo entre la escritura del destino y la limpieza del origen.
    const sessionStorage = makeWriteThrowingStorage({ "cdd.runs.v1": seedDoc });
    const store = createRunsStore({ sessionStorage, localStorage, now: () => 0 });

    const result = store.migrate(true);

    expect(result.ok).toBe(false);
    expect(result.reason).toBe("cleanup_failed");
    // Los datos SÍ quedaron a salvo en el destino verificado — no se perdieron.
    expect(result.records).toHaveLength(1);
    expect(store.getCredential(true, "run-1")).not.toBeNull();
  });
});

// F5-03A-R2 — defecto reproducido en la auditoría de F5-03A-R1: un
// `sectionId` almacenado con un token incrustado (p. ej. porque una
// acción directa, un `localStorage` manipulado a mano, o una llamada
// programática lo introdujo) sobrevivía intacto en `listPublic()`, y de
// ahí `resumeRun()` podía entregarlo al transporte y, en última instancia,
// a `state.sectionId`.
describe("F5-03A-R2 — sectionId nunca filtra un secreto embebido", () => {
  it("REPRODUCCIÓN: un sectionId con el patrón cdt_rt_* incrustado nunca sobrevive en listPublic/upsert/remove/migrate", () => {
    const store = makeStore();
    const poisoned = baseRecord({ sectionId: "seccion-cdt_rt_filtrado" });

    const upsertResult = store.upsert(false, poisoned);
    expect(JSON.stringify(upsertResult.records)).not.toContain("cdt_rt_filtrado");

    const [record] = store.listPublic(false);
    expect(JSON.stringify(record)).not.toContain("cdt_rt_filtrado");
    expect(record.sectionId).toBeNull();

    const removeResult = store.remove(false, "run-1");
    expect(JSON.stringify(removeResult)).not.toContain("cdt_rt_filtrado");
  });

  it("migrate() tampoco reintroduce un sectionId con el token incrustado", () => {
    const store = makeStore();
    store.upsert(false, baseRecord({ sectionId: "seccion-cdt_rt_filtrado" }));

    const result = store.migrate(true);

    expect(JSON.stringify(result.records)).not.toContain("cdt_rt_filtrado");
  });

  it("un sectionId válido ('seccion-1') sobrevive exactamente en listPublic", () => {
    const store = makeStore();
    store.upsert(false, baseRecord({ sectionId: "seccion-1" }));
    const [record] = store.listPublic(false);
    expect(record.sectionId).toBe("seccion-1");
  });

  it("getCredential() sigue devolviendo el token REAL sin alterar — la sanitización de sectionId nunca lo alcanza", () => {
    const store = makeStore();
    store.upsert(false, baseRecord({ sectionId: "seccion-cdt_rt_filtrado" }));
    expect(store.getCredential(false, "run-1")).toEqual({
      token: "cdt_rt_secreto",
      lastEventId: 3,
      tokenExpiresAt: null,
    });
  });
});

describe("F3-7B-R1 — la copia de diagnóstico de un JSON corrupto nunca contiene el token en claro", () => {
  it("un corrupto que aún contiene 'cdt_rt_...' en texto plano se redacta antes de aislarse", () => {
    const sessionStorage = makeMemoryStorage();
    // Reproduce el caso reportado: JSON corrupto (el parseo falla) pero
    // con el token todavía legible como subcadena.
    sessionStorage.setItem("cdd.runs.v1", '{"token":"cdt_rt_activo","broken":');
    const store = createRunsStore({ sessionStorage, localStorage: makeMemoryStorage(), now: () => 1785215567613 });

    store.listPublic(false); // dispara la lectura que aísla el corrupto

    const diagnosticKey = [...sessionStorage._map.keys()].find((k) => k.startsWith("cdd.runs.v1.corrupt."));
    expect(diagnosticKey).toBeDefined();
    const diagnosticValue = sessionStorage.getItem(diagnosticKey);
    expect(diagnosticValue).not.toContain("cdt_rt_activo");
    expect(diagnosticValue).toContain("[REDACTADO]");
  });

  it("una escritura válida exitosa barre las copias de diagnóstico previas de esa misma clave", () => {
    const sessionStorage = makeMemoryStorage();
    sessionStorage.setItem("cdd.runs.v1", "{esto no es json");
    sessionStorage.setItem("cdd.runs.v1.corrupt.111", "resto viejo");
    const store = createRunsStore({ sessionStorage, localStorage: makeMemoryStorage(), now: () => 222 });

    store.listPublic(false); // aísla el corrupto actual en .corrupt.222
    store.upsert(false, baseRecord()); // primera escritura válida real

    const remainingDiagnostics = [...sessionStorage._map.keys()].filter((k) =>
      k.startsWith("cdd.runs.v1.corrupt.")
    );
    expect(remainingDiagnostics).toEqual([]);
  });

  it("clearAll también barre las copias de diagnóstico, no solo la clave principal", () => {
    const sessionStorage = makeMemoryStorage();
    sessionStorage.setItem("cdd.runs.v1.corrupt.999", "restos con [REDACTADO]");
    sessionStorage.setItem("cdd.runs.v1", JSON.stringify({ schemaVersion: 1, records: [] }));
    const store = createRunsStore({ sessionStorage, localStorage: makeMemoryStorage(), now: () => 0 });

    store.clearAll(false);

    expect(sessionStorage.getItem("cdd.runs.v1")).toBeNull();
    expect(sessionStorage.getItem("cdd.runs.v1.corrupt.999")).toBeNull();
  });

  it("migrate() con éxito también barre las copias de diagnóstico del origen y del destino", () => {
    const sessionStorage = makeMemoryStorage();
    const localStorage = makeMemoryStorage();
    sessionStorage.setItem("cdd.runs.v1.corrupt.1", "diagnóstico viejo del origen");
    localStorage.setItem("cdd.runs.v1.corrupt.2", "diagnóstico viejo del destino");
    const store = createRunsStore({ sessionStorage, localStorage, now: () => 0 });
    store.upsert(false, baseRecord());

    const result = store.migrate(true);

    expect(result.ok).toBe(true);
    expect(sessionStorage.getItem("cdd.runs.v1.corrupt.1")).toBeNull();
    expect(localStorage.getItem("cdd.runs.v1.corrupt.2")).toBeNull();
  });
});
