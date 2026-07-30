/**
 * Lógica pura (sin React/JSX) que decide si una página de solo-desarrollo
 * está disponible. Extraída de `pages/_dev/ui.js` a propósito: Vite/Vitest
 * no puede analizar JSX dentro de un archivo `.js` sin una reconfiguración
 * invasiva del pipeline de transformación, mientras que Next.js (SWC) sí
 * lo acepta con normalidad. Aislar la única pieza que de verdad necesita
 * probarse por unidad evita ese conflicto de herramientas sin tocar la
 * extensión del archivo de página que pide el encargo.
 */
export function devOnlyGetStaticProps(env = process.env) {
  if (env.NODE_ENV === "production") {
    return { notFound: true };
  }
  return { props: {} };
}
