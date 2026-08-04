from __future__ import annotations

import httpx
import pytest

from modules.admin.infrastructure.connection_tester import ConnectionTestStatus, test_connection as run_connection_test


def _client_for(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_no_base_url_returns_not_configured():
    result = await run_connection_test(base_url=None, auth_type=None, credential=None)

    assert result.status is ConnectionTestStatus.NOT_CONFIGURED
    assert result.success is False


@pytest.mark.asyncio
async def test_200_is_healthy():
    def handler(request):
        return httpx.Response(200, json={"ok": True})

    result = await run_connection_test(
        base_url="https://api.example.com/ping", auth_type=None, credential=None, client=_client_for(handler)
    )

    assert result.status is ConnectionTestStatus.HEALTHY
    assert result.success is True
    assert result.http_status == 200
    assert result.latency_ms is not None


@pytest.mark.asyncio
async def test_401_is_unauthorized():
    def handler(request):
        return httpx.Response(401)

    result = await run_connection_test(
        base_url="https://api.example.com/ping", auth_type="bearer", credential="bad-key", client=_client_for(handler)
    )

    assert result.status is ConnectionTestStatus.UNAUTHORIZED
    assert result.success is False


@pytest.mark.asyncio
async def test_429_is_rate_limited():
    def handler(request):
        return httpx.Response(429)

    result = await run_connection_test(
        base_url="https://api.example.com/ping", auth_type=None, credential=None, client=_client_for(handler)
    )

    assert result.status is ConnectionTestStatus.RATE_LIMITED


@pytest.mark.asyncio
async def test_500_is_warning_not_offline():
    def handler(request):
        return httpx.Response(500)

    result = await run_connection_test(
        base_url="https://api.example.com/ping", auth_type=None, credential=None, client=_client_for(handler)
    )

    assert result.status is ConnectionTestStatus.WARNING


@pytest.mark.asyncio
async def test_timeout_is_classified_as_timeout():
    def handler(request):
        raise httpx.TimeoutException("timed out", request=request)

    result = await run_connection_test(
        base_url="https://api.example.com/ping", auth_type=None, credential=None, client=_client_for(handler)
    )

    assert result.status is ConnectionTestStatus.TIMEOUT


@pytest.mark.asyncio
async def test_connection_error_is_offline():
    def handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    result = await run_connection_test(
        base_url="https://api.example.com/ping", auth_type=None, credential=None, client=_client_for(handler)
    )

    assert result.status is ConnectionTestStatus.OFFLINE


@pytest.mark.asyncio
async def test_bearer_auth_sets_authorization_header():
    captured = {}

    def handler(request):
        captured["authorization"] = request.headers.get("authorization")
        return httpx.Response(200)

    await run_connection_test(
        base_url="https://api.example.com/ping", auth_type="bearer", credential="secret-token",
        client=_client_for(handler),
    )

    assert captured["authorization"] == "Bearer secret-token"


@pytest.mark.asyncio
async def test_api_key_query_auth_sets_param_not_header():
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("authorization")
        return httpx.Response(200)

    await run_connection_test(
        base_url="https://api.example.com/ping", auth_type="api_key_query", credential="secret-value",
        client=_client_for(handler),
    )

    assert "api_key=secret-value" in captured["url"]
    assert captured["authorization"] is None


@pytest.mark.asyncio
async def test_api_key_header_defaults_to_x_api_key():
    captured = {}

    def handler(request):
        captured["x-api-key"] = request.headers.get("x-api-key")
        return httpx.Response(200)

    await run_connection_test(
        base_url="https://api.example.com/ping", auth_type="api_key_header", credential="secret-value",
        client=_client_for(handler),
    )

    assert captured["x-api-key"] == "secret-value"


@pytest.mark.asyncio
async def test_api_key_header_uses_custom_header_name_when_configured():
    """API-Football (and other providers) expect their key on a specific, non-default header
    name — a provider configured with `auth_header_name` must send the key there, not on the
    generic "X-API-Key" fallback."""
    captured = {}

    def handler(request):
        captured["apisports-key"] = request.headers.get("x-apisports-key")
        captured["default-key"] = request.headers.get("x-api-key")
        return httpx.Response(200)

    await run_connection_test(
        base_url="https://v3.football.api-sports.io/status", auth_type="api_key_header",
        credential="secret-value", header_name="x-apisports-key", client=_client_for(handler),
    )

    assert captured["apisports-key"] == "secret-value"
    assert captured["default-key"] is None


@pytest.mark.asyncio
async def test_credential_never_appears_in_message():
    def handler(request):
        return httpx.Response(401)

    result = await run_connection_test(
        base_url="https://api.example.com/ping", auth_type="bearer", credential="super-secret-value",
        client=_client_for(handler),
    )

    assert "super-secret-value" not in result.message
