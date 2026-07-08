import pytest

from app.quality.eligibility import compute_column_eligibility, compute_dataset_eligibility

PUBLISHER_STATUSES = ["verified", "unknown", "private_or_non_official"]
PII_LEVELS = ["low", "medium", "high", "unknown"]


def _expected_status(publisher_status: str, pii_risk_level: str, api_active: bool) -> str:
    if not api_active or pii_risk_level in ("unknown", "high"):
        return "blocked"
    if publisher_status != "verified":
        return "diagnostic_only"
    return "eligible"


@pytest.mark.parametrize("publisher_status", PUBLISHER_STATUSES)
@pytest.mark.parametrize("pii_risk_level", PII_LEVELS)
@pytest.mark.parametrize("api_active", [True, False])
def test_eligibility_matrix(publisher_status: str, pii_risk_level: str, api_active: bool) -> None:
    result = compute_dataset_eligibility(publisher_status, pii_risk_level, api_active)

    expected = _expected_status(publisher_status, pii_risk_level, api_active)
    assert result.eligibility_status == expected


def test_verified_low_pii_active_is_eligible_with_no_reasons() -> None:
    result = compute_dataset_eligibility("verified", "low", True)

    assert result.eligibility_status == "eligible"
    assert result.eligibility_reasons == []


def test_medium_pii_is_eligible_with_aggregation_reason() -> None:
    result = compute_dataset_eligibility("verified", "medium", True)

    assert result.eligibility_status == "eligible"
    assert result.eligibility_reasons == ["pii_medium_requires_aggregation"]


def test_unverified_publisher_is_diagnostic_only_not_blocked() -> None:
    result = compute_dataset_eligibility("unknown", "low", True)

    assert result.eligibility_status == "diagnostic_only"
    assert result.eligibility_reasons == ["publisher_unknown"]


def test_private_publisher_reason() -> None:
    result = compute_dataset_eligibility("private_or_non_official", "low", True)

    assert result.eligibility_status == "diagnostic_only"
    assert result.eligibility_reasons == ["publisher_private"]


def test_pii_unknown_blocks_even_with_verified_publisher() -> None:
    result = compute_dataset_eligibility("verified", "unknown", True)

    assert result.eligibility_status == "blocked"
    assert result.eligibility_reasons == ["pii_unknown"]


def test_pii_high_blocks() -> None:
    result = compute_dataset_eligibility("verified", "high", True)

    assert result.eligibility_status == "blocked"
    assert result.eligibility_reasons == ["pii_high"]


def test_inactive_api_blocks_even_with_everything_else_fine() -> None:
    result = compute_dataset_eligibility("verified", "low", False)

    assert result.eligibility_status == "blocked"
    assert result.eligibility_reasons == ["api_inactive"]


def test_multiple_reasons_all_accumulate() -> None:
    result = compute_dataset_eligibility("unknown", "high", False)

    assert result.eligibility_status == "blocked"
    assert set(result.eligibility_reasons) == {"api_inactive", "publisher_unknown", "pii_high"}


def test_blocked_takes_precedence_over_diagnostic_only() -> None:
    result = compute_dataset_eligibility("private_or_non_official", "unknown", True)

    assert result.eligibility_status == "blocked"
    assert set(result.eligibility_reasons) == {"publisher_private", "pii_unknown"}


def test_column_inherits_dataset_reasons_and_adds_its_own_pii() -> None:
    dataset_result = compute_dataset_eligibility("unknown", "low", True)

    column_result = compute_column_eligibility(dataset_result.eligibility_reasons, "high")

    assert column_result.eligibility_status == "blocked"
    assert set(column_result.eligibility_reasons) == {"publisher_unknown", "pii_high"}


def test_column_low_pii_but_dataset_publisher_unknown_stays_diagnostic_only() -> None:
    dataset_result = compute_dataset_eligibility("unknown", "low", True)

    column_result = compute_column_eligibility(dataset_result.eligibility_reasons, "low")

    assert column_result.eligibility_status == "diagnostic_only"
    assert column_result.eligibility_reasons == ["publisher_unknown"]
