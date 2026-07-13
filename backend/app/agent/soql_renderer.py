"""Renderer puro y determinista de ValidatedQueryPlan al subconjunto SoQL permitido."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.agent.plan_validator import (
    ValidatedFilter,
    ValidatedQueryPlan,
    ValidatedScalar,
)
from app.agent.query_plan import (
    FilterOperator,
    QueryOperation,
    ScalarType,
    SortDirection,
    SortTargetKind,
)

_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")


class RenderedQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal["rendered-query.v1"] = "rendered-query.v1"
    source_plan_hash: str
    dataset_id: str
    canonical_soql: str
    dimension_aliases: tuple[str, ...]
    metric_aliases: tuple[str, ...]
    group_count_alias: str | None
    purpose: str


def _identifier(value: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"identificador SoQL inválido: {value!r}")
    return value


def _number(value: str, *, integer: bool) -> str:
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"literal numérico inválido: {value!r}") from exc
    if not parsed.is_finite():
        raise ValueError("los literales numéricos deben ser finitos")
    if integer and parsed != parsed.to_integral_value():
        raise ValueError(f"literal entero inválido: {value!r}")
    normalized = format(parsed.normalize(), "f")
    return "0" if normalized in {"-0", ""} else normalized


def _literal(value: ValidatedScalar) -> str:
    if value.type is ScalarType.TEXT:
        return "'" + value.value.replace("'", "''") + "'"
    if value.type is ScalarType.NUMBER:
        return _number(value.value, integer=False)
    if value.type is ScalarType.INTEGER:
        return _number(value.value, integer=True)
    if value.type is ScalarType.BOOLEAN:
        lowered = value.value.casefold()
        if lowered not in {"true", "false"}:
            raise ValueError(f"literal booleano inválido: {value.value!r}")
        return lowered
    if value.type is ScalarType.DATE:
        try:
            parsed_date = date.fromisoformat(value.value)
        except ValueError as exc:
            raise ValueError(f"literal de fecha inválido: {value.value!r}") from exc
        return f"'{parsed_date.isoformat()}'"
    if value.type is ScalarType.DATETIME:
        try:
            parsed_datetime = datetime.fromisoformat(value.value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"literal datetime inválido: {value.value!r}") from exc
        canonical = parsed_datetime.isoformat(timespec="seconds")
        return f"'{canonical}'"
    raise AssertionError(f"tipo escalar no exhaustivo: {value.type}")


def _filter(item: ValidatedFilter) -> str:
    column = _identifier(item.field_name)
    values = tuple(_literal(value) for value in item.values)
    operators = {
        FilterOperator.EQ: "=",
        FilterOperator.NE: "!=",
        FilterOperator.LT: "<",
        FilterOperator.LTE: "<=",
        FilterOperator.GT: ">",
        FilterOperator.GTE: ">=",
    }
    if item.operator in operators:
        return f"{column} {operators[item.operator]} {values[0]}"
    if item.operator is FilterOperator.IN:
        return "(" + " or ".join(f"{column} = {value}" for value in values) + ")"
    if item.operator is FilterOperator.BETWEEN:
        return f"({column} >= {values[0]} and {column} <= {values[1]})"
    if item.operator is FilterOperator.IS_NULL:
        return f"{column} is null"
    if item.operator is FilterOperator.IS_NOT_NULL:
        return f"{column} is not null"
    raise AssertionError(f"operador no exhaustivo: {item.operator}")


def render_soql(plan: ValidatedQueryPlan) -> RenderedQuery:
    """Renderiza sin I/O ni mutación; una entrada cruda se rechaza explícitamente."""

    if not isinstance(plan, ValidatedQueryPlan):
        raise TypeError("render_soql acepta exclusivamente ValidatedQueryPlan")

    dimension_aliases = tuple(f"dim_{index}" for index in range(1, len(plan.dimensions) + 1))
    metric_aliases = tuple(
        f"metric_{item.operation.value}_{index}"
        for index, item in enumerate(plan.metrics, start=1)
    )
    select_items = [
        f"{_identifier(item.field_name)} as {alias}"
        for item, alias in zip(plan.dimensions, dimension_aliases, strict=True)
    ]
    for item, alias in zip(plan.metrics, metric_aliases, strict=True):
        if item.operation is QueryOperation.COUNT:
            expression = "count(*)"
        else:
            assert item.field_name is not None
            expression = f"{item.operation.value}({_identifier(item.field_name)})"
        select_items.append(f"{expression} as {alias}")

    group_count_alias = "group_count" if plan.include_group_count else None
    if group_count_alias is not None and not any(
        item.operation is QueryOperation.COUNT for item in plan.metrics
    ):
        select_items.append(f"count(*) as {group_count_alias}")

    parts = ["select " + ", ".join(select_items)]
    if plan.filters:
        parts.append("where " + " and ".join(_filter(item) for item in plan.filters))
    if plan.operation is not QueryOperation.LOOKUP and plan.dimensions:
        parts.append(
            "group by "
            + ", ".join(_identifier(item.field_name) for item in plan.dimensions)
        )
    if plan.order_by:
        order_items: list[str] = []
        for item in plan.order_by:
            aliases = (
                dimension_aliases
                if item.target_kind is SortTargetKind.DIMENSION
                else metric_aliases
            )
            direction = "asc" if item.direction is SortDirection.ASC else "desc"
            order_items.append(f"{aliases[item.target_index]} {direction}")
        parts.append("order by " + ", ".join(order_items))
    parts.append(f"limit {plan.limit}")

    return RenderedQuery(
        source_plan_hash=plan.source_plan_hash,
        dataset_id=plan.dataset_id,
        canonical_soql=" ".join(parts),
        dimension_aliases=dimension_aliases,
        metric_aliases=metric_aliases,
        group_count_alias=group_count_alias,
        purpose=plan.purpose,
    )
