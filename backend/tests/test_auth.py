def test_login_success(client, seeded_doctor):
    response = client.post(
        "/api/auth/login",
        json={"username": "doctor01", "password": "secret123", "role": "DOCTOR"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "DOCTOR"
    assert "access_token" in body


def test_login_wrong_password(client, seeded_doctor):
    response = client.post(
        "/api/auth/login",
        json={"username": "doctor01", "password": "wrong", "role": "DOCTOR"},
    )
    assert response.status_code == 401


def test_login_role_mismatch_is_rejected(client, seeded_doctor):
    """A user whose real role is DOCTOR must not log in by selecting ADMIN."""
    response = client.post(
        "/api/auth/login",
        json={"username": "doctor01", "password": "secret123", "role": "ADMIN"},
    )
    assert response.status_code == 401


def test_me_requires_token(client, seeded_doctor):
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_me_returns_current_user(client, seeded_doctor):
    login = client.post(
        "/api/auth/login",
        json={"username": "doctor01", "password": "secret123", "role": "DOCTOR"},
    )
    token = login.json()["access_token"]
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["username"] == "doctor01"
