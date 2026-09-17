#!/usr/bin/env python
"""Build knowledge/manifest/knowledge_manifest.csv (UTF-8 with BOM).

Sources of truth
----------------
* scripts/_kb_shared.py  -> registry (id, title, authority, level, type, version,
  diseases, scenarios, qianfan_kb, source_url, domain dir)
* knowledge/raw/_download_report.json -> what was really downloaded, its path,
  size, sha256 and the real error for whatever failed
* knowledge/raw/_dates.json -> publish date pulled out of the official page

Nothing is invented: a document that could not be downloaded becomes
status=draft / local_file=PENDING / empty sha256 with a `pending manual
download: ...` note.

Usage: python scripts/build_manifest.py [--date-report path]
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _kb_shared as S  # noqa: E402

# Dates that the official annex (not the notice page) states, or that were read
# on the official page by scripts/extract_publish_dates.py. Applied only when the
# page extraction found nothing, and never guessed.
DATE_OVERRIDES = {
    "HTN001": "2025-09-19",   # 发布日期 stated in the WS/T 872-2025 annex PDF
    "PRIM003": "2015-10-14",  # 国卫办基层发〔2015〕46号
    "MULTI002": "2023-04-15",  # 2023041513592396.pdf upload path 2023/04
}


#: 已下载、但**不得进入生产检索**的文档。
#:
#: 判据来自 `scripts/verify_content_match.py` 的 title_bigram_ratio：
#: 若文件内容里几乎找不到注册标题的字样，说明抓到的不是这份文档（典型是无文本层扫描件
#: 只剩少量版式文字）。这类文件保留在磁盘上作为来源记录，但 status=draft，
#: 生产检索只使用 status=active，因此不会污染 Citation。
FORCE_DRAFT = {
    "LIFE001A": "内容与标题不匹配（title_bigram_ratio=0.11）："
    "官方附件为扫描件，文本层仅约 456 字符，需 OCR",
    "LIFE001B": "内容与标题不匹配（title_bigram_ratio=0.11）："
    "官方附件为扫描件，文本层仅约 472 字符，需 OCR",
    "LIFE001C": "内容与标题不匹配（title_bigram_ratio=0.05）："
    "官方附件为扫描件，文本层仅约 503 字符，需 OCR",
}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date-report", default=str(S.RAW_DIR / "_dates.json"))
    args = ap.parse_args(argv[1:])

    S.ensure_dirs()
    dl = S.load_json(S.DOWNLOAD_REPORT) or {"documents": []}
    by_id = {d["document_id"]: d for d in dl.get("documents", [])}
    dates = S.load_json(args.date_report) or {}

    rows = []
    for doc in S.DOCUMENTS:
        did = doc["document_id"]
        e = by_id.get(did, {})
        status = e.get("status", "")
        local = e.get("local_file", "")
        sha = e.get("sha256", "")
        notes = doc["notes"]

        if status in ("downloaded", "skipped") and local:
            with open(S.PROJECT_ROOT / local, "rb") as fh:  # ensure it is still there
                fh.read(1)
            row_status = "active"
            if did in FORCE_DRAFT:
                # 文件已拿到但内容不可用于检索：保留 local_file/sha256 作来源记录，
                # 只把 status 降为 draft（生产检索只使用 active）
                row_status = "draft"
                notes = (notes + "; " if notes else "") + FORCE_DRAFT[did]
            if e.get("waf_note"):
                notes = (notes + "; " if notes else "") + e["waf_note"]
            if e.get("annex_pdf"):
                notes = (notes + "; " if notes else "") + f"annex pdf: {e['annex_pdf']}"
        else:
            row_status = "draft"
            local = "PENDING"
            sha = ""
            reason = (e.get("error") or "download failed").replace("\n", " ")[:200]
            notes = (notes + "; " if notes else "") + f"pending manual download: {reason}"

        # 优先级：官方页面抽取值 > 人工核定的 DATE_OVERRIDES > 注册表内置值
        # （注册表内置值此前被漏掉，导致人工核定的发布日期进不了 manifest）
        publish = (
            (dates.get(did, {}) or {}).get("publish_date", "")
            or DATE_OVERRIDES.get(did, "")
            or doc.get("publish_date", "")
        )
        effective = (dates.get(did, {}) or {}).get("effective_date", "") or doc["effective_date"]
        rows.append({
            "document_id": did,
            "title": doc["title"],
            "authority": doc["authority"],
            "authority_level": doc["authority_level"],
            "document_type": doc["document_type"],
            "version": doc["version"],
            "publish_date": publish,
            "effective_date": effective,
            "replaced_by": doc["replaced_by"],
            "status": row_status,
            "diseases": "|".join(doc["diseases"]),
            "scenarios": "|".join(doc["scenarios"]),
            "language": doc["language"],
            "source_url": doc["source_url"],
            "local_file": local if local == "PENDING" else S.relpath(S.PROJECT_ROOT / local),
            "sha256": sha,
            "qianfan_kb": doc["qianfan_kb"],
            "notes": notes.strip(),
        })

    S.MANIFEST_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(S.MANIFEST_CSV, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=S.MANIFEST_COLUMNS, lineterminator="\r\n")
        w.writeheader()
        w.writerows(rows)

    active = sum(1 for r in rows if r["status"] == "active")
    print(f"manifest -> {S.relpath(S.MANIFEST_CSV)}")
    print(f"rows={len(rows)} active={active} draft={len(rows) - active}")
    for r in rows:
        if r["status"] != "active":
            print(f"  draft {r['document_id']:<8} {r['notes'][:110]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
