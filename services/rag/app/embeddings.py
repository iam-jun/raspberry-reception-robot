from __future__ import annotations

import hashlib
import math
import warnings
from functools import lru_cache
from typing import Iterable

from .config import RagSettings


class EmbeddingProvider:
    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or RagSettings().embedding_model
        self._model = None

    def embed_text(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        model = self._load_model()
        if model is not None:
            vectors = model.embed(texts)
            return [_normalize_vector(vector) for vector in vectors]
        return [_hash_embedding(text) for text in texts]

    def _load_model(self):
        if self._model is False:
            return None
        if self._model is not None:
            return self._model
        try:
            from fastembed import TextEmbedding

            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message=".*now uses mean pooling.*", category=UserWarning)
                self._model = TextEmbedding(model_name=self.model_name)
            return self._model
        except Exception:
            self._model = False
            return None


def _normalize_vector(vector: Iterable[float]) -> list[float]:
    values = [float(value) for value in vector]
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [value / norm for value in values]


@lru_cache(maxsize=4096)
def _hash_embedding(text: str, dimensions: int = 384) -> list[float]:
    """Small deterministic fallback for tests/offline demos when FastEmbed is unavailable."""
    vector = [0.0] * dimensions
    tokens = text.lower().split()
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]
