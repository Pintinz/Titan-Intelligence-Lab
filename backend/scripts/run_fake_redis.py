"""One-off local dev helper: runs fakeredis's real TCP server on localhost:6379 so the backend's
distributed lock (SyncOrchestrator) and sync cache have something to connect to — no actual Redis
install available in this environment, and TITANIQ_REDIS_URL already points at this address
(backend/.env). Speaks the real Redis wire protocol; the app's redis.asyncio.Redis client
connects to it exactly as it would a real Redis instance, no application code changes needed.

Usage: python scripts/run_fake_redis.py
"""

from __future__ import annotations

from fakeredis import TcpFakeServer

if __name__ == "__main__":
    server_address = ("127.0.0.1", 6379)
    server = TcpFakeServer(server_address, server_type="redis")
    print(f"fakeredis TCP server listening on {server_address[0]}:{server_address[1]}")
    server.serve_forever()
