"""远程访问模式下的最小 token 鉴权。"""

import config
from flask import request

COOKIE_NAME = "personal_os_token"
HEADER_NAME = "X-Personal-OS-Token"
QUERY_PARAM = "token"
LOCAL_ADDRS = frozenset({"127.0.0.1", "::1"})


def is_local_request():
    addr = (request.remote_addr or "").strip()
    if addr not in LOCAL_ADDRS:
        return False
    forwarded = (request.headers.get("X-Forwarded-For") or "").strip()
    return not forwarded


def auth_required():
    if not config.is_remote_mode():
        return False
    return not is_local_request()


def extract_token():
    token = (request.args.get(QUERY_PARAM) or "").strip()
    if token:
        return token
    token = (request.headers.get(HEADER_NAME) or "").strip()
    if token:
        return token
    return (request.cookies.get(COOKIE_NAME) or "").strip()


def validate_token(token):
    expected = config.get_access_token()
    if not expected:
        return False
    return token == expected


def is_public_path():
    if request.path == "/api/health":
        return True
    if request.path.startswith("/static/"):
        return True
    return False


def token_from_query():
    return (request.args.get(QUERY_PARAM) or "").strip()