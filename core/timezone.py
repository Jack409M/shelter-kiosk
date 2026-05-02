from core.time_utils import to_chicago


def to_chicago_time(value: str | None) -> str:
    if not value:
        return "—"

    dt = to_chicago(value)
    if not dt:
        return value

    return dt.strftime("%m/%d/%Y %I:%M %p")
