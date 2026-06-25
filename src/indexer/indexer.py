"""
Codebase Indexer
----------------
Walks a repo, extracts Python functions/classes using AST,
chunks them, and stores embeddings in ChromaDB.
"""
import ast
import hashlib
import json
import re
from pathlib import Path
from typing import Iterator

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

try:
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
    _EF = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
except Exception:
    # Fallback: simple TF-IDF-style hash embedding
    import hashlib
    import numpy as np

    class _SimpleEF:
        def name(self): return "simple_hash_ef"
        def embed_query(self, input): return self(input)
        def __call__(self, input):
            vecs = []
            for text in input:
                words = text.lower().split()
                vec = np.zeros(384)
                for i, w in enumerate(words[:384]):
                    h = int(hashlib.md5(w.encode()).hexdigest(), 16)
                    vec[h % 384] += 1.0
                norm = np.linalg.norm(vec)
                if norm > 0:
                    vec /= norm
                vecs.append(vec.tolist())
            return vecs

    _EF = _SimpleEF()

from src.config import CHROMA_DIR, COLLECTION_NAME, TOP_K_CONTEXT


def _file_hash(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _extract_chunks(source: str, filepath: str) -> list[dict]:
    """Extract function and class definitions from Python source via AST."""
    chunks = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # Fall back to line-based chunking for non-parseable files
        lines = source.splitlines()
        for i in range(0, len(lines), 50):
            chunk_lines = lines[i : i + 50]
            chunks.append({
                "code": "\n".join(chunk_lines),
                "name": f"{filepath}:lines_{i}_{i+len(chunk_lines)}",
                "type": "block",
                "lineno": i + 1,
                "filepath": filepath,
            })
        return chunks

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            # Only top-level and class-level (not nested inside functions)
            start = node.lineno - 1
            end = node.end_lineno
            code_lines = source.splitlines()[start:end]
            code = "\n".join(code_lines)

            # Get docstring if available
            docstring = ast.get_docstring(node) or ""

            # Get decorators
            decorators = []
            for d in getattr(node, "decorator_list", []):
                decorators.append(ast.unparse(d) if hasattr(ast, "unparse") else "")

            chunk = {
                "code": code,
                "name": f"{filepath}::{node.name}",
                "type": type(node).__name__,
                "lineno": node.lineno,
                "filepath": filepath,
                "docstring": docstring,
                "decorators": json.dumps(decorators),
            }
            chunks.append(chunk)

    # If nothing extracted, treat whole file as one chunk
    if not chunks:
        chunks.append({
            "code": source,
            "name": f"{filepath}::module",
            "type": "module",
            "lineno": 1,
            "filepath": filepath,
            "docstring": "",
            "decorators": "[]",
        })

    return chunks


def _chunk_id(filepath: str, name: str, lineno: int) -> str:
    raw = f"{filepath}::{name}::{lineno}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


class CodebaseIndexer:
    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)
        self.client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=_EF,
        )

    def index(self, extensions: list[str] = None, force: bool = False) -> int:
        """Index all source files. Returns number of chunks indexed."""
        if extensions is None:
            extensions = [".py"]

        files = [
            p for ext in extensions
            for p in self.repo_path.rglob(f"*{ext}")
            if not any(part.startswith(".") or part in ("__pycache__", "node_modules", "venv", ".venv")
                       for part in p.parts)
        ]

        total = 0
        for filepath in files:
            try:
                source = filepath.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            relative = str(filepath.relative_to(self.repo_path))
            chunks = _extract_chunks(source, relative)

            ids, documents, metadatas = [], [], []
            for chunk in chunks:
                cid = _chunk_id(relative, chunk["name"], chunk.get("lineno", 0))
                # Build rich document for embedding
                doc = f"FILE: {relative}\nNAME: {chunk['name']}\nTYPE: {chunk['type']}\n\n{chunk['code']}"
                ids.append(cid)
                documents.append(doc)
                meta = {k: str(v) for k, v in chunk.items() if k != "code"}
                meta["file_hash"] = _file_hash(filepath)
                metadatas.append(meta)

            if ids:
                self.collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
                total += len(ids)

        return total

    def query(self, query_text: str, k: int = TOP_K_CONTEXT) -> list[dict]:
        """Semantic search over the codebase."""
        results = self.collection.query(
            query_texts=[query_text],
            n_results=min(k, self.collection.count()),
            include=["documents", "metadatas", "distances"],
        )
        hits = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            hits.append({"document": doc, "metadata": meta, "score": 1 - dist})
        return hits

    def count(self) -> int:
        return self.collection.count()

    def reset(self):
        self.client.delete_collection(COLLECTION_NAME)
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=_EF,
        )
