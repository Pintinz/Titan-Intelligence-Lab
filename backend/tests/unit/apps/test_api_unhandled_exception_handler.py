from fastapi.testclient import TestClient

from apps.api.main import app


def test_an_unhandled_exception_still_carries_cors_headers():
    """Real incident, 2026-08-29: a genuinely unhandled exception (first found as a DecryptionError
    crashing a provider-credentials endpoint, inside the route body — both real incidents this
    session found were exactly this shape) shipped with no Access-Control-Allow-Origin header at
    all — Starlette's bare ServerErrorMiddleware fallback sits outside every user middleware,
    including CORSMiddleware. A browser can't distinguish that from a network failure. The global
    `@app.exception_handler(Exception)` is the backstop: it's processed by ExceptionMiddleware,
    which sits INSIDE the user middleware stack, so its response passes back out through
    CORSMiddleware normally — this must hold for ANY unhandled exception a route body raises, not
    just the two specific ones already found and fixed directly."""

    @app.get("/api/v1/_test_only_unhandled_crash")
    async def _crash():
        raise RuntimeError("something genuinely unexpected")

    # One of the module's own default-allowed origins (_default_origins in main.py) — the
    # production frontend origin is only added via TITANIQ_CORS_ORIGINS, read once at import
    # time, so it can't be exercised by monkeypatching the env var mid-test.
    test_origin = "http://localhost:5173"
    try:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/v1/_test_only_unhandled_crash", headers={"Origin": test_origin})
    finally:
        app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", None) != "/api/v1/_test_only_unhandled_crash"]

    assert response.status_code == 500
    assert response.headers.get("access-control-allow-origin") == test_origin
