"""对「官方源本身没有可用文字层」的文档做 OCR，产出**待人工校对的草稿**。

⚠️ 重要：本脚本**只写 `knowledge/ocr/`**，绝不修改 manifest / processed / chunks。
   按契约要求，OCR 结果**必须人工校对**（尤其数字）后才能进生产检索 ——
   慢病数据里 `140` 被认成 `14O` 这类错误是不能接受的。

适用对象（官方源本身就是扫描件或文字层损坏）：
    PRIM003  39 页  ToUnicode 全坏（中文→U+00xx、数字→全角、字母→U+72xx）
    CORE002  10 页  纯扫描件（0 字符）
    LIFE001  14 页  扫描件（388 字符）
    LIFE001A 16 页  扫描件（391 字符）
    LIFE001B 14 页  扫描件（405 字符）
    LIFE001C 14 页  扫描件（418 字符）

用法::

    python scripts/ocr_documents.py --dry-run
    python scripts/ocr_documents.py
    python scripts/ocr_documents.py --only CORE002 LIFE008
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

RAW_DIR = PROJECT_ROOT / "knowledge" / "raw"
OUT_DIR = PROJECT_ROOT / "knowledge" / "ocr"
REPORT = OUT_DIR / "_ocr_report.json"

#: 需要 OCR 的文档 → (PDF 相对路径, 页数, 官方来源页)
TARGETS: dict[str, dict[str, object]] = {
    "PRIM003": {
        "pdf": "knowledge/raw/07_primarycare/PRIM003.pdf",
        "pages": 39,
        "why": "官方 PDF 的 ToUnicode CMap 损坏，文字层全是乱码",
        "url": "https://www.nhc.gov.cn/wjw/c100309/201511/6725aa6b7b6846058e3abf6ab3ee32d4.shtml",
    },
    "CORE002": {
        "pdf": "knowledge/raw/01_core/CORE002.pdf",
        "pages": 10,
        "why": "官方附件为纯扫描件（PyMuPDF 抽取 0 字符）",
        "url": "https://www.nhc.gov.cn/jws/c100073/202511/d3b6755fe7004cdeac938bf77b6a4a80.shtml",
    },
    "LIFE001": {
        "pdf": "knowledge/raw/06_lifestyle/LIFE001.pdf",
        "pages": 14,
        "why": "官方附件为扫描件（文本层仅 388 字符）",
        "url": "https://www.nhc.gov.cn/ylyjs/gzdt/202407/256b4eb8398440a8811344c7be50a333.shtml",
    },
    "LIFE001A": {
        "pdf": "knowledge/raw/06_lifestyle/LIFE001A.pdf",
        "pages": 16,
        "why": "官方附件为扫描件（文本层仅 391 字符）",
        "url": "https://www.nhc.gov.cn/ylyjs/gzdt/202407/256b4eb8398440a8811344c7be50a333.shtml",
    },
    "LIFE001B": {
        "pdf": "knowledge/raw/06_lifestyle/LIFE001B.pdf",
        "pages": 14,
        "why": "官方附件为扫描件（文本层仅 405 字符）",
        "url": "https://www.nhc.gov.cn/ylyjs/gzdt/202407/256b4eb8398440a8811344c7be50a333.shtml",
    },
    "LIFE001C": {
        "pdf": "knowledge/raw/06_lifestyle/LIFE001C.pdf",
        "pages": 14,
        "why": "官方附件为扫描件（文本层仅 418 字符）",
        "url": "https://www.nhc.gov.cn/ylyjs/gzdt/202407/256b4eb8398440a8811344c7be50a333.shtml",
    },
    # 注意：LIFE008 曾经被误判为扫描件，实际是**原生文本型单页 PDF**
    # （实测 0 张图片、0 个矢量对象），内容本身就是「标题 + 八条核心知识」，
    # 文本层 106 字符即全文，**不需要 OCR**，因此不在此清单中。
}

#: OCR 常见误识修正（**只做确定性的、无损的**修正，不做任何语义改写）
DASH_BETWEEN_DIGITS = re.compile(r"(?<=\d)\s*[一－–—]\s*(?=\d)")
SPACE_BEFORE_UNIT = re.compile(r"(WS|GB|T|/)\s*(?=\d)")


def fix_ocr_artifacts(text: str) -> tuple[str, int]:
    """修正 OCR 已知的确定性误识。返回 (修正后文本, 修正次数)。"""
    fixed, n1 = DASH_BETWEEN_DIGITS.subn("—", text)
    return fixed, n1


def ocr_pdf(pdf_path: Path, *, dpi: int = 200) -> tuple[list[str], list[int]]:
    """逐页 OCR，返回 (每页文本, 每页字符数)。"""
    import pymupdf
    from rapidocr_onnxruntime import RapidOCR

    engine = RapidOCR()
    pages: list[str] = []
    counts: list[int] = []
    with pymupdf.open(pdf_path) as doc:
        for index in range(doc.page_count):
            pix = doc[index].get_pixmap(dpi=dpi)
            png = pix.tobytes("png")
            result, _elapsed = engine(png)
            lines = [item[1] for item in (result or [])]
            text = "\n".join(lines).strip()
            fixed, _ = fix_ocr_artifacts(text)
            pages.append(fixed)
            counts.append(len(fixed))
    return pages, counts


def main() -> int:
    parser = argparse.ArgumentParser(description="对无文本层的官方文档做 OCR（产出待校对草稿）")
    parser.add_argument("--only", nargs="*", default=None, help="只处理指定 document_id")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="已存在也重跑")
    parser.add_argument("--dpi", type=int, default=200)
    args = parser.parse_args()

    ids = args.only or list(TARGETS)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "script": "scripts/ocr_documents.py",
        "engine": "rapidocr-onnxruntime",
        "dpi": args.dpi,
        "warning": "OCR 草稿，必须人工校对（尤其数字）后才可进入生产检索",
        "documents": [],
    }

    for doc_id in ids:
        spec = TARGETS.get(doc_id)
        if spec is None:
            print(f"[{doc_id}] 不在 OCR 目标清单里，跳过")
            continue
        pdf = PROJECT_ROOT / str(spec["pdf"])
        out_txt = OUT_DIR / f"{doc_id}.txt"
        entry = {
            "document_id": doc_id,
            "pdf": spec["pdf"],
            "expected_pages": spec["pages"],
            "why": spec["why"],
            "source_url": spec["url"],
            "out_file": out_txt.relative_to(PROJECT_ROOT).as_posix(),
        }
        if not pdf.exists():
            entry.update(status="missing_pdf")
            print(f"[{doc_id}] PDF 不存在：{pdf}")
            report["documents"].append(entry)
            continue
        if out_txt.exists() and not args.force and out_txt.stat().st_size > 2000:
            entry.update(status="skipped", chars=out_txt.stat().st_size)
            print(f"[{doc_id}] 已存在，跳过（--force 可重跑）")
            report["documents"].append(entry)
            continue

        if args.dry_run:
            entry.update(status="dry_run")
            print(f"[{doc_id}] 将 OCR {pdf.name}（约 {spec['pages']} 页）")
            report["documents"].append(entry)
            continue

        started = time.perf_counter()
        pages, counts = ocr_pdf(pdf, dpi=args.dpi)
        body = "\n\n".join(f"<!-- page {i + 1} -->\n{text}" for i, text in enumerate(pages) if text.strip())
        header = (
            f"> ⚠️ **OCR 草稿，未经人工校对，不得直接进入生产检索。**\n"
            f"> document_id: `{doc_id}`\n"
            f"> 来源: {spec['url']}\n"
            f"> 原件: `{spec['pdf']}`（{spec['why']}）\n"
            f"> 引擎: rapidocr-onnxruntime @ {args.dpi} DPI\n\n"
        )
        out_txt.write_text(header + body, encoding="utf-8")
        total = sum(counts)
        entry.update(
            status="ocr_done",
            pages_ocred=len(counts),
            chars=total,
            chars_per_page=round(total / max(1, len(counts)), 1),
            empty_pages=sum(1 for c in counts if c < 10),
            elapsed_s=round(time.perf_counter() - started, 1),
        )
        print(
            f"[{doc_id}] OCR 完成：{len(counts)} 页 / {total} 字符 "
            f"（空白页 {entry['empty_pages']}）{entry['elapsed_s']}s"
        )
        report["documents"].append(entry)

    if not args.dry_run:
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n报告 -> {REPORT.relative_to(PROJECT_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
