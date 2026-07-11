"""T-404: nodo T8 `comparabilidad_territorial` integrado al grafo real, y
recomendacion determinista de `external_sources` en `no_evidence_report`
(contracts/agent-tools.md §T8, contracts/api-rest.md §4).
"""

from __future__ import annotations

import uuid

import pytest

from app.agent.graph import (
    GraphDependencies,
    NoEvidenceReport,
    PlannerOutput,
    RouterOutput,
    SynthesisOutput,
    build_graph,
    initial_state,
)


class StaticModel:
    def __init__(self, value):
        self.value = value

    async def ainvoke(self, _input, **_kwargs):
        return self.value


class TwoTerritoriesRouter:
    """resolver_geografia(Bogotá) -> resolver_geografia(El Carmen de
    Viboral) -> finish, sin `ejecutar_soql` (fuerza el camino no_evidence)."""

    def __init__(self):
        self.calls = 0

    async def ainvoke(self, _messages, **_kwargs):
        self.calls += 1
        if self.calls == 1:
            return RouterOutput(
                action="resolver_geografia",
                reasoning_summary="Resuelvo el primer territorio",
                tool_input={"termino": "Bogotá"},
            )
        if self.calls == 2:
            return RouterOutput(
                action="resolver_geografia",
                reasoning_summary="Resuelvo el segundo territorio",
                tool_input={"termino": "El Carmen de Viboral"},
            )
        return RouterOutput(
            action="finish", reasoning_summary="No hay evidencia numérica", tool_input={}
        )


class OneTerritoryRouter:
    def __init__(self):
        self.calls = 0

    async def ainvoke(self, _messages, **_kwargs):
        self.calls += 1
        if self.calls == 1:
            return RouterOutput(
                action="resolver_geografia",
                reasoning_summary="Resuelvo el territorio",
                tool_input={"termino": "Bogotá"},
            )
        return RouterOutput(
            action="finish", reasoning_summary="No hay evidencia numérica", tool_input={}
        )


class NoEvidenceSynthesizer:
    async def ainvoke(self, _messages, **_kwargs):
        return SynthesisOutput(
            summary="No encontré evidencia suficiente en el catálogo.",
            no_evidence_report=NoEvidenceReport(
                reason="No hay datasets con el nivel territorial solicitado.",
            ),
        )


async def resolver_geografia_fake(raw_input: dict) -> dict:
    termino = raw_input.get("termino", "")
    if "carmen" in termino.lower():
        return {
            "ok": True,
            "matches": [
                {
                    "code": "05148",
                    "name": "EL CARMEN DE VIBORAL",
                    "department_code": "05",
                    "department_name": "ANTIOQUIA",
                    "level": "municipality",
                    "like_pattern": "%CARMEN DE VIBORAL%",
                    "confidence": 0.93,
                }
            ],
        }
    return {
        "ok": True,
        "matches": [
            {
                "code": "11001",
                "name": "BOGOTÁ, D.C.",
                "department_code": "11",
                "department_name": "BOGOTÁ, D.C.",
                "level": "municipality",
                "like_pattern": "%BOGOTA%",
                "confidence": 0.95,
            }
        ],
    }


async def _unused(_raw_input):
    return {"ok": False, "error": {"code": "UNUSED", "message": "unused"}}


def _tools():
    return {
        "buscar_catalogo": _unused,
        "perfilar_dataset": _unused,
        "resolver_geografia": resolver_geografia_fake,
        "explorar_valores": _unused,
        "ejecutar_soql": _unused,
    }


def _deps(router, synthesizer, *, territorial_loader=None):
    return GraphDependencies(
        engine=None,
        planner_model=StaticModel(
            PlannerOutput(
                intention="Comparar territorios",
                subqueries=["Resolver el primer territorio", "Resolver el segundo territorio"],
                recommended_next_action="Resolver geografía",
            )
        ),
        router_model=router,
        synthesizer_model=synthesizer,
        tools=_tools(),
        llm_provider="google",
        llm_model="gemini-2.5-flash",
        max_steps=10,
        persist=False,
        territorial_loader=territorial_loader,
    )


@pytest.mark.asyncio
async def test_t8_triggers_when_two_distinct_territories_resolved():
    calls: list[list[str]] = []

    async def territorial_loader(codes: list[str]) -> dict:
        calls.append(codes)
        return {
            "ok": True,
            "comparable": False,
            "reasons": ["tipologia_gap"],
            "territorios": [
                {
                    "divipola_code": "11001",
                    "level": "municipality",
                    "tipologia_dnp": "Bogotá",
                    "categoria_ley_617": "ESP",
                },
                {
                    "divipola_code": "05148",
                    "level": "municipality",
                    "tipologia_dnp": "5",
                    "categoria_ley_617": "6",
                },
            ],
        }

    deps = _deps(
        TwoTerritoriesRouter(), NoEvidenceSynthesizer(), territorial_loader=territorial_loader
    )
    graph = build_graph(deps, interrupt=False)
    result = await graph.ainvoke(
        initial_state(uuid.uuid4(), "Compara Bogotá con El Carmen de Viboral", max_steps=10)
    )

    assert calls == [["11001", "05148"]]
    assert result["territorial_comparability"]["comparable"] is False
    assert result["territorial_comparability"]["reasons"] == ["tipologia_gap"]
    assert result["territorial_checked_codes"] == ["11001", "05148"]


@pytest.mark.asyncio
async def test_t8_does_not_trigger_with_a_single_territory():
    calls: list[list[str]] = []

    async def territorial_loader(codes: list[str]) -> dict:
        calls.append(codes)
        return {"ok": True, "comparable": True, "reasons": [], "territorios": []}

    graph = build_graph(
        _deps(OneTerritoryRouter(), NoEvidenceSynthesizer(), territorial_loader=territorial_loader),
        interrupt=False,
    )
    result = await graph.ainvoke(
        initial_state(uuid.uuid4(), "¿Qué código DIVIPOLA tiene Bogotá?", max_steps=10)
    )

    assert calls == []
    assert result.get("territorial_comparability") is None


@pytest.mark.asyncio
async def test_no_evidence_report_gets_deterministic_external_sources():
    graph = build_graph(_deps(OneTerritoryRouter(), NoEvidenceSynthesizer()), interrupt=False)
    result = await graph.ainvoke(
        initial_state(
            uuid.uuid4(),
            "¿Cuál es la tipología de capacidad territorial de mi municipio?",
            max_steps=10,
        )
    )

    external_sources = result["final_answer"]["no_evidence_report"]["external_sources"]
    assert external_sources
    assert external_sources[0]["entidad"] == "DNP - TerriData"
    assert external_sources[0]["url"] == "https://terridata.dnp.gov.co"


@pytest.mark.asyncio
async def test_no_evidence_report_has_no_external_sources_when_no_keyword_matches():
    graph = build_graph(_deps(OneTerritoryRouter(), NoEvidenceSynthesizer()), interrupt=False)
    result = await graph.ainvoke(
        initial_state(
            uuid.uuid4(), "¿Cuántos gatos hay registrados en el municipio?", max_steps=10
        )
    )

    assert result["final_answer"]["no_evidence_report"]["external_sources"] == []
