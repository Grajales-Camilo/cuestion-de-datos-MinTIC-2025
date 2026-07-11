from __future__ import annotations

from pathlib import Path

import pytest

from eval.loader import GoldenSuiteError, default_suite_path, load_golden_suite


def test_loads_frozen_golden_v1() -> None:
    suite = load_golden_suite(default_suite_path("golden-v1"))

    assert suite.name == "golden-v1"
    assert suite.version == "1.0.0"
    assert len(suite.cases) == 50
    assert sum(case.case_type == "positive" for case in suite.cases) == 40
    assert sum(case.case_type == "negative" for case in suite.cases) == 10


@pytest.mark.parametrize("name", ["", "../golden-v1", "other-suite"])
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
