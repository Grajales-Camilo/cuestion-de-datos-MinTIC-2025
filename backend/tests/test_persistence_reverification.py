"""RF-212 (T-617C-R1): reverificación de claims cuantitativos persistidos,
histórico (alias) y nuevo (nombre real), sin red ni PostgreSQL real -- los
modelos ORM se construyen en memoria, sin sesión."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from app.agent.persistence import _reverify_quantitative_synthesis_fact
from app.db.models import EvidenceResult, QualityReport, QuantitativeClaim
from app.quality.claims import compute_legacy_source_hash, compute_source_hash

RUN_ID = uuid.uuid4()
EVIDENCE_ID = uuid.uuid4()
DATASET_ID = "abcd-1234"
SOQL = "select genero_hombre as dim_1 limit 1"
ROWS = [{"dim_1": "764"}]


def _evidence() -> EvidenceResult:
    return EvidenceResult(
        id=EVIDENCE_ID,
        run_id=RUN_ID,
        dataset_id=DATASET_ID,
        soql_query=SOQL,
        executed_at=datetime.now(UTC),
        source_url="https://example.test/resource/abcd-1234.json",
        rows=ROWS,
        row_count=1,
    )


def _quality() -> QualityReport:
    return QualityReport(
        evidence_id=EVIDENCE_ID,
        score_total=90,
        classification="alta",
        eligibility_status="eligible",
        eligibility_reasons=[],
    )


def test_new_claim_reverifies_with_real_column_name_and_yields_verified_label() -> None:
    """Requisito 5 (T-615H): una reverificación nueva recupera la columna
    fuente real y deriva `label`/`label_status` sin volver a leer el alias."""

    raw_value = Decimal("764")
    source_hash = compute_source_hash(
        dataset_id=DATASET_ID,
        canonical_soql=SOQL,
        source_row_indexes=(0,),
        rows=tuple(ROWS),
        execution_columns=("dim_1",),
        public_columns=("genero_hombre",),
        formula=None,
        raw_value=raw_value,
        unit=None,
        rounding=0,
    )
    claim = QuantitativeClaim(
        id=uuid.uuid4(),
        run_id=RUN_ID,
        evidence_id=EVIDENCE_ID,
        claim_text="lookup: pregunta (dim_1, fila 0): 764",
        claim_type="direct",
        source_row_indexes=[0],
        columns_used=["genero_hombre"],
        formula=None,
        raw_value=raw_value,
        display_value="764",
        unit=None,
        rounding=0,
        source_hash=source_hash,
    )

    fact = _reverify_quantitative_synthesis_fact(
        run_id=RUN_ID, claim=claim, evidence=_evidence(), quality=_quality()
    )

    assert fact is not None
    assert fact.columns == ("genero_hombre",)
    assert fact.label == "Genero hombre"
    assert fact.label_status == "verified"
    assert fact.display_value == "764"


def test_legacy_claim_with_alias_columns_still_reverifies() -> None:
    """Requisito 4: un claim persistido antes de T-617C-R1 (columns_used =
    alias de ejecución, hash v1.0.0) sigue reverificándose -- no se
    invalida evidencia histórica en silencio -- pero queda `ambiguous`
    porque no hay nombre real que exponer como etiqueta."""

    raw_value = Decimal("764")
    legacy_hash = compute_legacy_source_hash(
        dataset_id=DATASET_ID,
        canonical_soql=SOQL,
        source_row_indexes=(0,),
        rows=tuple(ROWS),
        columns=("dim_1",),
        formula=None,
        raw_value=raw_value,
        unit=None,
        rounding=0,
    )
    claim = QuantitativeClaim(
        id=uuid.uuid4(),
        run_id=RUN_ID,
        evidence_id=EVIDENCE_ID,
        claim_text="lookup: pregunta (dim_1, fila 0): 764",
        claim_type="direct",
        source_row_indexes=[0],
        columns_used=["dim_1"],
        formula=None,
        raw_value=raw_value,
        display_value="764",
        unit=None,
        rounding=0,
        source_hash=legacy_hash,
    )

    fact = _reverify_quantitative_synthesis_fact(
        run_id=RUN_ID, claim=claim, evidence=_evidence(), quality=_quality()
    )

    assert fact is not None
    assert fact.columns == ("dim_1",)
    assert fact.label is None
    assert fact.label_status == "ambiguous"
    assert fact.display_value == "764"


def test_new_claim_with_tampered_hash_is_rejected() -> None:
    """La reverificación sigue bloqueando manipulación: un `source_hash` que
    no reproduce el algoritmo v2.0.0 se rechaza (fact=None), igual que
    antes de T-617C-R1."""

    claim = QuantitativeClaim(
        id=uuid.uuid4(),
        run_id=RUN_ID,
        evidence_id=EVIDENCE_ID,
        claim_text="lookup: pregunta (dim_1, fila 0): 764",
        claim_type="direct",
        source_row_indexes=[0],
        columns_used=["genero_hombre"],
        formula=None,
        raw_value=Decimal("764"),
        display_value="764",
        unit=None,
        rounding=0,
        source_hash="sha256:" + "0" * 64,
    )

    fact = _reverify_quantitative_synthesis_fact(
        run_id=RUN_ID, claim=claim, evidence=_evidence(), quality=_quality()
    )

    assert fact is None


def test_new_claim_with_unresolvable_column_is_rejected_not_crashed() -> None:
    """Si el nombre público persistido no puede vincularse con ningún alias
    del SoQL persistido (columna inexistente/corrupta), la reverificación
    se abstiene en vez de fallar con una excepción no controlada."""

    claim = QuantitativeClaim(
        id=uuid.uuid4(),
        run_id=RUN_ID,
        evidence_id=EVIDENCE_ID,
        claim_text="lookup: pregunta (dim_1, fila 0): 764",
        claim_type="direct",
        source_row_indexes=[0],
        columns_used=["columna_que_no_existe_en_el_soql"],
        formula=None,
        raw_value=Decimal("764"),
        display_value="764",
        unit=None,
        rounding=0,
        source_hash="sha256:" + "0" * 64,
    )

    fact = _reverify_quantitative_synthesis_fact(
        run_id=RUN_ID, claim=claim, evidence=_evidence(), quality=_quality()
    )

    assert fact is None
