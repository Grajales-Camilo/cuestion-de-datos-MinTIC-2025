"""T8 `comparabilidad_territorial`: nodo determinista de advertencia de
comparabilidad territorial (contracts/agent-tools.md §T8, RF-202,
data-model.md §6, research.md §18). No usa LLM y no es invocable por el
enrutador -- el grafo lo ejecuta automaticamente cuando T3
(`resolver_geografia`) resuelve >= 2 territorios distintos en la misma
corrida.

**Regla de uso (Art. I):** la salida NUNCA incluye `poblacion` ni
`ingresos_totales_cop` de `territorio_tipologia` -- esos campos son solo
senal interna (no llegan por SoQL, ver data-model.md §6) y no pueden
citarse como cifra. Solo `level`/`tipologia_dnp`/`categoria_ley_617`
(clasificaciones, no cifras) llegan al sintetizador.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.db.models import TerritorioTipologia

# Orden de la escala municipal (Tabla 3-1 del informe DNP, Resolucion 3910
# de 2025): "brecha de tipologia" se mide como distancia de indices.
MUNICIPAL_TIPOLOGIA_SCALE = ("Bogotá", "Ciudades grandes", "1", "2", "3", "4", "5")
_TOP_TIER = {"Bogotá", "Ciudades grandes"}
TIPOLOGIA_GAP_THRESHOLD = 3


@dataclass(frozen=True)
class TerritorioComparabilidad:
    divipola_code: str
    level: str | None
    tipologia_dnp: str | None
    categoria_ley_617: str | None


@dataclass(frozen=True)
class ComparabilidadResult:
    comparable: bool | None
    reasons: tuple[str, ...]
    territorios: tuple[TerritorioComparabilidad, ...]


def _tipologia_gap(a: str, b: str) -> bool:
    if a == b:
        return False
    if a in _TOP_TIER or b in _TOP_TIER:
        return True
    try:
        return (
            abs(MUNICIPAL_TIPOLOGIA_SCALE.index(a) - MUNICIPAL_TIPOLOGIA_SCALE.index(b))
            >= TIPOLOGIA_GAP_THRESHOLD
        )
    except ValueError:
        # tipologia fuera de la escala conocida (dato inesperado): no se
        # afirma una brecha que no se puede sustentar (Art. I).
        return False


def evaluate_comparability(
    territorios: tuple[TerritorioComparabilidad, ...],
) -> ComparabilidadResult:
    """Funcion pura (contracts/agent-tools.md §T8): decide si un conjunto de
    territorios ya resueltos son comparables entre si."""

    if any(t.tipologia_dnp is None for t in territorios):
        return ComparabilidadResult(
            comparable=None, reasons=("sin_tipologia",), territorios=territorios
        )

    reasons: list[str] = []
    if len({t.level for t in territorios}) > 1:
        reasons.append("level_mismatch")

    municipios = [t for t in territorios if t.level == "municipality"]
    if any(
        _tipologia_gap(municipios[i].tipologia_dnp, municipios[j].tipologia_dnp)
        for i in range(len(municipios))
        for j in range(i + 1, len(municipios))
    ):
        reasons.append("tipologia_gap")

    return ComparabilidadResult(
        comparable=not reasons,
        reasons=tuple(reasons),
        territorios=territorios,
    )


async def comparabilidad_territorial(divipola_codes: list[str], *, engine: AsyncEngine) -> dict:
    """T8: consulta `territorio_tipologia` para los codigos resueltos por T3
    y devuelve la salida documentada en contracts/agent-tools.md §T8."""

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(
                    TerritorioTipologia.divipola_code,
                    TerritorioTipologia.level,
                    TerritorioTipologia.tipologia_dnp,
                    TerritorioTipologia.categoria_ley_617,
                ).where(TerritorioTipologia.divipola_code.in_(divipola_codes))
            )
        ).all()
    by_code = {row.divipola_code: row for row in rows}

    territorios = tuple(
        TerritorioComparabilidad(
            divipola_code=code,
            level=by_code[code].level if code in by_code else None,
            tipologia_dnp=by_code[code].tipologia_dnp if code in by_code else None,
            categoria_ley_617=by_code[code].categoria_ley_617 if code in by_code else None,
        )
        for code in divipola_codes
    )
    result = evaluate_comparability(territorios)
    return {
        "ok": True,
        "comparable": result.comparable,
        "reasons": list(result.reasons),
        "territorios": [
            {
                "divipola_code": t.divipola_code,
                "level": t.level,
                "tipologia_dnp": t.tipologia_dnp,
                "categoria_ley_617": t.categoria_ley_617,
            }
            for t in result.territorios
        ],
    }
