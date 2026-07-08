from app.quality.pii_classifier import (
    ColumnPiiClassification,
    classify_column,
    classify_dataset,
    load_pii_patterns,
)

FIXTURE = load_pii_patterns()


def test_high_risk_column_is_detected() -> None:
    result = classify_column("numero_cedula", None, None, FIXTURE)
    assert result.risk_level == "high"


def test_high_risk_ignores_accents_and_case() -> None:
    result = classify_column("Número de Cédula", None, None, FIXTURE)
    assert result.risk_level == "high"


def test_low_risk_geographic_code() -> None:
    result = classify_column("municipio", None, None, FIXTURE)
    assert result.risk_level == "low"


def test_medium_risk_quasi_identifier() -> None:
    result = classify_column("salario_individual", None, None, FIXTURE)
    assert result.risk_level == "medium"


def test_unrecognized_column_defaults_to_unknown() -> None:
    result = classify_column("campo_raro_xyz_123", None, None, FIXTURE)
    assert result.risk_level == "unknown"


def test_description_can_trigger_classification() -> None:
    result = classify_column("valor", None, "Historia clinica del paciente", FIXTURE)
    assert result.risk_level == "high"


def test_dataset_risk_is_max_of_columns() -> None:
    columns = [
        ColumnPiiClassification(risk_level="low"),
        ColumnPiiClassification(risk_level="high"),
        ColumnPiiClassification(risk_level="medium"),
    ]
    result = classify_dataset(columns, "Dataset generico", None, None, FIXTURE)
    assert result.risk_level == "high"


def test_dataset_risk_is_not_averaged() -> None:
    columns = [ColumnPiiClassification(risk_level="low")] * 19 + [
        ColumnPiiClassification(risk_level="high")
    ]
    result = classify_dataset(columns, "Dataset generico", None, None, FIXTURE)
    assert result.risk_level == "high"


def test_dataset_title_keyword_escalates_risk() -> None:
    columns = [ColumnPiiClassification(risk_level="low")] * 5
    result = classify_dataset(columns, "Historia Clinica por municipio", None, None, FIXTURE)
    assert result.risk_level == "high"


def test_dataset_title_keyword_does_not_downgrade_unknown() -> None:
    columns = [ColumnPiiClassification(risk_level="unknown")] * 3
    result = classify_dataset(columns, "Beneficiarios del programa", None, None, FIXTURE)
    assert result.risk_level == "unknown"


def test_dataset_with_no_columns_defaults_to_unknown() -> None:
    result = classify_dataset([], "Dataset vacio", None, None, FIXTURE)
    assert result.risk_level == "unknown"


def test_dataset_all_low_columns_stay_low() -> None:
    columns = [ColumnPiiClassification(risk_level="low")] * 4
    result = classify_dataset(columns, "Codigos DIVIPOLA por municipio", None, None, FIXTURE)
    assert result.risk_level == "low"
