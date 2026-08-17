"""Validate Phase 5A shadow identities and render the Nginx candidate config.

The deployment inputs are deliberately small and strict.  This module uses no
shell evaluation and no third-party template engine; every supported placeholder
has one validated value and rendering fails if any placeholder remains.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
from dataclasses import dataclass
from pathlib import Path


class ShadowDeploymentError(RuntimeError):
    """Raised when a shadow deployment identity or template input is unsafe."""


SHADOW_ID_PATTERN = r"[a-z0-9][a-z0-9-]{0,63}"
_SHADOW_ID_RE = re.compile(rf"{SHADOW_ID_PATTERN}\Z")
_FQDN_LABEL_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")
_PORT_RE = re.compile(r"[0-9]+\Z")
_SAFE_POSIX_PATH_RE = re.compile(r"/[A-Za-z0-9._/-]+\Z")
_PLACEHOLDER_RE = re.compile(r"__PSY_SHADOW_[A-Z0-9_]+__")
_INJECTION_CHARACTERS = frozenset("\x00\r\n;{}")
_MIN_UNPRIVILEGED_PORT = 1024
_MAX_TCP_PORT = 65535


def _strict_scalar(value, *, label: str) -> str:
    if value is None:
        raise ShadowDeploymentError(f"{label} is required")
    raw = str(value)
    if not raw or raw != raw.strip():
        raise ShadowDeploymentError(f"{label} must be non-empty without whitespace")
    if any(character in raw for character in _INJECTION_CHARACTERS):
        raise ShadowDeploymentError(f"{label} contains forbidden configuration data")
    return raw


def validate_shadow_identity(value, *, label: str) -> str:
    """Return one canonical shadow instance/release id or fail closed."""
    raw = _strict_scalar(value, label=label)
    if not _SHADOW_ID_RE.fullmatch(raw):
        raise ShadowDeploymentError(
            f"{label} must match ^{SHADOW_ID_PATTERN}$"
        )
    return raw


def validate_shadow_fqdn(value) -> str:
    """Return one lowercase ASCII FQDN suitable for an Nginx server_name."""
    raw = _strict_scalar(value, label="shadow server name")
    if raw != raw.lower() or len(raw) > 253 or "." not in raw or raw.endswith("."):
        raise ShadowDeploymentError(
            "shadow server name must be one canonical lowercase FQDN"
        )
    labels = raw.split(".")
    if any(not _FQDN_LABEL_RE.fullmatch(label) for label in labels):
        raise ShadowDeploymentError("shadow server name is not a valid FQDN")
    return raw


def validate_shadow_bind_address(value) -> str:
    """Return one canonical, non-wildcard IPv4 listen address."""
    raw = _strict_scalar(value, label="shadow bind address")
    try:
        address = ipaddress.IPv4Address(raw)
    except ipaddress.AddressValueError as exc:
        raise ShadowDeploymentError("shadow bind address must be a valid IPv4") from exc
    if str(address) != raw or address.is_unspecified:
        raise ShadowDeploymentError(
            "shadow bind address must be canonical and cannot be 0.0.0.0"
        )
    return raw


def validate_shadow_port(value) -> int:
    """Return one strict, non-privileged TCP port for the shadow upstream."""
    raw = _strict_scalar(value, label="shadow port")
    if len(raw) > 5 or not _PORT_RE.fullmatch(raw):
        raise ShadowDeploymentError("shadow port must be a decimal integer")
    port = int(raw, 10)
    if not _MIN_UNPRIVILEGED_PORT <= port <= _MAX_TCP_PORT:
        raise ShadowDeploymentError(
            f"shadow port must be between {_MIN_UNPRIVILEGED_PORT} and {_MAX_TCP_PORT}"
        )
    return port


def validate_shadow_deployment_path(value, *, label: str) -> str:
    """Validate one reviewed Linux absolute path without Nginx metacharacters."""
    raw = _strict_scalar(value, label=label)
    if not _SAFE_POSIX_PATH_RE.fullmatch(raw) or raw == "/" or "//" in raw:
        raise ShadowDeploymentError(
            f"{label} must be a safe absolute POSIX path"
        )
    if any(part in {"", ".", ".."} for part in raw.split("/")[1:]):
        raise ShadowDeploymentError(
            f"{label} must not contain empty, dot, or parent path segments"
        )
    return raw


@dataclass(frozen=True)
class ShadowNginxInputs:
    server_name: str
    bind_address: str
    port: int
    certificate_path: str
    certificate_key_path: str
    acme_root: str
    proxy_auth_snippet: str


def validate_shadow_nginx_inputs(
    *,
    server_name,
    bind_address,
    port,
    certificate_path,
    certificate_key_path,
    acme_root,
    proxy_auth_snippet,
) -> ShadowNginxInputs:
    """Validate every value that can be inserted into the Nginx template."""
    return ShadowNginxInputs(
        server_name=validate_shadow_fqdn(server_name),
        bind_address=validate_shadow_bind_address(bind_address),
        port=validate_shadow_port(port),
        certificate_path=validate_shadow_deployment_path(
            certificate_path, label="shadow certificate path"
        ),
        certificate_key_path=validate_shadow_deployment_path(
            certificate_key_path, label="shadow certificate key path"
        ),
        acme_root=validate_shadow_deployment_path(
            acme_root, label="shadow ACME root"
        ),
        proxy_auth_snippet=validate_shadow_deployment_path(
            proxy_auth_snippet, label="shadow proxy auth snippet"
        ),
    )


def render_shadow_nginx(template_text: str, **raw_inputs) -> str:
    """Render the fixed template only after validating its complete contract."""
    values = validate_shadow_nginx_inputs(**raw_inputs)
    replacements = {
        "__PSY_SHADOW_SERVER_NAME__": values.server_name,
        "__PSY_SHADOW_BIND_ADDRESS__": values.bind_address,
        "__PSY_SHADOW_PORT__": str(values.port),
        "__PSY_SHADOW_CERTIFICATE_PATH__": values.certificate_path,
        "__PSY_SHADOW_CERTIFICATE_KEY_PATH__": values.certificate_key_path,
        "__PSY_SHADOW_ACME_ROOT__": values.acme_root,
        "__PSY_SHADOW_PROXY_AUTH_SNIPPET__": values.proxy_auth_snippet,
    }
    present = set(_PLACEHOLDER_RE.findall(template_text))
    expected = set(replacements)
    if present != expected:
        missing = sorted(expected - present)
        unknown = sorted(present - expected)
        details = []
        if missing:
            details.append("missing=" + ",".join(missing))
        if unknown:
            details.append("unknown=" + ",".join(unknown))
        raise ShadowDeploymentError(
            "shadow Nginx template placeholder contract mismatch: "
            + "; ".join(details)
        )

    rendered = template_text
    for placeholder, replacement in replacements.items():
        rendered = rendered.replace(placeholder, replacement)
    if "__PSY_SHADOW_" in rendered or _PLACEHOLDER_RE.search(rendered):
        raise ShadowDeploymentError(
            "rendered shadow Nginx config contains unresolved placeholders"
        )
    return rendered


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate and render the PSY Phase 5A shadow deployment"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    identity = subparsers.add_parser(
        "validate-identity", help="validate the shadow instance and release id"
    )
    identity.add_argument("--instance", required=True)
    identity.add_argument("--release-id", required=True)

    render = subparsers.add_parser(
        "render-nginx", help="validate inputs and render the shadow Nginx template"
    )
    render.add_argument("--instance", required=True)
    render.add_argument("--release-id", required=True)
    render.add_argument("--template", required=True)
    render.add_argument("--output")
    render.add_argument("--check", action="store_true")
    render.add_argument("--server-name", required=True)
    render.add_argument("--bind-address", required=True)
    render.add_argument("--port", required=True)
    render.add_argument("--certificate", required=True)
    render.add_argument("--certificate-key", required=True)
    render.add_argument("--acme-root", required=True)
    render.add_argument("--proxy-auth-snippet", required=True)
    return parser


def main(argv=None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        instance = validate_shadow_identity(args.instance, label="shadow instance id")
        release_id = validate_shadow_identity(
            args.release_id, label="shadow release id"
        )
        if args.command == "validate-identity":
            print(json.dumps({"instance": instance, "release_id": release_id}))
            return 0

        template_path = Path(args.template).expanduser()
        if not template_path.is_absolute():
            raise ShadowDeploymentError(
                "shadow Nginx template path must be absolute"
            )
        try:
            template_text = template_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ShadowDeploymentError(
                "shadow Nginx template cannot be read"
            ) from exc
        rendered = render_shadow_nginx(
            template_text,
            server_name=args.server_name,
            bind_address=args.bind_address,
            port=args.port,
            certificate_path=args.certificate,
            certificate_key_path=args.certificate_key,
            acme_root=args.acme_root,
            proxy_auth_snippet=args.proxy_auth_snippet,
        )
        if args.check:
            if args.output:
                raise ShadowDeploymentError(
                    "--check validates without writing and cannot use --output"
                )
            print(
                json.dumps(
                    {
                        "ok": True,
                        "instance": instance,
                        "release_id": release_id,
                        "placeholders_remaining": False,
                    }
                )
            )
            return 0
        if not args.output:
            raise ShadowDeploymentError("render-nginx requires --output or --check")
        output_value = validate_shadow_deployment_path(
            args.output, label="rendered shadow Nginx output path"
        )
        output_path = Path(output_value)
        try:
            with output_path.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(rendered)
        except FileExistsError as exc:
            raise ShadowDeploymentError(
                "refusing to overwrite rendered shadow Nginx config"
            ) from exc
        except OSError as exc:
            raise ShadowDeploymentError(
                "rendered shadow Nginx config cannot be written"
            ) from exc
        print(json.dumps({"ok": True, "output": str(output_path)}))
        return 0
    except ShadowDeploymentError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
