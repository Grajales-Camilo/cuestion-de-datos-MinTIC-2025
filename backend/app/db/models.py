from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class OfficialPublisher(Base):
    __tablename__ = "official_publishers"
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ("
            "'ministerio', 'departamento_administrativo', 'gobernacion', 'alcaldia', "
            "'universidad_publica', 'empresa_estado', 'establecimiento_publico', "
            "'otra_estatal')",
            name="ck_official_publishers_entity_type",
        ),
        ForeignKeyConstraint(["successor_id"], ["official_publishers.id"]),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)
    successor_id: Mapped[str | None] = mapped_column(Text)
    verification_source: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OfficialPublisherAlias(Base):
    __tablename__ = "official_publisher_aliases"
    __table_args__ = (
        Index(
            "uq_official_alias_unambiguous",
            "alias_normalized",
            unique=True,
            postgresql_where=text("ambiguous = false"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    publisher_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("official_publishers.id", ondelete="CASCADE"),
        nullable=False,
    )
    alias_normalized: Mapped[str] = mapped_column(Text, nullable=False)
    alias_raw: Mapped[str | None] = mapped_column(Text)
    ambiguous: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    verification_source: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CatalogDataset(Base):
    __tablename__ = "catalog_datasets"
    __table_args__ = (
        CheckConstraint(
            "publisher_verification_status IN ('verified', 'unknown', "
            "'private_or_non_official')",
            name="ck_catalog_datasets_publisher_verification_status",
        ),
        CheckConstraint(
            "pii_risk_level IN ('low', 'medium', 'high', 'unknown')",
            name="ck_catalog_datasets_pii_risk_level",
        ),
        CheckConstraint(
            "eligibility_status IN ('eligible', 'diagnostic_only', 'blocked')",
            name="ck_catalog_datasets_eligibility_status",
        ),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    publisher: Mapped[str | None] = mapped_column(Text)
    official_publisher_id: Mapped[str | None] = mapped_column(ForeignKey("official_publishers.id"))
    publisher_verification_status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'unknown'"),
    )
    category: Mapped[str | None] = mapped_column(Text)
    row_count: Mapped[int | None] = mapped_column(BigInteger)
    data_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latest_observed_cutoff_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    api_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    pii_risk_level: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'unknown'"),
    )
    pii_reviewed_by: Mapped[str | None] = mapped_column(Text)
    pii_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pii_review_source: Mapped[str | None] = mapped_column(Text)
    pii_review_notes: Mapped[str | None] = mapped_column(Text)
    eligibility_status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'diagnostic_only'"),
    )
    eligibility_reasons: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    embedding_text: Mapped[str | None] = mapped_column(Text)


class CatalogColumn(Base):
    __tablename__ = "catalog_columns"
    __table_args__ = (
        CheckConstraint(
            "null_ratio IS NULL OR (null_ratio >= 0 AND null_ratio <= 1)",
            name="ck_catalog_columns_null_ratio",
        ),
        CheckConstraint(
            "pii_risk_level IN ('low', 'medium', 'high', 'unknown')",
            name="ck_catalog_columns_pii_risk_level",
        ),
        CheckConstraint(
            "eligibility_status IN ('eligible', 'diagnostic_only', 'blocked')",
            name="ck_catalog_columns_eligibility_status",
        ),
        UniqueConstraint("dataset_id", "field_name", name="uq_catalog_columns_dataset_field"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    dataset_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("catalog_datasets.id", ondelete="CASCADE"),
        nullable=False,
    )
    field_name: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str | None] = mapped_column(Text)
    data_type: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    sample_values: Mapped[Any | None] = mapped_column(JSONB)
    null_ratio: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    pii_risk_level: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'unknown'"),
    )
    contains_personal_data: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    eligibility_status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'diagnostic_only'"),
    )
    eligibility_reasons: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )


class IngestRun(Base):
    __tablename__ = "ingest_runs"
    __table_args__ = (
        CheckConstraint("trigger IN ('manual', 'cron')", name="ck_ingest_runs_trigger"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trigger: Mapped[str] = mapped_column(Text, nullable=False)
    datasets_new: Mapped[int | None] = mapped_column(Integer)
    datasets_updated: Mapped[int | None] = mapped_column(Integer)
    datasets_failed: Mapped[int | None] = mapped_column(Integer)
    error_summary: Mapped[Any | None] = mapped_column(JSONB)


class WorkerInstance(Base):
    __tablename__ = "worker_instances"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'expired', 'shutdown')",
            name="ck_worker_instances_status",
        ),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)


class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'completed', 'no_evidence', 'failed', 'interrupted')",
            name="ck_agent_runs_status",
        ),
        CheckConstraint(
            "retention_class IN ('user', 'eval')",
            name="ck_agent_runs_retention_class",
        ),
        CheckConstraint("last_event_seq >= 0", name="ck_agent_runs_last_event_seq"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    question: Mapped[str] = mapped_column(Text, nullable=False)
    context_hint: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    worker_instance_id: Mapped[str | None] = mapped_column(ForeignKey("worker_instances.id"))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_event_seq: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    run_access_token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    run_access_token_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    retention_class: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'user'"),
    )
    terminal_error_code: Mapped[str | None] = mapped_column(Text)
    terminal_event_written_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    llm_provider: Mapped[str | None] = mapped_column(Text)
    llm_model: Mapped[str | None] = mapped_column(Text)
    steps_used: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    estimated_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    final_answer: Mapped[Any | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AgentStep(Base):
    __tablename__ = "agent_steps"
    __table_args__ = (
        UniqueConstraint("run_id", "step_number", name="uq_agent_steps_run_step"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    node: Mapped[str] = mapped_column(Text, nullable=False)
    tool_input: Mapped[Any | None] = mapped_column(JSONB)
    tool_output_summary: Mapped[Any | None] = mapped_column(JSONB)
    display_message: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)


class AgentRunEvent(Base):
    __tablename__ = "agent_run_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('step', 'evidence', 'answer', 'error')",
            name="ck_agent_run_events_event_type",
        ),
        CheckConstraint("seq > 0", name="ck_agent_run_events_seq"),
        UniqueConstraint("run_id", "seq", name="uq_agent_run_events_run_seq"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[Any] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TechnicalMetric(Base):
    __tablename__ = "technical_metrics"
    __table_args__ = (
        CheckConstraint(
            "retention_class_origin IN ('user', 'eval')",
            name="ck_technical_metrics_retention_class_origin",
        ),
        CheckConstraint(
            "status_final IN ('running', 'completed', 'no_evidence', 'failed', 'interrupted')",
            name="ck_technical_metrics_status_final",
        ),
        CheckConstraint(
            "deletion_reason IN ('retention_expired', 'user_requested')",
            name="ck_technical_metrics_deletion_reason",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    run_month: Mapped[str] = mapped_column(Text, nullable=False)
    source_run_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    retention_class_origin: Mapped[str] = mapped_column(Text, nullable=False)
    status_final: Mapped[str] = mapped_column(Text, nullable=False)
    llm_provider: Mapped[str | None] = mapped_column(Text)
    llm_model: Mapped[str | None] = mapped_column(Text)
    steps_used: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    estimated_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deletion_reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EvidenceResult(Base):
    __tablename__ = "evidence_results"
    __table_args__ = (
        CheckConstraint(
            "data_cutoff_confidence IS NULL OR "
            "(data_cutoff_confidence >= 0 AND data_cutoff_confidence <= 1)",
            name="ck_evidence_results_data_cutoff_confidence",
        ),
        CheckConstraint(
            "data_cutoff_basis IN ('data_cutoff_at', 'data_updated_at_fallback', 'unknown')",
            name="ck_evidence_results_data_cutoff_basis",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    dataset_id: Mapped[str] = mapped_column(ForeignKey("catalog_datasets.id"), nullable=False)
    soql_query: Mapped[str] = mapped_column(Text, nullable=False)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    rows: Mapped[Any] = mapped_column(JSONB, nullable=False)
    row_count: Mapped[int | None] = mapped_column(Integer)
    data_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    data_cutoff_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    data_cutoff_method: Mapped[str | None] = mapped_column(Text)
    data_cutoff_column: Mapped[str | None] = mapped_column(Text)
    data_cutoff_confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    data_cutoff_basis: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'unknown'"),
    )
    data_cutoff_inferred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    narrative: Mapped[str | None] = mapped_column(Text)
    citation: Mapped[Any] = mapped_column(JSONB, nullable=False)


class QualityReport(Base):
    __tablename__ = "quality_reports"
    __table_args__ = (
        CheckConstraint(
            "score_total >= 0 AND score_total <= 100",
            name="ck_quality_reports_score_total",
        ),
        CheckConstraint(
            "classification IN ('alta', 'media', 'baja', 'no_recomendada')",
            name="ck_quality_reports_classification",
        ),
        CheckConstraint(
            "eligibility_status IN ('eligible', 'diagnostic_only', 'blocked')",
            name="ck_quality_reports_eligibility_status",
        ),
    )

    evidence_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evidence_results.id", ondelete="CASCADE"),
        primary_key=True,
    )
    score_total: Mapped[int] = mapped_column(Integer, nullable=False)
    classification: Mapped[str] = mapped_column(Text, nullable=False)
    eligibility_status: Mapped[str] = mapped_column(Text, nullable=False)
    eligibility_reasons: Mapped[Any] = mapped_column(JSONB, nullable=False)
    dim_schema: Mapped[Any] = mapped_column(JSONB, nullable=False)
    dim_completeness: Mapped[Any] = mapped_column(JSONB, nullable=False)
    dim_timeliness: Mapped[Any] = mapped_column(JSONB, nullable=False)
    dim_traceability: Mapped[Any] = mapped_column(JSONB, nullable=False)
    warnings_user: Mapped[Any | None] = mapped_column(JSONB)
    validator_version: Mapped[str] = mapped_column(Text, nullable=False)


class QuantitativeClaim(Base):
    __tablename__ = "quantitative_claims"
    __table_args__ = (
        CheckConstraint(
            "claim_type IN ('direct', 'derived')",
            name="ck_quantitative_claims_claim_type",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    evidence_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evidence_results.id", ondelete="CASCADE"),
        nullable=False,
    )
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    claim_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_row_indexes: Mapped[list[int]] = mapped_column(ARRAY(Integer), nullable=False)
    columns_used: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    formula: Mapped[Any | None] = mapped_column(JSONB)
    raw_value: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    display_value: Mapped[str] = mapped_column(Text, nullable=False)
    unit: Mapped[str | None] = mapped_column(Text)
    rounding: Mapped[int | None] = mapped_column(Integer)
    source_hash: Mapped[str] = mapped_column(Text, nullable=False)


class EvalSuite(Base):
    __tablename__ = "eval_suites"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    version: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EvalCase(Base):
    __tablename__ = "eval_cases"
    __table_args__ = (
        CheckConstraint("case_type IN ('positive', 'negative')", name="ck_eval_cases_case_type"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    suite_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("eval_suites.id", ondelete="CASCADE"),
        nullable=False,
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    case_type: Mapped[str] = mapped_column(Text, nullable=False)
    expected_dataset_ids: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    expected_facts: Mapped[Any | None] = mapped_column(JSONB)
    seed: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    notes: Mapped[str | None] = mapped_column(Text)


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id: Mapped[uuid.UUID] = uuid_pk()
    suite_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("eval_suites.id"),
        nullable=False,
    )
    git_commit: Mapped[str] = mapped_column(Text, nullable=False)
    llm_provider: Mapped[str] = mapped_column(Text, nullable=False)
    llm_model: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_model: Mapped[str | None] = mapped_column(Text)
    eval_seed: Mapped[int] = mapped_column(Integer, nullable=False)
    config_snapshot: Mapped[Any] = mapped_column(JSONB, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    success_rate: Mapped[Decimal | None] = mapped_column(Numeric)
    socrata_success_rate: Mapped[Decimal | None] = mapped_column(Numeric)
    claims_coverage: Mapped[Decimal | None] = mapped_column(Numeric)
    claims_reproducible: Mapped[Decimal | None] = mapped_column(Numeric)
    orphan_figures_count: Mapped[int | None] = mapped_column(Integer)
    recall_at_10: Mapped[Decimal | None] = mapped_column(Numeric)
    fabrication_count: Mapped[int | None] = mapped_column(Integer)
    latency_simple_p95_ms: Mapped[int | None] = mapped_column(Integer)
    latency_multistep_p95_ms: Mapped[int | None] = mapped_column(Integer)
    latency_p50_ms: Mapped[int | None] = mapped_column(Integer)
    latency_p95_ms: Mapped[int | None] = mapped_column(Integer)
    avg_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))


class EvalCaseResult(Base):
    __tablename__ = "eval_case_results"
    __table_args__ = (
        UniqueConstraint("eval_run_id", "case_id", name="uq_eval_case_results_run_case"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    eval_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("eval_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("eval_cases.id"),
        nullable=False,
    )
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="SET NULL"),
    )
    passed: Mapped[bool | None] = mapped_column(Boolean)
    status_final: Mapped[str] = mapped_column(Text, nullable=False)
    expected_dataset_hit: Mapped[bool | None] = mapped_column(Boolean)
    metrics: Mapped[Any] = mapped_column(JSONB, nullable=False)
    quality_summary: Mapped[Any | None] = mapped_column(JSONB)
    evidence_dataset_ids: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    claim_fingerprint_hashes: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    error_code: Mapped[str | None] = mapped_column(Text)
    failure_reason: Mapped[str | None] = mapped_column(Text)


class DivipolaEntry(Base):
    __tablename__ = "divipola_entries"
    __table_args__ = (
        CheckConstraint(
            "level IN ('department', 'municipality')",
            name="ck_divipola_entries_level",
        ),
        Index(
            "ix_divipola_entries_name_normalized_trgm",
            "name_normalized",
            postgresql_using="gin",
            postgresql_ops={"name_normalized": "gin_trgm_ops"},
        ),
    )

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    department_code: Mapped[str | None] = mapped_column(Text)
    department_name: Mapped[str | None] = mapped_column(Text)
    level: Mapped[str] = mapped_column(Text, nullable=False)
    name_normalized: Mapped[str] = mapped_column(Text, nullable=False)
    alt_names: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
