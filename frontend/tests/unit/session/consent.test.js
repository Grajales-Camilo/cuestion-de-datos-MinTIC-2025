import { describe, expect, it } from "vitest";
import { CURRENT_CONSENT_VERSION, clearConsent, readConsent, writeConsent } from "../../../lib/session/consent.js";

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
  };
}

describe("consent — ausente", () => {
  it("sin registro previo: granted false", () => {
    const storage = makeMemoryStorage();
    expect(readConsent({ storage })).toEqual({ granted: false, consentVersion: null, acceptedAt: null });
  });
});

describe("consent — aceptación válida", () => {
  it("writeConsent + readConsent con la misma versión: granted true", () => {
    const storage = makeMemoryStorage();
    writeConsent({ storage, consentVersion: CURRENT_CONSENT_VERSION, now: () => "2026-07-27T00:00:00.000Z" });

    const result = readConsent({ storage, requiredVersion: CURRENT_CONSENT_VERSION });
    expect(result.granted).toBe(true);
    expect(result.consentVersion).toBe(CURRENT_CONSENT_VERSION);
    expect(result.acceptedAt).toBe("2026-07-27T00:00:00.000Z");
  });
});

describe("consent — versión distinta", () => {
  it("versión almacenada distinta de la requerida: granted false (vuelve a pedir)", () => {
    const storage = makeMemoryStorage();
    writeConsent({ storage, consentVersion: 1, now: () => "2026-07-27T00:00:00.000Z" });

    const result = readConsent({ storage, requiredVersion: 2 });
    expect(result.granted).toBe(false);
  });
});

describe("consent — corrupto", () => {
  it("JSON no interpretable: granted false, no lanza", () => {
    const storage = makeMemoryStorage();
    storage.setItem("cdd.consent.v1", "{esto no es json");
    expect(() => readConsent({ storage })).not.toThrow();
    expect(readConsent({ storage }).granted).toBe(false);
  });

  it("JSON válido pero con forma incorrecta (falta acceptedAt): granted false", () => {
    const storage = makeMemoryStorage();
    storage.setItem("cdd.consent.v1", JSON.stringify({ schemaVersion: 1, consentVersion: 1 }));
    expect(readConsent({ storage }).granted).toBe(false);
  });

  it("schemaVersion inesperado: granted false", () => {
    const storage = makeMemoryStorage();
    storage.setItem(
      "cdd.consent.v1",
      JSON.stringify({ schemaVersion: 99, consentVersion: 1, acceptedAt: "2026-07-27T00:00:00.000Z" })
    );
    expect(readConsent({ storage }).granted).toBe(false);
  });
});

describe("consent — error de almacenamiento nunca habilita el POST", () => {
  it("storage.getItem lanza: granted false, nunca true por accidente", () => {
    const throwingStorage = {
      getItem: () => {
        throw new Error("bloqueado por el navegador");
      },
      setItem: () => {},
      removeItem: () => {},
    };
    expect(readConsent({ storage: throwingStorage })).toEqual({
      granted: false,
      consentVersion: null,
      acceptedAt: null,
    });
  });
});

describe("consent — el registro nunca incluye pregunta, contexto ni tokens", () => {
  it("el documento persistido solo tiene schemaVersion, consentVersion y acceptedAt", () => {
    const storage = makeMemoryStorage();
    writeConsent({ storage, consentVersion: 1, now: () => "2026-07-27T00:00:00.000Z" });
    const raw = JSON.parse(storage.getItem("cdd.consent.v1"));
    expect(Object.keys(raw).sort()).toEqual(["acceptedAt", "consentVersion", "schemaVersion"]);
  });
});

describe("clearConsent", () => {
  it("revoca un consentimiento previamente concedido", () => {
    const storage = makeMemoryStorage();
    writeConsent({ storage, consentVersion: 1, now: () => "2026-07-27T00:00:00.000Z" });
    clearConsent(storage);
    expect(readConsent({ storage }).granted).toBe(false);
  });
});
