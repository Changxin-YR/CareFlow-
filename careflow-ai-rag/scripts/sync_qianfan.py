"""把本地知识库同步到百度千帆知识库（按 8 个知识域分组）。

用法::

    python scripts/sync_qianfan.py --dry-run      # 只打印将要同步的内容与统计
    python scripts/sync_qianfan.py                # 真实调用千帆
    python scripts/sync_qianfan.py --kb KB_HTN    # 只同步某个域

> 🔴 **本脚本的真实同步路径尚未用凭据验证（BLOCKED）。**
> 千帆知识库相关接口在不同平台版本间路径与入参存在差异，脚本已把路径做成
> 可配置项并对响应做宽容解析，但**上线前必须按当期官方文档核对**
> `QianfanClient.DEFAULT_PATHS["kb_retrieve"]` / `["appbuilder_run"]`
> 以及下面 `CREATE_DOC_PATH`。

同步粒度：**按域聚合为整篇文档上传**（每个 `KB_*` 一篇，内容为该域全部
active 文档的清洗正文拼接），而不是逐 chunk 上传 —— 减少调用次数、降低成本。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.clients.qianfan import QianfanClient  # noqa: E402
from app.core.config import KB_IDS, load_settings  # noqa: E402
from app.core.errors import CareFlowError  # noqa: E402
from app.services.manifest_service import KnowledgeStore  # noqa: E402

PROCESSED_DIR = PROJECT_ROOT / "knowledge" / "processed"
DOCS_DIR = PROJECT_ROOT / "docs"

#: 千帆「新增文档」路径 —— 需按当期官方文档核对
CREATE_DOC_PATH = "/v2/knowledgeBase/document"


def build_domain_payloads(store: KnowledgeStore) -> dict[str, dict]:
    """按知识域聚合 active 文档的清洗正文。"""
    payloads: dict[str, dict] = {}
    for entry in store.active_documents():
        kb = entry.qianfan_kb
        if kb not in KB_IDS:
            continue
        bucket = payloads.setdefault(
            kb,
            {"kb": kb, "documents": [], "chars": 0, "missing_text": []},
        )
        processed = PROCESSED_DIR / f"{entry.document_id}.md"
        if not processed.exists():
            bucket["missing_text"].append(entry.document_id)
            continue
        text = processed.read_text(encoding="utf-8").strip()
        bucket["documents"].append(
            {
                "document_id": entry.document_id,
                "title": entry.title,
                "authority": entry.authority,
                "authority_level": entry.authority_level,
                "version": entry.version,
                "effective_date": entry.effective_date,
                "source_url": entry.source_url,
                "text": text,
            }
        )
        bucket["chars"] += len(text)
    return payloads


def render_body(bucket: dict) -> str:
    """把某域的所有文档拼成一篇可上传的正文（保留可追溯的来源标注）。"""
    blocks: list[str] = []
    for doc in bucket["documents"]:
        blocks.append(
            f"## {doc['title']}\n\n"
            f"（document_id: {doc['document_id']}；发布机构：{doc['authority']}；"
            f"权威等级：{doc['authority_level']}；版本：{doc['version'] or '未标注'}；"
            f"来源：{doc['source_url']}）\n\n"
            f"{doc['text']}"
        )
    return "\n\n---\n\n".join(blocks)


async def sync(only: list[str] | None, dry_run: bool) -> int:
    settings = load_settings()
    if not settings.qianfan_configured and not dry_run:
        print("✗ 缺少 QIANFAN_API_KEY / QIANFAN_APP_ID —— 请先配置 .env，或使用 --dry-run")
        return 2

    store = KnowledgeStore(settings).load()
    store.require_ready()
    payloads = build_domain_payloads(store)

    print(f"provider={settings.ai_provider} base_url={settings.qianfan_base_url}")
    print(f"active 文档 {len(store.active_documents())} 篇，聚合为 {len(payloads)} 个知识域\n")

    client = QianfanClient(settings)
    report: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": "dry_run" if dry_run else "live",
        "base_url": settings.qianfan_base_url,
        "knowledge_bases": [],
    }
    failures = 0

    try:
        for kb in KB_IDS:
            if only and kb not in only:
                continue
            bucket = payloads.get(kb)
            kb_id = settings.kb_id_for(kb)
            if bucket is None:
                print(f"[{kb}] 无 active 文档，跳过")
                continue
            body = render_body(bucket)
            entry = {
                "kb": kb,
                "kb_id": "SET" if kb_id else "",
                "documents": len(bucket["documents"]),
                "chars": len(body),
                "missing_text": bucket["missing_text"],
            }
            if not kb_id:
                entry["status"] = "skipped_no_kb_id"
                print(
                    f"[{kb}] {len(bucket['documents'])} 篇 / {len(body)} 字符 —— "
                    f"未配置 QIANFAN_{kb}_ID，跳过"
                )
                report["knowledge_bases"].append(entry)
                continue

            if dry_run:
                entry["status"] = "dry_run"
                print(
                    f"[{kb}] {len(bucket['documents'])} 篇 / {len(body)} 字符 → kb_id={kb_id[:8]}… (dry-run)"
                )
                report["knowledge_bases"].append(entry)
                continue

            print(f"[{kb}] 上传中 … {len(body)} 字符 → kb_id={kb_id[:8]}…")
            try:
                result = await client.create_document(
                    path=CREATE_DOC_PATH,
                    payload={
                        "knowledgeBaseId": kb_id,
                        "name": f"CareFlow-{kb}-{datetime.now(timezone.utc):%Y%m%d}",
                        "content": body,
                        "sourceUrl": bucket["documents"][0]["source_url"],
                    },
                )
                entry["status"] = "uploaded"
                entry["response_keys"] = sorted(result.keys())[:8] if isinstance(result, dict) else []
            except CareFlowError as exc:
                entry["status"] = "failed"
                entry["error_code"] = exc.code.value
                entry["error"] = exc.message[:200]
                failures += 1
                print(f"    ✗ {exc.code.value}: {exc.message[:160]}")
            report["knowledge_bases"].append(entry)
    finally:
        await client.aclose()

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    out = PROJECT_ROOT / "knowledge" / "manifest" / "_sync_qianfan_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告 -> {out.relative_to(PROJECT_ROOT).as_posix()}")
    if dry_run:
        print("dry-run 完成：未发起任何真实请求。")
        return 0
    if failures:
        print(f"同步完成但有 {failures} 个域失败。")
        return 1
    print("同步完成。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="同步知识库到百度千帆")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划，不发起真实请求")
    parser.add_argument("--kb", nargs="*", default=None, help="只同步指定知识域，如 --kb KB_HTN")
    args = parser.parse_args()
    return asyncio.run(sync(args.kb, args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
