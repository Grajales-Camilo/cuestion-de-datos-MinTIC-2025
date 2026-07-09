import pytest

from app.db.publishers_admin import AddPublishersError, merge_publishers


def _base_fixture() -> dict:
    return {
        "fixture_version": "2026-01-01",
        "updated_at": "2026-01-01T00:00:00Z",
        "publishers": [
            {
                "id": "dane",
                "canonical_name": "Departamento Administrativo Nacional de Estadística",
                "entity_type": "departamento_administrativo",
                "active": True,
                "verification_source": "https://www.dane.gov.co/",
                "aliases": [
                    {
                        "alias_raw": "DANE",
                        "ambiguous": False,
                        "verification_source": "https://www.dane.gov.co/",
                    }
                ],
            }
        ],
        "known_private_publishers": [],
    }


def _row(**overrides) -> dict:
    row = {
        "id": "gobernacion-narino",
        "canonical_name": "Gobernación de Nariño",
        "entity_type": "gobernacion",
        "verification_source": "https://www.narino.gov.co/",
        "aliases": "",
        "ambiguous_aliases": "",
        "active": "true",
    }
    row.update(overrides)
    return row


def test_new_publisher_is_appended_with_aliases() -> None:
    data = _base_fixture()

    summary = merge_publishers(
        data, [_row(aliases="Gob Nariño|Gobernacion Narino")], update_existing=False
    )

    assert summary.publishers_added == 1
    assert summary.aliases_added == 2
    assert len(data["publishers"]) == 2
    new_entry = data["publishers"][1]
    assert new_entry["id"] == "gobernacion-narino"
    assert [a["alias_raw"] for a in new_entry["aliases"]] == ["Gob Nariño", "Gobernacion Narino"]
    assert all(a["ambiguous"] is False for a in new_entry["aliases"])


def test_ambiguous_aliases_are_flagged_and_skip_collision_check() -> None:
    data = _base_fixture()

    summary = merge_publishers(
        data, [_row(ambiguous_aliases="DANE")], update_existing=False
    )

    assert summary.publishers_added == 1
    new_entry = data["publishers"][1]
    assert new_entry["aliases"][0] == {
        "alias_raw": "DANE",
        "ambiguous": True,
        "verification_source": "https://www.narino.gov.co/",
    }


def test_existing_id_merges_new_alias_without_duplicating() -> None:
    data = _base_fixture()

    summary = merge_publishers(
        data,
        [
            _row(
                id="dane",
                canonical_name="Departamento Administrativo Nacional de Estadística",
                entity_type="departamento_administrativo",
                verification_source="https://www.dane.gov.co/",
                aliases="DANE|Estadisticas DANE",
            )
        ],
        update_existing=False,
    )

    assert summary.publishers_added == 0
    assert summary.publishers_updated == 0
    assert summary.aliases_added == 1  # "DANE" ya existia, solo se agrega el nuevo
    dane = data["publishers"][0]
    assert [a["alias_raw"] for a in dane["aliases"]] == ["DANE", "Estadisticas DANE"]
    assert any("ya existia" in w for w in summary.warnings)


def test_existing_id_with_changed_field_is_rejected_without_update_flag() -> None:
    data = _base_fixture()

    with pytest.raises(AddPublishersError, match="usa --update-existing"):
        merge_publishers(
            data,
            [_row(id="dane", canonical_name="Nombre Distinto")],
            update_existing=False,
        )


def test_existing_id_with_changed_field_is_applied_with_update_flag() -> None:
    data = _base_fixture()

    summary = merge_publishers(
        data,
        [
            _row(
                id="dane",
                canonical_name="Nombre Corregido",
                entity_type="departamento_administrativo",
                verification_source="https://www.dane.gov.co/",
            )
        ],
        update_existing=True,
    )

    assert summary.publishers_updated == 1
    assert data["publishers"][0]["canonical_name"] == "Nombre Corregido"


def test_unambiguous_alias_colliding_with_another_entity_is_rejected() -> None:
    data = _base_fixture()

    with pytest.raises(AddPublishersError, match="ya pertenece a 'dane'"):
        merge_publishers(data, [_row(aliases="DANE")], update_existing=False)


def test_canonical_name_colliding_with_existing_alias_is_rejected() -> None:
    data = _base_fixture()

    with pytest.raises(AddPublishersError, match="canonical_name normaliza igual"):
        merge_publishers(data, [_row(canonical_name="DANE")], update_existing=False)


def test_duplicate_id_within_same_batch_is_rejected() -> None:
    data = _base_fixture()

    with pytest.raises(AddPublishersError, match="id duplicado dentro del CSV"):
        merge_publishers(data, [_row(), _row()], update_existing=False)


def test_invalid_entity_type_is_rejected() -> None:
    data = _base_fixture()

    with pytest.raises(AddPublishersError, match="entity_type"):
        merge_publishers(data, [_row(entity_type="empresa_privada")], update_existing=False)


def test_missing_required_field_is_rejected() -> None:
    data = _base_fixture()

    with pytest.raises(AddPublishersError, match="no pueden estar vacios"):
        merge_publishers(data, [_row(canonical_name="")], update_existing=False)


def test_invalid_active_value_is_rejected() -> None:
    data = _base_fixture()

    with pytest.raises(AddPublishersError, match="active debe ser"):
        merge_publishers(data, [_row(active="quizas")], update_existing=False)
