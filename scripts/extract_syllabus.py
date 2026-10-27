#!/usr/bin/env python3
"""Conservative PDF extraction.

This initial extractor extracts candidate records only from clearly delimited
subject/paper headings. It deliberately does not guess missing codes, credits,
units or exam patterns. Uncertain documents are reported for review and do not
replace a previously validated category dataset.
"""
from __future__ import annotations
import hashlib, json, re, sys
from datetime import datetime, timezone
from pathlib import Path
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data/source-manifest.json"
DATA_ROOT = ROOT / "data/syllabus"
HISTORY = ROOT / "data/update-history.json"
MIN_TEXT_CHARS = 350
CATEGORY_FILES = {"DSC":"dsc.json","MDC":"mdc.json","VAC":"vac.json","SEC":"sec.json","Compulsory":"compulsory.json","AEC":"compulsory.json","HCP":"compulsory.json","Punjabi":"compulsory.json"}

def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
def read_json(path, default):
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return default
def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()
def clean(text):
    return re.sub(r"[ \t]+", " ", text.replace("\x00"," ")).strip()
def session_from(text, url):
    match = re.search(r"\b(20\d{2})\s*[-–/]\s*(\d{2,4})\b", text)
    if match:
        start, end = match.group(1), match.group(2)
        if len(end) == 2: end = start[:2] + end
        return f"{start}-{end}"
    match = re.search(r"/(20\d{2})/", url)
    return f"{match.group(1)}-{str(int(match.group(1))+1)[-2:]}" if match else None

def parse_document(doc):
    path = ROOT / doc["path"]
    reader = PdfReader(str(path), strict=True)
    if len(reader.pages) < 1: raise ValueError("PDF contains no pages")
    chunks = []
    for page in reader.pages:
        try: chunks.append(page.extract_text() or "")
        except Exception: chunks.append("")
    text = clean("\n".join(chunks))
    if len(text) < MIN_TEXT_CHARS:
        raise ValueError(f"Suspiciously small text extraction ({len(text)} chars); PDF may be scanned or extraction failed")
    # This parser only accepts explicit subject labels/headings; no speculative records.
    candidates = []
    lines = [clean(line) for line in text.splitlines() if clean(line)]
    subject_patterns = [
        re.compile(r"^(?:subject|paper)\s*(?:name|title)?\s*[:\-]\s*(.{4,120})$", re.I),
        re.compile(r"^(?:course title|title of paper)\s*[:\-]\s*(.{4,120})$", re.I),
    ]
    code_pattern = re.compile(r"^(?:paper\s*)?(?:code|course code)\s*[:\-]\s*([A-Z0-9][A-Z0-9./_-]{1,30})$", re.I)
    title_pattern = re.compile(r"^(?:paper title|title of paper|course title)\s*[:\-]\s*(.{3,160})$", re.I)
    credit_pattern = re.compile(r"^(?:credits?)\s*[:\-]\s*(\d+(?:\.\d+)?)$", re.I)
    semester_pattern = re.compile(r"\b(?:semester|sem\.?)\s*[-:]?\s*(I|II|III|IV|V|VI|VII|VIII|1|2|3|4|5|6|7|8)\b", re.I)
    current = {}
    for line in lines:
        sm = semester_pattern.search(line)
        if sm and "semester" not in current:
            roman = {"I":"1","II":"2","III":"3","IV":"4","V":"5","VI":"6","VII":"7","VIII":"8"}
            current["semester"] = roman.get(sm.group(1).upper(), sm.group(1))
        cm = code_pattern.match(line)
        if cm: current["paperCode"] = cm.group(1).strip()
        tm = title_pattern.match(line)
        if tm: current["paperTitle"] = tm.group(1).strip()
        cr = credit_pattern.match(line)
        if cr: current["credits"] = float(cr.group(1)) if "." in cr.group(1) else int(cr.group(1))
        for pattern in subject_patterns:
            sub = pattern.match(line)
            if sub:
                subject = sub.group(1).strip(" .:-")
                if len(subject) >= 3:
                    rec = dict(current)
                    rec["subject"] = subject
                    candidates.append(rec)
                    current = {k:v for k,v in current.items() if k == "semester"}
                break
    # A weak heuristic is not enough to publish a whole PDF as a dataset.
    unique = []
    seen = set()
    for rec in candidates:
        key = (rec.get("semester"), rec["subject"].casefold(), rec.get("paperCode","").casefold())
        if key not in seen:
            seen.add(key); unique.append(rec)
    if not unique:
        raise ValueError("No confidently delimited subject records found; retained prior dataset")
    return unique, text

def validate_candidates(records, doc):
    if len(records) < 2:
        raise ValueError(f"Only {len(records)} candidate record(s) extracted; below safe publication threshold")
    for record in records:
        if not record.get("subject") or len(record["subject"]) < 3: raise ValueError("Empty/invalid subject")
        if not record.get("semester") or str(record["semester"]) not in set("12345678"): raise ValueError("Missing/invalid semester in extracted candidate")
    return True

def main():
    manifest = read_json(MANIFEST, {"documents":{}})
    history = read_json(HISTORY, {"schemaVersion":"1.0","updates":[]})
    changed_docs = []
    for doc in manifest.get("documents", {}).values():
        path = ROOT / doc.get("path","")
        if not path.exists() or not doc.get("category"): continue
        category = doc["category"]
        filename = CATEGORY_FILES.get(category)
        if not filename: continue
        try:
            records, extracted_text = parse_document(doc)
            validate_candidates(records, doc)
            session = session_from(extracted_text, doc["url"])
            if not session:
                raise ValueError("Academic session could not be established from official document")
            final_records = []
            for rec in records:
                final_records.append({
                    "course":doc.get("course","ba"), "programme":doc.get("course","ba").upper(),
                    "semester":rec["semester"], "category":category, "subject":rec["subject"],
                    "paperCode":rec.get("paperCode"), "paperTitle":rec.get("paperTitle"),
                    "paperType":None, "credits":rec.get("credits"), "units":None,
                    "detailedTopics":None, "qpStructure":None, "examinationPattern":None,
                    "academicSession":session, "sourceUrl":doc["url"], "documentHash":doc["sha256"],
                    "documentName":Path(doc["path"]).name, "lastChecked":manifest.get("lastChecked"),
                    "lastUpdated":doc.get("downloadedAt")
                })
            target = DATA_ROOT / str(doc.get("course","ba")).lower() / filename
            old_obj = read_json(target, {"records":[]})
            old_records = old_obj.get("records",[]) if isinstance(old_obj,dict) else old_obj
            # Keep other source documents' records; replace only records from this exact source URL.
            retained = [r for r in old_records if r.get("sourceUrl") != doc["url"]]
            merged = retained + final_records
            merged.sort(key=lambda r:(str(r.get("semester","")),str(r.get("subject","")).casefold()))
            target_obj = {"schemaVersion":"1.0","course":doc.get("course","ba"),"category":category,
                          "academicSession":session,"lastUpdated":now(),"status":"validated_extraction",
                          "recordCount":len(merged),"records":merged}
            # Atomic write only after validation.
            target.parent.mkdir(parents=True, exist_ok=True)
            temp = target.with_suffix(".json.tmp")
            temp.write_text(json.dumps(target_obj,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
            temp.replace(target)
            changed_docs.append({"document":doc["path"],"sourceUrl":doc["url"],"sha256":doc["sha256"],"records":len(final_records),"category":category,"session":session})
            print(f"Validated {len(final_records)} records from {doc['path']}")
        except Exception as exc:
            print(f"SAFE SKIP {doc.get('path')}: {exc}", file=sys.stderr)
    if changed_docs:
        history.setdefault("updates",[]).append({"timestamp":now(),"documents":changed_docs})
        history["updates"] = history["updates"][-100:]
        temp = HISTORY.with_suffix(".json.tmp")
        temp.write_text(json.dumps(history,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        temp.replace(HISTORY)
    # Do not fail the whole workflow merely because one document needs human review.
    # The workflow validation stage verifies that existing JSON remains structurally valid.
if __name__ == "__main__":
    main()
