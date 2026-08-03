import { Dancing_Script } from "next/font/google";

/**
 * Excepción documentada a "tipografía única sans-serif" (constitution.md
 * Art. V / plan.md §7, "Diseño visual"): esta familia SOLO se usa para la
 * frase "- #AI for good" en los encabezados de `/` y `/app` — nunca para
 * ningún otro texto. Autohospedada con `next/font` (los archivos se
 * descargan una vez en build time y se sirven desde el propio dominio; cero
 * llamadas a Google Fonts en cada carga de página). Un solo peso (700):
 * el regular de Dancing Script es demasiado fino para leerse bien a los
 * tamaños de un encabezado.
 */
export const taglineFont = Dancing_Script({ subsets: ["latin"], weight: "700", display: "swap" });
