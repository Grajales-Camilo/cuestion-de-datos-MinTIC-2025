from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from eval.loader import GoldenSuiteError, default_suite_path, load_golden_suite


def test_loads_frozen_golden_v1() -> None:
    suite = load_golden_suite(default_suite_path("golden-v1"))

    assert suite.name == "golden-v1"
    assert suite.version == "1.0.0"
    assert len(suite.cases) == 50
    assert sum(case.case_type == "positive" for case in suite.cases) == 40
    assert sum(case.case_type == "negative" for case in suite.cases) == 10


def test_loads_approved_golden_v2_with_typed_acceptable_facts() -> None:
    suite = load_golden_suite(default_suite_path("golden-v2"))

    assert suite.schema_version == "golden-v2"
    assert suite.name == "golden-v2"
    assert suite.version == "2.0.0"
    assert len(suite.cases) == 50
    assert sum(case.case_type == "positive" for case in suite.cases) == 40
    assert sum(case.case_type == "negative" for case in suite.cases) == 10
    assert sum(len(case.acceptable_facts) for case in suite.cases) == 59
    postal = next(case for case in suite.cases if case.case_id == "pilot-016-codigos-postales")
    assert postal.classification == "multi_response"
    assert {fact["canonical_value"] for fact in postal.acceptable_facts} == {
        "153420",
        "153427",
    }


@pytest.mark.parametrize("name", ["", "../golden-v1", "../golden-v2", "other-suite"])
def test_default_suite_path_rejects_unapproved_suite(name: str) -> None:
    with pytest.raises(GoldenSuiteError, match="golden-v1"):
        default_suite_path(name)


def test_rejects_suite_not_frozen(tmp_path: Path) -> None:
    source = default_suite_path("golden-v1")
    candidate = tmp_path / "golden-v1.yaml"
    candidate.write_text(
        source.read_text(encoding="utf-8").replace("status: congelado", "status: draft"),
        encoding="utf-8",
    )

    with pytest.raises(GoldenSuiteError, match="congelada"):
        load_golden_suite(candidate)


def test_rejects_invalid_golden_v2_fact_operation(tmp_path: Path) -> None:
    raw = yaml.safe_load(default_suite_path("golden-v2").read_text(encoding="utf-8"))
    raw["cases"][0]["acceptable_facts"][0]["operation"] = "invented"
    candidate = tmp_path / "golden-v2.yaml"
    candidate.write_text(
        yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    with pytest.raises(GoldenSuiteError, match="hecho aceptable inválido"):
        load_golden_suite(candidate)


def test_rejects_tampered_golden_v2_facts_even_when_shape_is_valid(tmp_path: Path) -> None:
    raw = yaml.safe_load(default_suite_path("golden-v2").read_text(encoding="utf-8"))
    raw["cases"][0]["acceptable_facts"][0]["value_or_set"] = "otra etiqueta"
    candidate = tmp_path / "golden-v2.yaml"
    candidate.write_text(
        yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    with pytest.raises(GoldenSuiteError, match="huella de acceptable_facts"):
        load_golden_suite(candidate)
