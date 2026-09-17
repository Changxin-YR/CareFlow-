"""校验知识来源：本地文件完整性 + 官方 URL 可达性。

用法::

    python scripts/verify_sources.py              # 只做离线校验（默认）
    python scripts/verify_sources.py --online     # 额外探测 source_url 可达性
    python scripts/verify_sources.py --online --json

离线校验（默认，必须全部通过）：

* `status=active` 的行：`local_file` 必须存在，且文件 sha256 必须与 manifest 一致；
* `status!=active` 的行：允许 `local_file=PENDING`；
* 所有行：`source_url` 必须是 http(s) 且指向官方域名白名单之外时给出警告。

在线校验（`--online`）：

* 对 `source_url` 发 HEAD/GET；
* **`www.nhc.gov.cn` 返回 412 属于预期**（WZWS JS 风控，非浏览器客户端一律 412），
  因此 412 记为 `reachable_waf`，不算失败；
* 401/403 记为 `blocked`（付费墙/需授权），同样不算失败但会列出。

退出码：0 = 无错误，1 = 有错误。
"""

from __future__ import annotations

import argparse
import csv
import os
import hashlib
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

#: 默认与应用一致：先读 ``MANIFEST_PATH`` 环境变量（否则会
#: “校验了一份不是当前运行时使用的 manifest 却报 PASS”——典型的静默通过型缺陷。
_default_manifest = os.environ.get("MANIFEST_PATH", "").strip()
MANIFEST = (
    Path(_default_manifest)
    if _default_manifest
    else PROJECT_ROOT / "knowledge" / "manifest" / "knowledge_manifest.csv"
)
if not MANIFEST.is_absolute():
    MANIFEST = PROJECT_ROOT / MANIFEST

OFFICIAL_HOSTS = (
    "nhc.gov.cn",
    "gov.cn",
    "who.int",
    "nccd.org.cn",
    "sinocardiomed.com",
    "yiigle.com",
    "dxy.cn",
)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_rows() -> list[dict[str, str]]:
    if not MANIFEST.exists():
        raise SystemExit(f"manifest 不存在：{MANIFEST}")
    with MANIFEST.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def check_offline(rows: list[dict[str, str]]) -> tuple[list[dict], list[dict]]:
    errors: list[dict] = []
    warnings: list[dict] = []
    for row in rows:
        document_id = row["document_id"]
        local_file = (row.get("local_file") or "").strip()
        status = (row.get("status") or "").strip()
        if status == "active":
            if not local_file or local_file == "PENDING":
                errors.append({"document_id": document_id, "reason": "active 行缺少 local_file"})
                continue
            path = PROJECT_ROOT / local_file
            if not path.exists():
                errors.append(
                    {"document_id": document_id, "reason": f"local_file 不存在：{local_file}"}
                )
                continue
            actual = sha256_file(path)
            expected = (row.get("sha256") or "").strip()
            if actual != expected:
                errors.append(
                    {
                        "document_id": document_id,
                        "reason": "sha256 不一致",
                        "expected": expected[:16],
                        "actual": actual[:16],
                    }
                )
        else:
            # draft/superseded 也可以保留下载到的文件作为来源记录；
            # 只有「声明有文件却不存在」才是问题。
            if local_file and local_file != "PENDING":
                path = PROJECT_ROOT / local_file
                if not path.exists():
                    errors.append(
                        {
                            "document_id": document_id,
                            "reason": f"非 active 但 local_file 指向的文件不存在：{local_file}",
                        }
                    )
            if not (row.get("notes") or "").strip():
                warnings.append(
                    {"document_id": document_id, "reason": "非 active 但 notes 为空，缺少原因说明"}
                )

        url = (row.get("source_url") or "").strip()
        if not url.startswith("http"):
            errors.append({"document_id": document_id, "reason": f"source_url 非法：{url!r}"})
        elif not any(host in url for host in OFFICIAL_HOSTS):
            warnings.append(
                {"document_id": document_id, "reason": f"source_url 不在官方域名白名单：{url}"}
            )
    return errors, warnings


def check_online(rows: list[dict[str, str]]) -> list[dict]:
    import httpx

    results: list[dict] = []
    headers = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}
    with httpx.Client(timeout=20, follow_redirects=True, headers=headers, trust_env=False) as client:
        for row in rows:
            url = row["source_url"]
            entry = {"document_id": row["document_id"], "url": url}
            try:
                response = client.get(url)
                status = response.status_code
                entry["http_status"] = status
                if status in (200, 206):
                    entry["verdict"] = "reachable"
                elif status == 412:
                    entry["verdict"] = "reachable_waf"  # WZWS：非浏览器客户端必然 412
                elif status in (401, 403):
                    entry["verdict"] = "blocked"  # 付费墙/需授权
                elif status in (301, 302):
                    entry["verdict"] = "redirect"
                else:
                    entry["verdict"] = f"http_{status}"
            except Exception as exc:  # noqa: BLE001
                entry["verdict"] = "network_error"
                entry["error"] = f"{type(exc).__name__}: {exc}"[:160]
            results.append(entry)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="校验知识来源")
    parser.add_argument("--online", action="store_true", help="额外探测 source_url 可达性")
    parser.add_argument("--json", action="store_true", help="输出机器可读结果")
    parser.add_argument(
        "--manifest",
        default="",
        help="manifest 路径（默认取 MANIFEST_PATH 环境变量，再退回 knowledge/manifest/knowledge_manifest.csv）",
    )
    args = parser.parse_args()

    global MANIFEST
    if args.manifest:
        MANIFEST = Path(args.manifest)
        if not MANIFEST.is_absolute():
            MANIFEST = PROJECT_ROOT / MANIFEST

    rows = load_rows()
    errors, warnings = check_offline(rows)
    payload: dict = {
        "manifest": str(MANIFEST),
        "rows": len(rows),
        "errors": errors,
        "warnings": warnings,
    }

    if args.online:
        online = check_online(rows)
        payload["online"] = online
        counts: dict[str, int] = {}
        for item in online:
            counts[item["verdict"]] = counts.get(item["verdict"], 0) + 1
        payload["online_summary"] = counts

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"manifest: {MANIFEST}")
        print(f"rows: {len(rows)}")
        print(f"offline errors:   {len(errors)}")
        for item in errors:
            print(f"  ERROR   {item['document_id']:9} {item['reason']}")
        print(f"offline warnings: {len(warnings)}")
        for item in warnings:
            print(f"  WARN    {item['document_id']:9} {item['reason']}")
        if args.online:
            print("online:", payload.get("online_summary"))
            for item in payload.get("online", []):
                if item["verdict"] not in ("reachable", "reachable_waf"):
                    print(f"  ONLINE  {item['document_id']:9} {item['verdict']} {item.get('error','')}")

    if errors:
        print("VERIFY FAILED")
        return 1
    print("VERIFY PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
