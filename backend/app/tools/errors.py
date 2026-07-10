"""Sobre de error comun para las herramientas T1-T5 (contracts/agent-tools.md).

Toda herramienta devuelve `{"ok": false, "error": {"code", "message"}}` en
vez de propagar una excepcion (Art. IV.4, agent-tools.md regla comun #3):
"nunca lanza excepcion no controlada" (pruebas.md §2.1).
"""

from __future__ import annotations

from pydantic import ValidationError


def error_envelope(code: str, message: str, **extra: object) -> dict:
    error: dict[str, object] = {"code": code, "message": message}
    error.update(extra)
    return {"ok": False, "error": error}


def validation_error_envelope(exc: ValidationError) -> dict:
    """`INVALID_INPUT`: entrada que no pasa el esquema Pydantic de la herramienta."""

    first = exc.errors()[0]
    field = ".".join(str(part) for part in first["loc"])
    return error_envelope("INVALID_INPUT", f"{field}: {first['msg']}")
