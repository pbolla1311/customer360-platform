import os
import re

from fastapi.testclient import TestClient

os.environ["API_KEY"] = "test-api-key"

from customer360.api.main import app

client = TestClient(app)

AUTH_HEADERS = {"X-API-Key": "test-api-key"}

# Matches a <script> tag with no src attribute, i.e. an inline script body.
INLINE_SCRIPT_PATTERN = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>.*?</script>", re.DOTALL)


def test_root():
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["status"] == "running"


def test_health():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_get_customers():
    response = client.get(
        "/customers",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_invalid_customer():
    response = client.get(
        "/customers/does-not-exist",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 404


def test_customers_requires_api_key():
    response = client.get("/customers")

    assert response.status_code == 401


def test_customers_rejects_invalid_api_key():
    response = client.get(
        "/customers",
        headers={"X-API-Key": "wrong-key"},
    )

    assert response.status_code == 401


def test_customer_id_rejects_empty_path_segment():
    response = client.get(
        "/customers/",
        headers=AUTH_HEADERS,
        follow_redirects=False,
    )

    assert response.status_code in {307, 404}


def test_customer_id_rejects_overly_long_value():
    response = client.get(
        f"/customers/{'a' * 129}",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 422


def test_customer_id_rejects_invalid_characters():
    response = client.get(
        "/customers/customer%20id",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 422


def test_security_headers_are_present():
    response = client.get("/health")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"


def test_cors_allows_configured_origin():
    response = client.options(
        "/customers",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-API-Key",
        },
    )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == (
        "http://localhost:3000"
    )


def test_cors_rejects_unconfigured_origin():
    response = client.options(
        "/customers",
        headers={
            "Origin": "https://untrusted.example.com",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-API-Key",
        },
    )

    assert "Access-Control-Allow-Origin" not in response.headers


def test_docs_returns_ok():
    response = client.get("/docs")

    assert response.status_code == 200


def test_redoc_returns_ok():
    response = client.get("/redoc")

    assert response.status_code == 200


def test_openapi_json_returns_ok():
    response = client.get("/openapi.json")

    assert response.status_code == 200


def test_docs_uses_locally_hosted_assets():
    response = client.get("/docs")

    assert "/static/swagger/swagger-ui-bundle.js" in response.text
    assert "/static/swagger/swagger-ui.css" in response.text
    assert "cdn.jsdelivr.net" not in response.text


def test_redoc_uses_locally_hosted_assets():
    response = client.get("/redoc")

    assert "/static/redoc/redoc.standalone.js" in response.text
    assert "cdn.jsdelivr.net" not in response.text
    assert "fonts.googleapis.com" not in response.text


def test_docs_renders_swagger_ui_mount_point_and_referenced_assets_resolve():
    response = client.get("/docs")

    assert '<div id="swagger-ui">' in response.text

    script_srcs = re.findall(r'<script[^>]*\bsrc="([^"]+)"', response.text)
    assert script_srcs, "expected at least one external script tag"
    for src in script_srcs:
        asset_response = client.get(src)
        assert asset_response.status_code == 200, src

    stylesheet_hrefs = re.findall(
        r'<link[^>]*rel="stylesheet"[^>]*href="([^"]+)"', response.text
    )
    assert stylesheet_hrefs, "expected at least one stylesheet link"
    for href in stylesheet_hrefs:
        asset_response = client.get(href)
        assert asset_response.status_code == 200, href


def test_redoc_renders_mount_point_and_referenced_assets_resolve():
    response = client.get("/redoc")

    assert '<div id="redoc-container">' in response.text

    script_srcs = re.findall(r'<script[^>]*\bsrc="([^"]+)"', response.text)
    assert script_srcs, "expected at least one external script tag"
    for src in script_srcs:
        asset_response = client.get(src)
        assert asset_response.status_code == 200, src

    stylesheet_hrefs = re.findall(
        r'<link[^>]*rel="stylesheet"[^>]*href="([^"]+)"', response.text
    )
    assert stylesheet_hrefs, "expected at least one stylesheet link"
    for href in stylesheet_hrefs:
        asset_response = client.get(href)
        assert asset_response.status_code == 200, href


def test_docs_html_has_no_inline_script():
    response = client.get("/docs")

    assert INLINE_SCRIPT_PATTERN.findall(response.text) == []


def test_redoc_html_has_no_inline_script():
    response = client.get("/redoc")

    assert INLINE_SCRIPT_PATTERN.findall(response.text) == []


def test_csp_is_strict_on_docs_and_redoc():
    for path in ("/docs", "/redoc"):
        response = client.get(path)
        csp = response.headers["Content-Security-Policy"]

        assert "default-src 'self'" in csp
        assert "script-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp
        assert "base-uri 'self'" in csp
        assert "form-action 'self'" in csp
        assert "unsafe-inline" not in csp
        assert "unsafe-eval" not in csp


def test_redoc_csp_style_src_nonce_matches_the_scripts_it_serves():
    response = client.get("/redoc")
    csp = response.headers["Content-Security-Policy"]

    nonce_match = re.search(r"style-src 'self' 'nonce-([^']+)'", csp)
    assert nonce_match is not None, csp
    header_nonce = nonce_match.group(1)

    script_srcs = re.findall(r'<script[^>]*\bsrc="([^"]+)"', response.text)
    nonced_srcs = [src for src in script_srcs if "nonce=" in src]
    assert nonced_srcs, "expected script tags carrying the CSP nonce"
    for src in nonced_srcs:
        assert f"nonce={header_nonce}" in src


def test_csp_nonce_is_fresh_per_request():
    first = client.get("/redoc").headers["Content-Security-Policy"]
    second = client.get("/redoc").headers["Content-Security-Policy"]

    first_nonce = re.search(r"'nonce-([^']+)'", first).group(1)
    second_nonce = re.search(r"'nonce-([^']+)'", second).group(1)

    assert first_nonce != second_nonce


def test_redoc_init_js_rejects_malformed_nonce():
    response = client.get(
        "/redoc/init.js", params={"nonce": '"; alert(1); //'}
    )

    assert response.status_code == 422


def test_redoc_pre_init_js_patches_style_element_creation():
    response = client.get("/redoc/pre-init.js", params={"nonce": "abc123"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/javascript")
    assert "document.createElement" in response.text
    assert "abc123" in response.text


def test_redoc_init_js_bootstraps_redoc_without_unsafe_inline():
    response = client.get("/redoc/init.js", params={"nonce": "abc123"})

    assert response.status_code == 200
    assert "Redoc.init(" in response.text
    assert "nonce" in response.text
    assert "abc123" in response.text