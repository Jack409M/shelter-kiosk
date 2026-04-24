

def test_l9_refusal_flow_redirects_to_completion(client, db_session, test_resident):
    """
    Full flow:
    - Hit L9 disposition
    - Choose exit_now
    - Submit exit assessment
    - Verify redirect to l9_complete
    """

    resident_id = test_resident.id

    # Step 1: simulate hitting disposition and choosing refusal
    resp = client.post(
        f"/staff/case-management/{resident_id}/level9-disposition",
        data={
            "_csrf_token": "test",
            "disposition_action": "exit_now",
        },
        follow_redirects=False,
    )

    # Should redirect to exit assessment with from_l9=1
    assert resp.status_code == 302
    assert "exit-assessment" in resp.headers["Location"]

    # Step 2: submit exit assessment
    resp = client.post(
        f"/staff/case-management/{resident_id}/exit-assessment",
        data={
            "_csrf_token": "test",
            "date_exit_dwc": "2026-01-01",
            "exit_category": "Administrative Exit",
            "exit_reason": "Left by Choice",
            "graduate_dwc": "no",
            "leave_ama": "no",
        },
        follow_redirects=False,
    )

    # Step 3: verify redirect to completion page
    assert resp.status_code == 302
    assert f"/staff/case-management/{resident_id}/level9-complete" in resp.headers["Location"]
