from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import create_app

PRODUCTION_ORIGINS = ",".join(
    [
        "https://stylexac.ru",
        "https://www.stylexac.ru",
        "https://mini.stylexac.ru",
        "https://seller.stylexac.ru",
    ]
)


def test_allowed_mini_app_origin_gets_cors_headers(monkeypatch) -> None:
    monkeypatch.setattr(settings, "cors_origins_raw", PRODUCTION_ORIGINS)

    with TestClient(create_app()) as client:
        response = client.get("/health", headers={"Origin": "https://mini.stylexac.ru"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://mini.stylexac.ru"
    assert "X-Request-ID" in response.headers["access-control-expose-headers"]
    assert "ETag" in response.headers["access-control-expose-headers"]


def test_allowed_seller_origin_preflight_allows_auth_and_idempotency(monkeypatch) -> None:
    monkeypatch.setattr(settings, "cors_origins_raw", PRODUCTION_ORIGINS)

    with TestClient(create_app()) as client:
        response = client.options(
            "/api/v1/products",
            headers={
                "Origin": "https://seller.stylexac.ru",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization, Idempotency-Key, X-Request-ID",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://seller.stylexac.ru"
    allowed_headers = response.headers["access-control-allow-headers"].lower()
    assert "authorization" in allowed_headers
    assert "idempotency-key" in allowed_headers
    assert "x-request-id" in allowed_headers


def test_unknown_origin_is_not_allowed(monkeypatch) -> None:
    monkeypatch.setattr(settings, "cors_origins_raw", PRODUCTION_ORIGINS)

    with TestClient(create_app()) as client:
        response = client.options(
            "/api/v1/products",
            headers={
                "Origin": "https://evil.example",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
