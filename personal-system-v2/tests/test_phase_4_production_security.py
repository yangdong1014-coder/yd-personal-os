import importlib
import importlib.util
import logging
import re
import secrets
import sys
import threading
import time
from pathlib import Path

import pytest
from flask import Flask, g, session

import auth_service
import auth_repository
import config
import database
from conftest import extract_csrf_token


STRONG_TEST_SECRET = "K9vQ2mL7xR4cT8pN5wD3jH6sF1zB0yG8uC4aE7rM2kP9nV5q"
STRONG_PROXY_TOKEN = "R7wK4nT9pL2xV6cH1mQ8sD5fJ3zB0yG9uN4aE7rM2kP6vC8q"
RUNTIME_KEYS = (
    "PERSONAL_OS_ENV",
    "PERSONAL_OS_REMOTE",
    "PERSONAL_OS_BIND_HOST",
    "PERSONAL_OS_TRUSTED_HOSTS",
    "PERSONAL_OS_TRUSTED_PROXY",
    "PERSONAL_OS_PROXY_TOKEN",
    "YD_OS_DB_PATH",
    "SECRET_KEY",
    "FLASK_DEBUG",
)


def _clear_runtime(monkeypatch):
    for key in RUNTIME_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(config, "_PRODUCTION_PREFLIGHT_PATH", None)


def _production_env(monkeypatch, db_path, *, host="psy.example.test"):
    _clear_runtime(monkeypatch)
    monkeypatch.setenv("PERSONAL_OS_ENV", "production")
    monkeypatch.setenv("PERSONAL_OS_REMOTE", "1")
    monkeypatch.setenv("PERSONAL_OS_BIND_HOST", "127.0.0.1")
    monkeypatch.setenv("PERSONAL_OS_TRUSTED_HOSTS", host)
    monkeypatch.setenv("PERSONAL_OS_TRUSTED_PROXY", "127.0.0.1")
    monkeypatch.setenv("PERSONAL_OS_PROXY_TOKEN", STRONG_PROXY_TOKEN)
    monkeypatch.setenv("YD_OS_DB_PATH", str(Path(db_path).resolve()))
    monkeypatch.setenv("SECRET_KEY", STRONG_TEST_SECRET)


def _forwarded_environ(*, host="psy.example.test", client="203.0.113.9"):
    return {
        "REMOTE_ADDR": "127.0.0.1",
        "HTTP_X_FORWARDED_FOR": client,
        "HTTP_X_FORWARDED_PROTO": "https",
        "HTTP_X_FORWARDED_HOST": host,
        "HTTP_X_PSY_PROXY_TOKEN": STRONG_PROXY_TOKEN,
    }


def _make_production_app(monkeypatch, db_path):
    _production_env(monkeypatch, db_path)
    config.mark_production_preflight_complete(db_path)
    production_app = Flask("phase4-production")
    config.configure_flask_app(production_app)
    config.register_request_security(production_app)

    @production_app.get("/probe")
    def probe():
        return "ok"

    @production_app.get("/session-probe")
    def session_probe():
        session.clear()
        session["probe"] = "ok"
        session.permanent = True
        return "ok"

    return production_app


@pytest.mark.parametrize(
    "secret",
    [
        "short",
        "x" * 64,
        "replace_with_a_strong_random_value_123456789",
    ],
)
def test_weak_or_placeholder_production_secret_fails_closed(
    monkeypatch, tmp_path, secret
):
    _production_env(monkeypatch, tmp_path / "prod.db")
    monkeypatch.setenv("SECRET_KEY", secret)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        config.validate_production_safety()


@pytest.mark.parametrize(
    "hosts",
    ["", "*", ".example.test", "https://psy.example.test", "psy.example.test:443"],
)
def test_trusted_hosts_require_exact_names(monkeypatch, tmp_path, hosts):
    _production_env(monkeypatch, tmp_path / "prod.db")
    monkeypatch.setenv("PERSONAL_OS_TRUSTED_HOSTS", hosts)
    with pytest.raises(RuntimeError, match="TRUSTED_HOSTS"):
        config.validate_production_safety()


@pytest.mark.parametrize("proxy", ["*", "10.0.0.1", "127.0.0.0/8", "127.0.0.1,::1"])
def test_proxy_trust_requires_one_exact_loopback_peer(monkeypatch, tmp_path, proxy):
    _production_env(monkeypatch, tmp_path / "prod.db")
    monkeypatch.setenv("PERSONAL_OS_TRUSTED_PROXY", proxy)
    with pytest.raises(RuntimeError, match="TRUSTED_PROXY|loopback"):
        config.validate_production_safety()


def test_production_cookie_session_and_resource_limits(monkeypatch, tmp_path):
    production_app = _make_production_app(monkeypatch, tmp_path / "prod.db")

    assert production_app.config["SESSION_COOKIE_SECURE"] is True
    assert production_app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert production_app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert production_app.config["SESSION_REFRESH_EACH_REQUEST"] is False
    assert production_app.config["REMEMBER_COOKIE_SECURE"] is True
    assert production_app.config["REMEMBER_COOKIE_HTTPONLY"] is True
    assert production_app.config["REMEMBER_COOKIE_SAMESITE"] == "Lax"
    assert production_app.config["PERMANENT_SESSION_LIFETIME"].total_seconds() == 43200
    assert production_app.config["MAX_CONTENT_LENGTH"] == 16 * 1024 * 1024
    assert production_app.config["MAX_FORM_MEMORY_SIZE"] == 64 * 1024
    assert production_app.config["MAX_FORM_PARTS"] == 64
    assert production_app.config["TRUSTED_HOSTS"] == [
        "psy.example.test",
        "localhost",
        "127.0.0.1",
        "::1",
    ]


def test_direct_and_spoofed_forwarding_requests_are_rejected(monkeypatch, tmp_path):
    production_app = _make_production_app(monkeypatch, tmp_path / "prod.db")
    client = production_app.test_client()

    assert client.get("/probe", headers={"Host": "psy.example.test"}).status_code == 400

    spoofed = client.get(
        "/probe",
        headers={"Host": "psy.example.test"},
        environ_overrides={
            **_forwarded_environ(),
            "REMOTE_ADDR": "198.51.100.10",
        },
    )
    assert spoofed.status_code == 400

    loopback_without_proxy_token = client.get(
        "/probe",
        headers={"Host": "psy.example.test"},
        environ_overrides={
            key: value
            for key, value in _forwarded_environ().items()
            if key != "HTTP_X_PSY_PROXY_TOKEN"
        },
    )
    assert loopback_without_proxy_token.status_code == 400

    loopback_with_wrong_proxy_token = client.get(
        "/probe",
        headers={"Host": "psy.example.test"},
        environ_overrides={
            **_forwarded_environ(),
            "HTTP_X_PSY_PROXY_TOKEN": "wrong",
        },
    )
    assert loopback_with_wrong_proxy_token.status_code == 400

    multi_hop = client.get(
        "/probe",
        headers={"Host": "psy.example.test"},
        environ_overrides=_forwarded_environ(client="198.51.100.10, 203.0.113.9"),
    )
    assert multi_hop.status_code == 400

    wrong_proto = client.get(
        "/probe",
        headers={"Host": "psy.example.test"},
        environ_overrides={**_forwarded_environ(), "HTTP_X_FORWARDED_PROTO": "http"},
    )
    assert wrong_proto.status_code == 400

    remote_health = client.get(
        "/api/health",
        headers={"Host": "psy.example.test"},
        environ_overrides={"REMOTE_ADDR": "203.0.113.9"},
    )
    assert remote_health.status_code == 400


def test_hardened_health_allows_only_direct_loopback_probe(monkeypatch, tmp_path):
    production_app = _make_production_app(monkeypatch, tmp_path / "prod.db")

    @production_app.get("/api/health")
    def hardened_health():
        return {"ok": True, "data": {"status": "up"}}

    response = production_app.test_client().get(
        "/api/health",
        headers={"Host": "127.0.0.1"},
        environ_overrides={"REMOTE_ADDR": "127.0.0.1"},
    )
    assert response.status_code == 200
    assert response.get_json() == {"ok": True, "data": {"status": "up"}}


def test_valid_single_proxy_request_and_host_validation(monkeypatch, tmp_path):
    production_app = _make_production_app(monkeypatch, tmp_path / "prod.db")
    client = production_app.test_client()

    valid = client.get(
        "/probe",
        headers={"Host": "127.0.0.1"},
        environ_overrides=_forwarded_environ(),
    )
    assert valid.status_code == 200
    assert valid.get_data(as_text=True) == "ok"

    poisoned = client.get(
        "/probe",
        headers={"Host": "127.0.0.1"},
        environ_overrides=_forwarded_environ(host="evil.example"),
    )
    assert poisoned.status_code == 400


def test_hardened_session_cookie_flags_are_emitted(monkeypatch, tmp_path):
    production_app = _make_production_app(monkeypatch, tmp_path / "prod.db")
    response = production_app.test_client().get(
        "/session-probe",
        headers={"Host": "127.0.0.1"},
        environ_overrides=_forwarded_environ(),
    )
    cookie = response.headers["Set-Cookie"]
    assert "psy_session=" in cookie
    assert "Secure" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie
    assert "Expires=" in cookie


def test_health_is_minimal_and_security_headers_use_nonce(client):
    health = client.get("/api/health")
    assert health.get_json() == {"ok": True, "data": {"status": "up"}}
    assert health.headers["Cache-Control"] == "no-store"

    page = client.get("/")
    policy = page.headers["Content-Security-Policy"]
    nonce_match = re.search(r"script-src 'self' 'nonce-([^']+)'", policy)
    assert nonce_match
    nonce = nonce_match.group(1)
    markup = page.get_data(as_text=True)
    for tag in re.findall(r"<script(?![^>]*\bsrc=)[^>]*>", markup):
        assert f'nonce="{nonce}"' in tag
    assert "'unsafe-inline'" not in policy.split(";", 2)[1]
    assert page.headers["X-Frame-Options"] == "DENY"
    assert page.headers["X-Content-Type-Options"] == "nosniff"
    assert page.headers["Referrer-Policy"] == "same-origin"
    assert page.headers["Cross-Origin-Opener-Policy"] == "same-origin"
    assert page.headers["Cross-Origin-Resource-Policy"] == "same-origin"
    assert page.headers["X-Robots-Tag"].startswith("noindex")
    assert page.headers["X-Request-ID"]


def test_hardened_response_adds_hsts(monkeypatch, tmp_path):
    import app as app_module

    production_app = _make_production_app(monkeypatch, tmp_path / "prod.db")
    with production_app.test_request_context(
        "/probe", base_url="https://psy.example.test"
    ):
        g.csp_nonce = secrets.token_urlsafe(24)
        g.request_id = "phase4-test-request"
        g.source_fingerprint = "phase4-test-source"
        response = app_module.apply_security_headers(production_app.response_class("ok"))
    assert response.headers["Strict-Transport-Security"] == "max-age=31536000"


def test_oversized_json_is_rejected_before_handler(client, test_app):
    original = test_app.config["MAX_CONTENT_LENGTH"]
    test_app.config["MAX_CONTENT_LENGTH"] = 128
    try:
        response = client.post("/api/goals", json={"name": "x" * 512, "type": "年度"})
    finally:
        test_app.config["MAX_CONTENT_LENGTH"] = original
    assert response.status_code == 413
    assert response.get_json()["code"] == "request_too_large"


def test_login_rate_limit_is_source_based_and_does_not_echo_identifier(test_app):
    import app as app_module

    app_module._login_rate_limiter.reset()
    browser = test_app.test_client()
    source = {"REMOTE_ADDR": "203.0.113.41"}
    for index in range(config.LOGIN_RATE_LIMIT_ATTEMPTS):
        page = browser.get("/login", environ_overrides=source)
        response = browser.post(
            "/login",
            data={
                "identifier": f"rotating-user-{index}",
                "password": "wrong password",
                "csrf_token": extract_csrf_token(page),
            },
            environ_overrides=source,
        )
        assert response.status_code == 200

    page = browser.get("/login", environ_overrides=source)
    blocked = browser.post(
        "/login",
        data={
            "identifier": "sensitive-person@example.com",
            "password": "wrong password",
            "csrf_token": extract_csrf_token(page),
        },
        environ_overrides=source,
    )
    assert blocked.status_code == 429
    assert blocked.headers["Retry-After"]
    assert "sensitive-person@example.com" not in blocked.get_data(as_text=True)

    other_source = browser.get(
        "/login", environ_overrides={"REMOTE_ADDR": "203.0.113.42"}
    )
    assert other_source.status_code == 200


def _login_post(browser, *, source, identifier, password):
    environ = {"REMOTE_ADDR": source}
    page = browser.get("/login", environ_overrides=environ)
    return browser.post(
        "/login",
        data={
            "identifier": identifier,
            "password": password,
            "csrf_token": extract_csrf_token(page),
        },
        environ_overrides=environ,
    )


def test_single_source_cannot_lock_target_account(test_app):
    user = auth_service.bootstrap_admin(
        "dos-target", "dos-target@example.com", "correct target password"
    )
    browser = test_app.test_client()
    for _ in range(5):
        response = _login_post(
            browser,
            source="203.0.113.51",
            identifier=user["email"],
            password="wrong target password",
        )
        assert response.status_code == 200

    stored = auth_repository.get_user_by_id(user["id"])
    assert stored["failed_login_count"] == 1
    assert stored["locked_until"] is None

    success = _login_post(
        browser,
        source="203.0.113.51",
        identifier=user["email"],
        password="correct target password",
    )
    assert success.status_code == 302


def test_username_and_email_aliases_share_one_source_contribution(test_app):
    user = auth_service.bootstrap_admin(
        "alias-target", "alias-target@example.com", "correct alias password"
    )
    browser = test_app.test_client()
    for identifier in (user["username"], user["email"]):
        assert _login_post(
            browser,
            source="203.0.113.57",
            identifier=identifier,
            password="wrong alias password",
        ).status_code == 200
    assert auth_repository.get_user_by_id(user["id"])["failed_login_count"] == 1


def test_concurrent_same_source_contributes_only_once(test_app):
    user = auth_service.bootstrap_admin(
        "thread-target", "thread-target@example.com", "correct thread password"
    )
    barrier = threading.Barrier(10)
    failures = []

    def authenticate_wrong_password():
        barrier.wait()
        try:
            auth_service.authenticate(
                user["username"],
                "wrong thread password",
                failure_source="one-threaded-source",
            )
        except auth_service.AuthenticationError:
            failures.append(True)

    threads = [threading.Thread(target=authenticate_wrong_password) for _ in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(failures) == 10
    stored = auth_repository.get_user_by_id(user["id"])
    assert stored["failed_login_count"] == 1
    assert stored["locked_until"] is None


def test_source_limit_is_atomic_and_blocks_before_authentication(monkeypatch, test_app):
    import app as app_module

    limiter = app_module.LoginRateLimiter(attempts=10, window_seconds=60)
    barrier = threading.Barrier(20)
    results = []

    def consume():
        barrier.wait()
        results.append(limiter.consume_attempt("same-source", now=100.0))

    threads = [threading.Thread(target=consume) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results.count(0) == 10
    assert len([value for value in results if value == 60]) == 10

    browser = test_app.test_client()
    original_authenticate = auth_service.authenticate
    calls = []
    recorded_failures = []

    def measured_authenticate(*args, **kwargs):
        calls.append(args[0])
        return original_authenticate(*args, **kwargs)

    def record_failure_spy(*args, **kwargs):
        recorded_failures.append(args[0])

    monkeypatch.setattr(auth_service, "authenticate", measured_authenticate)
    monkeypatch.setattr(auth_repository, "record_login_failure", record_failure_spy)
    for index in range(config.LOGIN_RATE_LIMIT_ATTEMPTS):
        response = _login_post(
            browser,
            source="203.0.113.52",
            identifier=f"unknown-{index}",
            password="wrong password",
        )
        assert response.status_code == 200
    blocked = _login_post(
        browser,
        source="203.0.113.52",
        identifier="blocked-before-auth",
        password="wrong password",
    )
    assert blocked.status_code == 429
    assert len(calls) == config.LOGIN_RATE_LIMIT_ATTEMPTS
    assert recorded_failures == []


def test_unknown_and_real_accounts_share_generic_source_behavior(test_app):
    user = auth_service.bootstrap_admin(
        "known-target", "known-target@example.com", "correct target password"
    )
    browser = test_app.test_client()
    unknown = _login_post(
        browser,
        source="203.0.113.53",
        identifier="missing-target@example.com",
        password="wrong target password",
    )
    real = _login_post(
        browser,
        source="203.0.113.53",
        identifier=user["email"],
        password="wrong target password",
    )
    assert unknown.status_code == real.status_code == 200
    assert "用户名、邮箱或密码不正确" in unknown.get_data(as_text=True)
    assert "用户名、邮箱或密码不正确" in real.get_data(as_text=True)
    assert auth_repository.get_user_by_id(user["id"])["failed_login_count"] == 1


def test_normal_user_recovers_after_a_few_mistakes(test_app):
    user = auth_service.bootstrap_admin(
        "recover-user", "recover-user@example.com", "correct recovery password"
    )
    browser = test_app.test_client()
    for _ in range(3):
        assert _login_post(
            browser,
            source="203.0.113.54",
            identifier=user["username"],
            password="wrong recovery password",
        ).status_code == 200

    success = _login_post(
        browser,
        source="203.0.113.54",
        identifier=user["username"],
        password="correct recovery password",
    )
    assert success.status_code == 302
    stored = auth_repository.get_user_by_id(user["id"])
    assert stored["failed_login_count"] == 0
    assert stored["locked_until"] is None


def test_success_resets_account_contributions_but_not_source_failures(test_app):
    user = auth_service.bootstrap_admin(
        "reset-user", "reset-user@example.com", "correct reset password"
    )
    browser = test_app.test_client()
    for _ in range(9):
        assert _login_post(
            browser,
            source="203.0.113.55",
            identifier=user["username"],
            password="wrong reset password",
        ).status_code == 200

    assert _login_post(
        browser,
        source="203.0.113.55",
        identifier=user["username"],
        password="correct reset password",
    ).status_code == 302
    assert auth_repository.get_user_by_id(user["id"])["failed_login_count"] == 0

    with browser.session_transaction() as session_state:
        session_state.clear()
    tenth_failure = _login_post(
        browser,
        source="203.0.113.55",
        identifier=user["username"],
        password="wrong reset password",
    )
    assert tenth_failure.status_code == 200
    blocked = _login_post(
        browser,
        source="203.0.113.55",
        identifier=user["username"],
        password="wrong reset password",
    )
    assert blocked.status_code == 429

    other_source = _login_post(
        browser,
        source="203.0.113.56",
        identifier=user["username"],
        password="wrong reset password",
    )
    assert other_source.status_code == 200
    assert auth_repository.get_user_by_id(user["id"])["failed_login_count"] == 2


def test_five_distinct_sources_preserve_distributed_account_lock(test_app):
    user = auth_service.bootstrap_admin(
        "distributed-target",
        "distributed-target@example.com",
        "correct distributed password",
    )
    browser = test_app.test_client()
    for source_number in range(auth_service.MAX_FAILED_LOGINS):
        response = _login_post(
            browser,
            source=f"203.0.113.{100 + source_number}",
            identifier=user["username"],
            password="wrong distributed password",
        )
        assert response.status_code == 200

    stored = auth_repository.get_user_by_id(user["id"])
    assert stored["failed_login_count"] == auth_service.MAX_FAILED_LOGINS
    assert stored["locked_until"] is not None


def test_login_enumeration_errors_are_uniform(test_app):
    browser = test_app.test_client()
    active = auth_service.bootstrap_admin(
        "phase4admin", "phase4admin@example.com", "phase 4 admin password"
    )
    disabled, temporary = auth_service.create_standard_user(
        "phase4disabled", "phase4disabled@example.com"
    )
    auth_service.set_standard_user_active(disabled["id"], False)

    for identifier, password in (
        ("missing-user", "wrong password"),
        (active["username"], "wrong password"),
        (disabled["username"], temporary),
    ):
        page = browser.get("/login")
        response = browser.post(
            "/login",
            data={
                "identifier": identifier,
                "password": password,
                "csrf_token": extract_csrf_token(page),
            },
        )
        assert response.status_code == 200
        assert "用户名、邮箱或密码不正确" in response.get_data(as_text=True)


def test_login_enumeration_hash_work_is_comparable(monkeypatch, test_app):
    active = auth_service.bootstrap_admin(
        "phase4timing", "phase4timing@example.com", "phase 4 timing password"
    )
    disabled, temporary = auth_service.create_standard_user(
        "phase4timingdisabled", "phase4timingdisabled@example.com"
    )
    auth_service.set_standard_user_active(disabled["id"], False)

    original_check = auth_service.check_password_hash
    calls = []

    def measured_check(stored_hash, password):
        calls.append((stored_hash, password))
        return original_check(stored_hash, password)

    monkeypatch.setattr(auth_service, "check_password_hash", measured_check)
    for identifier, password in (
        ("missing-timing-user", "wrong password"),
        (active["username"], "wrong password"),
        (disabled["username"], temporary),
    ):
        before = len(calls)
        started = time.perf_counter()
        with pytest.raises(auth_service.AuthenticationError):
            auth_service.authenticate(identifier, password)
        assert time.perf_counter() - started < 5
        assert len(calls) == before + 1


def test_access_log_excludes_query_identity_and_secret(client, caplog):
    caplog.set_level(logging.INFO, logger="psy.access")
    secret_value = "do-not-log-this"
    response = client.get(
        f"/api/goals?token={secret_value}&email=person@example.com",
        environ_overrides={"REMOTE_ADDR": "203.0.113.77"},
    )
    assert response.status_code == 200
    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "endpoint=api_list_goals" in messages
    assert secret_value not in messages
    assert "person@example.com" not in messages
    assert "203.0.113.77" not in messages


def test_production_preflight_requires_explicit_current_database(
    tmp_path, monkeypatch
):
    import production

    _clear_runtime(monkeypatch)
    monkeypatch.setenv("PERSONAL_OS_ENV", "production")
    monkeypatch.setenv("PERSONAL_OS_REMOTE", "1")
    monkeypatch.setenv("PERSONAL_OS_TRUSTED_HOSTS", "psy.example.test")
    monkeypatch.setenv("PERSONAL_OS_TRUSTED_PROXY", "127.0.0.1")
    monkeypatch.setenv("PERSONAL_OS_PROXY_TOKEN", STRONG_PROXY_TOKEN)
    monkeypatch.setenv("SECRET_KEY", STRONG_TEST_SECRET)
    with pytest.raises(production.ProductionPreflightError, match="YD_OS_DB_PATH"):
        production.run_preflight(require_release_context=False)

    empty = tmp_path / "empty.db"
    empty.touch()
    monkeypatch.setenv("YD_OS_DB_PATH", str(empty))
    with pytest.raises(production.ProductionPreflightError, match="非空"):
        production.run_preflight(require_release_context=False)


def test_hardened_runtime_rejects_relative_database_and_debug(monkeypatch, tmp_path):
    _production_env(monkeypatch, tmp_path / "prod.db")
    monkeypatch.setenv("YD_OS_DB_PATH", "relative-production.db")
    with pytest.raises(RuntimeError, match="绝对路径"):
        config.validate_production_safety()

    monkeypatch.setenv("YD_OS_DB_PATH", str((tmp_path / "prod.db").resolve()))
    monkeypatch.setenv("FLASK_DEBUG", "1")
    with pytest.raises(RuntimeError, match="FLASK_DEBUG"):
        config.validate_production_safety()


def test_production_preflight_accepts_only_verified_v22_temp_database(
    tmp_path, monkeypatch
):
    import production

    db_path = tmp_path / "staged-v22.db"
    monkeypatch.setattr(database, "DB_PATH", str(db_path))
    database.init_db()
    auth_service.bootstrap_admin(
        "preflightadmin", "preflightadmin@example.com", "preflight admin password"
    )
    _production_env(monkeypatch, db_path)
    before_bytes = db_path.read_bytes()
    before_mtime = db_path.stat().st_mtime_ns

    report = production.run_preflight(require_release_context=False)
    assert report["schema_version"] == database.SCHEMA_USER_VERSION
    assert report["integrity_check"] == "ok"
    assert report["foreign_key_check_rows"] == 0
    assert report["active_admins"] == 1
    assert report["proxy_hops"] == 1
    assert db_path.read_bytes() == before_bytes
    assert db_path.stat().st_mtime_ns == before_mtime


def test_production_app_requires_preflight_authorization(monkeypatch, tmp_path):
    _production_env(monkeypatch, tmp_path / "prod.db")
    with pytest.raises(RuntimeError, match="只读预检"):
        config.configure_flask_app(Flask("bypass-production-entry"))


def test_flask_development_server_is_blocked_in_hardened_mode(
    monkeypatch, tmp_path
):
    _production_env(monkeypatch, tmp_path / "prod.db")
    with pytest.raises(SystemExit, match="active-release launcher"):
        config.get_server_run_options()


def test_production_gunicorn_factory_preflights_before_import(monkeypatch):
    import production

    events = []
    fake_app = Flask("gunicorn-contract")

    def fake_validate(app=None):
        events.append(("validate", app))

    def fake_preflight(*, require_release_context=True):
        assert require_release_context is True
        events.append(("preflight", None))

    monkeypatch.setitem(sys.modules, "app", type("FakeApp", (), {"app": fake_app}))
    monkeypatch.setattr(production, "run_preflight", fake_preflight)
    monkeypatch.setattr(config, "validate_production_safety", fake_validate)

    assert production.create_app() is fake_app
    assert events == [("preflight", None), ("validate", fake_app)]


def test_gunicorn_config_is_single_worker_preloaded_and_bounded(monkeypatch):
    monkeypatch.setenv("PERSONAL_OS_TRUSTED_PROXY", "127.0.0.1")
    config_path = Path(__file__).parents[1] / "gunicorn.conf.py"
    spec = importlib.util.spec_from_file_location("psy_gunicorn_config", config_path)
    gunicorn_config = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gunicorn_config)

    assert gunicorn_config.bind == "127.0.0.1:5000"
    assert gunicorn_config.workers == 1
    assert gunicorn_config.worker_class == "gthread"
    assert gunicorn_config.threads == 4
    assert gunicorn_config.preload_app is True
    assert gunicorn_config.reload is False
    assert gunicorn_config.accesslog is None
    assert gunicorn_config.control_socket_disable is True
    assert gunicorn_config.forwarded_allow_ips == "127.0.0.1"
    assert gunicorn_config.secure_scheme_headers == {
        "X-FORWARDED-PROTO": "https"
    }
    assert gunicorn_config.forwarder_headers == ""
    assert gunicorn_config.limit_request_line == 4094
    assert gunicorn_config.limit_request_fields == 64
    assert gunicorn_config.limit_request_field_size == 8190


def test_gunicorn_config_rejects_worker_or_bind_overrides(monkeypatch):
    monkeypatch.setenv("PERSONAL_OS_TRUSTED_PROXY", "127.0.0.1")
    config_path = Path(__file__).parents[1] / "gunicorn.conf.py"
    spec = importlib.util.spec_from_file_location("psy_gunicorn_guard", config_path)
    gunicorn_config = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gunicorn_config)

    class FakeConfig:
        bind = ["127.0.0.1:5000"]
        workers = 2
        worker_class_str = "gthread"
        threads = 4
        preload_app = True
        reload = False
        forwarded_allow_ips = ["127.0.0.1"]
        forwarder_headers = ""
        control_socket_disable = True

    fake_server = type("FakeServer", (), {"cfg": FakeConfig()})()
    with pytest.raises(RuntimeError, match="one Gunicorn worker"):
        gunicorn_config.on_starting(fake_server)

    fake_server.cfg.workers = 1
    fake_server.cfg.bind = ["0.0.0.0:5000"]
    with pytest.raises(RuntimeError, match="bind 127.0.0.1"):
        gunicorn_config.on_starting(fake_server)

    with pytest.raises(RuntimeError, match="one Gunicorn worker"):
        gunicorn_config.nworkers_changed(fake_server, 2, 1)


def _gunicorn_runtime_server(forwarded_allow_ips):
    class FakeConfig:
        bind = ["127.0.0.1:5000"]
        workers = 1
        worker_class_str = "gthread"
        threads = 4
        preload_app = True
        reload = False
        forwarder_headers = ""
        control_socket_disable = True

    cfg = FakeConfig()
    cfg.forwarded_allow_ips = forwarded_allow_ips
    return type("FakeServer", (), {"cfg": cfg})()


def test_gunicorn_on_starting_accepts_exact_forwarded_allow_ips_list(monkeypatch):
    monkeypatch.setenv("PERSONAL_OS_TRUSTED_PROXY", "127.0.0.1")
    config_path = Path(__file__).parents[1] / "gunicorn.conf.py"
    spec = importlib.util.spec_from_file_location(
        "psy_gunicorn_forwarded_allow_ips_pass", config_path
    )
    gunicorn_config = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gunicorn_config)

    gunicorn_config.on_starting(_gunicorn_runtime_server(["127.0.0.1"]))


@pytest.mark.parametrize(
    "forwarded_allow_ips",
    (
        ["127.0.0.1", "::1"],
        ["*"],
        ["8.8.8.8"],
        [],
        "127.0.0.1",
        "*",
    ),
)
def test_gunicorn_on_starting_rejects_non_exact_forwarded_allow_ips(
    monkeypatch, forwarded_allow_ips
):
    monkeypatch.setenv("PERSONAL_OS_TRUSTED_PROXY", "127.0.0.1")
    config_path = Path(__file__).parents[1] / "gunicorn.conf.py"
    spec = importlib.util.spec_from_file_location(
        "psy_gunicorn_forwarded_allow_ips_fail", config_path
    )
    gunicorn_config = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gunicorn_config)

    with pytest.raises(RuntimeError, match="forwarded_allow_ips must match the trusted proxy"):
        gunicorn_config.on_starting(_gunicorn_runtime_server(forwarded_allow_ips))
