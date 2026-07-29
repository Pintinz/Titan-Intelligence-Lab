"""Realtime dimension of the Milestone 6 integration suite (docs/supabase.md).

Table-membership in the ``supabase_realtime`` publication is already verified at the SQL level
in ``test_database.py::test_realtime_publication_has_expected_tables_only``. This file adds the
one thing that check can't cover: that the Realtime *service* itself is reachable and accepts a
Phoenix channel join for one of our deliberately-enabled tables — a real websocket handshake
against the live project, not just a Postgres catalog read.

Uses ``websockets`` (dev-only dependency, added specifically for this tier — see
pyproject.toml) since httpx has no websocket support.
"""

from __future__ import annotations

import json

import pytest
import websockets

from tests.integration.conftest import SUPABASE_ANON_KEY, SUPABASE_PROJECT_URL, requires_supabase_api


def _ws_url() -> str:
    host = SUPABASE_PROJECT_URL.replace("https://", "wss://").replace("http://", "ws://")
    return f"{host}/realtime/v1/websocket?apikey={SUPABASE_ANON_KEY}&vsn=1.0.0"


@requires_supabase_api
async def test_can_join_sessions_realtime_channel():
    async with websockets.connect(_ws_url(), open_timeout=10) as ws:
        join_message = {
            "topic": "realtime:identity_sessions_smoke_test",
            "event": "phx_join",
            "payload": {
                "config": {
                    "postgres_changes": [{"event": "*", "schema": "identity", "table": "sessions"}],
                }
            },
            "ref": "1",
        }
        await ws.send(json.dumps(join_message))

        reply = json.loads(await ws.recv())

        assert reply["event"] == "phx_reply"
        assert reply["payload"]["status"] == "ok", reply
