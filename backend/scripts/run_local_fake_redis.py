"""Local dev-only Redis stand-in: this Windows machine's WSL networking (VirtioProxy fallback
mode) doesn't support the usual localhost port-forwarding, so a real Redis running inside WSL is
unreachable from the Windows-side backend. Rather than reconfigure WSL networking or install
third-party Windows software, this runs fakeredis's own TcpFakeServer — a dependency this project
already uses for its offline test suite (docs/deployment.md §3: "SQLite/fakeredis") — as a real
local TCP server speaking the Redis wire protocol on localhost:6379, so TITANIQ_REDIS_URL works
exactly as configured with zero code or config changes.

Usage: python scripts/run_local_fake_redis.py
"""

from __future__ import annotations

from fakeredis import TcpFakeServer

if __name__ == "__main__":
    server = TcpFakeServer(("localhost", 6379))
    print("fakeredis TCP server listening on localhost:6379 (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
