from flask import Blueprint, request, jsonify
import json
from core.form_mapping_engine import FormMappingEngine

jotform_webhook = Blueprint(
    "jotform_webhook",
    __name__,
)

mapping_engine = FormMappingEngine()


@jotform_webhook.route("/webhooks/jotform", methods=["POST"])
def jotform_webhook_receiver():
    """
    Receives JotForm submissions and extracts safe dataset updates
    based on the mapping CSV.
    """

    try:
        raw_submission = request.form.get("rawRequest")

        if not raw_submission:
            return jsonify({"error": "missing rawRequest"}), 400

        submission = json.loads(raw_submission)

        form_name = submission.get("formTitle")

        submission_data = submission.get("answers", {})

        updates = mapping_engine.get_updates(
            form_name=form_name,
            submission_data=submission_data
        )

        # For now we just return what would update
        # Database write logic comes next

        return jsonify(
            {
                "status": "received",
                "form_name": form_name,
                "updates_detected": updates
            }
        )

    except Exception as e:
        return jsonify(
            {
                "status": "error",
                "message": str(e)
            }
        ), 500
