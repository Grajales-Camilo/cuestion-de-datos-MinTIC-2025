/**
 * Parser SSE (Server-Sent Events) incremental y puro.
 *
 * Sin I/O, sin red, sin estado global: recibe bytes crudos (`Uint8Array`) a
 * medida que llegan de un `fetch()` en curso y devuelve los eventos que ya
 * quedaron completos. Nunca asume que un chunk de red equivale a una línea o
 * a un evento — un evento puede llegar partido en cualquier byte entre dos
 * chunks, incluso a mitad de una secuencia UTF-8 multibyte.
 *
 * Uso:
 *   const parser = createSseParser();
 *   for await (const chunk of reader) {
 *     for (const event of parser.push(chunk)) handle(event);
 *   }
 *   for (const event of parser.flush()) handle(event); // fin del stream
 *
 * Forma de un evento despachado (línea en blanco encontrada):
 *   { id?: string, event?: string, data: string, retry?: number,
 *     json?: unknown, parseError?: { message: string } }
 *
 * `json` está presente únicamente si `data` no está vacío y es JSON válido.
 * `parseError` está presente únicamente si `data` no está vacío y NO es JSON
 * válido — nunca se lanza una excepción por esto; el `data` original se
 * conserva intacto en ambos casos.
 *
 * Comentario SSE (línea que empieza con `:`, p. ej. `: ping`):
 *   { comment: true, data: string }
 * Se despacha de inmediato, sin alterar el evento que se esté acumulando.
 *
 * Resto sin terminar al llamar a `flush()` (el stream terminó antes de la
 * línea en blanco que dispara el despacho): se clasifica, nunca se descarta
 * en silencio ni se hace pasar por un evento válido.
 *   { incomplete: true, id?: string, event?: string, data: string, retry?: number }
 */

const LINE_BREAK = /\r\n|\r|\n/;

function splitLines(buffer) {
  const lines = [];
  let lineStart = 0;
  let i = 0;

  while (i < buffer.length) {
    const ch = buffer[i];
    if (ch === "\n") {
      lines.push(buffer.slice(lineStart, i));
      i += 1;
      lineStart = i;
    } else if (ch === "\r") {
      if (i + 1 < buffer.length) {
        const isCrLf = buffer[i + 1] === "\n";
        lines.push(buffer.slice(lineStart, i));
        i += isCrLf ? 2 : 1;
        lineStart = i;
      } else {
        // El '\r' es el último carácter disponible: podría ser el primer
        // byte de un '\r\n' partido entre dos chunks. No se resuelve
        // todavía; queda en el resto para la siguiente llamada.
        break;
      }
    } else {
      i += 1;
    }
  }

  return { lines, rest: buffer.slice(lineStart) };
}

function parseField(line) {
  if (line === "") return { blank: true };
  if (line.startsWith(":")) return { comment: true, text: line.slice(1).trimStart() };

  const colonIndex = line.indexOf(":");
  let name;
  let value;
  if (colonIndex === -1) {
    name = line;
    value = "";
  } else {
    name = line.slice(0, colonIndex);
    value = line.slice(colonIndex + 1);
    if (value.startsWith(" ")) value = value.slice(1);
  }
  return { field: name, value };
}

// Mensaje deliberadamente constante: nunca debe incorporar el payload
// original, tokens ni el mensaje nativo de `JSON.parse` (que en algunos
// motores cita fragmentos del texto que falló al parsear). El dato crudo
// solo vive en `event.data`.
const JSON_PARSE_ERROR_MESSAGE = 'El campo "data" no es JSON válido.';

function attachJson(event) {
  if (event.data === "") return event;
  try {
    event.json = JSON.parse(event.data);
  } catch {
    event.parseError = { message: JSON_PARSE_ERROR_MESSAGE };
  }
  return event;
}

export function createSseParser() {
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let pending = null; // evento en construcción: { id?, event?, dataLines, retry? }

  function ensurePending() {
    if (pending === null) pending = { dataLines: [] };
    return pending;
  }

  function applyLine(line, out) {
    const parsed = parseField(line);

    if (parsed.comment) {
      out.push({ comment: true, data: parsed.text });
      return;
    }

    if (parsed.blank) {
      if (pending === null) return; // línea en blanco sin evento acumulado: no-op
      const event = {};
      if (pending.id !== undefined) event.id = pending.id;
      if (pending.event !== undefined) event.event = pending.event;
      if (pending.retry !== undefined) event.retry = pending.retry;
      event.data = pending.dataLines.join("\n");
      pending = null;
      out.push(attachJson(event));
      return;
    }

    const { field, value } = parsed;
    if (field === "id") {
      ensurePending().id = value;
    } else if (field === "event") {
      ensurePending().event = value;
    } else if (field === "data") {
      ensurePending().dataLines.push(value);
    } else if (field === "retry") {
      if (/^\d+$/.test(value)) ensurePending().retry = Number(value);
    }
    // Campos desconocidos se ignoran, según la especificación de SSE.
  }

  function push(chunk) {
    const text = decoder.decode(chunk, { stream: true });
    buffer += text;
    const { lines, rest } = splitLines(buffer);
    buffer = rest;

    const out = [];
    for (const line of lines) applyLine(line, out);
    return out;
  }

  function flush() {
    const tail = decoder.decode();
    buffer += tail;

    // Un '\r' colgante al final del buffer ya no puede formar un '\r\n':
    // se resuelve aquí como el fin de la línea que lo precede.
    if (buffer.endsWith("\r")) {
      buffer = buffer.slice(0, -1) + "\n";
    }

    // Sin salto final: el texto que queda es la última línea del stream.
    if (buffer.length > 0 && !LINE_BREAK.test(buffer[buffer.length - 1])) {
      buffer += "\n";
    }

    const { lines } = splitLines(buffer);
    buffer = "";

    const out = [];
    for (const line of lines) applyLine(line, out);

    if (pending !== null) {
      const leftover = { incomplete: true };
      if (pending.id !== undefined) leftover.id = pending.id;
      if (pending.event !== undefined) leftover.event = pending.event;
      if (pending.retry !== undefined) leftover.retry = pending.retry;
      leftover.data = pending.dataLines.join("\n");
      pending = null;
      out.push(leftover);
    }

    return out;
  }

  return { push, flush };
}
