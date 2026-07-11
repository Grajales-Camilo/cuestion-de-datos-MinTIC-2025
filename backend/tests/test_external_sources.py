import re

import pytest

from app.quality.external_sources import (
    MAX_SUGGESTIONS,
    ExternalSource,
    load_external_sources,
    suggest_external_sources,
)

_FAKE_CATALOG = (
    ExternalSource(
        entidad="DANE",
        url="https://www.dane.gov.co",
        temas=("poblacion", "censo"),
        por_que="Autoridad estadística nacional.",
    ),
    ExternalSource(
        entidad="DNP - TerriData",
        url="https://terridata.dnp.gov.co",
        temas=("tipologia", "capacidad territorial"),
        por_que="Indicadores territoriales oficiales.",
    ),
    ExternalSource(
        entidad="IGAC",
        url="https://www.igac.gov.co",
        temas=("catastro",),
        por_que="Autoridad catastral.",
    ),
)


def test_matches_by_keyword_case_and_accent_insensitive() -> None:
    matches = suggest_external_sources("¿Cuál es la POBLACIÓN de Sonsón?", catalog=_FAKE_CATALOG)

    assert matches == [
        {
            "entidad": "DANE",
            "url": "https://www.dane.gov.co",
            "por_que": "Autoridad estadística nacional.",
        }
    ]


def test_matches_multi_word_tema() -> None:
    matches = suggest_external_sources(
        "¿Qué capacidad territorial tiene mi municipio?", catalog=_FAKE_CATALOG
    )

    assert matches[0]["entidad"] == "DNP - TerriData"


def test_no_match_returns_empty_list() -> None:
    matches = suggest_external_sources("¿Cuántos gatos hay en el municipio?", catalog=_FAKE_CATALOG)

    assert matches == []


def test_never_returns_more_than_max_suggestions() -> None:
    wide_catalog = tuple(
        ExternalSource(
            entidad=f"Entidad {i}", url=f"https://e{i}.gov.co", temas=("dato",), por_que="x"
        )
        for i in range(10)
    )

    matches = suggest_external_sources("dato dato dato", catalog=wide_catalog)

    assert len(matches) <= MAX_SUGGESTIONS


def test_result_never_contains_a_url_absent_from_the_catalog() -> None:
    """Regla no negociable (contracts/api-rest.md §4): la url SIEMPRE sale
    del catalogo, nunca se sintetiza a partir del texto de la pregunta."""

    matches = suggest_external_sources("catastro y limites territoriales", catalog=_FAKE_CATALOG)

    known_urls = {source.url for source in _FAKE_CATALOG}
    assert all(match["url"] in known_urls for match in matches)


# --- Integridad del fixture real (mismo espiritu que test_pii_patterns_fixture.py) ---


def test_real_fixture_loads() -> None:
    sources = load_external_sources()
    assert len(sources) > 0


def test_every_source_has_https_url_and_at_least_one_tema() -> None:
    for source in load_external_sources():
        assert re.match(r"^https://", source.url), source.entidad
        assert len(source.temas) > 0, source.entidad
        assert source.por_que.strip(), source.entidad


def test_entidad_names_are_unique() -> None:
    sources = load_external_sources()
    names = [source.entidad for source in sources]
    assert len(names) == len(set(names))


def test_real_catalog_matches_dnp_territorial_question() -> None:
    matches = suggest_external_sources("¿Cuál es la tipología de capacidad territorial?")

    assert any(match["entidad"] == "DNP - TerriData" for match in matches)


@pytest.mark.parametrize(
    "question",
    ["", "consulta genérica sin ningún tema oficial conocido de por medio"],
)
def test_real_catalog_no_false_positive_on_unrelated_question(question: str) -> None:
    assert suggest_external_sources(question) == []
