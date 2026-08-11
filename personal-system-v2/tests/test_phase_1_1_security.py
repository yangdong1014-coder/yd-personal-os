import re
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from flask import Flask

import auth_repository
import auth_service
import config
import database
from conftest import extract_csrf_token


RUNTIME_ENV_KEYS = (
    "PERSONAL_OS_ENV",
    "PERSONAL_OS_REMOTE",
    "PERSONAL_OS_BIND_HOST",
    "PERSONAL_OS_BG",
    "SECRET_KEY",
)
PUBLIC_ENDPOINTS = {"login", "api_health", "service_worker", "static"}
IDENTITY_ENDPOINTS = {"change_password", "logout", "api_current_user"}


def _clear_runtime_environment(monkeypatch):
    for key in RUNTIME_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def _login(client, identifier, password):
    login_page = client.get("/login")
    return client.post(
        "/login",
        data={
            "identifier": identifier,
            "password": password,
            "csrf_token": extract_csrf_token(login_page),
        },
    )


def _login_standard_user(test_app):
    user, temporary_password = auth_service.create_standard_user(
        "phase11user", "phase11@example.com"
    )
    client = test_app.test_client()
    login_response = _login(client, user["username"], temporary_password)
    assert login_response.status_code == 302
    assert login_response.headers["Location"] == "/change-password"

    change_page = client.get("/change-password")
    changed = client.post(
        "/change-password",
        data={
            "current_password": temporary_password,
            "new_password": "phase 1.1 permanent password",
            "confirm_password": "phase 1.1 permanent password",
            "csrf_token": extract_csrf_token(change_page),
        },
    )
    assert changed.status_code == 302
    assert changed.headers["Location"] == "/"
    return client, user


def _concrete_path(rule):
    path = rule.rule
    for argument, converter in rule._converters.items():
        replacement = (
            "1" if converter.__class__.__name__ == "IntegerConverter" else "probe"
        )
        path = re.sub(
            rf"<(?:[^:<>]+:)?{re.escape(argument)}>", replacement, path
        )
    return path


def test_standard_user_is_centrally_denied_every_non_identity_route(test_app):
    client, _ = _login_standard_user(test_app)
    csrf_token = extract_csrf_token(client.get("/change-password"))
    denied = []

    for rule in test_app.url_map.iter_rules():
        if rule.endpoint in PUBLIC_ENDPOINTS | IDENTITY_ENDPOINTS:
            continue
        path = _concrete_path(rule)
        for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
            headers = {"X-CSRFToken": csrf_token} if method != "GET" else {}
            response = client.open(path, method=method, headers=headers)
            assert response.status_code == 403, (
                f"ordinary user unexpectedly reached {method} {path} "
                f"({rule.endpoint}): {response.status_code}"
            )
            if path.startswith("/api/"):
                expected_code = (
                    "admin_required"
                    if rule.endpoint == "admin_users_page"
                    or rule.endpoint.startswith("api_admin_")
                    else "business_access_pending"
                )
                assert response.get_json()["code"] == expected_code
            else:
                markup = response.get_data(as_text=True)
                assert "无权访问" in markup or "业务功能暂未开放" in markup
            denied.append((method, path))

    assert ("GET", "/") in denied
    assert ("GET", "/api/goals") in denied
    assert ("POST", "/api/goals") in denied
    assert ("GET", "/api/export") in denied
    assert len(denied) >= 40


def test_standard_user_identity_surface_and_required_static_remain_available(test_app):
    client, _ = _login_standard_user(test_app)

    assert client.get("/login").status_code == 302
    assert client.get("/change-password").status_code == 200
    assert client.get("/api/auth/me").status_code == 200
    assert client.get("/static/css/main.css").status_code == 200
    health = client.get("/api/health")
    assert health.status_code == 200
    assert set(health.get_json()["data"]) == {"status", "version", "remote_mode"}


def test_admin_keeps_current_business_access(client):
    assert client.get("/").status_code == 200
    assert client.get("/api/goals").status_code == 200
    assert client.get("/api/export").status_code == 200


def test_logout_revokes_copied_cookie_and_every_existing_session(test_app):
    admin = auth_service.bootstrap_admin(
        "logoutadmin", "logout@example.com", "logout replay test password"
    )
    first = test_app.test_client()
    second = test_app.test_client()
    assert _login(first, admin["username"], "logout replay test password").status_code == 302
    assert _login(second, admin["username"], "logout replay test password").status_code == 302

    copied_cookie = first.get_cookie("psy_session").value
    old_version = auth_repository.get_user_by_id(admin["id"])["auth_version"]
    home = first.get("/")
    logged_out = first.post(
        "/logout", data={"csrf_token": extract_csrf_token(home)}
    )

    assert logged_out.status_code == 302
    assert logged_out.headers["Clear-Site-Data"] == '"cache", "storage"'
    assert (
        auth_repository.get_user_by_id(admin["id"])["auth_version"]
        == old_version + 1
    )
    assert second.get("/api/auth/me").status_code == 401

    replay = test_app.test_client()
    replay.set_cookie("psy_session", copied_cookie)
    response = replay.get("/api/auth/me")
    assert response.status_code == 401
    assert response.get_json()["code"] == "authentication_required"


def test_production_missing_secret_key_fails_closed(monkeypatch):
    _clear_runtime_environment(monkeypatch)
    monkeypatch.setenv("PERSONAL_OS_ENV", "production")

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        config.configure_flask_app(Flask("production-missing-secret"))


def test_remote_missing_secret_key_fails_closed(monkeypatch):
    _clear_runtime_environment(monkeypatch)
    monkeypatch.setenv("PERSONAL_OS_REMOTE", "1")

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        config.configure_flask_app(Flask("remote-missing-secret"))


def test_unlabelled_runtime_cannot_silently_fall_back_to_development(monkeypatch):
    _clear_runtime_environment(monkeypatch)

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        config.configure_flask_app(Flask("unlabelled-runtime"))

    monkeypatch.setenv("SECRET_KEY", "u" * 48)
    unlabelled_app = Flask("unlabelled-with-secret")
    config.configure_flask_app(unlabelled_app)
    options = config.get_server_run_options(unlabelled_app)
    assert unlabelled_app.config["SESSION_COOKIE_SECURE"] is True
    assert options["debug"] is False
    assert options["use_reloader"] is False


def test_remote_with_secret_is_hardened_without_production_label(monkeypatch):
    _clear_runtime_environment(monkeypatch)
    monkeypatch.setenv("PERSONAL_OS_REMOTE", "1")
    monkeypatch.setenv("SECRET_KEY", "r" * 48)
    monkeypatch.setenv("PERSONAL_OS_BG", "0")
    remote_app = Flask("remote-with-secret")

    config.configure_flask_app(remote_app)
    options = config.get_server_run_options(remote_app)

    assert remote_app.config["SESSION_COOKIE_SECURE"] is True
    assert remote_app.debug is False
    assert options["debug"] is False
    assert options["use_reloader"] is False


def test_non_loopback_is_hardened_and_requires_explicit_remote_opt_in(monkeypatch):
    _clear_runtime_environment(monkeypatch)
    monkeypatch.setenv("PERSONAL_OS_BIND_HOST", "0.0.0.0")

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        config.configure_flask_app(Flask("non-loopback-missing-secret"))

    monkeypatch.setenv("SECRET_KEY", "n" * 48)
    with pytest.raises(RuntimeError, match="PERSONAL_OS_REMOTE"):
        config.configure_flask_app(Flask("non-loopback-no-opt-in"))

    monkeypatch.setenv("PERSONAL_OS_REMOTE", "1")
    exposed_app = Flask("non-loopback-hardened")
    config.configure_flask_app(exposed_app)
    options = config.get_server_run_options(exposed_app)
    assert exposed_app.config["SESSION_COOKIE_SECURE"] is True
    assert options["debug"] is False
    assert options["use_reloader"] is False


def test_normal_local_development_keeps_ephemeral_local_mode(monkeypatch):
    _clear_runtime_environment(monkeypatch)
    monkeypatch.setenv("PERSONAL_OS_ENV", "development")
    local_app = Flask("local-development")

    config.configure_flask_app(local_app)
    options = config.get_server_run_options(local_app)

    assert local_app.config["SECRET_KEY"]
    assert local_app.config["SESSION_COOKIE_SECURE"] is False
    assert options["host"] == "127.0.0.1"
    assert options["debug"] is True
    assert options["use_reloader"] is True

    monkeypatch.setenv("PERSONAL_OS_BG", "1")
    background_options = config.get_server_run_options(local_app)
    assert background_options["debug"] is False
    assert background_options["use_reloader"] is False


def test_normal_production_configuration_is_secure(monkeypatch):
    _clear_runtime_environment(monkeypatch)
    monkeypatch.setenv("PERSONAL_OS_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "p" * 48)
    monkeypatch.setenv("PERSONAL_OS_BG", "0")
    production_app = Flask("normal-production")

    config.configure_flask_app(production_app)
    options = config.get_server_run_options(production_app)

    assert production_app.config["SESSION_COOKIE_SECURE"] is True
    assert production_app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert production_app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert production_app.debug is False
    assert options["debug"] is False
    assert options["use_reloader"] is False


@pytest.mark.parametrize("background", ["0", "1"])
def test_python_app_run_path_never_enables_remote_debug(
    test_app, monkeypatch, background
):
    _clear_runtime_environment(monkeypatch)
    monkeypatch.setenv("PERSONAL_OS_REMOTE", "1")
    monkeypatch.setenv("SECRET_KEY", "s" * 48)
    monkeypatch.setenv("PERSONAL_OS_BG", background)

    import app as app_module

    server_app = Flask(f"server-entry-{background}")
    config.configure_flask_app(server_app)
    run_options = {}
    initialized = []
    monkeypatch.setattr(app_module, "app", server_app)
    monkeypatch.setattr(app_module.database, "init_db", lambda: initialized.append(True))
    monkeypatch.setattr(server_app, "run", lambda **kwargs: run_options.update(kwargs))

    app_module.run_server()

    assert initialized == [True]
    assert run_options["debug"] is False
    assert run_options["use_reloader"] is False


def test_hardened_app_rejects_late_cookie_or_debug_downgrade(monkeypatch):
    _clear_runtime_environment(monkeypatch)
    monkeypatch.setenv("PERSONAL_OS_REMOTE", "1")
    monkeypatch.setenv("SECRET_KEY", "h" * 48)
    hardened_app = Flask("downgrade-detection")
    config.configure_flask_app(hardened_app)

    hardened_app.config["SESSION_COOKIE_SECURE"] = False
    with pytest.raises(RuntimeError, match="SESSION_COOKIE_SECURE"):
        config.validate_production_safety(hardened_app)

    hardened_app.config["SESSION_COOKIE_SECURE"] = True
    hardened_app.debug = True
    with pytest.raises(RuntimeError, match="debug"):
        config.validate_production_safety(hardened_app)


def test_bootstrap_admin_is_atomic_under_concurrency(test_app):
    barrier = threading.Barrier(2)

    def attempt(index):
        barrier.wait(timeout=10)
        try:
            user = auth_service.bootstrap_admin(
                f"bootstrap{index}",
                f"bootstrap{index}@example.com",
                "atomic bootstrap password",
            )
            return "created", user["id"]
        except auth_service.ConflictError:
            return "conflict", None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, (1, 2)))

    assert sorted(result[0] for result in results) == ["conflict", "created"]
    assert auth_repository.count_admins() == 1
    with pytest.raises(auth_service.ConflictError, match="已经初始化"):
        auth_service.bootstrap_admin(
            "bootstrap3",
            "bootstrap3@example.com",
            "atomic bootstrap password",
        )


def test_pwa_only_caches_static_shell_and_deletes_every_legacy_cache(client):
    worker = client.get("/service-worker.js").get_data(as_text=True)

    assert 'psy-2-pwa-auth-shell-v2' in worker
    assert ".filter((key) => key !== CACHE_NAME)" in worker
    assert ".map((key) => caches.delete(key))" in worker
    assert 'request.mode === "navigate"' in worker
    assert 'request.destination === "document"' in worker
    assert 'url.pathname.startsWith("/api/")' in worker
    assert 'url.pathname.startsWith("/static/")' in worker
    assert '"/login"' not in worker
    assert 'cache.match("/")' not in worker


def test_bfcache_restore_revalidates_before_revealing_private_html(client):
    script = client.get("/static/js/main.js").get_data(as_text=True)

    assert 'window.addEventListener("pageshow", guardBackForwardCacheRestore)' in script
    assert "if (!event.persisted) return;" in script
    assert 'document.documentElement.style.visibility = "hidden"' in script
    assert 'fetch("/api/auth/me"' in script
    assert 'cache: "no-store"' in script
    assert 'window.location.replace("/login")' in script


def test_private_html_and_api_responses_are_never_cacheable(client):
    for path in ("/", "/api/goals", "/api/export", "/admin/users"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "no-store, private"
        assert response.headers["Pragma"] == "no-cache"
        assert "Cookie" in response.headers.get("Vary", "")


def test_phase_1_1_does_not_add_user_id_to_business_tables(test_app):
    conn = database.get_connection()
    try:
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
            if not row["name"].startswith("sqlite_")
        }
        assert "users" in tables
        for table in tables - {"users"}:
            columns = {
                row["name"]
                for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()
            }
            assert "user_id" not in columns, table
    finally:
        conn.close()
