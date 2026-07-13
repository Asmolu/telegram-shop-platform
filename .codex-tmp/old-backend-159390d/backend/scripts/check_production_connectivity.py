from __future__ import annotations

import argparse
import json
import os
import re
import socket
import ssl
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from ipaddress import ip_address
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

CRITICAL_ENDPOINTS = (
    ("api.health", "GET", "/health"),
    ("api.products", "GET", "/api/v1/products?limit=1"),
    ("api.categories", "GET", "/api/v1/categories"),
    ("api.tags", "GET", "/api/v1/tags"),
    ("api.banners", "GET", "/api/v1/banners?limit=1&offset=0"),
)
TOKEN_REDACTION = "***redacted***"


@dataclass
class CheckResult:
    name: str
    status: str
    duration_ms: int | None = None
    details: dict[str, Any] = field(default_factory=dict)


class ConnectivityChecker:
    def __init__(self, timeout: float, ip_mode: str = "auto", allow_private: bool = False) -> None:
        self.timeout = timeout
        self.ip_mode = ip_mode
        self.allow_private = allow_private

    def dns(self, url: str, name: str) -> CheckResult:
        parsed = require_url(url)
        started = time.perf_counter()
        try:
            addresses = resolve_host(parsed.hostname or "", self.ip_mode)
            self._reject_private(addresses)
            return CheckResult(
                name,
                "ok",
                elapsed_ms(started),
                {"host": parsed.hostname, "addresses": addresses},
            )
        except Exception as exc:  # noqa: BLE001 - sanitized for CLI output
            return CheckResult(name, "fail", elapsed_ms(started), {"error": sanitize_error(exc)})

    def tcp(self, url: str, name: str) -> CheckResult:
        parsed = require_url(url)
        started = time.perf_counter()
        try:
            addresses = resolve_host(parsed.hostname or "", self.ip_mode)
            self._reject_private(addresses)
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            connect_tcp(addresses[0], port, self.timeout)
            return CheckResult(
                name,
                "ok",
                elapsed_ms(started),
                {"address": addresses[0], "port": port},
            )
        except Exception as exc:  # noqa: BLE001
            return CheckResult(name, "fail", elapsed_ms(started), {"error": sanitize_error(exc)})

    def tls(self, url: str, name: str) -> CheckResult:
        parsed = require_url(url)
        if parsed.scheme != "https":
            return CheckResult(name, "warn", details={"reason": "not_https"})
        started = time.perf_counter()
        try:
            addresses = resolve_host(parsed.hostname or "", self.ip_mode)
            self._reject_private(addresses)
            cert = tls_handshake(
                addresses[0],
                parsed.hostname or "",
                parsed.port or 443,
                self.timeout,
            )
            expires_at = parse_cert_expiry(cert)
            if expires_at and expires_at <= datetime.now(UTC):
                return CheckResult(
                    name,
                    "fail",
                    elapsed_ms(started),
                    {"error": "certificate_expired", "expires_at": expires_at.isoformat()},
                )
            return CheckResult(
                name,
                "ok",
                elapsed_ms(started),
                {
                    "host": parsed.hostname,
                    "expires_at": expires_at.isoformat() if expires_at else None,
                },
            )
        except Exception as exc:  # noqa: BLE001
            return CheckResult(name, "fail", elapsed_ms(started), {"error": sanitize_error(exc)})

    def http(
        self,
        url: str,
        name: str,
        *,
        method: str = "GET",
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        host_header: str | None = None,
        expected_status: set[int] | None = None,
        optional: bool = False,
    ) -> CheckResult:
        started = time.perf_counter()
        try:
            parsed = require_url(url)
            addresses = resolve_host(parsed.hostname or "", self.ip_mode)
            self._reject_private(addresses)
            request_headers = dict(headers or {})
            if host_header:
                request_headers["Host"] = host_header
            with httpx.Client(timeout=self.timeout, follow_redirects=False) as client:
                with client.stream(
                    method,
                    url,
                    json=json_body,
                    headers=request_headers or None,
                ) as response:
                    ttfb_ms = elapsed_ms(started)
                    content = response.read()
                    total_ms = elapsed_ms(started)
            status = response.status_code
            ok_status = expected_status or {200}
            status_name = "ok" if status in ok_status else ("warn" if optional else "fail")
            return CheckResult(
                name,
                status_name,
                total_ms,
                {
                    "status": status,
                    "http_version": response.http_version,
                    "content_type": response.headers.get("content-type"),
                    "content_length": len(content),
                    "cache_control": response.headers.get("cache-control"),
                    "etag": response.headers.get("etag"),
                    "x_request_id": response.headers.get("x-request-id"),
                    "location": response.headers.get("location"),
                    "ttfb_ms": ttfb_ms,
                    "total_ms": total_ms,
                },
            )
        except Exception as exc:  # noqa: BLE001
            return CheckResult(
                name,
                "warn" if optional else "fail",
                elapsed_ms(started),
                {"error": sanitize_error(exc)},
            )

    def etag_304(self, url: str, name: str, *, host_header: str | None = None) -> CheckResult:
        first = self.http(
            url,
            f"{name}.etag_source",
            expected_status={200},
            optional=True,
            host_header=host_header,
        )
        etag = first.details.get("etag")
        if not etag:
            return CheckResult(name, "warn", first.duration_ms, {"reason": "etag_missing"})
        return self.http(
            url,
            name,
            headers={"If-None-Match": str(etag)},
            expected_status={304},
            host_header=host_header,
        )

    def _reject_private(self, addresses: list[str]) -> None:
        if self.allow_private:
            return
        for address in addresses:
            parsed = ip_address(address)
            if parsed.is_private or parsed.is_loopback or parsed.is_link_local:
                msg = f"refusing private address {address}; pass --allow-private for local checks"
                raise ValueError(msg)


def run_checks(args: argparse.Namespace) -> list[CheckResult]:
    checker = ConnectivityChecker(args.timeout, args.ip_mode, args.allow_private)
    results: list[CheckResult] = []

    for label, base_url in [
        ("api", args.api_base_url),
        ("mini_app", args.mini_app_url),
        ("seller_panel", args.seller_panel_url),
    ]:
        results.extend([
            checker.dns(base_url, f"{label}.dns"),
            checker.tcp(base_url, f"{label}.tcp"),
            checker.tls(base_url, f"{label}.tls"),
        ])

    api_origin = origin_url(args.api_base_url)
    api_host_header = args.api_host_header
    mini_host_header = args.mini_host_header
    seller_host_header = args.seller_host_header
    for name, method, path in CRITICAL_ENDPOINTS:
        results.append(
            checker.http(
                urljoin(api_origin, path),
                name,
                method=method,
                host_header=api_host_header,
            )
        )
    results.append(
        checker.etag_304(
            urljoin(api_origin, "/api/v1/products?limit=1"),
            "api.products.304",
            host_header=api_host_header,
        )
    )

    results.append(checker.http(args.mini_app_url, "mini_app.html", host_header=mini_host_header))
    results.append(
        checker.http(args.seller_panel_url, "seller_panel.html", host_header=seller_host_header)
    )
    asset_url = discover_asset_url(args.mini_app_url, checker, host_header=mini_host_header)
    if asset_url:
        results.append(
            checker.http(
                asset_url,
                "mini_app.hashed_asset",
                optional=True,
                host_header=mini_host_header,
            )
        )
    else:
        results.append(
            CheckResult(
                "mini_app.hashed_asset",
                "warn",
                details={"reason": "not_discovered"},
            )
        )

    if args.uploads_test_url:
        results.append(checker.http(args.uploads_test_url, "uploads.sample_image", optional=True))

    if args.check_telemetry:
        results.append(
            checker.http(
                urljoin(api_origin, "/api/v1/analytics/telemetry"),
                "telemetry.synthetic_ingest",
                method="POST",
                json_body=synthetic_telemetry_payload(),
                expected_status={202},
                optional=True,
                host_header=api_host_header,
            )
        )

    if args.telegram_public:
        results.extend(telegram_public_checks(checker))
    for env_name in args.telegram_bot_env:
        results.extend(telegram_token_checks(checker, env_name))

    return results


def telegram_public_checks(checker: ConnectivityChecker) -> list[CheckResult]:
    base = "https://api.telegram.org"
    return [
        checker.dns(base, "telegram.dns"),
        checker.tcp(base, "telegram.tcp"),
        checker.tls(base, "telegram.tls"),
        checker.http(base, "telegram.http", expected_status={200, 302, 404}, optional=True),
    ]


def telegram_token_checks(checker: ConnectivityChecker, env_name: str) -> list[CheckResult]:
    token = os.environ.get(env_name)
    if not token:
        return [
            CheckResult(
                f"telegram.{env_name}.token",
                "warn",
                details={"reason": "env_missing"},
            )
        ]
    base = f"https://api.telegram.org/bot{token}/"
    results = [
        checker.http(
            urljoin(base, "getMe"),
            f"telegram.{env_name}.getMe",
            expected_status={200},
            optional=True,
        ),
        checker.http(
            urljoin(base, "getWebhookInfo"),
            f"telegram.{env_name}.getWebhookInfo",
            expected_status={200},
            optional=True,
        ),
    ]
    for result in results:
        result.details = redact_token_values(result.details, token)
    return results


def discover_asset_url(
    frontend_url: str,
    checker: ConnectivityChecker,
    *,
    host_header: str | None = None,
) -> str | None:
    result = checker.http(
        frontend_url,
        "mini_app.asset_discovery",
        optional=True,
        host_header=host_header,
    )
    if result.status == "fail":
        return None
    try:
        headers = {"Host": host_header} if host_header else None
        response = httpx.get(
            frontend_url,
            timeout=checker.timeout,
            follow_redirects=False,
            headers=headers,
        )
    except httpx.HTTPError:
        return None
    match = re.search(
        r'(?:src|href)="([^"]*/assets/[^"]+\.(?:js|css))"',
        response.text,
    )
    if not match:
        return None
    return urljoin(frontend_url, match.group(1) or "")


def synthetic_telemetry_payload() -> dict[str, Any]:
    return {
        "events": [
            {
                "name": "mini_app.bootstrap_started",
                "version": 1,
                "session_id": "synthetic-connectivity-check",
                "client_event_id": f"synthetic-{int(time.time())}",
                "route": "/synthetic",
                "platform": "web",
                "network_state": "online",
                "success": True,
            }
        ]
    }


def resolve_host(host: str, ip_mode: str) -> list[str]:
    family = socket.AF_UNSPEC
    if ip_mode == "ipv4":
        family = socket.AF_INET
    elif ip_mode == "ipv6":
        family = socket.AF_INET6
    infos = socket.getaddrinfo(host, None, family, socket.SOCK_STREAM)
    addresses = sorted({info[4][0] for info in infos})
    if not addresses:
        raise socket.gaierror(f"no addresses for {host}")
    return addresses


def connect_tcp(address: str, port: int, timeout: float) -> None:
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        sock.connect((address, port))


def tls_handshake(address: str, host: str, port: int, timeout: float) -> dict[str, Any]:
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    context = ssl.create_default_context()
    with socket.socket(family, socket.SOCK_STREAM) as raw_sock:
        raw_sock.settimeout(timeout)
        raw_sock.connect((address, port))
        with context.wrap_socket(raw_sock, server_hostname=host) as tls_sock:
            return tls_sock.getpeercert()


def parse_cert_expiry(cert: dict[str, Any]) -> datetime | None:
    value = cert.get("notAfter")
    if not isinstance(value, str):
        return None
    return datetime.strptime(value, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=UTC)


def require_url(value: str):
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"expected http(s) URL, got {value!r}")
    return parsed


def origin_url(value: str) -> str:
    parsed = require_url(value)
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{parsed.hostname}{port}"


def elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def sanitize_error(exc: Exception) -> str:
    text = str(exc)
    for _, value in os.environ.items():
        if value and len(value) > 20 and value in text:
            text = text.replace(value, TOKEN_REDACTION)
    return text


def redact_token_values(value: Any, token: str) -> Any:
    if isinstance(value, str):
        return value.replace(token, TOKEN_REDACTION)
    if isinstance(value, dict):
        return {key: redact_token_values(item, token) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_token_values(item, token) for item in value]
    return value


def render_human(results: list[CheckResult]) -> str:
    lines = []
    for result in results:
        duration = f" {result.duration_ms}ms" if result.duration_ms is not None else ""
        details = (
            f" {json.dumps(result.details, ensure_ascii=False, sort_keys=True)}"
            if result.details
            else ""
        )
        lines.append(f"[{result.status.upper()}] {result.name}{duration}{details}")
    return "\n".join(lines)


def exit_code(results: list[CheckResult]) -> int:
    return 1 if any(result.status == "fail" for result in results) else 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="TelegramShopPlatform production connectivity checker",
    )
    parser.add_argument("--api-base-url", required=True)
    parser.add_argument("--mini-app-url", required=True)
    parser.add_argument("--seller-panel-url", required=True)
    parser.add_argument("--uploads-test-url")
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--format", choices=["human", "json"], default="human")
    parser.add_argument("--ip-mode", choices=["auto", "ipv4", "ipv6"], default="auto")
    parser.add_argument("--allow-private", action="store_true")
    parser.add_argument("--check-telemetry", action="store_true")
    parser.add_argument("--telegram-public", action="store_true")
    parser.add_argument("--telegram-bot-env", action="append", default=[])
    parser.add_argument("--api-host-header")
    parser.add_argument("--mini-host-header")
    parser.add_argument("--seller-host-header")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    results = run_checks(args)
    if args.format == "json":
        print(json.dumps([result.__dict__ for result in results], ensure_ascii=False, indent=2))
    else:
        print(render_human(results))
    return exit_code(results)


if __name__ == "__main__":
    raise SystemExit(main())
