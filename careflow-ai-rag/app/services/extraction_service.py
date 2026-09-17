"""结构化提取服务。

两条路径：

* **确定性规则提取**（始终执行）：正则 + 受控词表，负责数值类生命体征、
  症状、生活方式、用药的提取，并对否定句做过滤；
* **LLM 提取**（`AI_PROVIDER=qianfan` 时）：负责自由文本里的语义补全。

两者结果做**并集去重**；LLM 结果还必须通过 **grounding 校验**
（`source_text` 必须能在患者原文中逐字找到），否则丢弃并记录 ——
这是防止"编造体征"的关键闸门。
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.clients.base import LLMClient
from app.core.config import Settings, load_settings
from app.core.errors import CareFlowError
from app.core.json_utils import (
    JSONParseError,
    ensure_object,
    fold_fullwidth,
    normalize_whitespace,
)
from app.core.logging_config import get_logger, log_event
from app.prompts import load_prompt, prompt_version
from app.schemas.common import ModelMeta, PatientContext, SafetyReport
from app.schemas.extraction import ExtractionData, ExtractionOptions, Observation, ObservationType
from app.services.safety_service import SafetyService

logger = get_logger("services.extraction")

NEGATION_MARKERS = ("没", "无", "不", "未", "否认", "从来没有", "并未", "没有")
NEGATION_WINDOW = 4

SYMPTOM_KEYWORDS: dict[str, str] = {
    "头晕": "头晕",
    "头昏": "头晕",
    "头痛": "头痛",
    "胸闷": "胸闷",
    "胸痛": "胸痛",
    "气短": "气短",
    "气促": "气促",
    "气喘": "气促",
    "呼吸困难": "呼吸困难",
    "喘不上气": "呼吸困难",
    "咳嗽": "咳嗽",
    "咳痰": "咳痰",
    "咳血": "咳血",
    "心慌": "心悸",
    "心悸": "心悸",
    "乏力": "乏力",
    "无力": "乏力",
    "水肿": "水肿",
    "浮肿": "水肿",
    "恶心": "恶心",
    "呕吐": "呕吐",
    "视物模糊": "视力模糊",
    "视力模糊": "视力模糊",
    "手脚麻木": "肢体麻木",
    "肢体麻木": "肢体麻木",
    "麻木": "肢体麻木",
    "多饮": "多饮",
    "多尿": "多尿",
    "口干": "口干",
    "盗汗": "盗汗",
    "失眠": "失眠",
    "嗜睡": "嗜睡",
    "体重下降": "体重下降",
    "夜间憋醒": "夜间憋醒",
    "下肢水肿": "下肢水肿",
}

MEDICATION_SUFFIXES = (
    "地平", "洛尔", "普利", "沙坦", "噻嗪", "利尿", "唑嗪",
    "双胍", "列净", "列汀", "格列", "波糖", "胰岛素",
    "他汀", "贝特", "阿司匹林", "氯吡格雷", "华法林",
    "沙美特罗", "福莫特罗", "噻托溴铵", "布地奈德", "孟鲁司特", "氨茶碱",
    "别嘌醇", "非布司他", "碳酸氢钠", "骨化三醇", "碳酸钙",
)

MEDICATION_TAKE_VERB = r"(?:在吃|正在吃|服用|在服用|吃了|用着|在用|口服|打|注射|吃着)"

#: 剂型结尾的药名，例如「硝苯地平缓释片」
MEDICATION_FORM_RE = re.compile(
    MEDICATION_TAKE_VERB
    + r"\s*([A-Za-z\u4e00-\u9fff]{2,14}?(?:片|胶囊|缓释片|控释片|分散片|颗粒|注射液|吸入剂|喷雾剂|滴丸|丸|贴))"
    r"(\d+(?:\.\d+)?\s*(?:mg|毫克|g|克|μg|ug|IU|iu|片|粒|喷|单位))?"
)

#: 通用名后缀（地平/沙坦/双胍/列净…）——覆盖没有剂型后缀的口语写法
MEDICATION_GENERIC_RE = re.compile(
    MEDICATION_TAKE_VERB
    + r"\s*([A-Za-z\u4e00-\u9fff]{1,10}?(?:地平|洛尔|普利|沙坦|噻嗪|唑嗪|双胍|列净|列汀|格列|波糖|"
    r"他汀|贝特|阿司匹林|氯吡格雷|华法林|沙美特罗|福莫特罗|噻托溴铵|布地奈德|孟鲁司特|氨茶碱|"
    r"别嘌醇|非布司他|胰岛素))"
    r"\s*(\d+(?:\.\d+)?\s*(?:mg|毫克|g|克|μg|ug|IU|iu|片|粒|喷|单位))?"
)

DOSE_TEXT_RE = re.compile(
    r"(\d+(?:\.\d+)?\s*(?:mg|毫克|g|克|μg|ug|IU|iu|片|粒|支|喷|单位))"
)
FREQ_TEXT_RE = re.compile(
    r"(每[天日]\s*[0-9一二三四五六七八九十]\s*次|一[天日]\s*[0-9一二三四五六七八九十]\s*次|"
    r"\d\s*次/日|bid|tid|qd|qn|每晚一次|早晨一次|睡前一次|按需|每[天日]|"
    r"每周\s*[0-9一二三四五六七八九十]\s*次)",
    re.IGNORECASE,
)

LIFESTYLE_PATTERNS: list[tuple[ObservationType, re.Pattern[str], str]] = [
    (
        ObservationType.SMOKING,
        re.compile(r"(?:吸烟|抽烟|烟龄)[^。；;，,\n]{0,20}?(?:每天|每日)?\s*(\d+(?:\.\d+)?)?\s*(支|根|包)?"),
        "",
    ),
    (ObservationType.ALCOHOL, re.compile(r"(?:饮酒|喝酒|喝白酒|喝啤酒)[^。；;，,\n]{0,20}"), ""),
    (ObservationType.EXERCISE, re.compile(r"(?:运动|散步|快走|慢跑|跑步|锻炼|做操|太极|广场舞|游泳)[^。；;，,\n]{0,24}"), ""),
    (ObservationType.DIET, re.compile(r"(?:饮食|忌口|口味|吃盐|食盐|低盐|淡食)[^。；;，,\n]{0,20}"), ""),
    (ObservationType.SLEEP, re.compile(r"(?:睡眠|睡了|入睡|失眠)[^。；;，,\n]{0,20}?(\d+(?:\.\d+)?)\s*(?:个)?\s*小时"), ""),
]

SLEEP_HOURS_RE = re.compile(r"(?:睡眠|睡了|入睡)[^。；;，,\n]{0,12}?(\d+(?:\.\d+)?)\s*(?:个)?\s*小时")

FOLLOWUP_EVENT_RE = re.compile(r"(复诊|随访|体检|门诊|住院|就诊|转到|转诊|预约)")

ADHERENCE_RE = re.compile(r"(漏服|忘记吃|忘记服|没按时|不规律服药|自行停药|断药|漏吃)")


# --------------------------------------------------------------------------- #
# 数值类规则
# --------------------------------------------------------------------------- #
def _negated(text: str, start: int) -> bool:
    window = text[max(0, start - NEGATION_WINDOW) : start]
    return any(marker in window for marker in NEGATION_MARKERS)


def _make(
    obs_type: ObservationType,
    value: dict[str, Any],
    unit: str,
    source: str,
    confidence: float,
    *,
    needs_confirmation: bool = False,
) -> Observation:
    return Observation(
        type=obs_type,
        value=value,
        unit=unit,
        confidence=confidence,
        source_text=source.strip(),
        needs_confirmation=needs_confirmation,
    )


def _extract_blood_pressure(folded: str, original: str) -> list[Observation]:
    """匹配用折叠文本，``source_text`` 用原文切片（两者下标一一对应）。"""
    text = folded
    observations: list[Observation] = []
    pair_re = re.compile(
        r"(?:血压|血压值|血压测量|测量血压|BP|bp)\s*[:：]?\s*(\d{2,3})\s*[/／]\s*(\d{2,3})"
    )
    split_re = re.compile(
        r"(?:收缩压|高压)\s*[:：]?\s*(\d{2,3})[^0-9]{0,6}(?:舒张压|低压)\s*[:：]?\s*(\d{2,3})"
    )
    for regex in (pair_re, split_re):
        for match in regex.finditer(text):
            systolic, diastolic = int(match.group(1)), int(match.group(2))
            if not (40 <= systolic <= 320 and 20 <= diastolic <= 200):
                continue
            observations.append(
                _make(
                    ObservationType.BLOOD_PRESSURE,
                    {"systolic": systolic, "diastolic": diastolic},
                    "mmHg",
                    original[match.start() : match.end()],
                    0.98,
                )
            )
    return observations


NUMERIC_RULES: list[tuple[ObservationType, re.Pattern[str], str, str, float]] = [
    (
        ObservationType.BLOOD_GLUCOSE,
        re.compile(
            r"(空腹血糖|餐后血糖|餐后2小时血糖|睡前血糖|随机血糖|血糖值|血糖)\s*[:：]?\s*(\d+(?:\.\d+)?)"
        ),
        "mmol/L",
        "value",
        0.95,
    ),
    (ObservationType.HBA1C, re.compile(r"(?:糖化血红蛋白|糖化|HbA1c|A1c|hba1c)\s*[:：]?\s*(\d+(?:\.\d+)?)\s*%?"), "%", "value", 0.95),
    (ObservationType.BLOOD_LIPID, re.compile(r"(?:总胆固醇|甘油三酯|低密度脂蛋白|高密度脂蛋白|LDL|HDL|TC|TG)\s*[:：]?\s*(\d+(?:\.\d+)?)"), "mmol/L", "value", 0.9),
    (ObservationType.URIC_ACID, re.compile(r"(?:血尿酸|尿酸)\s*[:：]?\s*(\d+(?:\.\d+)?)"), "μmol/L", "value", 0.9),
    (ObservationType.WEIGHT, re.compile(r"(?:体重)\s*[:：]?\s*(\d+(?:\.\d+)?)\s*(?:kg|公斤|千克|斤)?"), "kg", "value", 0.95),
    (ObservationType.HEIGHT, re.compile(r"(?:身高)\s*[:：]?\s*(\d+(?:\.\d+)?)\s*(?:cm|厘米|公分|米|m)?"), "cm", "value", 0.9),
    (ObservationType.BMI, re.compile(r"(?:BMI|体重指数)\s*[:：]?\s*(\d+(?:\.\d+)?)"), "", "value", 0.9),
    (ObservationType.WAIST, re.compile(r"(?:腰围)\s*[:：]?\s*(\d+(?:\.\d+)?)\s*(?:cm|厘米|公分)?"), "cm", "value", 0.9),
    (ObservationType.HEART_RATE, re.compile(r"(?:心率|脉搏)\s*[:：]?\s*(\d{2,3})"), "次/分", "value", 0.9),
    (ObservationType.BLOOD_OXYGEN, re.compile(r"(?:血氧饱和度|血氧|SpO2|spO2|氧饱和度)\s*[:：]?\s*(\d{2,3})\s*%?"), "%", "value", 0.9),
    (ObservationType.BODY_TEMPERATURE, re.compile(r"(?:体温)\s*[:：]?\s*((?:3\d|4[0-2])(?:\.\d+)?)"), "℃", "value", 0.9),
    (ObservationType.PEAK_FLOW, re.compile(r"(?:峰流速|PEF|呼气峰流速)\s*[:：]?\s*(\d{2,3})"), "L/min", "value", 0.85),
]


def rule_extract(text: str) -> list[Observation]:
    """确定性规则提取。

    匹配在**全角折叠后**的文本上进行（因此 ``ＢＰ１５８／９６``、``体温３６.８``
    这类中文输入法下的常见写法同样能正确提取），但 ``source_text`` **切片自用户原文**。

    之所以可以这样切：``fold_fullwidth`` 是严格 1:1 的字符替换（每个全角字符映射到
    恰好一个半角字符，U+3000 → 半角空格），折叠文本与原文**下标一一对应**，
    所以在折叠文本上得到的 ``[start, end)`` 直接拿去切原文即可。
    """
    if not text:
        return []
    original = text
    text = fold_fullwidth(text)

    def src(match: "re.Match[str]") -> str:
        """按匹配位置从**原文**取连续片段。"""
        return original[match.start() : match.end()]
    observations: list[Observation] = []
    observations.extend(_extract_blood_pressure(text, original))

    for obs_type, regex, unit, key, confidence in NUMERIC_RULES:
        for match in regex.finditer(text):
            if _negated(text, match.start()):
                continue
            groups = [group for group in match.groups() if group]
            raw_value = groups[-1] if groups else ""
            try:
                number = float(raw_value)
            except (TypeError, ValueError):
                continue
            if obs_type is ObservationType.BLOOD_GLUCOSE:
                context = "random"
                label = match.group(1)
                if "空腹" in label:
                    context = "fasting"
                elif "餐后" in label:
                    context = "postprandial"
                elif "睡前" in label:
                    context = "bedtime"
                value: dict[str, Any] = {"value": number, "context": context}
            else:
                value = {key: number}
            observations.append(
                _make(obs_type, value, unit, src(match), confidence)
            )

    # 症状（含否定过滤）
    for keyword, canonical in SYMPTOM_KEYWORDS.items():
        for match in re.finditer(re.escape(keyword), text):
            if _negated(text, match.start()):
                continue
            observations.append(
                _make(
                    ObservationType.SYMPTOM,
                    {"name": canonical, "present": True, "keyword": keyword},
                    "",
                    src(match),
                    0.8,
                    needs_confirmation=True,
                )
            )

    # 生活方式
    for obs_type, regex, unit in LIFESTYLE_PATTERNS:
        match = regex.search(text)
        if match is None or _negated(text, match.start()):
            continue
        snippet = src(match).strip()
        value: dict[str, Any] = {"description": snippet}
        if obs_type is ObservationType.SLEEP:
            hours = SLEEP_HOURS_RE.search(text)
            if hours:
                value["hours"] = float(hours.group(1))
        if obs_type is ObservationType.SMOKING:
            count = match.group(1) if match.groups() else None
            if count:
                try:
                    value["per_day"] = float(count)
                    value["unit"] = match.group(2) or "支"
                except ValueError:
                    pass
        observations.append(_make(obs_type, value, unit, snippet, 0.75, needs_confirmation=True))

    # 用药（只记录，不给建议）
    seen_medications: set[tuple[int, str]] = set()
    for regex in (MEDICATION_FORM_RE, MEDICATION_GENERIC_RE):
        for match in regex.finditer(text):
            name = (match.group(1) or "").strip()
            if not name:
                continue
            if any(match.start() >= start and match.start() < end for start, end in seen_medications):
                continue
            if regex is MEDICATION_FORM_RE and not any(
                suffix in name for suffix in MEDICATION_SUFFIXES
            ) and not name.endswith(("片", "胶囊", "颗粒", "丸", "吸入剂", "喷雾剂", "注射液", "滴丸", "贴")):
                continue
            window = text[match.start() : match.start() + 50]  # text 已是折叠文本
            dose = DOSE_TEXT_RE.search(window)
            freq = FREQ_TEXT_RE.search(window)
            value: dict[str, Any] = {"name": name}
            if dose:
                value["dose_text"] = dose.group(1).strip()
            elif match.lastindex and match.lastindex >= 2 and match.group(2):
                value["dose_text"] = match.group(2).strip()
            if freq:
                value["frequency_text"] = freq.group(1).strip()
            seen_medications.add((match.start(), match.end()))
            observations.append(
                _make(
                    ObservationType.MEDICATION,
                    value,
                    "",
                    src(match).strip(),
                    0.85,
                    needs_confirmation=True,
                )
            )

    # 随访事件 / 依从性
    event = FOLLOWUP_EVENT_RE.search(text)
    if event:
        observations.append(
            _make(
                ObservationType.FOLLOWUP_EVENT,
                {"event": event.group(1)},
                "",
                src(event),
                0.8,
                needs_confirmation=True,
            )
        )
    adherence = ADHERENCE_RE.search(text)
    if adherence:
        observations.append(
            _make(
                ObservationType.ADHERENCE,
                {"issue": adherence.group(1)},
                "",
                src(adherence),
                0.8,
                needs_confirmation=True,
            )
        )
    return observations


# --------------------------------------------------------------------------- #
# LLM 路径
# --------------------------------------------------------------------------- #
def build_user_message(text: str, patient_context: PatientContext | None) -> str:
    context_lines: list[str] = []
    if patient_context is not None:
        if patient_context.age_years is not None:
            context_lines.append(f"年龄：{patient_context.age_years} 岁")
        if patient_context.sex:
            context_lines.append(f"性别：{patient_context.sex}")
        if patient_context.known_conditions:
            context_lines.append(f"已知疾病：{'、'.join(patient_context.known_conditions)}")
    header = ""
    if context_lines:
        header = "【患者背景】（仅供参考，不得据此推断未出现的数据）\n" + "\n".join(context_lines) + "\n\n"
    return f"{header}【健康记录原文】\n{text}"


def _coerce_observations(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("observations")
    if raw is None:
        raw = payload.get("data", {}).get("observations") if isinstance(payload.get("data"), dict) else []
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _to_observation(item: dict[str, Any]) -> Observation | None:
    raw_type = str(item.get("type") or "").strip().upper()
    if raw_type not in ObservationType.__members__:
        return None
    payload = dict(item)
    payload["type"] = raw_type
    try:
        return Observation.model_validate(payload)
    except Exception:  # noqa: BLE001 - 单条非法不应影响整批
        return None


def is_grounded(observation: Observation, source_text: str) -> bool:
    """校验 `source_text` 是否来自患者原文（防编造）。"""
    fragment = observation.source_text
    if not fragment or not fragment.strip():
        return False
    haystack = normalize_whitespace(source_text)
    needle = normalize_whitespace(fragment)
    if not needle:
        return False
    return needle in haystack


class ExtractionService:
    """结构化提取编排。"""

    def __init__(
        self,
        client: LLMClient | None = None,
        *,
        settings: Settings | None = None,
        safety: SafetyService | None = None,
    ) -> None:
        self.settings = settings or load_settings()
        self.client = client
        self.safety = safety or SafetyService()
        self.use_llm = self.settings.is_qianfan and client is not None

    def _merge(self, rule_obs: list[Observation], llm_obs: list[Observation], text: str) -> tuple[list[Observation], list[dict[str, Any]]]:
        merged: list[Observation] = list(rule_obs)
        seen: set[tuple[str, str]] = {(item.type.value, item.source_text) for item in rule_obs}
        dropped: list[dict[str, Any]] = []
        for observation in llm_obs:
            if not is_grounded(observation, text):
                dropped.append(
                    {
                        "reason": "ungrounded_source_text",
                        "type": observation.type.value,
                        "source_text": observation.source_text[:60],
                    }
                )
                continue
            key = (observation.type.value, observation.source_text)
            if key in seen:
                continue
            seen.add(key)
            merged.append(observation)
        return merged, dropped

    async def extract(
        self,
        text: str,
        *,
        patient_context: PatientContext | None = None,
        options: ExtractionOptions | None = None,
        request_id: str = "",
    ) -> ExtractionData:
        options = options or ExtractionOptions()
        decision = self.safety.check_query(text, operation="extract")
        decision.enforce()

        rule_obs = rule_extract(text)
        observations = list(rule_obs)
        model_meta = ModelMeta(
            provider=self.settings.ai_provider,
            model="rule-engine",
            prompt_version=prompt_version("extraction_system"),
        )
        dropped: list[dict[str, Any]] = []
        notes: list[str] = []
        degraded = False

        if self.use_llm and self.client is not None:
            try:
                response = await self.client.chat(
                    [
                        {"role": "system", "content": load_prompt("extraction_system")},
                        {"role": "user", "content": build_user_message(text, patient_context)},
                    ],
                    task="extract",
                    temperature=0.0,
                    max_tokens=2000,
                    response_format={"type": "json_object"},
                )
                payload = ensure_object(response.text)
                llm_obs: list[Observation] = []
                for item in _coerce_observations(payload):
                    parsed = _to_observation(item)
                    if parsed is None:
                        dropped.append({"reason": "invalid_type_or_schema", "raw": str(item)[:120]})
                        continue
                    llm_obs.append(parsed)
                merged, ungrounded = self._merge(rule_obs, llm_obs, text)
                observations = merged
                dropped.extend(ungrounded)
                model_meta = ModelMeta(
                    provider=response.provider,
                    model=response.model,
                    latency_ms=response.latency_ms,
                    attempts=response.attempts,
                    prompt_version=prompt_version("extraction_system"),
                    usage=response.usage,
                )
            except JSONParseError as exc:
                degraded = True
                notes.append(f"LLM 返回非法 JSON，已降级为规则提取：{exc}")
                log_event(
                    logger,
                    "extraction json parse failed",
                    operation="extract",
                    provider="qianfan",
                    success=False,
                    error_code="LLM_INVALID_JSON",
                )
            except CareFlowError as exc:
                degraded = True
                notes.append(f"LLM 调用失败，已降级为规则提取：{exc.code.value}")
                log_event(
                    logger,
                    "extraction llm failed",
                    operation="extract",
                    provider=exc.code.value,
                    success=False,
                    error_code=exc.code.value,
                )
            except Exception as exc:  # noqa: BLE001
                degraded = True
                notes.append(f"LLM 异常，已降级为规则提取：{type(exc).__name__}")

        observations = observations[: options.max_observations]
        # source_text 切片自原文，因此 unmatched 也用原文
        unmatched = self._unmatched_text(text, observations)

        report = SafetyReport(
            flags=list(decision.report.flags),
            advice_seeking=decision.report.advice_seeking,
            requires_human_confirmation=True,
        )
        data = ExtractionData(
            observations=observations,
            unmatched_text=unmatched,
            observation_types=sorted({item.type.value for item in observations}),
            needs_patient_confirmation=True,
            safety=report,
            model=model_meta,
        )
        if degraded:
            notes.append("degraded=true：LLM 不可用，结果来自确定性规则引擎")
        log_event(
            logger,
            "extraction done",
            operation="extract",
            provider=model_meta.provider,
            model=model_meta.model,
            latency_ms=model_meta.latency_ms,
            success=True,
            observations=len(observations),
            dropped=len(dropped),
            degraded=degraded,
        )
        data.__dict__["_dropped"] = dropped
        data.__dict__["_notes"] = notes
        data.__dict__["_degraded"] = degraded
        return data

    @staticmethod
    def _unmatched_text(text: str, observations: list[Observation]) -> str:
        """把没有被任何 observation 覆盖的原文片段返回（供患者确认）。"""
        if not observations:
            return text.strip()[:500]
        spans: list[tuple[int, int]] = []
        for observation in observations:
            fragment = observation.source_text
            if not fragment:
                continue
            start = text.find(fragment)
            if start >= 0:
                spans.append((start, start + len(fragment)))
        spans.sort()
        merged: list[list[int]] = []
        for start, end in spans:
            if merged and start <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])
        uncovered: list[str] = []
        cursor = 0
        for start, end in merged:
            if start > cursor:
                uncovered.append(text[cursor:start])
            cursor = max(cursor, end)
        if cursor < len(text):
            uncovered.append(text[cursor:])
        joined = " ".join(part.strip() for part in uncovered if part.strip())
        return joined[:500]


def dumps_observations(items: list[Observation]) -> str:
    """调试/测试辅助。"""
    return json.dumps([item.model_dump() for item in items], ensure_ascii=False)
