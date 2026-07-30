from __future__ import annotations

import json
import uuid

from eval.loader import GoldenCase
from eval.metrics import CaseAssessment, TextualIntegrityAssessment
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


def test_eval_case_result_persists_only_privacy_safe_textual_snapshot() -> None:
    forbidden = {
        "La categoría seleccionada es Salud.",
        "Salud",
        "salud",
        "Narrativa privada",
        "valor fuente privado",
    }
    textual = TextualIntegrityAssessment(
        applicable=True,
        textual_fact_count=1,
        textual_reference_count=1,
        referenced_textual_fact_count=1,
        reproducible_textual_fact_count=1,
        textual_fact_reference_coverage=1.0,
        textual_facts_reproducible=1.0,
        textual_fact_display_match=1.0,
        orphan_factual_segments_count=0,
        invalid_textual_operation_count=0,
        grounded_fact_integrity=True,
        fact_fingerprints=(
            {
                "algorithm_version": "textual-fact-v1",
                "normalization_profile": "text-es-v1",
                "operation": "direct_text",
                "source_hash": f"sha256-jcs-v1:{'a' * 64}",
            },
        ),
    )
    row = _case_result_model(
        eval_run_id=uuid.uuid4(),
        case_db_id=uuid.uuid4(),
        agent_run_id=None,
        final={
            "status": "completed",
            "summary": "Narrativa privada",
            "narrative": "La categoría seleccionada es Salud.",
            "textual_facts": [
                {
                    "fact": "La categoría seleccionada es Salud.",
                    "raw_values": ["valor fuente privado"],
                    "normalized_values": ["salud"],
                    "display_value": "Salud",
                }
            ],
            "usage": {},
            "evidence": [
                {
                    "quality": {
                        "classification": "alta",
                        "eligibility_status": "eligible",
                        "warnings_user": ["valor fuente privado"],
                    }
                }
            ],
        },
        assessment=CaseAssessment(
            False,
            False,
            False,
            (),
            (),
            "falló",
            textual_integrity=textual,
        ),
        stage_diagnostics={"version": "1.0"},
    )

    persisted = {
        "passed": row.passed,
        "status_final": row.status_final,
        "expected_dataset_hit": row.expected_dataset_hit,
        "metrics": row.metrics,
        "quality_summary": row.quality_summary,
        "evidence_dataset_ids": row.evidence_dataset_ids,
        "claim_fingerprint_hashes": row.claim_fingerprint_hashes,
        "error_code": row.error_code,
        "failure_reason": row.failure_reason,
    }
    serialized = json.dumps(persisted, ensure_ascii=False, sort_keys=True)
    assert all(value not in serialized for value in forbidden)
    assert row.metrics["textual_integrity"]["grounded_fact_integrity"] is True


def test_historical_assessment_without_textual_snapshot_remains_readable() -> None:
    row = _case_result_model(
        eval_run_id=uuid.uuid4(),
        case_db_id=uuid.uuid4(),
        agent_run_id=None,
        final={"status": "no_evidence", "usage": {}, "evidence": []},
        assessment=CaseAssessment(False, False, False, (), (), "falló"),
        stage_diagnostics={"version": "1.0"},
    )

    assert "textual_integrity" not in row.metrics
