import html
import re

import pytest
from flask import Flask

import auth_repository
import auth_service
import config

STRONG_TEST_SECRET = "K9vQ2mL7xR4cT8pN5wD3jH6sF1zB0yG8uC4aE7rM2kP9nV5q"

_CSRF_PATTERNS = (
    re.compile(r'name="csrf-token" content="([^"]+)"'),
    re.compile(r'name="csrf_token" value="([^"]+)"'),
)


def csrf_from(response):
    markup = response.get_data(as_text=True)
    for pattern in _CSRF_PATTERNS:
        match = pattern.search(markup)
        if match:
            return html.unescape(match.group(1))
    raise AssertionError("response did not include a CSRF token")


def login(test_client, identifier, password, *, follow_redirects=False):
    login_page = test_client.get("/login")
    token = csrf_from(login_page)
    return test_client.post(
        "/login",
        data={
            "identifier": identifier,
            "password": password,
            "csrf_token": token,
        },
        follow_redirects=follow_redirects,
    )


def bootstrap_admin():
    password = "correct horse battery"
    admin = auth_service.bootstrap_admin("admin", "admin@example.com", password)
    return admin, password


def make_standard_user(username="person", email="person@example.com"):
    return auth_service.create_standard_user(username, email)


def change_temporary_password(test_client, temporary_password, new_password):
    response = login(
        test_client,
        "person",
        temporary_password,
        follow_redirects=True,
    )
    token = csrf_from(response)
    return test_client.post(
        "/change-password",
        data={
            "current_password": temporary_password,
            "new_password": new_password,
            "confirm_password": new_password,
            "csrf_token": token,
        },
        follow_redirects=True,
    )


def test_username_and_email_login_use_normalized_identity(unauthenticated_client):
    _, password = bootstrap_admin()

    username_login = login(unauthenticated_client, "ADMIN", password)
    assert username_login.status_code == 302
    assert username_login.headers["Location"] == "/"

    home = unauthenticated_client.get("/")
    token = csrf_from(home)
    unauthenticated_client.post(
        "/logout",
        data={"csrf_token": token},
    )

    email_login = login(unauthenticated_client, "ADMIN@EXAMPLE.COM", password)
    assert email_login.status_code == 302
    assert email_login.headers["Location"] == "/"


def test_wrong_identifier_or_password_does_not_authenticate(unauthenticated_client):
    _, password = bootstrap_admin()

    missing = login(unauthenticated_client, "missing", password)
    assert missing.status_code == 200
    assert "用户名、邮箱或密码不正确" in missing.get_data(as_text=True)

    wrong = login(unauthenticated_client, "admin", "incorrect password")
    assert wrong.status_code == 200
    assert "用户名、邮箱或密码不正确" in wrong.get_data(as_text=True)
    assert unauthenticated_client.get("/api/auth/me").status_code == 401


def test_unauthenticated_html_redirects_and_api_returns_401(unauthenticated_client):
    page = unauthenticated_client.get("/goals")
    assert page.status_code == 302
    assert page.headers["Location"].startswith("/login?next=/goals")

    api = unauthenticated_client.get("/api/goals")
    assert api.status_code == 401
    assert api.get_json()["code"] == "authentication_required"
    assert unauthenticated_client.get("/api/health").status_code == 200


def test_logout_clears_session_and_browser_cache(client):
    response = client.post("/logout")

    assert response.status_code == 302
    assert response.headers["Location"] == "/login"
    assert response.headers["Clear-Site-Data"] == '"cache", "storage"'
    assert client.get("/api/auth/me").status_code == 401


def test_disabled_user_cannot_login(unauthenticated_client):
    user, temporary_password = make_standard_user()
    auth_service.set_standard_user_active(user["id"], False)

    response = login(unauthenticated_client, "person", temporary_password)
    assert response.status_code == 200
    assert "用户名、邮箱或密码不正确" in response.get_data(as_text=True)


def test_disabling_logged_in_user_invalidates_session_on_next_request(test_app):
    admin, admin_password = bootstrap_admin()
    user, temporary_password = make_standard_user()
    admin_client = test_app.test_client()
    user_client = test_app.test_client()

    admin_home = login(admin_client, admin["username"], admin_password, follow_redirects=True)
    admin_csrf = csrf_from(admin_home)
    login(user_client, user["username"], temporary_password)
    assert user_client.get("/api/auth/me").status_code == 200

    disabled = admin_client.patch(
        f"/api/admin/users/{user['id']}/status",
        json={"is_active": False},
        headers={"X-CSRFToken": admin_csrf},
    )
    assert disabled.status_code == 200
    assert user_client.get("/api/auth/me").status_code == 401


def test_reset_password_invalidates_old_session_and_requires_change(test_app):
    admin, admin_password = bootstrap_admin()
    user, temporary_password = make_standard_user()
    admin_client = test_app.test_client()
    user_client = test_app.test_client()

    admin_home = login(admin_client, admin["username"], admin_password, follow_redirects=True)
    admin_csrf = csrf_from(admin_home)
    login(user_client, user["username"], temporary_password)

    reset = admin_client.post(
        f"/api/admin/users/{user['id']}/reset-password",
        json={},
        headers={"X-CSRFToken": admin_csrf},
    )
    assert reset.status_code == 200
    new_temporary_password = reset.get_json()["data"]["temporary_password"]
    assert user_client.get("/api/auth/me").status_code == 401

    relogin = login(user_client, "person", new_temporary_password)
    assert relogin.status_code == 302
    assert relogin.headers["Location"] == "/change-password"


def test_must_change_password_blocks_business_until_password_is_changed(test_app):
    make_standard_user()
    user_client = test_app.test_client()
    temporary_password = auth_service.reset_standard_user_password(1)[1]

    change_page = login(
        user_client,
        "person",
        temporary_password,
        follow_redirects=True,
    )
    assert change_page.request.path == "/change-password"
    assert user_client.get("/goals").headers["Location"] == "/change-password"
    blocked_api = user_client.get("/api/goals")
    assert blocked_api.status_code == 403
    assert blocked_api.get_json()["code"] == "password_change_required"

    token = csrf_from(change_page)
    changed = user_client.post(
        "/change-password",
        data={
            "current_password": temporary_password,
            "new_password": "a brand new secure password",
            "confirm_password": "a brand new secure password",
            "csrf_token": token,
        },
        follow_redirects=True,
    )
    assert changed.status_code == 200
    assert changed.request.path == "/"
    allowed_after_change = user_client.get("/api/goals")
    assert allowed_after_change.status_code == 200
    assert allowed_after_change.get_json()["data"] == []
    assert auth_repository.get_user_by_identifier("person")["must_change_password"] is False
    with user_client.session_transaction() as session_state:
        assert session_state.permanent is True


def test_standard_user_receives_403_for_admin_page_and_api(test_app):
    _, temporary_password = make_standard_user()
    user_client = test_app.test_client()
    changed = change_temporary_password(
        user_client,
        temporary_password,
        "a brand new secure password",
    )
    assert changed.status_code == 200

    api = user_client.get("/api/admin/users")
    assert api.status_code == 403
    assert api.get_json()["code"] == "admin_required"
    assert user_client.get("/admin/users").status_code == 403


def test_admin_can_manage_standard_users_but_cannot_create_admin(client):
    created = client.post(
        "/api/admin/users",
        json={"username": "newuser", "email": "newuser@example.com"},
    )
    assert created.status_code == 201
    payload = created.get_json()["data"]
    assert payload["user"]["role"] == "user"
    assert payload["user"]["must_change_password"] is True
    assert payload["temporary_password"]

    listed = client.get("/api/admin/users").get_json()["data"]
    listed_user = next(user for user in listed if user["id"] == payload["user"]["id"])
    assert "temporary_password" not in listed_user
    assert "password_hash" not in listed_user

    forbidden = client.post(
        "/api/admin/users",
        json={
            "username": "secondadmin",
            "email": "secondadmin@example.com",
            "role": "admin",
        },
    )
    assert forbidden.status_code == 400
    assert auth_repository.count_admins() == 1

    admin_id = next(user["id"] for user in listed if user["role"] == "admin")
    assert client.patch(
        f"/api/admin/users/{admin_id}/status",
        json={"is_active": False},
    ).status_code == 403
    assert client.post(
        f"/api/admin/users/{admin_id}/reset-password", json={}
    ).status_code == 403


def test_csrf_is_required_for_login_logout_and_existing_write_api(test_app):
    admin, password = bootstrap_admin()
    raw_client = test_app.test_client()

    missing_login_csrf = raw_client.post(
        "/login",
        data={"identifier": admin["username"], "password": password},
    )
    assert missing_login_csrf.status_code == 400

    home = login(raw_client, admin["username"], password, follow_redirects=True)
    csrf_token = csrf_from(home)
    missing_api_csrf = raw_client.post(
        "/api/goals",
        json={"name": "受保护目标", "type": "年度"},
    )
    assert missing_api_csrf.status_code == 400
    assert missing_api_csrf.get_json()["code"] == "csrf_failed"
    assert raw_client.post("/logout").status_code == 400

    valid = raw_client.post(
        "/api/goals",
        json={"name": "受保护目标", "type": "年度"},
        headers={"X-CSRFToken": csrf_token},
    )
    assert valid.status_code == 200


def test_login_rebuilds_session_and_does_not_store_credentials(test_app):
    admin, password = bootstrap_admin()
    raw_client = test_app.test_client()
    with raw_client.session_transaction() as session_data:
        session_data["attacker_marker"] = "fixed"

    login_page = raw_client.get("/login")
    cookie_before = raw_client.get_cookie("psy_session").value
    csrf_token = csrf_from(login_page)
    response = raw_client.post(
        "/login",
        data={
            "identifier": admin["username"],
            "password": password,
            "csrf_token": csrf_token,
        },
    )
    cookie_after = raw_client.get_cookie("psy_session").value

    assert response.status_code == 302
    assert cookie_after != cookie_before
    assert "HttpOnly" in response.headers.get("Set-Cookie", "")
    assert "SameSite=Lax" in response.headers.get("Set-Cookie", "")
    with raw_client.session_transaction() as session_data:
        assert "attacker_marker" not in session_data
        assert session_data["_user_id"] == str(admin["id"])
        assert session_data["auth_version"] == 1
        serialized = repr(dict(session_data))
        assert password not in serialized
        assert admin["email"] not in serialized
        assert admin["username"] not in serialized


def test_production_requires_secret_key_and_uses_secure_cookie(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "_PRODUCTION_PREFLIGHT_PATH", None)
    monkeypatch.setenv("PERSONAL_OS_ENV", "production")
    monkeypatch.delenv("PERSONAL_OS_REMOTE", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        config.configure_flask_app(Flask("missing-secret"))

    monkeypatch.setenv("SECRET_KEY", STRONG_TEST_SECRET)
    monkeypatch.setenv("PERSONAL_OS_REMOTE", "1")
    monkeypatch.setenv("YD_OS_DB_PATH", str(tmp_path / "secure.db"))
    monkeypatch.setenv("PERSONAL_OS_TRUSTED_HOSTS", "psy.example.test")
    monkeypatch.setenv("PERSONAL_OS_TRUSTED_PROXY", "127.0.0.1")
    monkeypatch.setenv(
        "PERSONAL_OS_PROXY_TOKEN",
        "R7wK4nT9pL2xV6cH1mQ8sD5fJ3zB0yG9uN4aE7rM2kP6vC8q",
    )
    config.mark_production_preflight_complete(tmp_path / "secure.db")
    production_app = Flask("secure-secret")
    config.configure_flask_app(production_app)
    assert production_app.config["SESSION_COOKIE_SECURE"] is True
    assert production_app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert production_app.config["SESSION_COOKIE_SAMESITE"] == "Lax"


def test_bootstrap_admin_cli_uses_hidden_input_and_runs_once(test_app):
    runner = test_app.test_cli_runner()
    password = "correct horse battery"
    result = runner.invoke(
        args=["bootstrap-admin"],
        input=f"bootstrap\nbootstrap@example.com\n{password}\n{password}\n",
    )
    assert result.exit_code == 0
    assert "管理员已初始化" in result.output
    assert password not in result.output

    second = runner.invoke(
        args=["bootstrap-admin"],
        input=f"other\nother@example.com\n{password}\n{password}\n",
    )
    assert second.exit_code != 0
    assert auth_repository.count_admins() == 1
