#!/usr/bin/env python
"""Extract the official publish date from every downloaded raw page.

Reads knowledge/raw/_download_report.json, looks for the 发布时间 / Published /
Date markers in the raw HTML of each document and writes
knowledge/raw/_dates.json. Never invents a date: when nothing is found the value
is an empty string.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _kb_shared as S  # noqa: E402

PATTERNS = [
    r"发布时间[：:\s]*</?[^>]*>?\s*(\d{4}-\d{2}-\d{2})",
    r"发布时间[\s\S]{0,80}?(\d{4}-\d{2}-\d{2})",
    r"发布日期[\s\S]{0,80}?(\d{4}-\d{2}-\d{2})",
    r'name="?PubDate"?[^>]*content="?(\d{4}-\d{2}-\d{2})',
    r'property="article:published_time"[^>]*content="([^"]+)"',
    r"(\d{4})年(\d{1,2})月(\d{1,2})日发布",
    r"'date[^']*'\s*:\s*'(\d{4}-\d{2}-\d{2})",
    r'"(?:datePublished|datePosted|publishDate)"\s*:\s*"(\d{4}-\d{2}-\d{2})',
    r"Published\s+(\d{1,2}\s+\w+\s+\d{4})",
]

#: 实施 / 施行日期（std pages 用"实施时间"，部分政策用"自 X 年 X 月 X 日起施行"）
EFFECTIVE_PATTERNS = [
    r"实施时间[：:\s]*</?[^>]*>?\s*(\d{4}-\d{2}-\d{2})",
    r"实施时间[\s\S]{0,80}?(\d{4}-\d{2}-\d{2})",
    r"实施日期[\s\S]{0,80}?(\d{4}-\d{2}-\d{2})",
    r"施行日期[\s\S]{0,80}?(\d{4}-\d{2}-\d{2})",
    r"生效日期[\s\S]{0,80}?(\d{4}-\d{2}-\d{2})",
    r"自(\d{4})年(\d{1,2})月(\d{1,2})日起施行",
    r"Effective\s+(\d{1,2}\s+\w+\s+\d{4})",
    # 中文写法：卫生健康标准页常见「实施时间 2026年3月1日」
    r"实施时间[\s\S]{0,300}?(\d{4})年(\d{1,2})月(\d{1,2})日",
    r"实施日期[\s\S]{0,300}?(\d{4})年(\d{1,2})月(\d{1,2})日",
    r"施行日期[\s\S]{0,300}?(\d{4})年(\d{1,2})月(\d{1,2})日",
    r"自(\d{4})年(\d{1,2})月(\d{1,2})日起(?:施行|实施)",
]


def extract(path: Path, patterns: list[str] | None = None) -> tuple[str, str]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    for pat in (patterns or PATTERNS):
        for m in re.finditer(pat, raw):
            val = m.group(1)
            if len(m.groups()) == 3:
                val = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
            val = val.strip()
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", val):
                return val, pat
            if re.fullmatch(r"\d{1,2}\s+\w+\s+\d{4}", val):
                return val, pat
    return "", ""


def main() -> int:
    report = S.load_json(S.DOWNLOAD_REPORT) or {}
    out = {}
    for e in report.get("documents", []):
        rel = e.get("local_file") or ""
        if not rel.endswith(".html"):
            out[e["document_id"]] = {
                "publish_date": "",
                "pattern": "",
                "effective_date": "",
                "effective_pattern": "",
                "source": rel,
            }
            continue
        p = S.PROJECT_ROOT / rel
        if not p.exists():
            continue
        date, pat = extract(p)
        eff, eff_pat = extract(p, EFFECTIVE_PATTERNS)
        out[e["document_id"]] = {
            "publish_date": date,
            "pattern": pat[:40],
            "effective_date": eff,
            "effective_pattern": eff_pat[:40],
            "source": rel,
        }
        print(f"{e['document_id']:<8} pub={date or '(none)':<12} eff={eff or '(none)':<12} {rel}")
    S.dump_json(S.RAW_DIR / "_dates.json", out)
    print("->", S.relpath(S.RAW_DIR / "_dates.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
