from __future__ import annotations

from datetime import UTC, datetime

from app.agent.runner import _add_months


def test_add_months_preserves_calendar_retention_at_month_end() -> None:
    value = datetime(2026, 1, 31, 12, 0, tzinfo=UTC)

    assert _add_months(value, 1) == datetime(2026, 2, 28, 12, 0, tzinfo=UTC)
    assert _add_months(value, 24) == datetime(2028, 1, 31, 12, 0, tzinfo=UTC)
