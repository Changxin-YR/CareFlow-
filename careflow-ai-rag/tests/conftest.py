"""pytest 夹具。

**重要**：这里的知识库夹具是**合成的测试数据**，标题带「【测试夹具】」前缀，
`source_url` 指向 `https://example.invalid/...`。它们唯一的作用是让单元测试
可以离线、确定性地运行；**它们不是官方资料，任何情况下都不得当作知识来源**。

真实知识库的验证在 `tests/test_live_knowledge.py`。
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from app.api import deps
from app.core.config import MANIFEST_COLUMNS, reload_settings

# --------------------------------------------------------------------------- #
# 合成知识库
# --------------------------------------------------------------------------- #
FIXTURE_DOCUMENTS: list[dict[str, str]] = [
    {
        "document_id": "HTN001",
        "title": "【测试夹具】高血压基层管理测试文档",
        "authority": "CareFlow Test Fixture",
        "authority_level": "P0",
        "document_type": "national_standard",
        "version": "2025",
        "publish_date": "2025-01-01",
        "effective_date": "2025-06-01",
        "replaced_by": "",
        "status": "active",
        "diseases": "HYPERTENSION",
        "scenarios": "followup|education",
        "language": "zh",
        "source_url": "https://example.invalid/fixture/htn001",
        "local_file": "knowledge/raw/02_hypertension/HTN001.html",
        "sha256": "0" * 64,
        "qianfan_kb": "KB_HTN",
        "notes": "合成测试数据",
    },
    {
        "document_id": "DM001",
        "title": "【测试夹具】糖尿病基层管理测试文档",
        "authority": "CareFlow Test Fixture",
        "authority_level": "P1",
        "document_type": "nhc_guideline",
        "version": "2024",
        "publish_date": "2024-05-01",
        "effective_date": "2024-07-01",
        "replaced_by": "",
        "status": "active",
        "diseases": "DIABETES",
        "scenarios": "followup|education",
        "language": "zh",
        "source_url": "https://example.invalid/fixture/dm001",
        "local_file": "knowledge/raw/03_diabetes/DM001.html",
        "sha256": "1" * 64,
        "qianfan_kb": "KB_DM",
        "notes": "合成测试数据",
    },
    {
        "document_id": "LIFE001",
        "title": "【测试夹具】慢性病食养测试文档",
        "authority": "CareFlow Test Fixture",
        "authority_level": "P3",
        "document_type": "expert_consensus",
        "version": "2024",
        "publish_date": "2024-02-01",
        "effective_date": "2024-03-01",
        "replaced_by": "",
        "status": "active",
        "diseases": "HYPERTENSION|OBESITY",
        "scenarios": "education|lifestyle",
        "language": "zh",
        "source_url": "https://example.invalid/fixture/life001",
        "local_file": "knowledge/raw/06_lifestyle/LIFE001.pdf",
        "sha256": "2" * 64,
        "qianfan_kb": "KB_LIFESTYLE",
        "notes": "合成测试数据",
    },
    {
        "document_id": "COPD900",
        "title": "【测试夹具】已停用文档（不得进入检索）",
        "authority": "CareFlow Test Fixture",
        "authority_level": "P2",
        "document_type": "nhc_policy",
        "version": "2019",
        "publish_date": "2019-01-01",
        "effective_date": "2019-02-01",
        "replaced_by": "COPD901",
        "status": "superseded",
        "diseases": "COPD",
        "scenarios": "followup",
        "language": "zh",
        "source_url": "https://example.invalid/fixture/copd900",
        "local_file": "PENDING",
        "sha256": "",
        "qianfan_kb": "KB_COPD",
        "notes": "合成测试数据，已作废",
    },
    {
        "document_id": "COPD901",
        "title": "【测试夹具】慢阻肺现行测试文档",
        "authority": "CareFlow Test Fixture",
        "authority_level": "P1",
        "document_type": "nhc_guideline",
        "version": "2024",
        "publish_date": "2024-06-01",
        "effective_date": "2024-08-01",
        "replaced_by": "",
        "status": "active",
        "diseases": "COPD",
        "scenarios": "followup|education",
        "language": "zh",
        "source_url": "https://example.invalid/fixture/copd901",
        "local_file": "knowledge/raw/04_copd/COPD901.html",
        "sha256": "3" * 64,
        "qianfan_kb": "KB_COPD",
        "notes": "合成测试数据",
    },
]

FIXTURE_CHUNKS: list[dict] = [
    {
        "chunk_id": "HTN001-0001",
        "document_id": "HTN001",
        "title": "【测试夹具】高血压基层管理测试文档",
        "authority": "CareFlow Test Fixture",
        "authority_level": "P0",
        "version": "2025",
        "effective_date": "2025-06-01",
        "diseases": ["HYPERTENSION"],
        "scenarios": ["followup", "education"],
        "section": "一、家庭血压测量",
        "section_path": ["一、家庭血压测量"],
        "source_url": "https://example.invalid/fixture/htn001",
        "content": (
            "家庭血压测量建议使用经过验证的上臂式电子血压计，测量前静坐五分钟，"
            "测量时上臂与心脏保持同一水平。建议每天早晚各测量一次，每次测量两到三遍，"
            "取平均值记录。对基层高血压患者开展随访时，应同时记录血压数值、测量时间"
            "与是否按时服药，用于业务后端的确定性规则判定。"
        ),
        "char_count": 128,
    },
    {
        "chunk_id": "HTN001-0002",
        "document_id": "HTN001",
        "title": "【测试夹具】高血压基层管理测试文档",
        "authority": "CareFlow Test Fixture",
        "authority_level": "P0",
        "version": "2025",
        "effective_date": "2025-06-01",
        "diseases": ["HYPERTENSION"],
        "scenarios": ["education"],
        "section": "二、生活方式干预",
        "section_path": ["二、生活方式干预"],
        "source_url": "https://example.invalid/fixture/htn001",
        "content": (
            "生活方式干预是高血压管理的基础措施，包括减少钠盐摄入、合理膳食、"
            "控制体重、戒烟限酒、规律运动与心理平衡。减少钠盐摄入可通过使用定量盐勺、"
            "减少腌制食品与加工食品摄入来实现。上述建议属于健康教育内容，"
            "具体治疗方案应由医生决定。"
        ),
        "char_count": 118,
    },
    {
        "chunk_id": "DM001-0001",
        "document_id": "DM001",
        "title": "【测试夹具】糖尿病基层管理测试文档",
        "authority": "CareFlow Test Fixture",
        "authority_level": "P1",
        "version": "2024",
        "effective_date": "2024-07-01",
        "diseases": ["DIABETES"],
        "scenarios": ["followup", "education"],
        "section": "三、血糖监测",
        "section_path": ["三、血糖监测"],
        "source_url": "https://example.invalid/fixture/dm001",
        "content": (
            "基层糖尿病患者的随访应关注血糖监测记录，包括空腹血糖、餐后血糖"
            "与糖化血红蛋白的检测结果。记录时应注明测量时间与进食情况，"
            "以便业务后端的规则引擎进行趋势判定。健康教育可围绕规律进餐、"
            "主食定量、增加膳食纤维摄入等方面开展。"
        ),
        "char_count": 112,
    },
    {
        "chunk_id": "LIFE001-0001",
        "document_id": "LIFE001",
        "title": "【测试夹具】慢性病食养测试文档",
        "authority": "CareFlow Test Fixture",
        "authority_level": "P3",
        "version": "2024",
        "effective_date": "2024-03-01",
        "diseases": ["HYPERTENSION", "OBESITY"],
        "scenarios": ["education", "lifestyle"],
        "section": "一、食养原则",
        "section_path": ["一、食养原则"],
        "source_url": "https://example.invalid/fixture/life001",
        "content": (
            "食养指导强调食物多样、谷类为主，多吃蔬菜水果与奶类大豆，"
            "适量吃鱼禽蛋瘦肉，少盐少油控糖限酒。食盐摄入应减少，"
            "同时注意隐性盐来源。体重管理应长期坚持，避免极端节食。"
        ),
        "char_count": 82,
    },
    {
        "chunk_id": "COPD900-0001",
        "document_id": "COPD900",
        "title": "【测试夹具】已停用文档（不得进入检索）",
        "authority": "CareFlow Test Fixture",
        "authority_level": "P2",
        "version": "2019",
        "effective_date": "2019-02-01",
        "diseases": ["COPD"],
        "scenarios": ["followup"],
        "section": "作废章节",
        "section_path": ["作废章节"],
        "source_url": "https://example.invalid/fixture/copd900",
        "content": "这是已作废文档的切片，任何检索都不应该返回它。慢阻肺 随访 血压 血糖 食盐 饮食 运动。",
        "char_count": 48,
    },
]


@pytest.fixture
def knowledge_dir(tmp_path: Path) -> dict[str, Path]:
    """写入合成 manifest 与 chunks，返回路径。"""
    manifest_path = tmp_path / "knowledge_manifest.csv"
    chunks_path = tmp_path / "chunks.jsonl"

    with manifest_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(MANIFEST_COLUMNS))
        writer.writeheader()
        for row in FIXTURE_DOCUMENTS:
            writer.writerow({column: row.get(column, "") for column in MANIFEST_COLUMNS})

    with chunks_path.open("w", encoding="utf-8") as handle:
        for chunk in FIXTURE_CHUNKS:
            handle.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    return {"manifest": manifest_path, "chunks": chunks_path}


@pytest.fixture
def mock_env(knowledge_dir, monkeypatch, tmp_path):
    """把进程环境切到 mock provider + 合成知识库，并重置所有单例。"""
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    monkeypatch.setenv("MANIFEST_PATH", str(knowledge_dir["manifest"]))
    monkeypatch.setenv("CHUNKS_PATH", str(knowledge_dir["chunks"]))
    monkeypatch.setenv("RAG_TOP_K", "5")
    monkeypatch.setenv("MAX_RETRIES", "1")
    # 合成夹具只有 4 个短切片，BM25 分值远低于真实语料；
    # 相关性闸门是**按真实语料标定**的部署参数，单元测试里显式关闭它，
    # 闸门本身的行为由 tests/test_retrieval.py 的专门用例覆盖。
    monkeypatch.setenv("RAG_MIN_MATCHED_TERMS", "1")
    monkeypatch.setenv("RAG_MIN_RELEVANCE_SCORE", "0")
    reload_settings()
    deps.reset_services()
    yield knowledge_dir
    deps.reset_services()
    reload_settings()


@pytest.fixture
def empty_env(tmp_path, monkeypatch):
    """知识库缺失的环境（用于 health=degraded、no-evidence 测试）。"""
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.setenv("MANIFEST_PATH", str(tmp_path / "missing_manifest.csv"))
    monkeypatch.setenv("CHUNKS_PATH", str(tmp_path / "missing_chunks.jsonl"))
    reload_settings()
    deps.reset_services()
    yield
    deps.reset_services()
    reload_settings()


@pytest.fixture
def services(mock_env):
    """直接构造服务容器（不经过 HTTP）。"""
    reload_settings()
    deps.reset_services()
    return deps.build_services()


@pytest.fixture
def client(mock_env):
    """FastAPI TestClient（mock provider + 合成知识库）。"""
    from fastapi.testclient import TestClient

    from app.main import create_app

    application = create_app()
    with TestClient(application) as test_client:
        yield test_client


@pytest.fixture
def empty_client(empty_env):
    from fastapi.testclient import TestClient

    from app.main import create_app

    application = create_app()
    with TestClient(application) as test_client:
        yield test_client
