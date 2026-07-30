import { Html, Head, Main, NextScript } from "next/document";

/**
 * Documento HTML base de la aplicación (Next.js Pages Router). Declara
 * `lang="es"` en el elemento raíz, requisito de RNF-012 / constitution.md
 * Art. V.5 (público objetivo sin formación técnica, interfaz en español
 * claro) — aplica a todas las páginas, legacy y v2, y no cambia nada de su
 * renderizado visual.
 *
 * El meta viewport vive en `_app.js`, no aquí: Next.js advierte en build
 * si se declara en `_document.js` porque este documento se renderiza una
 * sola vez en el servidor y no participa en la navegación cliente.
 */
export default function Document() {
  return (
    <Html lang="es">
      <Head />
      <body>
        <Main />
        <NextScript />
      </body>
    </Html>
  );
}
