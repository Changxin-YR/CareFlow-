"""Domain Router 单元测试（确定性 + LLM 补充）。"""

from __future__ import annotations

import json

import pytest

from app.clients.mock import MockLLMClient
from app.core.errors import QianfanTimeoutError
from app.services.routing_service import RoutingService, normalize_query


@pytest.fixture
def router():
    return RoutingService(None, enable_llm=False)


# --------------------------------------------------------------------------- #
# 归一化
# --------------------------------------------------------------------------- #
def test_normalize_query_fullwidth():
    assert normalize_query("血压１５８／９６") == "血压158/96"
    assert normalize_query("　高血压　") == "高血压"


# --------------------------------------------------------------------------- #
# 确定性路由
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("高血压患者家庭血压怎么测量？", "KB_HTN"),
        ("空腹血糖7.2应该注意什么", "KB_DM"),
        ("慢阻肺患者气促怎么办", "KB_COPD"),
        ("三高共管需要注意什么", "KB_MULTIMORBIDITY"),
        ("每天吃多少盐比较合适", "KB_LIFESTYLE"),
        ("家庭医生签约服务包含哪些内容", "KB_PRIMARYCARE"),
        ("中国公民健康素养包括哪些", "KB_CORE"),
        ("WHO HEARTS 是什么", "KB_WHO"),
    ],
)
def test_deterministic_single_domain(router, query, expected):
    result = router.deterministic(query)
    assert expected in result.domains, f"{query} -> {result.domains}"


def test_multi_domain_for_comorbidity(router):
    result = router.deterministic("高血压合并糖尿病患者的随访要点")
    assert "KB_HTN" in result.domains
    assert "KB_DM" in result.domains


def test_multi_domain_hypertension_diabetes_lipid(router):
    result = router.deterministic("高血压、糖尿病、血脂异常患者怎么综合管理")
    assert {"KB_HTN", "KB_DM", "KB_MULTIMORBIDITY"} <= set(result.domains)


def test_lifestyle_plus_disease(router):
    result = router.deterministic("高血压患者每天吃盐多少合适")
    assert "KB_HTN" in result.domains
    assert "KB_LIFESTYLE" in result.domains


def test_no_match_returns_empty(router):
    result = router.deterministic("今天天气怎么样")
    assert result.domains == []
    assert result.method == "deterministic"


def test_explicit_domains_win(router):
    result = router.deterministic("高血压", explicit=["KB_WHO"])
    assert result.domains == ["KB_WHO"]
    assert result.method == "explicit"


def test_explicit_domains_ignores_unknown(router):
    result = router.deterministic("高血压", explicit=["KB_NOPE", "KB_DM"])
    assert result.domains == ["KB_DM"]


def test_max_three_domains(router):
    query = "高血压 糖尿病 慢阻肺 血脂 饮食 运动 家庭医生 健康素养"
    result = router.deterministic(query)
    assert len(result.domains) <= 3


def test_ascii_keyword_boundaries(router):
    assert "KB_HTN" in router.deterministic("hypertension follow up").domains
    # 子串不应误命中
    assert "KB_WHO" not in router.deterministic("whole grain diet").domains


# --------------------------------------------------------------------------- #
# LLM 补充
# --------------------------------------------------------------------------- #
async def test_llm_router_used_when_no_match():
    client = MockLLMClient(handler=lambda task, messages: json.dumps({"domains": ["KB_DM"], "reason": "x"}))
    router = RoutingService(client, enable_llm=True)
    result = await router.route("那个测出来 8.5 要紧吗")
    assert result.domains == ["KB_DM"]
    assert result.llm_used is True
    assert client.calls[0]["task"] == "route"


async def test_llm_router_cannot_drop_deterministic_hits():
    client = MockLLMClient(handler=lambda task, messages: json.dumps({"domains": ["KB_WHO"]}))
    router = RoutingService(client, enable_llm=True)
    # 单域 + 长问句 → 触发 LLM 补充；确定性命中的 KB_HTN 必须保留
    result = await router.route("高血压患者在家里自己测量血压的时候需要注意哪些具体操作细节")
    assert "KB_HTN" in result.domains
    assert "KB_WHO" in result.domains  # LLM 只做新增
    assert result.llm_used is True


async def test_llm_router_only_adds_whitelisted_domains():
    client = MockLLMClient(handler=lambda task, messages: json.dumps({"domains": ["KB_HACK", "DM"]}))
    router = RoutingService(client, enable_llm=True)
    result = await router.route("今天天气怎么样")
    assert result.domains in ([], ["KB_DM"])
    assert "KB_HACK" not in result.domains


async def test_llm_router_invalid_json_falls_back():
    client = MockLLMClient(handler=lambda task, messages: "抱歉，我无法分类")
    router = RoutingService(client, enable_llm=True)
    result = await router.route("今天天气怎么样")
    assert result.domains == []


async def test_llm_router_error_is_non_fatal():
    client = MockLLMClient(responses=[QianfanTimeoutError("超时")])
    router = RoutingService(client, enable_llm=True)
    result = await router.route("今天天气怎么样")
    assert result.domains == []
    assert "QIANFAN_TIMEOUT" in result.llm_error


async def test_llm_router_disabled_by_settings():
    client = MockLLMClient(handler=lambda task, messages: json.dumps({"domains": ["KB_DM"]}))
    router = RoutingService(client, enable_llm=False)
    result = await router.route("今天天气怎么样")
    assert result.domains == []
    assert client.calls == []
