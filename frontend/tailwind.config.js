module.exports = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx}",
    "./components/**/*.{js,ts,jsx,tsx}"
  ],
  theme: {
    extend: {
      // Sistema visual de Frontend v2 ("Pulso por lo Público", ver
      // /DESIGN.md y /frontend/styles/tokens.css). Prefijo `cdt-` en todo
      // token nuevo para no chocar con la paleta/escala por defecto de
      // Tailwind que el frontend LEGACY sigue usando tal cual
      // (`bg-blue-700`, `text-slate-600`, animaciones de abajo, etc.) con
      // otros valores. Los componentes nuevos de v2 solo deben usar
      // utilidades `*-cdt-*`; nunca las utilidades Tailwind por defecto de
      // color/tipografía.
      colors: {
        "cdt-blue-900": "var(--cdt-blue-900)",
        "cdt-blue-700": "var(--cdt-blue-700)",
        "cdt-blue-500": "var(--cdt-blue-500)",
        "cdt-blue-100": "var(--cdt-blue-100)",
        "cdt-blue-50": "var(--cdt-blue-50)",
        "cdt-white": "var(--cdt-white)",
        "cdt-slate-900": "var(--cdt-slate-900)",
        "cdt-slate-600": "var(--cdt-slate-600)",
        "cdt-slate-400": "var(--cdt-slate-400)",
        "cdt-success": "var(--cdt-success)",
        "cdt-warning": "var(--cdt-warning)",
        "cdt-error": "var(--cdt-error)",
      },
      fontFamily: {
        "cdt-sans": ["var(--cdt-font-sans)"],
      },
      fontWeight: {
        "cdt-normal": "var(--cdt-weight-normal)",
        "cdt-bold": "var(--cdt-weight-bold)",
      },
      fontSize: {
        "cdt-xs": ["var(--cdt-text-xs)", { lineHeight: "var(--cdt-leading-normal)" }],
        "cdt-sm": ["var(--cdt-text-sm)", { lineHeight: "var(--cdt-leading-normal)" }],
        "cdt-base": ["var(--cdt-text-base)", { lineHeight: "var(--cdt-leading-relaxed)" }],
        "cdt-lg": ["var(--cdt-text-lg)", { lineHeight: "var(--cdt-leading-normal)" }],
        "cdt-xl": ["var(--cdt-text-xl)", { lineHeight: "var(--cdt-leading-tight)" }],
        "cdt-2xl": ["var(--cdt-text-2xl)", { lineHeight: "var(--cdt-leading-tight)" }],
      },
      spacing: {
        "cdt-1": "var(--cdt-space-1)",
        "cdt-2": "var(--cdt-space-2)",
        "cdt-3": "var(--cdt-space-3)",
        "cdt-4": "var(--cdt-space-4)",
        "cdt-5": "var(--cdt-space-5)",
        "cdt-6": "var(--cdt-space-6)",
        "cdt-8": "var(--cdt-space-8)",
        "cdt-10": "var(--cdt-space-10)",
        "cdt-12": "var(--cdt-space-12)",
        "cdt-16": "var(--cdt-space-16)",
        "cdt-tap": "var(--cdt-tap-min)",
      },
      borderRadius: {
        "cdt-none": "var(--cdt-radius-none)",
        "cdt-sm": "var(--cdt-radius-sm)",
        "cdt-md": "var(--cdt-radius-md)",
        "cdt-lg": "var(--cdt-radius-lg)",
        "cdt-full": "var(--cdt-radius-full)",
      },
      transitionDuration: {
        "cdt-fast": "var(--cdt-duration-fast)",
        "cdt-base": "var(--cdt-duration-base)",
      },
      transitionTimingFunction: {
        "cdt-standard": "var(--cdt-ease-standard)",
      },
      animation: {
        'float': 'float 6s ease-in-out infinite',
        'pulse-slow': 'pulse 4s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'gradient-x': 'gradient-x 15s ease infinite',
        'bounce-slow': 'bounce 3s infinite',
      },
      keyframes: {
        float: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-20px)' },
        },
        'gradient-x': {
          '0%, 100%': {
            'background-size': '200% 200%',
            'background-position': 'left center'
          },
          '50%': {
            'background-size': '200% 200%',
            'background-position': 'right center'
          },
        },
      }
    },
  },
  plugins: [
    require('@tailwindcss/typography'),
  ],
}
