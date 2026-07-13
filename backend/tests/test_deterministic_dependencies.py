import pytest

from app.agent.deterministic_dependencies import _column_type
from app.agent.query_plan import ColumnDataType


@pytest.mark.parametrize(
    ("catalog_type", "expected"),
    [
        ("Text", ColumnDataType.TEXT),
        ("Number", ColumnDataType.NUMBER),
        ("Calendar date", ColumnDataType.DATE),
        ("Floating timestamp", ColumnDataType.DATETIME),
        ("calendar_date", ColumnDataType.DATE),
        ("Point", ColumnDataType.LOCATION),
    ],
)
def test_column_type_normalizes_real_socrata_catalog_labels(
    catalog_type: str,
    expected: ColumnDataType,
) -> None:
    assert _column_type(catalog_type) is expected
