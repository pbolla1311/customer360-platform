import os
import re

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ["API_KEY"] = "test-api-key"
# Forces the landing page's LinkedIn link into its unconfigured, placeholder
# state regardless of what's set in the ambient environment, so the
# placeholder-safety tests are deterministic.
os.environ["AUTHOR_LINKEDIN_URL"] = ""

import customer360.api.main as main_module
from customer360.api.main import app
from customer360.api.pipeline_simulation_engine import ENGINE, EventStatus
from customer360.infrastructure.models import Customer360Profile
from customer360.infrastructure.repository import Customer360Repository
from customer360.infrastructure.session import Base, get_db_session
from customer360.outbox.repository import OutboxRepository

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


def test_root_landing_page_has_eight_live_deployment_links():
    response = client.get("/")

    assert response.text.count('class="demo-card"') == 8
    for href in (
        "/workspace",
        "/demo",
        "/demo/pipeline",
        "/",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/health",
    ):
        assert f'href="{href}"' in response.text, href


def test_root_landing_page_has_open_workspace_button():
    response = client.get("/")

    assert 'href="/workspace"' in response.text
    assert "Open Workspace" in response.text


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
    assert 'href="/demo/pipeline"' in footer_html
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
    for path in ("/", "/docs", "/redoc", "/demo", "/demo/pipeline"):
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


def _unreachable_db_session():
    """Yields a session successfully, but every query against it fails.

    Unlike _broken_db_session (which fails before FastAPI even gets a
    session), this simulates a DB that's down at query time -- the scenario
    pipeline_telemetry's db_reachable/count fallbacks are actually meant to
    degrade gracefully from, rather than a 500.
    """

    engine = create_engine(
        "sqlite:////nonexistent-directory-for-tests/unreachable.db",
        connect_args={"check_same_thread": False},
    )
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


# ---------------------------------------------------------------------
# /workspace (Customer360 Cloud)
# ---------------------------------------------------------------------


def test_workspace_page_returns_ok():
    response = client.get("/workspace")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


def test_workspace_page_has_title_and_nav_items():
    response = client.get("/workspace")

    assert "Customer360 Cloud" in response.text
    for label in (
        "Overview",
        "Customers",
        "Event Center",
        "Pipeline",
        "Monitoring",
        "Analytics",
        "Audit Logs",
        "API Explorer",
        "Settings",
    ):
        assert label in response.text


def test_workspace_page_embeds_pipeline_and_docs_via_iframe():
    response = client.get("/workspace")

    assert 'src="/demo/pipeline"' in response.text
    assert 'src="/docs"' in response.text


def test_workspace_page_has_no_inline_script():
    response = client.get("/workspace")

    assert INLINE_SCRIPT_PATTERN.findall(response.text) == []


def test_workspace_page_has_no_inline_style():
    response = client.get("/workspace")

    assert INLINE_STYLE_PATTERN.findall(response.text) == []


def test_workspace_page_has_no_inline_style_attributes():
    response = client.get("/workspace")

    assert re.findall(r'\sstyle="', response.text) == []


def test_workspace_page_assets_resolve():
    response = client.get("/workspace")

    script_srcs = re.findall(r'<script[^>]*\bsrc="([^"]+)"', response.text)
    stylesheet_hrefs = re.findall(
        r'<link[^>]*rel="stylesheet"[^>]*href="([^"]+)"', response.text
    )

    asset_urls = script_srcs + stylesheet_hrefs
    assert "/static/workspace/workspace.js" in script_srcs
    assert "/static/workspace/workspace-customers.js" in script_srcs
    assert "/static/workspace/workspace-pipeline.js" in script_srcs
    assert "/static/workspace/workspace-analytics.js" in script_srcs
    assert "/static/workspace/workspace.css" in stylesheet_hrefs

    for url in asset_urls:
        assert url.startswith("/static/"), url
        asset_response = client.get(url)
        assert asset_response.status_code == 200, url


def test_workspace_endpoint_excluded_from_openapi_schema():
    schema = client.get("/openapi.json").json()
    assert "/workspace" not in schema["paths"]


def test_workspace_does_not_affect_existing_demo_dashboard():
    """Regression: the new workspace shell must not change /demo."""

    response = client.get("/demo")
    assert response.status_code == 200
    assert "Demo Dashboard" in response.text


def test_workspace_does_not_affect_existing_pipeline_monitor():
    """Regression: the new workspace shell must not change /demo/pipeline."""

    response = client.get("/demo/pipeline")
    assert response.status_code == 200
    assert 'id="btn-generate"' in response.text


# ---------------------------------------------------------------------
# /demo dashboard
# ---------------------------------------------------------------------


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


# ---------------------------------------------------------------------
# /demo/pipeline monitor
# ---------------------------------------------------------------------


def _reset_pipeline_real_inputs_cache() -> None:
    """Pipeline endpoints cache real DB counts for a few seconds (see
    main.py's _real_pipeline_inputs) so a burst of dashboard polls doesn't
    repeat the same queries. That cache doesn't know about
    dependency_overrides, so any test that swaps the DB session must clear
    it first or it'll see a previous test's cached counts instead of its
    own override.
    """

    main_module._pipeline_real_inputs_cache = None


def _populated_sqlite_session():
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
    Customer360Repository(session).create(
        Customer360Profile(
            customer_id="PIPE-TEST-0001",
            first_name="Pipeline",
            last_name="Tester",
            email="pipeline.tester@example.com",
            city="Testville",
            state="TS",
            transaction_count=4,
            total_spend=88.0,
            average_transaction_value=22.0,
        )
    )
    try:
        yield session
    finally:
        session.close()


def test_pipeline_page_returns_ok():
    response = client.get("/demo/pipeline")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


def test_pipeline_page_has_dashboard_title_and_nav():
    response = client.get("/demo/pipeline")

    assert "Pipeline Monitor" in response.text
    assert 'href="/"' in response.text
    assert 'href="/demo"' in response.text
    assert 'href="/docs"' in response.text
    assert 'href="/api/v1/customers"' in response.text
    assert (
        'href="https://github.com/pbolla1311/customer360-platform"'
        in response.text
    )


def test_pipeline_page_has_no_inline_script():
    response = client.get("/demo/pipeline")

    assert INLINE_SCRIPT_PATTERN.findall(response.text) == []


def test_pipeline_page_has_no_inline_style():
    response = client.get("/demo/pipeline")

    assert INLINE_STYLE_PATTERN.findall(response.text) == []


def test_pipeline_page_assets_resolve():
    response = client.get("/demo/pipeline")

    script_srcs = re.findall(r'<script[^>]*\bsrc="([^"]+)"', response.text)
    stylesheet_hrefs = re.findall(
        r'<link[^>]*rel="stylesheet"[^>]*href="([^"]+)"', response.text
    )

    assert "/static/demo/pipeline/pipeline.js" in script_srcs
    assert "/static/demo/vendor/chart.umd.min.js" in script_srcs
    assert "/static/demo/pipeline/pipeline.css" in stylesheet_hrefs

    for url in script_srcs + stylesheet_hrefs:
        assert url.startswith("/static/"), url
        asset_response = client.get(url)
        assert asset_response.status_code == 200, url


def test_pipeline_page_shows_simulated_telemetry_notice():
    response = client.get("/demo/pipeline")

    assert "Simulated Pipeline Telemetry" in response.text


def test_pipeline_summary_does_not_require_api_key():
    response = client.get("/demo/api/pipeline/summary")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"generated_at", "kpis", "stages", "simulated"}
    assert body["simulated"] is True
    assert [stage["name"] for stage in body["stages"]] == [
        "Producer",
        "Kafka Topic",
        "Outbox",
        "Consumer",
        "Retry Queue",
        "Dead Letter Queue",
        "PostgreSQL",
    ]


def test_pipeline_summary_postgres_stage_matches_real_customer_count():
    _reset_pipeline_real_inputs_cache()
    app.dependency_overrides[get_db_session] = _populated_sqlite_session
    try:
        response = client.get("/demo/api/pipeline/summary")
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        _reset_pipeline_real_inputs_cache()

    postgres_stage = next(
        stage for stage in response.json()["stages"] if stage["name"] == "PostgreSQL"
    )
    assert postgres_stage["count"] == 1
    assert postgres_stage["status"] == "healthy"


def test_pipeline_summary_empty_database_still_returns_valid_snapshot():
    _reset_pipeline_real_inputs_cache()
    app.dependency_overrides[get_db_session] = _empty_sqlite_session
    try:
        response = client.get("/demo/api/pipeline/summary")
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        _reset_pipeline_real_inputs_cache()

    assert response.status_code == 200
    postgres_stage = next(
        stage for stage in response.json()["stages"] if stage["name"] == "PostgreSQL"
    )
    assert postgres_stage["count"] == 0


def test_pipeline_summary_backend_failure_surfaces_as_error_status():
    app.dependency_overrides[get_db_session] = _broken_db_session
    error_client = TestClient(app, raise_server_exceptions=False)
    try:
        response = error_client.get("/demo/api/pipeline/summary")
    finally:
        app.dependency_overrides.pop(get_db_session, None)

    assert response.status_code >= 500


def test_pipeline_events_does_not_require_api_key():
    response = client.get("/demo/api/pipeline/events")

    assert response.status_code == 200
    events = response.json()
    assert len(events) == 12
    for event in events:
        assert set(event) == {"timestamp", "event_type", "status", "detail"}
        assert event["status"] in {"healthy", "warning", "critical"}


def test_pipeline_events_can_reference_real_seeded_customers():
    app.dependency_overrides[get_db_session] = _populated_sqlite_session
    try:
        response = client.get("/demo/api/pipeline/events")
    finally:
        app.dependency_overrides.pop(get_db_session, None)

    assert response.status_code == 200


def test_pipeline_services_has_six_named_services():
    response = client.get("/demo/api/pipeline/services")

    assert response.status_code == 200
    services = response.json()
    assert [service["name"] for service in services] == [
        "API",
        "Database",
        "Kafka",
        "Consumer",
        "Outbox",
        "Scheduler",
    ]
    for service in services:
        assert service["latency_ms"] > 0


def test_pipeline_services_database_card_is_critical_when_db_unreachable():
    _reset_pipeline_real_inputs_cache()
    app.dependency_overrides[get_db_session] = _unreachable_db_session
    try:
        response = client.get("/demo/api/pipeline/services")
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        _reset_pipeline_real_inputs_cache()

    assert response.status_code == 200
    database_service = next(
        service for service in response.json() if service["name"] == "Database"
    )
    assert database_service["status"] == "critical"
    assert database_service["latency_ms"] > 100


def test_pipeline_summary_degrades_gracefully_when_db_unreachable():
    _reset_pipeline_real_inputs_cache()
    app.dependency_overrides[get_db_session] = _unreachable_db_session
    try:
        response = client.get("/demo/api/pipeline/summary")
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        _reset_pipeline_real_inputs_cache()

    assert response.status_code == 200
    body = response.json()
    postgres_stage = next(
        stage for stage in body["stages"] if stage["name"] == "PostgreSQL"
    )
    assert postgres_stage["count"] == 0
    assert postgres_stage["status"] == "critical"


def test_pipeline_charts_has_all_six_series_plus_event_types():
    response = client.get("/demo/api/pipeline/charts")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "messages_per_minute",
        "retries_over_time",
        "dlq_trend",
        "success_series",
        "failure_series",
        "latency_ms",
        "top_event_types",
    }
    assert len(body["messages_per_minute"]["categories"]) == 30
    assert len(body["messages_per_minute"]["values"]) == 30
    assert len(body["top_event_types"]["categories"]) == 8


def test_pipeline_customer_flow_returns_six_ordered_steps():
    app.dependency_overrides[get_db_session] = _populated_sqlite_session
    try:
        response = client.get("/demo/api/pipeline/customer/PIPE-TEST-0001")
    finally:
        app.dependency_overrides.pop(get_db_session, None)

    assert response.status_code == 200
    steps = response.json()
    assert [step["label"] for step in steps] == [
        "Profile Created",
        "Events Produced",
        "Kafka Published",
        "Consumer Processed",
        "Stored",
        "Audit Logged",
    ]


def test_pipeline_customer_flow_not_found_returns_404():
    response = client.get("/demo/api/pipeline/customer/does-not-exist")

    assert response.status_code == 404


def test_pipeline_customer_flow_rejects_invalid_characters():
    response = client.get("/demo/api/pipeline/customer/bad%20id")

    assert response.status_code == 422


def test_pipeline_endpoints_are_excluded_from_openapi_schema():
    schema = client.get("/openapi.json").json()

    assert "/demo/pipeline" not in schema["paths"]
    assert "/demo/api/pipeline/summary" not in schema["paths"]
    assert "/demo/api/pipeline/customer/{customer_id}" not in schema["paths"]


def test_pipeline_monitor_does_not_affect_existing_api_v1_customers():
    """Regression: adding the pipeline monitor must not change the real,
    authenticated versioned endpoints."""

    unauthenticated = client.get("/api/v1/customers")
    assert unauthenticated.status_code == 401

    authenticated = client.get("/api/v1/customers", headers=AUTH_HEADERS)
    assert authenticated.status_code == 200
    assert isinstance(authenticated.json(), list)


def test_pipeline_monitor_does_not_affect_v1_demo_dashboard():
    """Regression: the pre-existing /demo dashboard keeps working unchanged."""

    response = client.get("/demo")
    assert response.status_code == 200
    assert "Demo Dashboard" in response.text

# ---------------------------------------------------------------------
# /demo/pipeline Control Center (interactive actions)
# ---------------------------------------------------------------------
#
# Every test below either resets the shared ENGINE singleton first (it's
# process-wide, exactly like the production "Reset Demo" button touches the
# same shared state every visitor sees) or is itself read-only.


def _shared_sqlite_session_override():
    """Unlike _empty_sqlite_session/_populated_sqlite_session (a fresh,
    throwaway in-memory DB per call), this keeps ONE in-memory database
    alive across multiple requests/sessions -- needed to verify that a
    POST /generate in one request actually persisted a row visible to a
    later query, the same way the real app's one long-lived engine behaves
    across per-request sessions."""

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )

    def _override():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    return _override, factory


def test_pipeline_generate_event_returns_a_happy_path_trace():
    ENGINE.reset()
    try:
        response = client.post("/demo/api/pipeline/generate")

        assert response.status_code == 200
        body = response.json()
        assert body["event"]["status"] == "success"
        assert body["replay"] is False
        assert [step["stage"] for step in body["steps"]] == [
            "Producer",
            "Kafka Topic",
            "Outbox",
            "Consumer",
            "PostgreSQL",
        ]
    finally:
        ENGINE.reset()


def test_pipeline_generate_event_does_not_require_api_key():
    ENGINE.reset()
    try:
        response = client.post("/demo/api/pipeline/generate")
        assert response.status_code == 200
    finally:
        ENGINE.reset()


def test_pipeline_replay_without_a_prior_event_returns_409():
    ENGINE.reset()
    try:
        response = client.post("/demo/api/pipeline/replay")
        assert response.status_code == 409
    finally:
        ENGINE.reset()


def test_pipeline_replay_reuses_the_last_event_without_creating_a_new_one():
    ENGINE.reset()
    try:
        generated = client.post("/demo/api/pipeline/generate").json()
        replayed = client.post("/demo/api/pipeline/replay").json()

        assert replayed["event"]["event_id"] == generated["event"]["event_id"]
        assert replayed["replay"] is True

        state = client.get("/demo/api/pipeline/state").json()
        assert state["generated_count"] == 1
    finally:
        ENGINE.reset()


def test_pipeline_inject_failure_rejects_an_invalid_failure_type():
    ENGINE.reset()
    try:
        response = client.post(
            "/demo/api/pipeline/failure", json={"failure_type": "not-a-real-type"}
        )
        assert response.status_code == 422
    finally:
        ENGINE.reset()


def test_pipeline_inject_failure_marks_the_relevant_stage_and_retry_queue():
    ENGINE.reset()
    try:
        response = client.post(
            "/demo/api/pipeline/failure", json={"failure_type": "kafka_timeout"}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["event"]["status"] == "failed"
        failed_stages = [s["stage"] for s in body["steps"] if s["status"] == "failed"]
        assert failed_stages == ["Kafka Topic"]

        state = client.get("/demo/api/pipeline/state").json()
        assert state["retry_queue_count"] == 1
        assert state["consumer_healthy"] is False
    finally:
        ENGINE.reset()


def test_pipeline_retry_without_a_failed_event_returns_409():
    ENGINE.reset()
    try:
        response = client.post("/demo/api/pipeline/retry")
        assert response.status_code == 409
    finally:
        ENGINE.reset()


def test_pipeline_full_journey_fail_retry_recover_retry_succeeds():
    ENGINE.reset()
    try:
        client.post("/demo/api/pipeline/generate")
        client.post(
            "/demo/api/pipeline/failure", json={"failure_type": "consumer_failure"}
        )

        still_failing = client.post("/demo/api/pipeline/retry").json()
        assert still_failing["event"]["status"] == "failed"
        assert still_failing["event"]["retry_count"] == 2

        recovered = client.post("/demo/api/pipeline/recover").json()
        assert recovered["consumer_healthy"] is True

        succeeded = client.post("/demo/api/pipeline/retry").json()
        assert succeeded["event"]["status"] == "success"
        assert succeeded["steps"][-1]["stage"] == "PostgreSQL"
    finally:
        ENGINE.reset()


def test_pipeline_repeated_retries_reach_the_dlq():
    ENGINE.reset()
    try:
        client.post(
            "/demo/api/pipeline/failure", json={"failure_type": "database_timeout"}
        )

        last_body = None
        for _ in range(6):
            last_body = client.post("/demo/api/pipeline/retry").json()
            if last_body["event"]["status"] == "dlq":
                break

        assert last_body is not None
        assert last_body["event"]["status"] == "dlq"

        state = client.get("/demo/api/pipeline/state").json()
        assert state["dlq_count"] == 1
        assert state["retry_queue_count"] == 0
    finally:
        ENGINE.reset()


def test_pipeline_recover_consumer_marks_the_consumer_service_card_healthy_again():
    ENGINE.reset()
    try:
        client.post(
            "/demo/api/pipeline/failure", json={"failure_type": "consumer_failure"}
        )
        services_while_unhealthy = client.get("/demo/api/pipeline/services").json()
        consumer_unhealthy = next(
            s for s in services_while_unhealthy if s["name"] == "Consumer"
        )
        assert consumer_unhealthy["status"] == "critical"

        client.post("/demo/api/pipeline/recover")

        services_after = client.get("/demo/api/pipeline/services").json()
        consumer_after = next(s for s in services_after if s["name"] == "Consumer")
        assert consumer_after["status"] != "critical"
    finally:
        ENGINE.reset()


def test_pipeline_reset_clears_state_back_to_idle():
    ENGINE.reset()
    try:
        client.post("/demo/api/pipeline/generate")
        client.post(
            "/demo/api/pipeline/failure", json={"failure_type": "consumer_failure"}
        )

        response = client.post("/demo/api/pipeline/reset")

        assert response.status_code == 200
        state = response.json()
        assert state == {
            "current_event": None,
            "consumer_healthy": True,
            "generated_count": 0,
            "success_count": 0,
            "failed_count": 0,
            "retry_queue_count": 0,
            "dlq_count": 0,
            "has_replayable_event": False,
        }
    finally:
        ENGINE.reset()


def test_pipeline_summary_overlay_reflects_engine_deltas():
    ENGINE.reset()
    try:
        before = client.get("/demo/api/pipeline/summary").json()

        client.post("/demo/api/pipeline/generate")
        client.post(
            "/demo/api/pipeline/failure", json={"failure_type": "kafka_timeout"}
        )

        after = client.get("/demo/api/pipeline/summary").json()

        # The ambient (time-based) half of these numbers ticks upward on
        # its own between the two calls, so assert the engine's
        # contribution is present (>=) rather than pinning an exact delta.
        assert after["kpis"]["messages_processed"] >= before["kpis"]["messages_processed"] + 1
        assert after["kpis"]["failed_events"] >= before["kpis"]["failed_events"] + 1
        assert after["kpis"]["retry_queue"] >= before["kpis"]["retry_queue"] + 1

        producer_before = next(s for s in before["stages"] if s["name"] == "Producer")
        producer_after = next(s for s in after["stages"] if s["name"] == "Producer")
        assert producer_after["count"] >= producer_before["count"] + 1
    finally:
        ENGINE.reset()


def test_pipeline_summary_at_idle_engine_state_matches_pre_engine_behavior():
    """Regression: with the Control Center untouched (freshly reset), the
    summary endpoint's output must be identical to what it was before this
    feature existed -- delta 0 must be a true no-op overlay."""

    ENGINE.reset()
    try:
        response = client.get("/demo/api/pipeline/summary")

        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"generated_at", "kpis", "stages", "simulated"}
        assert [stage["name"] for stage in body["stages"]] == [
            "Producer",
            "Kafka Topic",
            "Outbox",
            "Consumer",
            "Retry Queue",
            "Dead Letter Queue",
            "PostgreSQL",
        ]
    finally:
        ENGINE.reset()


def test_pipeline_control_center_endpoints_are_excluded_from_openapi_schema():
    schema = client.get("/openapi.json").json()

    for path in (
        "/demo/api/pipeline/generate",
        "/demo/api/pipeline/replay",
        "/demo/api/pipeline/failure",
        "/demo/api/pipeline/retry",
        "/demo/api/pipeline/recover",
        "/demo/api/pipeline/reset",
        "/demo/api/pipeline/state",
    ):
        assert path not in schema["paths"], path


def test_pipeline_generate_persists_a_real_outbox_row_when_db_available():
    ENGINE.reset()
    override, factory = _shared_sqlite_session_override()
    app.dependency_overrides[get_db_session] = override
    try:
        response = client.post("/demo/api/pipeline/generate")
        event_id = response.json()["event"]["event_id"]

        session = factory()
        try:
            row = OutboxRepository(session).get_by_event_id(event_id)
            assert row is not None
            assert row.status == "PUBLISHED"
        finally:
            session.close()
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        ENGINE.reset()


def test_pipeline_reset_deletes_the_outbox_rows_it_created():
    ENGINE.reset()
    override, factory = _shared_sqlite_session_override()
    app.dependency_overrides[get_db_session] = override
    try:
        response = client.post("/demo/api/pipeline/generate")
        event_id = response.json()["event"]["event_id"]

        client.post("/demo/api/pipeline/reset")

        session = factory()
        try:
            assert OutboxRepository(session).get_by_event_id(event_id) is None
        finally:
            session.close()
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        ENGINE.reset()


def test_pipeline_generate_falls_back_to_in_memory_when_db_unreachable():
    ENGINE.reset()
    app.dependency_overrides[get_db_session] = _unreachable_db_session
    try:
        response = client.post("/demo/api/pipeline/generate")

        assert response.status_code == 200
        assert response.json()["event"]["status"] == "success"
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        ENGINE.reset()


def test_pipeline_control_center_does_not_affect_existing_api_v1_customers():
    """Regression: the interactive engine must not touch the real,
    authenticated versioned endpoints."""

    ENGINE.reset()
    try:
        client.post("/demo/api/pipeline/generate")

        unauthenticated = client.get("/api/v1/customers")
        assert unauthenticated.status_code == 401

        authenticated = client.get("/api/v1/customers", headers=AUTH_HEADERS)
        assert authenticated.status_code == 200
    finally:
        ENGINE.reset()


def test_pipeline_engine_status_values_round_trip_through_the_api():
    ENGINE.reset()
    try:
        body = client.post("/demo/api/pipeline/generate").json()
        assert body["event"]["status"] == EventStatus.SUCCESS.value
    finally:
        ENGINE.reset()


# ---------------------------------------------------------------------
# GET /demo/api/pipeline/history (Customer360 Cloud workspace: Event
# Center / Audit Logs)
# ---------------------------------------------------------------------


def test_pipeline_history_is_empty_at_idle_engine_state():
    ENGINE.reset()
    try:
        response = client.get("/demo/api/pipeline/history")
        assert response.status_code == 200
        assert response.json() == []
    finally:
        ENGINE.reset()


def test_pipeline_history_reflects_generated_events_most_recent_first():
    ENGINE.reset()
    try:
        first = client.post("/demo/api/pipeline/generate").json()
        second = client.post("/demo/api/pipeline/generate").json()

        history = client.get("/demo/api/pipeline/history").json()

        assert [entry["event"]["event_id"] for entry in history[:2]] == [
            second["event"]["event_id"],
            first["event"]["event_id"],
        ]
        assert history[0]["steps"][0]["stage"] == "Producer"
    finally:
        ENGINE.reset()


def test_pipeline_history_respects_limit_query_param():
    ENGINE.reset()
    try:
        for _ in range(3):
            client.post("/demo/api/pipeline/generate")

        history = client.get("/demo/api/pipeline/history?limit=1").json()
        assert len(history) == 1
    finally:
        ENGINE.reset()


def test_pipeline_history_endpoint_excluded_from_openapi_schema():
    schema = client.get("/openapi.json").json()
    assert "/demo/api/pipeline/history" not in schema["paths"]


# ---------------------------------------------------------------------
# PATCH /demo/api/customers/{customer_id} (Customer360 Cloud workspace:
# Customers edit -> DB -> Outbox -> Pipeline -> Audit Logs)
# ---------------------------------------------------------------------


def _customer_update_session_override():
    """Same shape as _shared_sqlite_session_override, but pre-seeds one
    editable customer -- needed here (unlike the Control Center tests) so
    the PATCH under test has a real row to load, mutate, and persist."""

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )

    seed_session = factory()
    Customer360Repository(seed_session).create(
        Customer360Profile(
            customer_id="CLOUD-TEST-0001",
            first_name="Ada",
            last_name="Lovelace",
            email="ada@example.com",
            city="London",
            state="LDN",
            transaction_count=2,
            total_spend=42.0,
            average_transaction_value=21.0,
        )
    )
    seed_session.close()

    def _override():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    return _override, factory


def test_update_customer_persists_changes_and_returns_updated_profile():
    ENGINE.reset()
    override, factory = _customer_update_session_override()
    app.dependency_overrides[get_db_session] = override
    try:
        response = client.patch(
            "/demo/api/customers/CLOUD-TEST-0001",
            json={"city": "Manchester", "state": "MCR"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["profile"]["city"] == "Manchester"
        assert body["profile"]["state"] == "MCR"
        assert body["trace"]["event"]["event_type"] == "Address Changed"
        assert body["trace"]["event"]["customer_id"] == "CLOUD-TEST-0001"
        assert body["trace"]["event"]["status"] == "success"

        verify_session = factory()
        try:
            persisted = Customer360Repository(verify_session).get_by_customer_id(
                "CLOUD-TEST-0001"
            )
            assert persisted is not None
            assert persisted.city == "Manchester"
            assert persisted.state == "MCR"
        finally:
            verify_session.close()
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        ENGINE.reset()


def test_update_customer_email_change_is_labeled_email_changed():
    ENGINE.reset()
    override, _factory = _customer_update_session_override()
    app.dependency_overrides[get_db_session] = override
    try:
        response = client.patch(
            "/demo/api/customers/CLOUD-TEST-0001",
            json={"email": "ada.lovelace@example.com"},
        )
        assert response.status_code == 200
        assert response.json()["trace"]["event"]["event_type"] == "Email Changed"
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        ENGINE.reset()


def test_update_customer_name_only_change_is_labeled_customer_updated():
    ENGINE.reset()
    override, _factory = _customer_update_session_override()
    app.dependency_overrides[get_db_session] = override
    try:
        response = client.patch(
            "/demo/api/customers/CLOUD-TEST-0001",
            json={"first_name": "Augusta"},
        )
        assert response.status_code == 200
        assert response.json()["trace"]["event"]["event_type"] == "Customer Updated"
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        ENGINE.reset()


def test_update_customer_appears_in_pipeline_history():
    ENGINE.reset()
    override, _factory = _customer_update_session_override()
    app.dependency_overrides[get_db_session] = override
    try:
        client.patch(
            "/demo/api/customers/CLOUD-TEST-0001",
            json={"city": "Manchester"},
        )
        history = client.get("/demo/api/pipeline/history").json()
        assert history[0]["event"]["customer_id"] == "CLOUD-TEST-0001"
        assert history[0]["event"]["event_type"] == "Address Changed"
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        ENGINE.reset()


def test_update_customer_not_found_returns_404():
    ENGINE.reset()
    override, _factory = _customer_update_session_override()
    app.dependency_overrides[get_db_session] = override
    try:
        response = client.patch(
            "/demo/api/customers/does-not-exist",
            json={"city": "Nowhere"},
        )
        assert response.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        ENGINE.reset()


def test_update_customer_rejects_invalid_email():
    ENGINE.reset()
    override, _factory = _customer_update_session_override()
    app.dependency_overrides[get_db_session] = override
    try:
        response = client.patch(
            "/demo/api/customers/CLOUD-TEST-0001",
            json={"email": "not-an-email"},
        )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        ENGINE.reset()


def test_update_customer_rejects_blank_field():
    ENGINE.reset()
    override, _factory = _customer_update_session_override()
    app.dependency_overrides[get_db_session] = override
    try:
        response = client.patch(
            "/demo/api/customers/CLOUD-TEST-0001",
            json={"first_name": ""},
        )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        ENGINE.reset()


def test_update_customer_rejects_invalid_customer_id_characters():
    response = client.patch(
        "/demo/api/customers/bad%20id",
        json={"city": "Nowhere"},
    )
    assert response.status_code == 422


def test_update_customer_does_not_require_api_key():
    ENGINE.reset()
    override, _factory = _customer_update_session_override()
    app.dependency_overrides[get_db_session] = override
    try:
        response = client.patch(
            "/demo/api/customers/CLOUD-TEST-0001",
            json={"city": "Manchester"},
        )
        assert response.status_code == 200
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        ENGINE.reset()


def test_update_customer_endpoint_excluded_from_openapi_schema():
    schema = client.get("/openapi.json").json()
    assert "/demo/api/customers/{customer_id}" not in schema["paths"]


def test_update_customer_persists_a_real_outbox_row_when_db_available():
    ENGINE.reset()
    override, _factory = _customer_update_session_override()
    app.dependency_overrides[get_db_session] = override
    try:
        response = client.patch(
            "/demo/api/customers/CLOUD-TEST-0001",
            json={"city": "Manchester"},
        )
        event_id = response.json()["trace"]["event"]["event_id"]

        verify_session = _factory()
        try:
            outbox_row = OutboxRepository(verify_session).get_by_event_id(event_id)
            assert outbox_row is not None
            assert outbox_row.status == "PUBLISHED"
        finally:
            verify_session.close()
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        ENGINE.reset()


# ---------------------------------------------------------------------
# PATCH /demo/api/customers/{customer_id} -- v3.0 additions: status/
# archive, tags, correlation_id, and the before/after audit trail
# ---------------------------------------------------------------------


def test_new_customer_defaults_to_active_status_and_no_tags():
    ENGINE.reset()
    override, _factory = _customer_update_session_override()
    app.dependency_overrides[get_db_session] = override
    try:
        response = client.get("/demo/api/customers/CLOUD-TEST-0001")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "active"
        assert body["tags"] == []
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        ENGINE.reset()


def test_update_customer_can_archive_and_is_labeled_account_archived():
    ENGINE.reset()
    override, _factory = _customer_update_session_override()
    app.dependency_overrides[get_db_session] = override
    try:
        response = client.patch(
            "/demo/api/customers/CLOUD-TEST-0001",
            json={"status": "archived"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["profile"]["status"] == "archived"
        assert body["trace"]["event"]["event_type"] == "Account Archived"
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        ENGINE.reset()


def test_update_customer_can_restore_an_archived_customer():
    ENGINE.reset()
    override, _factory = _customer_update_session_override()
    app.dependency_overrides[get_db_session] = override
    try:
        client.patch(
            "/demo/api/customers/CLOUD-TEST-0001",
            json={"status": "archived"},
        )
        response = client.patch(
            "/demo/api/customers/CLOUD-TEST-0001",
            json={"status": "active"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["profile"]["status"] == "active"
        assert body["trace"]["event"]["event_type"] == "Customer Updated"
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        ENGINE.reset()


def test_update_customer_rejects_invalid_status_value():
    ENGINE.reset()
    override, _factory = _customer_update_session_override()
    app.dependency_overrides[get_db_session] = override
    try:
        response = client.patch(
            "/demo/api/customers/CLOUD-TEST-0001",
            json={"status": "banned"},
        )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        ENGINE.reset()


def test_update_customer_tags_are_deduplicated_and_sorted():
    ENGINE.reset()
    override, _factory = _customer_update_session_override()
    app.dependency_overrides[get_db_session] = override
    try:
        response = client.patch(
            "/demo/api/customers/CLOUD-TEST-0001",
            json={"tags": ["vip", "enterprise", "vip"]},
        )
        assert response.status_code == 200
        assert response.json()["profile"]["tags"] == ["enterprise", "vip"]
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        ENGINE.reset()


def test_update_customer_rejects_too_many_tags():
    ENGINE.reset()
    override, _factory = _customer_update_session_override()
    app.dependency_overrides[get_db_session] = override
    try:
        response = client.patch(
            "/demo/api/customers/CLOUD-TEST-0001",
            json={"tags": [f"tag-{i}" for i in range(21)]},
        )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        ENGINE.reset()


def test_update_customer_response_includes_correlation_id():
    ENGINE.reset()
    override, _factory = _customer_update_session_override()
    app.dependency_overrides[get_db_session] = override
    try:
        response = client.patch(
            "/demo/api/customers/CLOUD-TEST-0001",
            json={"city": "Manchester"},
        )
        event = response.json()["trace"]["event"]
        assert event["correlation_id"] == f"corr-{event['event_id']}"
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        ENGINE.reset()


def test_update_customer_includes_audit_before_after_and_changes():
    ENGINE.reset()
    override, _factory = _customer_update_session_override()
    app.dependency_overrides[get_db_session] = override
    try:
        response = client.patch(
            "/demo/api/customers/CLOUD-TEST-0001",
            json={"city": "Manchester", "state": "MCR"},
        )
        audit = response.json()["trace"]["audit"]
        assert audit["actor"] == "Workspace User"
        assert set(audit["changes"]) == {"city", "state"}
        assert audit["before"]["city"] == "London"
        assert audit["before"]["state"] == "LDN"
        assert audit["after"]["city"] == "Manchester"
        assert audit["after"]["state"] == "MCR"
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        ENGINE.reset()


def test_update_customer_with_no_actual_changes_has_no_audit():
    ENGINE.reset()
    override, _factory = _customer_update_session_override()
    app.dependency_overrides[get_db_session] = override
    try:
        response = client.patch(
            "/demo/api/customers/CLOUD-TEST-0001",
            json={"first_name": "Ada"},
        )
        assert response.status_code == 200
        assert response.json()["trace"]["audit"] is None
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        ENGINE.reset()


def test_pipeline_history_entries_from_control_center_have_no_audit():
    ENGINE.reset()
    try:
        response = client.post("/demo/api/pipeline/generate")
        assert response.json()["audit"] is None

        history = client.get("/demo/api/pipeline/history").json()
        assert history[0]["audit"] is None
    finally:
        ENGINE.reset()


def test_pipeline_history_entries_include_correlation_id():
    ENGINE.reset()
    try:
        generated = client.post("/demo/api/pipeline/generate").json()
        history = client.get("/demo/api/pipeline/history").json()
        assert history[0]["event"]["correlation_id"] == (
            f"corr-{generated['event']['event_id']}"
        )
    finally:
        ENGINE.reset()
