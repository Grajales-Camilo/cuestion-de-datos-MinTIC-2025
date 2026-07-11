"""Recomendacion determinista de fuentes externas cuando el catalogo
Socrata no tiene el dato (T-404, contracts/api-rest.md §4, research.md
§18).

Sin LLM: la entidad, la URL y el texto explicativo vienen integros de
`external_sources.yaml`. El agente NUNCA elige ni genera una URL -- mismo
principio del Art. I aplicado a enlaces, para no arriesgar una fuente
alucinada en una respuesta "sin evidencia".
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

_CATALOG_PATH = Path(__file__).with_name("external_sources.yaml")
MAX_SUGGESTIONS = 3


@dataclass(frozen=True)
class ExternalSource:
    entidad: str
    url: str
    temas: tuple[str, ...]
    por_que: str


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    collapsed = re.sub(r"\s+", " ", without_accents)
    return collapsed.strip().lower()


@lru_cache(maxsize=1)
def load_external_sources() -> tuple[ExternalSource, ...]:
    raw = yaml.safe_load(_CATALOG_PATH.read_text(encoding="utf-8")) or {}
    return tuple(
        ExternalSource(
            entidad=item["entidad"],
            url=item["url"],
            temas=tuple(item["temas"]),
            por_que=item["por_que"].strip(),
        )
        for item in raw.get("sources", [])
    )


def suggest_external_sources(
    question: str, *, catalog: tuple[ExternalSource, ...] | None = None
) -> list[dict[str, str]]:
    """Coincidencia determinista de palabras clave: cada `tema` del catalogo
    se busca como subcadena del texto normalizado de la pregunta (sin
    tildes, minusculas). Devuelve hasta `MAX_SUGGESTIONS` entidades, en el
    orden del catalogo."""

    sources = catalog if catalog is not None else load_external_sources()
    normalized_question = _normalize(question)

    matches: list[dict[str, str]] = []
    for source in sources:
        if any(_normalize(tema) in normalized_question for tema in source.temas):
            matches.append(
                {"entidad": source.entidad, "url": source.url, "por_que": source.por_que}
            )
        if len(matches) >= MAX_SUGGESTIONS:
            break
    return matches
