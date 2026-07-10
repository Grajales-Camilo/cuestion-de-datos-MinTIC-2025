"""T3 `resolver_geografia` (contracts/agent-tools.md §T3, pruebas.md §2.1).

`rank_matches`/`build_like_pattern` son funciones puras (sin DB); la consulta
SQL real (`similarity`/`pg_trgm`, `alt_names`) se ejerce en
`tests/integration/test_resolver_geografia.py` contra Postgres real.
"""

from collections import namedtuple

from app.db.divipola import normalize_name
from app.tools.resolver_geografia import build_like_pattern, rank_matches

TrigramRow = namedtuple(
    "TrigramRow", "code name department_code department_name level score"
)
AltRow = namedtuple("AltRow", "code name department_code department_name level alt_names")


def _no_alt_matches() -> list:
    return []


def _no_trigram_matches() -> list:
    return []


def test_accented_and_case_variants_resolve_to_same_code_via_alt_names() -> None:
    bogota_row = AltRow(
        code="11001",
        name="BOGOTÁ, D.C.",
        department_code="11",
        department_name="BOGOTÁ, D.C.",
        level="municipality",
        alt_names=["Bogotá", "Bogotá D.C.", "Santafé de Bogotá"],
    )

    for termino in ["Bogotá", "bogota", "Bogotá D.C.", "BOGOTA"]:
        matches = rank_matches(_no_trigram_matches(), [bogota_row], normalize_name(termino))
        assert any(match["code"] == "11001" for match in matches), termino


def test_carmen_de_viboral_resolves_via_trigram_similarity() -> None:
    from app.db.divipola import normalize_name

    carmen_row = TrigramRow(
        code="05148",
        name="EL CARMEN DE VIBORAL",
        department_code="05",
        department_name="ANTIOQUIA",
        level="municipality",
        score=0.86,
    )

    matches = rank_matches(
        [carmen_row], _no_alt_matches(), normalize_name("Carmen de Viboral")
    )

    assert matches[0]["code"] == "05148"
    assert matches[0]["department_name"] == "ANTIOQUIA"


def test_ambiguous_term_returns_multiple_ordered_matches() -> None:
    from app.db.divipola import normalize_name

    valle = TrigramRow(
        code="76001", name="LA UNION", department_code="76",
        department_name="VALLE DEL CAUCA", level="municipality", score=1.0,
    )
    cauca = TrigramRow(
        code="19001", name="LA UNION", department_code="19",
        department_name="CAUCA", level="municipality", score=1.0,
    )
    narino = TrigramRow(
        code="52001", name="LA UNION", department_code="52",
        department_name="NARIÑO", level="municipality", score=0.9,
    )

    matches = rank_matches(
        [valle, cauca, narino], _no_alt_matches(), normalize_name("La Unión")
    )

    codes = [m["code"] for m in matches]
    assert {"76001", "19001"}.issubset(set(codes))
    assert matches == sorted(matches, key=lambda m: -m["confidence"])


def test_at_most_three_matches_returned() -> None:
    from app.db.divipola import normalize_name

    rows = [
        TrigramRow(
            code=str(i), name="LA UNION", department_code=str(i),
            department_name=f"DEPTO {i}", level="municipality", score=1.0,
        )
        for i in range(5)
    ]

    matches = rank_matches(rows, _no_alt_matches(), normalize_name("La Union"))

    assert len(matches) == 3


def test_alt_name_confidence_wins_over_lower_trigram_score() -> None:
    from app.db.divipola import normalize_name

    trigram_row = TrigramRow(
        code="11001", name="BOGOTÁ, D.C.", department_code="11",
        department_name="BOGOTÁ, D.C.", level="municipality", score=0.4,
    )
    alt_row = AltRow(
        code="11001", name="BOGOTÁ, D.C.", department_code="11",
        department_name="BOGOTÁ, D.C.", level="municipality",
        alt_names=["Santafé de Bogotá"],
    )

    matches = rank_matches(
        [trigram_row], [alt_row], normalize_name("Santafé de Bogotá")
    )

    assert matches[0]["confidence"] == 0.95


# --- like_pattern (vocales acentuables -> `_`) -------------------------------


def test_build_like_pattern_replaces_accentable_vowels_with_underscore() -> None:
    assert build_like_pattern("EL CARMEN DE VIBORAL") == "%_L C_RM_N D_ V_B_R_L%"


def test_build_like_pattern_handles_accented_vowels() -> None:
    assert build_like_pattern("Bogotá") == "%B_G_T_%"


def test_build_like_pattern_wraps_with_percent_wildcards() -> None:
    pattern = build_like_pattern("MEDELLIN")
    assert pattern.startswith("%")
    assert pattern.endswith("%")
