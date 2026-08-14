import hashlib
import hmac
import json
import logging
import os
import secrets
import threading
import time
from collections import defaultdict, deque
from functools import wraps
from urllib.parse import urlsplit

import click
from flask import (
    Flask,
    Response,
    current_app,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from flask_login import (
    LoginManager,
    current_user,
    login_required as flask_login_required,
    login_user,
    logout_user,
)
from flask_wtf.csrf import CSRFError, CSRFProtect
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

import ai_service
import asset_schemas
import auth_service
import changelog
import config
import database
import deliberation_service
import inbox_service
import obsidian_export
import positioning_service
import prompt_specs
import settings_store
from prompts import MODULES, PromptNotFoundError, list_prompts, read_raw, save as save_prompt

app = Flask(__name__)
config.configure_flask_app(app)
config.register_request_security(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.session_protection = "strong"
csrf = CSRFProtect()

_access_logger = logging.getLogger("psy.access")


class LoginRateLimiter:
    """Bounded in-process login-attempt limiter for the single WSGI process."""

    def __init__(self, *, attempts, window_seconds, max_sources=4096):
        self.attempts = attempts
        self.window_seconds = window_seconds
        self.max_sources = max_sources
        self._failures = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, failures, now):
        cutoff = now - self.window_seconds
        while failures and failures[0] <= cutoff:
            failures.popleft()

    def consume_attempt(self, source, *, now=None):
        current = time.monotonic() if now is None else now
        with self._lock:
            failures = self._failures[source]
            self._prune(failures, current)
            if len(failures) >= self.attempts:
                return max(
                    1,
                    int(self.window_seconds - (current - failures[0]) + 0.999),
                )
            failures.append(current)
            if len(self._failures) > self.max_sources:
                stale_sources = [
                    key
                    for key, values in self._failures.items()
                    if not values or values[-1] <= current - self.window_seconds
                ]
                for key in stale_sources:
                    self._failures.pop(key, None)
                while len(self._failures) > self.max_sources:
                    self._failures.pop(next(iter(self._failures)))
            return 0

    def release_success(self, source):
        """Refund only the current successful attempt, never prior failures."""
        with self._lock:
            failures = self._failures.get(source)
            if failures:
                failures.pop()
                if not failures:
                    self._failures.pop(source, None)

    def reset(self, source=None):
        with self._lock:
            if source is None:
                self._failures.clear()
            else:
                self._failures.pop(source, None)


_login_rate_limiter = LoginRateLimiter(
    attempts=config.LOGIN_RATE_LIMIT_ATTEMPTS,
    window_seconds=config.LOGIN_RATE_LIMIT_WINDOW_SECONDS,
)


@app.context_processor
def inject_globals():
    return {
        "ai_enabled": config.is_ai_enabled(),
        "current_version": changelog.get_current_version(),
        "nav_groups": NAV_GROUPS,
    }

NAV_ITEMS = [
    {"endpoint": "index", "label": "首页", "path": "/"},
    {"endpoint": "positioning", "label": "定位", "path": "/positioning"},
    {"endpoint": "goals", "label": "目标", "path": "/goals"},
    {"endpoint": "deliberations", "label": "推演", "path": "/deliberations"},
    {"endpoint": "opportunities", "label": "机会", "path": "/opportunities"},
    {"endpoint": "experiments", "label": "实验", "path": "/experiments"},
    {"endpoint": "feedback_page", "label": "反馈", "path": "/feedback"},
    {"endpoint": "tasks", "label": "项目 / 任务", "path": "/tasks"},
    {"endpoint": "reviews", "label": "复盘", "path": "/reviews"},
    {"endpoint": "assets", "label": "资产", "path": "/assets"},
    {"endpoint": "capabilities", "label": "能力", "path": "/capabilities"},
    {"endpoint": "inbox", "label": "智能归档", "path": "/inbox"},
    {"endpoint": "prompts", "label": "AI 管理 / 提示词", "path": "/prompts"},
    {"endpoint": "changelog", "label": "版本日志", "path": "/changelog"},
]

NAV_GROUPS = [
    {
        "label": "",
        "items": [
            {"endpoint": "index", "label": "首页", "path": "/"},
        ],
    },
    {
        "label": "战略层",
        "items": [
            {"endpoint": "positioning", "label": "定位", "path": "/positioning"},
            {"endpoint": "goals", "label": "目标", "path": "/goals"},
            {"endpoint": "deliberations", "label": "推演", "path": "/deliberations"},
        ],
    },
    {
        "label": "价值验证层",
        "items": [
            {"endpoint": "opportunities", "label": "机会", "path": "/opportunities"},
            {"endpoint": "experiments", "label": "实验", "path": "/experiments"},
            {"endpoint": "feedback_page", "label": "反馈", "path": "/feedback"},
        ],
    },
    {
        "label": "执行推进层",
        "items": [
            {"endpoint": "tasks", "label": "项目 / 任务", "path": "/tasks"},
            {"endpoint": "reviews", "label": "复盘", "path": "/reviews"},
        ],
    },
    {
        "label": "资产复利层",
        "items": [
            {"endpoint": "assets", "label": "资产", "path": "/assets"},
            {"endpoint": "capabilities", "label": "能力", "path": "/capabilities"},
        ],
    },
    {
        "label": "AI 工作台",
        "muted": True,
        "items": [
            {"endpoint": "inbox", "label": "智能归档", "path": "/inbox"},
            {"endpoint": "prompts", "label": "AI 管理 / 提示词", "path": "/prompts"},
        ],
    },
    {
        "label": "系统",
        "muted": True,
        "items": [
            {"endpoint": "changelog", "label": "版本日志", "path": "/changelog"},
        ],
    },
]


def _error(message, status=400, code=None):
    payload = {"ok": False, "error": message}
    if code:
        payload["code"] = code
    return jsonify(payload), status


def _business_value_error(exc, default_status=400):
    message = str(exc) or "参数无效"
    status = 404 if "不存在" in message else default_status
    return _error(message, status)


def _source_address():
    value = str(request.remote_addr or "").strip().strip("[]")
    try:
        from ipaddress import ip_address

        return str(ip_address(value))
    except ValueError:
        return "invalid"


def _source_fingerprint():
    return hmac.new(
        current_app.config["SECRET_KEY"].encode("utf-8"),
        _source_address().encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:16]


@app.before_request
def prepare_private_access_log():
    g.request_started_at = time.monotonic()
    g.request_id = secrets.token_hex(8)
    g.source_fingerprint = _source_fingerprint()


@app.errorhandler(RequestEntityTooLarge)
def handle_request_entity_too_large(_error_detail):
    message = "请求体过大"
    if _request_wants_json():
        return _error(message, 413, "request_too_large")
    return (
        render_template(
            "access_denied.html",
            error_title="请求过大",
            error_message=message,
        ),
        413,
    )


@app.errorhandler(Exception)
def handle_unexpected_error(exc):
    if isinstance(exc, RequestEntityTooLarge):
        return handle_request_entity_too_large(exc)
    if isinstance(exc, HTTPException):
        return exc
    current_app.logger.error(
        "request_failed request_id=%s endpoint=%s error_type=%s",
        getattr(g, "request_id", "unavailable"),
        request.endpoint or "unmatched",
        type(exc).__name__,
        exc_info=not current_app.config.get("PSY_HARDENED", False),
    )
    if _request_wants_json():
        return _error("服务器内部错误", 500, "internal_error")
    return (
        render_template(
            "access_denied.html",
            error_title="服务器内部错误",
            error_message="请求未能完成，请稍后重试。",
        ),
        500,
    )


def _request_wants_json():
    if request.path.startswith("/api/"):
        return True
    return request.accept_mimetypes.best_match(
        ["application/json", "text/html"]
    ) == "application/json"


def _unauthorized_response():
    if _request_wants_json():
        return _error("需要登录", 401, "authentication_required")
    next_path = request.full_path if request.query_string else request.path
    return redirect(url_for("login", next=next_path))


@login_manager.unauthorized_handler
def handle_unauthorized():
    return _unauthorized_response()


@login_manager.user_loader
def load_user(user_id):
    try:
        user = auth_service.get_user(int(user_id))
    except (TypeError, ValueError):
        return None
    if user is None or not user.is_active:
        return None
    if session.get("auth_version") != user.auth_version:
        return None
    return user


login_required = flask_login_required


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return _unauthorized_response()
        if not current_user.is_admin:
            if _request_wants_json():
                return _error("需要管理员权限", 403, "admin_required")
            return (
                render_template(
                    "access_denied.html",
                    error_title="无权访问",
                    error_message="该页面仅供系统管理员使用。",
                ),
                403,
            )
        return view(*args, **kwargs)

    return wrapped


PUBLIC_ENDPOINTS = frozenset({"login", "api_health", "service_worker", "static"})
IDENTITY_ONLY_ENDPOINTS = frozenset(
    {"change_password", "logout", "api_current_user"}
)


def _is_admin_endpoint(endpoint):
    return endpoint == "admin_users_page" or str(endpoint or "").startswith(
        "api_admin_"
    )


@app.before_request
def enforce_authenticated_user():
    if request.endpoint in PUBLIC_ENDPOINTS:
        return None
    if current_user.is_authenticated:
        if (
            current_user.must_change_password
            and request.endpoint not in IDENTITY_ONLY_ENDPOINTS
        ):
            if _request_wants_json():
                return _error(
                    "首次使用前必须修改密码",
                    403,
                    "password_change_required",
                )
            return redirect(url_for("change_password"))
        return None
    if session.get("_user_id") is not None:
        session.clear()
    return _unauthorized_response()


csrf.init_app(app)


@app.errorhandler(CSRFError)
def handle_csrf_error(_error_detail):
    message = "请求验证已失效，请刷新页面后重试"
    if _request_wants_json():
        return _error(message, 400, "csrf_failed")
    return (
        render_template(
            "access_denied.html",
            error_title="请求已失效",
            error_message=message,
        ),
        400,
    )


@app.after_request
def apply_security_headers(response):
    nonce = getattr(g, "csp_nonce", "")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    # Keep same-origin referrers so Flask-WTF can enforce its HTTPS origin
    # check, while never disclosing a private path to another origin.
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("X-XSS-Protection", "0")
    response.headers.setdefault(
        "Permissions-Policy",
        "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    )
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
    response.headers.setdefault("X-Robots-Tag", "noindex, nofollow, noarchive")
    if nonce:
        csp_directives = [
            "default-src 'self'",
            f"script-src 'self' 'nonce-{nonce}'",
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
            "font-src 'self' https://fonts.gstatic.com",
            "img-src 'self' data: blob:",
            "connect-src 'self'",
            "worker-src 'self'",
            "manifest-src 'self'",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",
        ]
        if current_app.config.get("PSY_HARDENED") is True:
            csp_directives.append("upgrade-insecure-requests")
        response.headers.setdefault(
            "Content-Security-Policy",
            "; ".join(csp_directives),
        )
    if current_app.config.get("PSY_HARDENED") is True and request.is_secure:
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000"
        )
    if request.endpoint == "api_health":
        response.headers["Cache-Control"] = "no-store"
    elif request.endpoint not in {"static", "service_worker"}:
        response.headers["Cache-Control"] = "no-store, private"
        response.headers["Pragma"] = "no-cache"
        response.headers.add("Vary", "Cookie")
    response.headers.setdefault("X-Request-ID", getattr(g, "request_id", ""))
    started_at = getattr(g, "request_started_at", None)
    duration_ms = (
        round((time.monotonic() - started_at) * 1000)
        if started_at is not None
        else -1
    )
    _access_logger.info(
        "request_complete request_id=%s endpoint=%s method=%s status=%s duration_ms=%s source=%s",
        getattr(g, "request_id", "unavailable"),
        request.endpoint or "unmatched",
        request.method,
        response.status_code,
        duration_ms,
        getattr(g, "source_fingerprint", "unavailable"),
    )
    return response


def _safe_next_path(candidate):
    candidate = str(candidate or "").strip()
    parsed = urlsplit(candidate)
    if (
        not candidate.startswith("/")
        or candidate.startswith("//")
        or parsed.scheme
        or parsed.netloc
        or parsed.path == "/login"
    ):
        return "/"
    return candidate


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        if current_user.must_change_password:
            return redirect(url_for("change_password"))
        return redirect(url_for("index"))

    error = None
    next_path = request.values.get("next", "")
    identifier = ""
    if request.method == "POST":
        source = _source_fingerprint()
        retry_after = _login_rate_limiter.consume_attempt(source)
        if retry_after:
            response = render_template(
                "login.html",
                error="登录尝试过多，请稍后重试",
                identifier="",
                next_path=next_path,
            )
            return response, 429, {"Retry-After": str(retry_after)}
        identifier = request.form.get("identifier", "").strip()
        try:
            user = auth_service.authenticate(
                identifier,
                request.form.get("password", ""),
                failure_source=source,
            )
        except auth_service.AuthenticationError as exc:
            error = str(exc)
        else:
            _login_rate_limiter.release_success(source)
            session.clear()
            login_user(user, remember=False, fresh=True)
            session.permanent = True
            session["auth_version"] = user.auth_version
            destination = (
                url_for("change_password")
                if user.must_change_password
                else _safe_next_path(next_path)
            )
            return redirect(destination)

    return render_template(
        "login.html",
        error=error,
        identifier=identifier,
        next_path=next_path,
    )


@app.post("/logout")
@login_required
def logout():
    auth_service.revoke_all_sessions(current_user.id)
    logout_user()
    session.clear()
    response = redirect(url_for("login"))
    response.headers["Clear-Site-Data"] = '"cache", "storage"'
    return response


@app.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    error = None
    if request.method == "POST":
        new_password = request.form.get("new_password", "")
        if new_password != request.form.get("confirm_password", ""):
            error = "两次输入的新密码不一致"
        else:
            try:
                user = auth_service.change_password(
                    current_user.id,
                    request.form.get("current_password", ""),
                    new_password,
                )
            except auth_service.AuthError as exc:
                error = str(exc)
            else:
                logout_user()
                session.clear()
                login_user(user, remember=False, fresh=True)
                session.permanent = True
                session["auth_version"] = user.auth_version
                return redirect(url_for("index"))
    return render_template(
        "change_password.html",
        active_page="change_password",
        error=error,
    )


@app.get("/api/auth/me")
@login_required
def api_current_user():
    return jsonify({"ok": True, "data": current_user.to_public_dict()})


@app.get("/admin/users")
@admin_required
def admin_users_page():
    return render_template(
        "admin_users.html",
        active_page="admin_users",
        users=auth_service.list_users(),
    )


@app.get("/api/admin/users")
@admin_required
def api_admin_list_users():
    return jsonify({"ok": True, "data": auth_service.list_users()})


@app.post("/api/admin/users")
@admin_required
def api_admin_create_user():
    payload = request.get_json(silent=True) or {}
    requested_role = payload.get("role", "user")
    if requested_role != "user":
        return _error("管理 API 只能创建普通用户", 400, "invalid_role")
    try:
        user, temporary_password = auth_service.create_standard_user(
            payload.get("username", ""),
            payload.get("email", ""),
        )
    except auth_service.ConflictError as exc:
        return _error(str(exc), 409)
    except auth_service.AuthError as exc:
        return _error(str(exc))
    return (
        jsonify(
            {
                "ok": True,
                "data": {
                    "user": user,
                    "temporary_password": temporary_password,
                },
            }
        ),
        201,
    )


@app.patch("/api/admin/users/<int:user_id>/status")
@admin_required
def api_admin_set_user_status(user_id):
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload.get("is_active"), bool):
        return _error("is_active 必须为布尔值")
    try:
        user = auth_service.set_standard_user_active(
            user_id,
            payload["is_active"],
        )
    except auth_service.AuthorizationError as exc:
        return _error(str(exc), 403)
    except auth_service.AuthError as exc:
        return _error(str(exc), 404)
    return jsonify({"ok": True, "data": user})


@app.post("/api/admin/users/<int:user_id>/reset-password")
@admin_required
def api_admin_reset_user_password(user_id):
    try:
        user, temporary_password = auth_service.reset_standard_user_password(user_id)
    except auth_service.AuthorizationError as exc:
        return _error(str(exc), 403)
    except auth_service.AuthError as exc:
        return _error(str(exc), 404)
    return jsonify(
        {
            "ok": True,
            "data": {
                "user": user,
                "temporary_password": temporary_password,
            },
        }
    )


@app.cli.command("bootstrap-admin")
def bootstrap_admin_command():
    """Create the one initial administrator using hidden password input."""
    database.init_db()
    username = click.prompt("管理员用户名").strip()
    email = click.prompt("管理员邮箱").strip()
    password = click.prompt(
        "管理员密码",
        hide_input=True,
        confirmation_prompt="再次输入管理员密码",
    )
    try:
        user = auth_service.bootstrap_admin(username, email, password)
    except auth_service.AuthError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"管理员已初始化：{user['username']} ({user['email']})")


@app.route("/api/health", methods=["GET"])
def api_health():
    return jsonify(
        {
            "ok": True,
            "data": {
                "status": "up",
            },
        }
    )


@app.route("/service-worker.js", methods=["GET"])
def service_worker():
    response = send_from_directory(
        app.static_folder,
        "service-worker.js",
        mimetype="application/javascript",
        max_age=0,
    )
    response.headers["Cache-Control"] = "no-cache"
    return response


@app.route("/")
def index():
    return render_template("index.html", active_page="index", nav_items=NAV_ITEMS)


@app.route("/opportunities")
def opportunities():
    return render_template(
        "opportunities.html",
        active_page="opportunities",
        nav_items=NAV_ITEMS,
        opportunity_statuses=database.OPPORTUNITY_STATUSES,
    )


@app.route("/deliberations")
def deliberations():
    return render_template(
        "deliberations.html",
        active_page="deliberations",
        nav_items=NAV_ITEMS,
    )


@app.route("/deliberations/new")
def new_deliberation():
    return render_template(
        "deliberation_new.html",
        active_page="deliberations",
        nav_items=NAV_ITEMS,
    )


@app.route("/deliberations/<int:deliberation_id>")
def deliberation_detail(deliberation_id):
    return render_template(
        "deliberation_detail.html",
        active_page="deliberations",
        nav_items=NAV_ITEMS,
        deliberation_id=deliberation_id,
    )


@app.route("/experiments")
def experiments():
    return render_template(
        "experiments.html",
        active_page="experiments",
        nav_items=NAV_ITEMS,
        experiment_types=database.EXPERIMENT_TYPES,
        experiment_statuses=database.EXPERIMENT_STATUSES,
    )


@app.route("/feedback")
def feedback_page():
    return render_template(
        "feedback.html",
        active_page="feedback_page",
        nav_items=NAV_ITEMS,
        feedback_sources=database.FEEDBACK_SOURCES,
        feedback_levels=database.FEEDBACK_LEVELS,
        feedback_related_types=database.FEEDBACK_RELATED_TYPES,
    )


@app.route("/positioning")
def positioning_page():
    return render_template(
        "positioning.html",
        active_page="positioning",
        nav_items=NAV_ITEMS,
        goal_types=database.GOAL_TYPES,
        positioning_cycles=database.POSITIONING_CYCLES,
        positioning_action_types=database.POSITIONING_ACTION_TYPES,
    )


@app.route("/goals")
def goals():
    return render_template(
        "goals.html",
        active_page="goals",
        nav_items=NAV_ITEMS,
        goal_types=database.GOAL_TYPES,
    )


@app.route("/tasks")
def tasks():
    return render_template(
        "tasks.html",
        active_page="tasks",
        nav_items=NAV_ITEMS,
        task_statuses=database.TASK_STATUSES,
    )


@app.route("/reviews")
def reviews():
    return render_template(
        "reviews.html",
        active_page="reviews",
        nav_items=NAV_ITEMS,
        review_types=database.REVIEW_TYPES,
        capability_modules=database.CAPABILITY_MODULES,
    )


@app.route("/assets")
def assets():
    return render_template(
        "assets.html",
        active_page="assets",
        nav_items=NAV_ITEMS,
        asset_types=database.ASSET_TYPES,
        maturity_levels=database.MATURITY_LEVELS,
        asset_levels=database.ASSET_LEVELS,
        asset_field_schemas=asset_schemas.get_frontend_schemas(),
        capability_modules=database.CAPABILITY_MODULES,
    )


@app.route("/capabilities")
def capabilities():
    return render_template(
        "capabilities.html",
        active_page="capabilities",
        nav_items=NAV_ITEMS,
        capability_modules=database.CAPABILITY_MODULES,
        capability_layers=database.CAPABILITY_LAYERS,
        level_types=database.LEVEL_TYPES,
    )


@app.route("/inbox")
def inbox_page():
    return render_template(
        "inbox.html",
        active_page="inbox",
        nav_items=NAV_ITEMS,
    )


@app.route("/inbox/history")
def inbox_history_page():
    return render_template(
        "inbox_history.html",
        active_page="inbox",
        nav_items=NAV_ITEMS,
    )


@app.route("/prompts")
def prompts_page():
    return render_template(
        "prompts.html",
        active_page="prompts",
        nav_items=NAV_ITEMS,
        prompt_modules=MODULES,
    )


@app.route("/changelog")
def changelog_page():
    return render_template(
        "changelog.html",
        active_page="changelog",
        nav_items=NAV_ITEMS,
        entries=changelog.list_entries(),
        current_version=changelog.get_current_version(),
    )


@app.route("/api/goals", methods=["GET"])
def api_list_goals():
    return jsonify({"ok": True, "data": database.list_goals(current_user.id)})


@app.route("/api/goals", methods=["POST"])
def api_create_goal():
    payload = request.get_json(silent=True) or {}
    try:
        goal = database.create_goal(
            payload.get("name", ""), payload.get("type", ""), current_user.id
        )
        return jsonify({"ok": True, "data": goal})
    except ValueError as exc:
        return _error(str(exc))


@app.route("/api/goals/<int:goal_id>", methods=["PATCH"])
def api_update_goal(goal_id):
    payload = request.get_json(silent=True) or {}
    try:
        goal = database.update_goal(goal_id, payload, current_user.id)
        return jsonify({"ok": True, "data": goal})
    except ValueError as exc:
        return _business_value_error(exc)


@app.route("/api/goals/<int:goal_id>", methods=["DELETE"])
def api_delete_goal(goal_id):
    try:
        result = database.delete_goal(goal_id, current_user.id)
        return jsonify({"ok": True, "data": result})
    except ValueError as exc:
        return _error(str(exc), 404)
    except database.DeleteError as exc:
        return _error(str(exc), 409)


@app.route("/api/deliberations", methods=["GET"])
def api_list_deliberations():
    return jsonify({
        "ok": True,
        "data": database.list_deliberations(current_user.id),
    })


@app.route("/api/deliberations", methods=["POST"])
def api_create_deliberation():
    payload = request.get_json(silent=True) or {}
    try:
        deliberation = database.create_deliberation(payload, current_user.id)
        return jsonify({"ok": True, "data": deliberation})
    except (ValueError, TypeError) as exc:
        return _error(str(exc) if str(exc) else "参数无效")


@app.route("/api/deliberations/<int:deliberation_id>", methods=["GET"])
def api_get_deliberation(deliberation_id):
    deliberation = database.get_deliberation(deliberation_id, current_user.id)
    if not deliberation:
        return _error("推演不存在", 404)
    return jsonify({"ok": True, "data": deliberation})


@app.route("/api/deliberations/<int:deliberation_id>", methods=["PATCH"])
def api_update_deliberation(deliberation_id):
    payload = request.get_json(silent=True) or {}
    try:
        deliberation = database.update_deliberation(
            deliberation_id, payload, current_user.id
        )
        return jsonify({"ok": True, "data": deliberation})
    except ValueError as exc:
        status = 404 if str(exc) == "推演不存在" else 400
        return _error(str(exc), status)


@app.route(
    "/api/deliberations/<int:deliberation_id>/analyze",
    methods=["POST"],
)
def api_analyze_deliberation(deliberation_id):
    try:
        deliberation = deliberation_service.analyze(
            deliberation_id, current_user.id
        )
        return jsonify({"ok": True, "data": deliberation})
    except deliberation_service.DeliberationServiceError as exc:
        status = 404 if str(exc) == "推演不存在" else 400
        return _error(str(exc), status)


@app.route(
    "/api/deliberations/<int:deliberation_id>/decision",
    methods=["PATCH"],
)
def api_save_deliberation_decision(deliberation_id):
    payload = request.get_json(silent=True) or {}
    try:
        deliberation = database.save_deliberation_decision(
            deliberation_id,
            payload,
            current_user.id,
        )
        return jsonify({"ok": True, "data": deliberation})
    except ValueError as exc:
        status = 404 if str(exc) == "推演不存在" else 400
        return _error(str(exc), status)


@app.route(
    "/api/deliberations/<int:deliberation_id>/review",
    methods=["PATCH"],
)
def api_save_deliberation_review(deliberation_id):
    payload = request.get_json(silent=True) or {}
    try:
        deliberation = database.save_deliberation_review(
            deliberation_id,
            payload,
            current_user.id,
        )
        return jsonify({"ok": True, "data": deliberation})
    except ValueError as exc:
        status = 404 if str(exc) == "推演不存在" else 400
        return _error(str(exc), status)


@app.route("/api/deliberations/<int:deliberation_id>", methods=["DELETE"])
def api_delete_deliberation(deliberation_id):
    try:
        result = database.delete_deliberation(deliberation_id, current_user.id)
        return jsonify({"ok": True, "data": result})
    except ValueError as exc:
        return _error(str(exc), 404)
    except database.DeleteError as exc:
        return _error(str(exc), 409)


@app.route("/api/projects", methods=["GET"])
def api_list_projects():
    goal_id = request.args.get("goal_id", type=int)
    return jsonify({
        "ok": True,
        "data": database.list_projects(current_user.id, goal_id),
    })


@app.route("/api/projects", methods=["POST"])
def api_create_project():
    payload = request.get_json(silent=True) or {}
    try:
        project = database.create_project(
            payload.get("goal_id"),
            payload.get("name", ""),
            payload.get("priority"),
            user_id=current_user.id,
        )
        return jsonify({"ok": True, "data": project})
    except (ValueError, TypeError) as exc:
        return _error(str(exc) if str(exc) else "参数无效")


@app.route("/api/projects/<int:project_id>", methods=["DELETE"])
def api_delete_project(project_id):
    try:
        result = database.delete_project(project_id, current_user.id)
        return jsonify({"ok": True, "data": result})
    except ValueError as exc:
        return _error(str(exc), 404)
    except database.DeleteError as exc:
        return _error(str(exc), 409)


@app.route("/api/projects/<int:project_id>", methods=["PATCH"])
def api_update_project(project_id):
    payload = request.get_json(silent=True) or {}
    try:
        project = database.update_project(project_id, payload, current_user.id)
        return jsonify({"ok": True, "data": project})
    except ValueError as exc:
        return _business_value_error(exc)


@app.route("/api/tasks", methods=["GET"])
def api_list_tasks():
    project_id = request.args.get("project_id", type=int)
    return jsonify({
        "ok": True,
        "data": database.list_tasks(current_user.id, project_id),
    })


@app.route("/api/tasks", methods=["POST"])
def api_create_task():
    payload = request.get_json(silent=True) or {}
    try:
        task = database.create_task(
            payload.get("project_id"),
            payload.get("name", ""),
            payload.get("priority"),
            user_id=current_user.id,
        )
        return jsonify({"ok": True, "data": task})
    except (ValueError, TypeError) as exc:
        return _error(str(exc) if str(exc) else "参数无效")


@app.route("/api/tasks/<int:task_id>/status", methods=["PATCH"])
def api_update_task_status(task_id):
    payload = request.get_json(silent=True) or {}
    try:
        task = database.update_task_status(
            task_id, payload.get("status", ""), current_user.id
        )
        return jsonify({"ok": True, "data": task})
    except ValueError as exc:
        return _business_value_error(exc)


@app.route("/api/tasks/<int:task_id>/today-progress", methods=["PATCH"])
def api_update_task_today_progress(task_id):
    payload = request.get_json(silent=True) or {}
    try:
        task = database.update_task_today_progress(
            task_id, bool(payload.get("enabled")), current_user.id
        )
        return jsonify({"ok": True, "data": task})
    except ValueError as exc:
        return _business_value_error(exc)


@app.route("/api/tasks/<int:task_id>", methods=["PATCH"])
def api_update_task(task_id):
    payload = request.get_json(silent=True) or {}
    try:
        task = database.update_task(task_id, payload, current_user.id)
        return jsonify({"ok": True, "data": task})
    except ValueError as exc:
        return _business_value_error(exc)


@app.route("/api/tasks/<int:task_id>", methods=["DELETE"])
def api_delete_task(task_id):
    try:
        result = database.delete_task(task_id, current_user.id)
        return jsonify({"ok": True, "data": result})
    except ValueError as exc:
        return _error(str(exc), 404)
    except database.DeleteError as exc:
        return _error(str(exc), 409)


@app.route("/api/dashboard", methods=["GET"])
def api_dashboard():
    return jsonify({"ok": True, "data": database.get_dashboard(current_user.id)})


@app.route("/api/value-dashboard", methods=["GET"])
def api_value_dashboard():
    return jsonify({
        "ok": True,
        "data": database.get_value_dashboard(current_user.id),
    })


@app.route("/api/opportunities", methods=["GET"])
def api_list_opportunities():
    return jsonify({
        "ok": True,
        "data": database.list_opportunities(current_user.id),
    })


@app.route("/api/opportunities", methods=["POST"])
def api_create_opportunity():
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify({
            "ok": True,
            "data": database.create_opportunity(payload, current_user.id),
        })
    except ValueError as exc:
        return _error(str(exc))


@app.route("/api/opportunities/<int:opportunity_id>", methods=["PATCH"])
def api_update_opportunity(opportunity_id):
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify({
            "ok": True,
            "data": database.update_opportunity(
                opportunity_id, payload, current_user.id
            ),
        })
    except ValueError as exc:
        status = 404 if "不存在" in str(exc) else 400
        return _error(str(exc), status)


@app.route("/api/opportunities/<int:opportunity_id>", methods=["DELETE"])
def api_delete_opportunity(opportunity_id):
    try:
        return jsonify({
            "ok": True,
            "data": database.delete_opportunity(opportunity_id, current_user.id),
        })
    except ValueError as exc:
        return _error(str(exc), 404)
    except database.DeleteError as exc:
        return _error(str(exc), 409)


@app.route("/api/opportunities/<int:opportunity_id>/links", methods=["GET"])
def api_opportunity_links(opportunity_id):
    try:
        return jsonify({
            "ok": True,
            "data": database.get_opportunity_links(
                opportunity_id, current_user.id
            ),
        })
    except ValueError as exc:
        return _error(str(exc), 404)


@app.route("/api/experiments", methods=["GET"])
def api_list_experiments():
    return jsonify({
        "ok": True,
        "data": database.list_experiments(current_user.id),
    })


@app.route("/api/experiments", methods=["POST"])
def api_create_experiment():
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify({
            "ok": True,
            "data": database.create_experiment(payload, current_user.id),
        })
    except ValueError as exc:
        return _error(str(exc))


@app.route("/api/experiments/<int:experiment_id>", methods=["PATCH"])
def api_update_experiment(experiment_id):
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify({
            "ok": True,
            "data": database.update_experiment(
                experiment_id, payload, current_user.id
            ),
        })
    except ValueError as exc:
        status = 404 if "不存在" in str(exc) else 400
        return _error(str(exc), status)


@app.route("/api/experiments/<int:experiment_id>", methods=["DELETE"])
def api_delete_experiment(experiment_id):
    try:
        return jsonify({
            "ok": True,
            "data": database.delete_experiment(experiment_id, current_user.id),
        })
    except ValueError as exc:
        return _error(str(exc), 404)
    except database.DeleteError as exc:
        return _error(str(exc), 409)


@app.route("/api/experiments/<int:experiment_id>/links", methods=["GET"])
def api_experiment_links(experiment_id):
    try:
        return jsonify({
            "ok": True,
            "data": database.get_experiment_links(experiment_id, current_user.id),
        })
    except ValueError as exc:
        return _error(str(exc), 404)


@app.route("/api/feedback", methods=["GET"])
def api_list_feedback():
    return jsonify({
        "ok": True,
        "data": database.list_feedback_items(current_user.id),
    })


@app.route("/api/feedback", methods=["POST"])
def api_create_feedback():
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify({
            "ok": True,
            "data": database.create_feedback_item(payload, current_user.id),
        })
    except ValueError as exc:
        return _error(str(exc))


@app.route("/api/feedback/<int:feedback_id>", methods=["PATCH"])
def api_update_feedback(feedback_id):
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify({
            "ok": True,
            "data": database.update_feedback_item(
                feedback_id, payload, current_user.id
            ),
        })
    except ValueError as exc:
        status = 404 if "不存在" in str(exc) else 400
        return _error(str(exc), status)


@app.route("/api/feedback/<int:feedback_id>", methods=["DELETE"])
def api_delete_feedback(feedback_id):
    try:
        return jsonify({
            "ok": True,
            "data": database.delete_feedback_item(feedback_id, current_user.id),
        })
    except ValueError as exc:
        return _error(str(exc), 404)
    except database.DeleteError as exc:
        return _error(str(exc), 409)


@app.route("/api/feedback/<int:feedback_id>/asset", methods=["POST"])
def api_create_asset_from_feedback(feedback_id):
    try:
        return jsonify({
            "ok": True,
            "data": database.create_asset_from_feedback(
                feedback_id, current_user.id
            ),
        })
    except ValueError as exc:
        status = 404 if "不存在" in str(exc) else 400
        return _error(str(exc), status)
    except TypeError as exc:
        return _error(str(exc) if str(exc) else "参数无效")


@app.route("/api/feedback/<int:feedback_id>/links", methods=["GET"])
def api_feedback_links(feedback_id):
    try:
        return jsonify({
            "ok": True,
            "data": database.get_feedback_links(feedback_id, current_user.id),
        })
    except ValueError as exc:
        return _error(str(exc), 404)


@app.route("/api/export", methods=["GET"])
def api_export():
    try:
        payload = database.export_all_data(current_user.id)
        filename = database.backup_filename()
        body = json.dumps(payload, ensure_ascii=False, indent=2)
        return Response(
            body,
            mimetype="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            },
        )
    except database.ExportError as exc:
        return _error(str(exc), 500)


@app.route("/api/export/obsidian.zip", methods=["GET"])
def api_export_obsidian():
    try:
        body = obsidian_export.build_obsidian_zip(current_user.id)
        filename = obsidian_export.zip_filename()
        return Response(
            body,
            mimetype="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            },
        )
    except obsidian_export.ObsidianExportError as exc:
        return _error(str(exc), 500)


@app.route("/api/import/preview", methods=["POST"])
def api_import_preview():
    payload = request.get_json(silent=True)
    if payload is None:
        return _error("请求体必须是有效的 JSON")
    try:
        stats = database.preview_import_data(payload, current_user.id)
        return jsonify({"ok": True, "data": stats})
    except database.DataImportError as exc:
        return _error(str(exc), 400)


@app.route("/api/import", methods=["POST"])
def api_import():
    payload = request.get_json(silent=True)
    if payload is None:
        return _error("请求体必须是有效的 JSON")
    try:
        stats = database.import_all_data(payload, current_user.id)
        return jsonify({"ok": True, "data": stats})
    except database.DataImportError as exc:
        body = {"ok": False, "error": str(exc)}
        body["data"] = exc.stats or database._import_failure_stats(
            errors=[str(exc)]
        )
        return jsonify(body), 400


@app.route("/api/reviews", methods=["GET"])
def api_list_reviews():
    return jsonify({"ok": True, "data": database.list_reviews(current_user.id)})


@app.route("/api/reviews", methods=["POST"])
def api_create_review():
    payload = request.get_json(silent=True) or {}
    try:
        review = database.create_review(
            payload.get("review_date", ""),
            payload.get("type", ""),
            payload.get("what_done", ""),
            payload.get("stuck", ""),
            payload.get("next_adjust", ""),
            payload.get("depositable", ""),
            current_user.id,
        )
        return jsonify({"ok": True, "data": review})
    except ValueError as exc:
        return _error(str(exc))


@app.route("/api/reviews/<int:review_id>", methods=["GET"])
def api_get_review(review_id):
    review = database.get_review(review_id, current_user.id)
    if not review:
        return _error("复盘不存在", 404)
    return jsonify({"ok": True, "data": review})


@app.route("/api/reviews/<int:review_id>", methods=["DELETE"])
def api_delete_review(review_id):
    try:
        result = database.delete_review(review_id, current_user.id)
        return jsonify({"ok": True, "data": result})
    except ValueError as exc:
        return _error(str(exc), 404)
    except database.DeleteError as exc:
        return _error(str(exc), 409)


@app.route("/api/assets", methods=["GET"])
def api_list_assets():
    tag = request.args.get("tag") or None
    asset_type = request.args.get("asset_type") or None
    try:
        return jsonify({
            "ok": True,
            "data": database.list_assets(
                current_user.id, tag, asset_type=asset_type
            ),
        })
    except ValueError as exc:
        return _error(str(exc))


@app.route("/api/assets", methods=["POST"])
def api_create_asset():
    payload = request.get_json(silent=True) or {}
    try:
        asset = database.create_asset(
            payload.get("title", ""),
            payload.get("asset_type", ""),
            capability_tags=payload.get("capability_tags", []),
            fields=payload.get("fields"),
            summary=payload.get("summary", ""),
            reusable_scenario=payload.get("reusable_scenario", ""),
            maturity=payload.get("maturity", "草稿"),
            source_review_id=payload.get("source_review_id"),
            trigger_context=payload.get("trigger_context"),
            core_content=payload.get("core_content"),
            asset_level=payload.get("asset_level", "资料"),
            evidence=payload.get("evidence", ""),
            external_expression=payload.get("external_expression", ""),
            transferable_scene=payload.get("transferable_scene", ""),
            productization_next_step=payload.get("productization_next_step", ""),
            user_id=current_user.id,
        )
        return jsonify({"ok": True, "data": asset})
    except (ValueError, TypeError) as exc:
        return _error(str(exc) if str(exc) else "参数无效")


@app.route("/api/assets/<int:asset_id>", methods=["PATCH"])
def api_update_asset(asset_id):
    payload = request.get_json(silent=True) or {}
    allowed_fields = {
        "title",
        "asset_type",
        "capability_tags",
        "maturity",
        "summary",
        "reusable_scenario",
        "fields",
        "trigger_context",
        "core_content",
        "asset_level",
        "evidence",
        "external_expression",
        "transferable_scene",
        "productization_next_step",
    }
    update_payload = {
        key: value for key, value in payload.items() if key in allowed_fields
    }
    try:
        asset = database.update_asset(
            asset_id, user_id=current_user.id, **update_payload
        )
        return jsonify({"ok": True, "data": asset})
    except ValueError as exc:
        return _business_value_error(exc)


@app.route("/api/assets/<int:asset_id>/links", methods=["GET"])
def api_asset_links(asset_id):
    try:
        return jsonify({
            "ok": True,
            "data": database.get_asset_links(asset_id, current_user.id),
        })
    except ValueError as exc:
        return _error(str(exc), 404)


@app.route("/api/assets/<int:asset_id>/reuse", methods=["POST"])
def api_increment_asset_reuse(asset_id):
    try:
        asset = database.increment_asset_reuse(asset_id, current_user.id)
        return jsonify({"ok": True, "data": asset})
    except ValueError as exc:
        return _error(str(exc), 404)


@app.route("/api/assets/<int:asset_id>", methods=["DELETE"])
def api_delete_asset(asset_id):
    try:
        result = database.delete_asset(asset_id, current_user.id)
        return jsonify({"ok": True, "data": result})
    except ValueError as exc:
        return _error(str(exc), 404)
    except database.DeleteError as exc:
        return _error(str(exc), 409)


@app.route("/api/ai/refine-review", methods=["POST"])
def api_ai_refine_review():
    payload = request.get_json(silent=True) or {}
    review_id = payload.get("review_id")
    if not review_id:
        return _error("缺少 review_id")
    try:
        draft = ai_service.refine_review_to_asset(review_id, current_user.id)
        return jsonify({"ok": True, "data": draft})
    except ai_service.AIServiceError as exc:
        return _error(str(exc))


@app.route("/api/ai/optimize-asset", methods=["POST"])
def api_ai_optimize_asset():
    payload = request.get_json(silent=True) or {}
    asset_id = payload.get("asset_id")
    if not asset_id:
        return _error("缺少 asset_id")
    try:
        result = ai_service.optimize_asset(asset_id, current_user.id)
        return jsonify({"ok": True, "data": result})
    except ai_service.AIServiceError as exc:
        return _error(str(exc))


@app.route("/api/ai/dashboard-briefing", methods=["POST"])
def api_ai_dashboard_briefing():
    try:
        result = ai_service.dashboard_briefing(current_user.id)
        return jsonify({"ok": True, "data": result})
    except ai_service.AIServiceError as exc:
        return _error(str(exc))


@app.route("/api/ai/decompose-goal", methods=["POST"])
def api_ai_decompose_goal():
    payload = request.get_json(silent=True) or {}
    goal_id = payload.get("goal_id")
    if not goal_id:
        return _error("缺少 goal_id")
    try:
        result = ai_service.decompose_goal_projects(goal_id, current_user.id)
        return jsonify({"ok": True, "data": result})
    except ai_service.AIServiceError as exc:
        return _error(str(exc))


@app.route("/api/ai/decompose-project", methods=["POST"])
def api_ai_decompose_project():
    payload = request.get_json(silent=True) or {}
    project_id = payload.get("project_id")
    if not project_id:
        return _error("缺少 project_id")
    try:
        result = ai_service.decompose_project_tasks(project_id, current_user.id)
        return jsonify({"ok": True, "data": result})
    except ai_service.AIServiceError as exc:
        return _error(str(exc))


@app.route("/api/ai/recommend-today-tasks", methods=["POST"])
def api_ai_recommend_today_tasks():
    try:
        result = ai_service.recommend_today_tasks(current_user.id)
        return jsonify({"ok": True, "data": result})
    except ai_service.AIServiceError as exc:
        return _error(str(exc))


@app.route("/api/ai/complete-review", methods=["POST"])
def api_ai_complete_review():
    payload = request.get_json(silent=True) or {}
    try:
        result = ai_service.complete_review_fields(
            payload.get("what_done", ""),
            payload.get("type", "每日"),
        )
        return jsonify({"ok": True, "data": result})
    except ai_service.AIServiceError as exc:
        return _error(str(exc))


@app.route("/api/ai/classify-asset", methods=["POST"])
def api_ai_classify_asset():
    payload = request.get_json(silent=True) or {}
    asset_id = payload.get("asset_id")
    if not asset_id:
        return _error("缺少 asset_id")
    try:
        result = ai_service.classify_asset(asset_id, current_user.id)
        return jsonify({"ok": True, "data": result})
    except ai_service.AIServiceError as exc:
        return _error(str(exc))


@app.route("/api/ai/template-asset", methods=["POST"])
def api_ai_template_asset():
    payload = request.get_json(silent=True) or {}
    asset_id = payload.get("asset_id")
    target_type = payload.get("target_type")
    if not asset_id:
        return _error("缺少 asset_id")
    if not target_type:
        return _error("缺少 target_type")
    try:
        result = ai_service.template_asset(
            asset_id, target_type, current_user.id
        )
        return jsonify({"ok": True, "data": result})
    except ai_service.AIServiceError as exc:
        return _error(str(exc))


@app.route("/api/ai/attribute-capability", methods=["POST"])
def api_ai_attribute_capability():
    payload = request.get_json(silent=True) or {}
    module = payload.get("module")
    if not module:
        return _error("缺少 module")
    try:
        result = ai_service.attribute_capability(module, current_user.id)
        return jsonify({"ok": True, "data": result})
    except ai_service.AIServiceError as exc:
        return _error(str(exc))


@app.route("/api/ai/diagnose-capabilities", methods=["POST"])
def api_ai_diagnose_capabilities():
    try:
        result = ai_service.diagnose_capabilities(current_user.id)
        return jsonify({"ok": True, "data": result})
    except ai_service.AIServiceError as exc:
        return _error(str(exc))


@app.route("/api/ai/aggregate-weekly-reviews", methods=["POST"])
def api_ai_aggregate_weekly_reviews():
    payload = request.get_json(silent=True) or {}
    review_ids = payload.get("review_ids")
    if not review_ids:
        return _error("缺少 review_ids")
    try:
        result = ai_service.aggregate_weekly_reviews(
            review_ids, current_user.id
        )
        return jsonify({"ok": True, "data": result})
    except ai_service.AIServiceError as exc:
        return _error(str(exc))


@app.route("/api/ai/dispatch-actions", methods=["POST"])
def api_ai_dispatch_actions():
    try:
        result = ai_service.dispatch_dashboard_actions(current_user.id)
        return jsonify({"ok": True, "data": result})
    except ai_service.AIServiceError as exc:
        return _error(str(exc))


def _value_chain_ai_response(object_type, action):
    payload = request.get_json(silent=True) or {}
    entity_id = payload.get("id")
    if not entity_id:
        return _error("缺少 id")
    try:
        result = ai_service.value_chain_ai_advice(
            object_type, action, entity_id, current_user.id
        )
        return jsonify({"ok": True, "data": result})
    except ai_service.AIServiceError as exc:
        return _error(str(exc))


@app.route("/api/ai/opportunity-advance", methods=["POST"])
def api_ai_opportunity_advance():
    return _value_chain_ai_response("opportunity", "advance")


@app.route("/api/ai/opportunity-red-team", methods=["POST"])
def api_ai_opportunity_red_team():
    return _value_chain_ai_response("opportunity", "red_team")


@app.route("/api/ai/opportunity-audit", methods=["POST"])
def api_ai_opportunity_audit():
    return _value_chain_ai_response("opportunity", "audit")


@app.route("/api/ai/experiment-advance", methods=["POST"])
def api_ai_experiment_advance():
    return _value_chain_ai_response("experiment", "advance")


@app.route("/api/ai/experiment-red-team", methods=["POST"])
def api_ai_experiment_red_team():
    return _value_chain_ai_response("experiment", "red_team")


@app.route("/api/ai/experiment-audit", methods=["POST"])
def api_ai_experiment_audit():
    return _value_chain_ai_response("experiment", "audit")


@app.route("/api/ai/feedback-advance", methods=["POST"])
def api_ai_feedback_advance():
    return _value_chain_ai_response("feedback", "advance")


@app.route("/api/ai/feedback-red-team", methods=["POST"])
def api_ai_feedback_red_team():
    return _value_chain_ai_response("feedback", "red_team")


@app.route("/api/ai/feedback-audit", methods=["POST"])
def api_ai_feedback_audit():
    return _value_chain_ai_response("feedback", "audit")


@app.route("/api/inbox/analyze", methods=["POST"])
def api_inbox_analyze():
    payload = request.get_json(silent=True) or {}
    try:
        result = inbox_service.analyze_text(
            payload.get("text", ""),
            ai_service.analyze_inbox_text,
            current_user.id,
        )
        return jsonify({
            "ok": True,
            "data": {
                "inbox_entry_id": result["inbox_entry_id"],
                "entry": result["entry"],
                "suggestions": result["suggestions"],
            },
        })
    except inbox_service.InboxServiceError as exc:
        return _error(str(exc))


@app.route("/api/inbox", methods=["GET"])
def api_list_inbox():
    limit = request.args.get("limit", default=20, type=int)
    limit = max(1, min(limit, 50))
    return jsonify({
        "ok": True,
        "data": database.list_inbox_entries(current_user.id, limit),
    })


@app.route("/api/inbox/<int:entry_id>", methods=["GET"])
def api_get_inbox(entry_id):
    try:
        result = inbox_service.get_inbox_detail(entry_id, current_user.id)
        return jsonify({"ok": True, "data": result})
    except inbox_service.InboxServiceError as exc:
        return _error(str(exc), 404)


@app.route("/api/inbox/commit", methods=["POST"])
def api_inbox_commit():
    payload = request.get_json(silent=True) or {}
    suggestion_ids = payload.get("suggestion_ids") or []
    override_payload = payload.get("override_payload") or []
    if not isinstance(suggestion_ids, list):
        return _error("suggestion_ids 必须为数组")
    if not isinstance(override_payload, list):
        return _error("override_payload 必须为数组")
    try:
        result = inbox_service.commit_suggestions(
            suggestion_ids,
            current_user.id,
            override_payload=override_payload,
        )
        return jsonify({"ok": True, "data": result})
    except inbox_service.InboxServiceError as exc:
        return _error(str(exc))


@app.route("/api/inbox/suggestions/<int:suggestion_id>/reject", methods=["POST"])
def api_inbox_reject_suggestion(suggestion_id):
    try:
        suggestion = inbox_service.reject_suggestion(
            suggestion_id, current_user.id
        )
        return jsonify({"ok": True, "data": suggestion})
    except inbox_service.InboxServiceError as exc:
        return _business_value_error(exc)


@app.route("/api/positioning/anchor", methods=["GET"])
def api_get_positioning_anchor():
    anchor = positioning_service.get_anchor(current_user.id)
    return jsonify({"ok": True, "data": anchor})


@app.route("/api/positioning/anchor", methods=["PUT"])
def api_update_positioning_anchor():
    payload = request.get_json(silent=True) or {}
    try:
        anchor = positioning_service.update_anchor(payload, current_user.id)
        return jsonify({"ok": True, "data": anchor})
    except positioning_service.PositioningServiceError as exc:
        return _error(str(exc))


@app.route("/api/positioning/calibrations", methods=["GET"])
def api_list_positioning_calibrations():
    limit = request.args.get("limit", default=50, type=int)
    return jsonify({
        "ok": True,
        "data": positioning_service.list_calibrations(current_user.id, limit),
    })


@app.route("/api/positioning/calibrations", methods=["POST"])
def api_create_positioning_calibration():
    payload = request.get_json(silent=True) or {}
    try:
        calibration = positioning_service.create_calibration(
            payload, current_user.id
        )
        return jsonify({"ok": True, "data": calibration})
    except positioning_service.PositioningServiceError as exc:
        return _error(str(exc))


@app.route("/api/positioning/calibrations/<int:calibration_id>", methods=["GET"])
def api_get_positioning_calibration(calibration_id):
    try:
        detail = positioning_service.get_calibration_detail(
            calibration_id, current_user.id
        )
        return jsonify({"ok": True, "data": detail})
    except positioning_service.PositioningServiceError as exc:
        return _error(str(exc), 404)


@app.route("/api/positioning/calibrations/<int:calibration_id>", methods=["PUT"])
def api_update_positioning_calibration(calibration_id):
    payload = request.get_json(silent=True) or {}
    try:
        calibration = positioning_service.update_calibration(
            calibration_id, payload, current_user.id
        )
        return jsonify({"ok": True, "data": calibration})
    except positioning_service.PositioningServiceError as exc:
        return _business_value_error(exc)


@app.route("/api/positioning/calibrations/<int:calibration_id>", methods=["DELETE"])
def api_delete_positioning_calibration(calibration_id):
    try:
        positioning_service.delete_calibration(calibration_id, current_user.id)
        return jsonify({"ok": True, "data": None})
    except positioning_service.PositioningServiceError as exc:
        return _error(str(exc), 404)


@app.route("/api/positioning/calibrations/<int:calibration_id>/actions", methods=["POST"])
def api_create_positioning_action(calibration_id):
    payload = request.get_json(silent=True) or {}
    try:
        action = positioning_service.create_goal_action(
            calibration_id, payload, current_user.id
        )
        return jsonify({"ok": True, "data": action})
    except positioning_service.PositioningServiceError as exc:
        return _error(str(exc))


@app.route("/api/positioning/actions/<int:action_id>", methods=["PUT"])
def api_update_positioning_action(action_id):
    payload = request.get_json(silent=True) or {}
    try:
        action = positioning_service.update_goal_action(
            action_id, payload, current_user.id
        )
        return jsonify({"ok": True, "data": action})
    except positioning_service.PositioningServiceError as exc:
        return _business_value_error(exc)


@app.route("/api/positioning/actions/<int:action_id>", methods=["DELETE"])
def api_delete_positioning_action(action_id):
    try:
        positioning_service.delete_goal_action(action_id, current_user.id)
        return jsonify({"ok": True, "data": None})
    except positioning_service.PositioningServiceError as exc:
        return _error(str(exc), 404)


@app.route("/api/positioning/actions/<int:action_id>/status", methods=["PATCH"])
def api_update_positioning_action_status(action_id):
    payload = request.get_json(silent=True) or {}
    try:
        action = positioning_service.update_goal_action_status(
            action_id,
            payload.get("status"),
            current_user.id,
        )
        return jsonify({"ok": True, "data": action})
    except positioning_service.PositioningServiceError as exc:
        return _business_value_error(exc)


@app.route("/api/changelog", methods=["GET"])
def api_changelog():
    return jsonify({
        "ok": True,
        "data": {
            "current": changelog.get_current_version(),
            "entries": changelog.list_entries(),
        },
    })


@app.route("/api/settings/ai-model", methods=["GET"])
def api_get_ai_model():
    stored = settings_store.get_stored_model()
    return jsonify({
        "ok": True,
        "data": {
            "model": config.get_deepseek_model(),
            "stored_model": stored or config.DEFAULT_DEEPSEEK_MODEL,
            "available": config.AVAILABLE_DEEPSEEK_MODELS,
            "env_locked": config.is_model_env_locked(),
            "env_model": config._ENV_DEEPSEEK_MODEL or None,
        },
    })


@app.route("/api/settings/ai-model", methods=["PUT"])
def api_set_ai_model():
    if config.is_model_env_locked():
        return _error(
            "模型已由环境变量 DEEPSEEK_MODEL 锁定，请在 .env 或系统环境中修改后重启服务"
        )
    payload = request.get_json(silent=True) or {}
    model = (payload.get("model") or "").strip()
    if model not in config.get_valid_model_ids():
        return _error("不支持的模型")
    settings_store.set_stored_model(model)
    return jsonify({"ok": True, "data": {"model": model}})


@app.route("/api/ai/prompts", methods=["GET"])
def api_list_prompts():
    module = request.args.get("module") or None
    items = list_prompts()
    if module:
        items = [item for item in items if item["module"] == module]
    return jsonify({"ok": True, "data": items})


@app.route("/api/ai/prompts/<module>/<scene>", methods=["GET"])
def api_get_prompt(module, scene):
    try:
        system = read_raw(module, scene, "system")
    except (PromptNotFoundError, ValueError) as exc:
        return _error(str(exc), 404)

    user = None
    try:
        user = read_raw(module, scene, "user")
    except PromptNotFoundError:
        pass

    return jsonify({
        "ok": True,
        "data": {
            "module": module,
            "scene": scene,
            "system": system,
            "user": user,
        },
    })


@app.route("/api/ai/prompts/<module>/<scene>/generate", methods=["POST"])
def api_generate_prompt(module, scene):
    payload = request.get_json(silent=True) or {}
    kind = payload.get("kind", "system")
    if kind not in ("system", "user"):
        return _error("kind 必须为 system 或 user")
    try:
        prompt_specs.get_scene_spec(module, scene)
    except ValueError as exc:
        return _error(str(exc), 404)
    try:
        result = ai_service.generate_prompt_draft(
            module,
            scene,
            kind,
            brief=payload.get("brief", ""),
            current=payload.get("current", ""),
        )
        return jsonify({"ok": True, "data": result})
    except ai_service.AIServiceError as exc:
        return _error(str(exc))


@app.route("/api/ai/prompts/<module>/<scene>", methods=["PUT"])
def api_save_prompt(module, scene):
    payload = request.get_json(silent=True) or {}
    kind = payload.get("kind", "system")
    content = payload.get("content")
    if content is None:
        return _error("缺少 content")
    if kind not in ("system", "user"):
        return _error("kind 必须为 system 或 user")
    try:
        path = save_prompt(module, scene, kind, content)
        return jsonify({"ok": True, "data": {"path": path}})
    except ValueError as exc:
        return _error(str(exc))


@app.route("/api/capabilities/practice-paths", methods=["GET"])
def api_list_capability_practice_paths():
    return jsonify({
        "ok": True,
        "data": database.list_capability_practice_paths(current_user.id),
    })


@app.route("/api/capabilities/<module>/practice-path", methods=["GET"])
def api_get_capability_practice_path(module):
    try:
        return jsonify({
            "ok": True,
            "data": database.get_capability_practice_path(
                module, current_user.id
            ),
        })
    except ValueError as exc:
        return _error(str(exc))


@app.route("/api/capabilities/<module>/practice-steps", methods=["POST"])
def api_create_capability_practice_step(module):
    payload = request.get_json(silent=True) or {}
    try:
        step = database.create_capability_practice_step(
            module,
            payload.get("title", ""),
            payload.get("description", ""),
            payload.get("detail", ""),
            payload.get("step_order"),
            user_id=current_user.id,
        )
        return jsonify({"ok": True, "data": step})
    except ValueError as exc:
        return _error(str(exc))


@app.route("/api/capabilities/practice-steps/<int:step_id>", methods=["PATCH"])
def api_update_capability_practice_step(step_id):
    payload = request.get_json(silent=True) or {}
    allowed = {"title", "description", "detail", "step_order"}
    update_payload = {key: value for key, value in payload.items() if key in allowed}
    try:
        step = database.update_capability_practice_step(
            step_id, user_id=current_user.id, **update_payload
        )
        return jsonify({"ok": True, "data": step})
    except ValueError as exc:
        status = 404 if "不存在" in str(exc) else 400
        return _error(str(exc), status)


@app.route("/api/capabilities/practice-steps/<int:step_id>", methods=["DELETE"])
def api_delete_capability_practice_step(step_id):
    try:
        result = database.delete_capability_practice_step(step_id, current_user.id)
        return jsonify({"ok": True, "data": result})
    except ValueError as exc:
        return _error(str(exc), 404)


@app.route("/api/capabilities/summary", methods=["GET"])
def api_capabilities_summary():
    return jsonify({
        "ok": True,
        "data": database.get_capability_summary(current_user.id),
    })


@app.route("/api/capability-entries", methods=["GET"])
def api_list_capability_entries():
    module = request.args.get("module") or None
    try:
        return jsonify({
            "ok": True,
            "data": database.list_capability_entries(current_user.id, module),
        })
    except ValueError as exc:
        return _error(str(exc))


@app.route("/api/capability-entries", methods=["POST"])
def api_create_capability_entry():
    payload = request.get_json(silent=True) or {}
    try:
        entry = database.create_capability_entry(
            payload.get("module", ""),
            payload.get("entry_date", ""),
            payload.get("content", ""),
            payload.get("source_project", ""),
            payload.get("level_type", ""),
            current_user.id,
        )
        return jsonify({"ok": True, "data": entry})
    except ValueError as exc:
        return _error(str(exc))


@app.route("/api/capability-entries/<int:entry_id>", methods=["DELETE"])
def api_delete_capability_entry(entry_id):
    try:
        result = database.delete_capability_entry(entry_id, current_user.id)
        return jsonify({"ok": True, "data": result})
    except ValueError as exc:
        return _error(str(exc), 404)
    except database.DeleteError as exc:
        return _error(str(exc), 409)


def run_server():
    run_options = config.get_server_run_options(app)
    database.init_db()
    app.run(**run_options)


if __name__ == "__main__":
    run_server()
