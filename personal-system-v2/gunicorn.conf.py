"""Fail-closed Gunicorn contract for the PSY v2.2 single-instance MVP."""

import os

from production_launcher import (
    DEFAULT_BIND_PORT,
    GUNICORN_BIND_PORT_ENV,
    validate_bind_port,
)

bind_port = validate_bind_port(
    os.environ.get(GUNICORN_BIND_PORT_ENV, str(DEFAULT_BIND_PORT))
)
bind = f"127.0.0.1:{bind_port}"
workers = 1
worker_class = "gthread"
threads = 4
preload_app = True
reload = False
timeout = 30
graceful_timeout = 30
keepalive = 2
backlog = 100
accesslog = None
errorlog = "-"
loglevel = "info"
control_socket_disable = True
forwarded_allow_ips = os.environ.get("PERSONAL_OS_TRUSTED_PROXY", "")
secure_scheme_headers = {"X-FORWARDED-PROTO": "https"}
forwarder_headers = ""
limit_request_line = 4094
limit_request_fields = 64
limit_request_field_size = 8190


def on_starting(server):
    """Reject CLI/environment overrides that weaken the in-process guards."""
    configured_bind = list(server.cfg.bind)
    expected_bind = f"127.0.0.1:{bind_port}"
    if configured_bind != [expected_bind]:
        raise RuntimeError(f"PSY production Gunicorn must bind {expected_bind}")
    if server.cfg.workers != 1:
        raise RuntimeError("PSY MVP login guards require exactly one Gunicorn worker")
    if server.cfg.worker_class_str != "gthread" or server.cfg.threads != 4:
        raise RuntimeError("PSY MVP Gunicorn requires gthread with exactly four threads")
    if not server.cfg.preload_app or server.cfg.reload:
        raise RuntimeError("PSY production requires preload_app and forbids reload")
    trusted_proxy = os.environ.get("PERSONAL_OS_TRUSTED_PROXY", "").strip()
    if trusted_proxy not in {"127.0.0.1", "::1"}:
        raise RuntimeError("Gunicorn requires one exact loopback trusted proxy")
    if server.cfg.forwarded_allow_ips != [trusted_proxy]:
        raise RuntimeError("Gunicorn forwarded_allow_ips must match the trusted proxy")
    if server.cfg.forwarder_headers:
        raise RuntimeError("Gunicorn forwarder_headers must remain empty")
    if not server.cfg.control_socket_disable:
        raise RuntimeError("PSY production forbids the Gunicorn control socket")


def nworkers_changed(server, new_value, old_value):
    """Forbid runtime TTIN/TTOU expansion beyond the one-worker MVP."""
    if int(new_value) != 1:
        raise RuntimeError("PSY MVP login guards require exactly one Gunicorn worker")
