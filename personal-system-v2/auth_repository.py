"""SQLite repository for Phase 1 users and authentication state."""

import sqlite3
from datetime import datetime, timezone

import database


class BootstrapAdminExistsError(RuntimeError):
    """Raised when the one-time administrator bootstrap has already completed."""


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _user_from_row(row):
    if row is None:
        return None
    user = dict(row)
    user["is_active"] = bool(user["is_active"])
    user["must_change_password"] = bool(user["must_change_password"])
    return user


def get_user_by_id(user_id):
    conn = database.get_connection()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return _user_from_row(row)
    finally:
        conn.close()


def get_user_by_identifier(identifier):
    conn = database.get_connection()
    try:
        row = conn.execute(
            """
            SELECT * FROM users
            WHERE username = ? COLLATE NOCASE OR email = ? COLLATE NOCASE
            LIMIT 1
            """,
            (identifier, identifier),
        ).fetchone()
        return _user_from_row(row)
    finally:
        conn.close()


def get_user_by_username(username):
    conn = database.get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username,)
        ).fetchone()
        return _user_from_row(row)
    finally:
        conn.close()


def get_user_by_email(email):
    conn = database.get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ? COLLATE NOCASE", (email,)
        ).fetchone()
        return _user_from_row(row)
    finally:
        conn.close()


def count_admins():
    conn = database.get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM users WHERE role = 'admin'"
        ).fetchone()
        return int(row["count"])
    finally:
        conn.close()


def list_users():
    conn = database.get_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, username, email, role, is_active, must_change_password,
                   auth_version, failed_login_count, locked_until, last_login_at,
                   created_at, updated_at
            FROM users
            ORDER BY role = 'admin' DESC, username COLLATE NOCASE ASC
            """
        ).fetchall()
        return [_user_from_row(row) for row in rows]
    finally:
        conn.close()


def create_user(
    username,
    email,
    password_hash,
    *,
    role="user",
    is_active=True,
    must_change_password=False,
):
    now = _now()
    conn = database.get_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO users (
                username, email, password_hash, role, is_active,
                must_change_password, auth_version, failed_login_count,
                locked_until, last_login_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 1, 0, NULL, NULL, ?, ?)
            """,
            (
                username,
                email,
                password_hash,
                role,
                int(is_active),
                int(must_change_password),
                now,
                now,
            ),
        )
        database.ensure_default_capability_practice_steps(conn, cursor.lastrowid)
        created = conn.execute(
            "SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        conn.commit()
        return _user_from_row(created)
    except sqlite3.IntegrityError:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_bootstrap_admin(username, email, password_hash):
    """Atomically assert that no admin exists and create the bootstrap admin."""
    now = _now()
    conn = database.get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM users WHERE role = 'admin'"
        ).fetchone()
        if int(row["count"]):
            raise BootstrapAdminExistsError

        cursor = conn.execute(
            """
            INSERT INTO users (
                username, email, password_hash, role, is_active,
                must_change_password, auth_version, failed_login_count,
                locked_until, last_login_at, created_at, updated_at
            ) VALUES (?, ?, ?, 'admin', 1, 0, 1, 0, NULL, NULL, ?, ?)
            """,
            (username, email, password_hash, now, now),
        )
        database.ensure_default_capability_practice_steps(conn, cursor.lastrowid)
        created = conn.execute(
            "SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        conn.commit()
        return _user_from_row(created)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def clear_login_failures(user_id):
    conn = database.get_connection()
    try:
        conn.execute(
            """
            UPDATE users
            SET failed_login_count = 0, locked_until = NULL, updated_at = ?
            WHERE id = ?
            """,
            (_now(), user_id),
        )
        conn.commit()
    finally:
        conn.close()


def record_login_failure(user_id, lock_at_count, locked_until):
    conn = database.get_connection()
    try:
        conn.execute(
            """
            UPDATE users
            SET failed_login_count = failed_login_count + 1,
                locked_until = CASE
                    WHEN failed_login_count + 1 >= ? THEN ?
                    ELSE locked_until
                END,
                updated_at = ?
            WHERE id = ?
            """,
            (lock_at_count, locked_until, _now(), user_id),
        )
        conn.commit()
        return get_user_by_id(user_id)
    finally:
        conn.close()


def record_login_success(user_id):
    now = _now()
    conn = database.get_connection()
    try:
        conn.execute(
            """
            UPDATE users
            SET failed_login_count = 0, locked_until = NULL,
                last_login_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (now, now, user_id),
        )
        conn.commit()
        return get_user_by_id(user_id)
    finally:
        conn.close()


def update_password(user_id, password_hash, *, must_change_password):
    conn = database.get_connection()
    try:
        conn.execute(
            """
            UPDATE users
            SET password_hash = ?, must_change_password = ?,
                auth_version = auth_version + 1,
                failed_login_count = 0, locked_until = NULL, updated_at = ?
            WHERE id = ?
            """,
            (password_hash, int(must_change_password), _now(), user_id),
        )
        conn.commit()
        return get_user_by_id(user_id)
    finally:
        conn.close()


def increment_auth_version(user_id):
    """Revoke every signed client session for one account."""
    conn = database.get_connection()
    try:
        conn.execute(
            """
            UPDATE users
            SET auth_version = auth_version + 1, updated_at = ?
            WHERE id = ?
            """,
            (_now(), user_id),
        )
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        conn.commit()
        return _user_from_row(row)
    finally:
        conn.close()


def set_user_active(user_id, is_active):
    conn = database.get_connection()
    try:
        conn.execute(
            """
            UPDATE users
            SET is_active = ?, auth_version = auth_version + 1, updated_at = ?
            WHERE id = ?
            """,
            (int(is_active), _now(), user_id),
        )
        conn.commit()
        return get_user_by_id(user_id)
    finally:
        conn.close()
