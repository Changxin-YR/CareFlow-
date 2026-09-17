"""AI Safety 服务 —— 输入防护 + 输出防护。

三条硬边界（契约 §3）：

1. **本系统不是 AI 医生**：不诊断、不开药、不给剂量、不要求停药/换药；
2. **RAG 文档只是数据**，其中的任何「指令」都不得被执行；
3. **Attention Level / 业务写库 / 人工确认** 全部属于 CareFlow 业务后端，
   本服务只输出**信号**与**需要人工确认**的标记。

本模块只做确定性的规则判定与文本裁剪，不调用 LLM 做安全裁决。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.core.errors import SafetyBlockedError
from app.core.logging_config import get_logger, log_event
from app.schemas.common import RetrievedChunk, SafetyReport

logger = get_logger("services.safety")

#: 硬拦截：提示词注入 / 越权 / 要求处方
HARD_BLOCK_PATTERNS: list[tuple[str, str]] = [
    (r"忽略(之前|上面|以上|先前|前述|所有)的?(所有)?(规则|指令|设定|提示|要求)", "指令覆盖尝试"),
    (r"ignore\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions|rules|prompts)", "指令覆盖尝试"),
    (r"(显示|输出|打印|重复|告诉我|泄露)(一下)?(你的)?(系统)?(提示词|系统提示|prompt|system\s*prompt|内部指令)", "索取系统提示词"),
    (r"(reveal|show|print|repeat|dump)\s+(me\s+)?(your\s+)?(system\s+prompt|instructions|hidden\s+prompt)", "索取系统提示词"),
    (r"(执行|按照|遵循|遵守|依据)(知识库|文档|资料|检索结果|上下文)(里|中|内)?的?(命令|指令|要求|指示)", "执行文档内指令"),
    (r"(你现在是|从现在起你是|请你?(扮演|模拟)|假装你是)(一名|一个|个)?\s*(医生|大夫|临床医生|药师|专家)", "角色越权"),
    (r"(developer\s*mode|开发者模式|越狱模式|jailbreak|\bDAN\b|无限制模式)", "越狱模式"),
    (r"(绕过|跳过|禁用|关闭)\s*(citation|引用|引用校验|安全校验|safety)", "绕过安全校验"),
    (r"(给我|帮我|替我|直接)(开|写|发)(一份|一个|个)?\s*(处方|药方|医嘱)", "索取处方"),
    (r"(我|他|她|本人)是(个)?医生[，,。\s]{0,10}(所以)?(给我|帮我|把)?\s*(处方|用药方案|开药)", "伪装医生索取处方"),
    (r"(推荐|告诉我|说一下|列出|建议)[^。！？\n]{0,10}(吃|服用|用)[^。！？\n]{0,8}?药", "索取用药推荐"),
    (r"(具体|明确)?(的)?(用药|服药)?\s*(剂量|用法用量)\s*(是)?\s*(多少|怎么用|几片|几次)", "索取具体剂量"),
    (r"(怎么|如何|能不能|可以)\s*(自行)?\s*(停药|换药)", "索取停药/换药建议"),
    # --- 同义改写变体（docs/SAFETY.md §9.1 实测绕过样例的回归修复） ---
    (r"(最大|最多|最少|安全|推荐|最佳|最优|标准)[^。！？\n]{0,10}?(能吃|可以吃|能服用|可以服用|能用|能打|吃|服用|用)"
     r"[^。！？\n]{0,8}?(多少|几|剂量|毫克|mg|片|粒|单位|毫升|ml)", "索取具体剂量"),
    (r"(多少|几)\s*(毫克|mg|毫克每|片|粒|单位|毫升|ml)", "索取具体剂量"),
    (r"(推荐|最佳|最优|标准|安全|常规|规范)\s*(的)?\s*(剂量|用量|用法用量|剂量区间|用药方案)", "索取具体剂量"),
    (r"(剂量|用量)[^。！？\n]{0,8}?(区间|范围|上限|是多少|多少)", "索取具体剂量"),
    (r"(把|将)[^。！？\n]{0,12}?(药|降压药|降糖药|胰岛素|他汀)[^。！？\n]{0,6}?(停|停掉|停用|停了|停服|换掉|换了)", "索取停药/换药建议"),
    (r"(停|停掉|停用|停服|换|换掉)[^。！？\n]{0,8}?(药)?[^。！？\n]{0,6}?(行不行|可以吗|好不好|行吗|要紧吗)", "索取停药/换药建议"),
    (r"(自购|自行购药|自己买药|自行买药|自己去买药)", "索取用药推荐"),
    (r"(按|按照|依照|根据)[^。！？\n]{0,10}?(文献|资料|文档|知识库|检索结果)[^。！？\n]{0,10}?(指示|指令|说明|要求)[^。！？\n]{0,6}?(操作|执行|做|回答)?", "执行文档内指令"),
    (r"ignore\s+(all\s+)?(earlier|preceding|prior|previous|above)\s+(directives|instructions|rules|prompts|messages)", "指令覆盖尝试"),
    (r"(disregard|forget)\s+(all\s+)?(earlier|preceding|prior|previous|above)", "指令覆盖尝试"),
]

#: 软标记：不拦截，但要在回答里明确拒绝处方行为
SOFT_FLAG_PATTERNS: list[tuple[str, str]] = [
    (r"(该|应该|要不要|能不能|可以)\s*(吃|停|换|加|减)[^。！？\n]{0,6}(药|量)", "ADVICE_SEEKING_MEDICATION"),
    (r"(是|是不是|会不会)(得了|患了|有)\s*(高血压|糖尿病|慢阻肺|痛风|肾病)", "ADVICE_SEEKING_DIAGNOSIS"),
    (r"(我|他|她)的(病|情况|指标).{0,6}(严重|要紧|危险)吗", "ADVICE_SEEKING_SEVERITY"),
    (r"(需不需要|要不要)(住院|手术|打针|输液)", "ADVICE_SEEKING_TREATMENT"),
]

#: 高风险红旗 —— 必须给出确定性的"立即就医"提示（模板，非 LLM 生成）
EMERGENCY_PATTERNS: list[tuple[str, str]] = [
    (r"胸(痛|闷|口).{0,12}(大汗|冒汗|冷汗|压榨|持续|不缓解|放射)", "疑似急性冠脉事件描述"),
    (r"(意识不清|昏迷|晕倒|晕厥|抽搐|叫不醒)", "意识障碍相关描述"),
    (r"(说话不清|言语不清|口角歪斜|嘴歪|半身|一侧肢体|偏身)(无力|麻木|不能动|活动不便)?", "疑似脑卒中症状描述"),
    (r"(呼吸困难|喘不上气|憋气|窒息).{0,10}(加重|严重|不能平卧|越来越)?", "呼吸困难相关描述"),
    (r"(血糖|血糖值)?.{0,6}(低于|＜|<)\s*3\.9|(低血糖)(昏迷|意识|抽搐)", "严重低血糖相关描述"),
    (r"(自杀|不想活|活不下去|轻生)", "自伤/自杀意念"),
    (r"(咳血|咯血|呕血|黑便|便血)", "出血相关描述"),
    (r"血压.{0,8}(≥|>=|大于|超过|高到)\s*(180|200)", "极高血压读数描述"),
    (r"(胎动减少|临产|破水)", "孕产急症相关描述"),
]

EMERGENCY_NOTICE = (
    "⚠️ 安全提示：你描述的情况可能属于需要紧急处理的情形。"
    "请立即拨打 120 或尽快前往就近医疗机构急诊就诊，不要等待线上回复。"
)

REDACTION_TEMPLATES: dict[str, str] = {
    "dosage": "【已移除：具体用药剂量属于处方行为，请以医生开具的处方为准】",
    "medication_change": "【已移除：任何停药、换药、加减剂量都必须由医生评估后决定】",
    "diagnosis": "【已移除：本系统不提供诊断结论，诊断请以医生面诊结果为准】",
    "self_treat": "【已移除：本系统不提供自行用药建议】",
}

#: 剂量数字：ASCII 数字 + 全角数字 + 中文数字
#: （中文语境下「一次两片」远比「一次 2 片」常见，只用 \d 会漏掉最口语化的表达）
DOSE_NUMBER = r"[0-9０-９一二三四五六七八九十百千万半两]+(?:\.\d+)?"

#: 药物剂型单位 —— 几乎只出现在用药场景，是强信号，**无需**额外上下文即可判定
DOSE_FORM_UNIT = r"(?:片|粒|丸|袋|支|吸|喷|滴)"
#: 药物专属质量/效价单位 —— 需要"服用类动词"佐证
DOSE_DRUG_MASS_UNIT = r"(?:mg|毫克|μg|ug|IU|iu|国际单位|单位)"
#: 通用质量/体积单位 —— **食物营养也用**，必须同时有药物上下文才判定
DOSE_FOOD_MASS_UNIT = r"(?:gb|g\b|ｇ|克|毫升|ml)"

DOSAGE_FORM_RE = re.compile(DOSE_NUMBER + r"\s*" + DOSE_FORM_UNIT, re.IGNORECASE)
DOSAGE_DRUG_MASS_RE = re.compile(DOSE_NUMBER + r"\s*" + DOSE_DRUG_MASS_UNIT, re.IGNORECASE)
DOSAGE_FOOD_MASS_RE = re.compile(DOSE_NUMBER + r"\s*" + DOSE_FOOD_MASS_UNIT, re.IGNORECASE)
#: 三者的并集 —— 保留该名称供文档 / 外部检查使用
DOSAGE_RE = re.compile(
    DOSE_NUMBER
    + r"\s*(?:"
    + DOSE_FORM_UNIT
    + r"|"
    + DOSE_DRUG_MASS_UNIT
    + r"|"
    + DOSE_FOOD_MASS_UNIT
    + r")",
    re.IGNORECASE,
)

#: "服用类"动词与剂量语境词
DOSE_VERB_RE = re.compile(
    r"(服用|口服|吃药|喝|服|加|减|增|调|改|每次|每日|每天|一天|一次|一日|饭后|饭前|睡前|"
    r"开始|起始|维持|推荐|建议|最大|剂量|用量|改为|按)"
)
#: 药物上下文（用于消解「每日 25 克」这类食物/营养表述的歧义）
DRUG_CONTEXT_RE = re.compile(
    r"(药|服药|服用|口服|剂量|用药|处方|片剂|胶囊|医嘱|医嘱|mg|毫克|IU|单位)"
)
MED_CHANGE_RE = re.compile(
    r"(停药|停用|停服|停掉|换药|换用|改用|加量|减量|加药|减药|加倍|自行调(整|量)|加服|"
    r"改为服用|建议服用|可以服用|推荐服用|把.{0,10}(改成|换成|停了|停掉|换掉)|"
    r"剂量翻倍|加大剂量|减少剂量|"
    r"(加|减|增|调)[一二三四五六七八九十半两0-9]+\s*(片|粒|丸|毫克|mg|单位|喷|吸|毫升|ml))"
)
DIAGNOSIS_RE = re.compile(
    r"(你(已经)?(患|得|患了|得了)有?\s*(高血压|糖尿病|慢阻肺|冠心病|肾病)|你被诊断为|你已经确诊|"
    r"确诊为|诊断为|说明你(得|患)了|可以确定你是)"
)
SELF_TREAT_RE = re.compile(
    r"((自行|自己|您自己|你自己|其自行)[^。！？\n]{0,12}?(买|购|服用|用药|吃药|服药|去药店)|"
    r"(买|购|自购|去药店买|到药店买)[^。！？\n]{0,10}?药|"
    r"自行(用药|服用|购药)|自购药|你自己吃点)"
)

#: 「科普提问」句式 —— 用于抑制紧急红旗的"前置 120 提示"（但保留 flag）
KNOWLEDGE_FRAME_RE = re.compile(
    r"(如何识别|怎样识别|怎么识别|如何判断|怎样判断|怎么判断|什么是|是什么|指的是|"
    r"的早期症状|的典型症状|的临床表现|有哪些表现|症状有哪些|科普|"
    r"急救措施|急救方法|抢救措施|的识别|的治疗原则)"
)
#: 明确的"正在发生"标记 —— 命中则不做抑制
ACUTE_MARKER_RE = re.compile(
    r"(我(现在|刚刚|刚|突然|昨天|今天)|家人(现在|刚刚|刚|突然)|有人(现在|刚刚|刚|突然)|"
    r"患者(现在|刚刚|刚|突然)|正在|刚刚|突然|已经(晕|吐|痛|倒))"
)

SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？!?；;\n])")


@dataclass
class SafetyDecision:
    """输入侧安全判定结果。"""

    blocked: bool = False
    reason: str = ""
    report: SafetyReport = field(default_factory=SafetyReport)
    sanitized_query: str = ""

    def enforce(self) -> None:
        """硬拦截时抛出契约错误。"""
        if not self.blocked:
            return
        raise SafetyBlockedError(
            self.reason or "请求被安全策略拦截",
            details={"flags": self.report.flags},
        )


def _is_dosage_advice(sentence: str) -> bool:
    """判断一句话是否构成「具体用药剂量建议」。

    分级判定，避免把**正当的营养健康教育**误裁：

    1. 出现药物剂型（片/粒/丸/袋/支/吸/喷/滴）→ 直接判定为用药剂量；
    2. 出现药物专属质量单位（mg/毫克/IU/单位）且含服用类动词 → 判定为用药剂量；
    3. 出现通用质量/体积单位（克/g/毫升/ml）→ **必须同时**有服用类动词
       **且**有药物上下文，否则视为食物/营养数值，不裁。

    例：
    * ``每次吃两片。`` → 命中规则 1 → 裁剪
    * ``每日 2000mg。`` → 命中规则 2 → 裁剪
    * ``低盐饮食每日食盐不超过 5 克。`` → 规则 3 缺少药物上下文 → **不裁**
    * ``每日饮水 1500 毫升。`` → 规则 3 缺少药物上下文 → **不裁**
    """
    if DOSAGE_FORM_RE.search(sentence):
        return True
    if DOSAGE_DRUG_MASS_RE.search(sentence) and DOSE_VERB_RE.search(sentence):
        return True
    if (
        DOSAGE_FOOD_MASS_RE.search(sentence)
        and DOSE_VERB_RE.search(sentence)
        and DRUG_CONTEXT_RE.search(sentence)
    ):
        return True
    return False


class SafetyService:
    """输入 / 输出双向安全校验。"""

    # ------------------------------------------------------------------ 输入
    def check_query(self, text: str, *, operation: str = "") -> SafetyDecision:
        decision = SafetyDecision(sanitized_query=text)
        normalized = re.sub(r"\s+", " ", (text or "")).strip()
        flags: list[str] = []

        for pattern, label in HARD_BLOCK_PATTERNS:
            if re.search(pattern, normalized, re.IGNORECASE):
                flags.append(f"PROMPT_INJECTION:{label}")
                decision.blocked = True
                decision.report.injection_detected = True
                decision.reason = f"安全策略拦截：检测到{label}，本系统不接受此类请求。"
                decision.report.flags = flags
                decision.report.block_reason = decision.reason
                log_event(
                    logger,
                    "safety blocked",
                    operation=operation or "safety",
                    success=False,
                    error_code="SAFETY_BLOCKED",
                    flags=flags,
                )
                return decision

        for pattern, label in SOFT_FLAG_PATTERNS:
            if re.search(pattern, normalized):
                flags.append(label)
                decision.report.advice_seeking = True

        emergency_hit = False
        for pattern, label in EMERGENCY_PATTERNS:
            if re.search(pattern, normalized):
                emergency_hit = True
        if emergency_hit:
            flags.append("EMERGENCY_RED_FLAG")
            # 科普提问（"如何识别脑卒中早期症状"）不应被前置"立即拨打 120"，
            # 但 flag 仍然保留 —— 分诊由业务后端的 Rule Engine 决定。
            if KNOWLEDGE_FRAME_RE.search(normalized) and not ACUTE_MARKER_RE.search(normalized):
                flags.append("EMERGENCY_KNOWLEDGE_FRAME")

        decision.report.flags = sorted(set(flags))
        return decision

    @staticmethod
    def emergency_notice_required(flags: list[str]) -> bool:
        """是否需要前置确定性的"立即就医"提示。"""
        return "EMERGENCY_RED_FLAG" in flags and "EMERGENCY_KNOWLEDGE_FRAME" not in flags

    # ------------------------------------------------------------------ 上下文
    def scan_context(self, hits: list[RetrievedChunk]) -> list[str]:
        """扫描检索上下文，识别文档内的「指令注入」痕迹。

        只做标记 —— 上下文在 Prompt 中已经被明确声明为**数据**。
        """
        flags: list[str] = []
        for hit in hits:
            content = hit.content or ""
            for pattern, label in HARD_BLOCK_PATTERNS[:5]:
                if re.search(pattern, content, re.IGNORECASE):
                    flags.append(f"CONTEXT_INJECTION_SUSPECTED:{hit.chunk_id or hit.document_id}:{label}")
                    break
        if flags:
            log_event(
                logger,
                "context injection suspected",
                operation="rag.answer",
                success=True,
                error_code="",
                flags=flags[:5],
            )
        return sorted(set(flags))

    # ------------------------------------------------------------------ 输出
    def sanitize_answer(
        self,
        text: str,
        *,
        emergency: bool = False,
        advice_seeking: bool = False,
    ) -> tuple[str, SafetyReport]:
        """对 LLM 生成的回答做确定性裁剪。"""
        report = SafetyReport(
            flags=[],
            advice_seeking=advice_seeking,
            requires_human_confirmation=True,
        )
        if not text:
            if emergency:
                report.flags.append("EMERGENCY_RED_FLAG")
                return EMERGENCY_NOTICE, report
            return text, report

        flags: list[str] = []
        redactions: list[str] = []
        sentences = [part for part in SENTENCE_SPLIT_RE.split(text) if part and part.strip()]
        original_chars = max(1, len(text))
        removed_chars = 0
        output: list[str] = []

        for sentence in sentences:
            replacement: str | None = None
            if DIAGNOSIS_RE.search(sentence):
                replacement = REDACTION_TEMPLATES["diagnosis"]
                flags.append("BLOCKED_DIAGNOSIS_STATEMENT")
                redactions.append("diagnosis")
            elif MED_CHANGE_RE.search(sentence):
                replacement = REDACTION_TEMPLATES["medication_change"]
                flags.append("BLOCKED_MEDICATION_CHANGE")
                redactions.append("medication_change")
            elif SELF_TREAT_RE.search(sentence):
                replacement = REDACTION_TEMPLATES["self_treat"]
                flags.append("BLOCKED_SELF_TREATMENT")
                redactions.append("self_treat")
            elif _is_dosage_advice(sentence):
                replacement = REDACTION_TEMPLATES["dosage"]
                flags.append("BLOCKED_DOSAGE_RECOMMENDATION")
                redactions.append("dosage")

            if replacement is None:
                output.append(sentence)
            else:
                removed_chars += len(sentence)
                output.append(replacement)

        sanitized = "".join(output).strip()

        # 裁剪掉太多 → 判定为"整段回答不可用"，用安全兜底话术替代
        if removed_chars / original_chars > 0.6 and redactions:
            sanitized = (
                "根据安全策略，本系统不能提供诊断结论、具体用药剂量或停药/换药建议。"
                "以下内容仅为可查证的官方健康知识提示，具体诊疗方案请咨询你的医生。"
            ) if not emergency else EMERGENCY_NOTICE
            flags.append("ANSWER_BLOCKED_AFTER_REDACTION")
            report.blocked = True
            report.block_reason = "回答主体违反安全策略，已整体替换为安全话术"

        if emergency:
            if EMERGENCY_NOTICE not in sanitized:
                sanitized = f"{EMERGENCY_NOTICE}\n\n{sanitized}".strip()
            flags.append("EMERGENCY_RED_FLAG")

        if advice_seeking:
            flags.append("ADVICE_SEEKING_NOTICE")
            if "医生" not in sanitized:
                sanitized = (
                    sanitized + "\n\n如有用药或诊疗问题，请咨询你的家庭医生或到医疗机构就诊。"
                ).strip()

        report.flags = sorted(set(flags))
        report.redactions = sorted(set(redactions))
        report.requires_human_confirmation = True
        return sanitized, report

    # ------------------------------------------------------------------ 工具
    @staticmethod
    def merge_reports(*reports: SafetyReport) -> SafetyReport:
        merged = SafetyReport()
        flags: set[str] = set()
        redactions: set[str] = set()
        for report in reports:
            if report is None:
                continue
            flags.update(report.flags)
            redactions.update(report.redactions)
            merged.blocked = merged.blocked or report.blocked
            merged.injection_detected = merged.injection_detected or report.injection_detected
            merged.advice_seeking = merged.advice_seeking or report.advice_seeking
            if report.block_reason and not merged.block_reason:
                merged.block_reason = report.block_reason
        merged.flags = sorted(flags)
        merged.redactions = sorted(redactions)
        merged.requires_human_confirmation = True
        return merged
