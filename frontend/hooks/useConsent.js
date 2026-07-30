import { useCallback, useMemo, useState } from "react";
import { CURRENT_CONSENT_VERSION, clearConsent, readConsent, writeConsent } from "../lib/session/consent";

function defaultStorage() {
  return typeof window !== "undefined" ? window.localStorage : null;
}

/**
 * Integra `lib/session/consent.js` (puro) con React. Consentimiento
 * ausente, corrupto o de una versión distinta de `CURRENT_CONSENT_VERSION`
 * se refleja como `consentGranted: false` — nunca se infiere una
 * aceptación que no está en `localStorage`.
 */
export function useConsent({ storage = defaultStorage(), consentVersion = CURRENT_CONSENT_VERSION } = {}) {
  const [record, setRecord] = useState(() => readConsent({ storage, requiredVersion: consentVersion }));

  const acceptConsent = useCallback(() => {
    writeConsent({ storage, consentVersion });
    setRecord(readConsent({ storage, requiredVersion: consentVersion }));
  }, [storage, consentVersion]);

  const revokeConsent = useCallback(() => {
    clearConsent(storage);
    setRecord(readConsent({ storage, requiredVersion: consentVersion }));
  }, [storage, consentVersion]);

  return useMemo(
    () => ({
      consentGranted: record.granted,
      consentVersion: record.consentVersion,
      acceptConsent,
      revokeConsent,
    }),
    [record, acceptConsent, revokeConsent]
  );
}
