import os
import re

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ["API_KEY"] = "test-api-key"
# Forces the landing page's LinkedIn link into its unconfigured, placeholder
# state regardless of what's set in the ambient environment, so the
# placeholder-safety tests are deterministic.
os.environ["AUTHOR_LINKEDIN_URL"] = ""

from customer360.api.main import app
from customer360.infrastructure.session import Base, get_db_session

client = TestClient(app)

AUTH_HEADERS = {"X-API-Key": "test-api-key"}

# Matches a <script> tag with no src attribute, i.e. an inline script body.
INLINE_SCRIPT_PATTERN = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>.*?</script>", re.DOTALL)

# Matches a <style> tag, i.e. an inline style block (as opposed to a
# <link rel="stylesheet">).
INLINE_STYLE_PATTERN = re.compile(r"<style[^>]*>.*?</style>", re.DOTALL)


def test_root_returns_html_landing_page():
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


def test_root_landing_page_links_to_docs_redoc_and_github():
    response = client.get("/")

    assert 'href="/docs"' in response.text
    assert 'href="/redoc"' in response.text
    assert (
        'href="https://github.com/pbolla1311/customer360-platform"'
        in response.text
    )


def test_root_landing_page_has_no_inline_script():
    response = client.get("/")

    assert INLINE_SCRIPT_PATTERN.findall(response.text) == []


def test_root_landing_page_has_no_inline_style():
    response = client.get("/")

    assert INLINE_STYLE_PATTERN.findall(response.text) == []


def test_root_landing_page_assets_resolve():
    response = client.get("/")

    script_srcs = re.findall(r'<script[^>]*\bsrc="([^"]+)"', response.text)
    stylesheet_hrefs = re.findall(
        r'<link[^>]*rel="stylesheet"[^>]*href="([^"]+)"', response.text
    )
    image_srcs = re.findall(r'<img[^>]*\bsrc="([^"]+)"', response.text)

    asset_urls = script_srcs + stylesheet_hrefs + image_srcs
    assert asset_urls, "expected the landing page to reference local assets"
    assert "/static/site/github-stats.js" in script_srcs

    for url in asset_urls:
        assert url.startswith("/static/"), url
        asset_response = client.get(url)
        assert asset_response.status_code == 200, url


def test_root_landing_page_has_github_stats_container():
    response = client.get("/")

    assert 'id="github-stats"' in response.text
    for stat_id in ("stat-stars", "stat-forks", "stat-license", "stat-release"):
        assert f'id="{stat_id}"' in response.text


def test_root_landing_page_has_six_live_deployment_links():
    response = client.get("/")

    assert response.text.count('class="demo-card"') == 6
    for href in ("/demo", "/", "/docs", "/redoc", "/openapi.json", "/health"):
        assert f'href="{href}"' in response.text, href


def test_root_landing_page_has_launch_demo_button():
    response = client.get("/")

    assert 'href="/demo"' in response.text
    assert "Launch Demo" in response.text


def test_root_landing_page_new_tab_links_use_noopener_noreferrer():
    response = client.get("/")

    new_tab_links = re.findall(
        r'<a\b[^>]*target="_blank"[^>]*>', response.text
    )
    assert new_tab_links, "expected at least one link that opens in a new tab"
    for tag in new_tab_links:
        assert 'rel="noopener noreferrer"' in tag, tag


def test_root_landing_page_shows_author_name_and_role():
    response = client.get("/")

    assert "Built by Prakhyath Bolla" in response.text
    assert "Data Engineer" in response.text


def test_root_landing_page_github_links_are_correct():
    response = client.get("/")

    assert 'href="https://github.com/pbolla1311"' in response.text
    assert (
        'href="https://github.com/pbolla1311/customer360-platform"'
        in response.text
    )


def test_root_landing_page_linkedin_placeholder_is_safe_when_unconfigured():
    response = client.get("/")

    assert "linkedin.com" not in response.text.lower()

    placeholders = re.findall(
        r'<span[^>]*class="[^"]*link-placeholder[^"]*"[^>]*>.*?</span>',
        response.text,
        re.DOTALL,
    )
    assert placeholders, "expected a placeholder element for the unset LinkedIn link"
    for placeholder in placeholders:
        assert "href=" not in placeholder
        assert 'aria-disabled="true"' in placeholder


def test_root_landing_page_architecture_image_opens_in_new_tab():
    response = client.get("/")

    match = re.search(
        r'<a\b[^>]*class="arch-panel arch-link"[^>]*>.*?</a>',
        response.text,
        re.DOTALL,
    )
    assert match is not None, "expected the architecture image to be wrapped in a link"

    link_html = match.group(0)
    assert 'href="/static/site/architecture.png"' in link_html
    assert 'target="_blank"' in link_html
    assert 'rel="noopener noreferrer"' in link_html

    img_match = re.search(r'<img\b[^>]*>', link_html)
    assert img_match is not None, "expected an <img> inside the architecture link"
    img_tag = img_match.group(0)
    assert 'src="/static/site/architecture.png"' in img_tag
    alt_match = re.search(r'alt="([^"]+)"', img_tag)
    assert alt_match is not None and alt_match.group(1).strip(), (
        "expected meaningful alt text on the architecture image"
    )


def test_root_landing_page_footer_has_required_content_and_links():
    response = client.get("/")

    assert "Built with FastAPI" in response.text
    assert "PostgreSQL" in response.text
    assert "Kafka" in response.text
    assert "Created by Prakhyath Bolla" in response.text

    footer_match = re.search(
        r"<footer\b.*?</footer>", response.text, re.DOTALL
    )
    assert footer_match is not None
    footer_html = footer_match.group(0)

    assert 'href="https://github.com/pbolla1311/customer360-platform"' in footer_html
    assert 'href="/demo"' in footer_html
    assert 'href="/docs"' in footer_html
    assert 'href="/redoc"' in footer_html
    assert 'href="/health"' in footer_html
    assert "v1.0" in footer_html or "v{{" not in footer_html


def test_csp_connect_src_allows_only_github_api():
    response = client.get("/")

    csp = response.headers["Content-Security-Policy"]
    assert "connect-src 'self' https://api.github.com" in csp
    assert "unsafe-inline" not in csp
    assert "unsafe-eval" not in csp


def test_status_returns_previous_root_json_response():
    response = client.get("/status")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "running"
    assert body["application"] == "Customer360 Platform"
    assert "version" in body


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
    for path in ("/", "/docs", "/redoc", "/demo"):
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


# ---------------------------------------------------------------------
# Existing v1 API behavior, locked in before adding /demo below.
# ---------------------------------------------------------------------


def test_v1_customers_requires_api_key():
    response = client.get("/api/v1/customers")

    assert response.status_code == 401


def test_v1_get_customers_with_valid_key():
    response = client.get("/api/v1/customers", headers=AUTH_HEADERS)

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_v1_health_matches_unversioned_health():
    assert client.get("/api/v1/health").json() == client.get("/health").json()


# ---------------------------------------------------------------------
# /demo dashboard
# ---------------------------------------------------------------------


def _empty_sqlite_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    testing_session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    session = testing_session_factory()
    try:
        yield session
    finally:
        session.close()


def _broken_db_session():
    raise RuntimeError("simulated database outage")
    yield  # pragma: no cover -- generator must contain a yield to be a dependency


def test_demo_page_returns_ok():
    response = client.get("/demo")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


def test_demo_page_has_dashboard_title():
    response = client.get("/demo")

    assert "Demo Dashboard" in response.text


def test_demo_page_links_to_versioned_customer_api():
    response = client.get("/demo")

    assert 'href="/api/v1/customers"' in response.text


def test_demo_page_links_to_swagger_and_github_and_landing():
    response = client.get("/demo")

    assert 'href="/docs"' in response.text
    assert 'href="/"' in response.text
    assert (
        'href="https://github.com/pbolla1311/customer360-platform"'
        in response.text
    )


def test_demo_page_has_no_inline_script():
    response = client.get("/demo")

    assert INLINE_SCRIPT_PATTERN.findall(response.text) == []


def test_demo_page_has_no_inline_style():
    response = client.get("/demo")

    assert INLINE_STYLE_PATTERN.findall(response.text) == []


def test_demo_page_assets_resolve():
    response = client.get("/demo")

    script_srcs = re.findall(r'<script[^>]*\bsrc="([^"]+)"', response.text)
    stylesheet_hrefs = re.findall(
        r'<link[^>]*rel="stylesheet"[^>]*href="([^"]+)"', response.text
    )

    asset_urls = script_srcs + stylesheet_hrefs
    assert "/static/demo/demo.js" in script_srcs
    assert "/static/demo/demo.css" in stylesheet_hrefs

    for url in asset_urls:
        assert url.startswith("/static/"), url
        asset_response = client.get(url)
        assert asset_response.status_code == 200, url


def test_demo_page_shows_accuracy_notice():
    response = client.get("/demo")

    assert "illustrative demo data" in response.text.lower()


def test_demo_customers_endpoint_does_not_require_api_key():
    response = client.get("/demo/api/customers")

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_demo_summary_endpoint_does_not_require_api_key():
    response = client.get("/demo/api/summary")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"total_customers", "active_profiles", "total_transactions"}


def test_demo_customer_detail_not_found_returns_404():
    response = client.get("/demo/api/customers/does-not-exist")

    assert response.status_code == 404


def test_demo_customer_detail_rejects_invalid_characters():
    response = client.get("/demo/api/customers/customer%20id")

    assert response.status_code == 422


def test_demo_customers_empty_database_renders_empty_list():
    app.dependency_overrides[get_db_session] = _empty_sqlite_session
    try:
        customers_response = client.get("/demo/api/customers")
        summary_response = client.get("/demo/api/summary")
    finally:
        app.dependency_overrides.pop(get_db_session, None)

    assert customers_response.status_code == 200
    assert customers_response.json() == []

    assert summary_response.status_code == 200
    assert summary_response.json() == {
        "total_customers": 0,
        "active_profiles": 0,
        "total_transactions": 0,
    }


def test_demo_customers_backend_failure_surfaces_as_error_status():
    app.dependency_overrides[get_db_session] = _broken_db_session
    error_client = TestClient(app, raise_server_exceptions=False)
    try:
        response = error_client.get("/demo/api/customers")
    finally:
        app.dependency_overrides.pop(get_db_session, None)

    assert response.status_code >= 500


def test_demo_endpoints_are_excluded_from_openapi_schema():
    schema = client.get("/openapi.json").json()

    assert "/demo" not in schema["paths"]
    assert "/demo/api/customers" not in schema["paths"]