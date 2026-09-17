#!/usr/bin/env python
"""Hard validation of knowledge/manifest/knowledge_manifest.csv.

Exits non-zero when any check fails. Problems go to stderr and, unless
--no-report-file is given, to knowledge/manifest/_validation_report.json.

Checks
------
* document_id non-empty and unique
* authority_level in {P0..P4}, status in {active,superseded,draft,disabled}
* document_type / diseases / scenarios / qianfan_kb inside the controlled vocabularies
* source_url non-empty and starting with http
* status=active  -> local_file exists and its sha256 matches the manifest
* status!=active -> local_file may be PENDING and sha256 may be empty
* replaced_by, when set, points at an existing document_id and forms no cycle
* title / authority / version non-empty

Usage:
    python scripts/validate_manifest.py [--json] [--manifest PATH]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _kb_shared as S  # noqa: E402

REPORT = S.MANIFEST_DIR / "_validation_report.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def validate(manifest: Path) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    checks: dict[str, int] = {}

    if not manifest.exists():
        return {"ok": False, "errors": [f"manifest not found: {manifest}"],
                "warnings": [], "checks": {}, "rows": 0}

    raw = manifest.read_bytes()
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    if not has_bom:
        warnings.append("manifest is not UTF-8 with BOM (utf-8-sig)")

    with open(manifest, "r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    checks["rows"] = len(rows)
    if fieldnames != S.MANIFEST_COLUMNS:
        errors.append(
            "column order mismatch:\n  expected: " + ",".join(S.MANIFEST_COLUMNS)
            + "\n  actual:   " + ",".join(fieldnames))

    seen_ids: dict[str, int] = {}
    for i, row in enumerate(rows, start=2):  # +1 header, +1 1-based
        def bad(msg: str):
            errors.append(f"line {i} [{row.get('document_id','?')}]: {msg}")

        did = (row.get("document_id") or "").strip()
        if not did:
            bad("document_id is empty")
        elif did in seen_ids:
            bad(f"duplicate document_id (first seen on line {seen_ids[did]})")
        else:
            seen_ids[did] = i

        for col in ("title", "authority", "version"):
            if not (row.get(col) or "").strip():
                bad(f"{col} is empty")

        level = (row.get("authority_level") or "").strip()
        if level not in S.AUTHORITY_LEVELS:
            bad(f"authority_level '{level}' not in {sorted(S.AUTHORITY_LEVELS)}")

        status = (row.get("status") or "").strip()
        if status not in S.STATUSES:
            bad(f"status '{status}' not in {sorted(S.STATUSES)}")

        dtype = (row.get("document_type") or "").strip()
        if dtype not in S.DOCUMENT_TYPES:
            bad(f"document_type '{dtype}' not in {sorted(S.DOCUMENT_TYPES)}")

        kb = (row.get("qianfan_kb") or "").strip()
        if kb not in S.QIANFAN_KBS:
            bad(f"qianfan_kb '{kb}' not in {sorted(S.QIANFAN_KBS)}")

        for col, vocab in (("diseases", S.DISEASES), ("scenarios", S.SCENARIOS)):
            val = (row.get(col) or "").strip()
            if not val:
                bad(f"{col} is empty")
                continue
            tokens = [t for t in val.split("|") if t]
            for t in tokens:
                if t not in vocab:
                    bad(f"{col} token '{t}' not in the controlled vocabulary")
            if len(tokens) != len(set(tokens)):
                bad(f"{col} contains duplicate tokens")

        url = (row.get("source_url") or "").strip()
        if not url:
            bad("source_url is empty")
        elif not url.startswith("http"):
            bad(f"source_url does not start with http: {url}")

        lang = (row.get("language") or "").strip()
        if lang not in ("zh", "en"):
            bad(f"language '{lang}' must be zh or en")

        local = (row.get("local_file") or "").strip()
        sha = (row.get("sha256") or "").strip()
        if status == "active":
            if not local or local == "PENDING":
                bad("status=active but local_file is PENDING/empty")
            else:
                p = S.PROJECT_ROOT / local
                if not p.exists():
                    bad(f"status=active but local_file does not exist: {local}")
                else:
                    actual = sha256_file(p)
                    if not sha:
                        bad("status=active but sha256 is empty")
                    elif actual != sha:
                        bad(f"sha256 mismatch for {local}: manifest={sha[:12]}... actual={actual[:12]}...")
        elif status == "superseded":
            if local != "PENDING" and local and not (S.PROJECT_ROOT / local).exists():
                bad(f"status=superseded but local_file missing: {local}")
        else:
            if sha:
                bad(f"status={status} but sha256 is not empty")

        if len(sha) not in (0, 64):
            bad(f"sha256 length {len(sha)} is not 64")

    # replaced_by integrity
    for row in rows:
        rb = (row.get("replaced_by") or "").strip()
        if rb and rb not in seen_ids:
            errors.append(f"replaced_by '{rb}' of {row['document_id']} does not exist")

    graph = {r["document_id"]: (r.get("replaced_by") or "").strip() for r in rows}
    for start in list(graph):
        seen = set()
        node = start
        while graph.get(node):
            if node in seen:
                errors.append(f"replaced_by cycle detected involving {node}")
                break
            seen.add(node)
            node = graph[node]

    checks["active"] = sum(1 for r in rows if (r.get("status") or "").strip() == "active")
    checks["draft"] = sum(1 for r in rows if (r.get("status") or "").strip() == "draft")
    checks["distinct_document_ids"] = len(seen_ids)
    checks["bom"] = int(has_bom)
    checks["errors"] = len(errors)
    checks["warnings"] = len(warnings)
    return {"ok": not errors, "errors": errors, "warnings": warnings,
            "checks": checks, "rows": len(rows)}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="machine readable result on stdout")
    ap.add_argument("--manifest", default=str(S.MANIFEST_CSV))
    ap.add_argument("--no-report-file", action="store_true")
    args = ap.parse_args(argv[1:])

    result = validate(Path(args.manifest))
    result["manifest"] = str(args.manifest)

    if not args.no_report_file:
        S.dump_json(REPORT, result)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for w in result["warnings"]:
            print(f"WARN  {w}", file=sys.stderr)
        for e in result["errors"]:
            print(f"ERROR {e}", file=sys.stderr)
        print(f"manifest: {result['manifest']}")
        print(f"checks: {json.dumps(result['checks'], ensure_ascii=False)}")
        if result["ok"]:
            print("VALIDATION PASSED")
        else:
            print(f"VALIDATION FAILED with {len(result['errors'])} error(s)", file=sys.stderr)

    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
