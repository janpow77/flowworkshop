"""Authentifizierungs- und Konto-Tests gegen das laufende System."""
from uuid import uuid4


def test_account_password_and_qr_flow(client):
    unique = uuid4().hex[:10]
    email = f"konto-{unique}@test.local"

    register = client.post("/api/event/register", json={
        "first_name": "Konto",
        "last_name": unique,
        "organization": "Testbehoerde",
        "email": email,
        "privacy_accepted": True,
    })
    assert register.status_code == 201

    login = client.post("/api/auth/login", json={"email": email})
    assert login.status_code == 200
    token = login.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    account = client.get("/api/auth/account", headers=headers)
    assert account.status_code == 200
    data = account.json()
    assert data["email"] == email
    assert data["qr_login_token"]
    assert data["qr_login_path"].startswith("/?qr=")
    assert data["has_password"] is False

    change = client.post("/api/auth/account/password", headers=headers, json={
        "new_password": "SicheresTestPwd!234",
    })
    assert change.status_code == 200
    assert change.json()["has_password"] is True

    email_only_login = client.post("/api/auth/login", json={"email": email})
    assert email_only_login.status_code == 401

    password_login = client.post("/api/auth/login", json={
        "email": email,
        "password": "SicheresTestPwd!234",
    })
    assert password_login.status_code == 200

    qr_login = client.post("/api/auth/qr-login", json={"token": data["qr_login_token"]})
    assert qr_login.status_code == 200

    generated = client.post("/api/auth/account/password/generate", headers=headers)
    assert generated.status_code == 200
    temporary_password = generated.json()["temporary_password"]
    assert len(temporary_password) >= 12

    temp_login = client.post("/api/auth/login", json={
        "email": email,
        "password": temporary_password,
    })
    assert temp_login.status_code == 200

    rotated = client.post("/api/auth/account/qr/rotate", headers=headers)
    assert rotated.status_code == 200
    rotated_data = rotated.json()
    assert rotated_data["qr_login_token"] != data["qr_login_token"]

    invalidated_old_qr = client.post("/api/auth/qr-login", json={"token": data["qr_login_token"]})
    assert invalidated_old_qr.status_code == 401
