from app.db.publishers import normalize_publisher_name


def test_normalize_strips_accents_and_uppercases() -> None:
    assert normalize_publisher_name("Ministerio de Educación") == "MINISTERIO DE EDUCACION"


def test_normalize_collapses_whitespace() -> None:
    assert normalize_publisher_name("  DANE   Colombia  ") == "DANE COLOMBIA"


def test_normalize_is_idempotent() -> None:
    once = normalize_publisher_name("Gobernación de Antioquia")
    twice = normalize_publisher_name(once)
    assert once == twice == "GOBERNACION DE ANTIOQUIA"


def test_normalize_case_insensitive_matches() -> None:
    assert normalize_publisher_name("sena") == normalize_publisher_name("SENA")
