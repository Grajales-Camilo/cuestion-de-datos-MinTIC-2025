/**
 * Espejo JS de un solo valor de `styles/tokens.css` (paleta inspirada en
 * VS Code, revisión de dirección posterior a DESIGN-01). Existe porque
 * Chart.js recibe colores como strings en tiempo de configuración de
 * JavaScript — no puede leer una variable CSS. Esta es la ÚNICA copia de
 * `--cdt-blue-700` permitida fuera de `tokens.css`; ningún componente debe
 * escribir un hexadecimal propio. `tests/unit/ui/tokens.test.js` compara
 * este valor contra `tokens.css` para que no puedan desincronizarse en
 * silencio.
 */
export const CDT_BLUE_700 = "#0068a8";
