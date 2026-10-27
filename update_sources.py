#!/usr/bin/env python3
"""Discover and download official PU syllabus PDFs, keeping a hash manifest.

Safety: downloaded files are staged first; the extractor only publishes records
when validation passes. A URL change alone is not treated as a document change.
"""
from __future__ import annotations
import hashlib, json, os, re, sys, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, urldefrag
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "data/sources.json"
MANIFEST = ROOT / "data/source-manifest.json"
PDF_ROOT = ROOT / "data/source-pdfs"
ALLOWED_HOSTS = {"puchd.ac.in", "www.puchd.ac.in", "websys.puchd.ac.in", "www.manuscripts.puchd.ac.in", "manuscripts.puchd.ac.in"}
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "CollegeSyllabusBuddy/1.0 (official syllabus change monitor; GitHub Actions)"})
TIMEOUT = (15, 60)
MAX_PDF_BYTES = 50 * 1024 * 1024

def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def safe_name(url: str) -> str:
    name = Path(urlparse(url).path).name or "document.pdf"
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    if not name.lower().endswith(".pdf"): name += ".pdf"
    return name[:150]

def official(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and parsed.hostname in ALLOWED_HOSTS

def get_manifest():
    if MANIFEST.exists():
        try: return json.loads(MANIFEST.read_text(encoding="utf-8"))
        except Exception: pass
    return {"schemaVersion":"1.0","documents":{}}

def save_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)

def discover():
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    docs = {item["url"]: {**item, "discoveredFrom":"seed"} for item in config.get("seedDocuments", [])}
    for index in config.get("indexes", []):
        url = index["url"]
        if not official(url): print(f"Skipping non-official index: {url}", file=sys.stderr); continue
        try:
            response = SESSION.get(url, timeout=TIMEOUT)
            response.raise_for_status()
            if "html" not in response.headers.get("content-type", "").lower() and not response.text.lstrip().lower().startswith(("<!doctype html", "<html")):
                print(f"Index did not return HTML: {url}", file=sys.stderr); continue
            soup = BeautifulSoup(response.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = urljoin(response.url, a["href"].strip())
                href, _ = urldefrag(href)
                if not official(href): continue
                text = " ".join(a.get_text(" ", strip=True).split())
                path = urlparse(href).path.lower()
                context = (text + " " + path).lower()
                # Only PDF/document links or clearly labelled syllabus links are candidates.
                is_pdf = path.endswith(".pdf")
                syllabus_hint = any(term in context for term in ("syllabus", "nep", "paper", "course", "semester", "b.a", "b.sc", "b.com", "bba"))
                if is_pdf and syllabus_hint:
                    docs.setdefault(href, {"url":href,"course":index.get("course","unknown"),"category":"unknown","label":text or safe_name(href),"discoveredFrom":url})
        except Exception as exc:
            print(f"Warning: index check failed for {url}: {exc}", file=sys.stderr)
    return docs

def download_one(url, info, manifest):
    if not official(url): raise ValueError(f"Refusing non-official URL: {url}")
    response = SESSION.get(url, timeout=TIMEOUT, stream=True)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "").lower()
    chunks, size = [], 0
    for chunk in response.iter_content(1024 * 128):
        if not chunk: continue
        size += len(chunk)
        if size > MAX_PDF_BYTES: raise ValueError(f"PDF exceeds {MAX_PDF_BYTES} bytes")
        chunks.append(chunk)
    data = b"".join(chunks)
    if len(data) < 1024 or not data.startswith(b"%PDF-"):
        raise ValueError(f"Response is not a valid PDF (size={len(data)}, content-type={content_type})")
    digest = sha256(data)
    previous = manifest["documents"].get(url, {})
    # Hash is authoritative: ETag/Last-Modified and URL are hints only.
    if previous.get("sha256") == digest and previous.get("path") and (ROOT / previous["path"]).exists():
        return previous, False
    folder = PDF_ROOT / re.sub(r"[^a-z0-9_-]", "", str(info.get("course","unknown")).lower())
    filename = safe_name(url)
    destination = folder / filename
    # Preserve prior version when bytes change.
    if destination.exists() and sha256(destination.read_bytes()) != digest:
        archive = folder / "versions"
        archive.mkdir(parents=True, exist_ok=True)
        old_hash = sha256(destination.read_bytes())[:12]
        shutil_path = archive / f"{destination.stem}-{old_hash}{destination.suffix}"
        if not shutil_path.exists(): shutil_path.write_bytes(destination.read_bytes())
    folder.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(destination.suffix + ".part")
    temp.write_bytes(data)
    # Validate PDF container with pypdf before moving into active source location.
    from pypdf import PdfReader
    reader = PdfReader(str(temp), strict=True)
    if len(reader.pages) < 1: raise ValueError("PDF has no pages")
    temp.replace(destination)
    record = {
        **info, "url":url, "path":str(destination.relative_to(ROOT)), "sha256":digest,
        "size":len(data), "etag":response.headers.get("ETag"),
        "lastModified":response.headers.get("Last-Modified"), "downloadedAt":now(),
        "pages":len(reader.pages), "contentType":content_type
    }
    return record, True

def main():
    manifest = get_manifest()
    manifest.setdefault("documents", {})
    candidates = discover()
    changed = []
    errors = []
    for url, info in candidates.items():
        try:
            record, did_change = download_one(url, info, manifest)
            manifest["documents"][url] = record
            if did_change: changed.append(record)
        except Exception as exc:
            errors.append({"url":url,"error":str(exc)})
            print(f"WARNING: {url}: {exc}", file=sys.stderr)
    # Only persist tracked metadata when at least one PDF's actual bytes changed.
    # A no-change poll must not create a commit just to update timestamps/status.
    previous_manifest = get_manifest()
    if changed:
        manifest["lastChecked"] = now()
        save_json(MANIFEST, manifest)
        save_json(ROOT / "data/discovery-report.json", {
            "checkedAt": now(), "candidateCount": len(candidates),
            "changedCount": len(changed), "errors": errors,
            "changed": [{"url":x["url"],"sha256":x["sha256"]} for x in changed]
        })
    print(f"Candidates: {len(candidates)}; changed/new PDFs: {len(changed)}; errors: {len(errors)}")
    # Fail only when all official index requests and all seed downloads failed.
    if errors and not manifest["documents"]:
        raise RuntimeError("No official documents could be validated; no syllabus data should be published.")
if __name__ == "__main__":
    main()
