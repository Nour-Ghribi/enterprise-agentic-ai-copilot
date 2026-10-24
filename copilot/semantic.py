"""Optional learned sentence-transformer embeddings executed locally with ONNX/FastEmbed."""

import os
from functools import lru_cache
from pathlib import Path

import numpy as np

from copilot.config import ROOT

MODEL = "sentence-transformers/all-MiniLM-L6-v2"


@lru_cache(maxsize=2)
def load_model(model_name, directory, download):
    from fastembed import TextEmbedding

    return TextEmbedding(model_name=model_name, cache_dir=directory, local_files_only=not download, threads=2)


class SemanticEncoder:
    def __init__(self, download=False):
        self.name = os.getenv("SEMANTIC_MODEL", MODEL)
        self.cache = Path(os.getenv("SEMANTIC_CACHE_DIR", str(ROOT / "data" / "models")))
        self.model = load_model(self.name, str(self.cache), download)

    def encode(self, texts):
        vectors = np.array(list(self.model.embed(texts)), dtype="float32")
        vectors /= np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)
        return vectors


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--download", action="store_true")
    options = parser.parse_args()
    encoder = SemanticEncoder(download=options.download)
    print(
        {
            "model": encoder.name,
            "cache": str(encoder.cache),
            "shape": encoder.encode(["renewal notice"]).shape,
        }
    )
