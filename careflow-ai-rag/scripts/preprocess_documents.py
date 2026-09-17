#!/usr/bin/env python
"""Clean the downloaded raw HTML/PDF corpus into Markdown.

Input : knowledge/raw/_download_report.json + the files it points at
Output: knowledge/processed/<document_id>.md
        knowledge/processed/_preprocess_report.json

Rules
-----
* Navigation, breadcrumbs, share widgets, scripts, styles, headers and footers
  are removed; the article body is kept.
* Heading hierarchy from the source (h1..h6, or bold/large PDF lines) is kept as
  Markdown #/##/###.
* Tables become Markdown tables with their header row and every cell preserved.
* Paragraphs are separated by blank lines.
* Text is never rewritten, summarised or translated: nothing but whitespace and
  zero-width characters is normalised.

Usage:
    python scripts/preprocess_documents.py             # all downloaded docs
    python scripts/preprocess_documents.py HTN001 ...
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _kb_shared as S  # noqa: E402

ZW = dict.fromkeys(map(ord, "\u200b\u200c\u200d\ufeff\u00ad"), None)

DROP_TAGS = ("script", "style", "noscript", "iframe", "form", "svg", "button",
             "nav", "header", "footer", "aside", "video", "audio", "canvas")

DROP_CLASS_PAT = re.compile(
    r"(nav|menu|crumb|bread|breadcrumb|foot|footer|header|top|banner|share|bdshare"
    r"|sidebar|side-bar|advert|advertise|ad-|_ad|qr|weixin|weibo|print|search"
    r"|related|recommend|hotword|keyword|tag-list|comment|pagination|page-nav"
    r"|toolbar|breadcrumb|skip|copyright|statement|bqsm|szsm|fx\b)", re.I)

BODY_IDS = ["xw_box", "zoom", "content", "con", "article", "artibody", "UCAP-CONTENT"]
BODY_CLASSES = ["article-content", "art-con", "news_content", "content_box",
                "TRS_Editor", "view TRS_UEDITOR", "con", "article", "rich_media_content"]

HEADING_RE_CN = re.compile(
    r"^(?:第[一二三四五六七八九十百]+[章节部分]|[一二三四五六七八九十]+[、.．)）]"
    r"|（[一二三四五六七八九十]+）|\([一二三四五六七八九十]+\)"
    r"|\d+(?:\.\d+){0,3}[、.．)）]?\s*\S)"
)
ANNEX_RE = re.compile(r"^\s*附件\s*\d*\s*[:：]?")

MD_INLINE = re.compile(r"([\\`*_{}\[\]<>#+\-.!|~])")


def log(msg: str) -> None:
    print(msg, flush=True)


def norm(text: str) -> str:
    """Normalise only whitespace / zero-width chars. Never rewords text."""
    t = text.translate(ZW)
    t = t.replace("\xa0", " ").replace("\u3000", " ")
    t = re.sub(r"[ \t\r\f\v]+", " ", t)
    t = re.sub(r" *\n *", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def md_escape(cell: str) -> str:
    c = norm(cell).replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")
    return re.sub(r"\s+", " ", c).strip()


# --------------------------------------------------------------------------- #
# HTML
# --------------------------------------------------------------------------- #
def drop_noise(soup):
    from bs4 import Comment
    for tag in soup.find_all(list(DROP_TAGS)):
        tag.decompose()
    for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
        c.extract()
    for tag in soup.find_all(True):
        # decompose() 会把节点 attrs 置为 None；同一次遍历里后续可能再遇到这类节点
        if tag.attrs is None:
            continue
        attrs = " ".join(
            str(v) for k, v in tag.attrs.items() if k in ("class", "id", "role"))
        if not attrs:
            continue
        if DROP_CLASS_PAT.search(attrs):
            tag.decompose()


def find_body_container(soup):
    """Locate the outermost realistic article container (not the <body>)."""
    best = None
    for i in BODY_IDS:
        node = soup.find(id=i)
        if node is not None and len(node.get_text(strip=True)) > 200:
            best = node
            break
    if best is None:
        for cls in BODY_CLASSES:
            for node in soup.find_all(class_=re.compile(re.escape(cls.split()[0]), re.I)):
                if len(node.get_text(strip=True)) > 300:
                    best = node
                    break
            if best is not None:
                break
    if best is None:
        # fall back to the densest <div>/<article> subtree
        cands = []
        for node in soup.find_all(["article", "div", "section"]):
            txt = node.get_text(strip=True)
            if len(txt) < 400:
                continue
            # prefer containers whose text is not dominated by link text
            link_len = sum(len(a.get_text(strip=True)) for a in node.find_all("a"))
            cands.append((len(txt) - 2 * link_len, len(txt), node))
        if cands:
            cands.sort(key=lambda x: (-x[0], -x[1]))
            best = cands[0][2]
    return best or soup.body or soup


def table_to_md(tbl) -> list:
    rows = tbl.find_all("tr")
    grid: list[list[str]] = []
    for tr in rows:
        cells = tr.find_all(["th", "td"], recursive=False) or tr.find_all(["th", "td"])
        if not cells:
            continue
        row = []
        for cell in cells:
            txt = md_escape(cell.get_text(" ", strip=True))
            try:
                span = int(cell.get("colspan", 1) or 1)
            except (TypeError, ValueError):
                span = 1
            row.append((txt, span))
        grid.append(row)
    if not grid:
        return []
    width = max(sum(sp for _, sp in row) for row in grid)
    out_rows = []
    for row in grid:
        flat = []
        for txt, span in row:
            flat.append(txt)
            if span > 1:
                flat.extend([txt] * (span - 1))
        flat += [""] * (width - len(flat))
        out_rows.append(flat[:width])
    header = out_rows[0]
    lines = ["| " + " | ".join(header) + " |",
             "| " + " | ".join(["---"] * width) + " |"]
    for row in out_rows[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return lines


def element_md(el, level: int = 0, seen=None) -> list:
    from bs4 import NavigableString, Tag

    if seen is None:
        seen = set()
    out: list[str] = []
    for child in el.children:
        if isinstance(child, NavigableString):
            txt = norm(str(child))
            if txt:
                out.append(txt)
            continue
        if not isinstance(child, Tag) or id(child) in seen:
            continue
        seen.add(id(child))
        name = child.name.lower()
        if name in ("script", "style", "noscript"):
            continue
        if name == "table":
            md = table_to_md(child)
            if md:
                out.append("\n".join(md))
            continue
        if name == "img":
            alt = norm(child.get("alt", "") or "")
            src = child.get("src", "") or ""
            if alt or src:
                out.append(f"![{alt}]({src})" if src else f"({alt})")
            continue
        if name == "br":
            out.append("")
            continue
        if name in ("ul", "ol"):
            for li in child.find_all("li", recursive=False):
                item = " ".join(x for x in element_md(li, level + 1, seen) if x)
                item = norm(item)
                if item:
                    out.append(("- " if name == "ul" else "1. ") + item)
            continue
        if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            txt = norm(child.get_text(" ", strip=True))
            if txt:
                lv = H_TAGS.index(name) + 1
                out.append("#" * min(lv, 4) + " " + txt)
            continue
        if name == "p":
            parts = [x for x in element_md(child, level + 1, seen) if x]
            ps = []
            for part in parts:
                ps.extend(part.split("\n\n"))
            out.append("\n".join(ps))
            continue
        if name in ("div", "section", "article", "main", "span", "td", "th",
                    "blockquote", "strong", "b", "em", "font", "a", "sup", "sub",
                    "center", "tbody", "tr", "label", "time", "figure"):
            parts = [x for x in element_md(child, level + 1, seen) if x]
            if parts:
                out.append("\n\n".join(parts))
            continue
        parts = [x for x in element_md(child, level + 1, seen) if x]
        if parts:
            out.append("\n\n".join(parts))
    return out


H_TAGS = ["h1", "h2", "h3", "h4", "h5", "h6"]


def html_to_md(raw: str, doc: dict) -> tuple[str, dict]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(raw, "lxml")
    page_title = norm(soup.title.get_text(" ", strip=True)) if soup.title else ""
    h1 = soup.find("h1")
    h1_text = norm(h1.get_text(" ", strip=True)) if h1 else ""

    drop_noise(soup)
    container = find_body_container(soup)

    blocks = element_md(container)
    blocks = [norm(b) for b in blocks]
    while blocks and not blocks[0].strip():
        blocks.pop(0)
    blocks = [b for b in blocks if b.strip()]

    # de-duplicate consecutive identical blocks
    dedup = []
    for b in blocks:
        if not dedup or dedup[-1] != b:
            dedup.append(b)
    blocks = dedup

    # crawl the neighbours after the container (nhc puts body inline sometimes)
    title_line = doc["title"]
    lines = [f"# {title_line}"]
    lines.append("")
    meta = {"page_title": page_title, "h1": h1_text, "blocks": len(blocks)}
    stats = {"headings": 0, "tables": 0}
    for b in blocks:
        if b.startswith("#"):
            stats["headings"] += 1
        if b.startswith("| "):
            stats["tables"] += 1
        lines.append(b)
        lines.append("")
    text = norm("\n".join(lines))
    return text, {**meta, **stats}


# --------------------------------------------------------------------------- #
# PDF
# --------------------------------------------------------------------------- #
def pdf_to_md(path: Path, doc: dict, max_pages: int | None = None) -> tuple[str, dict]:
    import pymupdf

    spans_by_size: dict[float, int] = {}
    page_lines: list[list[dict]] = []
    with pymupdf.open(path) as pdf:
        n_pages = pdf.page_count
        pages = range(n_pages) if max_pages is None else range(min(n_pages, max_pages))
        for pno in pages:
            page = pdf[pno]
            d = page.get_text("dict")
            lines = []
            for block in d.get("blocks", []):
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    spans = [s for s in line.get("spans", []) if (s.get("text") or "").strip()]
                    if not spans:
                        continue
                    text = "".join(s["text"] for s in spans)
                    sizes = [round(float(s.get("size", 0)), 1) for s in spans]
                    size = max(sizes) if sizes else 0.0
                    bold = any(("bold" in (s.get("font", "") or "").lower()
                                or s.get("flags", 0) & 16) for s in spans)
                    lines.append({"text": text, "size": size, "bold": bool(bold),
                                  "x0": round(float(line["bbox"][0]), 1),
                                  "y0": round(float(line["bbox"][1]), 1)})
                    spans_by_size[size] = spans_by_size.get(size, 0) + len(text)
            page_lines.append(lines)

    body_size = max(spans_by_size.items(), key=lambda kv: kv[1])[0] if spans_by_size else 0.0
    heading_sizes = sorted({sz for sz in spans_by_size if sz >= body_size + 1.0}, reverse=True)
    size_level = {}
    for i, sz in enumerate(heading_sizes):
        size_level[sz] = min(i + 2, 4)  # h2..h4

    def is_heading(ln: dict) -> int | None:
        txt = ln["text"].strip()
        if not txt or len(txt) > 60:
            return None
        if re.fullmatch(r"[\d\s.\-—–]+", txt):
            return None  # bare page numbers
        if ln["size"] in size_level and ln["size"] > body_size + 0.5:
            return size_level[ln["size"]]
        if ln["bold"] and re.match(r"^(?:\d+(?:\.\d+)*\s+\S|[一二三四五六七八九十]+[、.])", txt):
            return 2
        return None

    use_size = len(heading_sizes) >= 2
    lines_out: list[str] = []
    stats = {"headings": 0, "tables": 0, "body_size": body_size}
    buf: list[str] = []

    def flush():
        nonlocal buf
        txt = ""
        for part in buf:
            part = part.strip()
            if not part:
                continue
            if not txt:
                txt = part
            elif re.search(r"[A-Za-z0-9)\]}]\s*$", txt) and re.match(r"[A-Za-z0-9(\[]", part):
                txt += " " + part
            else:
                txt += part
        buf = []
        txt = norm(txt)
        if txt:
            lines_out.append(txt)

    for pno, lines in enumerate(page_lines):
        if pno > 0:
            flush()
        for ln in lines:
            txt = norm(ln["text"])
            if not txt:
                continue
            # drop running headers/footers that repeat the page number
            if re.fullmatch(r"WS/T\s*\d+[—-]\d+", txt) and ln["size"] <= body_size + 0.2:
                continue
            lvl = is_heading(ln) if use_size else None
            if lvl is None and (HEADING_RE_CN.match(txt) or ANNEX_RE.match(txt)) and len(txt) < 60:
                lvl = 2
            if ANNEX_RE.match(txt) and len(txt) < 40:
                lvl = 2
            if lvl:
                flush()
                lines_out.append("#" * lvl + " " + txt)
                stats["headings"] += 1
                continue
            buf.append(txt)

    flush()
    # de-duplicate identical adjacent blocks (running heads)
    dedup = []
    for b in lines_out:
        if not dedup or dedup[-1] != b:
            dedup.append(b)
    lines_out = dedup

    header = [f"# {doc['title']}", ""]
    body = "\n\n".join(lines_out)
    return norm("\n".join(header) + "\n" + body), stats


# --------------------------------------------------------------------------- #
def process(doc: dict, entry: dict) -> dict:
    did = doc["document_id"]
    out_path = S.PROCESSED_DIR / f"{did}.md"
    rec = {
        "document_id": did,
        "title": doc["title"],
        "source_file": entry.get("local_file", ""),
        "extra_files": [f["local_file"] for f in entry.get("secondary_files", [])],
        "out_file": S.relpath(out_path),
        "chars": 0,
        "headings": 0,
        "tables": 0,
        "status": "failed",
        "error": "",
        "input_kind": entry.get("ext", ""),
    }

    pdf_rel = None
    if entry.get("annex_pdf"):
        pdf_rel = entry["annex_pdf"]
    elif entry.get("ext") == "pdf":
        pdf_rel = entry.get("local_file")
    elif entry.get("secondary_files"):
        pdf_rel = entry["secondary_files"][0]["local_file"]

    html_rel = entry.get("local_file") if entry.get("ext") == "html" else None

    text = ""
    stats = {}
    used = ""
    try:
        if pdf_rel:
            p = S.PROJECT_ROOT / pdf_rel
            if not p.exists():
                raise FileNotFoundError(pdf_rel)
            chars = sum(len(pg.get_text("text") or "") for pg in _open_pdf(p))
            if chars < 400 and html_rel:
                text, stats = _from_html(html_rel, doc)
                used = html_rel
            else:
                text, stats = pdf_to_md(p, doc)
                used = pdf_rel
                if html_rel and entry.get("content_kind") == "html" and entry.get("bytes", 0) > 4000:
                    page_text, page_stats = _from_html(html_rel, doc)
                    # notice page metadata (发文机关/日期/附件说明) precedes the annex body
                    extra = "\n\n".join(
                        b for b in page_text.split("\n\n")
                        if b.strip() and not b.startswith("# "))
                    if extra:
                        text = f"# {doc['title']}\n\n{extra}\n\n{text.split(chr(10),1)[1].strip()}"
                        stats["headings"] = stats.get("headings", 0) + page_stats.get("headings", 0)
                        stats["tables"] = stats.get("tables", 0) + page_stats.get("tables", 0)
        elif html_rel:
            text, stats = _from_html(html_rel, doc)
            used = html_rel
        else:
            rec["status"] = "skipped"
            rec["error"] = "no downloaded file"
            return rec
    except Exception as exc:  # noqa: BLE001
        rec["error"] = f"{type(exc).__name__}: {exc}"
        return rec

    out_path.write_text(text, encoding="utf-8")
    rec.update({
        "chars": len(text),
        "headings": stats.get("headings", 0),
        "tables": stats.get("tables", 0),
        "status": "ok",
        "input_kind": "pdf" if used.endswith(".pdf") else "html",
        "used_file": used,
        "error": "",
    })
    if used.endswith(".pdf"):
        rec["annex_pdf"] = used
        rec["annex_pdf_chars"] = stats.get("annex_pdf_chars", rec["chars"])
    return rec


def _open_pdf(p: Path):
    import pymupdf
    return pymupdf.open(p)


def _from_html(rel: str, doc: dict):
    p = S.PROJECT_ROOT / rel
    raw = p.read_text(encoding="utf-8", errors="replace")
    return html_to_md(raw, doc)


def main(argv: list[str]) -> int:
    ids = [a for a in argv[1:] if not a.startswith("-")]
    S.ensure_dirs()
    report = S.load_json(S.DOWNLOAD_REPORT) or {"documents": []}
    by_id = {d["document_id"]: d for d in report.get("documents", [])}
    docs = S.DOCUMENTS if not ids else [d for d in S.DOCUMENTS if d["document_id"] in ids]

    out = []
    for doc in docs:
        did = doc["document_id"]
        entry = by_id.get(did)
        if entry is None or entry.get("status") == "failed" or not entry.get("local_file"):
            out.append({
                "document_id": did, "title": doc["title"], "source_file": "",
                "out_file": "", "chars": 0, "headings": 0, "tables": 0,
                "status": "no_source",
                "error": (entry or {}).get("error", "not downloaded"),
            })
            log(f"[{did}] no_source")
            continue
        try:
            rec = process(doc, entry)
        except Exception as exc:  # noqa: BLE001
            rec = {"document_id": did, "title": doc["title"], "status": "failed",
                   "error": f"{type(exc).__name__}: {exc}", "chars": 0,
                   "headings": 0, "tables": 0, "out_file": "", "source_file": ""}
        out.append(rec)
        log(f"[{did}] {rec['status']:<9} chars={rec['chars']:>7} headings={rec['headings']:>3} "
            f"tables={rec['tables']:>3} {rec.get('error','')}")

    S.dump_json(S.PREPROCESS_REPORT, {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "documents": out,
        "summary": {
            "ok": sum(1 for r in out if r["status"] == "ok"),
            "no_source": sum(1 for r in out if r["status"] == "no_source"),
            "failed": sum(1 for r in out if r["status"] == "failed"),
            "total_chars": sum(r["chars"] for r in out),
        },
    })
    log("")
    log(f"processed report -> {S.relpath(S.PREPROCESS_REPORT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
