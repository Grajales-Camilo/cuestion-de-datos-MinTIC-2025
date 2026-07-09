import pytest

from app.db.divipola import (
    DivipolaRowError,
    derive_department_entries,
    municipality_entry_from_row,
    normalize_name,
    rows_to_entries,
)

_CARMEN_VIBORAL_ROW = {
    "cod_dpto": "05",
    "dpto": "ANTIOQUIA",
    "cod_mpio": "05148",
    "nom_mpio": "EL CARMEN DE VIBORAL",
    "tipo_municipio": "Municipio",
}

_BOGOTA_ROW = {
    "cod_dpto": "11",
    "dpto": "BOGOTÁ, D.C.",
    "cod_mpio": "11001",
    "nom_mpio": "BOGOTÁ, D.C.",
    "tipo_municipio": "Municipio",
}


def test_normalize_strips_accents_and_uppercases() -> None:
    assert normalize_name("El Carmen de Viboral") == "EL CARMEN DE VIBORAL"


def test_normalize_collapses_whitespace() -> None:
    assert normalize_name("  Bogotá   D.C.  ") == "BOGOTA D.C."


def test_normalize_is_idempotent() -> None:
    once = normalize_name("Quibdó")
    twice = normalize_name(once)
    assert once == twice == "QUIBDO"


def test_municipality_entry_from_row_carmen_viboral() -> None:
    entry = municipality_entry_from_row(_CARMEN_VIBORAL_ROW)

    assert entry.code == "05148"
    assert entry.name == "EL CARMEN DE VIBORAL"
    assert entry.department_code == "05"
    assert entry.department_name == "ANTIOQUIA"
    assert entry.level == "municipality"
    assert entry.name_normalized == "EL CARMEN DE VIBORAL"
    assert entry.alt_names is None


def test_municipality_entry_applies_known_alt_names() -> None:
    entry = municipality_entry_from_row(_BOGOTA_ROW)

    assert entry.code == "11001"
    assert entry.alt_names == ["Bogotá", "Bogotá D.C.", "Santafé de Bogotá"]


@pytest.mark.parametrize(
    "row",
    [
        {"cod_dpto": "05", "dpto": "ANTIOQUIA", "cod_mpio": "", "nom_mpio": "X"},
        {"cod_dpto": "05", "dpto": "ANTIOQUIA", "cod_mpio": "05148", "nom_mpio": ""},
        {"cod_dpto": "", "dpto": "ANTIOQUIA", "cod_mpio": "05148", "nom_mpio": "X"},
        {"cod_dpto": "05", "dpto": "", "cod_mpio": "05148", "nom_mpio": "X"},
    ],
)
def test_municipality_entry_rejects_incomplete_rows(row: dict) -> None:
    with pytest.raises(DivipolaRowError):
        municipality_entry_from_row(row)


def test_derive_department_entries_deduplicates_by_code() -> None:
    municipalities = [
        municipality_entry_from_row(_CARMEN_VIBORAL_ROW),
        municipality_entry_from_row(
            {"cod_dpto": "05", "dpto": "ANTIOQUIA", "cod_mpio": "05001", "nom_mpio": "MEDELLÍN"}
        ),
        municipality_entry_from_row(_BOGOTA_ROW),
    ]

    departments = derive_department_entries(municipalities)

    assert {d.code for d in departments} == {"05", "11"}
    antioquia = next(d for d in departments if d.code == "05")
    assert antioquia.name == "ANTIOQUIA"
    assert antioquia.level == "department"
    assert antioquia.name_normalized == "ANTIOQUIA"
    assert antioquia.department_code is None
    assert antioquia.department_name is None

    bogota_dept = next(d for d in departments if d.code == "11")
    assert bogota_dept.alt_names == ["Bogotá", "Bogotá D.C.", "Santafé de Bogotá"]


def test_rows_to_entries_includes_departments_and_municipalities() -> None:
    entries = rows_to_entries([_CARMEN_VIBORAL_ROW, _BOGOTA_ROW])

    levels = {(entry.code, entry.level) for entry in entries}
    assert ("05", "department") in levels
    assert ("11", "department") in levels
    assert ("05148", "municipality") in levels
    assert ("11001", "municipality") in levels
    assert len(entries) == 4
