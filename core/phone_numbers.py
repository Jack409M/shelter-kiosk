from __future__ import annotations


def phone_digits(value: object | None) -> str:
    """Return only numeric digits from a phone value."""
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def normalize_phone_10(value: object | None) -> str | None:
    """
    Normalize a US phone number to the locked database format.

    Stored format: 8065551234
    Accepts punctuation, spaces, parentheses, and an optional leading 1.
    Returns None when the value cannot become exactly 10 digits.
    """
    digits = phone_digits(value)

    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]

    if len(digits) == 10:
        return digits

    return None


def normalize_optional_phone_10(value: object | None) -> str | None:
    """Normalize a blankable phone field to 10 digits or None."""
    if not phone_digits(value):
        return None
    return normalize_phone_10(value)


def phone_has_value(value: object | None) -> bool:
    """Return True when a phone field contains any digits."""
    return bool(phone_digits(value))


def format_phone_display(value: object | None) -> str:
    """Render a stored 10 digit phone number as (806) 555-1234."""
    normalized = normalize_phone_10(value)
    if not normalized:
        return ""
    return f"({normalized[0:3]}) {normalized[3:6]}-{normalized[6:10]}"
