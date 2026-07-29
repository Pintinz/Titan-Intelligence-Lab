"""Local-filesystem `ModelArtifactStorePort` — the dev/offline-test adapter. A future Supabase
Storage-backed adapter (mirroring the `ai-reports`/`generated-charts` buckets from Milestone 6)
implements the same port for production without any Training Platform code changing
(docs/decisions.md ADR-008 adapter-swap posture).
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class LocalFilesystemArtifactStore:
    root_dir: str = ".model_artifacts"

    async def save(self, key: str, payload: bytes) -> str:
        path = os.path.join(self.root_dir, key)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "wb") as f:
            f.write(payload)
        return path

    async def load(self, ref: str) -> bytes:
        with open(ref, "rb") as f:
            return f.read()
