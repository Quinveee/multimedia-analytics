import csv
import io
import json
import os
import re
import tarfile
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

import requests
from PIL import Image
from tqdm import tqdm

from uri_norm import canonical_uri

load_dotenv()

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE.parent / "data"
MMPEDIA_DIR = HERE.parent / "mmpedia"

KG_PATH = DATA_DIR / "kg_subset.json"
VALIDATED_PATH = DATA_DIR / "validated_questions.json"
COVERAGE_PATH = DATA_DIR / "coverage.csv"
IMAGES_OUT = DATA_DIR / "images"
ENTITY2IMAGE = "entity2image.json"

ZENODO_BASE = "https://zenodo.org/records/7816711/files/"
THUMB_SIZE = 256

# Set MMPEDIA_AUTO_DOWNLOAD=1 to allow fetching entity2image.json + needed tars.
AUTO_DOWNLOAD = os.environ.get("MMPEDIA_AUTO_DOWNLOAD") == "1"
KEEP_ARCHIVES = os.environ.get("MMPEDIA_KEEP_ARCHIVES") == "1"
# Set MMPEDIA_FETCH_ALL=1 to fetch every available image (882k), not just the
# validated-question (seeds + evidence) entities, which is the default.
FETCH_ALL = os.environ.get("MMPEDIA_FETCH_ALL") == "1"

_ARCHIVE_RE = re.compile(r"(Entlist\d+)", re.IGNORECASE)
_SLUG_RE = re.compile(r"[^A-Za-z0-9._-]+")


def node_key(node_id: str) -> str:
    """Canonical MMpedia key for a node id: ``dbr:Bart_Tanski`` -> ``Bart_Tanski``."""
    local = node_id.split(":", 1)[1] if node_id.startswith("dbr:") else node_id
    return canonical_uri(local)


def archive_of(rel_path: str) -> str | None:
    """``Entlist141/Foo/Foo+1.jpg`` -> ``Entlist141.tar`` (None if no Entlist part)."""
    m = _ARCHIVE_RE.search(rel_path)
    return f"{m.group(1)}.tar" if m else None


def slug(node_id: str) -> str:
    """Filesystem-safe thumbnail name for a node id."""
    return _SLUG_RE.sub("_", node_key(node_id)).strip("_") + ".jpg"


def match_entities(node_ids, entity2image: dict) -> dict[str, list]:
    """Map node id -> its MMpedia image paths, for nodes present in entity2image.

    entity2image keys are canonicalized once so encoding differences (e.g. a
    node ``dbr:Ain't_I_a_Woman%3F`` vs key ``Ain't_I_a_Woman?``) still match.
    """
    by_key = {canonical_uri(k): v for k, v in entity2image.items()}
    out = {}
    for nid in node_ids:
        paths = by_key.get(node_key(nid))
        if paths:
            out[nid] = list(paths)
    return out


def load_focus_entities(validated_path: Path) -> set[str]:
    """dbr: node ids the eval renders: seeds + evidence subjects/objects."""
    if not validated_path.exists():
        print(f"  WARN {validated_path.name} missing - no entities to fetch")
        return set()
    focus: set[str] = set()
    for q in json.loads(validated_path.read_text(encoding="utf-8")):
        focus.update(s for s in q.get("seed_uris", []) if s.startswith("dbr:"))
        for t in q.get("evidence_triples", []):
            focus.update(v for v in (t.get("subject"), t.get("object"))
                         if v and v.startswith("dbr:"))
    return focus


def _degrees(edges) -> dict[str, int]:
    deg: dict[str, int] = {}
    for e in edges:
        deg[e["subject"]] = deg.get(e["subject"], 0) + 1
        deg[e["object"]] = deg.get(e["object"], 0) + 1
    return deg


def thumbnail(src, dest: Path, size: int = THUMB_SIZE) -> None:
    """Resize an image (path or file-like) to <=size px and save as JPEG."""
    with Image.open(src) as im:
        im = im.convert("RGB")
        im.thumbnail((size, size))
        dest.parent.mkdir(parents=True, exist_ok=True)
        im.save(dest, "JPEG", quality=85)


def _download(url: str, dest: Path) -> None:
    tmp = dest.with_name(dest.name + ".part")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        with open(tmp, "wb") as f, tqdm(total=total, unit="B", unit_scale=True,
                                        desc=dest.name) as bar:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
                bar.update(len(chunk))
    tmp.replace(dest)


def load_entity_images(mmpedia_dir: Path, auto_download: bool) -> dict | None:
    """Load entity2image.json from mmpedia_dir, downloading it if allowed. None if absent."""
    path = mmpedia_dir / ENTITY2IMAGE
    if not path.exists():
        if not auto_download:
            return None
        print(f"  downloading {ENTITY2IMAGE} (~1.4 GB)...")
        _download(f"{ZENODO_BASE}{ENTITY2IMAGE}?download=1", path)
    return json.loads(path.read_text(encoding="utf-8"))


def _ensure_archive(archive: str, mmpedia_dir: Path, auto_download: bool) -> Path | None:
    path = mmpedia_dir / archive
    if path.exists():
        return path
    if not auto_download:
        return None
    print(f"  downloading {archive} (~3 GB)...")
    _download(f"{ZENODO_BASE}{archive}?download=1", path)
    return path


def _archive_rel(rel: str) -> str:
    """entity2image paths are 'MMpedia/EntlistNNN/...'; tar members and extracted
    files are rooted at 'EntlistNNN/...' — drop the leading 'MMpedia/'."""
    return rel[len("MMpedia/"):] if rel.startswith("MMpedia/") else rel


def _first_existing(rel_paths, mmpedia_dir: Path) -> str | None:
    for rel in rel_paths:
        ar = _archive_rel(rel)
        if (mmpedia_dir / ar).exists():
            return ar
    return None


def _member(tar: tarfile.TarFile, rel_paths) -> str | None:
    names = set(tar.getnames())
    for rel in rel_paths:
        ar = _archive_rel(rel)
        if ar in names:
            return ar
    return None


def fetch_thumbnails(matched: dict, mmpedia_dir: Path, images_out: Path,
                     auto_download: bool) -> dict[str, str]:
    """Produce a thumbnail per matched entity; return node id -> 'images/<file>'.

    Resume-skip: entities whose thumbnail already exists are returned as-is, so
    an interrupted run doesn't re-download archives for work already done.
    """
    thumbs: dict[str, str] = {}
    by_archive: dict[str, list] = {}
    bar = tqdm(total=len(matched), unit="img", desc="thumbnails")

    for nid, paths in matched.items():
        dest = images_out / slug(nid)
        if dest.exists():
            thumbs[nid] = f"images/{dest.name}"
            bar.update(1)
            continue
        rel = _first_existing(paths, mmpedia_dir)
        if rel:
            try:
                thumbnail(mmpedia_dir / rel, dest)
                thumbs[nid] = f"images/{dest.name}"
            except Exception as exc:
                print(f"  WARN thumbnail {nid}: {exc}")
            bar.update(1)
        elif paths and (arc := archive_of(paths[0])):
            by_archive.setdefault(arc, []).append((nid, paths, dest))
        else:
            bar.update(1)

    for archive, entries in sorted(by_archive.items()):
        tar_path = _ensure_archive(archive, mmpedia_dir, auto_download)
        if tar_path is None:
            print(f"  {archive} not present (set MMPEDIA_AUTO_DOWNLOAD=1) - "
                  f"{len(entries)} entities skipped")
            bar.update(len(entries))
            continue
        with tarfile.open(tar_path) as tar:
            for nid, paths, dest in entries:
                name = _member(tar, paths)
                if name:
                    buf = io.BytesIO(tar.extractfile(name).read())
                    try:
                        thumbnail(buf, dest)
                        thumbs[nid] = f"images/{dest.name}"
                    except Exception as exc:
                        print(f"  WARN thumbnail {nid}: {exc}")
                bar.update(1)
        if not KEEP_ARCHIVES:
            tar_path.unlink(missing_ok=True)
    bar.close()
    return thumbs


def write_coverage(path: Path, nodes, degree, n_images, has_image_ids) -> None:
    """has_image reflects MMpedia AVAILABILITY (all nodes), not whether a
    thumbnail was fetched (which is scoped to the validated set)."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["entity", "has_image", "n_images", "degree", "abstract_len", "types"])
        for n in nodes:
            nid = n["id"]
            w.writerow([nid, nid in has_image_ids, n_images.get(nid, 0),
                        degree.get(nid, 0), len(n.get("abstract") or ""),
                        "|".join(n.get("types") or [])])


def run(kg_path: Optional[Path] = None, mmpedia_dir: Optional[Path] = None, images_out: Optional[Path] = None,
        coverage_path: Optional[Path] = None, validated_path: Optional[Path] = None,
        auto_download: Optional[bool] = None, fetch_all: Optional[bool] = None) -> None:
    kg_path = kg_path or KG_PATH
    mmpedia_dir = mmpedia_dir or MMPEDIA_DIR
    images_out = images_out or IMAGES_OUT
    coverage_path = coverage_path or COVERAGE_PATH
    validated_path = validated_path or VALIDATED_PATH
    auto_download = AUTO_DOWNLOAD if auto_download is None else auto_download
    fetch_all = FETCH_ALL if fetch_all is None else fetch_all

    print(f"AUTO_DOWNLOAD is {AUTO_DOWNLOAD}")
    print(f"FETCH_ALL is {FETCH_ALL}")
    print(f"KEEP_ARCHIVES is {KEEP_ARCHIVES}\n")

    print("loading kg_subset...")
    kg = json.loads(kg_path.read_text(encoding="utf-8"))
    nodes, edges = kg["nodes"], kg["edges"]
    degree = _degrees(edges)
    print(f"  {len(nodes)} nodes, {len(edges)} edges")

    entity2image = load_entity_images(mmpedia_dir, auto_download)
    available: dict[str, list] = {}
    if entity2image is None:
        print(f"  no {ENTITY2IMAGE} in {mmpedia_dir} and auto-download off - "
              "skipping images (missing image is RQ2 signal)")
    else:
        available = match_entities([n["id"] for n in nodes], entity2image)
        print(f"  {len(available)} / {len(nodes)} nodes have an MMpedia image")

    n_images = {nid: len(p) for nid, p in available.items()}
    write_coverage(coverage_path, nodes, degree, n_images, set(available))
    print(f"  coverage.csv -> {coverage_path} ({len(available)} of {len(nodes)} nodes have an image)")

    thumbs: dict[str, str] = {}
    if available:
        if fetch_all:
            to_fetch = available
            print(f"  MMPEDIA_FETCH_ALL=1: fetching all {len(to_fetch)} available images")
        else:
            focus = load_focus_entities(validated_path) & set(available)
            to_fetch = {nid: available[nid] for nid in focus}
            print(f"  fetching {len(to_fetch)} validated-question entities")
        thumbs = fetch_thumbnails(to_fetch, mmpedia_dir, images_out, auto_download)
        print(f"  {len(thumbs)} thumbnails ready -> {images_out}")

    changed = 0
    for n in nodes:
        rel = thumbs.get(n["id"])
        if rel and n.get("image") != rel:
            n["image"] = rel
            changed += 1
    if changed:
        tmp = kg_path.with_name(kg_path.name + ".tmp")
        tmp.write_text(json.dumps(kg, indent=2), encoding="utf-8")
        os.replace(tmp, kg_path)
        print(f"  filled {changed} node images; rewrote {kg_path.name}")


if __name__ == "__main__":
    run()
