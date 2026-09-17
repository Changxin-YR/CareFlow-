"""CareFlow 康脉智护 —— AI/RAG 离线评测框架。

用法::

    python scripts/evaluate.py                      # 默认：跟随 AI_PROVIDER
    python scripts/evaluate.py --provider mock      # 强制离线规则/摘录基线
    python scripts/evaluate.py --suite rag,citation # 只跑指定套件
    python scripts/evaluate.py --out eval/results

设计原则
--------
* **只测可客观判定的东西**：字段是否提取、值是否一致、引用是否命中真实文档、
  该说"没证据"的时候有没有说"没证据"。
* **不做医学正确性评分**。本框架无法判断"医学准不准"，
  因此 `eval/REPORT.md` 中不会出现任何"医学准确率"数字。
* 每个套件都输出逐条明细，便于定位回归。
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import load_settings  # noqa: E402

EVAL_DIR = PROJECT_ROOT / "eval"
DATASET_DIR = EVAL_DIR / "datasets"
RESULTS_DIR = EVAL_DIR / "results"

SUITE_FILES = {
    "extraction": "extraction_cases.jsonl",
    "routing": "routing_cases.jsonl",
    "rag": "rag_cases.jsonl",
    "citation": "citation_cases.jsonl",
    "no_evidence": "no_evidence_cases.jsonl",
    "safety": "safety_cases.jsonl",
    "injection": "injection_cases.jsonl",
}


def load_cases(suite: str) -> list[dict[str, Any]]:
    path = DATASET_DIR / SUITE_FILES[suite]
    if not path.exists():  # pragma: no cover
        raise SystemExit(f"数据集不存在：{path}")
    cases: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, start=1):
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            try:
                cases.append(json.loads(line))
            except json.JSONDecodeError as exc:  # pragma: no cover
                raise SystemExit(f"{path}:{lineno} 非法 JSON: {exc}") from exc
    return cases


@dataclass
class SuiteResult:
    name: str
    total: int = 0
    passed: int = 0
    metrics: dict[str, float] = field(default_factory=dict)
    failures: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    duration_ms: int = 0

    @property
    def pass_rate(self) -> float:
        return (self.passed / self.total) if self.total else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "total": self.total,
            "passed": self.passed,
            "pass_rate": round(self.pass_rate, 4),
            "metrics": {key: round(value, 4) for key, value in self.metrics.items()},
            "failures": self.failures[:40],
            "notes": self.notes,
            "duration_ms": self.duration_ms,
        }


# --------------------------------------------------------------------------- #
# 套件实现
# --------------------------------------------------------------------------- #
async def run_extraction(services, cases: list[dict]) -> SuiteResult:
    result = SuiteResult(name="extraction")
    type_hits = type_total = 0
    value_hits = value_total = 0
    schema_ok = 0
    ungrounded = 0
    observations_total = 0

    for case in cases:
        result.total += 1
        expected: list[dict] = case["expected"]
        try:
            data = await services.extraction.extract(case["text"])
        except Exception as exc:  # noqa: BLE001
            result.failures.append({"id": case["id"], "error": f"{type(exc).__name__}: {exc}"})
            type_total += len(expected)
            value_total += len(expected)
            continue

        schema_ok += 1
        produced = {item.type.value: item for item in data.observations}
        observations_total += len(data.observations)
        case_failed: list[str] = []
        for want in expected:
            want_type = want["type"]
            type_total += 1
            if want_type not in produced:
                case_failed.append(f"缺失类型 {want_type}")
                continue
            type_hits += 1
            if "value" in want:
                value_total += 1
                actual = produced[want_type].value
                if _value_matches(want["value"], actual):
                    value_hits += 1
                else:
                    case_failed.append(f"{want_type} 值不符：期望 {want['value']} 实际 {actual}")
        for observation in data.observations:
            if observation.source_text and observation.source_text not in case["text"]:
                ungrounded += 1
                case_failed.append(f"非原文观测：{observation.type.value}/{observation.source_text}")
        if case_failed:
            result.failures.append({"id": case["id"], "issues": case_failed})
        else:
            result.passed += 1

    result.metrics = {
        "field_accuracy": type_hits / type_total if type_total else 0.0,
        "value_accuracy": value_hits / value_total if value_total else 0.0,
        "schema_pass_rate": schema_ok / result.total if result.total else 0.0,
        "hallucination_rate": (ungrounded / observations_total) if observations_total else 0.0,
    }
    result.notes.append(f"共提取 {observations_total} 条 observation，其中非原文 {ungrounded} 条")
    return result


def _value_matches(expected: dict, actual: dict) -> bool:
    for key, want in expected.items():
        got = actual.get(key)
        if isinstance(want, (int, float)) and isinstance(got, (int, float)):
            if abs(float(want) - float(got)) > 1e-6:
                return False
        elif str(got) != str(want):
            return False
    return True


async def run_routing(services, cases: list[dict]) -> SuiteResult:
    result = SuiteResult(name="routing")
    recall_sum = precision_sum = 0.0
    exact = 0
    for case in cases:
        result.total += 1
        routing = await services.router.route(case["query"], explicit=case.get("domains"))
        got = set(routing.domains)
        want = set(case["expected_domains"])
        if not want:
            ok = not got
            recall = precision = 1.0 if ok else 0.0
        else:
            intersect = got & want
            recall = len(intersect) / len(want)
            precision = len(intersect) / len(got) if got else 0.0
            ok = want <= got
        recall_sum += recall
        precision_sum += precision
        exact += 1 if got == want else 0
        if not ok:
            result.failures.append({"id": case["id"], "query": case["query"], "expected": sorted(want), "got": sorted(got)})
        else:
            result.passed += 1
    total = result.total or 1
    result.metrics = {
        "domain_recall": recall_sum / total,
        "domain_precision": precision_sum / total,
        "exact_match_rate": exact / total,
    }
    return result


async def run_rag(services, cases: list[dict]) -> SuiteResult:
    result = SuiteResult(name="rag")
    recall_hits = recall_total = 0
    citation_hits = 0
    authority_hits = 0
    authority_total = 0
    must_fail = 0

    for case in cases:
        result.total += 1
        response = await services.rag.answer(_rag_request(case))
        got_docs = {hit.document_id for hit in response.retrieved}
        issues: list[str] = []

        expected_docs = set(case.get("expected_documents") or [])
        if expected_docs:
            recall_total += 1
            if got_docs & expected_docs:
                recall_hits += 1
            else:
                issues.append(f"Recall@K 未命中：期望 {sorted(expected_docs)} 实际 {sorted(got_docs)}")

        if case.get("expect_citation", True):
            if response.citations:
                citation_hits += 1
            else:
                issues.append("未返回 Citation")
        elif response.citations:
            issues.append(f"不该有 Citation 却返回了 {len(response.citations)} 条")

        expected_levels = set(case.get("expected_authority_levels") or [])
        if expected_levels:
            authority_total += 1
            levels = {citation.authority_level for citation in response.citations}
            if levels & expected_levels:
                authority_hits += 1
            else:
                issues.append(f"权威等级未命中：期望 {sorted(expected_levels)} 实际 {sorted(levels)}")

        for phrase in case.get("answer_must_contain", []):
            if phrase not in response.answer:
                issues.append(f"答案缺少必需内容：{phrase}")
        for phrase in case.get("answer_must_not_contain", []):
            if phrase in response.answer:
                issues.append(f"答案包含禁止内容：{phrase}")

        if issues:
            must_fail += 1
            result.failures.append({"id": case["id"], "query": case["query"], "issues": issues})
        else:
            result.passed += 1

    total = result.total or 1
    result.metrics = {
        "recall_at_k": recall_hits / recall_total if recall_total else 0.0,
        "citation_hit_rate": citation_hits / total,
        # 本批用例没有声明 expected_authority_levels 时记为 1.0（不适用），
        # 避免读者把 0.0 误读成"权威等级全部未命中"
        "authority_hit_rate": authority_hits / authority_total if authority_total else 1.0,
        "case_pass_rate": result.passed / total,
    }
    if not authority_total:
        result.notes.append(
            "本批 RAG 用例未声明 expected_authority_levels，authority_hit_rate 不适用（记为 1.0）"
        )
    return result


def _rag_request(case: dict):
    from app.schemas.rag import RagOptions, RagRequest

    options = case.get("options") or {}
    return RagRequest(query=case["query"], options=RagOptions(**options) if options else RagOptions())


CITATION_FIXTURE_DOCUMENTS: list[dict[str, str]] = [
    ("HTN001", "高血压基层管理（评测夹具）", "P0", "KB_HTN", "active"),
    ("DM001", "糖尿病基层管理（评测夹具）", "P1", "KB_DM", "active"),
    ("LIFE001", "慢性病食养（评测夹具）", "P1", "KB_LIFESTYLE", "active"),
    ("PRIM001", "居民健康档案（评测夹具）", "P1", "KB_PRIMARYCARE", "active"),
    ("PRIM003", "老年人健康管理（评测夹具）", "P0", "KB_PRIMARYCARE", "active"),
    ("COPD901", "慢阻肺现行（评测夹具）", "P1", "KB_COPD", "active"),
    ("COPD900", "慢阻肺已作废（评测夹具）", "P2", "KB_COPD", "superseded"),
]


def build_citation_service():
    """Citation 套件用**自包含夹具**，不依赖真实知识库的下载进度。"""
    import csv
    import tempfile

    from app.core.config import MANIFEST_COLUMNS
    from app.services.citation_service import CitationService
    from app.services.manifest_service import KnowledgeStore

    tmp = Path(tempfile.mkdtemp(prefix="careflow_citation_eval_"))
    manifest = tmp / "knowledge_manifest.csv"
    chunks = tmp / "chunks.jsonl"
    rows = []
    chunk_rows = []
    for index, (doc_id, title, level, kb, status) in enumerate(CITATION_FIXTURE_DOCUMENTS):
        rows.append(
            {
                "document_id": doc_id,
                "title": title,
                "authority": "CareFlow Eval Fixture",
                "authority_level": level,
                "document_type": "nhc_guideline",
                "version": "2024",
                "publish_date": "2024-01-01",
                "effective_date": "2024-01-01",
                "replaced_by": "",
                "status": status,
                "diseases": "HYPERTENSION",
                "scenarios": "education",
                "language": "zh",
                "source_url": f"https://example.invalid/eval/{doc_id.lower()}",
                "local_file": "PENDING",
                "sha256": "",
                "qianfan_kb": kb,
                "notes": "评测夹具",
            }
        )
        chunk_rows.append(
            {
                "chunk_id": f"{doc_id}-0001",
                "document_id": doc_id,
                "title": title,
                "authority_level": level,
                "source_url": f"https://example.invalid/eval/{doc_id.lower()}",
                "content": f"{title} 的评测内容 {index}",
            }
        )
        if doc_id == "HTN001":
            chunk_rows.append(
                {
                    "chunk_id": "HTN001-0002",
                    "document_id": doc_id,
                    "title": title,
                    "authority_level": level,
                    "source_url": f"https://example.invalid/eval/{doc_id.lower()}",
                    "content": "高血压生活方式干预评测内容",
                }
            )
    with manifest.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(MANIFEST_COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    with chunks.open("w", encoding="utf-8") as handle:
        for row in chunk_rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    settings = dataclasses.replace(load_settings(), manifest_path=manifest, chunks_path=chunks)
    store = KnowledgeStore(settings).load()
    return CitationService(store)


async def run_citation(services, cases: list[dict]) -> SuiteResult:
    """构造检索命中 → 校验 Citation 必须/不得产生。"""
    from app.schemas.common import RetrievedChunk

    citation_service = build_citation_service()
    result = SuiteResult(name="citation")
    false_citations = 0
    caught = 0

    for case in cases:
        result.total += 1
        hits = [
            RetrievedChunk(
                chunk_id=item.get("chunk_id", ""),
                document_id=item.get("document_id", ""),
                title=item.get("title", ""),
                section=item.get("section", ""),
                authority_level=item.get("authority_level", ""),
                source_url=item.get("source_url", ""),
                content=item.get("content", "内容"),
            )
            for item in case["hits"]
        ]
        built = citation_service.build(
            hits,
            used_markers=case.get("used_markers"),
            used_chunk_ids=case.get("used_chunk_ids"),
        )
        expected_ids = set(case.get("expected_citation_document_ids") or [])
        got_ids = {citation.document_id for citation in built.citations}
        expected_drops = set(case.get("expected_drop_reasons") or [])
        got_drops = {item.reason for item in built.dropped}

        issues: list[str] = []
        if got_ids != expected_ids:
            issues.append(f"引用文档不符：期望 {sorted(expected_ids)} 实际 {sorted(got_ids)}")
        missing_drops = expected_drops - got_drops
        if missing_drops:
            issues.append(f"未产生预期丢弃原因：{sorted(missing_drops)}")

        if case.get("must_be_rejected"):
            if built.citations:
                false_citations += len(built.citations)
                issues.append("非法引用未被拦截")
            else:
                caught += 1

        # 反向校验：所有产出的引用都必须能通过 verify
        for citation in built.citations:
            ok, reason = citation_service.verify_citation(citation)
            if not ok:
                false_citations += 1
                issues.append(f"产出了不可验证引用：{reason}")

        if issues:
            result.failures.append({"id": case["id"], "issues": issues})
        else:
            result.passed += 1

    negatives = sum(1 for case in cases if case.get("must_be_rejected"))
    result.metrics = {
        "citation_case_pass_rate": result.passed / (result.total or 1),
        "false_citation_count": float(false_citations),
        "illegal_citation_block_rate": (caught / negatives) if negatives else 1.0,
    }
    result.notes.append(f"非法引用样本 {negatives} 条，全部拦截 = {caught == negatives}")
    return result


async def run_no_evidence(services, cases: list[dict]) -> SuiteResult:
    result = SuiteResult(name="no_evidence")
    correct = 0
    for case in cases:
        result.total += 1
        response = await services.rag.answer(_rag_request(case))
        want = bool(case["expect_insufficient_evidence"])
        got = bool(response.insufficient_evidence)
        issues: list[str] = []
        if got != want:
            issues.append(f"insufficient_evidence 期望 {want} 实际 {got}")
        if got and response.citations:
            issues.append("无证据却给出了 Citation")
        if issues:
            result.failures.append({"id": case["id"], "query": case["query"], "issues": issues})
        else:
            correct += 1
            result.passed += 1
    result.metrics = {"no_evidence_accuracy": correct / (result.total or 1)}
    return result


async def run_safety(services, cases: list[dict]) -> SuiteResult:
    result = SuiteResult(name="safety")
    block_correct = 0
    flag_correct = 0
    flag_total = 0
    for case in cases:
        result.total += 1
        decision = services.safety.check_query(case["text"])
        issues: list[str] = []
        want_block = bool(case.get("expect_blocked"))
        if decision.blocked != want_block:
            issues.append(f"blocked 期望 {want_block} 实际 {decision.blocked}")
        else:
            block_correct += 1
        for flag in case.get("expect_flags", []):
            flag_total += 1
            if flag in decision.report.flags:
                flag_correct += 1
            else:
                issues.append(f"缺少 flag {flag}")
        if issues:
            result.failures.append({"id": case["id"], "text": case["text"][:40], "issues": issues})
        else:
            result.passed += 1
    result.metrics = {
        "block_decision_accuracy": block_correct / (result.total or 1),
        "flag_accuracy": flag_correct / flag_total if flag_total else 1.0,
    }
    return result


async def run_injection(services, cases: list[dict]) -> SuiteResult:
    result = SuiteResult(name="injection")
    blocked = 0
    for case in cases:
        result.total += 1
        decision = services.safety.check_query(case["text"])
        if decision.report.injection_detected or decision.blocked:
            blocked += 1
            result.passed += 1
        else:
            result.failures.append(
                {"id": case["id"], "text": case["text"][:60], "issues": ["注入未被识别"]}
            )
    result.metrics = {
        "injection_detection_rate": blocked / (result.total or 1),
        "injection_bypass_count": float(result.total - blocked),
    }
    return result


SUITES = {
    "extraction": run_extraction,
    "routing": run_routing,
    "rag": run_rag,
    "citation": run_citation,
    "no_evidence": run_no_evidence,
    "safety": run_safety,
    "injection": run_injection,
}


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
async def run_all(suite_names: list[str], provider: str) -> dict[str, Any]:
    from app.core.config import load_settings, reload_settings
    from app.api import deps

    if provider:
        import os

        os.environ["AI_PROVIDER"] = provider
    reload_settings()
    deps.reset_services()
    services = deps.build_services()
    settings = load_settings()

    store_health = services.store.health()
    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provider": settings.ai_provider,
        "contract_version": "CF-CONTRACT-2.0",
        "knowledge": {
            "documents_total": store_health["stats"]["documents_total"],
            "documents_active": store_health["stats"]["documents_active"],
            "chunks_total": store_health["stats"]["chunks_total"],
            "manifest_status": store_health["manifest"],
            "knowledge_status": store_health["knowledge"],
        },
        "suites": {},
    }
    for name in suite_names:
        cases = load_cases(name)
        started = time.perf_counter()
        suite_result = await SUITES[name](services, cases)
        suite_result.duration_ms = int((time.perf_counter() - started) * 1000)
        report["suites"][name] = suite_result.to_dict()
        print(
            f"  {name:<12} cases={suite_result.total:<4} pass={suite_result.passed:<4} "
            f"rate={suite_result.pass_rate:.2%}  {suite_result.metrics}"
        )
    return report


def write_report(payload: dict[str, Any]) -> tuple[Path, Path]:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = RESULTS_DIR / f"eval_{stamp}.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines: list[str] = []
    lines.append("# CareFlow 康脉智护 —— Eval 报告\n")
    lines.append(f"- 生成时间（UTC）：`{payload['generated_at']}`")
    lines.append(f"- AI Provider：`{payload['provider']}`")
    lines.append(f"- 契约版本：`{payload['contract_version']}`")
    knowledge = payload["knowledge"]
    lines.append(
        f"- 知识库：{knowledge['documents_total']} 篇（active {knowledge['documents_active']}）／"
        f"{knowledge['chunks_total']} 个切片"
    )
    lines.append("")
    lines.append("> 说明：本报告**不包含任何「医学准确率」指标**。评测只覆盖")
    lines.append("> 可客观判定的工程指标（提取字段/数值、路由召回、检索命中、")
    lines.append("> Citation 真实性、无证据行为、安全拦截）。医学正确性必须由临床专家评审。")
    lines.append("")

    lines.append("## 1. 汇总\n")
    lines.append("| 套件 | 用例数 | 通过 | 通过率 | 关键指标 |")
    lines.append("|---|---:|---:|---:|---|")
    for name, suite in payload["suites"].items():
        metrics = "；".join(f"{k}={v}" for k, v in suite["metrics"].items())
        lines.append(
            f"| {name} | {suite['total']} | {suite['passed']} | {suite['pass_rate']:.2%} | {metrics} |"
        )
    lines.append("")

    lines.append("## 2. 逐套件明细\n")
    for name, suite in payload["suites"].items():
        lines.append(f"### {name}\n")
        lines.append(f"- 用例 {suite['total']} 条，通过 {suite['passed']} 条，耗时 {suite['duration_ms']} ms")
        for key, value in suite["metrics"].items():
            lines.append(f"- `{key}` = **{value}**")
        for note in suite.get("notes", []):
            lines.append(f"- 备注：{note}")
        if suite["failures"]:
            lines.append(f"- 失败 {len(suite['failures'])} 条（最多展示 10 条）：")
            for failure in suite["failures"][:10]:
                lines.append(f"  - `{failure.get('id')}`：{failure.get('issues') or failure.get('error')}")
        else:
            lines.append("- 失败：0")
        lines.append("")

    lines.append("## 3. 原始结果\n")
    lines.append(f"完整逐条结果见 `{json_path.relative_to(PROJECT_ROOT).as_posix()}`。")
    lines.append("")

    report_path = EVAL_DIR / "REPORT.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, report_path


def main() -> int:
    parser = argparse.ArgumentParser(description="CareFlow AI/RAG 离线评测")
    parser.add_argument("--provider", default="", help="mock | qianfan（默认跟随 .env）")
    parser.add_argument("--suite", default="", help="逗号分隔的套件名；默认全部")
    parser.add_argument("--out", default="", help="结果目录（默认 eval/results）")
    args = parser.parse_args()

    if args.out:
        global RESULTS_DIR
        RESULTS_DIR = Path(args.out)

    names = [name.strip() for name in args.suite.split(",") if name.strip()] or list(SUITES)
    unknown = [name for name in names if name not in SUITES]
    if unknown:
        raise SystemExit(f"未知套件：{unknown}，可选：{list(SUITES)}")

    print(f"CareFlow Eval —— provider={args.provider or '(from env)'} suites={names}")
    payload = asyncio.run(run_all(names, args.provider))
    json_path, report_path = write_report(payload)
    print(f"\nJSON: {json_path}")
    print(f"报告: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
