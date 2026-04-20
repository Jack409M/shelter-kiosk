from routes.case_management_parts.budget_scoring import load_budget_score_snapshot

# inside promotion_review_view before render
    budget_score_snapshot = load_budget_score_snapshot(resident_id)

# pass into render_template
        budget_score_snapshot=budget_score_snapshot,
