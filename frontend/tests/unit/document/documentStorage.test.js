import { readFileSync } from "node:fs";
import path from "node:path";
import { Editor } from "@tiptap/core";
import { afterEach, describe, expect, it } from "vitest";
import {
  DOCUMENT_STORAGE_BACKUP_PREFIX,
  DOCUMENT_STORAGE_KEY,
  DOCUMENT_STORAGE_SCHEMA_VERSION,
  DOCUMENT_STORAGE_STATUS,
  buildDocumentBackupPayload,
  buildRawBackupPayload,
  clearStoredDocument,
  loadStoredDocument,
  migrateStoredDocument,
  saveStoredDocument,
} from "../../../lib/document/documentStorage.js";
import {
  DOCUMENT_MODEL_VERSION,
  FREE_TEMPLATE_ID,
  createFreeTemplateDocument,
} from "../../../lib/document/documentModel.js";
import { EMPTY_DOCUMENT_JSON } from "../../../lib/document/documentSchema.js";
import { createDocumentEditorExtensions } from "../../../lib/document/schema.js";

const fixture = JSON.parse(
  readFileSync(path.resolve(process.cwd(), "tests/fixtures/completed-with-claims.json"), "utf8"),
);

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

/** Envoltorio de solo-escritura que reutiliza los datos YA guardados en
 * `base`, pero cuyo `setItem` siempre lanza `QuotaExceededError` — para
 * probar que un fallo de escritura conserva el último valor válido. */
function makeQuotaExceededStorage(base) {
  return {
    getItem: base.getItem,
    removeItem: base.removeItem,
    get length() {
      return base.length;
    },
    key: base.key,
    setItem: () => {
      const error = new Error("cuota agotada");
      error.name = "QuotaExceededError";
      throw error;
    },
  };
}

function makeThrowingStorage() {
  return {
    getItem: () => {
      throw new Error("bloqueado");
    },
    setItem: () => {
      throw new Error("bloqueado");
    },
    removeItem: () => {
      throw new Error("bloqueado");
    },
  };
}

// Doble sintético INLINE (mismo criterio que `documentModel.test.js`): payload
// mínimo derivado del fixture REAL `completed-with-claims.json` para insertar
// una cita de evidencia verdadera, no fabricada.
function realFixturePayload({ classification, citationId = "citation-storage-001" } = {}) {
  const evidence = structuredClone(fixture.answer.evidence[0]);
  if (classification) {
    evidence.quality = { ...evidence.quality, classification };
  }
  return {
    runId: fixture.run_id,
    evidence,
    claims: structuredClone(fixture.answer.claims),
    citationId,
    insertedAt: "2026-07-28T13:00:00.000Z",
  };
}

const editors = [];
function createEditor() {
  const editor = new Editor({
    extensions: createDocumentEditorExtensions(),
    content: { type: "doc", content: [{ type: "paragraph" }] },
  });
  editors.push(editor);
  return editor;
}
afterEach(() => {
  while (editors.length > 0) editors.pop().destroy();
});

function documentWithSectionContent(content) {
  return {
    version: DOCUMENT_MODEL_VERSION,
    templateId: FREE_TEMPLATE_ID,
    title: "Documento libre",
    sections: [{ sectionId: "seccion-1", title: "Sección 1", content }],
  };
}

describe("saveStoredDocument / loadStoredDocument — round-trip (F6-01, RF-102/RF-103, ESC-08)", () => {
  it("guarda y carga un documento libre válido", () => {
    const storage = makeMemoryStorage();
    const doc = createFreeTemplateDocument();
    doc.sections[0].content = {
      type: "doc",
      content: [{ type: "paragraph", content: [{ type: "text", text: "Texto de prueba" }] }],
    };

    expect(saveStoredDocument(storage, doc, { now: () => 1000 })).toMatchObject({ ok: true });

    const result = loadStoredDocument(storage, { now: () => 2000 });
    expect(result.status).toBe(DOCUMENT_STORAGE_STATUS.OK);
    expect(result.document).toEqual(doc);
    expect(result.envelope).toMatchObject({
      schemaVersion: DOCUMENT_STORAGE_SCHEMA_VERSION,
      createdAt: "1970-01-01T00:00:01.000Z",
    });
  });

  it("round-trip exacto de texto y EvidenceCitationNode (fixture real)", () => {
    const storage = makeMemoryStorage();
    const editor = createEditor();
    editor.commands.insertContent("Diagnóstico de cobertura educativa.");
    expect(editor.commands.insertEvidenceCitation(realFixturePayload())).toBe(true);
    const content = editor.getJSON();

    const doc = documentWithSectionContent(content);
    expect(saveStoredDocument(storage, doc).ok).toBe(true);

    const result = loadStoredDocument(storage);
    expect(result.status).toBe(DOCUMENT_STORAGE_STATUS.OK);
    expect(result.document.sections[0].content).toEqual(content);

    const [citation] = result.document.sections[0].content.content.filter((node) => node.type === "evidenceCitation");
    expect(citation.attrs.runId).toBe(fixture.run_id);
    expect(citation.attrs.evidenceId).toBe(fixture.answer.evidence[0].evidence_id);
    expect(citation.attrs.eligibilityStatus).toBe("eligible");
  });

  it("warningRequired:true sobrevive el round-trip", () => {
    const storage = makeMemoryStorage();
    const editor = createEditor();
    expect(
      editor.commands.insertEvidenceCitation(
        realFixturePayload({ classification: "no_recomendada", citationId: "citation-warn-001" }),
      ),
    ).toBe(true);
    const content = editor.getJSON();
    saveStoredDocument(storage, documentWithSectionContent(content));

    const result = loadStoredDocument(storage);
    const [citation] = result.document.sections[0].content.content.filter((node) => node.type === "evidenceCitation");
    expect(citation.attrs.warningRequired).toBe(true);
    expect(citation.attrs.qualityClassification).toBe("no_recomendada");
  });

  it("ningún token aparece en el sobre persistido", () => {
    const storage = makeMemoryStorage();
    const editor = createEditor();
    editor.commands.insertContent("Sección con evidencia real.");
    editor.commands.insertEvidenceCitation(realFixturePayload());
    saveStoredDocument(storage, documentWithSectionContent(editor.getJSON()));

    const raw = storage.getItem(DOCUMENT_STORAGE_KEY);
    expect(raw).not.toMatch(/cdt_rt_[A-Za-z0-9_-]+/);
    expect(raw.toLowerCase()).not.toContain('"token"');
    expect(raw.toLowerCase()).not.toContain('"authorization"');
  });

  it("no guarda un documento semánticamente inválido", () => {
    const storage = makeMemoryStorage();
    const invalidDoc = { version: DOCUMENT_MODEL_VERSION, templateId: FREE_TEMPLATE_ID, title: "x", sections: [] };
    const result = saveStoredDocument(storage, invalidDoc);
    expect(result).toEqual({ ok: false, reason: "invalid_document", code: "INVALID_SECTIONS" });
    expect(storage.getItem(DOCUMENT_STORAGE_KEY)).toBeNull();
  });

  it("QuotaExceededError al guardar conserva el último documento válido en el almacén", () => {
    const base = makeMemoryStorage();
    const validDoc = createFreeTemplateDocument();
    saveStoredDocument(base, validDoc, { now: () => 1 });
    const previousRaw = base.getItem(DOCUMENT_STORAGE_KEY);

    const quotaLimited = makeQuotaExceededStorage(base);
    const otherDoc = createFreeTemplateDocument();
    otherDoc.sections[0].content.content.push({ type: "paragraph" });
    const result = saveStoredDocument(quotaLimited, otherDoc, { now: () => 2 });

    expect(result).toEqual({ ok: false, reason: "quota_exceeded" });
    expect(base.getItem(DOCUMENT_STORAGE_KEY)).toBe(previousRaw);
  });

  it("storage no disponible (null o que lanza) nunca lanza", () => {
    expect(() => loadStoredDocument(null)).not.toThrow();
    expect(loadStoredDocument(null).status).toBe(DOCUMENT_STORAGE_STATUS.EMPTY);

    const throwing = makeThrowingStorage();
    expect(() => loadStoredDocument(throwing)).not.toThrow();
    expect(loadStoredDocument(throwing).status).toBe(DOCUMENT_STORAGE_STATUS.UNAVAILABLE);

    expect(() => saveStoredDocument(throwing, createFreeTemplateDocument())).not.toThrow();
    expect(() => clearStoredDocument(throwing)).not.toThrow();
  });

  it("una sección inválida impide restaurar el documento completo (sin carga parcial)", () => {
    const storage = makeMemoryStorage();
    const doc = createFreeTemplateDocument();
    doc.sections.push({ sectionId: "seccion-2", title: "Sección 2", content: structuredClone(EMPTY_DOCUMENT_JSON) });
    saveStoredDocument(storage, doc);

    const envelope = JSON.parse(storage.getItem(DOCUMENT_STORAGE_KEY));
    envelope.document.sections[1].content = { type: "doc", content: [{ type: "nodo-inexistente" }] };
    storage.setItem(DOCUMENT_STORAGE_KEY, JSON.stringify(envelope));

    const result = loadStoredDocument(storage);
    expect(result.status).toBe(DOCUMENT_STORAGE_STATUS.INVALID);
    expect(result.document).toBeNull();
  });
});

describe("loadStoredDocument — corrupción y versiones (PARTE 4)", () => {
  it("JSON corrupto se aísla en una clave de diagnóstico; la clave original queda intacta", () => {
    const storage = makeMemoryStorage();
    storage.setItem(DOCUMENT_STORAGE_KEY, "{no es json");

    const result = loadStoredDocument(storage, { now: () => 5000 });

    expect(result.status).toBe(DOCUMENT_STORAGE_STATUS.CORRUPT);
    expect(result.document).toBeNull();
    expect(result.diagnosticKey).toBe(`${DOCUMENT_STORAGE_KEY}.corrupt.5000`);
    expect(storage.getItem(result.diagnosticKey)).toBe("{no es json");
    expect(storage.getItem(DOCUMENT_STORAGE_KEY)).toBe("{no es json");
  });

  it("la copia diagnóstica de un JSON corrupto queda redactada", () => {
    const storage = makeMemoryStorage();
    storage.setItem(DOCUMENT_STORAGE_KEY, '{"token": "cdt_rt_abc123", roto');

    const result = loadStoredDocument(storage, { now: () => 6000 });

    expect(storage.getItem(result.diagnosticKey)).not.toContain("cdt_rt_abc123");
    expect(storage.getItem(result.diagnosticKey)).toContain("[REDACTADO]");
    expect(result.raw).not.toContain("cdt_rt_abc123");
  });

  it("un documento semánticamente inválido se aísla y nunca se muestra parcialmente", () => {
    const storage = makeMemoryStorage();
    const envelope = {
      schemaVersion: DOCUMENT_STORAGE_SCHEMA_VERSION,
      createdAt: "2026-01-01T00:00:00.000Z",
      updatedAt: "2026-01-01T00:00:00.000Z",
      document: { version: DOCUMENT_MODEL_VERSION, templateId: "plantilla-desconocida", title: "x", sections: [] },
    };
    storage.setItem(DOCUMENT_STORAGE_KEY, JSON.stringify(envelope));

    const result = loadStoredDocument(storage, { now: () => 6500 });

    expect(result.status).toBe(DOCUMENT_STORAGE_STATUS.INVALID);
    expect(result.document).toBeNull();
    expect(result.diagnosticKey).toBe(`${DOCUMENT_STORAGE_KEY}.corrupt.6500`);
    expect(storage.getItem(DOCUMENT_STORAGE_KEY)).toBe(JSON.stringify(envelope));
  });

  it("una versión futura no se abre ni se sobrescribe", () => {
    const storage = makeMemoryStorage();
    const futureEnvelope = {
      schemaVersion: DOCUMENT_STORAGE_SCHEMA_VERSION + 1,
      createdAt: "2026-01-01T00:00:00.000Z",
      updatedAt: "2026-01-02T00:00:00.000Z",
      document: { version: 999, templateId: "algo-futuro", title: "Futuro", sections: [] },
    };
    storage.setItem(DOCUMENT_STORAGE_KEY, JSON.stringify(futureEnvelope));

    const result = loadStoredDocument(storage);

    expect(result.status).toBe(DOCUMENT_STORAGE_STATUS.FUTURE_VERSION);
    expect(result.document).toBeNull();
    expect(result.envelope).toEqual(futureEnvelope);
    expect(JSON.parse(storage.getItem(DOCUMENT_STORAGE_KEY))).toEqual(futureEnvelope);
  });

  it("buildDocumentBackupPayload / buildRawBackupPayload producen JSON descargable sin volver a envolver un raw ya-texto", () => {
    const value = { a: 1 };
    const objectPayload = buildDocumentBackupPayload(value, { now: () => 1000 });
    expect(JSON.parse(objectPayload.contents)).toEqual(value);
    expect(objectPayload.filename).toMatch(/^cuestion-de-datos-documento-.*\.json$/);

    const raw = '{"a":1}';
    const rawPayload = buildRawBackupPayload(raw, { now: () => 1000 });
    expect(rawPayload.contents).toBe(raw);
  });
});

describe("migrateStoredDocument — runner genérico (DOBLE SINTÉTICO: no hay historia real de cdd.doc.v1 anterior a F6-01)", () => {
  // `cdd.doc.v1` nunca existió antes de este incremento, así que no hay
  // ninguna forma "v0" real que migrar. Este bloque ejercita el runner
  // ENCADENADO con un paso inventado exclusivamente para la prueba
  // (`schemaVersion: 0`), nunca registrado en producción — ver docstring de
  // `documentStorage.js`. No se fabrica evidencia histórica: el resultado de
  // estas pruebas describe el comportamiento del runner, no un hecho sobre
  // versiones reales de la app.
  function syntheticV0Envelope() {
    return {
      schemaVersion: 0,
      createdAt: "2020-01-01T00:00:00.000Z",
      updatedAt: "2020-01-01T00:00:00.000Z",
      legacyDocument: { templateId: FREE_TEMPLATE_ID }, // forma v0 sintética, distinta de `document`
    };
  }
  const syntheticMigrations = {
    0: (envelope) => ({
      schemaVersion: 1,
      createdAt: envelope.createdAt,
      updatedAt: envelope.updatedAt,
      document: createFreeTemplateDocument(),
    }),
  };

  it("crea un backup en cdd.doc.backup.<versión de origen> antes de modificar", () => {
    const storage = makeMemoryStorage();
    const original = syntheticV0Envelope();

    const result = migrateStoredDocument(original, { migrations: syntheticMigrations, storage, now: () => 7000 });

    expect(result.ok).toBe(true);
    expect(result.migrated).toBe(true);
    expect(JSON.parse(storage.getItem(`${DOCUMENT_STORAGE_BACKUP_PREFIX}0`))).toEqual(original);
  });

  it("es idempotente: aplicarla dos veces sobre su propio resultado no cambia nada", () => {
    const storage = makeMemoryStorage();
    const original = syntheticV0Envelope();

    const first = migrateStoredDocument(original, { migrations: syntheticMigrations, storage, now: () => 7000 });
    const second = migrateStoredDocument(first.envelope, { migrations: syntheticMigrations, storage, now: () => 8000 });

    expect(second).toEqual({ ok: true, envelope: first.envelope, migrated: false });
  });

  it("una migración fallida conserva el sobre original intacto", () => {
    const storage = makeMemoryStorage();
    const original = syntheticV0Envelope();
    const brokenMigrations = {
      0: () => {
        throw new Error("boom");
      },
    };

    const result = migrateStoredDocument(original, { migrations: brokenMigrations, storage, now: () => 9000 });

    expect(result).toEqual({ ok: false, reason: "migration_threw", envelope: original });
  });

  it("loadStoredDocument: MIGRATION_FAILED no sobrescribe el sobre original ya persistido", () => {
    const storage = makeMemoryStorage();
    const original = syntheticV0Envelope();
    storage.setItem(DOCUMENT_STORAGE_KEY, JSON.stringify(original));
    const brokenMigrations = {
      0: () => {
        throw new Error("boom");
      },
    };

    const result = loadStoredDocument(storage, { migrations: brokenMigrations, now: () => 9500 });

    expect(result.status).toBe(DOCUMENT_STORAGE_STATUS.MIGRATION_FAILED);
    expect(result.document).toBeNull();
    expect(JSON.parse(storage.getItem(DOCUMENT_STORAGE_KEY))).toEqual(original);
  });

  describe("F6-01-R1: backup verificado (write+reread+comparar) y cadena estricta", () => {
    it("backup rechazado al escribir: migración bloqueada, cdd.doc.v1 byte-idéntico, sin backup", () => {
      const base = makeMemoryStorage();
      const original = syntheticV0Envelope();
      const rejectingBackup = {
        getItem: base.getItem,
        removeItem: base.removeItem,
        get length() {
          return base.length;
        },
        key: base.key,
        setItem: (key, value) => {
          if (key.startsWith(DOCUMENT_STORAGE_BACKUP_PREFIX)) {
            const error = new Error("cuota agotada solo para el backup");
            error.name = "QuotaExceededError";
            throw error;
          }
          base.setItem(key, value);
        },
      };
      rejectingBackup.setItem(DOCUMENT_STORAGE_KEY, JSON.stringify(original));

      const result = migrateStoredDocument(original, {
        migrations: syntheticMigrations,
        storage: rejectingBackup,
        now: () => 10_000,
      });

      expect(result).toEqual({ ok: false, reason: "backup_write_failed", envelope: original });
      expect(base.getItem(DOCUMENT_STORAGE_KEY)).toBe(JSON.stringify(original));
      expect(base.getItem(`${DOCUMENT_STORAGE_BACKUP_PREFIX}0`)).toBeNull();
    });

    it("backup 'exitoso' según setItem pero no releído igual (Storage que reporta éxito sin persistir de verdad): migración bloqueada", () => {
      const base = makeMemoryStorage();
      const original = syntheticV0Envelope();
      base.setItem(DOCUMENT_STORAGE_KEY, JSON.stringify(original));
      const silentlyDroppingBackup = {
        getItem: base.getItem,
        removeItem: base.removeItem,
        get length() {
          return base.length;
        },
        key: base.key,
        setItem: (key, value) => {
          if (key.startsWith(DOCUMENT_STORAGE_BACKUP_PREFIX)) return; // no lanza, pero tampoco persiste
          base.setItem(key, value);
        },
      };

      const result = migrateStoredDocument(original, {
        migrations: syntheticMigrations,
        storage: silentlyDroppingBackup,
        now: () => 10_500,
      });

      expect(result).toEqual({ ok: false, reason: "backup_verification_failed", envelope: original });
      expect(base.getItem(DOCUMENT_STORAGE_KEY)).toBe(JSON.stringify(original));
    });

    it("backup escrito y verificado exactamente igual al original: la migración SÍ se ejecuta", () => {
      const storage = makeMemoryStorage();
      const original = syntheticV0Envelope();

      const result = migrateStoredDocument(original, { migrations: syntheticMigrations, storage, now: () => 11_000 });

      expect(result.ok).toBe(true);
      expect(result.envelope.schemaVersion).toBe(DOCUMENT_STORAGE_SCHEMA_VERSION);
      expect(JSON.parse(storage.getItem(`${DOCUMENT_STORAGE_BACKUP_PREFIX}0`))).toEqual(original);
    });

    it("un paso 0→2 se rechaza cerrado cuando la versión soportada es 1 (nunca se acepta como si fuera 0→1)", () => {
      const storage = makeMemoryStorage();
      const original = syntheticV0Envelope();
      const skipAheadMigrations = {
        0: (envelope) => ({ schemaVersion: 2, createdAt: envelope.createdAt, updatedAt: envelope.updatedAt, document: {} }),
      };

      const result = migrateStoredDocument(original, { migrations: skipAheadMigrations, storage, now: () => 12_000 });

      expect(result).toEqual({ ok: false, reason: "migration_step_invalid", envelope: original });
    });

    it("un paso que no avanza (0→0) se rechaza cerrado", () => {
      const storage = makeMemoryStorage();
      const original = syntheticV0Envelope();
      const noProgressMigrations = {
        0: (envelope) => ({ ...envelope, schemaVersion: 0 }),
      };

      const result = migrateStoredDocument(original, { migrations: noProgressMigrations, storage, now: () => 12_500 });

      expect(result).toEqual({ ok: false, reason: "migration_step_invalid", envelope: original });
    });

    it("un paso que retrocede la versión se rechaza cerrado (no solo 'no avanza')", () => {
      // No existe hoy una versión soportada > 1, así que un "1→0" real no es
      // alcanzable desde la API pública (schemaVersion 1 ya es la vigente y
      // nunca entra al bucle de migración). Este caso ejercita la misma
      // invariante (`next !== current + 1`) con un retroceso genuino
      // (0→-1), que sí es alcanzable con el runner actual.
      const storage = makeMemoryStorage();
      const original = syntheticV0Envelope();
      const regressingMigrations = {
        0: (envelope) => ({ ...envelope, schemaVersion: -1 }),
      };

      const result = migrateStoredDocument(original, { migrations: regressingMigrations, storage, now: () => 13_000 });

      expect(result).toEqual({ ok: false, reason: "migration_step_invalid", envelope: original });
    });

    it("la cadena exacta hasta la versión soportada (0→1, único paso real hoy) tiene éxito", () => {
      const storage = makeMemoryStorage();
      const original = syntheticV0Envelope();

      const result = migrateStoredDocument(original, { migrations: syntheticMigrations, storage, now: () => 13_500 });

      expect(result.ok).toBe(true);
      expect(result.envelope.schemaVersion).toBe(DOCUMENT_STORAGE_SCHEMA_VERSION);
    });

    it("un paso ausente conserva el original intacto (el backup ya escrito no se pierde)", () => {
      const storage = makeMemoryStorage();
      const original = syntheticV0Envelope();

      const result = migrateStoredDocument(original, { migrations: {}, storage, now: () => 14_000 });

      expect(result).toEqual({ ok: false, reason: "no_migration_path", envelope: original });
      expect(JSON.parse(storage.getItem(`${DOCUMENT_STORAGE_BACKUP_PREFIX}0`))).toEqual(original);
    });

    it("una excepción durante un paso conserva el original Y el backup ya verificado", () => {
      const storage = makeMemoryStorage();
      const original = syntheticV0Envelope();
      const throwingMigrations = {
        0: () => {
          throw new Error("boom");
        },
      };

      const result = migrateStoredDocument(original, { migrations: throwingMigrations, storage, now: () => 14_500 });

      expect(result).toEqual({ ok: false, reason: "migration_threw", envelope: original });
      expect(JSON.parse(storage.getItem(`${DOCUMENT_STORAGE_BACKUP_PREFIX}0`))).toEqual(original);
    });

    it("una migración exitosa CONSERVA el backup (nunca se borra automáticamente)", () => {
      const storage = makeMemoryStorage();
      const original = syntheticV0Envelope();

      const result = migrateStoredDocument(original, { migrations: syntheticMigrations, storage, now: () => 15_000 });

      expect(result.ok).toBe(true);
      expect(storage.getItem(`${DOCUMENT_STORAGE_BACKUP_PREFIX}0`)).not.toBeNull();

      // Solo un borrado deliberado del documento completo limpia backups.
      clearStoredDocument(storage);
      expect(storage.getItem(`${DOCUMENT_STORAGE_BACKUP_PREFIX}0`)).toBeNull();
    });
  });
});

describe("F6-02A PARTE 1.2: migración lograda en memoria pero no persistida", () => {
  // DOBLE SINTÉTICO (mismo criterio que el resto del bloque `migrateStoredDocument`):
  // no hay ninguna migración real registrada en producción todavía.
  function syntheticV0Envelope() {
    return {
      schemaVersion: 0,
      createdAt: "2020-01-01T00:00:00.000Z",
      updatedAt: "2020-01-01T00:00:00.000Z",
      legacyDocument: { templateId: FREE_TEMPLATE_ID },
    };
  }
  const syntheticMigrations = {
    0: (envelope) => ({
      schemaVersion: 1,
      createdAt: envelope.createdAt,
      updatedAt: envelope.updatedAt,
      document: createFreeTemplateDocument(),
    }),
  };

  /** Envoltorio cuyo `setItem` falla EXCLUSIVAMENTE para `blockedKey` (la
   * clave vigente `cdd.doc.v1`), simulando que el backup sí prosperó pero la
   * escritura final del sobre migrado no. */
  function makeWriteBlockedForKeyStorage(base, blockedKey) {
    return {
      getItem: base.getItem,
      removeItem: base.removeItem,
      get length() {
        return base.length;
      },
      key: base.key,
      setItem: (key, value) => {
        if (key === blockedKey) {
          const error = new Error("cuota agotada al persistir la migración");
          error.name = "QuotaExceededError";
          throw error;
        }
        base.setItem(key, value);
      },
    };
  }

  it("loadStoredDocument NUNCA devuelve status:'ok' si la escritura del sobre migrado falla", () => {
    const base = makeMemoryStorage();
    const original = syntheticV0Envelope();
    base.setItem(DOCUMENT_STORAGE_KEY, JSON.stringify(original));
    const storage = makeWriteBlockedForKeyStorage(base, DOCUMENT_STORAGE_KEY);

    const result = loadStoredDocument(storage, { migrations: syntheticMigrations, now: () => 20_000 });

    expect(result.status).not.toBe(DOCUMENT_STORAGE_STATUS.OK);
    expect(result.status).toBe(DOCUMENT_STORAGE_STATUS.MIGRATION_FAILED);
    expect(result.document).toBeNull();
    expect(result.reason).toBe("migration_write_failed");
  });

  it("tras el fallo de escritura, la clave original y el backup verificado permanecen intactos", () => {
    const base = makeMemoryStorage();
    const original = syntheticV0Envelope();
    base.setItem(DOCUMENT_STORAGE_KEY, JSON.stringify(original));
    const storage = makeWriteBlockedForKeyStorage(base, DOCUMENT_STORAGE_KEY);

    loadStoredDocument(storage, { migrations: syntheticMigrations, now: () => 20_500 });

    expect(JSON.parse(base.getItem(DOCUMENT_STORAGE_KEY))).toEqual(original);
    expect(JSON.parse(base.getItem(`${DOCUMENT_STORAGE_BACKUP_PREFIX}0`))).toEqual(original);
  });
});

describe("F6-02A PARTE 1.3: una migración no puede mutar el sobre original devuelto", () => {
  // DOBLE SINTÉTICO inline: simula una migración con un bug real (muta su
  // propio argumento) para verificar que el runner nunca deja que esa
  // mutación se filtre al valor "original" que se ofrece para descarga.
  function syntheticV0Envelope() {
    return {
      schemaVersion: 0,
      createdAt: "2020-01-01T00:00:00.000Z",
      updatedAt: "2020-01-01T00:00:00.000Z",
      legacyDocument: { templateId: FREE_TEMPLATE_ID },
    };
  }

  it("una migración que muta su argumento y LUEGO LANZA no altera el valor devuelto ni el backup", () => {
    const storage = makeMemoryStorage();
    const original = syntheticV0Envelope();
    const pristine = structuredClone(original);
    const mutatingThrowMigrations = {
      0: (envelope) => {
        envelope.legacyDocument.templateId = "MUTADO-POR-BUG";
        envelope.schemaVersion = 1;
        throw new Error("boom-after-mutating");
      },
    };

    const result = migrateStoredDocument(original, {
      migrations: mutatingThrowMigrations,
      storage,
      now: () => 21_000,
    });

    expect(result).toEqual({ ok: false, reason: "migration_threw", envelope: pristine });
    expect(original).toEqual(pristine);
    expect(JSON.parse(storage.getItem(`${DOCUMENT_STORAGE_BACKUP_PREFIX}0`))).toEqual(pristine);
  });

  it("una migración que muta su argumento y SALTA DE VERSIÓN no altera el valor devuelto", () => {
    const storage = makeMemoryStorage();
    const original = syntheticV0Envelope();
    const pristine = structuredClone(original);
    const mutatingSkipMigrations = {
      0: (envelope) => {
        envelope.legacyDocument.templateId = "MUTADO-SKIP";
        return { schemaVersion: 2, createdAt: envelope.createdAt, updatedAt: envelope.updatedAt, document: {} };
      },
    };

    const result = migrateStoredDocument(original, {
      migrations: mutatingSkipMigrations,
      storage,
      now: () => 21_500,
    });

    expect(result).toEqual({ ok: false, reason: "migration_step_invalid", envelope: pristine });
    expect(original).toEqual(pristine);
  });

  it("una migración que muta su argumento y SE ESTANCA (no avanza de versión) no altera el valor devuelto", () => {
    const storage = makeMemoryStorage();
    const original = syntheticV0Envelope();
    const pristine = structuredClone(original);
    const mutatingStuckMigrations = {
      0: (envelope) => {
        envelope.legacyDocument.templateId = "MUTADO-ESTANCADO";
        return { ...envelope, schemaVersion: 0 };
      },
    };

    const result = migrateStoredDocument(original, {
      migrations: mutatingStuckMigrations,
      storage,
      now: () => 22_000,
    });

    expect(result).toEqual({ ok: false, reason: "migration_step_invalid", envelope: pristine });
    expect(original).toEqual(pristine);
  });

  it("loadStoredDocument: el envelope ofrecido para descarga tras MIGRATION_FAILED nunca refleja la mutación de una migración con bug", () => {
    const storage = makeMemoryStorage();
    const original = syntheticV0Envelope();
    const pristine = structuredClone(original);
    storage.setItem(DOCUMENT_STORAGE_KEY, JSON.stringify(original));
    const mutatingThrowMigrations = {
      0: (envelope) => {
        envelope.legacyDocument.templateId = "MUTADO-POR-BUG";
        throw new Error("boom");
      },
    };

    const result = loadStoredDocument(storage, { migrations: mutatingThrowMigrations, now: () => 22_500 });

    expect(result.status).toBe(DOCUMENT_STORAGE_STATUS.MIGRATION_FAILED);
    expect(result.envelope).toEqual(pristine);
  });
});

describe("Descargas saneadas (F6-01-R1, PARTE 6.18): cero token/Authorization en el contenido descargable", () => {
  it("buildDocumentBackupPayload y buildRawBackupPayload nunca contienen un token de corrida", () => {
    const doc = createFreeTemplateDocument();
    const objectPayload = buildDocumentBackupPayload({ schemaVersion: 1, createdAt: "x", updatedAt: "y", document: doc });
    expect(objectPayload.contents).not.toMatch(/cdt_rt_[A-Za-z0-9_-]+/);
    expect(objectPayload.contents.toLowerCase()).not.toContain('"authorization"');

    const rawPayload = buildRawBackupPayload('{"token":"[REDACTADO]", roto');
    expect(rawPayload.contents).not.toMatch(/cdt_rt_[A-Za-z0-9_-]+/);
  });
});
