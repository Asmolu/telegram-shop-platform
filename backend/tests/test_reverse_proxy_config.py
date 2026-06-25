from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CADDYFILE = ROOT / "deploy" / "caddy" / "Caddyfile.frankfurt.example"


def test_frankfurt_caddyfile_contains_required_domains() -> None:
    content = CADDYFILE.read_text(encoding="utf-8")

    for domain in [
        "stylexac.ru",
        "www.stylexac.ru",
        "mini.stylexac.ru",
        "seller.stylexac.ru",
        "api.stylexac.ru",
    ]:
        assert domain in content


def test_frankfurt_caddyfile_does_not_strip_api_or_upload_paths() -> None:
    content = CADDYFILE.read_text(encoding="utf-8")

    assert "handle_path" not in content
    assert "@api path /api/*" in content
    assert "@uploads path /uploads/*" in content
    assert "reverse_proxy backend:8000" in content


def test_api_and_uploads_are_matched_before_frontend_proxy() -> None:
    content = CADDYFILE.read_text(encoding="utf-8")
    mini_block_start = content.index("stylexac.ru")
    api_match = content.index("import api_and_uploads", mini_block_start)
    frontend_proxy = content.index("reverse_proxy mini-app:80", mini_block_start)
    seller_block_start = content.index("seller.stylexac.ru")
    seller_api_match = content.index("import api_and_uploads", seller_block_start)
    seller_frontend_proxy = content.index("reverse_proxy seller-panel:80", seller_block_start)

    assert api_match < frontend_proxy
    assert seller_api_match < seller_frontend_proxy
