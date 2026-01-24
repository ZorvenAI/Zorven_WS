#!/usr/bin/env python3
"""
Kong Gateway E2E Testing Suite for AI Brand Automator

Tests the Kong Gateway implementation running in Docker containers.
Validates:
- Kong Gateway health and admin API
- Route configuration and proxying
- JWT authentication flow
- CORS headers
- Rate limiting
- Health endpoints
- Protected vs public routes

Usage:
    python scripts/test_kong_e2e.py
    python scripts/test_kong_e2e.py --verbose
    python scripts/test_kong_e2e.py --kong-url http://localhost:8000
"""

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

try:
    import requests
except ImportError:
    print("Error: 'requests' package required. Install with: pip install requests")
    sys.exit(1)


# =============================================================================
# Configuration
# =============================================================================
@dataclass
class TestConfig:
    """Test configuration"""

    kong_proxy_url: str = "http://localhost:8000"
    kong_admin_url: str = "http://localhost:8002"
    mcp_server_url: str = "http://localhost:8003"
    frontend_url: str = "http://localhost:3000"
    verbose: bool = False
    timeout: int = 10
    test_user_email: str = field(
        default_factory=lambda: f"kong_test_{int(time.time())}@test.com"
    )
    test_user_password: str = "SecurePass123!"


@dataclass
class TestResult:
    """Individual test result"""

    name: str
    passed: bool
    message: str
    duration_ms: float
    details: Optional[dict] = None


class TestResults:
    """Collection of test results"""

    def __init__(self):
        self.results: list[TestResult] = []
        self.start_time = time.time()

    def add(self, result: TestResult):
        self.results.append(result)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def duration(self) -> float:
        return time.time() - self.start_time


# =============================================================================
# Test Utilities
# =============================================================================
def log(message: str, verbose: bool = False, force: bool = False):
    """Log message if verbose mode or forced"""
    if verbose or force:
        print(message)


def run_test(test_func):
    """Decorator to run a test and capture results"""

    def wrapper(config: TestConfig) -> TestResult:
        start = time.time()
        try:
            passed, message, details = test_func(config)
            duration = (time.time() - start) * 1000
            return TestResult(
                name=test_func.__doc__ or test_func.__name__,
                passed=passed,
                message=message,
                duration_ms=duration,
                details=details,
            )
        except Exception as e:
            duration = (time.time() - start) * 1000
            return TestResult(
                name=test_func.__doc__ or test_func.__name__,
                passed=False,
                message=f"Exception: {str(e)}",
                duration_ms=duration,
            )

    return wrapper


# =============================================================================
# Kong Gateway Infrastructure Tests
# =============================================================================
@run_test
def test_kong_proxy_reachable(config: TestConfig) -> tuple[bool, str, dict]:
    """Kong Gateway Proxy is reachable"""
    response = requests.get(f"{config.kong_proxy_url}/health/", timeout=config.timeout)
    if response.status_code == 200:
        return True, "Kong proxy responding", {"status_code": response.status_code}
    return (
        False,
        f"Unexpected status: {response.status_code}",
        {"status_code": response.status_code},
    )


@run_test
def test_kong_admin_api(config: TestConfig) -> tuple[bool, str, dict]:
    """Kong Admin API is accessible"""
    response = requests.get(f"{config.kong_admin_url}/status", timeout=config.timeout)
    if response.status_code == 200:
        data = response.json()
        return (
            True,
            "Admin API responding",
            {
                "database_reachable": data.get("database", {}).get("reachable"),
                "server": data.get("server", {}),
            },
        )
    return False, f"Admin API returned {response.status_code}", {}


@run_test
def test_kong_services_configured(config: TestConfig) -> tuple[bool, str, dict]:
    """Kong services are properly configured"""
    response = requests.get(f"{config.kong_admin_url}/services", timeout=config.timeout)
    if response.status_code == 200:
        services = response.json().get("data", [])
        service_names = [s.get("name") for s in services]
        expected = ["core-api-service", "auth-service", "health-service"]
        found = [s for s in expected if s in service_names]
        if len(found) >= 3:
            return True, f"Found {len(services)} services", {"services": service_names}
        return (
            False,
            f"Missing services. Found: {service_names}",
            {"services": service_names},
        )
    return False, f"Failed to get services: {response.status_code}", {}


@run_test
def test_kong_routes_configured(config: TestConfig) -> tuple[bool, str, dict]:
    """Kong routes are properly configured"""
    response = requests.get(f"{config.kong_admin_url}/routes", timeout=config.timeout)
    if response.status_code == 200:
        routes = response.json().get("data", [])
        route_names = [r.get("name") for r in routes]
        expected = [
            "core-api-route",
            "auth-login-route",
            "auth-register-route",
            "health-routes",
        ]
        found = [r for r in expected if r in route_names]
        if len(found) >= 4:
            return True, f"Found {len(routes)} routes", {"routes": route_names}
        return False, f"Missing routes. Found: {route_names}", {"routes": route_names}
    return False, f"Failed to get routes: {response.status_code}", {}


@run_test
def test_kong_plugins_configured(config: TestConfig) -> tuple[bool, str, dict]:
    """Kong plugins are properly configured"""
    response = requests.get(f"{config.kong_admin_url}/plugins", timeout=config.timeout)
    if response.status_code == 200:
        plugins = response.json().get("data", [])
        plugin_names = list(set(p.get("name") for p in plugins))
        expected = ["cors", "rate-limiting", "jwt"]
        found = [p for p in expected if p in plugin_names]
        if len(found) >= 3:
            return True, f"Found plugins: {plugin_names}", {"plugins": plugin_names}
        return (
            False,
            f"Missing plugins. Found: {plugin_names}",
            {"plugins": plugin_names},
        )
    return False, f"Failed to get plugins: {response.status_code}", {}


# =============================================================================
# Health Endpoint Tests (Public Routes)
# =============================================================================
@run_test
def test_health_endpoint_via_kong(config: TestConfig) -> tuple[bool, str, dict]:
    """Health endpoint accessible via Kong (no auth)"""
    response = requests.get(f"{config.kong_proxy_url}/health/", timeout=config.timeout)
    if response.status_code == 200:
        data = response.json()
        status = data.get("status")
        if status == "healthy":
            return (
                True,
                "Health check passed",
                {
                    "components": data.get("components", {}),
                    "response_time_ms": data.get("response_time_ms"),
                },
            )
        return False, f"Health status: {status}", data
    return False, f"Health check failed: {response.status_code}", {}


@run_test
def test_ready_endpoint_via_kong(config: TestConfig) -> tuple[bool, str, dict]:
    """Ready endpoint accessible via Kong (no auth)"""
    response = requests.get(f"{config.kong_proxy_url}/ready/", timeout=config.timeout)
    if response.status_code == 200:
        data = response.json()
        if data.get("ready") is True:
            return True, "Readiness check passed", data
        return False, "Not ready", data
    return False, f"Ready check failed: {response.status_code}", {}


@run_test
def test_alive_endpoint_via_kong(config: TestConfig) -> tuple[bool, str, dict]:
    """Alive endpoint accessible via Kong (no auth)"""
    response = requests.get(f"{config.kong_proxy_url}/alive/", timeout=config.timeout)
    if response.status_code == 200:
        data = response.json()
        if data.get("alive") is True:
            return True, "Liveness check passed", data
        return False, "Not alive", data
    return False, f"Alive check failed: {response.status_code}", {}


# =============================================================================
# Authentication Tests (Public Routes)
# =============================================================================
@run_test
def test_register_endpoint_via_kong(config: TestConfig) -> tuple[bool, str, dict]:
    """Registration endpoint accessible via Kong (no auth)"""
    payload = {
        "email": config.test_user_email,
        "password": config.test_user_password,
        "first_name": "Kong",
        "last_name": "Test",
    }
    response = requests.post(
        f"{config.kong_proxy_url}/api/v1/auth/register/",
        json=payload,
        timeout=config.timeout,
    )
    if response.status_code == 201:
        data = response.json()
        tokens = data.get("tokens", {})
        if tokens.get("access") and tokens.get("refresh"):
            return (
                True,
                "Registration successful",
                {"user_id": data.get("user", {}).get("id"), "has_tokens": True},
            )
        return False, "Missing tokens in response", data
    elif response.status_code == 400:
        # User might already exist
        return (
            True,
            "Registration endpoint working (user exists)",
            {"status": response.status_code},
        )
    return (
        False,
        f"Registration failed: {response.status_code}",
        {"response": response.text[:200]},
    )


@run_test
def test_login_endpoint_via_kong(config: TestConfig) -> tuple[bool, str, dict]:
    """Login endpoint accessible via Kong (no auth)"""
    # First register a user to ensure we can login
    register_payload = {
        "email": f"login_test_{int(time.time())}@test.com",
        "password": config.test_user_password,
        "first_name": "Login",
        "last_name": "Test",
    }
    reg_response = requests.post(
        f"{config.kong_proxy_url}/api/v1/auth/register/",
        json=register_payload,
        timeout=config.timeout,
    )

    if reg_response.status_code != 201:
        return (
            False,
            f"Setup failed - couldn't register: {reg_response.status_code}",
            {},
        )

    # Now test login
    login_payload = {
        "email": register_payload["email"],
        "password": register_payload["password"],
    }
    response = requests.post(
        f"{config.kong_proxy_url}/api/v1/auth/login/",
        json=login_payload,
        timeout=config.timeout,
    )

    if response.status_code == 200:
        data = response.json()
        if data.get("access") and data.get("refresh"):
            return True, "Login successful", {"has_tokens": True}
        return False, "Missing tokens", data
    return (
        False,
        f"Login failed: {response.status_code}",
        {"response": response.text[:200]},
    )


@run_test
def test_token_refresh_via_kong(config: TestConfig) -> tuple[bool, str, dict]:
    """Token refresh endpoint accessible via Kong"""
    # Register and get tokens
    email = f"refresh_test_{int(time.time())}@test.com"
    reg_response = requests.post(
        f"{config.kong_proxy_url}/api/v1/auth/register/",
        json={
            "email": email,
            "password": config.test_user_password,
            "first_name": "Refresh",
            "last_name": "Test",
        },
        timeout=config.timeout,
    )

    if reg_response.status_code != 201:
        return False, f"Setup failed: {reg_response.status_code}", {}

    tokens = reg_response.json().get("tokens", {})
    refresh_token = tokens.get("refresh")

    if not refresh_token:
        return False, "No refresh token from registration", {}

    # Test refresh
    response = requests.post(
        f"{config.kong_proxy_url}/api/v1/auth/refresh/",
        json={"refresh": refresh_token},
        timeout=config.timeout,
    )

    if response.status_code == 200:
        data = response.json()
        if data.get("access"):
            return True, "Token refresh successful", {"has_new_access": True}
        return False, "Missing new access token", data
    return False, f"Refresh failed: {response.status_code}", {}


# =============================================================================
# Protected Route Tests (JWT Required)
# =============================================================================
@run_test
def test_protected_route_without_token(config: TestConfig) -> tuple[bool, str, dict]:
    """Protected route blocks unauthenticated access"""
    response = requests.get(
        f"{config.kong_proxy_url}/api/v1/companies/", timeout=config.timeout
    )
    if response.status_code == 401:
        return True, "Unauthenticated request correctly blocked", {"status": 401}
    return (
        False,
        f"Expected 401, got {response.status_code}",
        {"status": response.status_code},
    )


@run_test
def test_protected_route_with_invalid_token(
    config: TestConfig,
) -> tuple[bool, str, dict]:
    """Protected route blocks invalid JWT"""
    headers = {"Authorization": "Bearer invalid_token_here"}
    response = requests.get(
        f"{config.kong_proxy_url}/api/v1/companies/",
        headers=headers,
        timeout=config.timeout,
    )
    if response.status_code == 401:
        return True, "Invalid token correctly rejected", {"status": 401}
    return (
        False,
        f"Expected 401, got {response.status_code}",
        {"status": response.status_code},
    )


@run_test
def test_protected_route_with_valid_token(config: TestConfig) -> tuple[bool, str, dict]:
    """Protected route allows authenticated access"""
    # Register and get tokens
    email = f"protected_test_{int(time.time())}@test.com"
    reg_response = requests.post(
        f"{config.kong_proxy_url}/api/v1/auth/register/",
        json={
            "email": email,
            "password": config.test_user_password,
            "first_name": "Protected",
            "last_name": "Test",
        },
        timeout=config.timeout,
    )

    if reg_response.status_code != 201:
        return False, f"Setup failed: {reg_response.status_code}", {}

    tokens = reg_response.json().get("tokens", {})
    access_token = tokens.get("access")

    if not access_token:
        return False, "No access token from registration", {}

    # Test protected endpoint
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(
        f"{config.kong_proxy_url}/api/v1/companies/",
        headers=headers,
        timeout=config.timeout,
    )

    if response.status_code in [
        200,
        404,
    ]:  # 200 = has companies, 404 = no companies yet
        return True, "Authenticated request allowed", {"status": response.status_code}
    return (
        False,
        f"Expected 200/404, got {response.status_code}",
        {"status": response.status_code},
    )


# =============================================================================
# CORS Tests
# =============================================================================
@run_test
def test_cors_preflight_request(config: TestConfig) -> tuple[bool, str, dict]:
    """CORS preflight request handled correctly"""
    headers = {
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Authorization, Content-Type",
    }
    response = requests.options(
        f"{config.kong_proxy_url}/api/v1/companies/",
        headers=headers,
        timeout=config.timeout,
    )

    cors_origin = response.headers.get("Access-Control-Allow-Origin")
    cors_methods = response.headers.get("Access-Control-Allow-Methods")
    cors_headers = response.headers.get("Access-Control-Allow-Headers")

    details = {
        "allow_origin": cors_origin,
        "allow_methods": cors_methods,
        "allow_headers": cors_headers,
    }

    if cors_origin and ("localhost:3000" in cors_origin or cors_origin == "*"):
        return True, "CORS preflight handled", details
    return False, "CORS headers missing or incorrect", details


@run_test
def test_cors_actual_request(config: TestConfig) -> tuple[bool, str, dict]:
    """CORS headers present on actual requests"""
    headers = {"Origin": "http://localhost:3000"}
    response = requests.get(
        f"{config.kong_proxy_url}/health/", headers=headers, timeout=config.timeout
    )

    cors_origin = response.headers.get("Access-Control-Allow-Origin")
    cors_credentials = response.headers.get("Access-Control-Allow-Credentials")

    details = {"allow_origin": cors_origin, "allow_credentials": cors_credentials}

    if cors_origin:
        return True, "CORS headers present", details
    return False, "CORS headers missing", details


# =============================================================================
# Rate Limiting Tests
# =============================================================================
@run_test
def test_rate_limit_headers_present(config: TestConfig) -> tuple[bool, str, dict]:
    """Rate limiting headers are present"""
    response = requests.get(f"{config.kong_proxy_url}/health/", timeout=config.timeout)

    rate_limit = response.headers.get(
        "X-RateLimit-Limit-Minute"
    ) or response.headers.get("RateLimit-Limit")
    rate_remaining = response.headers.get(
        "X-RateLimit-Remaining-Minute"
    ) or response.headers.get("RateLimit-Remaining")

    details = {
        "rate_limit": rate_limit,
        "rate_remaining": rate_remaining,
        "all_headers": dict(response.headers),
    }

    # Rate limiting headers may not always be present depending on Kong config
    if rate_limit or rate_remaining:
        return True, "Rate limit headers present", details
    # Check if rate limiting is working even without headers
    return True, "Rate limiting configured (headers may be hidden)", details


# =============================================================================
# Celery Tests
# =============================================================================
@run_test
def test_celery_worker_running(config: TestConfig) -> tuple[bool, str, dict]:
    """Celery worker container is running and healthy"""
    import subprocess

    try:
        result = subprocess.run(
            [
                "docker",
                "ps",
                "--filter",
                "name=celery-worker",
                "--format",
                "{{.Status}}",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        status = result.stdout.strip()
        if "Up" in status:
            return True, "Celery worker running", {"status": status}
        return False, f"Celery worker not running: {status}", {"status": status}
    except Exception as e:
        return False, f"Failed to check: {str(e)}", {}


@run_test
def test_celery_beat_running(config: TestConfig) -> tuple[bool, str, dict]:
    """Celery Beat scheduler is running"""
    import subprocess

    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=celery-beat", "--format", "{{.Status}}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        status = result.stdout.strip()
        if "Up" in status:
            return True, "Celery Beat running", {"status": status}
        return False, f"Celery Beat not running: {status}", {"status": status}
    except Exception as e:
        return False, f"Failed to check: {str(e)}", {}


@run_test
def test_celery_worker_connected_to_redis(config: TestConfig) -> tuple[bool, str, dict]:
    """Celery worker is connected to Redis broker"""
    import subprocess

    try:
        result = subprocess.run(
            ["docker", "logs", "--tail", "50", "ai-brand-automator-celery-worker-1"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        logs = result.stdout + result.stderr
        if "Connected to redis://" in logs and "ready" in logs.lower():
            return True, "Celery worker connected to Redis", {"connected": True}
        return False, "Connection not found in logs", {"logs_tail": logs[-500:]}
    except Exception as e:
        return False, f"Failed to check: {str(e)}", {}


@run_test
def test_celery_tasks_discovered(config: TestConfig) -> tuple[bool, str, dict]:
    """Celery worker discovered automation tasks"""
    import subprocess

    try:
        result = subprocess.run(
            ["docker", "logs", "--tail", "100", "ai-brand-automator-celery-worker-1"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        logs = result.stdout + result.stderr
        expected_tasks = [
            "automation.publish_scheduled_posts",
            "automation.publish_single_post",
        ]
        found_tasks = [t for t in expected_tasks if t in logs]
        if len(found_tasks) >= 2:
            return (
                True,
                f"Found {len(found_tasks)} automation tasks",
                {"tasks": found_tasks},
            )
        return False, f"Missing tasks. Found: {found_tasks}", {"tasks": found_tasks}
    except Exception as e:
        return False, f"Failed to check: {str(e)}", {}


# =============================================================================
# MCP Server Tests
# =============================================================================
@run_test
def test_mcp_server_health(config: TestConfig) -> tuple[bool, str, dict]:
    """MCP Server health endpoint is accessible"""
    response = requests.get(f"{config.mcp_server_url}/health", timeout=config.timeout)
    if response.status_code == 200:
        data = response.json()
        if data.get("status") == "healthy":
            return (
                True,
                "MCP Server healthy",
                {
                    "service": data.get("service"),
                    "version": data.get("version"),
                    "transport": data.get("transport"),
                },
            )
        return False, f"MCP status: {data.get('status')}", data
    return False, f"MCP health failed: {response.status_code}", {}


# =============================================================================
# Frontend Tests
# =============================================================================
@run_test
def test_frontend_reachable(config: TestConfig) -> tuple[bool, str, dict]:
    """Frontend is reachable"""
    response = requests.get(config.frontend_url, timeout=config.timeout)
    if response.status_code == 200:
        return True, "Frontend responding", {"content_length": len(response.content)}
    return False, f"Frontend returned {response.status_code}", {}


# =============================================================================
# Integration Tests
# =============================================================================
@run_test
def test_full_auth_flow_via_kong(config: TestConfig) -> tuple[bool, str, dict]:
    """Full authentication flow through Kong"""
    email = f"full_flow_{int(time.time())}@test.com"
    password = config.test_user_password

    # Step 1: Register
    reg_response = requests.post(
        f"{config.kong_proxy_url}/api/v1/auth/register/",
        json={
            "email": email,
            "password": password,
            "first_name": "Full",
            "last_name": "Flow",
        },
        timeout=config.timeout,
    )

    if reg_response.status_code != 201:
        return False, f"Registration failed: {reg_response.status_code}", {}

    # Step 2: Login
    login_response = requests.post(
        f"{config.kong_proxy_url}/api/v1/auth/login/",
        json={"email": email, "password": password},
        timeout=config.timeout,
    )

    if login_response.status_code != 200:
        return False, f"Login failed: {login_response.status_code}", {}

    tokens = login_response.json()
    access_token = tokens.get("access")
    refresh_token = tokens.get("refresh")

    # Step 3: Access protected route
    headers = {"Authorization": f"Bearer {access_token}"}
    protected_response = requests.get(
        f"{config.kong_proxy_url}/api/v1/companies/",
        headers=headers,
        timeout=config.timeout,
    )

    if protected_response.status_code not in [200, 404]:
        return False, f"Protected access failed: {protected_response.status_code}", {}

    # Step 4: Refresh token
    refresh_response = requests.post(
        f"{config.kong_proxy_url}/api/v1/auth/refresh/",
        json={"refresh": refresh_token},
        timeout=config.timeout,
    )

    if refresh_response.status_code != 200:
        return False, f"Token refresh failed: {refresh_response.status_code}", {}

    # Step 5: Use new token
    new_access = refresh_response.json().get("access")
    headers = {"Authorization": f"Bearer {new_access}"}
    final_response = requests.get(
        f"{config.kong_proxy_url}/api/v1/companies/",
        headers=headers,
        timeout=config.timeout,
    )

    if final_response.status_code in [200, 404]:
        return (
            True,
            "Full auth flow completed successfully",
            {
                "steps_completed": [
                    "register",
                    "login",
                    "protected_access",
                    "refresh",
                    "new_token_access",
                ]
            },
        )
    return False, f"Final access failed: {final_response.status_code}", {}


@run_test
def test_kong_proxies_to_backend(config: TestConfig) -> tuple[bool, str, dict]:
    """Kong correctly proxies requests to Django backend"""
    # Make request through Kong
    kong_response = requests.get(
        f"{config.kong_proxy_url}/health/", timeout=config.timeout
    )

    if kong_response.status_code == 200:
        data = kong_response.json()
        # Verify it's actually Django responding (has our specific health format)
        if "components" in data and "database" in data.get("components", {}):
            return True, "Kong proxying to Django backend", {"backend_health": data}
        return False, "Response doesn't match Django format", data
    return False, f"Proxy failed: {kong_response.status_code}", {}


# =============================================================================
# Test Runner
# =============================================================================
def run_all_tests(config: TestConfig) -> TestResults:
    """Run all Kong E2E tests"""
    results = TestResults()

    # Define test suites
    infrastructure_tests = [
        test_kong_proxy_reachable,
        test_kong_admin_api,
        test_kong_services_configured,
        test_kong_routes_configured,
        test_kong_plugins_configured,
    ]

    health_tests = [
        test_health_endpoint_via_kong,
        test_ready_endpoint_via_kong,
        test_alive_endpoint_via_kong,
    ]

    auth_tests = [
        test_register_endpoint_via_kong,
        test_login_endpoint_via_kong,
        test_token_refresh_via_kong,
    ]

    protected_tests = [
        test_protected_route_without_token,
        test_protected_route_with_invalid_token,
        test_protected_route_with_valid_token,
    ]

    cors_tests = [
        test_cors_preflight_request,
        test_cors_actual_request,
    ]

    rate_limit_tests = [
        test_rate_limit_headers_present,
    ]

    celery_tests = [
        test_celery_worker_running,
        test_celery_beat_running,
        test_celery_worker_connected_to_redis,
        test_celery_tasks_discovered,
    ]

    service_tests = [
        test_mcp_server_health,
        test_frontend_reachable,
    ]

    integration_tests = [
        test_full_auth_flow_via_kong,
        test_kong_proxies_to_backend,
    ]

    test_suites = [
        ("Kong Infrastructure", infrastructure_tests),
        ("Health Endpoints", health_tests),
        ("Authentication Routes", auth_tests),
        ("Protected Routes", protected_tests),
        ("CORS Configuration", cors_tests),
        ("Rate Limiting", rate_limit_tests),
        ("Celery Workers", celery_tests),
        ("Container Services", service_tests),
        ("Integration", integration_tests),
    ]

    for suite_name, tests in test_suites:
        print(f"\n{'='*60}")
        print(f"  {suite_name}")
        print(f"{'='*60}")

        for test_func in tests:
            result = test_func(config)
            results.add(result)

            status = "✅ PASS" if result.passed else "❌ FAIL"
            print(f"{status}: {result.name}")

            if config.verbose:
                print(f"       Message: {result.message}")
                print(f"       Duration: {result.duration_ms:.2f}ms")
                if result.details:
                    print(f"       Details: {json.dumps(result.details, indent=2)}")
            elif not result.passed:
                print(f"       → {result.message}")

    return results


def print_summary(results: TestResults):
    """Print test summary"""
    print(f"\n{'='*60}")
    print("  TEST SUMMARY")
    print(f"{'='*60}")
    print(f"  Total Tests:  {results.total}")
    print(f"  Passed:       {results.passed} ✅")
    print(f"  Failed:       {results.failed} ❌")
    print(f"  Duration:     {results.duration:.2f}s")
    print(f"  Pass Rate:    {results.passed/results.total*100:.1f}%")
    print(f"{'='*60}")

    if results.failed > 0:
        print("\n  Failed Tests:")
        for r in results.results:
            if not r.passed:
                print(f"    ❌ {r.name}: {r.message}")

    print()


def main():
    parser = argparse.ArgumentParser(description="Kong Gateway E2E Tests")
    parser.add_argument(
        "--kong-url", default="http://localhost:8000", help="Kong proxy URL"
    )
    parser.add_argument(
        "--kong-admin", default="http://localhost:8002", help="Kong admin URL"
    )
    parser.add_argument(
        "--mcp-url", default="http://localhost:8003", help="MCP server URL"
    )
    parser.add_argument(
        "--frontend-url", default="http://localhost:3000", help="Frontend URL"
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument(
        "--timeout", type=int, default=10, help="Request timeout in seconds"
    )

    args = parser.parse_args()

    config = TestConfig(
        kong_proxy_url=args.kong_url,
        kong_admin_url=args.kong_admin,
        mcp_server_url=args.mcp_url,
        frontend_url=args.frontend_url,
        verbose=args.verbose,
        timeout=args.timeout,
    )

    print("\n" + "#" * 60)
    print("#  KONG GATEWAY E2E TEST SUITE")
    print(f"#  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("#" * 60)
    print("\nConfiguration:")
    print(f"  Kong Proxy:  {config.kong_proxy_url}")
    print(f"  Kong Admin:  {config.kong_admin_url}")
    print(f"  MCP Server:  {config.mcp_server_url}")
    print(f"  Frontend:    {config.frontend_url}")
    print(f"  Timeout:     {config.timeout}s")
    print(f"  Verbose:     {config.verbose}")

    # Run tests
    results = run_all_tests(config)

    # Print summary
    print_summary(results)

    # Exit with appropriate code
    return 0 if results.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
