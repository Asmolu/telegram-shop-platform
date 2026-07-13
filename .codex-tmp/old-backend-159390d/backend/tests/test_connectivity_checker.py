from __future__ import annotations

import ssl
from datetime import UTC, datetime

import httpx

from scripts import check_production_connectivity as checker


class FakeClient:
    responses: list[httpx.Response] = []
    calls: list[tuple[str, str]] = []

    def __init__(self, **_: object) -> None:
        return None

    def __enter__(self) -> FakeClient:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def request(self, method: str, url: str, **_: object) -> httpx.Response:
        self.calls.append((method, url))
        return self.responses.pop(0)

    def stream(self, method: str, url: str, **_: object) -> FakeStream:
        self.calls.append((method, url))
        return FakeStream(self.responses.pop(0))


class FakeStream:
    def __init__(self, response: httpx.Response) -> None:
        self.response = response

    def __enter__(self) -> httpx.Response:
        return self.response

    def __exit__(self, *_: object) -> None:
        return None


def setup_network(monkeypatch, addresses: list[str] | None = None) -> None:
    monkeypatch.setattr(
        checker,
        "resolve_host",
        lambda _host, _mode: addresses or ["93.184.216.34"],
    )
    monkeypatch.setattr(checker, "connect_tcp", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        checker,
        "tls_handshake",
        lambda *_args, **_kwargs: {"notAfter": "Jan 01 00:00:00 2030 GMT"},
    )
    monkeypatch.setattr(checker.httpx, "Client", FakeClient)


def response(
    status: int = 200,
    headers: dict[str, str] | None = None,
    body: bytes = b"{}",
) -> httpx.Response:
    return httpx.Response(status, headers=headers or {}, content=body)


def test_successful_result_and_json_output(monkeypatch, capsys) -> None:
    setup_network(monkeypatch)
    FakeClient.responses = [
        response(),
        response(),
        response(),
        response(),
        response(),
        response(headers={"etag": '"products-v1"'}),
        response(304),
        response(body=b'<script src="/assets/index.js"></script>'),
        response(body=b"<html>seller</html>"),
        response(body=b"console.log(1)"),
    ]
    monkeypatch.setattr(
        checker,
        "discover_asset_url",
        lambda *_args, **_kwargs: "https://mini.stylexac.ru/assets/index.js",
    )

    code = checker.main([
        "--api-base-url",
        "https://api.stylexac.ru/api/v1",
        "--mini-app-url",
        "https://mini.stylexac.ru",
        "--seller-panel-url",
        "https://seller.stylexac.ru",
        "--format",
        "json",
    ])

    captured = capsys.readouterr()
    assert code == 0
    assert '"api.health"' in captured.out
    assert '"status": "ok"' in captured.out
    assert '"ttfb_ms"' in captured.out


def test_dns_failure_is_critical(monkeypatch) -> None:
    monkeypatch.setattr(
        checker,
        "resolve_host",
        lambda _host, _mode: (_ for _ in ()).throw(OSError("dns failed")),
    )

    result = checker.ConnectivityChecker(timeout=1).dns("https://api.stylexac.ru", "api.dns")

    assert result.status == "fail"
    assert "dns failed" in result.details["error"]


def test_tcp_timeout_is_critical(monkeypatch) -> None:
    setup_network(monkeypatch)
    monkeypatch.setattr(
        checker,
        "connect_tcp",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError("timed out")),
    )

    result = checker.ConnectivityChecker(timeout=1).tcp("https://api.stylexac.ru", "api.tcp")

    assert result.status == "fail"
    assert "timed out" in result.details["error"]


def test_tls_hostname_mismatch_is_critical(monkeypatch) -> None:
    setup_network(monkeypatch)
    monkeypatch.setattr(
        checker,
        "tls_handshake",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ssl.CertificateError("hostname mismatch")),
    )

    result = checker.ConnectivityChecker(timeout=1).tls("https://api.stylexac.ru", "api.tls")

    assert result.status == "fail"
    assert "hostname mismatch" in result.details["error"]


def test_expired_certificate_is_critical(monkeypatch) -> None:
    setup_network(monkeypatch)
    monkeypatch.setattr(
        checker,
        "tls_handshake",
        lambda *_args, **_kwargs: {"notAfter": "Jan 01 00:00:00 2020 GMT"},
    )

    result = checker.ConnectivityChecker(timeout=1).tls("https://api.stylexac.ru", "api.tls")

    assert result.status == "fail"
    assert result.details["error"] == "certificate_expired"


def test_http_500_sets_failed_exit(monkeypatch) -> None:
    setup_network(monkeypatch)
    FakeClient.responses = [response(500)]

    result = checker.ConnectivityChecker(timeout=1).http(
        "https://api.stylexac.ru/health",
        "api.health",
    )

    assert result.status == "fail"
    assert checker.exit_code([result]) == 1


def test_etag_304_check(monkeypatch) -> None:
    setup_network(monkeypatch)
    FakeClient.responses = [response(headers={"etag": '"catalog-v1"'}), response(304)]

    result = checker.ConnectivityChecker(timeout=1).etag_304(
        "https://api.stylexac.ru/api/v1/products?limit=1",
        "api.products.304",
    )

    assert result.status == "ok"
    assert result.details["status"] == 304


def test_private_ip_protection(monkeypatch) -> None:
    setup_network(monkeypatch, ["127.0.0.1"])

    result = checker.ConnectivityChecker(timeout=1).dns("https://api.stylexac.ru", "api.dns")

    assert result.status == "fail"
    assert "refusing private address" in result.details["error"]


def test_human_output_and_warnings_are_zero_exit() -> None:
    results = [checker.CheckResult("optional", "warn", details={"reason": "not_configured"})]

    assert checker.exit_code(results) == 0
    assert "[WARN] optional" in checker.render_human(results)


def test_telegram_token_is_redacted_and_checks_are_read_only(monkeypatch) -> None:
    setup_network(monkeypatch)
    FakeClient.calls = []
    FakeClient.responses = [response(), response()]
    token = "1234567890:abcdefghijklmnopqrstuvwxyz"
    monkeypatch.setenv("BOT_TOKEN_FOR_TEST", token)

    results = checker.telegram_token_checks(
        checker.ConnectivityChecker(timeout=1, allow_private=True),
        "BOT_TOKEN_FOR_TEST",
    )

    assert [call[1].split("/")[-1] for call in FakeClient.calls] == ["getMe", "getWebhookInfo"]
    assert all(
        "setWebhook" not in call[1] and "deleteWebhook" not in call[1]
        for call in FakeClient.calls
    )
    assert token not in checker.render_human(results)


def test_cert_expiry_parser() -> None:
    parsed = checker.parse_cert_expiry({"notAfter": "Jan 01 00:00:00 2030 GMT"})

    assert parsed == datetime(2030, 1, 1, tzinfo=UTC)


def test_parse_args_requires_urls() -> None:
    args = checker.parse_args([
        "--api-base-url",
        "https://api.stylexac.ru/api/v1",
        "--mini-app-url",
        "https://mini.stylexac.ru",
        "--seller-panel-url",
        "https://seller.stylexac.ru",
        "--ip-mode",
        "ipv4",
    ])

    assert args.ip_mode == "ipv4"


def test_synthetic_payload_is_allowlisted() -> None:
    payload = checker.synthetic_telemetry_payload()

    assert payload["events"][0]["name"] == "mini_app.bootstrap_started"
    assert "token" not in payload["events"][0]
    assert "initData" not in payload["events"][0]
