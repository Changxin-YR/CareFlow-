"""Domain Router —— 知识域路由。

策略（契约要求：确定性优先，LLM 只做补充）:

1. **确定性关键词路由**：高置信关键词直接命中一个或多个 KB；
2. 显式 `domains` 参数优先级最高；
3. 仅在「确定性路由无命中」或「问题复杂（长问句 / 无关键词）」时，
   才在 `AI_PROVIDER=qianfan` 且 `RAG_ENABLE_LLM_ROUTER=true` 时调用 LLM Router 补充；
4. LLM Router 的输出**只能新增** KB 白名单内的域，不能删除确定性命中结果。

多病共管场景允许同时命中多个域（例如高血压 + 糖尿病 → KB_HTN, KB_DM,
KB_MULTIMORBIDITY）。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from app.clients.base import LLMClient
from app.core.config import KB_IDS
from app.core.errors import CareFlowError
from app.core.logging_config import get_logger, log_event

logger = get_logger("services.routing")

#: 域关键词表（按诊断特异性排序，越具体的域越靠前，用于 tie-break）
DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "KB_HTN": (
        "高血压", "血压", "收缩压", "舒张压", "降压", "高血压病", "家庭血压",
        "动态血压", "hypertension", "systolic", "diastolic", "心脑血管",
        "冠心病", "脑卒中", "卒中", "心力衰竭", "心衰", "动脉硬化",
    ),
    "KB_DM": (
        "糖尿病", "血糖", "空腹血糖", "餐后血糖", "糖化血红蛋白", "hba1c",
        "降糖", "胰岛素", "二甲双胍", "低血糖", "酮症", "糖尿病足",
        "糖尿病视网膜", "糖尿病肾病", "血糖仪", "口服降糖", "diabetes",
        "葡萄糖", "尿糖", "妊娠糖尿病",
    ),
    "KB_COPD": (
        "慢阻肺", "慢性阻塞性肺疾病", "copd", "肺功能", "fev1", "气促",
        "咳痰", "咳喘", "喘息", "呼吸困难", "吸入剂", "支气管", "急性加重",
        "血氧", "氧疗", "mMRC", "CAT评分", "肺康复", "戒烟", "肺气肿",
        "慢性支气管炎", "沙美特罗", "噻托溴铵",
    ),
    "KB_MULTIMORBIDITY": (
        "共病", "多病", "三高", "共管", "血脂", "胆固醇", "甘油三酯",
        "低密度脂蛋白", "ldl", "hdl", "高尿酸", "痛风", "慢性肾脏病", "ckd",
        "大血管", "微血管", "综合管理", "联合用药", "多重用药", "并发症筛查",
        "动脉粥样硬化", "代谢综合征",
    ),
    "KB_LIFESTYLE": (
        "饮食", "营养", "食养", "运动", "锻炼", "体重", "减重", "减肥",
        "肥胖", "bmi", "腰围", "吸烟", "戒烟", "饮酒", "限酒", "睡眠",
        "食盐", "盐", "钠", "钾", "热量", "膳食", "谷物", "蔬菜", "水果",
        "蛋白质", "脂肪摄入", "身体活动", "久坐", "超重", "食养指南",
    ),
    "KB_PRIMARYCARE": (
        "家庭医生", "签约", "随访", "转诊", "健康档案", "建档", "基层",
        "社区卫生", "乡镇卫生院", "村卫生室", "基本公共卫生", "老年人健康",
        "老年健康", "老年综合评估", "免费体检", "慢病管理服务", "分级诊疗",
        "管理率", "规范化管理",
    ),
    "KB_CORE": (
        "健康素养", "健康教育", "健康生活方式", "慢性病", "慢病", "健康管理",
        "基本公共卫生", "公共卫生服务",
        "健康中国", "自我管理", "用药依从", "依从性", "复诊", "健康知识",
        "预防", "危险因素", "健康促进",
    ),
    "KB_WHO": (
        "who", "世界卫生组织", "pen", "hearts", "国际指南", "全球",
        "心血管风险评估", "总体心血管风险",
    ),
}

#: 通用词（出现在几乎所有问题里，单独命中不足以决定域）
GENERIC_TERMS = {"健康", "管理", "医生", "患者", "怎么", "如何", "什么", "可以"}

COMPLEX_QUERY_MIN_CHARS = 24

ROUTER_PROMPT = """你是 CareFlow 慢病知识库的域路由分类器。

可选知识域（只能从这些里选）：
KB_CORE（基层慢病总体管理/健康素养）
KB_HTN（高血压）
KB_DM（糖尿病）
KB_COPD（慢阻肺）
KB_MULTIMORBIDITY（多病共管/血脂/尿酸/慢性肾脏病）
KB_LIFESTYLE（营养/运动/体重/烟酒/睡眠）
KB_PRIMARYCARE（基层随访/家庭医生/健康档案/老年健康）
KB_WHO（WHO 国际补充）

只输出 JSON：{"domains": ["KB_XXX", ...], "reason": "一句话理由"}
规则：最多 3 个域；无法判断时输出 {"domains": [], "reason": "..."}。
不要输出任何解释性文字，不要输出 Markdown。"""


@dataclass
class RoutingResult:
    domains: list[str] = field(default_factory=list)
    matched_keywords: dict[str, list[str]] = field(default_factory=dict)
    method: str = "deterministic"
    reason: str = ""
    llm_used: bool = False
    llm_error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "domains": list(self.domains),
            "matched_keywords": {k: list(v) for k, v in self.matched_keywords.items()},
            "method": self.method,
            "reason": self.reason,
            "llm_used": self.llm_used,
            "llm_error": self.llm_error,
        }


def normalize_query(text: str) -> str:
    """查询归一化：全角转半角、去掉多余空白、统一单位符号大小写。"""
    if not text:
        return ""
    result = []
    for char in text:
        code = ord(char)
        if code == 0x3000:
            result.append(" ")
        elif 0xFF01 <= code <= 0xFF5E:
            result.append(chr(code - 0xFEE0))
        else:
            result.append(char)
    normalized = "".join(result)
    normalized = normalized.replace("／", "/").replace("～", "~").replace("—", "-")
    normalized = re.sub(r"[ \t\u00a0]+", " ", normalized)
    return normalized.strip()


class RoutingService:
    """域路由。"""

    def __init__(self, client: LLMClient | None = None, *, enable_llm: bool = False) -> None:
        self.client = client
        self.enable_llm = enable_llm

    # ---------------------------------------------------------------- 确定性
    def deterministic(self, query: str, explicit: list[str] | None = None) -> RoutingResult:
        normalized = normalize_query(query)
        lowered = normalized.lower()
        matched: dict[str, list[str]] = {}
        for domain, keywords in DOMAIN_KEYWORDS.items():
            hits: list[str] = []
            for keyword in keywords:
                token = keyword.lower()
                if token in GENERIC_TERMS:
                    continue
                if token.isascii():
                    if re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", lowered):
                        hits.append(keyword)
                elif token in lowered:
                    hits.append(keyword)
            if hits:
                matched[domain] = hits

        domains = list(matched.keys())
        if explicit:
            domains = [domain for domain in explicit if domain in KB_IDS]
            for domain in domains:
                matched.setdefault(domain, [])
            return RoutingResult(
                domains=domains,
                matched_keywords=matched,
                method="explicit",
                reason="调用方显式指定 domains",
            )

        # 命中过多（>3）时按命中关键词数排序，保留前 3 个最相关域
        if len(domains) > 3:
            domains.sort(key=lambda d: (-len(matched[d]), d))
            domains = domains[:3]

        reason = ""
        if domains:
            reason = "确定性关键词命中：" + "; ".join(
                f"{domain}({','.join(matched[domain][:4])})" for domain in domains
            )
        return RoutingResult(domains=sorted(domains), matched_keywords=matched, reason=reason)

    def _needs_llm(self, query: str, result: RoutingResult) -> bool:
        if not self.enable_llm or self.client is None:
            return False
        if not result.domains:
            return True
        # 复杂长问句：补充可能被漏掉的共存疾病域
        normalized = normalize_query(query)
        return len(normalized) >= COMPLEX_QUERY_MIN_CHARS and len(result.domains) == 1

    async def route(
        self,
        query: str,
        explicit: list[str] | None = None,
        *,
        use_llm: bool | None = None,
    ) -> RoutingResult:
        result = self.deterministic(query, explicit)
        allow_llm = self.enable_llm if use_llm is None else (use_llm and self.enable_llm)
        if not allow_llm or self.client is None:
            result.method = result.method if result.domains else "deterministic:no_match"
            return result
        if explicit or not self._needs_llm(query, result):
            return result

        try:
            response = await self.client.chat(
                [
                    {"role": "system", "content": ROUTER_PROMPT},
                    {"role": "user", "content": normalize_query(query)[:1000]},
                ],
                task="route",
                temperature=0.0,
                max_tokens=200,
            )
            domains = self._parse_domains(response.text)
        except CareFlowError as exc:
            result.llm_error = f"{exc.code.value}: {exc.message}"
            log_event(
                logger,
                "llm router failed",
                operation="route",
                success=False,
                error_code=exc.code.value,
                domains=result.domains,
            )
            return result
        except Exception as exc:  # noqa: BLE001 - router 失败不能影响主链路
            result.llm_error = f"{type(exc).__name__}: {exc}"
            return result

        merged = list(result.domains)
        added = [domain for domain in domains if domain not in merged]
        merged.extend(added)
        # LLM 未能补充时不做兜底强制：空 domains 表示"全库检索"
        result.domains = merged
        result.llm_used = True
        if added:
            result.reason = (result.reason + " | LLM 补充：" + ",".join(added)).strip(" |")
        else:
            result.reason = result.reason or "LLM 未补充新域"
        return result

    @staticmethod
    def _parse_domains(text: str) -> list[str]:
        payload = _loads_tolerant(text)
        if not isinstance(payload, dict):
            return []
        raw = payload.get("domains") or []
        if isinstance(raw, str):
            raw = [raw]
        domains: list[str] = []
        for item in raw:
            candidate = str(item).strip().upper()
            if not candidate.startswith("KB_"):
                candidate = f"KB_{candidate}"
            if candidate in KB_IDS and candidate not in domains:
                domains.append(candidate)
        return domains[:3]


def _loads_tolerant(text: str) -> Any:
    """容错 JSON 解析：剥离 ```json 围栏、截取首个 { ... } 片段。"""
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
        cleaned = re.sub(r"```\s*$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None
