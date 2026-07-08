from datetime import date

from app.db.publishers import is_publisher_valid_for_reference_date


def test_active_publisher_is_always_valid() -> None:
    assert is_publisher_valid_for_reference_date(True, None, None, date(2020, 1, 1)) is True
    assert (
        is_publisher_valid_for_reference_date(
            True, date(2030, 1, 1), date(2031, 1, 1), date(2020, 1, 1)
        )
        is True
    )


def test_inactive_publisher_without_range_is_always_valid() -> None:
    assert is_publisher_valid_for_reference_date(False, None, None, date(2020, 1, 1)) is True


def test_inactive_publisher_before_valid_from_is_invalid() -> None:
    assert (
        is_publisher_valid_for_reference_date(False, date(2020, 1, 1), None, date(2019, 12, 31))
        is False
    )


def test_inactive_publisher_after_valid_until_is_invalid() -> None:
    assert (
        is_publisher_valid_for_reference_date(False, None, date(2020, 12, 31), date(2021, 1, 1))
        is False
    )


def test_inactive_publisher_inside_range_is_valid() -> None:
    assert (
        is_publisher_valid_for_reference_date(
            False, date(2015, 1, 1), date(2020, 12, 31), date(2018, 6, 1)
        )
        is True
    )


def test_inactive_publisher_on_boundary_dates_is_valid() -> None:
    assert (
        is_publisher_valid_for_reference_date(
            False, date(2015, 1, 1), date(2020, 12, 31), date(2015, 1, 1)
        )
        is True
    )
    assert (
        is_publisher_valid_for_reference_date(
            False, date(2015, 1, 1), date(2020, 12, 31), date(2020, 12, 31)
        )
        is True
    )
