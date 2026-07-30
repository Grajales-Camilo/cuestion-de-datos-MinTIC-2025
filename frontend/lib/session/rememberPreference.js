/**
 * Preferencia "Recordar mis investigaciones en este equipo" (D-1). Es un
 * booleano inocuo, no un secreto: se guarda siempre en `localStorage` para
 * que sobreviva entre pestañas y cierres del navegador — de lo contrario,
 * activar el opt-in una vez y volver a abrir el sitio en una pestaña nueva
 * lo mostraría desmarcado otra vez, contradiciendo lo que el usuario pidió.
 * El valor por defecto ante cualquier ausencia o error es `false`
 * (desmarcado, D-1).
 */
import { safeReadJson, safeWriteJson } from "./storage.js";

export const REMEMBER_RUNS_KEY = "cdd.runs.remember.v1";

export function readRememberRuns(storage) {
  const result = safeReadJson(storage, REMEMBER_RUNS_KEY);
  if (!result.ok || result.value === null || typeof result.value !== "object") return false;
  return result.value.rememberRuns === true;
}

export function writeRememberRuns(storage, rememberRuns) {
  return safeWriteJson(storage, REMEMBER_RUNS_KEY, { rememberRuns: Boolean(rememberRuns) });
}
