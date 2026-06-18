import pytest

import database


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(database, "DB_PATH", str(db_path))
    database.init_db()

    from app import app

    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client