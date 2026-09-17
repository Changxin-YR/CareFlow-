"""真实语料下的检索行为回归测试（相关性闸门 / 跨语言覆盖率 / 拆分与日期）。

为什么单独一个文件：闸门阈值与覆盖率分母都是**按当前语料标定**的
（28 篇 active / 2448 个可检索切片）。合成夹具的分值尺度完全不同，
因此这里必须用**真实知识库**构造服务；产物不存在时整体 skip。

锁定 2026-09-17 第三轮补数据后发现的三个真实问题：
1. 补入 WHO 全文后，`WHO PEN 是什么？` 因为 who/pen 在 WHO 语料里 IDF 极低
   （页眉页脚到处都有）被打成 4.4 分，被 score>=12 的闸门拦死
   → 新增「查询词覆盖率」分支；
2. 极短查询下覆盖率会虚高（命中 1 个词就是 1.0），把无关查询放行
   → 覆盖率分支必须配 `matched >= 2`；
3. 中英混合查询（`WHO HEARTS 关于心血管风险管理怎么说的？`）的 8 个中文词
   在纯英文的 KB_WHO 子集里 df=0，永远不可能命中
   → 覆盖率分母改为「只在被检索子集内统计 df>0 的词」。
"""

from __future__ import annotations

import os

import pytest

from app.api import deps
from app.core.config import PROJECT_ROOT, reload_settings

MANIFEST = PROJECT_ROOT / "knowledge" / "manifest" / "knowledge_manifest.csv"
CHUNKS = PROJECT_ROOT / "knowledge" / "chunks" / "chunks.jsonl"

pytestmark = pytest.mark.skipif(
    not (MANIFEST.exists() and CHUNKS.exists()),
    reason="真实知识库产物不存在",
)


@pytest.fixture(scope="module")
def real_services():
    """用**真实知识库**构造服务（不经过合成夹具）。"""
    os.environ["AI_PROVIDER"] = "mock"
    os.environ["APP_ENV"] = "test"
    # 关键：清掉夹具注入的路径覆盖，让配置回落到 knowledge/ 真实产物
    os.environ.pop("MANIFEST_PATH", None)
    os.environ.pop("CHUNKS_PATH", None)
    reload_settings()
    deps.reset_services()
    services = deps.build_services()
    yield services
    deps.reset_services()
    reload_settings()


async def test_gate_keeps_acronym_query_against_full_who_text(real_services):
    """`WHO PEN 是什么？` 必须能命中 —— 这是补 WHO 全文的初衷。"""
    result = await real_services.retrieval.search("WHO PEN 是什么？", domains=["KB_WHO"])
    assert result.hits, "WHO 缩写查询被闸门拦死了"
    assert any(hit.document_id == "WHO001" for hit in result.hits)


async def test_gate_keeps_cross_language_query(real_services):
    """中英混合查询：中文词在英文子集里 df=0，不应计入覆盖率分母。"""
    result = await real_services.retrieval.search(
        "WHO HEARTS 关于心血管风险管理怎么说的？", domains=["KB_WHO"]
    )
    assert result.hits, "跨语言查询被闸门拦死了"
    assert {hit.document_id for hit in result.hits} & {"WHO002", "WHO003"}


@pytest.mark.parametrize(
    "query",
    [
        "今天天气怎么样，适合去钓鱼吗",
        "帮我写一首关于春天的诗",
        "苹果公司最新的财报怎么样",
        "明天股市会涨还是跌",
        "推荐一家附近的川菜馆",
        "怎么用 Python 写一个爬虫",
        "世界杯决赛什么时候开始",
        "量子纠缠的数学推导是什么",
        "汽车发动机怎么保养",
        "请解释一下区块链共识算法",
    ],
)
async def test_gate_blocks_unrelated_queries(real_services, query):
    """无关查询必须一条都不放行（无答案 > 编造答案）。"""
    result = await real_services.retrieval.search(query)
    assert result.is_empty, f"{query!r} 放行了 {[h.document_id for h in result.hits]}"


async def test_gate_keeps_short_but_fully_covered_query(real_services):
    result = await real_services.retrieval.search("家庭血压应该怎么测量")
    assert result.hits
    # HTN001（WS/T 872—2025 管理标准，P0）与 HTN002（国家基层高血压防治管理指南，P3）
    # 都是该问题的正确权威来源，不锁定具体某一篇
    assert result.hits[0].document_id in {"HTN001", "HTN002"}
    assert all(hit.document_id.startswith("HTN") or hit.document_id == "CORE005" for hit in result.hits)


async def test_draft_documents_never_retrieved(real_services):
    """6 篇 draft（付费墙 3 篇 + 内容不可用 3 篇）绝不能出现在检索结果里。"""
    draft_ids = {"DM002", "DM003", "MULTI001", "LIFE001A", "LIFE001B", "LIFE001C"}
    for query in ("糖尿病防治指南", "高血糖症营养指导", "三高共管", "血脂指南", "老年人健康管理"):
        result = await real_services.retrieval.search(query)
        leaked = {h.document_id for h in result.hits} & draft_ids
        assert not leaked, f"{query!r} 命中了 draft 文档 {leaked}"


def test_who_full_text_is_indexed(real_services):
    """WHO 三篇现在应是完整英文原文（不再是 1~2K 字符的摘要页）。"""
    who_chunks = [
        chunk
        for chunk in real_services.store.chunks
        if chunk.document_id in {"WHO001", "WHO002", "WHO003"}
    ]
    assert len(who_chunks) > 1000, f"WHO 切片只有 {len(who_chunks)} 个，疑似仍是摘要页"
    total = sum(chunk.char_count for chunk in who_chunks)
    assert total > 500_000, f"WHO 正文合计只有 {total} 字符"


def test_split_documents_are_registered(real_services):
    """LIFE001 拆成 4 份、LIFE008 拆成 2 份，都要在 manifest 里。"""
    entries = real_services.store.entries
    for doc_id in ("LIFE001", "LIFE001A", "LIFE001B", "LIFE001C", "LIFE008", "LIFE008A"):
        assert doc_id in entries, f"{doc_id} 未登记"
    assert entries["LIFE001A"].is_active is False, "内容不可用的扫描件应为 draft"
    assert entries["LIFE008A"].is_active is True, "释义文本层可用，应为 active"


def test_manifest_dates_filled(real_services):
    """本轮补的 7 个 publish_date 必须落地；effective_date 不得用 publish_date 冒充。"""
    entries = real_services.store.entries
    expected = {
        "HTN002": "2025-09-24",
        "DM002": "2021-04-27",
        "DM003": "2022-03-01",
        "MULTI001": "2023-07-24",
        "WHO001": "2020-09-07",
        "WHO002": "2020-07-13",
        "WHO003": "2018-05-02",
    }
    for doc_id, date in expected.items():
        assert entries[doc_id].publish_date == date, doc_id
        assert entries[doc_id].effective_date == "", f"{doc_id} 的 effective_date 不该有值"
    assert entries["PRIM003"].effective_date == "2016-04-01"
    assert entries["HTN001"].effective_date == "2026-03-01"


def test_no_publish_date_was_used_as_effective_date(real_services):
    """全局不变量：effective_date 若等于 publish_date，说明有冒充嫌疑。"""
    offenders = [
        entry.document_id
        for entry in real_services.store.entries.values()
        if entry.effective_date and entry.effective_date == entry.publish_date
    ]
    assert not offenders, f"以下文档的 effective_date 与 publish_date 相同，疑似冒充：{offenders}"
