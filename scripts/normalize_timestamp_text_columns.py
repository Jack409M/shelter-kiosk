from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.app_factory import create_app
from core.timestamp_normalization import normalize_timestamp_columns


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize timestamp text columns to UTC naive ISO format."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write normalized timestamp values. Without this flag, the script is a dry run.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    os.environ.setdefault("START_PASS_RETENTION_SCHEDULER", "0")
    app = create_app({"START_PASS_RETENTION_SCHEDULER": False})

    with app.app_context():
        result = normalize_timestamp_columns(apply=bool(args.apply))

    print(f"Discovered {result.columns_discovered} timestamp-like text columns.")

    for detail in result.details:
        if detail.would_update or detail.updated:
            action = "updated" if result.applied else "would update"
            count = detail.updated if result.applied else detail.would_update
            print(f"{detail.table_name}.{detail.column_name}: {action} {count} row(s)")

    if not result.applied:
        print("Dry run complete. No database changes were written.")

    print("Summary:")
    for key, value in result.as_dict().items():
        if key == "details":
            continue
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
