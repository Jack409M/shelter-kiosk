import subprocess
import sys
from pathlib import Path

WIDTH_TOKEN = "field-width-"


def get_staged_files():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        capture_output=True,
        text=True,
        check=False,
    )
    return [Path(f) for f in result.stdout.splitlines()]


def is_template(file):
    return file.suffix in [".html", ".jinja", ".j2"]


def needs_check(content):
    return any(tag in content for tag in ["<input", "<select", "<textarea"])


def has_width(content):
    return WIDTH_TOKEN in content


def main():
    failed = []

    for file in get_staged_files():
        if not file.exists():
            continue

        if not is_template(file):
            continue

        content = file.read_text(errors="ignore")

        if needs_check(content) and not has_width(content):
            failed.append(str(file))

    if failed:
        print("\nField width rule violation:\n")
        for f in failed:
            print(f" - {f}")
        print("\nAdd field-width-* classes before committing.\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
