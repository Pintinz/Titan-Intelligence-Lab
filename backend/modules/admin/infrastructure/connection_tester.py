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


def _resolve_request_url(base_url: str, auth_type: str | None, credential: str | None) -> str:
    """Audit fix (2026-08-10): TheSportsDB (and providers like it) embed the API key as a URL
    *path segment* rather than a header/query param — verified live, `.../json/{key}/all_sports.php`
    is the real convention, and none of the other auth_types can express that. ``api_key_path``
    substitutes a ``{key}`` placeholder in `base_url` with the credential; a `base_url` with no
    placeholder is returned unchanged (falls through to the generic unauthenticated-request case
    below, same as an unrecognized auth_type)."""
    if auth_type == "api_key_path" and credential and "{key}" in base_url:
        return base_url.replace("{key}", credential)
    return base_url


async def test_oauth2_client_credentials(
    *,
    token_url: str | None,
    client_id: str | None,
    client_secret: str | None,
    timeout_seconds: int = 10,
    client: httpx.AsyncClient | None = None,
) -> ConnectionTestResult:
    """RFC 6749 client-credentials grant — POSTs ``client_id``/``client_secret``/
    ``grant_type=client_credentials`` as form-urlencoded to ``token_url`` and classifies success
    by whether a Bearer access token comes back. Exists alongside ``test_connection`` (rather
    than folding into it) because this shape is fundamentally different: two paired credential
    values instead of one, and a POST token exchange instead of a single authenticated GET —
    e.g. Flutterwave's V4 API issues short-lived tokens from a static client_id/client_secret
    pair instead of accepting one static API key directly.

    Deliberately never returns the issued access token in ``raw_body`` (unlike
    ``test_connection``, which passes through whatever the provider returned) — a fresh Bearer
    token is itself a live credential, and nothing here needs to inspect it."""
    if not token_url or not client_id or not client_secret:
        return ConnectionTestResult(
            status=ConnectionTestStatus.NOT_CONFIGURED,
            latency_ms=None,
            http_status=None,
            message="Missing token URL, client ID, or client secret — nothing to test.",
        )

    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=timeout_seconds)
    started = perf_counter()
    try:
        response = await http_client.post(
            token_url,
            data={"client_id": client_id, "client_secret": client_secret, "grant_type": "client_credentials"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        latency_ms = (perf_counter() - started) * 1000

        if response.status_code in (400, 401, 403):
            return ConnectionTestResult(
                ConnectionTestStatus.UNAUTHORIZED, latency_ms, response.status_code,
                "Provider rejected the client credentials.",
            )
        if response.status_code == 429:
            return ConnectionTestResult(
                ConnectionTestStatus.RATE_LIMITED, latency_ms, response.status_code,
                "Provider is rate-limiting this credential (429).",
            )
        if 200 <= response.status_code < 300:
            try:
                got_token = bool(response.json().get("access_token"))
            except ValueError:
                got_token = False
            if got_token:
                return ConnectionTestResult(
                    ConnectionTestStatus.HEALTHY, latency_ms, response.status_code,
                    "Reachable and authenticated — access token issued.",
                )
            return ConnectionTestResult(
                ConnectionTestStatus.WARNING, latency_ms, response.status_code,
                "200 response but no access_token in the body.",
            )
        return ConnectionTestResult(
            ConnectionTestStatus.WARNING, latency_ms, response.status_code,
            f"Unexpected response status {response.status_code}.",
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
    request_url = _resolve_request_url(base_url, auth_type, credential)

    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=timeout_seconds)
    started = perf_counter()
    try:
        response = await http_client.get(request_url, **request_kwargs)
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
