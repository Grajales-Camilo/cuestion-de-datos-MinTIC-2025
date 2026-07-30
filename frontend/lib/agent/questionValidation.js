/**
 * Validación pura de la pregunta de investigación al límite del contrato
 * (`contracts/api-rest.md` §2: `question` 10-2000 caracteres tras `trim`).
 * Compartida por `QuestionComposer` (pregunta libre) y por el flujo de
 * "Investigar esta sección" (F5-03A) para no duplicar el umbral en dos
 * sitios.
 */

export const MIN_QUESTION_LENGTH = 10;
export const MAX_QUESTION_LENGTH = 2000;

/**
 * @param {string} rawQuestion
 * @returns {{trimmed: string, tooShort: boolean, isValid: boolean}}
 */
export function validateQuestion(rawQuestion) {
  const trimmed = typeof rawQuestion === "string" ? rawQuestion.trim() : "";
  const tooShort = trimmed.length > 0 && trimmed.length < MIN_QUESTION_LENGTH;
  const isValid = trimmed.length >= MIN_QUESTION_LENGTH && trimmed.length <= MAX_QUESTION_LENGTH;
  return { trimmed, tooShort, isValid };
}
