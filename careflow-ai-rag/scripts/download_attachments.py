"""CareFlow 康脉智护 —— 官方附件补充下载。

**为什么需要这个脚本**

部分官方页面（尤其是「统一官方入口」型页面）本身只是**通知页**，
正文很短、真正的内容在页面上的**附件 PDF** 里。例如：

* `https://www.nhc.gov.cn/sps/c100088/202301/f01895a06c5349ef999f25da833c166d.shtml`
  是《关于印发成人高脂血症食养指南（2023年版）等 4 项食养指南的通知》，
  正文只有通知本身；四份指南各自在 `files/xxxx.pdf` 附件中。
* `https://www.nhc.gov.cn/sps/c100088/202402/9ba512ba8e314a47a181db11d2fa188d.shtml`
  同理（2024 年版 4 项食养指南）。

如果只抓页面本身，`LIFE002/003/004` 会拿到**同一份通知页**（内容重复、
且 Citation 指向的不是指南本体）。本脚本按**附件标题精确匹配**下载真正的指南 PDF。

同时处理 WHO 出版页 → `iris.who.int` 全文 PDF 的跳转。

用法::

    python scripts/download_attachments.py --dry-run
    python scripts/download_attachments.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

RAW_DIR = PROJECT_ROOT / "knowledge" / "raw"
REPORT = RAW_DIR / "_attachment_report.json"

from playwright_fetch import DEFAULT_ARGS, DEFAULT_UA, fetch_bytes  # noqa: E402

#: document_id -> (入口页 URL, 附件标题关键词)
NHC_ATTACHMENTS: dict[str, tuple[str, str]] = {
    "LIFE002": (
        "https://www.nhc.gov.cn/sps/c100088/202301/f01895a06c5349ef999f25da833c166d.shtml",
        "成人高血压食养指南",
    ),
    "LIFE003": (
        "https://www.nhc.gov.cn/sps/c100088/202301/f01895a06c5349ef999f25da833c166d.shtml",
        "成人糖尿病食养指南",
    ),
    "LIFE004": (
        "https://www.nhc.gov.cn/sps/c100088/202301/f01895a06c5349ef999f25da833c166d.shtml",
        "成人高脂血症食养指南",
    ),
    "LIFE005": (
        "https://www.nhc.gov.cn/sps/c100088/202402/9ba512ba8e314a47a181db11d2fa188d.shtml",
        "成人高尿酸血症与痛风食养指南",
    ),
    "LIFE006": (
        "https://www.nhc.gov.cn/sps/c100088/202402/9ba512ba8e314a47a181db11d2fa188d.shtml",
        "成人肥胖食养指南",
    ),
    "LIFE007": (
        "https://www.nhc.gov.cn/sps/c100088/202402/9ba512ba8e314a47a181db11d2fa188d.shtml",
        "成人慢性肾脏病食养指南",
    ),
}

#: WHO 出版页 → 已知全文 PDF（landing 页解析不到时的兜底）
WHO_EXPLICIT_PDF: dict[str, str] = {
    "WHO001": "https://iris.who.int/bitstream/handle/10665/334186/9789240009226-eng.pdf",
}

WHO_LANDING: dict[str, Path] = {
    "WHO001": RAW_DIR / "08_who" / "WHO001.html",
    "WHO002": RAW_DIR / "08_who" / "WHO002.html",
    "WHO003": RAW_DIR / "08_who" / "WHO003.html",
}

WHO_KNOWN_PDF = {
    "WHO002": "https://iris.who.int/bitstream/handle/10665/341077/9789240021367-eng.pdf",
    "WHO003": "https://iris.who.int/bitstream/handle/10665/312273/WHO-NMH-NVI-18.1-eng.pdf",
}


def _existing_html(document_id: str) -> Path | None:
    hits = [p for p in RAW_DIR.rglob(f"{document_id}.html")]
    return hits[0] if hits else None


def _find_attachment(href_titles: list[tuple[str, str]], keyword: str) -> str | None:
    """按标题关键词匹配附件（排除「问答」）。"""
    for href, title in href_titles:
        if keyword in title and "问答" not in title:
            return href
    return None


def extract_attachment_links(html: str, base_url: str) -> list[tuple[str, str]]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    out: list[tuple[str, str]] = []
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if not re.search(r"\.(pdf|docx?|wps|xlsx?)$", href, re.IGNORECASE):
            continue
        out.append((urljoin(base_url, href), anchor.get_text(strip=True)))
    return out


async def run(dry_run: bool = False) -> dict:
    from playwright.async_api import async_playwright

    report: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "script": "scripts/download_attachments.py",
        "documents": [],
    }

    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=True, args=DEFAULT_ARGS)
    context = await browser.new_context(
        locale="zh-CN", user_agent=DEFAULT_UA, accept_downloads=True
    )

    try:
        # ---------------- NHC 食养指南附件 ----------------
        cache: dict[str, list[tuple[str, str]]] = {}
        for document_id, (page_url, keyword) in NHC_ATTACHMENTS.items():
            entry: dict = {"document_id": document_id, "page_url": page_url, "keyword": keyword}
            html_path = _existing_html(document_id)
            if html_path is None:
                entry.update(status="failed", error="入口页 HTML 不存在，请先运行 download_documents.py")
                report["documents"].append(entry)
                continue
            if page_url not in cache:
                cache[page_url] = extract_attachment_links(
                    html_path.read_text(encoding="utf-8", errors="ignore"), page_url
                )
            pdf_url = _find_attachment(cache[page_url], keyword)
            if not pdf_url:
                entry.update(status="failed", error=f"未在入口页找到匹配「{keyword}」的附件")
                report["documents"].append(entry)
                continue
            entry["pdf_url"] = pdf_url
            target = RAW_DIR / "06_lifestyle" / f"{document_id}.pdf"
            entry["local_file"] = target.relative_to(PROJECT_ROOT).as_posix()
            if dry_run:
                entry["status"] = "dry_run"
                report["documents"].append(entry)
                continue
            if target.exists() and target.stat().st_size > 10_000:
                entry.update(status="skipped", bytes=target.stat().st_size)
                report["documents"].append(entry)
                continue
            content, status, error = await fetch_bytes(pdf_url, context=context, referer=page_url)
            if content and content[:4] == b"%PDF" and len(content) > 10_000:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
                entry.update(status="downloaded", http_status=status, bytes=len(content))
            else:
                entry.update(
                    status="failed",
                    http_status=status,
                    error=error or f"非 PDF 或过小（{len(content)} bytes, magic={content[:8]!r}）",
                )
            report["documents"].append(entry)

        # ---------------- WHO 全文 PDF ----------------
        for document_id, landing in WHO_LANDING.items():
            entry = {"document_id": document_id, "landing": landing.name}
            pdf_url = ""
            if landing.exists():
                links = extract_attachment_links(
                    landing.read_text(encoding="utf-8", errors="ignore"),
                    "https://www.who.int/",
                )
                for href, _title in links:
                    if "iris.who.int" in urlparse(href).netloc and href.lower().endswith(".pdf"):
                        pdf_url = href
                        break
                if not pdf_url:
                    matches = re.findall(
                        r"https://iris\.who\.int/bitstream/handle/[^\s\"'<>]+?\.pdf", 
                        landing.read_text(encoding="utf-8", errors="ignore"),
                    )
                    pdf_url = matches[0] if matches else ""
            if not pdf_url:
                pdf_url = WHO_EXPLICIT_PDF.get(document_id) or WHO_KNOWN_PDF.get(document_id, "")
            entry["pdf_url"] = pdf_url
            if not pdf_url:
                entry.update(status="failed", error="未解析到 WHO 全文 PDF 链接")
                report["documents"].append(entry)
                continue
            target = RAW_DIR / "08_who" / f"{document_id}.pdf"
            entry["local_file"] = target.relative_to(PROJECT_ROOT).as_posix()
            if dry_run:
                entry["status"] = "dry_run"
                report["documents"].append(entry)
                continue
            if target.exists() and target.stat().st_size > 50_000:
                entry.update(status="skipped", bytes=target.stat().st_size)
                report["documents"].append(entry)
                continue
            content, status, error = await fetch_bytes(pdf_url, context=context, referer="https://www.who.int/")
            if content and content[:4] == b"%PDF" and len(content) > 50_000:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
                entry.update(status="downloaded", http_status=status, bytes=len(content))
            else:
                entry.update(
                    status="failed",
                    http_status=status,
                    error=error or f"非 PDF 或过小（{len(content)} bytes）",
                )
            report["documents"].append(entry)
    finally:
        await context.close()
        await browser.close()
        await playwright.stop()

    counts: dict[str, int] = {}
    for doc in report["documents"]:
        counts[doc["status"]] = counts.get(doc["status"], 0) + 1
    report["summary"] = counts
    if not dry_run:
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="下载官方附件（食养指南 PDF / WHO 全文 PDF）")
    parser.add_argument("--dry-run", action="store_true", help="只解析链接，不下载")
    args = parser.parse_args()

    report = asyncio.run(run(dry_run=args.dry_run))
    for doc in report["documents"]:
        print(
            f'{doc["document_id"]:9} {doc["status"]:11} '
            f'{str(doc.get("bytes", "")):>9} {doc.get("pdf_url", "")[:90]}'
            + (f'  ERR={doc["error"][:70]}' if doc.get("error") else "")
        )
    print("summary:", report["summary"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
