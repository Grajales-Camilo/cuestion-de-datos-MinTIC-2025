"""Mensajes en español claro para `warnings_user` (Art. V.5, contracts/validacion-calidad.md §4).

Ningún mensaje nombra checks técnicos (`schema.columns_present`, etc.); solo
describe el problema en lenguaje que un funcionario municipal sin formación
técnica pueda entender.
"""

from __future__ import annotations

from datetime import datetime

_MESES_ES = {
    1: "enero",
    2: "febrero",
    3: "marzo",
    4: "abril",
    5: "mayo",
    6: "junio",
    7: "julio",
    8: "agosto",
    9: "septiembre",
    10: "octubre",
    11: "noviembre",
    12: "diciembre",
}


def format_month_year(value: datetime) -> str:
    return f"{_MESES_ES[value.month]} de {value.year}"


def null_ratio_warning(column: str, ratio: float) -> str:
    pct = round(ratio * 100)
    return (
        f"El {pct}% de los registros de la columna '{column}' están vacíos; "
        "los promedios o totales calculados pueden variar."
    )


def placeholder_warning(column: str, value: str) -> str:
    return (
        f"La columna '{column}' contiene el valor de relleno '{value}'; "
        "no debe interpretarse como una categoría o cifra real."
    )


def timeliness_warning(basis: str, base_date: datetime | None) -> str:
    if basis == "data_cutoff_at" and base_date is not None:
        return f"Este dato tiene corte {format_month_year(base_date)}; puede estar desactualizado."
    if basis == "data_updated_at_fallback" and base_date is not None:
        return (
            f"El portal actualizó este dataset en {format_month_year(base_date)}, pero no fue "
            "posible inferir el corte estadístico de las filas consultadas."
        )
    return (
        "No fue posible determinar ni el corte estadístico ni la fecha de actualización de "
        "este dato; su vigencia es desconocida."
    )


def empty_result_warning() -> str:
    return "La consulta no devolvió resultados; no hay datos para mostrar como hallazgo."


def missing_source_warning() -> str:
    return (
        "Falta información de la fuente (publicador o enlace de origen); este dato no se "
        "puede citar de forma verificable."
    )


def publisher_not_verified_warning() -> str:
    return (
        "No fue posible confirmar que la fuente de este dato sea una entidad oficial "
        "registrada; se muestra solo como referencia, no como sustento principal."
    )


def pii_aggregation_insufficient_warning() -> str:
    return (
        "Este dato agrupa muy pocos registros por fila; para proteger la privacidad de las "
        "personas no se puede mostrar hasta que agrupe más casos."
    )
