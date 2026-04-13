import csv
from pathlib import Path

MAPPING_FILE = Path("docs/dwc_jotform_to_dataset_mapping.csv")


class FormMappingEngine:
    def __init__(self, mapping_file: Path | None = None):
        self.mapping_file = mapping_file or MAPPING_FILE
        self.mappings = self._load_mapping()

    def _load_mapping(self) -> list[dict[str, str]]:
        if not self.mapping_file.exists():
            raise FileNotFoundError(f"Mapping file not found: {self.mapping_file}")

        with self.mapping_file.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return [row for row in reader]

    def get_updates(self, form_name: str, submission_data: dict) -> list[dict[str, str]]:
        """
        Return safe dataset updates allowed by the mapping CSV.

        Expected CSV columns:
        - form_name
        - jotform_field_label
        - jotform_field_key
        - dataset_field
        - update_database
        - store_in_pdf_only
        - notes
        """

        updates: list[dict[str, str]] = []

        for mapping in self.mappings:
            if (mapping.get("form_name") or "").strip() != form_name:
                continue

            if (mapping.get("update_database") or "").strip().lower() != "yes":
                continue

            field_key = (mapping.get("jotform_field_key") or "").strip()
            dataset_field = (mapping.get("dataset_field") or "").strip()

            if not field_key or not dataset_field:
                continue

            if field_key not in submission_data:
                continue

            value = submission_data[field_key]

            if value in (None, ""):
                continue

            updates.append(
                {
                    "dataset_field": dataset_field,
                    "value": value,
                }
            )

        return updates
