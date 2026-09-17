#!/usr/bin/env python
"""Sanity check that every downloaded file really is the registered document.

Wild guesswork is not acceptable in a knowledge base, so this script prints the
opening text of each PDF/HTML and checks for token overlap with the registry
title. Output: knowledge/raw/_content_check.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _kb_shared as S  # noqa: E402

PUNCT = re.compile(r"[\s\u3000\-—_（）()《》〈〉【】\[\].,、；;:：!！?？\"'“”‘’／/]+")


def stem(t: str) -> str:
    return PUNCT.sub("", t)


def bigrams(t: str) -> set:
    s = stem(t)
    return {s[i:i + 2] for i in range(len(s) - 1)}


def main() -> int:
    report = S.load_json(S.DOWNLOAD_REPORT) or {}
    out = {}
    for e in report.get("documents", []):
        did = e["document_id"]
        doc = S.DOCS_BY_ID[did]
        head = ""
        rel = e.get("annex_pdf") or (e.get("local_file") if e.get("ext") == "pdf" else "")
        if rel and rel.endswith(".pdf"):
            p = S.PROJECT_ROOT / rel
            if p.exists():
                try:
                    import pymupdf
                    with pymupdf.open(p) as pdf:
                        head = "".join(pdf[i].get_text("text") for i in range(min(3, pdf.page_count)))
                except Exception as exc:  # noqa: BLE001
                    head = f"<pdf error {exc}>"
        elif e.get("local_file", "").endswith(".html"):
            p = S.PROJECT_ROOT / e["local_file"]
            if p.exists():
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(p.read_text(encoding="utf-8", errors="replace"), "lxml")
                for t in soup(["script", "style"]):
                    t.decompose()
                head = soup.get_text(" ", strip=True)[:4000]

        title_bg = bigrams(doc["title"])
        flat = stem(head[:4000])
        head_bg = {flat[i:i + 2] for i in range(len(flat) - 1)}
        overlap = len((title_bg & head_bg))
        ratio = round(overlap / max(1, len(title_bg)), 3)
        out[did] = {
            "registry_title": doc["title"],
            "source": rel or e.get("local_file", ""),
            "title_bigram_overlap": overlap,
            "title_bigram_ratio": ratio,
            "head": " ".join(head[:260].split()),
        }
        flag = "OK  " if ratio >= 0.34 else ("??  " if ratio >= 0.15 else "MISMATCH")
        print(f"{flag} {did:<8} ratio={ratio:<5} {doc['title'][:34]}")
        print(f"        {out[did]['head'][:150]}")
    S.dump_json(S.RAW_DIR / "_content_check.json", out)
    print("->", S.relpath(S.RAW_DIR / "_content_check.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
