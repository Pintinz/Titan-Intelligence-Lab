"""ONNX Export architecture (Milestone 9.1 Model Serving). The spec names this alongside "future
TensorFlow/PyTorch support" and "future distributed serving" — explicitly forward-looking, not a
working requirement this milestone delivers. This is the interface-only seam (same posture as
Milestone 7's RAG-foundation retrieval port, docs/decisions.md: real interfaces land now, a
concrete `onnx`/`skl2onnx`-backed adapter lands when a real production need for cross-runtime
model export shows up).
"""

from __future__ import annotations

from typing import Protocol

from modules.predictions.ports.ml_model import PredictionModelPort


class ModelExportPort(Protocol):
    async def export_to_onnx(self, model: PredictionModelPort) -> bytes: ...
