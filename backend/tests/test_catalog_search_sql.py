"""T-614R2: la rama lexical debe consultar el tsvector materializado."""

from __future__ import annotations

import inspect

from app.catalog.search import search_catalog


def test_lexical_candidates_use_materialized_search_vector() -> None:
    source = inspect.getsource(search_catalog)
    lexical_cte = source.split("lexical_candidates AS (", maxsplit=1)[1].split(
        "candidate_ids AS (", maxsplit=1
    )[0]

    assert "d.lexical_search_vector @@ to_tsquery" in lexical_cte
    assert "to_tsvector(" not in lexical_cte
