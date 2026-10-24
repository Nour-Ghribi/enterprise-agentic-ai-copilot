"""Local hybrid lexical retrieval; hashing vectors need no download or API key."""

import hashlib
import json
import re
import os
from pathlib import Path

import faiss
from pypdf import PdfReader
from sklearn.feature_extraction.text import HashingVectorizer

from copilot.models import Search

faiss.omp_set_num_threads(1)  # Small local corpus: avoid expensive OpenMP oversubscription.

STOP = {
    "the",
    "is",
    "a",
    "an",
    "of",
    "for",
    "and",
    "in",
    "to",
    "what",
    "which",
    "are",
    "my",
    "contract",
    "customer",
}


def tokens(text):
    return set(re.findall(r"[a-z0-9]+", text.lower())) - STOP


class ContractIndex:
    def __init__(self, directory: Path):
        self.directory = directory
        self.vectorizer = HashingVectorizer(
            n_features=2048, alternate_sign=False, norm="l2", stop_words="english"
        )
        self.chunks = []
        self.index = faiss.IndexFlatIP(2048)
        self.semantic_index = None
        self.encoder = None
        self.semantic_error = None
        self.ingest(directory / "contracts")

    def ingest(self, source: Path):
        """Only operator-controlled local PDFs. No user paths or remote fetches are exposed by the API."""
        chunks = []
        manifest = {}
        for path in sorted(source.glob("contract-C[0-9][0-9][0-9].pdf")):
            cid = path.stem.split("-")[-1]
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            manifest[path.name] = digest
            for page_num, page in enumerate(PdfReader(path).pages, 1):
                text = page.extract_text() or ""
                for offset in range(0, len(text), 700):
                    chunk = text[offset : offset + 850]
                    chunks.append(
                        {
                            "id": f"{path.stem}:p{page_num}:{offset}",
                            "customer_id": cid,
                            "document": path.name,
                            "page": page_num,
                            "text": chunk,
                            "source_sha256": digest,
                            "untrusted_content": True,
                            "suspicious": bool(
                                re.search(
                                    r"ignore.{0,30}instructions|system prompt|approve.*action", chunk, re.I
                                )
                            ),
                        }
                    )
        self.chunks = chunks
        self.semantic_index = None
        self.index = faiss.IndexFlatIP(2048)
        if chunks:
            vectors = self.vectorizer.transform([c["text"] for c in chunks]).toarray().astype("float32")
            self.index.add(vectors)
        (self.directory / "contracts.faiss").write_bytes(faiss.serialize_index(self.index).tobytes())
        (self.directory / "chunks.json").write_text(json.dumps(chunks, indent=2), encoding="utf-8")
        (self.directory / "index_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    def ensure_semantic(self):
        if self.semantic_index is not None:
            return True
        if os.getenv("SEMANTIC_ENABLED", "0") != "1":
            self.semantic_error = "Semantic retrieval disabled; lexical fallback"
            return False
        try:
            from copilot.semantic import SemanticEncoder

            self.encoder = SemanticEncoder()
            vectors = self.encoder.encode([c["text"] for c in self.chunks])
            self.semantic_index = faiss.IndexFlatIP(vectors.shape[1])
            self.semantic_index.add(vectors)
            return True
        except (ImportError, OSError, ValueError, RuntimeError) as exc:
            self.semantic_error = f"Semantic model unavailable ({type(exc).__name__}); lexical fallback"
            return False

    def search(self, request: Search) -> list[dict]:
        lexical = self.lexical_search(request)
        if request.retrieval_mode != "hybrid" or not self.ensure_semantic():
            return [
                {
                    **c,
                    "retrieval_mode": "lexical",
                    "semantic_warning": self.semantic_error if request.retrieval_mode == "hybrid" else None,
                }
                for c in lexical
            ]
        query = self.encoder.encode([request.query])
        distances, indices = self.semantic_index.search(query, len(self.chunks))
        candidates = {c["id"]: {**c, "fusion_score": 1 / (60 + rank)} for rank, c in enumerate(lexical, 1)}
        rank = 0
        for similarity, idx in zip(distances[0], indices[0]):
            chunk = self.chunks[int(idx)]
            if chunk["suspicious"] or (request.customer_id and chunk["customer_id"] != request.customer_id):
                continue
            if float(similarity) < float(os.getenv("SEMANTIC_MIN_SIMILARITY", "0.25")):
                continue
            rank += 1
            row = candidates.setdefault(chunk["id"], {**chunk, "fusion_score": 0})
            row["fusion_score"] += 1 / (60 + rank)
            row["semantic_similarity"] = round(float(similarity), 4)
        results = sorted(candidates.values(), key=lambda r: r["fusion_score"], reverse=True)[: request.limit]
        return [
            {
                **c,
                "retrieval_score": round(c["fusion_score"], 6),
                "retrieval_mode": "hybrid",
                "embedding_model": self.encoder.name,
            }
            for c in results
        ]

    def lexical_search(self, request: Search) -> list[dict]:
        if not self.chunks:
            return []
        vector = self.vectorizer.transform([request.query]).toarray().astype("float32")
        distances, indices = self.index.search(vector, len(self.chunks))
        results = []
        wanted = tokens(request.query)
        for similarity, idx in zip(distances[0], indices[0]):
            chunk = self.chunks[int(idx)]
            if request.customer_id and chunk["customer_id"] != request.customer_id:
                continue
            overlap = len(wanted & tokens(chunk["text"])) / max(len(wanted), 1)
            if overlap == 0 or chunk["suspicious"]:
                continue
            score = 0.65 * float(similarity) + 0.35 * overlap
            results.append({**chunk, "retrieval_score": round(score, 4)})
        return sorted(results, key=lambda r: r["retrieval_score"], reverse=True)[: request.limit]
