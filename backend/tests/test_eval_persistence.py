from __future__ import annotations

import uuid

from eval.loader import GoldenCase
from eval.metrics import CaseAssessment
from eval.persistence import case_signature
from eval.run import _case_result_model


def test_case_signature_is_stable_for_equivalent_case() -> None:
    case = GoldenCase(
        case_id="case-1",
        case_type="positive",
        question="Pregunta",
        expected_dataset_ids=("abcd-1234",),
        expected_facts=({"expected_value": {"total": "10"}},),
        seed=601001,
        notes="Nota",
    )

    assert case_signature(case) == case_signature(case)


def test_case_signature_changes_when_frozen_content_changes() -> None:
    original = GoldenCase("case-1", "negative", "Pregunta", (), (), 601001, "Nota")
    changed = GoldenCase("case-1", "negative", "Otra pregunta", (), (), 601001, "Nota")

    assert case_signature(original) != case_signature(changed)


def test_eval_case_result_persists_versioned_stage_diagnostics_inside_metrics() -> None:
    diagnostics = {
        "version": "1.0",
        "failure_stage": "retrieval",
        "failure_code": "expected_dataset_not_retrieved",
        "retrieved_dataset_ids": ["other-id"],
    }
    row = _case_result_model(
        eval_run_id=uuid.uuid4(),
        case_db_id=uuid.uuid4(),
        agent_run_id=None,
        final={"status": "no_evidence", "usage": {}, "evidence": []},
        assessment=CaseAssessment(False, False, False, (), (), "falló"),
        stage_diagnostics=diagnostics,
    )

    assert row.metrics["stage_diagnostics"] == diagnostics
    assert row.metrics["stage_diagnostics"]["version"] == "1.0"
