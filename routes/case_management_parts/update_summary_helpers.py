from __future__ import annotations


def clean_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def join_non_empty(parts: list[str]) -> str:
    cleaned = [str(part).strip() for part in parts if part and str(part).strip()]
    return " | ".join(cleaned)


def normalize_detail(value) -> str | None:
    cleaned = clean_text(value)
    return cleaned or None


def normalize_key(value) -> str | None:
    cleaned = clean_text(value)
    return cleaned or None


def normalize_label(value) -> str | None:
    cleaned = clean_text(value)
    return cleaned or None


def display_snapshot_label(
    item_key: str,
    label_map: dict[str, str] | None,
    fallback_label: str,
) -> str:
    if label_map and item_key in label_map:
        return label_map[item_key]
    return fallback_label


def resolve_snapshot_change_type(old_value: str, new_value: str) -> str | None:
    if old_value == new_value:
        return None
    if old_value and not new_value:
        return "removed"
    if not old_value and new_value:
        return "added"
    return "updated"


def resolve_snapshot_item_label(
    item_key: str,
    change_type: str,
    label_map: dict[str, str] | None,
    added_label: str,
    removed_label: str,
    updated_label: str,
) -> str:
    if label_map:
        return display_snapshot_label(
            item_key=item_key,
            label_map=label_map,
            fallback_label=item_key,
        )

    if change_type == "added":
        return added_label or item_key
    if change_type == "removed":
        return removed_label or item_key
    return updated_label or item_key


def resolve_snapshot_detail(change_type: str, old_value: str, new_value: str) -> str | None:
    if change_type == "removed":
        return normalize_detail(old_value)
    return normalize_detail(new_value)
