from scrappystats.services.report_common import build_table_from_rows


def test_build_table_from_rows_tolerates_missing_and_extra_columns():
    columns = [
        {"key": "name", "label": "Name", "min_width": 4},
        {"key": "score", "label": "Score", "min_width": 5},
    ]
    rows = [
        {"name": "Alpha", "score": 10, "extra": "ignored"},
        {"name": "Beta"},
    ]

    table = build_table_from_rows(columns, rows)

    assert "Name" in table
    assert "Score" in table
