"""Chart availability for prose, without authorizing its UI-only measurements."""
from math import isfinite
from typing import Any, Mapping


def run_series_info(series: Mapping[str, Any]) -> dict[str, Any]:
    rows = series.get("rows")
    rows = rows if isinstance(rows, (list, tuple)) else ()
    valid = [
        row for row in rows
        if isinstance(row, Mapping)
        and isinstance(row.get("step"), int) and not isinstance(row.get("step"), bool)
        and any(
            isinstance(row.get(key), (int, float)) and not isinstance(row.get(key), bool)
            and isfinite(row[key])
            for key in ("input_rate", "scheduled_rate")
        )
    ]
    dates = sorted(str(row["date"]) for row in valid if isinstance(row.get("date"), str) and row["date"])
    def label(key: str) -> str | None:
        value = series.get(key)
        return value if isinstance(value, str) else None

    return {
        "available": bool(valid),
        "has_multiple_steps": len({row["step"] for row in valid}) > 1,
        "metric": label("metric"), "unit": label("unit"),
        "input_source": label("input_source"), "schedule_source": label("schedule_source"),
        "from_date": dates[0] if dates else None,
        "to_date": dates[-1] if dates else None,
    }
