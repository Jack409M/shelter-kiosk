import csv
from pathlib import Path


MAPPING_FILE = Path("docs/dwc_jotform_to_dataset_mapping.csv")


class FormMappingEngine:
    def __init__(self):
        self.mappings = self._load_mapping()

    def _load_mapping(self):
        mappings = []

        if not MAPPING_FILE.exists():
            raise FileNotFoundError(f"Mapping file not found: {MAPPING_FILE}")

        with open(MAPPING_FILE, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                mappings.append(row)

        return mappings

    def get_updates(self, form_name, submission_data):
        """
        Returns a list of safe database updates based on the mapping file.
        """

        updates = []

        for mapping in self.mappings:

            if mapping["form_name"] != form_name:
                continue

            if mapping["update_database"].lower() != "yes":
                continue

            field_key = mapping["jotform_field_key"]

            if field_key not in submission_data:
                continue

            value = submission_data[field_key]

            updates.append(
                {
                    "table": mapping["dataset_table"],
                    "column": mapping["dataset_field"],
                    "value": value,
                }
            )

        return updates
