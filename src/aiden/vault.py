"""Vault indexing and search: AIden's memory of the user's Obsidian notes.

The vault is mounted read-only. Notes are split into chunks by heading, embedded,
and stored in a Qdrant collection together with their path, heading and the note's
modification time. A background thread re-scans periodically and re-embeds only
notes whose modification time changed; deleted notes are removed from the index.

Embedding is split by task (see docker-compose.yaml): bulk indexing goes to
ovms-embed-index (NPU) when it's available, search queries to ovms-embed-query (CPU).

Vault content is private: it only ever goes to local services (OVMS, Qdrant).
"""
import logging
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

VAULT_DIR = os.environ.get("VAULT_DIR", "/vault")
QDRANT_URL = os.environ.get("QDRANT_URL", "http://qdrant:6333")
COLLECTION = "vault"
EMBED_MODEL = os.environ.get("OVMS_EMBED_MODEL_NAME", "")
EMBED_INDEX_URL = "http://ovms-embed-index:8003/v3/embeddings"
EMBED_QUERY_URL = "http://ovms-embed-query:8003/v3/embeddings"
SCAN_INTERVAL_S = int(os.environ.get("VAULT_SCAN_INTERVAL_S", "300"))
SKIP_DIRS = {".obsidian", ".git", ".trash"}
MAX_CHUNK_CHARS = 1500
EMBED_BATCH = 8

logger = logging.getLogger("aiden.vault")
HEADING = re.compile(r"^(#{1,6})\s+(.*)$")

status: Dict[str, Any] = {
    "state": "starting", "notes_on_disk": 0, "notes_indexed": 0, "chunks_indexed": 0,
    "pending_notes": 0, "embed_device": None, "last_scan_started": None,
    "last_scan_finished": None, "last_error": None,
}


# --- Chunking ---------------------------------------------------------------

def strip_frontmatter(text: str) -> str:
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            return text[end + 4:].lstrip("\n")
    return text


def split_long(text: str) -> List[str]:
    """Split a section into pieces of at most MAX_CHUNK_CHARS, on paragraph boundaries."""
    if len(text) <= MAX_CHUNK_CHARS:
        return [text]
    pieces, current = [], ""
    for para in re.split(r"\n\s*\n", text):
        while len(para) > MAX_CHUNK_CHARS:
            if current:
                pieces.append(current); current = ""
            pieces.append(para[:MAX_CHUNK_CHARS]); para = para[MAX_CHUNK_CHARS:]
        if len(current) + len(para) + 2 > MAX_CHUNK_CHARS and current:
            pieces.append(current); current = ""
        current = f"{current}\n\n{para}" if current else para
    if current:
        pieces.append(current)
    return pieces


def chunk_note(rel_path: str, text: str) -> List[Dict[str, str]]:
    """Chunks with the heading trail they sit under, e.g. 'Setup > Docker'."""
    title = os.path.splitext(os.path.basename(rel_path))[0]
    trail: List[str] = []
    sections: List[tuple] = []
    body: List[str] = []

    def flush():
        content = "\n".join(body).strip()
        if content:
            sections.append((" > ".join(trail), content))
        body.clear()

    for line in strip_frontmatter(text).splitlines():
        match = HEADING.match(line)
        if match:
            flush()
            level = len(match.group(1))
            trail[:] = trail[:level - 1] + [match.group(2).strip()]
        else:
            body.append(line)
    flush()

    chunks = []
    for heading, content in sections:
        for piece in split_long(content):
            # Note title and heading are embedded with the text, which helps retrieval
            context = f"{title} > {heading}" if heading else title
            chunks.append({"heading": heading, "text": piece, "embed_text": f"{context}\n\n{piece}"})
    return chunks


# --- Embeddings -------------------------------------------------------------

def embed(texts: List[str], url: str) -> List[List[float]]:
    response = requests.post(url, json={"model": EMBED_MODEL, "input": texts}, timeout=300)
    response.raise_for_status()
    return [d["embedding"] for d in sorted(response.json()["data"], key=lambda d: d["index"])]


def index_embed_url() -> str:
    """NPU for bulk indexing when it's up, otherwise the always-on CPU service."""
    try:
        requests.get(EMBED_INDEX_URL.replace("/v3/embeddings", "/v2/health/ready"), timeout=2).raise_for_status()
        status["embed_device"] = "npu"
        return EMBED_INDEX_URL
    except requests.RequestException:
        status["embed_device"] = "cpu"
        return EMBED_QUERY_URL


# --- Qdrant -----------------------------------------------------------------

def qdrant(method: str, path: str, **kwargs) -> Dict[str, Any]:
    response = requests.request(method, f"{QDRANT_URL}{path}", timeout=60, **kwargs)
    response.raise_for_status()
    return response.json()


def ensure_collection(dim: int):
    if requests.get(f"{QDRANT_URL}/collections/{COLLECTION}", timeout=10).status_code == 200:
        return
    qdrant("PUT", f"/collections/{COLLECTION}", json={"vectors": {"size": dim, "distance": "Cosine"}})
    qdrant("PUT", f"/collections/{COLLECTION}/index", json={"field_name": "path", "field_schema": "keyword"})


def indexed_mtimes() -> Dict[str, float]:
    """path -> mtime for every note currently in the index."""
    if requests.get(f"{QDRANT_URL}/collections/{COLLECTION}", timeout=10).status_code != 200:
        return {}
    mtimes, offset = {}, None
    while True:
        body = {"limit": 1000, "with_payload": ["path", "mtime"], "with_vector": False}
        if offset is not None:
            body["offset"] = offset
        result = qdrant("POST", f"/collections/{COLLECTION}/points/scroll", json=body)["result"]
        for point in result["points"]:
            mtimes[point["payload"]["path"]] = point["payload"]["mtime"]
        offset = result.get("next_page_offset")
        if offset is None:
            return mtimes


def delete_note(rel_path: str):
    qdrant("POST", f"/collections/{COLLECTION}/points/delete?wait=true",
           json={"filter": {"must": [{"key": "path", "match": {"value": rel_path}}]}})


def count_chunks() -> int:
    if requests.get(f"{QDRANT_URL}/collections/{COLLECTION}", timeout=10).status_code != 200:
        return 0
    return qdrant("POST", f"/collections/{COLLECTION}/points/count", json={"exact": True})["result"]["count"]


# --- Scanning ---------------------------------------------------------------

def notes_on_disk() -> Dict[str, float]:
    found = {}
    for directory, dirs, files in os.walk(VAULT_DIR):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            if name.endswith(".md"):
                full = os.path.join(directory, name)
                found[os.path.relpath(full, VAULT_DIR)] = os.path.getmtime(full)
    return found


def index_note(rel_path: str, mtime: float, url: str):
    with open(os.path.join(VAULT_DIR, rel_path), encoding="utf-8", errors="replace") as f:
        chunks = chunk_note(rel_path, f.read())
    points = []
    for start in range(0, len(chunks), EMBED_BATCH):
        batch = chunks[start:start + EMBED_BATCH]
        vectors = embed([c["embed_text"] for c in batch], url)
        ensure_collection(len(vectors[0]))
        for i, (chunk, vector) in enumerate(zip(batch, vectors), start):
            points.append({
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"vault/{rel_path}#{i}")),
                "vector": vector,
                "payload": {"path": rel_path, "heading": chunk["heading"], "text": chunk["text"],
                            "chunk": i, "mtime": mtime},
            })
    delete_note(rel_path)
    if points:
        qdrant("PUT", f"/collections/{COLLECTION}/points?wait=true", json={"points": points})


def scan(tracer=None):
    status["state"] = "scanning"
    status["last_scan_started"] = datetime.now(timezone.utc).isoformat()
    disk = notes_on_disk()
    indexed = indexed_mtimes()
    # Qdrant stores floats with slightly less precision, so exact equality would re-embed
    # unchanged notes on every scan; real edits differ by far more than 1 ms
    changed = [p for p, m in disk.items() if p not in indexed or abs(indexed[p] - m) > 1e-3]
    removed = [p for p in indexed if p not in disk]
    status.update(notes_on_disk=len(disk), pending_notes=len(changed))

    for rel_path in removed:
        delete_note(rel_path)
    if changed:
        status["state"] = "indexing"
        url = index_embed_url()
        for rel_path in sorted(changed):
            try:
                if tracer:
                    with tracer.start_as_current_span("vault.index_note") as span:
                        span.set_attribute("vault.embed_device", status["embed_device"])
                        index_note(rel_path, disk[rel_path], url)
                else:
                    index_note(rel_path, disk[rel_path], url)
            except (requests.RequestException, OSError, ValueError) as exc:
                status["last_error"] = f"{rel_path}: {type(exc).__name__}"
                logger.warning("Indexing %s failed: %s", rel_path, exc)
            status["pending_notes"] -= 1

    status.update(notes_indexed=len(indexed_mtimes()), chunks_indexed=count_chunks(), state="idle",
                  last_scan_finished=datetime.now(timezone.utc).isoformat())
    logger.info("Vault scan: %d notes, %d changed, %d removed", len(disk), len(changed), len(removed))


def run_forever(tracer=None):
    while True:
        try:
            scan(tracer)
        except Exception as exc:  # keep the indexer alive; the next scan retries
            status.update(state="error", last_error=type(exc).__name__)
            logger.exception("Vault scan failed")
        time.sleep(SCAN_INTERVAL_S)


def start(tracer=None):
    if not os.path.isdir(VAULT_DIR):
        status.update(state="disabled", last_error=f"{VAULT_DIR} not mounted")
        return
    threading.Thread(target=run_forever, args=(tracer,), daemon=True, name="vault-indexer").start()


# --- Search -----------------------------------------------------------------

def search(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    vector = embed([query], EMBED_QUERY_URL)[0]
    result = qdrant("POST", f"/collections/{COLLECTION}/points/search",
                    json={"vector": vector, "limit": limit, "with_payload": True})["result"]
    return [{"path": r["payload"]["path"], "heading": r["payload"]["heading"],
             "score": round(r["score"], 3), "text": r["payload"]["text"]} for r in result]
