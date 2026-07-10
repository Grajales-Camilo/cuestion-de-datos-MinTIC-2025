"""Guardia SoQL estructural (T-302, contracts/agent-tools.md §T5, RNF-011, RF-207).

`validate_and_canonicalize` es el unico punto de entrada: parsea la consulta
con una gramatica restringida propia (whitelist, no blacklist como nucleo),
valida contra el catalogo (`ColumnCatalog`) y produce una `CanonicalQuery`
lista para ejecutar contra la SODA API con parametros discretos
(`$select`/`$where`/`$group`/`$having`/`$order`/`$limit`/`$offset`) y para
persistir de forma estable (mismo input canonico ⇒ mismo `source_hash` en
T7, tasks.md T-403).

Decisiones de diseno no evidentes en el contrato (documentadas aqui porque
son la unica fuente; el PR las resume):
- Los codigos de error usados por rechazos puramente estructurales/de
  gramatica (sentencias multiples, clausulas fuera de lista blanca,
  funciones no permitidas, `SELECT *`, literales invalidos, limites de
  complejidad, `OFFSET > 5000`, alias no resoluble en `ORDER BY`) son todos
  `SOQL_FORBIDDEN` (agent-tools.md regla 1 ya usa ese codigo para
  "construccion no reconocida por la gramatica", y pruebas.md agrupa todos
  estos casos en la misma vinera de pruebas). `SOQL_UNKNOWN_COLUMN` queda
  reservado exclusivamente para columnas que SI son una referencia valida
  (en SELECT/WHERE/GROUP BY/HAVING, o en ORDER BY cuando coincide con una
  columna del SELECT) pero no existen en `catalog_columns` (regla 4).
- `ORDER BY` solo puede referenciar un alias declarado en el SELECT o el
  nombre de una columna que tambien aparece en el SELECT (no cualquier
  columna del dataset): evita la ambiguedad entre "alias no resoluble"
  (SOQL_FORBIDDEN, regla 10) y "columna inexistente" (SOQL_UNKNOWN_COLUMN,
  regla 4) de forma determinista.
- Funciones agregadas (`sum/avg/count/min/max`) NO se permiten dentro de
  `WHERE` (invalido en SQL/SoQL: una agregacion todavia no existe en esa
  fase de evaluacion); si o son validas en `SELECT`/`HAVING`. Funciones
  escalares (`upper/lower/date_extract_y/date_trunc_*`) se permiten como
  operandos en `WHERE`/`HAVING`/`SELECT`, no en `GROUP BY`/`ORDER BY`
  (que solo referencian columnas/alias, gramatica minima, Art. III YAGNI).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal as PyLiteral

MAX_WHERE_CONDITIONS = 15
MAX_GROUP_BY_COLUMNS = 5
MAX_OFFSET = 5000
DEFAULT_LIMIT = 1000
MAX_LIMIT = 1000

AGG_FUNCTIONS = {"sum", "avg", "count", "min", "max"}
SCALAR_FUNCTIONS = {"upper", "lower", "date_extract_y"} | {
    f"date_trunc_{unit}" for unit in ("y", "ym", "ymd")
}
ALLOWED_FUNCTIONS = AGG_FUNCTIONS | SCALAR_FUNCTIONS

_BLACKLIST_PATTERN = re.compile(
    r"(?i)\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|GRANT)\b|;"
)

_COMPARISON_OPERATORS = ("<=", ">=", "!=", "<>", "=", "<", ">")


class SoqlGuardError(Exception):
    """Rechazo de la guardia estructural, con el codigo del contrato (agent-tools.md §T5)."""

    def __init__(self, code: str, message: str, *, valid_columns: list[str] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.valid_columns = valid_columns


# --- AST -------------------------------------------------------------------


@dataclass(frozen=True)
class Column:
    name: str


@dataclass(frozen=True)
class Star:
    pass


@dataclass(frozen=True)
class Literal:
    value: object
    kind: PyLiteral["string", "number", "boolean"]


@dataclass(frozen=True)
class FuncCall:
    name: str
    args: tuple[Operand, ...]


Operand = Column | Star | Literal | FuncCall


@dataclass(frozen=True)
class Comparison:
    left: Operand
    op: str
    right: Operand


@dataclass(frozen=True)
class LikePredicate:
    left: Operand
    negated: bool
    right: Operand


@dataclass(frozen=True)
class IsNullPredicate:
    operand: Operand
    negated: bool


@dataclass(frozen=True)
class Not:
    inner: Condition


@dataclass(frozen=True)
class BoolOp:
    op: PyLiteral["AND", "OR"]
    operands: tuple[Condition, ...]


Condition = Comparison | LikePredicate | IsNullPredicate | Not | BoolOp


@dataclass(frozen=True)
class SelectItem:
    expr: Operand
    alias: str | None


@dataclass(frozen=True)
class OrderItem:
    ref: str
    direction: PyLiteral["ASC", "DESC"]


@dataclass(frozen=True)
class ParsedQuery:
    select_items: tuple[SelectItem, ...]
    where: Condition | None
    group_by: tuple[str, ...]
    having: Condition | None
    order_by: tuple[OrderItem, ...]
    limit: int
    offset: int
    limit_was_explicit: bool


# --- Lexer -------------------------------------------------------------------

_TOKEN_SPEC = [
    ("WHITESPACE", r"\s+"),
    ("STRING", r"'(?:[^']|'')*'"),
    ("NUMBER", r"\d+\.\d+|\d+"),
    ("OP", r"<=|>=|!=|<>|=|<|>|,|\(|\)|\*"),
    ("IDENT", r"[A-Za-z_][A-Za-z0-9_]*"),
]
_TOKEN_RE = re.compile("|".join(f"(?P<{name}>{pattern})" for name, pattern in _TOKEN_SPEC))

_KEYWORDS = {
    "SELECT",
    "WHERE",
    "GROUP",
    "BY",
    "HAVING",
    "ORDER",
    "LIMIT",
    "OFFSET",
    "AS",
    "AND",
    "OR",
    "NOT",
    "LIKE",
    "IS",
    "NULL",
    "ASC",
    "DESC",
    "TRUE",
    "FALSE",
}


@dataclass(frozen=True)
class Token:
    kind: str
    text: str
    pos: int


def tokenize(soql: str) -> list[Token]:
    tokens: list[Token] = []
    pos = 0
    while pos < len(soql):
        match = _TOKEN_RE.match(soql, pos)
        if match is None:
            raise SoqlGuardError(
                "SOQL_FORBIDDEN", f"caracter no reconocido por la gramatica en la posicion {pos}"
            )
        kind = match.lastgroup
        text = match.group()
        if kind != "WHITESPACE":
            if kind == "IDENT" and text.upper() in _KEYWORDS:
                tokens.append(Token(text.upper(), text, pos))
            else:
                tokens.append(Token(kind, text, pos))
        pos = match.end()
    tokens.append(Token("EOF", "", len(soql)))
    return tokens


# --- Parser ------------------------------------------------------------------


class _Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self._tokens = tokens
        self._i = 0

    def _peek(self) -> Token:
        return self._tokens[self._i]

    def _advance(self) -> Token:
        token = self._tokens[self._i]
        self._i += 1
        return token

    def _expect(self, kind: str) -> Token:
        token = self._peek()
        if token.kind != kind:
            raise SoqlGuardError(
                "SOQL_FORBIDDEN",
                f"se esperaba {kind} y se encontro {token.kind!r} ({token.text!r})",
            )
        return self._advance()

    def parse(self) -> ParsedQuery:
        self._expect("SELECT")
        select_items = self._parse_select_list()
        where = None
        if self._peek().kind == "WHERE":
            self._advance()
            where = self._parse_condition()
        group_by: tuple[str, ...] = ()
        if self._peek().kind == "GROUP":
            self._advance()
            self._expect("BY")
            group_by = self._parse_group_by_list()
        having = None
        if self._peek().kind == "HAVING":
            self._advance()
            having = self._parse_condition()
        order_by: tuple[OrderItem, ...] = ()
        if self._peek().kind == "ORDER":
            self._advance()
            self._expect("BY")
            order_by = self._parse_order_by_list()
        limit = DEFAULT_LIMIT
        limit_was_explicit = False
        if self._peek().kind == "LIMIT":
            self._advance()
            limit = int(self._expect("NUMBER").text)
            limit_was_explicit = True
        offset = 0
        if self._peek().kind == "OFFSET":
            self._advance()
            offset = int(self._expect("NUMBER").text)
        if self._peek().kind != "EOF":
            raise SoqlGuardError(
                "SOQL_FORBIDDEN",
                "token inesperado tras las clausulas reconocidas "
                f"({self._peek().text!r}); solo se admite una sentencia",
            )
        return ParsedQuery(
            select_items=select_items,
            where=where,
            group_by=group_by,
            having=having,
            order_by=order_by,
            limit=limit,
            offset=offset,
            limit_was_explicit=limit_was_explicit,
        )

    # -- SELECT --

    def _parse_select_list(self) -> tuple[SelectItem, ...]:
        items = [self._parse_select_item()]
        while self._peek().kind == "OP" and self._peek().text == ",":
            self._advance()
            items.append(self._parse_select_item())
        return tuple(items)

    def _parse_select_item(self) -> SelectItem:
        expr = self._parse_select_operand()
        alias = None
        if self._peek().kind == "AS":
            self._advance()
            alias = self._expect("IDENT").text
        return SelectItem(expr=expr, alias=alias)

    def _parse_select_operand(self) -> Operand:
        token = self._peek()
        if token.kind == "OP" and token.text == "*":
            raise SoqlGuardError(
                "SOQL_FORBIDDEN",
                "SELECT * esta prohibido; nombra columnas explicitas (regla 7)",
            )
        if token.kind == "IDENT" and self._tokens[self._i + 1].kind == "OP" and (
            self._tokens[self._i + 1].text == "("
        ):
            return self._parse_func_call()
        return self._parse_column()

    def _parse_func_call(self) -> FuncCall:
        name_token = self._expect("IDENT")
        name = name_token.text.lower()
        if name not in ALLOWED_FUNCTIONS:
            raise SoqlGuardError(
                "SOQL_FORBIDDEN", f"funcion no permitida: {name_token.text!r} (regla 6)"
            )
        self._expect("OP")  # '('
        args: list[Operand] = []
        if not (self._peek().kind == "OP" and self._peek().text == ")"):
            args.append(self._parse_func_arg())
            while self._peek().kind == "OP" and self._peek().text == ",":
                self._advance()
                args.append(self._parse_func_arg())
        closing = self._advance()
        if not (closing.kind == "OP" and closing.text == ")"):
            raise SoqlGuardError("SOQL_FORBIDDEN", "parentesis sin cerrar en llamada a funcion")
        return FuncCall(name=name, args=tuple(args))

    def _parse_func_arg(self) -> Operand:
        token = self._peek()
        if token.kind == "OP" and token.text == "*":
            self._advance()
            return Star()
        if token.kind in {"STRING", "NUMBER", "TRUE", "FALSE"}:
            return self._parse_literal()
        return self._parse_column()

    def _parse_column(self) -> Column:
        token = self._expect("IDENT")
        return Column(name=token.text.lower())

    def _parse_literal(self) -> Literal:
        token = self._advance()
        if token.kind == "STRING":
            return Literal(value=token.text[1:-1].replace("''", "'"), kind="string")
        if token.kind == "NUMBER":
            value: float | int = float(token.text) if "." in token.text else int(token.text)
            return Literal(value=value, kind="number")
        if token.kind in {"TRUE", "FALSE"}:
            return Literal(value=token.kind == "TRUE", kind="boolean")
        raise SoqlGuardError(
            "SOQL_FORBIDDEN",
            f"literal no permitido: {token.text!r}; solo strings, numeros y booleanos (regla 10)",
        )

    # -- GROUP BY / ORDER BY --

    def _parse_group_by_list(self) -> tuple[str, ...]:
        columns = [self._parse_column().name]
        while self._peek().kind == "OP" and self._peek().text == ",":
            self._advance()
            columns.append(self._parse_column().name)
        return tuple(columns)

    def _parse_order_by_list(self) -> tuple[OrderItem, ...]:
        items = [self._parse_order_item()]
        while self._peek().kind == "OP" and self._peek().text == ",":
            self._advance()
            items.append(self._parse_order_item())
        return tuple(items)

    def _parse_order_item(self) -> OrderItem:
        ref = self._expect("IDENT").text.lower()
        direction: PyLiteral["ASC", "DESC"] = "ASC"
        if self._peek().kind in {"ASC", "DESC"}:
            direction = self._advance().kind  # type: ignore[assignment]
        return OrderItem(ref=ref, direction=direction)

    # -- condiciones (WHERE/HAVING) --

    def _parse_condition(self) -> Condition:
        return self._parse_or()

    def _parse_or(self) -> Condition:
        operands = [self._parse_and()]
        while self._peek().kind == "OR":
            self._advance()
            operands.append(self._parse_and())
        if len(operands) == 1:
            return operands[0]
        return BoolOp(op="OR", operands=tuple(operands))

    def _parse_and(self) -> Condition:
        operands = [self._parse_not()]
        while self._peek().kind == "AND":
            self._advance()
            operands.append(self._parse_not())
        if len(operands) == 1:
            return operands[0]
        return BoolOp(op="AND", operands=tuple(operands))

    def _parse_not(self) -> Condition:
        if self._peek().kind == "NOT":
            self._advance()
            return Not(inner=self._parse_not())
        return self._parse_predicate()

    def _parse_predicate(self) -> Condition:
        if self._peek().kind == "OP" and self._peek().text == "(":
            self._advance()
            condition = self._parse_condition()
            closing = self._advance()
            if not (closing.kind == "OP" and closing.text == ")"):
                raise SoqlGuardError("SOQL_FORBIDDEN", "parentesis sin cerrar en condicion")
            return condition

        left = self._parse_condition_operand()

        if self._peek().kind == "IS":
            self._advance()
            negated = False
            if self._peek().kind == "NOT":
                self._advance()
                negated = True
            self._expect("NULL")
            return IsNullPredicate(operand=left, negated=negated)

        negated_like = False
        if self._peek().kind == "NOT":
            self._advance()
            negated_like = True
        if self._peek().kind == "LIKE":
            self._advance()
            right = self._parse_condition_operand()
            return LikePredicate(left=left, negated=negated_like, right=right)
        if negated_like:
            raise SoqlGuardError("SOQL_FORBIDDEN", "NOT solo es valido antes de LIKE o IS NULL")

        op_token = self._peek()
        if op_token.kind == "OP" and op_token.text in _COMPARISON_OPERATORS:
            self._advance()
            right = self._parse_condition_operand()
            return Comparison(left=left, op=op_token.text, right=right)

        raise SoqlGuardError(
            "SOQL_FORBIDDEN",
            f"operador de comparacion no reconocido tras {left!r} (token {op_token.text!r})",
        )

    def _parse_condition_operand(self) -> Operand:
        token = self._peek()
        if token.kind in {"STRING", "NUMBER", "TRUE", "FALSE"}:
            return self._parse_literal()
        if token.kind == "IDENT" and self._tokens[self._i + 1].kind == "OP" and (
            self._tokens[self._i + 1].text == "("
        ):
            func = self._parse_func_call()
            if func.name in AGG_FUNCTIONS:
                raise SoqlGuardError(
                    "SOQL_FORBIDDEN",
                    f"la funcion agregada {func.name!r} no es valida en WHERE/condiciones simples",
                )
            return func
        return self._parse_column()


def parse_soql(soql: str) -> ParsedQuery:
    tokens = tokenize(soql)
    return _Parser(tokens).parse()


# --- Validacion de complejidad y catalogo ------------------------------------


def _count_conditions(condition: Condition | None) -> int:
    if condition is None:
        return 0
    if isinstance(condition, BoolOp):
        return sum(_count_conditions(operand) for operand in condition.operands)
    if isinstance(condition, Not):
        return _count_conditions(condition.inner)
    return 1


def _iter_columns_in_operand(operand: Operand) -> list[str]:
    if isinstance(operand, Column):
        return [operand.name]
    if isinstance(operand, FuncCall):
        columns: list[str] = []
        for arg in operand.args:
            columns.extend(_iter_columns_in_operand(arg))
        return columns
    return []


def _iter_columns_in_condition(condition: Condition | None) -> list[str]:
    if condition is None:
        return []
    if isinstance(condition, BoolOp):
        columns: list[str] = []
        for operand in condition.operands:
            columns.extend(_iter_columns_in_condition(operand))
        return columns
    if isinstance(condition, Not):
        return _iter_columns_in_condition(condition.inner)
    if isinstance(condition, Comparison):
        return _iter_columns_in_operand(condition.left) + _iter_columns_in_operand(condition.right)
    if isinstance(condition, LikePredicate):
        return _iter_columns_in_operand(condition.left) + _iter_columns_in_operand(condition.right)
    if isinstance(condition, IsNullPredicate):
        return _iter_columns_in_operand(condition.operand)
    return []


def _referenced_columns(parsed: ParsedQuery) -> set[str]:
    columns: set[str] = set()
    for item in parsed.select_items:
        columns.update(_iter_columns_in_operand(item.expr))
    columns.update(_iter_columns_in_condition(parsed.where))
    columns.update(parsed.group_by)
    columns.update(_iter_columns_in_condition(parsed.having))
    return columns


@dataclass(frozen=True)
class ColumnInfo:
    field_name: str
    pii_risk_level: PyLiteral["low", "medium", "high", "unknown"]
    eligibility_status: PyLiteral["eligible", "diagnostic_only", "blocked"]


@dataclass(frozen=True)
class DatasetCatalogInfo:
    dataset_id: str
    api_active: bool
    eligibility_status: PyLiteral["eligible", "diagnostic_only", "blocked"]
    columns: tuple[ColumnInfo, ...]


@dataclass(frozen=True)
class CanonicalQuery:
    canonical_soql: str
    select_clause: str
    where_clause: str | None
    group_by_clause: str | None
    having_clause: str | None
    order_by_clause: str | None
    limit: int
    offset: int


def _render_operand(operand: Operand) -> str:
    if isinstance(operand, Column):
        return operand.name
    if isinstance(operand, Star):
        return "*"
    if isinstance(operand, Literal):
        if operand.kind == "string":
            escaped = str(operand.value).replace("'", "''")
            return f"'{escaped}'"
        if operand.kind == "boolean":
            return "true" if operand.value else "false"
        return str(operand.value)
    if isinstance(operand, FuncCall):
        args = ", ".join(_render_operand(arg) for arg in operand.args)
        return f"{operand.name}({args})"
    raise TypeError(f"operando no reconocido: {operand!r}")


def _render_condition(condition: Condition, *, nested: bool = False) -> str:
    if isinstance(condition, BoolOp):
        joined = f" {condition.op} ".join(
            _render_condition(op, nested=True) for op in condition.operands
        )
        return f"({joined})" if nested and len(condition.operands) > 1 else joined
    if isinstance(condition, Not):
        return f"NOT {_render_condition(condition.inner, nested=True)}"
    if isinstance(condition, Comparison):
        left, right = _render_operand(condition.left), _render_operand(condition.right)
        return f"{left} {condition.op} {right}"
    if isinstance(condition, LikePredicate):
        keyword = "NOT LIKE" if condition.negated else "LIKE"
        return f"{_render_operand(condition.left)} {keyword} {_render_operand(condition.right)}"
    if isinstance(condition, IsNullPredicate):
        keyword = "IS NOT NULL" if condition.negated else "IS NULL"
        return f"{_render_operand(condition.operand)} {keyword}"
    raise TypeError(f"condicion no reconocida: {condition!r}")


def _validate_medium_pii_policy(
    parsed: ParsedQuery, columns_by_name: dict[str, ColumnInfo], dataset_pii_medium: bool
) -> None:
    referenced = _referenced_columns(parsed)
    is_medium = dataset_pii_medium or any(
        columns_by_name[name].pii_risk_level == "medium"
        for name in referenced
        if name in columns_by_name
    )
    if not is_medium:
        return

    group_by_names = set(parsed.group_by)
    has_count_agg = False
    for item in parsed.select_items:
        expr = item.expr
        if isinstance(expr, Column):
            if expr.name in group_by_names:
                continue
            raise SoqlGuardError(
                "PII_AGGREGATION_REQUIRED",
                "el dataset/columna tiene pii_risk_level=medium: el SELECT solo puede "
                f"tener agregados y dimensiones de GROUP BY, no la columna {expr.name!r} suelta",
            )
        if isinstance(expr, FuncCall):
            if expr.name not in AGG_FUNCTIONS:
                raise SoqlGuardError(
                    "PII_AGGREGATION_REQUIRED",
                    "con pii_risk_level=medium solo se permiten agregados en SELECT, "
                    f"no {expr.name!r}",
                )
            if expr.name == "count":
                has_count_agg = True
        else:
            raise SoqlGuardError(
                "PII_AGGREGATION_REQUIRED",
                "con pii_risk_level=medium el SELECT solo admite agregados o columnas de GROUP BY",
            )
    if not has_count_agg:
        raise SoqlGuardError(
            "PII_AGGREGATION_REQUIRED",
            "con pii_risk_level=medium el SELECT debe incluir count(*) o count(columna)",
        )


def validate_and_canonicalize(soql: str, dataset: DatasetCatalogInfo) -> CanonicalQuery:
    """Valida `soql` contra la gramatica restringida y el catalogo de `dataset`.

    Lanza `SoqlGuardError` con el codigo del contrato (agent-tools.md §T5) en
    el primer incumplimiento; no ejecuta nada contra Socrata.
    """
    if _BLACKLIST_PATTERN.search(soql):
        raise SoqlGuardError(
            "SOQL_FORBIDDEN",
            "la consulta contiene una palabra clave o separador prohibido "
            "(defensa en profundidad, regla 13)",
        )

    if not dataset.api_active:
        raise SoqlGuardError(
            "DATASET_INACTIVE", f"el dataset {dataset.dataset_id!r} no tiene api_active=true"
        )
    if dataset.eligibility_status != "eligible":
        raise SoqlGuardError(
            "EVIDENCE_NOT_ELIGIBLE",
            f"el dataset {dataset.dataset_id!r} tiene eligibility_status="
            f"{dataset.eligibility_status!r}, no se ejecuta contra Socrata",
        )

    parsed = parse_soql(soql)

    if len(parsed.group_by) > MAX_GROUP_BY_COLUMNS:
        raise SoqlGuardError(
            "SOQL_FORBIDDEN",
            f"GROUP BY tiene {len(parsed.group_by)} columnas, el maximo es "
            f"{MAX_GROUP_BY_COLUMNS} (regla 11)",
        )
    where_conditions = _count_conditions(parsed.where)
    if where_conditions > MAX_WHERE_CONDITIONS:
        raise SoqlGuardError(
            "SOQL_FORBIDDEN",
            f"WHERE tiene {where_conditions} condiciones, el maximo es "
            f"{MAX_WHERE_CONDITIONS} (regla 11)",
        )
    if parsed.offset > MAX_OFFSET:
        raise SoqlGuardError(
            "SOQL_FORBIDDEN", f"OFFSET {parsed.offset} excede el maximo de {MAX_OFFSET} (regla 9)"
        )

    columns_by_name = {column.field_name: column for column in dataset.columns}
    referenced = _referenced_columns(parsed)
    unknown = sorted(referenced - columns_by_name.keys())
    if unknown:
        raise SoqlGuardError(
            "SOQL_UNKNOWN_COLUMN",
            f"columnas inexistentes en el dataset: {unknown}",
            valid_columns=sorted(columns_by_name.keys()),
        )
    for name in referenced:
        column = columns_by_name[name]
        if column.eligibility_status != "eligible" and column.pii_risk_level != "medium":
            raise SoqlGuardError(
                "EVIDENCE_NOT_ELIGIBLE",
                f"la columna {name!r} tiene eligibility_status={column.eligibility_status!r}",
            )
        if column.pii_risk_level in {"unknown", "high"}:
            raise SoqlGuardError(
                "EVIDENCE_NOT_ELIGIBLE",
                f"la columna {name!r} tiene pii_risk_level={column.pii_risk_level!r}",
            )

    _validate_medium_pii_policy(parsed, columns_by_name, dataset_pii_medium=False)

    declared_aliases = {item.alias for item in parsed.select_items if item.alias}
    select_plain_columns = {
        item.expr.name for item in parsed.select_items if isinstance(item.expr, Column)
    }
    for order_item in parsed.order_by:
        if order_item.ref in declared_aliases:
            continue
        if order_item.ref in select_plain_columns:
            continue
        raise SoqlGuardError(
            "SOQL_FORBIDDEN",
            f"ORDER BY {order_item.ref!r} no es un alias declarado ni una columna "
            "presente en el SELECT (regla 10)",
        )

    limit = min(parsed.limit, MAX_LIMIT) if parsed.limit_was_explicit else DEFAULT_LIMIT

    def _render_select_item(item: SelectItem) -> str:
        rendered = _render_operand(item.expr)
        return f"{rendered} AS {item.alias}" if item.alias else rendered

    select_clause = ", ".join(_render_select_item(item) for item in parsed.select_items)
    where_clause = _render_condition(parsed.where) if parsed.where else None
    group_by_clause = ", ".join(parsed.group_by) if parsed.group_by else None
    having_clause = _render_condition(parsed.having) if parsed.having else None
    order_by_clause = (
        ", ".join(f"{item.ref} {item.direction}" for item in parsed.order_by)
        if parsed.order_by
        else None
    )

    parts = [f"SELECT {select_clause}"]
    if where_clause:
        parts.append(f"WHERE {where_clause}")
    if group_by_clause:
        parts.append(f"GROUP BY {group_by_clause}")
    if having_clause:
        parts.append(f"HAVING {having_clause}")
    if order_by_clause:
        parts.append(f"ORDER BY {order_by_clause}")
    parts.append(f"LIMIT {limit}")
    parts.append(f"OFFSET {parsed.offset}")
    canonical_soql = " ".join(parts)

    return CanonicalQuery(
        canonical_soql=canonical_soql,
        select_clause=select_clause,
        where_clause=where_clause,
        group_by_clause=group_by_clause,
        having_clause=having_clause,
        order_by_clause=order_by_clause,
        limit=limit,
        offset=parsed.offset,
    )
