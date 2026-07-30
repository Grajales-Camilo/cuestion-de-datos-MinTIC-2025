/**
 * Resuelve y valida `NEXT_PUBLIC_BACKEND_URL`: la única variable de entorno
 * pública que el frontend v2 usa para hablar con el backend determinista.
 *
 * Nunca hace fallback silencioso a `localhost`: si la variable falta o es
 * inválida, lanza. El mensaje describe la regla violada, nunca el valor
 * recibido completo (podría contener credenciales embebidas) ni el objeto
 * `env` — evita filtrar cualquier otra variable presente en ese objeto.
 *
 * El acceso por defecto usa el patrón literal `process.env.NEXT_PUBLIC_BACKEND_URL`
 * (no una indirección como `process.env[nombre]` ni un parámetro por
 * defecto `env = process.env` seguido de `env.NEXT_PUBLIC_BACKEND_URL`):
 * el `DefinePlugin` de webpack que Next.js usa para inyectar variables
 * `NEXT_PUBLIC_*` en el bundle del navegador solo reemplaza esa expresión
 * exacta a nivel de código fuente — una indirección la deja como
 * `process.env.NEXT_PUBLIC_BACKEND_URL` sin sustituir, y en el navegador
 * `process` no existe, así que la función siempre "fallaría" por variable
 * ausente aunque `.env.local` la tenga bien definida. `env` sigue siendo
 * inyectable para pruebas (Node/Vitest sí tiene un `process.env` real y
 * dinámico, ajeno a esta sustitución de build).
 */
export function resolveBackendUrl(env) {
  const source = env ?? { NEXT_PUBLIC_BACKEND_URL: process.env.NEXT_PUBLIC_BACKEND_URL };
  const raw = source.NEXT_PUBLIC_BACKEND_URL;

  if (typeof raw !== "string" || raw.trim() === "") {
    throw new Error(
      "Falta NEXT_PUBLIC_BACKEND_URL. Defínela en frontend/.env.local " +
        "(ver frontend/.env.local.example); no existe un valor por defecto."
    );
  }

  let parsed;
  try {
    parsed = new URL(raw.trim());
  } catch {
    throw new Error("NEXT_PUBLIC_BACKEND_URL no es una URL válida.");
  }

  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new Error("NEXT_PUBLIC_BACKEND_URL debe usar el esquema http: o https:.");
  }
  if (parsed.username !== "" || parsed.password !== "") {
    throw new Error("NEXT_PUBLIC_BACKEND_URL no debe incluir credenciales embebidas.");
  }
  if (parsed.search !== "") {
    throw new Error("NEXT_PUBLIC_BACKEND_URL no debe incluir parámetros de consulta.");
  }
  if (parsed.hash !== "") {
    throw new Error("NEXT_PUBLIC_BACKEND_URL no debe incluir un fragmento (#).");
  }
  if (parsed.pathname !== "/") {
    throw new Error("NEXT_PUBLIC_BACKEND_URL no debe incluir una ruta distinta de la raíz.");
  }

  // Reconstrucción manual (no `parsed.origin`/`toString()`) para que la
  // barra final quede siempre normalizada fuera, sin importar cómo llegó.
  return `${parsed.protocol}//${parsed.host}`;
}
