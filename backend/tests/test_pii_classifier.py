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


def test_low_risk_survives_realistic_non_empty_description() -> None:
    """Regresion del hallazgo T-303: con description no vacia (el caso normal
    en produccion), el allowlist de low debia seguir resolviendo -- antes de
    la correccion, el ancla `$` nunca alcanzaba el final de un haystack
    concatenado con la descripcion y esto quedaba en 'unknown'."""
    result = classify_column(
        "municipio",
        "Municipio",
        "Nombre del municipio de residencia del estudiante segun DIVIPOLA",
        FIXTURE,
    )
    assert result.risk_level == "low"


def test_low_risk_resolves_via_display_name_despite_socrata_mangling() -> None:
    """Socrata reemplaza cada caracter acentuado por '_' en field_name
    ('codigo' -> 'c_digo') pero preserva la tilde en display_name; el
    allowlist de low debe resolver usando display_name."""
    result = classify_column(
        "c_digo_municipio", "Código_Municipio", "Codigo DIVIPOLA del municipio", FIXTURE
    )
    assert result.risk_level == "low"


def test_low_risk_education_indicator_words_with_level_suffix() -> None:
    for field, display in [
        ("aprobaci_n_transici_n", "Aprobación_Transición"),
        ("reprobaci_n_media", "Reprobación_Media"),
        ("repitencia_primaria", "Repitencia_Primaria"),
        ("deserci_n_secundaria", "Deserción_Secundaria"),
    ]:
        description = "Indicador educativo agregado por municipio"
        result = classify_column(field, display, description, FIXTURE)
        assert result.risk_level == "low", f"{field} deberia ser low"


def test_low_risk_institutional_metric() -> None:
    result = classify_column(
        "sedes_conectadas_a_internet",
        "Sedes_Conectadas_A_Internet",
        "Porcentaje de sedes oficiales conectadas a internet",
        FIXTURE,
    )
    assert result.risk_level == "low"


def test_medium_risk_quasi_identifier() -> None:
    result = classify_column("salario_individual", None, None, FIXTURE)
    assert result.risk_level == "medium"


def test_unrecognized_column_defaults_to_unknown() -> None:
    result = classify_column("campo_raro_xyz_123", None, None, FIXTURE)
    assert result.risk_level == "unknown"


def test_reviewed_roadmap_column_is_scoped_to_dataset_and_exact_schema() -> None:
    reviewed = classify_column(
        "monto_aporte_en_usd",
        "MONTO APORTE EN USD",
        "Monto institucional de cooperación",
        FIXTURE,
        dataset_id="2d3i-f9wd",
    )
    other_dataset = classify_column(
        "monto_aporte_en_usd",
        "MONTO APORTE EN USD",
        "Monto sin contexto revisado",
        FIXTURE,
        dataset_id="otro-dataset",
    )
    changed_schema = classify_column(
        "monto_aporte_usd_nuevo",
        "MONTO APORTE USD NUEVO",
        None,
        FIXTURE,
        dataset_id="2d3i-f9wd",
    )

    assert reviewed.risk_level == "low"
    assert reviewed.matched_pattern_id == "reviewed_dataset:2d3i-f9wd"
    assert other_dataset.risk_level == "unknown"
    assert changed_schema.risk_level == "unknown"


def test_high_signal_wins_over_reviewed_roadmap_column() -> None:
    result = classify_column(
        "nombre_del_actor",
        "NOMBRE DEL ACTOR",
        "Número de identificación personal del actor",
        FIXTURE,
        dataset_id="2d3i-f9wd",
    )

    assert result.risk_level == "high"


def test_roadmap_person_name_and_identifier_columns_are_high() -> None:
    for field_name in ("primer_nombre_declarante_pn", "segundo_apellido", "numero_identificacion"):
        result = classify_column(field_name, None, None, FIXTURE, dataset_id="c82u-588k")
        assert result.risk_level == "high", field_name


def test_non_personal_site_identifier_is_not_misclassified_as_personal() -> None:
    result = classify_column(
        "nusd",
        "NUSD",
        "Número único de identificación del sitio de disposición final",
        FIXTURE,
        dataset_id="84tn-nnhf",
    )

    assert result.risk_level == "low"


def test_description_can_trigger_classification() -> None:
    result = classify_column("valor", None, "Historia clinica del paciente", FIXTURE)
    assert result.risk_level == "high"


def test_high_risk_description_overrides_low_looking_field_name() -> None:
    """El orden high -> medium -> low no debe romperse: una descripcion de
    alto riesgo debe ganarle a un field_name que por si solo calificaria low."""
    result = classify_column("municipio", "Municipio", "Domicilio y cedula del paciente", FIXTURE)
    assert result.risk_level == "high"


def test_low_risk_bare_etc_code() -> None:
    result = classify_column("etc", "ETC", "Nombre de la Entidad Territorial Certificada", FIXTURE)
    assert result.risk_level == "low"


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


def test_nomina_dataset_keyword_does_not_match_denominaba() -> None:
    columns = [ColumnPiiClassification(risk_level="low")]
    result = classify_dataset(
        columns,
        "Temperatura ambiente del aire",
        "Anteriormente este conjunto de datos se denominaba datos hidrometeorológicos",
        "Ambiente",
        FIXTURE,
    )

    assert result.risk_level == "low"
