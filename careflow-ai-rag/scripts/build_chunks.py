#!/usr/bin/env python
"""Structure-aware semantic chunking of the processed corpus.

Input : knowledge/processed/<document_id>.md + knowledge/manifest/knowledge_manifest.csv
Output: knowledge/chunks/chunks.jsonl
        knowledge/chunks/index_meta.json

Rules
-----
* Chunks follow the heading order of the document: level 1 -> level 2 -> level 3
  -> paragraphs. A heading is never left dangling at the end of a chunk and a
  heading never starts a chunk without at least one following block.
* Target size 500-900 characters, overlap 80-150 characters. Overlap is taken by
  repeating whole trailing blocks (paragraph lines) of the previous chunk, so a
  sentence or a table row is never cut in half.
* Tables are kept whole; an oversized table is split only at row boundaries with
  the header row repeated.
* `content` is always a verbatim, contiguous slice of the cleaned Markdown file
  (only paragraph separators are normalised). Nothing is rewritten or summarised.

Usage:
    python scripts/build_chunks.py
    python scripts/build_chunks.py --min 500 --max 900 --overlap 120
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _kb_shared as S  # noqa: E402

DEFAULT_MIN = 500
DEFAULT_MAX = 900
DEFAULT_OVERLAP = 120
SENT_END = "。！？；!?;"


def log(msg: str) -> None:
    print(msg, flush=True)


# --------------------------------------------------------------------------- #
def load_manifest() -> dict:
    out = {}
    if not S.MANIFEST_CSV.exists():
        return out
    with open(S.MANIFEST_CSV, "r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            out[row["document_id"]] = row
    return out


def _gap_before(lines: list[str], start: int, has_prev_block: bool) -> str:
    """返回该块相对上一块在**原文中的真实分隔符**。

    * 第一个块 → ``""``
    * 上一行是空行 → ``"\\n\\n"``（原文就是段落分隔）
    * 上一行非空 → ``"\\n"``（原文只是换行，不能补成空行）

    这是保证 ``content`` 逐字等于原文连续片段的关键：以前统一用 ``"\\n\\n"``
    重连，遇到「标题行紧跟正文行」就会凭空多出一个空行。
    """
    if not has_prev_block:
        return ""
    if start > 0 and not lines[start - 1].strip():
        return "\n\n"
    return "\n"


def parse_blocks(text: str) -> list[dict]:
    """Split cleaned Markdown into heading / table / text blocks."""
    lines = text.split("\n")
    blocks: list[dict] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.startswith("|"):
            j = i
            rows = []
            while j < len(lines) and lines[j].startswith("|"):
                rows.append(lines[j])
                j += 1
            blocks.append({"type": "table", "lines": rows, "text": "\n".join(rows),
                           "gap": _gap_before(lines, i, bool(blocks))})
            i = j
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            blocks.append({"type": "heading", "level": len(m.group(1)),
                           "text": m.group(2).strip(),
                           "md": line, "lines": [line],
                           "gap": _gap_before(lines, i, bool(blocks))})
            i += 1
            continue
        j = i
        buf = []
        while j < len(lines) and lines[j].strip() and not lines[j].startswith(("|", "#")):
            buf.append(lines[j])
            j += 1
        if j == i:
            # 兜底：以 "#" 开头但不是合法标题（如 "#标签"、
            # "#######"）的行会让上面的 while 一步不走，
            # 从而 i == j 导致死循环。这里强制前进一行。
            buf = [lines[i]]
            j = i + 1
        blocks.append({"type": "text", "lines": buf, "text": "\n".join(buf),
                       "gap": _gap_before(lines, i, bool(blocks))})
        i = j
    return blocks


def section_path_for(blocks: list[dict]) -> None:
    stack: list[tuple[int, str]] = []
    for b in blocks:
        if b["type"] == "heading":
            lvl = b["level"]
            while stack and stack[-1][0] >= lvl:
                stack.pop()
            stack.append((lvl, b["text"]))
            b["section_path"] = []
        else:
            b["section_path"] = [t for _, t in stack]
    # headings carry the path of their ancestors (excluding themselves)
    stack = []
    for b in blocks:
        if b["type"] == "heading":
            lvl = b["level"]
            while stack and stack[-1][0] >= lvl:
                stack.pop()
            b["section_path"] = [t for _, t in stack]
            stack.append((lvl, b["text"]))


def split_long_text(text: str, max_chars: int) -> list[str]:
    """Split a single oversized paragraph at sentence boundaries only."""
    if len(text) <= max_chars:
        return [text]
    parts = []
    cur = ""
    for ch in text:
        cur += ch
        if ch in SENT_END and len(cur) >= max_chars * 0.55:
            parts.append(cur)
            cur = ""
    if cur.strip():
        if parts and len(cur) < max_chars * 0.3:
            parts[-1] += cur
        else:
            parts.append(cur)
    out = []
    for p in parts:
        while len(p) > max_chars:
            out.append(p[:max_chars])
            p = p[max_chars:]
        out.append(p)
    return [p for p in out if p.strip()]


def split_table(lines: list[str], max_chars: int) -> list[list[str]]:
    """Split a Markdown table at row boundaries, repeating the header."""
    if sum(len(x) + 1 for x in lines) <= max_chars:
        return [lines]
    header = lines[:2]
    body = lines[2:]
    out = []
    cur = list(header)
    cur_len = sum(len(x) + 1 for x in header)
    for row in body:
        rl = len(row) + 1
        if cur_len + rl > max_chars and len(cur) > 2:
            out.append(cur)
            cur = list(header)
            cur_len = sum(len(x) + 1 for x in header)
        cur.append(row)
        cur_len += rl
    if len(cur) > 2:
        out.append(cur)
    return out or [lines]


def build_units(blocks: list[dict], max_chars: int) -> list[dict]:
    """Turn blocks into packable units (heading+oversized blocks handled)."""
    units: list[dict] = []
    for idx, b in enumerate(blocks):
        if b["type"] == "heading":
            units.append({"kind": "heading", "level": b["level"], "text": b["md"],
                          "gap": b.get("gap", "\n\n"),
                          "section_path": b["section_path"],
                          "section": b["text"], "block_index": idx})
            continue
        if b["type"] == "table":
            parts = split_table(b["lines"], max_chars)
            for pi, part in enumerate(parts):
                txt = "\n".join(part)
                suffix = "" if pi == 0 else "\n（续表）"
                units.append({"kind": "table", "text": txt + suffix,
                              "gap": b.get("gap", "\n\n") if pi == 0 else "\n",
                              "section_path": b["section_path"],
                              "section": b["section_path"][-1] if b["section_path"] else "",
                              "block_index": idx})
            continue
        for pi, piece in enumerate(split_long_text(b["text"], max_chars)):
            units.append({"kind": "text", "text": piece,
                          "glue": pi > 0,
                          "gap": b.get("gap", "\n\n") if pi == 0 else "",
                          "section_path": b["section_path"],
                          "section": b["section_path"][-1] if b["section_path"] else "",
                          "block_index": idx})
    return units


def join_units(units: list[dict]) -> str:
    """拼接 unit。``glue=True`` 的 unit 是同一段落被硬切出来的后续片段，
    必须用空串粘连，否则会在原文中平白多插一个段落分隔，
    导致 content 不再是逐字连续片段。
    """
    parts: list[str] = []
    for unit in units:
        if not unit["text"].strip():
            continue
        if parts and not unit.get("glue"):
            # 用该 unit 在原文中的真实前置分隔符，而不是一律 "\n\n"
            parts.append(unit.get("gap", "\n\n"))
        parts.append(unit["text"])
    return "".join(parts)


def pack(units: list[dict], min_chars: int, max_chars: int) -> list[list[int]]:
    """Greedy packing: 500-900 chars, headings never dangle.

    两处修复（原实现在部分文档上会死循环 / 卡死）：

    1. ``while`` 回退标题时不能把刚拿出来的标题再放回
       ``cur``，否则循环条件永远成立（无限循环）；
       正确做法是把它们存起来，给下一个 chunk 当开头。
    2. 长度用增量累加代替每次 ``join_units`` 重新拼接，
       避免 80000+ 字符 / 2800+ unit 文档上的 O(n^2)。
    """
    unit_len = [len(u["text"]) + (2 if u["text"].strip() else 0) for u in units]
    groups: list[list[int]] = []
    cur: list[int] = []
    cur_len = 0

    for i, _unit in enumerate(units):
        add = unit_len[i]
        if cur and cur_len + add > max_chars:
            # chunk 不能以标题结尾：把尾部标题拆到下一块
            carried: list[int] = []
            while cur and units[cur[-1]]["kind"] == "heading":
                head = cur.pop()
                cur_len -= unit_len[head]
                carried.insert(0, head)
            if cur:
                groups.append(list(cur))
            cur = carried + [i]
            cur_len = sum(unit_len[k] for k in cur)
        else:
            cur.append(i)
            cur_len += add
        # close the chunk once it reached the target and the next unit is a heading
        if cur_len >= min_chars:
            nxt = units[i + 1] if i + 1 < len(units) else None
            if nxt is not None and nxt["kind"] == "heading":
                groups.append(list(cur))
                cur = []
                cur_len = 0
    if cur:
        groups.append(list(cur))
    return [g for g in groups if join_units([units[k] for k in g]).strip()]


def apply_overlap(groups: list[list[int]], units: list[dict],
                  overlap_min: int, overlap_max: int) -> list[list[int]]:
    """用上一块**末尾**的整 unit 作为重叠。

    修复：原实现从前往后遍历并 ``insert(0, k)``，
    导致重叠部分**顺序被倒转**，
    拼出来的 `content` 不再是原文的连续片段（影响 Citation 引用可信度）。
    正确做法：从尾部倒着取，保证连续且顺序不变；
    遇到标题即停（不跨越标题边界）。
    """
    out: list[list[int]] = []
    for gi, g in enumerate(groups):
        if gi == 0:
            out.append(list(g))
            continue
        prev = groups[gi - 1]
        carried: list[int] = []
        size = 0
        for k in reversed(prev):
            if units[k]["kind"] == "heading":
                break
            step = len(units[k]["text"]) + 2
            if size + step > overlap_max:
                break
            carried.insert(0, k)
            size += step
        out.append(carried + list(g))
    return out


def make_chunks(document_id: str, text: str, meta: dict, args) -> list[dict]:
    blocks = parse_blocks(text)
    section_path_for(blocks)
    units = build_units(blocks, args.max)
    if not units:
        return []
    groups = pack(units, args.min, args.max)
    groups = apply_overlap(groups, units, args.overlap_min, args.overlap)
    chunks = []
    seq = 0
    for g in groups:
        content = join_units([units[k] for k in g])
        if not content.strip():
            continue
        if len(content) > args.hard_max:
            # extremely defensive: trim at a paragraph boundary
            cut = content.rfind("\n\n", 0, args.hard_max)
            content = content[:cut if cut > args.min else args.hard_max]
        seq += 1
        heads = [units[k]["section_path"] for k in g if units[k]["kind"] != "heading"]
        sp = heads[0] if heads else []
        if not sp:
            for k in g:
                if units[k]["kind"] == "heading":
                    sp = units[k]["section_path"] + [units[k]["section"].split(" ", 1)[-1]]
                    break
        section = sp[-1] if sp else ""
        for k in g:
            if units[k]["kind"] != "heading":
                section = units[k]["section"] or section
                break
        chunks.append({
            "chunk_id": f"{document_id}-{seq:04d}",
            "document_id": document_id,
            "title": meta.get("title", ""),
            "authority": meta.get("authority", ""),
            "authority_level": meta.get("authority_level", ""),
            "version": meta.get("version", ""),
            "publish_date": meta.get("publish_date", ""),
            "effective_date": meta.get("effective_date", ""),
            "diseases": [x for x in (meta.get("diseases", "") or "").split("|") if x],
            "scenarios": [x for x in (meta.get("scenarios", "") or "").split("|") if x],
            "section": section,
            "section_path": sp,
            "source_url": meta.get("source_url", ""),
            "content": content,
            "char_count": len(content),
        })
    return chunks


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min", type=int, default=DEFAULT_MIN)
    ap.add_argument("--max", type=int, default=DEFAULT_MAX)
    ap.add_argument("--hard-max", type=int, default=1200)
    ap.add_argument("--overlap", type=int, default=DEFAULT_OVERLAP)
    ap.add_argument("--overlap-min", type=int, default=80)
    ap.add_argument("--target-overlap", type=int, default=120)
    ap.add_argument("--only", nargs="*", default=None)
    args = ap.parse_args(argv[1:])

    manifest = load_manifest()
    pre = S.load_json(S.PREPROCESS_REPORT) or {"documents": []}
    ready = [r for r in pre.get("documents", [])
             if r.get("status") == "ok" and r.get("out_file")]

    S.CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    all_chunks: list[dict] = []
    per_doc: dict[str, int] = {}
    per_kb: dict[str, int] = {}
    skipped: list[dict] = []
    problems: list[str] = []

    for rec in ready:
        did = rec["document_id"]
        if args.only and did not in args.only:
            continue
        meta = manifest.get(did, {})
        path = S.PROJECT_ROOT / rec["out_file"]
        if not path.exists():
            skipped.append({"document_id": did, "reason": "processed file missing"})
            continue
        text = path.read_text(encoding="utf-8")
        chunks = make_chunks(did, text, meta, args)
        if not chunks:
            skipped.append({"document_id": did, "reason": "no chunkable content"})
            continue
        # verbatim check
        for c in chunks:
            if c["content"] not in text:
                problems.append(f"{c['chunk_id']}: content is not a verbatim slice")
            if c["char_count"] != len(c["content"]):
                problems.append(f"{c['chunk_id']}: char_count mismatch")
        all_chunks.extend(chunks)
        per_doc[did] = len(chunks)
        kb = meta.get("qianfan_kb", "UNKNOWN") or "UNKNOWN"
        per_kb[kb] = per_kb.get(kb, 0) + len(chunks)
        log(f"[{did}] {len(chunks):>4} chunks  (source {rec['chars']} chars)")

    with open(S.CHUNKS_JSONL, "w", encoding="utf-8", newline="\n") as fh:
        for c in all_chunks:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")

    sizes = [c["char_count"] for c in all_chunks]
    S.dump_json(S.INDEX_META, {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "script": "scripts/build_chunks.py",
        "params": {
            "target_min_chars": args.min,
            "target_max_chars": args.max,
            "hard_max_chars": args.hard_max,
            "overlap_chars": args.overlap,
            "overlap_min_chars": args.overlap_min,
            "split_boundary": "heading/paragraph/table-row only; never inside a clause or table row",
            "content_policy": "verbatim contiguous slice of knowledge/processed/<id>.md",
        },
        "chunks_total": len(all_chunks),
        "chunks_per_document": per_doc,
        "chunks_per_kb": per_kb,
        "documents_chunked": len(per_doc),
        "documents_without_source": [r["document_id"] for r in pre.get("documents", [])
                                     if r.get("status") != "ok"],
        "skipped": skipped,
        "verification": {"verbatim_problems": problems},
        "size_stats": {
            "min": min(sizes) if sizes else 0,
            "max": max(sizes) if sizes else 0,
            "mean": round(sum(sizes) / len(sizes), 1) if sizes else 0,
            "under_min": sum(1 for s in sizes if s < args.min),
            "over_max": sum(1 for s in sizes if s > args.max),
        },
    })
    log("")
    log(f"chunks -> {S.relpath(S.CHUNKS_JSONL)}  total={len(all_chunks)}")
    log(f"index meta -> {S.relpath(S.INDEX_META)}")
    if problems:
        log(f"!! verbatim problems: {len(problems)}")
        for p in problems[:10]:
            log("   " + p)
    stats = S.load_json(S.INDEX_META)["size_stats"]
    log(f"size stats: {json.dumps(stats, ensure_ascii=False)}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
