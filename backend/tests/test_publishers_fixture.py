from app.db.publishers import load_fixture

VALID_ENTITY_TYPES = {
    "ministerio",
    "departamento_administrativo",
    "gobernacion",
    "alcaldia",
    "universidad_publica",
    "empresa_estado",
    "establecimiento_publico",
    "otra_estatal",
}


def test_fixture_loads_and_ids_are_unique() -> None:
    fixture = load_fixture()

    ids = [publisher.id for publisher in fixture.publishers]
    assert len(ids) == len(set(ids))
    assert len(fixture.publishers) > 0


def test_fixture_entity_types_are_valid() -> None:
    fixture = load_fixture()

    for publisher in fixture.publishers:
        assert publisher.entity_type in VALID_ENTITY_TYPES


def test_fixture_every_publisher_has_verification_source() -> None:
    fixture = load_fixture()

    for publisher in fixture.publishers:
        assert publisher.verification_source
        for alias in publisher.aliases:
            assert alias.verification_source


def test_fixture_known_private_publishers_have_verification_source() -> None:
    fixture = load_fixture()

    for entry in fixture.known_private_publishers:
        assert entry.verification_source
