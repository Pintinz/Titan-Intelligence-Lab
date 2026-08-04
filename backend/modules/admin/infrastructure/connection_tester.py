"""Generic HTTP connection tester for the Provider Registry (docs/admin_center.md §2, Milestone
11B) — the backend for the Operations Center's "Test Connection" button.

Deliberately provider-agnostic: rather than hand-writing a prober per provider (API-Football,
NewsAPI, Gemini, ...), this makes one HTTP request to `ProviderDefinition.base_url` with the
credential attached according to `auth_type`, and classifies the *transport-level* outcome
(reachable/unauthorized/rate-limited/timeout/error) — it does not know or care about any
provider's specific response schema. A provider-specific richer check can layer on top later
without changing this contract.

Never logs or returns the plaintext credential — it is used once to build the outbound request
and discarded (docs/security.md §2).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from time import perf_counter

import httpx


class ConnectionTestStatus(str, Enum):
    HEALTHY = "healthy"
    WARNING = "warning"
    OFFLINE = "offline"
    UNAUTHORIZED = "unauthorized"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    NOT_CONFIGURED = "not_configured"  # no base_url on the provider yet — nothing to call


@dataclass
class ConnectionTestResult:
    status: ConnectionTestStatus
    latency_ms: float | None
    http_status: int | None
    message: str
    # The raw parsed JSON body, captured whenever the response is valid JSON — regardless of
    # HTTP status or classification above. This tester stays deliberately provider-agnostic (see
    # module docstring), so it never interprets this body; callers that want to derive a
    # provider-specific capability note (e.g. API-SPORTS' `response.subscription.plan`) from it
    # can, without this module needing to know any provider's schema.
    raw_body: dict | None = None

    @property
    def success(self) -> bool:
        return self.status is ConnectionTestStatus.HEALTHY


def _apply_auth(
    request_kwargs: dict,
    auth_type: str | None,
    credential: str | None,
    username: str | None,
    header_name: str | None = None,
) -> None:
    if not credential:
        return
    if auth_type == "bearer":
        request_kwargs.setdefault("headers", {})["Authorization"] = f"Bearer {credential}"
    elif auth_type == "api_key_header":
        # Providers disagree on the header name (API-Football wants "x-apisports-key", others
        # "X-API-Key") — `header_name` lets a provider be configured with its real one instead
        # of silently sending a header the provider will never recognize.
        request_kwargs.setdefault("headers", {})[header_name or "X-API-Key"] = credential
    elif auth_type == "api_key_query":
        request_kwargs.setdefault("params", {})["api_key"] = credential
    elif auth_type == "basic":
        request_kwargs["auth"] = (username or "", credential)
    # else: no recognized auth_type — request goes out unauthenticated, which is a legitimate
    # outcome for e.g. a public webhook receiver health path.


async def test_connection(
    *,
    base_url: str | None,
    auth_type: str | None,
    credential: str | None,
    username: str | None = None,
    header_name: str | None = None,
    timeout_seconds: int = 10,
    client: httpx.AsyncClient | None = None,
) -> ConnectionTestResult:
    if not base_url:
        return ConnectionTestResult(
            status=ConnectionTestStatus.NOT_CONFIGURED,
            latency_ms=None,
            http_status=None,
            message="No base URL configured for this provider yet — nothing to test.",
        )

    request_kwargs: dict = {}
    _apply_auth(request_kwargs, auth_type, credential, username, header_name)

    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=timeout_seconds)
    started = perf_counter()
    try:
        response = await http_client.get(base_url, **request_kwargs)
        latency_ms = (perf_counter() - started) * 1000
        try:
            raw_body = response.json()
            raw_body = raw_body if isinstance(raw_body, dict) else None
        except ValueError:
            raw_body = None

        if response.status_code in (401, 403):
            return ConnectionTestResult(
                ConnectionTestStatus.UNAUTHORIZED, latency_ms, response.status_code,
                "Provider rejected the credential (401/403).", raw_body,
            )
        if response.status_code == 429:
            return ConnectionTestResult(
                ConnectionTestStatus.RATE_LIMITED, latency_ms, response.status_code,
                "Provider is rate-limiting this credential (429).", raw_body,
            )
        if 200 <= response.status_code < 300:
            return ConnectionTestResult(
                ConnectionTestStatus.HEALTHY, latency_ms, response.status_code, "Reachable and authenticated.", raw_body,
            )
        return ConnectionTestResult(
            ConnectionTestStatus.WARNING, latency_ms, response.status_code,
            f"Unexpected response status {response.status_code}.", raw_body,
        )
    except httpx.TimeoutException:
        return ConnectionTestResult(
            ConnectionTestStatus.TIMEOUT, (perf_counter() - started) * 1000, None,
            f"No response within {timeout_seconds}s.",
        )
    except httpx.HTTPError as exc:
        return ConnectionTestResult(
            ConnectionTestStatus.OFFLINE, (perf_counter() - started) * 1000, None,
            f"Connection failed: {type(exc).__name__}.",
        )
    finally:
        if owns_client:
            await http_client.aclose()
