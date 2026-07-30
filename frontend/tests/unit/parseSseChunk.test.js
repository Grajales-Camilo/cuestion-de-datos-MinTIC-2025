import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { createSseParser } from "../../lib/sse/parseSseChunk.js";

const encoder = new TextEncoder();

function bytes(text) {
  return encoder.encode(text);
}

function runOnce(text) {
  const parser = createSseParser();
  const events = parser.push(bytes(text));
  events.push(...parser.flush());
  return events;
}

const FIXTURE_PATH = path.resolve(
  process.cwd(),
  "tests/fixtures/completed-stream.sse.txt"
);

describe("createSseParser", () => {
  it("1. despacha un evento simple con id, event y data JSON válido", () => {
    const events = runOnce('id: 1\nevent: step\ndata: {"foo":1}\n\n');

    expect(events).toEqual([
      { id: "1", event: "step", data: '{"foo":1}', json: { foo: 1 } },
    ]);
  });

  it("2. une varias líneas data: con \\n antes de interpretarlas", () => {
    const events = runOnce('data: {"a":1,\ndata: "b":2}\n\n');

    expect(events).toHaveLength(1);
    expect(events[0].data).toBe('{"a":1,\n"b":2}');
    expect(events[0].json).toEqual({ a: 1, b: 2 });
  });

  it("3. acepta \\n, \\r\\n y \\r como separador de línea con el mismo resultado", () => {
    const variants = [
      "data: hola\ndata: mundo\n\n",
      "data: hola\r\ndata: mundo\r\n\r\n",
      "data: hola\rdata: mundo\r\r",
    ];

    for (const input of variants) {
      const events = runOnce(input);
      // "hola\nmundo" no es JSON válido: se acepta el parseError adjunto,
      // lo que importa aquí es que el join de líneas dio el mismo resultado
      // sin importar el separador usado.
      expect(events).toHaveLength(1);
      expect(events[0].data).toBe("hola\nmundo");
    }
  });

  it("4. produce comment:true para líneas ': ping' sin romper el evento en construcción", () => {
    const soloComentario = runOnce(": ping\n\n");
    expect(soloComentario).toEqual([{ comment: true, data: "ping" }]);

    const comentarioIntercalado = runOnce(
      'event: step\n: keepalive\ndata: {"x":1}\n\n'
    );
    expect(comentarioIntercalado).toEqual([
      { comment: true, data: "keepalive" },
      { event: "step", data: '{"x":1}', json: { x: 1 } },
    ]);
  });

  it("5. ensambla correctamente el fixture real partido byte a byte", () => {
    const raw = readFileSync(FIXTURE_PATH);
    const parser = createSseParser();
    const events = [];

    for (let i = 0; i < raw.length; i += 1) {
      events.push(...parser.push(raw.subarray(i, i + 1)));
    }
    events.push(...parser.flush());

    expect(events).toHaveLength(10);
    expect(events.every((event) => !event.comment && !event.incomplete)).toBe(
      true
    );
    expect(events.every((event) => event.parseError === undefined)).toBe(
      true
    );

    expect(events[0]).toMatchObject({ id: "1", event: "step" });
    expect(events[0].json.node).toBe("start");

    const last = events[9];
    expect(last).toMatchObject({ id: "10", event: "answer" });
    expect(last.json.status).toBe("completed");
    expect(last.json.run_id).toBe("e6ae9a62-3394-4eee-b9e4-c76a3adf9582");
    expect(last.json.claims).toHaveLength(1);
  });

  it("6. un data: que no es JSON produce parseError en vez de lanzar una excepción", () => {
    expect(() => runOnce("data: esto no es json\n\n")).not.toThrow();

    const events = runOnce("data: esto no es json\n\n");
    expect(events).toHaveLength(1);
    expect(events[0].data).toBe("esto no es json");
    expect(events[0].json).toBeUndefined();
    expect(events[0].parseError).toBeTruthy();
    expect(typeof events[0].parseError.message).toBe("string");

    // El mensaje es constante: nunca incorpora el payload original ni datos
    // sensibles que pudiera contener (p. ej. un token pegado en el data:).
    expect(events[0].parseError.message).not.toContain("esto no es json");

    const otroPayload = runOnce(
      'data: cdt_rt_secreto123 no es json tampoco\n\n'
    );
    expect(otroPayload[0].parseError.message).not.toContain("cdt_rt_secreto123");
    expect(otroPayload[0].data).toBe("cdt_rt_secreto123 no es json tampoco");

    // Mismo mensaje sin importar el payload que falló: es una constante, no
    // una descripción derivada del dato ni del error nativo de JSON.parse.
    expect(otroPayload[0].parseError.message).toBe(
      events[0].parseError.message
    );
  });

  it("7. ignora el BOM solo al inicio del stream y respeta el espacio opcional tras ':'", () => {
    const conBom = runOnce("﻿data: x\n\n");
    // "x" no es JSON válido: lo que importa aquí es que el BOM inicial no
    // quedó pegado al valor del primer campo.
    expect(conBom).toHaveLength(1);
    expect(conBom[0].data).toBe("x");
    expect(conBom[0].data.charCodeAt(0)).not.toBe(0xfeff);

    const conEspacio = runOnce("data: valor\n\n");
    expect(conEspacio[0].data).toBe("valor");

    const sinEspacio = runOnce("data:valor\n\n");
    expect(sinEspacio[0].data).toBe("valor");

    const dosEspacios = runOnce("data:  valor\n\n");
    expect(dosEspacios[0].data).toBe(" valor");

    // Un BOM que NO está al inicio absoluto del stream no se elimina: solo
    // se ignora la primera vez, según la especificación de text/event-stream.
    const parser = createSseParser();
    const primeraParte = parser.push(bytes("data: antes\n\n"));
    const segundaParte = parser.push(bytes("data: ﻿despues\n\n"));
    expect(primeraParte[0].data).toBe("antes");
    expect(segundaParte[0].data).toBe("﻿despues");
    expect(segundaParte[0].data.charCodeAt(0)).toBe(0xfeff);
  });

  it("8. flush() finaliza el decoder y clasifica cualquier resto sin perderlo ni lanzar", () => {
    const parser = createSseParser();
    const duringPush = parser.push(
      bytes('id: 99\nevent: answer\ndata: {"partial":true}\n')
    );
    expect(duringPush).toEqual([]); // sin línea en blanco, nada se despacha todavía

    const flushed = parser.flush();
    expect(flushed).toEqual([
      { incomplete: true, id: "99", event: "answer", data: '{"partial":true}' },
    ]);

    // Secuencia UTF-8 truncada al final del stream: flush() no debe lanzar,
    // y el resultado debe quedar clasificado de forma controlada (el
    // TextDecoder nativo cierra la secuencia incompleta con U+FFFD en vez
    // de perder el byte o romper el parseo).
    const parser2 = createSseParser();
    parser2.push(bytes("data: "));
    parser2.push(new Uint8Array([0xc3])); // primer byte de "á" (0xC3 0xA1), sin el segundo
    let truncado;
    expect(() => {
      truncado = parser2.flush();
    }).not.toThrow();
    expect(truncado).toEqual([{ incomplete: true, data: "�" }]);
  });
});
