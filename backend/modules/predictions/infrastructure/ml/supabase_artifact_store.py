"""Supabase Storage-backed `ModelArtifactStorePort` — the production adapter
`local_artifact_store.py`'s own docstring anticipated ("mirroring the ai-reports/generated-charts
buckets from Milestone 6"). `LocalFilesystemArtifactStore` writes to the container's local disk,
which Render (and most PaaS hosts) wipes on every deploy/restart — every trained model's artifact
was silently lost on the next deploy, permanently degrading that market back to its formula-
predictor fallback (`prediction_engine.py::_resolve_predictor`'s `champion_artifact_load_failed`
catch) until the next retraining cycle happened to land on the same, soon-to-be-redeployed
instance. Traced live in production 2026-08-23: `football.correct_score`'s real trained Champion
("Logistic Regression v3") existed but its artifact had already been wiped by an earlier deploy,
so every generation fell back to `WeightedLinearPredictor`'s honest-placeholder raw score
("5.1086") for a market that predicts a discrete scoreline — visibly malformed, and correctly
blocked from Gemini narration by `PredictionConsistencyGate`.

Uses the Supabase Storage REST API directly via `httpx` (same "real HTTP-calling code over an
SDK dependency" posture as `gemini_adapter.py`) with the project's SERVICE ROLE key — required
because artifacts are backend-owned system data with no individual end-user owner, so the
per-user `(storage.foldername(name))[1] = auth.uid()::text` RLS shape every other private bucket
uses (migration 0013) doesn't apply; the service role key bypasses RLS entirely, same as every
other Supabase service-role use elsewhere in a backend of this shape. Never the anon key — that
key is public (shipped in the frontend bundle) and would make this bucket world-writable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

import httpx
from pydantic_settings import BaseSettings, SettingsConfigDict

MODEL_ARTIFACTS_BUCKET = "model-artifacts"


class SupabaseStorageSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TITANIQ_")

    supabase_project_url: str
    supabase_service_role_key: str


@lru_cache
def get_supabase_storage_settings() -> SupabaseStorageSettings:
    return SupabaseStorageSettings()  # type: ignore[call-arg]


class ArtifactStoreError(RuntimeError):
    pass


@dataclass
class SupabaseStorageArtifactStore:
    project_url: str | None = None
    service_role_key: str | None = None
    bucket: str = MODEL_ARTIFACTS_BUCKET
    _client: httpx.AsyncClient | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.project_url is None or self.service_role_key is None:
            settings = get_supabase_storage_settings()
            self.project_url = self.project_url or settings.supabase_project_url
            self.service_role_key = self.service_role_key or settings.supabase_service_role_key
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.project_url,
                headers={
                    "apikey": self.service_role_key,
                    "Authorization": f"Bearer {self.service_role_key}",
                },
                timeout=30.0,
            )

    async def save(self, key: str, payload: bytes) -> str:
        response = await self._client.post(
            f"/storage/v1/object/{self.bucket}/{key}",
            content=payload,
            headers={"Content-Type": "application/octet-stream", "x-upsert": "true"},
        )
        if response.status_code >= 400:
            raise ArtifactStoreError(f"upload failed for '{key}': {response.status_code} {response.text}")
        return f"{self.bucket}/{key}"

    async def load(self, ref: str) -> bytes:
        path = ref[len(self.bucket) + 1 :] if ref.startswith(f"{self.bucket}/") else ref
        response = await self._client.get(f"/storage/v1/object/{self.bucket}/{path}")
        if response.status_code >= 400:
            raise ArtifactStoreError(f"download failed for '{ref}': {response.status_code} {response.text}")
        return response.content

    async def aclose(self) -> None:
        await self._client.aclose()
