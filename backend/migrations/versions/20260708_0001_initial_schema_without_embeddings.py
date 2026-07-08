"""Initial schema without catalog embeddings.

Revision ID: 20260708_0001
Revises:
Create Date: 2026-07-08 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260708_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB
TEXT_ARRAY = postgresql.ARRAY(sa.Text())
INT_ARRAY = postgresql.ARRAY(sa.Integer())


def created_at_column() -> sa.Column:
    return sa.Column("created_at", sa.DateTime(timezone=True), nullable=False)


def upgrade() -> None:
    op.create_table(
        "official_publishers",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("canonical_name", sa.Text(), nullable=False),
        sa.Column("normalized_name", sa.Text(), nullable=False, unique=True),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("valid_from", sa.Date()),
        sa.Column("valid_until", sa.Date()),
        sa.Column("successor_id", sa.Text()),
        sa.Column("verification_source", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "entity_type IN ("
            "'ministerio', 'departamento_administrativo', 'gobernacion', 'alcaldia', "
            "'universidad_publica', 'empresa_estado', 'establecimiento_publico', "
            "'otra_estatal')",
            name="ck_official_publishers_entity_type",
        ),
        sa.ForeignKeyConstraint(["successor_id"], ["official_publishers.id"]),
    )

    op.create_table(
        "official_publisher_aliases",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("publisher_id", sa.Text(), nullable=False),
        sa.Column("alias_normalized", sa.Text(), nullable=False),
        sa.Column("alias_raw", sa.Text()),
        sa.Column("ambiguous", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("verification_source", sa.Text(), nullable=False),
        created_at_column(),
        sa.ForeignKeyConstraint(
            ["publisher_id"],
            ["official_publishers.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "uq_official_alias_unambiguous",
        "official_publisher_aliases",
        ["alias_normalized"],
        unique=True,
        postgresql_where=sa.text("ambiguous = false"),
    )

    op.create_table(
        "catalog_datasets",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("publisher", sa.Text()),
        sa.Column("official_publisher_id", sa.Text()),
        sa.Column(
            "publisher_verification_status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'unknown'"),
        ),
        sa.Column("category", sa.Text()),
        sa.Column("row_count", sa.BigInteger()),
        sa.Column("data_updated_at", sa.DateTime(timezone=True)),
        sa.Column("latest_observed_cutoff_at", sa.DateTime(timezone=True)),
        sa.Column("metadata_synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("api_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "pii_risk_level",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'unknown'"),
        ),
        sa.Column("pii_reviewed_by", sa.Text()),
        sa.Column("pii_reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("pii_review_source", sa.Text()),
        sa.Column("pii_review_notes", sa.Text()),
        sa.Column(
            "eligibility_status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'diagnostic_only'"),
        ),
        sa.Column(
            "eligibility_reasons",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("embedding_text", sa.Text()),
        sa.CheckConstraint(
            "publisher_verification_status IN ('verified', 'unknown', "
            "'private_or_non_official')",
            name="ck_catalog_datasets_publisher_verification_status",
        ),
        sa.CheckConstraint(
            "pii_risk_level IN ('low', 'medium', 'high', 'unknown')",
            name="ck_catalog_datasets_pii_risk_level",
        ),
        sa.CheckConstraint(
            "eligibility_status IN ('eligible', 'diagnostic_only', 'blocked')",
            name="ck_catalog_datasets_eligibility_status",
        ),
        sa.ForeignKeyConstraint(["official_publisher_id"], ["official_publishers.id"]),
    )

    op.create_table(
        "catalog_columns",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("dataset_id", sa.Text(), nullable=False),
        sa.Column("field_name", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text()),
        sa.Column("data_type", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("sample_values", JSONB),
        sa.Column("null_ratio", sa.Numeric(5, 4)),
        sa.Column(
            "pii_risk_level",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'unknown'"),
        ),
        sa.Column(
            "contains_personal_data",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "eligibility_status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'diagnostic_only'"),
        ),
        sa.Column(
            "eligibility_reasons",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.CheckConstraint(
            "null_ratio IS NULL OR (null_ratio >= 0 AND null_ratio <= 1)",
            name="ck_catalog_columns_null_ratio",
        ),
        sa.CheckConstraint(
            "pii_risk_level IN ('low', 'medium', 'high', 'unknown')",
            name="ck_catalog_columns_pii_risk_level",
        ),
        sa.CheckConstraint(
            "eligibility_status IN ('eligible', 'diagnostic_only', 'blocked')",
            name="ck_catalog_columns_eligibility_status",
        ),
        sa.ForeignKeyConstraint(["dataset_id"], ["catalog_datasets.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("dataset_id", "field_name", name="uq_catalog_columns_dataset_field"),
    )

    op.create_table(
        "ingest_runs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("trigger", sa.Text(), nullable=False),
        sa.Column("datasets_new", sa.Integer()),
        sa.Column("datasets_updated", sa.Integer()),
        sa.Column("datasets_failed", sa.Integer()),
        sa.Column("error_summary", JSONB),
        sa.CheckConstraint("trigger IN ('manual', 'cron')", name="ck_ingest_runs_trigger"),
    )

    op.create_table(
        "worker_instances",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'expired', 'shutdown')",
            name="ck_worker_instances_status",
        ),
    )

    op.create_table(
        "agent_runs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("context_hint", sa.Text()),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("worker_instance_id", sa.Text()),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("last_event_seq", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("run_access_token_hash", sa.Text(), nullable=False),
        sa.Column("run_access_token_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "retention_class",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'user'"),
        ),
        sa.Column("terminal_error_code", sa.Text()),
        sa.Column("terminal_event_written_at", sa.DateTime(timezone=True)),
        sa.Column("llm_provider", sa.Text()),
        sa.Column("llm_model", sa.Text()),
        sa.Column("steps_used", sa.Integer()),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("estimated_cost_usd", sa.Numeric(10, 6)),
        sa.Column("final_answer", JSONB),
        created_at_column(),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'no_evidence', 'failed', 'interrupted')",
            name="ck_agent_runs_status",
        ),
        sa.CheckConstraint(
            "retention_class IN ('user', 'eval')",
            name="ck_agent_runs_retention_class",
        ),
        sa.CheckConstraint("last_event_seq >= 0", name="ck_agent_runs_last_event_seq"),
        sa.ForeignKeyConstraint(["worker_instance_id"], ["worker_instances.id"]),
    )

    op.create_table(
        "agent_steps",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("run_id", UUID, nullable=False),
        sa.Column("step_number", sa.Integer(), nullable=False),
        sa.Column("node", sa.Text(), nullable=False),
        sa.Column("tool_input", JSONB),
        sa.Column("tool_output_summary", JSONB),
        sa.Column("display_message", sa.Text()),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("error", sa.Text()),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("run_id", "step_number", name="uq_agent_steps_run_step"),
    )

    op.create_table(
        "agent_run_events",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("run_id", UUID, nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        created_at_column(),
        sa.CheckConstraint(
            "event_type IN ('step', 'evidence', 'answer', 'error')",
            name="ck_agent_run_events_event_type",
        ),
        sa.CheckConstraint("seq > 0", name="ck_agent_run_events_seq"),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("run_id", "seq", name="uq_agent_run_events_run_seq"),
    )

    op.create_table(
        "technical_metrics",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("run_month", sa.Text(), nullable=False),
        sa.Column("source_run_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("retention_class_origin", sa.Text(), nullable=False),
        sa.Column("status_final", sa.Text(), nullable=False),
        sa.Column("llm_provider", sa.Text()),
        sa.Column("llm_model", sa.Text()),
        sa.Column("steps_used", sa.Integer()),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("estimated_cost_usd", sa.Numeric(10, 6)),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deletion_reason", sa.Text(), nullable=False),
        created_at_column(),
        sa.CheckConstraint(
            "retention_class_origin IN ('user', 'eval')",
            name="ck_technical_metrics_retention_class_origin",
        ),
        sa.CheckConstraint(
            "status_final IN ('running', 'completed', 'no_evidence', 'failed', 'interrupted')",
            name="ck_technical_metrics_status_final",
        ),
        sa.CheckConstraint(
            "deletion_reason IN ('retention_expired', 'user_requested')",
            name="ck_technical_metrics_deletion_reason",
        ),
    )

    op.create_table(
        "evidence_results",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("run_id", UUID, nullable=False),
        sa.Column("dataset_id", sa.Text(), nullable=False),
        sa.Column("soql_query", sa.Text(), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("rows", JSONB, nullable=False),
        sa.Column("row_count", sa.Integer()),
        sa.Column("data_updated_at", sa.DateTime(timezone=True)),
        sa.Column("data_cutoff_at", sa.DateTime(timezone=True)),
        sa.Column("data_cutoff_method", sa.Text()),
        sa.Column("data_cutoff_column", sa.Text()),
        sa.Column("data_cutoff_confidence", sa.Numeric(3, 2)),
        sa.Column(
            "data_cutoff_basis",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'unknown'"),
        ),
        sa.Column("data_cutoff_inferred_at", sa.DateTime(timezone=True)),
        sa.Column("narrative", sa.Text()),
        sa.Column("citation", JSONB, nullable=False),
        sa.CheckConstraint(
            "data_cutoff_confidence IS NULL OR "
            "(data_cutoff_confidence >= 0 AND data_cutoff_confidence <= 1)",
            name="ck_evidence_results_data_cutoff_confidence",
        ),
        sa.CheckConstraint(
            "data_cutoff_basis IN ('data_cutoff_at', 'data_updated_at_fallback', 'unknown')",
            name="ck_evidence_results_data_cutoff_basis",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dataset_id"], ["catalog_datasets.id"]),
    )

    op.create_table(
        "quality_reports",
        sa.Column("evidence_id", UUID, primary_key=True),
        sa.Column("score_total", sa.Integer(), nullable=False),
        sa.Column("classification", sa.Text(), nullable=False),
        sa.Column("eligibility_status", sa.Text(), nullable=False),
        sa.Column("eligibility_reasons", JSONB, nullable=False),
        sa.Column("dim_schema", JSONB, nullable=False),
        sa.Column("dim_completeness", JSONB, nullable=False),
        sa.Column("dim_timeliness", JSONB, nullable=False),
        sa.Column("dim_traceability", JSONB, nullable=False),
        sa.Column("warnings_user", JSONB),
        sa.Column("validator_version", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "score_total >= 0 AND score_total <= 100",
            name="ck_quality_reports_score_total",
        ),
        sa.CheckConstraint(
            "classification IN ('alta', 'media', 'baja', 'no_recomendada')",
            name="ck_quality_reports_classification",
        ),
        sa.CheckConstraint(
            "eligibility_status IN ('eligible', 'diagnostic_only', 'blocked')",
            name="ck_quality_reports_eligibility_status",
        ),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence_results.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "quantitative_claims",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("run_id", UUID, nullable=False),
        sa.Column("evidence_id", UUID, nullable=False),
        sa.Column("claim_text", sa.Text(), nullable=False),
        sa.Column("claim_type", sa.Text(), nullable=False),
        sa.Column("source_row_indexes", INT_ARRAY, nullable=False),
        sa.Column("columns_used", TEXT_ARRAY, nullable=False),
        sa.Column("formula", JSONB),
        sa.Column("raw_value", sa.Numeric(), nullable=False),
        sa.Column("display_value", sa.Text(), nullable=False),
        sa.Column("unit", sa.Text()),
        sa.Column("rounding", sa.Integer()),
        sa.Column("source_hash", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "claim_type IN ('direct', 'derived')",
            name="ck_quantitative_claims_claim_type",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence_results.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "eval_suites",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("description", sa.Text()),
        sa.Column("version", sa.Text()),
        created_at_column(),
    )

    op.create_table(
        "eval_cases",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("suite_id", UUID, nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("case_type", sa.Text(), nullable=False),
        sa.Column("expected_dataset_ids", TEXT_ARRAY),
        sa.Column("expected_facts", JSONB),
        sa.Column("seed", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("notes", sa.Text()),
        sa.CheckConstraint(
            "case_type IN ('positive', 'negative')",
            name="ck_eval_cases_case_type",
        ),
        sa.ForeignKeyConstraint(["suite_id"], ["eval_suites.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "eval_runs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("suite_id", UUID, nullable=False),
        sa.Column("git_commit", sa.Text(), nullable=False),
        sa.Column("llm_provider", sa.Text(), nullable=False),
        sa.Column("llm_model", sa.Text(), nullable=False),
        sa.Column("embedding_model", sa.Text()),
        sa.Column("eval_seed", sa.Integer(), nullable=False),
        sa.Column("config_snapshot", JSONB, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("success_rate", sa.Numeric()),
        sa.Column("socrata_success_rate", sa.Numeric()),
        sa.Column("claims_coverage", sa.Numeric()),
        sa.Column("claims_reproducible", sa.Numeric()),
        sa.Column("orphan_figures_count", sa.Integer()),
        sa.Column("recall_at_10", sa.Numeric()),
        sa.Column("fabrication_count", sa.Integer()),
        sa.Column("latency_simple_p95_ms", sa.Integer()),
        sa.Column("latency_multistep_p95_ms", sa.Integer()),
        sa.Column("latency_p50_ms", sa.Integer()),
        sa.Column("latency_p95_ms", sa.Integer()),
        sa.Column("avg_cost_usd", sa.Numeric(10, 6)),
        sa.ForeignKeyConstraint(["suite_id"], ["eval_suites.id"]),
    )

    op.create_table(
        "eval_case_results",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("eval_run_id", UUID, nullable=False),
        sa.Column("case_id", UUID, nullable=False),
        sa.Column("agent_run_id", UUID),
        sa.Column("passed", sa.Boolean()),
        sa.Column("status_final", sa.Text(), nullable=False),
        sa.Column("expected_dataset_hit", sa.Boolean()),
        sa.Column("metrics", JSONB, nullable=False),
        sa.Column("quality_summary", JSONB),
        sa.Column("evidence_dataset_ids", TEXT_ARRAY),
        sa.Column("claim_fingerprint_hashes", TEXT_ARRAY),
        sa.Column("error_code", sa.Text()),
        sa.Column("failure_reason", sa.Text()),
        sa.ForeignKeyConstraint(["eval_run_id"], ["eval_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["case_id"], ["eval_cases.id"]),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("eval_run_id", "case_id", name="uq_eval_case_results_run_case"),
    )

    op.create_table(
        "divipola_entries",
        sa.Column("code", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("department_code", sa.Text()),
        sa.Column("department_name", sa.Text()),
        sa.Column("level", sa.Text(), nullable=False),
        sa.Column("name_normalized", sa.Text(), nullable=False),
        sa.Column("alt_names", TEXT_ARRAY),
        sa.CheckConstraint(
            "level IN ('department', 'municipality')",
            name="ck_divipola_entries_level",
        ),
    )
    op.create_index(
        "ix_divipola_entries_name_normalized_trgm",
        "divipola_entries",
        ["name_normalized"],
        postgresql_using="gin",
        postgresql_ops={"name_normalized": "gin_trgm_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_divipola_entries_name_normalized_trgm", table_name="divipola_entries")
    op.drop_table("divipola_entries")
    op.drop_table("eval_case_results")
    op.drop_table("eval_runs")
    op.drop_table("eval_cases")
    op.drop_table("eval_suites")
    op.drop_table("quantitative_claims")
    op.drop_table("quality_reports")
    op.drop_table("evidence_results")
    op.drop_table("technical_metrics")
    op.drop_table("agent_run_events")
    op.drop_table("agent_steps")
    op.drop_table("agent_runs")
    op.drop_table("worker_instances")
    op.drop_table("ingest_runs")
    op.drop_table("catalog_columns")
    op.drop_table("catalog_datasets")
    op.drop_index("uq_official_alias_unambiguous", table_name="official_publisher_aliases")
    op.drop_table("official_publisher_aliases")
    op.drop_table("official_publishers")
