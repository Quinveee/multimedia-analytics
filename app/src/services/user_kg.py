"""Write layer for user-added KG triples.

Additions go to a separate SQLite DB (config.USER_KG_PATH) with the same
nodes/edges schema as the frozen base plus source/created_at columns. The base
is never written here; services.kg merges the two at read time.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from src import config

# Reuse the offline canonicalisation so generated ids match what Spotlight and
# the retriever produce.
_OFFLINE_SCRIPTS = Path(config.ROOT_DIR).parent / "offline" / "scripts"
if _OFFLINE_SCRIPTS.is_dir() and str(_OFFLINE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_OFFLINE_SCRIPTS))

from uri_norm import canonical_uri  # noqa: E402
from enrich import shorten          # noqa: E402

_SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    id         TEXT PRIMARY KEY,
    label      TEXT,
    abstract   TEXT,
    types      TEXT,
    image      TEXT,
    source     TEXT NOT NULL DEFAULT 'user',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS edges (
    subject         TEXT NOT NULL,
    predicate       TEXT NOT NULL,
    object          TEXT NOT NULL,
    predicate_label TEXT,
    source          TEXT NOT NULL DEFAULT 'user',
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_user_edges_subject ON edges(subject);
CREATE INDEX IF NOT EXISTS idx_user_edges_object  ON edges(object);
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_edges_triple ON edges(subject, predicate, object);
"""

_PREFIXES = {
    "dbr:": "http://dbpedia.org/resource/",
    "dbo:": "http://dbpedia.org/ontology/",
    "dbp:": "http://dbpedia.org/property/",
}

_SLUG_RE = re.compile(r"[^A-Za-z0-9._-]+")


def ensure_user_db(path=None) -> Path:
    """Create the user DB and its schema if missing. Idempotent."""
    path = Path(path or config.USER_KG_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    try:
        con.executescript(_SCHEMA)
        con.commit()
    finally:
        con.close()
    return path


def _connect(path=None) -> sqlite3.Connection:
    """Open a write connection to the user DB (schema ensured)."""
    return sqlite3.connect(str(ensure_user_db(path)))


def _expand(value: str) -> str:
    """Expand a dbr:/dbo:/dbp: prefix to a full DBpedia URI."""
    for short, full in _PREFIXES.items():
        if value.startswith(short):
            return full + value[len(short):]
    return value


def canonical_id(value: str, *, predicate: bool = False) -> str:
    """Canonical dbr:/dbo:/dbp: id for a bare label, full URI, or prefixed id.

    A bare label becomes a dbr: resource, or a dbp: property when predicate=True.
    """
    v = (value or "").strip()
    if not v:
        raise ValueError("empty identifier")
    if v.startswith(("http://", "https://")) or any(v.startswith(p) for p in _PREFIXES):
        return shorten(canonical_uri(_expand(v)))
    base = _PREFIXES["dbp:"] if predicate else _PREFIXES["dbr:"]
    return shorten(canonical_uri(base + v.replace(" ", "_")))


def _label_from_id(node_id: str) -> str:
    """Fallback display label derived from a node id."""
    local = node_id.split(":", 1)[1] if ":" in node_id else node_id
    return local.replace("_", " ")


def image_slug(node_id: str) -> str:
    """Filesystem-safe image name for a node id, matching the offline slug."""
    local = node_id.split(":", 1)[1] if node_id.startswith("dbr:") else node_id
    return _SLUG_RE.sub("_", canonical_uri(local)).strip("_") + ".jpg"


def save_user_image(data: bytes, node_id: str, images_dir=None) -> str:
    """Save image bytes for a node and return the path stored in node.image."""
    images_dir = Path(images_dir or config.USER_IMAGES_DIR)
    images_dir.mkdir(parents=True, exist_ok=True)
    name = image_slug(node_id)
    (images_dir / name).write_bytes(data)
    return f"{images_dir.name}/{name}"


def _default_kg():
    """Return the shared KnowledgeGraph singleton (imported lazily)."""
    from src.services.kg import KG
    return KG


def _write_node(con, node_id, fields, images_dir, now):
    """Insert a node row for a new endpoint; no-op if the id already exists."""
    fields = fields or {}
    label = (fields.get("label") or "").strip() or _label_from_id(node_id)
    abstract = (fields.get("abstract") or "").strip()
    types = fields.get("types") or []
    if isinstance(types, str):
        types = [t.strip() for t in re.split(r"[,;]", types) if t.strip()]
    image_rel = fields.get("image")
    image_bytes = fields.get("image_bytes")
    if image_bytes and not image_rel:
        image_rel = save_user_image(image_bytes, node_id, images_dir)
    con.execute(
        "INSERT OR IGNORE INTO nodes (id, label, abstract, types, image, source, created_at) "
        "VALUES (?, ?, ?, ?, ?, 'user', ?)",
        (node_id, label, abstract, json.dumps(types), image_rel, now),
    )
    return {"id": node_id, "label": label, "image": image_rel}


def add_triple(*, subject, predicate, object, predicate_label=None,
               subject_node=None, object_node=None,
               kg=None, user_path=None, images_dir=None) -> dict:
    """Persist a user-added triple and return the written ids and created nodes.

    subject/object are raw strings (an existing id, full URI, or new label); the
    *_node dicts {label, abstract, types, image|image_bytes} are applied only to
    the endpoint that turns out to be new. Raises ValueError if neither endpoint
    already exists, if subject == object, or if the triple already exists.
    """
    kg = kg if kg is not None else _default_kg()
    user_path = Path(user_path or config.USER_KG_PATH)

    s_id = canonical_id(subject)
    o_id = canonical_id(object)
    p_id = canonical_id(predicate, predicate=True)
    p_label = (predicate_label or "").strip() or p_id.split(":", 1)[-1]

    if s_id == o_id:
        raise ValueError("Subject and object are the same entity; a triple must connect two different nodes.")

    existing = kg.existing_nodes([s_id, o_id])
    s_exists, o_exists = s_id in existing, o_id in existing
    if not s_exists and not o_exists:
        raise ValueError(
            f"Both '{s_id}' and '{o_id}' are new. An added triple must touch at "
            f"least one existing entity so retrieval can reach it — pick an existing "
            f"entity for the subject or the object.")
    if kg.has_edge(s_id, p_id, o_id):
        raise ValueError("That triple already exists in the graph.")

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    created_nodes = []
    con = _connect(user_path)
    try:
        for nid, exists, fields in ((s_id, s_exists, subject_node), (o_id, o_exists, object_node)):
            if not exists:
                created_nodes.append(_write_node(con, nid, fields, images_dir, now))
        con.execute(
            "INSERT INTO edges (subject, predicate, object, predicate_label, source, created_at) "
            "VALUES (?, ?, ?, ?, 'user', ?)",
            (s_id, p_id, o_id, p_label, now),
        )
        con.commit()
    finally:
        con.close()

    return {"subject": s_id, "predicate": p_id, "object": o_id, "predicate_label": p_label,
            "created_nodes": created_nodes, "source": "user", "created_at": now}


def reset(kg=None, user_path=None, images_dir=None) -> dict:
    """Drop all user additions (DB rows + uploaded images) to revert to the base.

    Detaches and re-attaches the read layer so its live connection survives the
    file swap.
    """
    kg = kg if kg is not None else _default_kg()
    user_path = Path(user_path or config.USER_KG_PATH)
    images_dir = Path(images_dir or config.USER_IMAGES_DIR)

    kg.detach_user()
    try:
        user_path.unlink(missing_ok=True)
        ensure_user_db(user_path)
        removed = 0
        if images_dir.exists():
            for p in images_dir.iterdir():
                if p.is_file():
                    p.unlink()
                    removed += 1
    finally:
        kg.attach_user()
    return {"user_db": str(user_path), "images_removed": removed}
