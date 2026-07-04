"""
embedder.py
Offline TF-IDF embedder — no internet, no model download needed.
Uses only numpy which is already installed.
TF-IDF is a well-established NLP technique (documented in academic literature)
and works well for retrieval over a small, well-structured knowledge base.
"""

import re
import json
import math
from pathlib import Path
import numpy as np


def tokenize(text: str) -> list:
    """Lowercase and extract word tokens (handles EN, FR, Pidgin)."""
    return re.findall(r"\b[a-zA-ZÀ-ÿ]{2,}\b", text.lower())


class TFIDFEmbedder:
    def __init__(self):
        self.vocab: dict = {}
        self.idf: dict = {}
        self.dim: int = 0

    def fit(self, texts: list):
        """Build vocabulary and IDF weights from all documents."""
        doc_freq = {}
        N = len(texts)
        for text in texts:
            unique_tokens = set(tokenize(text))
            for t in unique_tokens:
                doc_freq[t] = doc_freq.get(t, 0) + 1

        vocab_list = sorted(doc_freq.keys())
        self.vocab = {w: i for i, w in enumerate(vocab_list)}
        # Smoothed IDF
        self.idf = {
            w: math.log((N + 1) / (freq + 1)) + 1
            for w, freq in doc_freq.items()
        }
        self.dim = len(self.vocab)
        print(f"  Vocabulary size: {self.dim} tokens from {N} documents")

    def embed(self, text: str) -> list:
        """Embed a single text as a normalised TF-IDF vector."""
        tokens = tokenize(text)
        if not tokens:
            return [0.0] * self.dim
        vec = np.zeros(self.dim)
        tf: dict = {}
        for t in tokens:
            tf[t] = tf.get(t, 0) + 1
        for t, count in tf.items():
            if t in self.vocab:
                vec[self.vocab[t]] = (count / len(tokens)) * self.idf.get(t, 1.0)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.tolist()

    def embed_many(self, texts: list) -> list:
        return [self.embed(t) for t in texts]

    def save(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"vocab": self.vocab, "idf": self.idf, "dim": self.dim}, f)
        print(f"  Embedder saved to {path}")

    @classmethod
    def load(cls, path: str):
        obj = cls()
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        obj.vocab = data["vocab"]
        obj.idf = data["idf"]
        obj.dim = data["dim"]
        return obj
