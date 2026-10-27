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


# Very common "glue" words.  They appear in almost every sentence, so they say
# nothing about the TOPIC of a question, and keeping them lets an off-topic
# question like "What is the capital of France?" look similar to our passages
# just because both contain "what", "is", "the", "of".  Removing them (from the
# passages AND from the questions) makes the similarity scores meaningful.
STOPWORDS = set("""
an the of to in on at for from by with about as is are was were be been being am do does did done
have has had having me my mine we us our you your he she it its they them their this that these
those there here and or but if so than then too very can could should would will shall may might
must not no nor what which who whom whose when where why how also just only any some all each every
more most other such own same into over under again further once up down out off while during
before after between both few ever get got make made use used using one two
le la les un une des de du au aux et ou mais donc ni car que qui quoi dont ce cet cette ces ça ca
est sont suis es sommes êtes etre être été ont ai as avons avez avoir il elle on nous vous ils
elles je tu te se mon ma mes ton ta tes son sa ses notre nos votre vos leur leurs en dans sur sous
avec sans pour par plus moins très comment pourquoi quand quel quelle quels quelles ne pas faire
fait peut peux puis dois doit
na di dem dey wey don wan fit go
""".split())


def normalise(text: str) -> str:
    """Tidy a piece of text before it is embedded: remove control characters,
    lowercase it and collapse runs of spaces/new lines into single spaces."""
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", text or "")
    return re.sub(r"\s+", " ", text.lower()).strip()


def tokenize(text: str) -> list:
    """Lowercase and extract word tokens (handles EN, FR, Pidgin).
    Punctuation and numbers are dropped, single letters and stop-words are ignored."""
    words = re.findall(r"\b[a-zA-ZÀ-ÿ]{2,}\b", normalise(text))
    return [w for w in words if w not in STOPWORDS]


def is_zero_vector(vec) -> bool:
    """True when a vector has no signal at all, i.e. NONE of the words in the
    question exist in the knowledge base vocabulary."""
    return not any(vec)


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
