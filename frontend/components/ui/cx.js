/** Combina nombres de clase, descartando valores falsy. Sin dependencias externas. */
export function cx(...classes) {
  return classes.filter(Boolean).join(" ");
}
