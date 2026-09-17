#!/usr/bin/env python
"""Download the 30 official source documents for the CareFlow knowledge base.

Design notes
------------
* Only official hosts are contacted (nhc.gov.cn, who.int / iris.who.int,
  hbp-office.nccd.org.cn, sinocardiomed.com, rs.yiigle.com, drugs.dxy.cn).
  Third-party mirrors, search caches and reposts are never used.
* www.nhc.gov.cn sits behind a WZWS JS challenge that answers plain
  httpx/requests with HTTP 412. The verified workaround is Playwright chromium:
  navigate with wait_until="commit", then poll page.inner_text("body") every 2 s
  until the body is long enough (the JS challenge passes in a few seconds).
* Idempotent: an already downloaded raw file is reported as "skipped" and keeps
  its recorded sha256. Re-running never re-downloads and never errors out.
* Retries: at most 3 attempts per URL, 3 s apart. On final failure the document
  is recorded as failed with the real error text; the manifest builder then marks
  it status=draft / local_file=PENDING. Paywalls are never bypassed.

Usage:
    python scripts/download_documents.py            # all documents
    python scripts/download_documents.py HTN001 DM002
    python scripts/download_documents.py --force    # re-download everything
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _kb_shared as S  # noqa: E402

BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")
HTTP_HEADERS = {
    "User-Agent": BROWSER_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}
MAX_ATTEMPTS = 3

# Documents whose only official pointer is behind a login/authorisation wall.
# We never bypass such a wall, so these are recorded as pending manual download
# even when a portal shell happens to render.
FORCE_PENDING = {
    "DM003": "third-party portal drugs.dxy.cn renders only a preview; full text "
             "requires login/membership (paywall not bypassed)",
    "PRIM003": "official annex PDF (WS/T 484-2015) has a broken/absent text layer "
               "(subset CID fonts without ToUnicode); no faithful text can be "
               "extracted without OCR, so the raw html/pdf are kept for manual OCR",
}

SEPARATORS = (" ", "\t", "\r", "\n", ".", ",", ";", ":", "(", ")", "[", "]",
              "%", "/", "-", "+", chr(39), chr(34))


def is_readable_text(text: str, sample: int = 4000) -> bool:
    """True when a PDF text layer yields real text, not CID garbage.

    Standards PDFs from the national standards system often use subset CID fonts
    without a ToUnicode map; extraction then returns private-use codepoints.
    Such text must never enter the knowledge base.
    """
    s = text[:sample]
    if not s.strip():
        return False
    good = 0
    for ch in s:
        o = ord(ch)
        if 0x4E00 <= o <= 0x9FFF or 0x3000 <= o <= 0x303F or 0xFF00 <= o <= 0xFFEF:
            good += 1
        elif ch.isascii() and (ch.isalnum() or ch in SEPARATORS):
            good += 1
    return good / max(1, len(s)) > 0.75


def _forced_pending(doc: dict, keep_evidence: bool = True) -> dict | None:
    reason = FORCE_PENDING.get(doc["document_id"])
    if not reason:
        return None
    kept = []
    for ext in ("html", "pdf"):
        p = target_paths(doc, ext)
        if p.exists():
            if keep_evidence:
                kept.append(S.relpath(p))
            else:
                p.unlink()
    return {
        "document_id": doc["document_id"], "title": doc["title"],
        "url": doc["source_url"], "status": "failed", "http_status": 401,
        "bytes": 0, "sha256": "", "error": f"paywall_or_login_wall: {reason}",
        "attempt": 0, "local_file": "", "ext": "", "content_kind": "",
        "attachments": [], "secondary_files": [], "checks": [
            {"url": doc["source_url"], "error": reason}],
        "annex_pdf": None, "annex_pdf_chars": 0,
        "host": doc["source_url"].split("/")[2],
        "forced_pending": True,
        "evidence_files": kept,
    }
RETRY_SLEEP = 3.0
MIN_HTML_BODY = 300   # rendered-body floor for a real page
MIN_REAL_BODY = 250   # below this we still assume the challenge is pending
MIN_PDF_BYTES = 10_000
NHC_HOSTS = ("www.nhc.gov.cn", "nhc.gov.cn")
BROWSER_HOSTS = NHC_HOSTS + ("hbp-office.nccd.org.cn", "drugs.dxy.cn", "rs.yiigle.com")
# A 412 response with a substantially rendered body is a passed WZWS challenge,
# not a failure: the challenge answers the first navigation with 412 and then
# rewrites the DOM. Only treat 412 as an error when the body stays vestigial.
WAF_SOFT_STATUSES = {200, 206, 301, 302, 412}
PAGE_MARKERS = ("ICP\u5907", "\u4e2d\u534e\u4eba\u6c11\u5171\u548c\u56fd", "\u56fd\u5bb6\u536b\u751f\u5065\u5eb7")


def log(msg: str) -> None:
    print(msg, flush=True)


def is_pdf_bytes(head: bytes) -> bool:
    return head[:5] == b"%PDF-"


def target_paths(doc: dict, ext: str) -> Path:
    return S.RAW_DIR / doc["domain_dir"] / f"{doc['document_id']}.{ext}"


# --------------------------------------------------------------------------- #
# HTTP (non-WAF hosts)
# --------------------------------------------------------------------------- #
def http_fetch(url: str, timeout: float = 45.0):
    """Return (status, content, content_type, error)."""
    import httpx
    try:
        with httpx.Client(headers=HTTP_HEADERS, follow_redirects=True,
                          timeout=timeout, verify=False) as client:
            r = client.get(url)
            return r.status_code, r.content, r.headers.get("content-type", ""), None
    except Exception as exc:  # noqa: BLE001
        return None, b"", "", f"{type(exc).__name__}: {exc}"


# --------------------------------------------------------------------------- #
# Playwright (WAF hosts + JS heavy pages)
# --------------------------------------------------------------------------- #
async def playwright_fetch(url: str):
    """Return (status, kind, payload, error).

    kind is "html" (payload=str) or "pdf" (payload=bytes).
    """
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        try:
            ctx = await browser.new_context(
                locale="zh-CN", user_agent=BROWSER_UA,
                viewport={"width": 1440, "height": 900},
                accept_downloads=True,
            )
            page = await ctx.new_page()
            resp = None
            goto_err = ""
            try:
                resp = await page.goto(url, timeout=60_000, wait_until="commit")
            except Exception as exc:  # noqa: BLE001
                goto_err = f"{type(exc).__name__}: {exc}"
                resp = None
            if goto_err and "Download is starting" not in goto_err:
                return None, "html", "", f"goto failed: {goto_err}"

            status = resp.status if resp else None
            ctype = ""
            if resp is not None:
                try:
                    ctype = (resp.headers or {}).get("content-type", "")
                except Exception:  # noqa: BLE001
                    ctype = ""

            # Direct PDF response -> fetch through the same WAF-cookied context.
            # nhc serves r.d. pdfs as attachments, so fetch by URL rather than
            # relying on the download event.
            if "pdf" in ctype.lower() or url.lower().endswith(".pdf"):
                try:
                    r = await ctx.request.get(url, timeout=90_000)
                    body = await r.body()
                    if r.status in (200, 206) and body[:5] == b"%PDF-":
                        return r.status, "pdf", body, None
                    return r.status, "pdf", body, (
                        f"pdf fetch not a pdf: status={r.status} bytes={len(body)}")
                except Exception as exc:  # noqa: BLE001
                    return status, "pdf", b"", f"pdf request failed: {type(exc).__name__}: {exc}"

            body = ""
            for i in range(15):
                try:
                    body = await page.inner_text("body")
                except Exception:  # noqa: BLE001
                    body = ""
                if len(body) > 800 and any(m in body for m in PAGE_MARKERS):
                    break            # challenge already passed
                if i == 14:
                    break
                await asyncio.sleep(2)
            html = await page.content()
            if len(body) < MIN_REAL_BODY:
                return status or 0, "html", html, (
                    f"waf_or_empty_body: body_len={len(body)} status={status} "
                    f"title={await _safe_title(page)}")
            if not any(m in body or m in html for m in PAGE_MARKERS):
                return status or 0, "html", html, (
                    f"unexpected_page: body_len={len(body)} status={status} "
                    f"title={await _safe_title(page)}")
            return status or 200, "html", html, None
        finally:
            await browser.close()


async def _safe_title(page) -> str:
    try:
        return await page.title()
    except Exception:  # noqa: BLE001
        return "?"


def fetch_url(url: str) -> dict:
    """Fetch one URL with retries. Returns a dict describing the outcome."""
    host = url.split("/")[2].lower() if "//" in url else ""
    use_browser = any(host == h or host.endswith("." + h) for h in BROWSER_HOSTS)
    last_err = ""
    http_status = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if use_browser:
            try:
                status, kind, payload, err = asyncio.run(playwright_fetch(url))
            except Exception as exc:  # noqa: BLE001
                status, kind, payload, err = None, "html", "", f"playwright: {type(exc).__name__}: {exc}"
        else:
            status, content, ctype, err = http_fetch(url)
            http_status = status
            if err is None and is_pdf_bytes(content):
                kind, payload = "pdf", content
            elif err is None:
                kind, payload = "html", content.decode("utf-8", errors="replace")
            else:
                kind, payload = "html", ""
            status = status or 0

        http_status = status
        if err is None:
            if kind == "pdf" and len(payload) < MIN_PDF_BYTES:
                err = f"suspiciously small pdf: {len(payload)} bytes"
            elif kind == "html" and len(payload) < 2000:
                err = f"html payload too small: {len(payload)} bytes"
        if err is None and status not in WAF_SOFT_STATUSES and status != 0:
            err = f"http {status}"
        if err is None:
            return {"ok": True, "kind": kind, "payload": payload,
                    "http_status": status, "attempt": attempt, "error": ""}

        last_err = err
        log(f"      attempt {attempt}/{MAX_ATTEMPTS} failed: {err}")
        if attempt < MAX_ATTEMPTS:
            time.sleep(RETRY_SLEEP)

    # Non-browser hosts may still be reachable through the browser fallback.
    if not use_browser:
        log("      http path failed -> trying playwright fallback")
        try:
            status, kind, payload, err = asyncio.run(playwright_fetch(url))
            if err is None and status in (200, 206, 0):
                return {"ok": True, "kind": kind, "payload": payload,
                        "http_status": status, "attempt": MAX_ATTEMPTS + 1, "error": ""}
            last_err = f"{last_err} | playwright fallback: {err or status}"
        except Exception as exc:  # noqa: BLE001
            last_err = f"{last_err} | playwright fallback: {type(exc).__name__}: {exc}"

    return {"ok": False, "kind": None, "payload": b"", "http_status": http_status,
            "attempt": MAX_ATTEMPTS, "error": last_err}


def write_payload(path: Path, kind: str, payload) -> int:
    tmp = path.with_suffix(path.suffix + ".part")
    if kind == "pdf":
        data = payload if isinstance(payload, bytes) else bytes(payload)
    else:
        text = payload if isinstance(payload, str) else payload.decode("utf-8", errors="replace")
        data = text.encode("utf-8")
    tmp.write_bytes(data)
    tmp.replace(path)
    return len(data)


# --------------------------------------------------------------------------- #
# Official attachment discovery (same official host only)
# --------------------------------------------------------------------------- #
def find_annex_pdfs(html_path: Path, source_url: str) -> list[dict]:
    from bs4 import BeautifulSoup
    from urllib.parse import quote, unquote, urljoin

    try:
        soup = BeautifulSoup(html_path.read_text(encoding="utf-8", errors="replace"), "lxml")
    except Exception:  # noqa: BLE001
        return []
    out = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        low = href.lower()
        if not (low.endswith(".pdf") or ".pdf?" in low or ".pdf#" in low):
            continue
        # nhc annex hrefs contain literal spaces and CJK -> percent-encode, then join
        full = urljoin(source_url, quote(href, safe="%/:=&?~#!$,;@" + chr(39) + "()*[]|"))
        if full in seen:
            continue
        seen.add(full)
        label = a.get_text(" ", strip=True) or unquote(full.rsplit("/", 1)[-1])
        out.append({"url": full, "label": label[:160]})
    return out


def _stem(text: str) -> str:
    """Drop punctuation/spaces so CJK bigrams can be compared."""
    return re.sub(r"[\s\u3000\-—_（）()《》〈〉【】\[\].,、；;:：!！?？\"\"'\u201c\u201d]+", "", text)


def _bigrams(text: str) -> set:
    st = _stem(text)
    return {st[i:i + 2] for i in range(len(st) - 1)}


def match_annex(doc: dict, cands: list) -> list:
    """Rank official annex candidates against the document title.

    nhc download pages list every annex of a notice, so the first pdf link is
    frequently the wrong annex. Score on filename stem + anchor label.
    """
    from urllib.parse import unquote as _uq

    tb = _bigrams(doc["title"])
    tstem = _stem(doc["title"])
    scored = []
    for c in cands:
        stem = _stem(_uq(c["url"].rsplit("/", 1)[-1]))
        label = _stem(c["label"])
        score = len(tb & _bigrams(stem)) + 2 * len(tb & _bigrams(label))
        if len(stem) > 3 and stem in tstem:
            score += 6
        scored.append((score, c))
    scored.sort(key=lambda x: -x[0])
    return [dict(c, match_score=sc) for sc, c in scored]


def pdf_text_chars(path: Path) -> int:
    try:
        import pymupdf
        with pymupdf.open(path) as doc:
            return sum(len(p.get_text("text") or "") for p in doc)
    except Exception:  # noqa: BLE001
        return 0


# --------------------------------------------------------------------------- #
# Main per-document routine
# --------------------------------------------------------------------------- #
def process_document(doc: dict, force: bool = False) -> dict:
    did = doc["document_id"]
    html_path = target_paths(doc, "html")
    pdf_path = target_paths(doc, "pdf")
    forced = _forced_pending(doc)
    if forced is not None:
        log(f"[{did}] forced pending: {forced['error']}")
        return forced
    entry = {
        "document_id": did,
        "title": doc["title"],
        "url": doc["source_url"],
        "status": "failed",
        "http_status": None,
        "bytes": 0,
        "sha256": "",
        "error": "",
        "attempt": 0,
        "local_file": "",
        "ext": "",
        "content_kind": "",
        "secondary_files": [],
        "attachments": [],
        "annex_pdf": None,
        "annex_pdf_chars": 0,
        "checks": [],
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "host": doc["source_url"].split("/")[2],
    }

    existing_html = html_path.exists() and html_path.stat().st_size > 0
    existing_pdf = pdf_path.exists() and pdf_path.stat().st_size > 0

    if (existing_html or existing_pdf) and not force:
        if existing_html:
            entry.update(status="skipped", local_file=S.relpath(html_path), ext="html",
                         content_kind="html",
                         bytes=html_path.stat().st_size,
                         sha256=S.sha256_file(html_path))
        if existing_pdf:
            if entry["local_file"]:
                entry["secondary_files"].append({
                    "local_file": S.relpath(pdf_path), "ext": "pdf",
                    "bytes": pdf_path.stat().st_size, "sha256": S.sha256_file(pdf_path),
                    "role": "attachment_pdf",
                })
            else:
                entry.update(local_file=S.relpath(pdf_path), ext="pdf",
                             content_kind="pdf", bytes=pdf_path.stat().st_size,
                             sha256=S.sha256_file(pdf_path))
        log(f"[{did}] skipped (already present: {entry['local_file']})")
        _maybe_annex(doc, entry, html_path if existing_html else None, force)
        return entry

    log(f"[{did}] GET {doc['source_url']}")
    res = fetch_url(doc["source_url"])
    entry["http_status"] = res["http_status"]
    entry["attempt"] = res["attempt"]

    if not res["ok"]:
        entry["error"] = res["error"]
        entry["status"] = "failed"
        log(f"[{did}] FAILED: {res['error']}")
        return entry

    kind = res["kind"]
    if kind == "pdf":
        entry["bytes"] = write_payload(pdf_path, "pdf", res["payload"])
        entry.update(status="downloaded", local_file=S.relpath(pdf_path), ext="pdf",
                     content_kind="pdf", sha256=S.sha256_file(pdf_path))
        log(f"[{did}] downloaded PDF {entry['bytes']} bytes")
    else:
        # A PDF served with an html content-type still starts with %PDF-.
        payload = res["payload"]
        if isinstance(payload, bytes) and is_pdf_bytes(payload):
            entry["bytes"] = write_payload(pdf_path, "pdf", payload)
            entry.update(status="downloaded", local_file=S.relpath(pdf_path), ext="pdf",
                         content_kind="pdf", sha256=S.sha256_file(pdf_path))
            log(f"[{did}] downloaded PDF {entry['bytes']} bytes")

    if not entry["local_file"] and kind == "html":
        entry["bytes"] = write_payload(html_path, "html", res["payload"])
        note = ""
        if res["http_status"] == 412:
            note = "navigation status 412 (WZWS challenge) but body fully rendered"
        entry.update(status="downloaded", local_file=S.relpath(html_path), ext="html",
                     content_kind="html", sha256=S.sha256_file(html_path),
                     waf_note=note)
        log(f"[{did}] downloaded HTML {entry['bytes']} bytes")

    _maybe_annex(doc, entry, html_path, force)
    return entry


def _maybe_annex(doc: dict, entry: dict, html_path, force: bool) -> None:
    """Record (and optionally download) official annex PDFs / WHO IRIS PDF."""
    did = doc["document_id"]
    urls: list[dict] = []
    if html_path is not None and html_path.exists():
        found = find_annex_pdfs(html_path, doc["source_url"])
        entry["attachments"] = [u["url"] for u in found]
        urls = match_annex(doc, found)
        entry["annex_candidates"] = [
            {"url": u["url"], "label": u["label"], "match_score": u["match_score"]}
            for u in urls]
    if entry.get("ext") != "pdf":
        extra = [{"url": u, "label": "registry extra official pdf", "match_score": 99}
                 for u in (S.EXTRA_URLS.get(did) or [])]
        urls = extra + urls

    if not urls:
        return
    pdf_path = target_paths(doc, "pdf")
    if pdf_path.exists() and pdf_path.stat().st_size > 0 and not force:
        chars = pdf_text_chars(pdf_path)
        entry["annex_pdf"] = S.relpath(pdf_path)
        entry["annex_pdf_chars"] = chars
        return

    for cand in urls[:5]:
        url = cand["url"]
        score = cand.get("match_score", 0)
        if score <= 0 and not cand["url"].lower().endswith(".pdf"):
            continue
        if score <= 0 and len([u for u in urls if u.get("match_score", 0) > 0]) > 0:
            # another annex matches the title far better; do not settle for this one
            continue
        log(f"[{did}]   annex try (score={score}): {url}")
        r = fetch_url(url)
        if not r["ok"]:
            entry["checks"].append({"url": url, "error": r["error"]})
            continue
        if r["kind"] == "html" and isinstance(r["payload"], str) and not r["payload"].startswith("%PDF"):
            entry["checks"].append({"url": url, "error": "not a pdf (html served)"})
            continue
        already_main = bool(entry["local_file"]) and (
            Path(S.PROJECT_ROOT / entry["local_file"]).resolve() == pdf_path.resolve())
        if already_main:
            n = pdf_path.stat().st_size if pdf_path.exists() else 0
        else:
            n = write_payload(pdf_path, "pdf", r["payload"])
        chars = pdf_text_chars(pdf_path)
        entry["annex_pdf"] = S.relpath(pdf_path)
        entry["annex_pdf_chars"] = chars
        min_chars = 1500 if entry["content_kind"] == "pdf" else 3000
        if chars < min_chars and entry["content_kind"] == "html" and entry["bytes"] > 4000:
            # Notice-only attachment (e.g. a 公告 with no standard text): drop it.
            pdf_path.unlink(missing_ok=True)
            entry["annex_pdf"] = None
            entry["checks"].append({"url": url, "error": f"annex pdf too short ({chars} chars)"})
            continue
        readable = True
        try:
            import pymupdf as _pm
            with _pm.open(pdf_path) as _pdf:
                _sample = "".join(
                    _pdf[i].get_text("text") for i in range(min(3, _pdf.page_count)))
            readable = is_readable_text(_sample)
        except Exception:  # noqa: BLE001
            readable = True
        if not readable:
            pdf_path.unlink(missing_ok=True)
            entry["annex_pdf"] = None
            entry["checks"].append({
                "url": url,
                "error": f"pdf text layer unreadable (cid garbage): {chars} chars rejected"})
            log(f"[{did}]   annex rejected: unreadable text layer")
            continue
        entry["annex_chars"] = chars
        entry["annex_label"] = cand.get("label", "")
        log(f"[{did}]   annex downloaded {n} bytes, {chars} text chars")
        break


def main(argv: list[str]) -> int:
    force = "--force" in argv
    ids = [a for a in argv[1:] if not a.startswith("-")]
    docs = S.DOCUMENTS if not ids else [d for d in S.DOCUMENTS if d["document_id"] in ids]
    if not docs:
        log("no matching documents")
        return 2

    S.ensure_dirs()
    report = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "script": "scripts/download_documents.py",
              "documents_total": len(S.DOCUMENTS),
              "documents": []}
    prior = S.load_json(S.DOWNLOAD_REPORT) or {}
    prior_by_id = {d["document_id"]: d for d in prior.get("documents", [])}

    for doc in docs:
        try:
            entry = process_document(doc, force=force)
        except Exception as exc:  # noqa: BLE001
            entry = prior_by_id.get(doc["document_id"], {
                "document_id": doc["document_id"], "title": doc["title"],
                "url": doc["source_url"], "http_status": None, "bytes": 0,
                "sha256": "", "local_file": "", "ext": "", "attachments": [],
                "secondary_files": [], "checks": [], "attempt": 0,
            })
            entry["status"] = "failed"
            entry["error"] = f"{type(exc).__name__}: {exc}"
            log(f"[{doc['document_id']}] EXCEPTION: {entry['error']}")
        prior_by_id[doc["document_id"]] = entry

    for doc in S.DOCUMENTS:
        e = prior_by_id.get(doc["document_id"])
        if e is not None:
            report["documents"].append(e)

    counts = {}
    for e in report["documents"]:
        counts[e["status"]] = counts.get(e["status"], 0) + 1
    report["summary"] = counts
    S.dump_json(S.DOWNLOAD_REPORT, report)

    log("")
    log("=" * 72)
    log(f"download report -> {S.relpath(S.DOWNLOAD_REPORT)}")
    log(f"summary: {json.dumps(counts, ensure_ascii=False)}")
    for e in report["documents"]:
        flag = {"downloaded": "OK  ", "skipped": "SKIP", "failed": "FAIL"}.get(e["status"], "?   ")
        log(f"  {flag} {e['document_id']:<8} {e.get('local_file',''):<48} "
            f"{e.get('bytes',0):>9} B  {e.get('error','')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
