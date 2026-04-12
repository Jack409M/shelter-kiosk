from __future__ import annotations


def _login_resident(client):
    with client.session_transaction() as session:
        session["resident_id"] = 1
        session["resident_identifier"] = "RID-1"
        session["resident_first"] = "Jane"
        session["resident_last"] = "Doe"
        session["resident_shelter"] = "abba"
        session["sms_consent_done"] = True


def _login_staff(client):
    with client.session_transaction() as session:
        session["staff_user_id"] = 1
        session["username"] = "admin"
        session["role"] = "admin"
        session["shelter"] = "abba"
        session["allowed_shelters"] = ["abba"]


# ----------------------------
# Resident → Staff boundary
# ----------------------------

def test_resident_cannot_access_staff_dashboard(client):
    _login_resident(client)

    response = client.get("/staff/admin/dashboard", follow_redirects=False)

    assert response.status_code in (301, 302)
    assert "/staff/login" in response.headers["Location"]


# ----------------------------
# Staff → Resident boundary
# ----------------------------

def test_staff_cannot_use_resident_transport(client):
    _login_staff(client)

    response = client.get("/transport", follow_redirects=False)

    # should be redirected to resident signin or blocked
    assert response.status_code in (301, 302)
    assert "/resident" in response.headers["Location"]


# ----------------------------
# Missing session safety
# ----------------------------

def test_transport_without_session_redirects_safely(client):
    response = client.get("/transport", follow_redirects=False)

    assert response.status_code in (301, 302)
    assert "/resident" in response.headers["Location"]


def test_partial_resident_session_is_rejected(client):
    # missing identifier
    with client.session_transaction() as session:
        session["resident_id"] = 1

    response = client.get("/transport", follow_redirects=False)

    assert response.status_code in (301, 302)
    assert "/resident" in response.headers["Location"]


# ----------------------------
# Session tampering resistance
# ----------------------------

def test_fake_resident_identifier_does_not_crash_or_grant_access(client):
    with client.session_transaction() as session:
        session["resident_identifier"] = "FAKE"
        session["resident_first"] = "Fake"
        session["resident_last"] = "User"
        session["resident_shelter"] = "abba"
        session["sms_consent_done"] = True

    response = client.get("/transport", follow_redirects=False)

    # must not 500 or allow access blindly
    assert response.status_code in (301, 302, 403)


def test_staff_session_missing_role_fails_safe(client):
    with client.session_transaction() as session:
        session["staff_user_id"] = 1
        # missing role intentionally

    response = client.get("/staff/admin/dashboard", follow_redirects=False)

    assert response.status_code in (301, 302)
    assert "/staff/login" in response.headers["Location"]
