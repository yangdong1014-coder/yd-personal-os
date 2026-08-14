import html
import os
import re

import pytest

# The insecure local runtime is an explicit test/development choice.
os.environ.setdefault("PERSONAL_OS_ENV", "development")

import auth_service
import database

_CSRF_PATTERNS = (
    re.compile(r'name="csrf-token" content="([^"]+)"'),
    re.compile(r'name="csrf_token" value="([^"]+)"'),
)


def extract_csrf_token(response):
    markup = response.get_data(as_text=True)
    for pattern in _CSRF_PATTERNS:
        match = pattern.search(markup)
        if match:
            return html.unescape(match.group(1))
    raise AssertionError("response did not include a CSRF token")


class AuthenticatedClient:
    """Test helper that uses a real login and supplies that session's CSRF token."""

    def __init__(self, raw_client, csrf_token, user_id):
        self.raw_client = raw_client
        self.csrf_token = csrf_token
        self.user_id = user_id

    def _write(self, method, *args, **kwargs):
        headers = dict(kwargs.pop("headers", {}) or {})
        headers.setdefault("X-CSRFToken", self.csrf_token)
        kwargs["headers"] = headers
        return getattr(self.raw_client, method)(*args, **kwargs)

    def get(self, *args, **kwargs):
        return self.raw_client.get(*args, **kwargs)

    def post(self, *args, **kwargs):
        return self._write("post", *args, **kwargs)

    def put(self, *args, **kwargs):
        return self._write("put", *args, **kwargs)

    def patch(self, *args, **kwargs):
        return self._write("patch", *args, **kwargs)

    def delete(self, *args, **kwargs):
        return self._write("delete", *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self.raw_client, name)


@pytest.fixture
def test_app(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(database, "DB_PATH", str(db_path))
    database.init_db()

    from app import app
    import app as app_module

    app.config.update(TESTING=True, WTF_CSRF_ENABLED=True)
    app_module._login_rate_limiter.reset()
    auth_service._account_failure_guard.reset()
    return app


@pytest.fixture
def unauthenticated_client(test_app):
    with test_app.test_client() as test_client:
        yield test_client


@pytest.fixture
def client(test_app):
    password = "test admin password"
    admin = auth_service.bootstrap_admin(
        "testadmin", "testadmin@example.com", password
    )

    with test_app.test_client() as test_client:
        login_page = test_client.get("/login")
        login_csrf = extract_csrf_token(login_page)
        response = test_client.post(
            "/login",
            data={
                "identifier": "testadmin",
                "password": password,
                "csrf_token": login_csrf,
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        csrf_token = extract_csrf_token(response)
        yield AuthenticatedClient(test_client, csrf_token, admin["id"])
