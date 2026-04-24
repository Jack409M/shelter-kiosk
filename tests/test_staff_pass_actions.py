
# --- regression: legacy GET must not mutate ---

def test_legacy_get_routes_do_not_change_pass_state(app, client):
    from core.db import db_fetchone

    # minimal login
    with client.session_transaction() as s:
        s["staff_user_id"] = 1
        s["username"] = "staff"
        s["role"] = "case_manager"
        s["shelter"] = "abba"
        s["allowed_shelters"] = ["abba"]

    from core.runtime import init_db
    from core.db import db_execute, db_fetchone

    with app.app_context():
        init_db()
        db_execute("DELETE FROM resident_passes")
        db_execute("DELETE FROM residents")
        db_execute("INSERT INTO residents (resident_identifier,resident_code,first_name,last_name,shelter,is_active,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s)",("r1","c1","Jane","Resident","abba",True,"2026-01-01T00:00:00"))
        rid = db_fetchone("SELECT id FROM residents WHERE resident_identifier=%s",("r1",))["id"]
        db_execute("INSERT INTO resident_passes (resident_id,shelter,pass_type,status,start_at,end_at,destination,created_at,updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",(rid,"abba","pass","pending","2099-01-01T10:00:00","2099-01-01T18:00:00","Clinic","2026-01-01T00:00:00","2026-01-01T00:00:00"))
        pid = db_fetchone("SELECT id FROM resident_passes ORDER BY id DESC LIMIT 1")["id"]

    client.get(f"/staff/passes/approve/{pid}")
    client.get(f"/staff/passes/deny/{pid}")
    client.get(f"/staff/passes/check-in/{pid}")

    with app.app_context():
        row = db_fetchone("SELECT status FROM resident_passes WHERE id=%s",(pid,))

    assert row["status"] == "pending"
