#!/usr/bin/env python3
"""Validate published JSON and enforce safe-publish invariants."""
import hashlib, json, re, sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/syllabus"
ALLOWED_HOSTS = {"puchd.ac.in","www.puchd.ac.in","websys.puchd.ac.in","www.manuscripts.puchd.ac.in","manuscripts.puchd.ac.in"}
errors = []
count = 0
seen = set()
for path in sorted(DATA.glob("**/*.json")):
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"{path.relative_to(ROOT)}: invalid JSON: {exc}"); continue
    records = obj.get("records", []) if isinstance(obj, dict) else obj
    if not isinstance(records, list):
        errors.append(f"{path.relative_to(ROOT)}: records must be a list"); continue
    for i, rec in enumerate(records):
        count += 1
        prefix = f"{path.relative_to(ROOT)} record {i}"
        for field in ("course","semester","category","subject","sourceUrl","documentHash","academicSession"):
            if not rec.get(field): errors.append(f"{prefix}: missing required {field}")
        if rec.get("subject") and len(str(rec["subject"]).strip()) < 3: errors.append(f"{prefix}: suspicious subject")
        url = rec.get("sourceUrl","")
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS: errors.append(f"{prefix}: source is not an allowed official PU host")
        digest = rec.get("documentHash","")
        if not re.fullmatch(r"[a-f0-9]{64}", digest): errors.append(f"{prefix}: invalid SHA-256 documentHash")
        key = (str(rec.get("course")).lower(),str(rec.get("semester")),str(rec.get("category")).lower(),str(rec.get("subject")).casefold(),str(rec.get("paperCode") or "").casefold(),url)
        if key in seen: errors.append(f"{prefix}: duplicate record key")
        seen.add(key)
print(f"Validated {count} published syllabus records.")
if errors:
    print("\n".join("ERROR: "+e for e in errors), file=sys.stderr)
    sys.exit(1)
