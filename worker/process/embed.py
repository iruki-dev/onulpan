"""3단계 임베딩. 운영은 bge-m3(로컬 CPU, 1024차원), 개발·테스트는 결정적 해시 임베더.

임베딩 API를 쓰지 않는다. 비용이 0원이 되고, 기사 본문을 외부로 보내는 경로도 하나 줄어든다.
환경 변수 ONULPAN_EMBEDDER=bge-m3|hashing (기본: sentence-transformers가 설치되어 있으면 bge-m3)
"""
from __future__ import annotations

import hashlib
import os
import threading
from typing import Protocol

import numpy as np

DIM = 1024


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str]) -> np.ndarray: ...


class HashingEmbedder:
    """문자 2·3-gram을 해시해 1024차원에 흩뿌린 뒤 정규화한다. 의미는 못 잡지만 결정적이고 가볍다."""

    name = "hashing"

    def _one(self, text: str) -> np.ndarray:
        v = np.zeros(DIM, dtype=np.float32)
        s = "".join((text or "").split())
        for n in (2, 3):
            for i in range(len(s) - n + 1):
                h = hashlib.blake2b(s[i : i + n].encode("utf-8"), digest_size=8).digest()
                idx = int.from_bytes(h[:4], "little") % DIM
                sign = 1.0 if h[4] & 1 else -1.0
                v[idx] += sign
        norm = float(np.linalg.norm(v))
        return v / norm if norm > 0 else v

    def embed(self, texts: list[str]) -> np.ndarray:
        return np.stack([self._one(t) for t in texts]) if texts else np.zeros((0, DIM), dtype=np.float32)


class BgeM3Embedder:
    name = "bge-m3"

    def __init__(self, model_name: str = "BAAI/bge-m3", max_seq_length: int = 512):
        from sentence_transformers import SentenceTransformer  # 무거운 의존성은 여기서만

        self.model = SentenceTransformer(model_name, device="cpu")
        self.model.max_seq_length = max_seq_length

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, DIM), dtype=np.float32)
        return np.asarray(
            self.model.encode(texts, batch_size=16, normalize_embeddings=True, show_progress_bar=False),
            dtype=np.float32,
        )


_embedder: Embedder | None = None
_lock = threading.Lock()


def get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        with _lock:
            if _embedder is None:
                choice = os.environ.get("ONULPAN_EMBEDDER", "")
                if choice == "hashing":
                    _embedder = HashingEmbedder()
                else:
                    try:
                        _embedder = BgeM3Embedder()
                    except ImportError:
                        if choice == "bge-m3":
                            raise
                        _embedder = HashingEmbedder()
    return _embedder


def set_embedder(e: Embedder | None) -> None:
    global _embedder
    _embedder = e


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))
