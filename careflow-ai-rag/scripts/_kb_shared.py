"""Shared registry + config for the CareFlow knowledge-base pipeline.

Single source of truth: DOCUMENTS below (30 official documents, first import batch).
All paths are relative to the project root. No third-party mirrors are ever used.
"""
from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "knowledge" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "knowledge" / "processed"
CHUNKS_DIR = PROJECT_ROOT / "knowledge" / "chunks"
MANIFEST_DIR = PROJECT_ROOT / "knowledge" / "manifest"
DOCS_DIR = PROJECT_ROOT / "docs"

MANIFEST_CSV = MANIFEST_DIR / "knowledge_manifest.csv"
DOWNLOAD_REPORT = RAW_DIR / "_download_report.json"
PREPROCESS_REPORT = PROCESSED_DIR / "_preprocess_report.json"
CHUNKS_JSONL = CHUNKS_DIR / "chunks.jsonl"
INDEX_META = CHUNKS_DIR / "index_meta.json"

MANIFEST_COLUMNS = [
    "document_id", "title", "authority", "authority_level", "document_type",
    "version", "publish_date", "effective_date", "replaced_by", "status",
    "diseases", "scenarios", "language", "source_url", "local_file", "sha256",
    "qianfan_kb", "notes",
]

DOMAIN_DIRS = {
    "01_core", "02_hypertension", "03_diabetes", "04_copd",
    "05_multimorbidity", "06_lifestyle", "07_primarycare", "08_who",
}

# Controlled vocabularies -----------------------------------------------------
AUTHORITY_LEVELS = {"P0", "P1", "P2", "P3", "P4"}
STATUSES = {"active", "superseded", "draft", "disabled"}
DOCUMENT_TYPES = {
    "national_standard", "nhc_policy", "nhc_guideline", "professional_guideline",
    "expert_consensus", "who_guideline",
}
DISEASES = {
    "HYPERTENSION", "DIABETES", "COPD", "DYSLIPIDEMIA", "OBESITY",
    "HYPERURICEMIA", "CKD", "ELDERLY_HEALTH", "GENERAL_HEALTH",
    "MULTIMORBIDITY", "LIFESTYLE", "PRIMARY_CARE", "CARDIOVASCULAR",
}
SCENARIOS = {
    "followup", "education", "screening", "risk_assessment",
    "medication_safety", "lifestyle", "referral", "health_record",
}
QIANFAN_KBS = {
    "KB_CORE", "KB_HTN", "KB_DM", "KB_COPD", "KB_MULTIMORBIDITY",
    "KB_LIFESTYLE", "KB_PRIMARYCARE", "KB_WHO",
}


def _d(document_id, title, authority, authority_level, document_type, version,
       publish_date, diseases, scenarios, qianfan_kb, domain_dir, url,
       language="zh", kind="html", notes="", effective_date="", replaced_by=""):
    return {
        "document_id": document_id,
        "title": title,
        "authority": authority,
        "authority_level": authority_level,
        "document_type": document_type,
        "version": version,
        "publish_date": publish_date,
        "effective_date": effective_date,
        "replaced_by": replaced_by,
        "diseases": diseases,
        "scenarios": scenarios,
        "language": language,
        "source_url": url,
        "qianfan_kb": qianfan_kb,
        "domain_dir": domain_dir,
        "kind": kind,
        "notes": notes,
    }


DOCUMENTS = [
    # ---- 01_core -----------------------------------------------------------
    _d("CORE001", "关于加强基层慢性病健康管理服务的指导意见", "国家卫生健康委等",
       "P1", "nhc_policy", "2025", "2025-10-27",
       ["GENERAL_HEALTH", "PRIMARY_CARE", "MULTIMORBIDITY"],
       ["followup", "screening", "risk_assessment", "referral", "health_record"],
       "KB_CORE", "01_core",
       "https://www.nhc.gov.cn/jws/c100073/202510/3974d142eb1c4dd385b6e880f8617dcc.shtml"),
    _d("CORE002", "基层慢性病健康管理服务能力建设指引", "国家卫生健康委",
       "P1", "nhc_policy", "2025", "2025-11-20",
       ["GENERAL_HEALTH", "PRIMARY_CARE", "MULTIMORBIDITY"],
       ["followup", "screening", "risk_assessment", "referral", "health_record"],
       "KB_CORE", "01_core",
       "https://www.nhc.gov.cn/jws/c100073/202511/d3b6755fe7004cdeac938bf77b6a4a80.shtml",
       notes="page body is authoritative; attachment PDF optional supplement"),
    _d("CORE003", "国家基本公共卫生服务规范（第三版）", "国家卫生计生委",
       "P1", "nhc_policy", "第三版", "2017-02-28",
       ["GENERAL_HEALTH", "PRIMARY_CARE", "HYPERTENSION", "DIABETES", "ELDERLY_HEALTH"],
       ["followup", "screening", "risk_assessment", "education", "health_record"],
       "KB_CORE", "01_core",
       "https://www.nhc.gov.cn/jws/s3578/201703/d20c37e23e1f4c7db7b8e25f34473e1b.shtml",
       notes="notice page; full annexes are attachment PDFs on the same official page"),
    _d("CORE004", "关于做好2025年基本公共卫生服务工作的通知", "国家卫生健康委等",
       "P1", "nhc_policy", "2025", "2025-06-13",
       ["GENERAL_HEALTH", "PRIMARY_CARE"],
       ["followup", "screening", "health_record"],
       "KB_CORE", "01_core",
       "https://www.nhc.gov.cn/jws/c100073/202506/14a23782324542f59137bbf24a1c988f.shtml"),
    _d("CORE005", "中国公民健康素养——基本知识与技能（2024年版）", "国家卫生健康委",
       "P1", "nhc_policy", "2024版", "2024-05-30",
       ["GENERAL_HEALTH", "LIFESTYLE"],
       ["education", "lifestyle", "risk_assessment"],
       "KB_CORE", "01_core",
       "https://www.nhc.gov.cn/xcs/c100123/202405/73a4927142f34152abed875634a3c13b.shtml"),
    _d("CORE006", "中国公民健康素养——基本知识与技能释义（2024年版）", "国家卫生健康委",
       "P1", "nhc_policy", "2024版", "2024-05-30",
       ["GENERAL_HEALTH", "LIFESTYLE"],
       ["education", "lifestyle", "risk_assessment"],
       "KB_CORE", "01_core",
       "https://www.nhc.gov.cn/xcs/c100122/202405/f251e896a50a49ff8c632b4b3da93126.shtml"),
    # ---- 02_hypertension ---------------------------------------------------
    _d("HTN001", "基层医疗卫生机构高血压防治管理标准 WS/T 872—2025", "国家卫生健康委",
       "P0", "national_standard", "WS/T 872—2025", "2025-09-05",
       ["HYPERTENSION", "CARDIOVASCULAR"],
       ["followup", "screening", "risk_assessment", "medication_safety", "referral"],
       "KB_HTN", "02_hypertension",
       "https://www.nhc.gov.cn/wjw/c100309/202509/b601cb822b25461f92f7aa66c03495a8.shtml",
       notes="standard release notice page; standard text PDF is an attachment on the same page"),
    _d("HTN002", "国家基层高血压防治管理指南 2025版", "国家心血管病中心",
       "P3", "professional_guideline", "2025版", "",
       ["HYPERTENSION", "CARDIOVASCULAR"],
       ["followup", "risk_assessment", "medication_safety", "lifestyle", "referral"],
       "KB_HTN", "02_hypertension",
       "https://hbp-office.nccd.org.cn/download.html",
       notes="official download page of National Center for Cardiovascular Diseases"),
    _d("HTN003", "健康中国行动—心脑血管疾病防治行动实施方案（2023—2030年）", "国家卫生健康委等",
       "P1", "nhc_policy", "2023—2030", "2023-11-01",
       ["CARDIOVASCULAR", "HYPERTENSION", "DYSLIPIDEMIA"],
       ["screening", "risk_assessment", "education", "referral"],
       "KB_HTN", "02_hypertension",
       "https://www.nhc.gov.cn/ylyjs/gzdt/202311/a40dcf8a65314b818c46c9d1e683b9c3.shtml"),
    # ---- 03_diabetes -------------------------------------------------------
    _d("DM001", "健康中国行动——糖尿病防治行动实施方案（2024—2030年）", "国家卫生健康委等",
       "P1", "nhc_policy", "2024—2030", "2024-07-16",
       ["DIABETES", "MULTIMORBIDITY"],
       ["screening", "risk_assessment", "education", "referral", "followup"],
       "KB_DM", "03_diabetes",
       "https://www.nhc.gov.cn/wjw/c100375/202407/752d85bddda5420eb1c1fe3c2772a100.shtml"),
    _d("DM002", "中国2型糖尿病防治指南（2020年版）", "中华医学会糖尿病学分会",
       "P3", "professional_guideline", "2020版", "",
       ["DIABETES"],
       ["followup", "risk_assessment", "medication_safety", "lifestyle", "referral"],
       "KB_DM", "03_diabetes",
       "https://rs.yiigle.com/CN2021/1315505.htm",
       notes="pending manual download: publisher paywall (Yiigle), no official free full text"),
    _d("DM003", "国家基层糖尿病防治管理指南（2022）", "国家基层糖尿病防治管理办公室",
       "P3", "professional_guideline", "2022", "",
       ["DIABETES", "PRIMARY_CARE"],
       ["followup", "screening", "medication_safety", "lifestyle", "referral"],
       "KB_DM", "03_diabetes",
       "https://drugs.dxy.cn/pc/clinicalGuidelines/pFt03XqSDLS5Swuag1he4yw",
       notes="pending manual download: third-party portal requires login/authorization"),
    # ---- 04_copd -----------------------------------------------------------
    _d("COPD001", "慢性阻塞性肺疾病患者健康服务规范（试行）", "国家卫生健康委",
       "P1", "nhc_policy", "试行", "2024-09-13",
       ["COPD"],
       ["followup", "screening", "risk_assessment", "education", "referral"],
       "KB_COPD", "04_copd",
       "https://www.nhc.gov.cn/jws/c100073/202409/ad3c2a8221184272872a31ae400ecd37.shtml"),
    _d("COPD002", "健康中国行动——慢性呼吸系统疾病防治行动实施方案（2024—2030年）",
       "国家卫生健康委等", "P1", "nhc_policy", "2024—2030", "2024-07-30",
       ["COPD"],
       ["screening", "risk_assessment", "education", "referral", "followup"],
       "KB_COPD", "04_copd",
       "https://www.nhc.gov.cn/ylyjs/gzdt/202407/eee1c5827dc84989907d9e4cb2d24c4b.shtml"),
    # ---- 05_multimorbidity -------------------------------------------------
    _d("MULTI001", "“三高”共管规范化诊疗中国专家共识（2023版）", "中华医学会等",
       "P3", "expert_consensus", "2023版", "",
       ["HYPERTENSION", "DIABETES", "DYSLIPIDEMIA", "MULTIMORBIDITY", "CARDIOVASCULAR"],
       ["followup", "risk_assessment", "medication_safety", "referral"],
       "KB_MULTIMORBIDITY", "05_multimorbidity",
       "https://rs.yiigle.com/CN2021/1467649.htm",
       notes="pending manual download: publisher paywall (Yiigle), no official free full text"),
    _d("MULTI002", "中国血脂管理指南（2023年）", "中国血脂管理指南修订联合专家委员会",
       "P3", "professional_guideline", "2023", "",
       ["DYSLIPIDEMIA", "CARDIOVASCULAR", "MULTIMORBIDITY"],
       ["risk_assessment", "medication_safety", "lifestyle", "followup"],
       "KB_MULTIMORBIDITY", "05_multimorbidity",
       "https://www.sinocardiomed.com/wp-content/uploads/2023/04/2023041513592396.pdf",
       kind="pdf",
       notes="official PDF full text published by Chinese Society of Cardiology (sinocardiomed.com)"),
    # ---- 06_lifestyle ------------------------------------------------------
    _d("LIFE001", "高血压等慢性病营养和运动指导原则（2024年版）", "国家卫生健康委",
       "P1", "nhc_policy", "2024版", "2024-07-22",
       ["HYPERTENSION", "DIABETES", "DYSLIPIDEMIA", "LIFESTYLE", "MULTIMORBIDITY"],
       ["lifestyle", "education", "followup"],
       "KB_LIFESTYLE", "06_lifestyle",
       "https://www.nhc.gov.cn/ylyjs/gzdt/202407/256b4eb8398440a8811344c7be50a333.shtml"),
    _d("LIFE002", "成人高血压食养指南（2023年版）", "国家卫生健康委",
       "P1", "nhc_policy", "2023版", "2023-01-13",
       ["HYPERTENSION", "LIFESTYLE"],
       ["lifestyle", "education", "followup"],
       "KB_LIFESTYLE", "06_lifestyle",
       "https://www.nhc.gov.cn/sps/c100088/202301/f01895a06c5349ef999f25da833c166d.shtml",
       notes="shared official entry page for four 食养指南 (2023); annex PDF on the same page"),
    _d("LIFE003", "成人糖尿病食养指南（2023年版）", "国家卫生健康委",
       "P1", "nhc_policy", "2023版", "2023-01-13",
       ["DIABETES", "LIFESTYLE"],
       ["lifestyle", "education", "followup"],
       "KB_LIFESTYLE", "06_lifestyle",
       "https://www.nhc.gov.cn/sps/c100088/202301/f01895a06c5349ef999f25da833c166d.shtml",
       notes="shared official entry page for four 食养指南 (2023); annex PDF on the same page"),
    _d("LIFE004", "成人高脂血症食养指南（2023年版）", "国家卫生健康委",
       "P1", "nhc_policy", "2023版", "2023-01-13",
       ["DYSLIPIDEMIA", "LIFESTYLE"],
       ["lifestyle", "education", "followup"],
       "KB_LIFESTYLE", "06_lifestyle",
       "https://www.nhc.gov.cn/sps/c100088/202301/f01895a06c5349ef999f25da833c166d.shtml",
       notes="shared official entry page for four 食养指南 (2023); annex PDF on the same page"),
    _d("LIFE005", "成人高尿酸血症与痛风食养指南（2024年版）", "国家卫生健康委",
       "P1", "nhc_policy", "2024版", "2024-02-08",
       ["HYPERURICEMIA", "LIFESTYLE"],
       ["lifestyle", "education", "followup"],
       "KB_LIFESTYLE", "06_lifestyle",
       "https://www.nhc.gov.cn/sps/c100088/202402/9ba512ba8e314a47a181db11d2fa188d.shtml",
       notes="shared official entry page for four 食养指南 (2024); annex PDF on the same page"),
    _d("LIFE006", "成人肥胖食养指南（2024年版）", "国家卫生健康委",
       "P1", "nhc_policy", "2024版", "2024-02-08",
       ["OBESITY", "LIFESTYLE"],
       ["lifestyle", "education", "followup"],
       "KB_LIFESTYLE", "06_lifestyle",
       "https://www.nhc.gov.cn/sps/c100088/202402/9ba512ba8e314a47a181db11d2fa188d.shtml",
       notes="shared official entry page for four 食养指南 (2024); annex PDF on the same page"),
    _d("LIFE007", "成人慢性肾脏病食养指南（2024年版）", "国家卫生健康委",
       "P1", "nhc_policy", "2024版", "2024-02-08",
       ["CKD", "LIFESTYLE"],
       ["lifestyle", "education", "followup"],
       "KB_LIFESTYLE", "06_lifestyle",
       "https://www.nhc.gov.cn/sps/c100088/202402/9ba512ba8e314a47a181db11d2fa188d.shtml",
       notes="shared official entry page for four 食养指南 (2024); annex PDF on the same page"),
    _d("LIFE008", "居民体重管理核心知识（2024年版）及释义", "国家卫生健康委",
       "P1", "nhc_policy", "2024版", "2024-07-22",
       ["OBESITY", "LIFESTYLE"],
       ["lifestyle", "education", "risk_assessment"],
       "KB_LIFESTYLE", "06_lifestyle",
       "https://www.nhc.gov.cn/ylyjs/gzdt/202407/9ec6136773bc41048a39f275fcc37b44.shtml"),
    # ---- 07_primarycare ----------------------------------------------------
    _d("PRIM001", "居民电子健康档案首页基本内容（试行）", "国家卫生健康委",
       "P1", "nhc_policy", "试行", "2024-06-21",
       ["GENERAL_HEALTH", "PRIMARY_CARE"],
       ["health_record", "followup", "referral"],
       "KB_PRIMARYCARE", "07_primarycare",
       "https://www.nhc.gov.cn/jws/c100073/202406/f6520c3818c34637ab5f9d3d5232aaf3.shtml"),
    _d("PRIM002", "家庭医生签约基本服务包清单（试行）", "国家卫生健康委",
       "P1", "nhc_policy", "试行", "2025-04-15",
       ["GENERAL_HEALTH", "PRIMARY_CARE", "MULTIMORBIDITY"],
       ["followup", "education", "referral", "health_record", "lifestyle"],
       "KB_PRIMARYCARE", "07_primarycare",
       "https://www.nhc.gov.cn/jws/c100073/202504/57fa208d505041168bcf192331a129d2.shtml"),
    _d("PRIM003", "老年人健康管理技术规范 WS/T 484—2015", "国家卫生计生委",
       "P0", "national_standard", "WS/T 484—2015", "2015-11-04",
       ["ELDERLY_HEALTH", "PRIMARY_CARE", "HYPERTENSION", "DIABETES"],
       ["followup", "screening", "risk_assessment", "health_record", "medication_safety"],
       "KB_PRIMARYCARE", "07_primarycare",
       "https://www.nhc.gov.cn/wjw/c100309/201511/6725aa6b7b6846058e3abf6ab3ee32d4.shtml",
       notes="standard release notice page; standard text PDF is an attachment on the same page"),
    # ---- 08_who ------------------------------------------------------------
    _d("WHO001", "WHO PEN (Package of essential NCD interventions)", "World Health Organization",
       "P4", "who_guideline", "2nd edition", "",
       ["HYPERTENSION", "DIABETES", "CARDIOVASCULAR", "MULTIMORBIDITY", "PRIMARY_CARE"],
       ["screening", "risk_assessment", "followup", "medication_safety", "referral"],
       "KB_WHO", "08_who",
       "https://www.who.int/publications/i/item/9789240009226",
       language="en", kind="mixed",
       notes="official WHO item page; IRIS PDF https://iris.who.int/bitstream/handle/10665/334186/9789240009226-eng.pdf"),
    _d("WHO002", "WHO HEARTS: Risk-based CVD Management", "World Health Organization",
       "P4", "who_guideline", "HEARTS technical package", "",
       ["CARDIOVASCULAR", "HYPERTENSION", "DYSLIPIDEMIA"],
       ["risk_assessment", "followup", "medication_safety", "referral"],
       "KB_WHO", "08_who",
       "https://www.who.int/publications/i/item/9789240001367",
       language="en", kind="mixed"),
    _d("WHO003", "WHO HEARTS: Healthy-lifestyle counselling", "World Health Organization",
       "P4", "who_guideline", "HEARTS technical package", "",
       ["CARDIOVASCULAR", "LIFESTYLE", "HYPERTENSION"],
       ["lifestyle", "education", "followup"],
       "KB_WHO", "08_who",
       "https://www.who.int/publications/i/item/WHO-NMH-NVI-18-1",
       language="en", kind="mixed"),
]

DOCS_BY_ID = {d["document_id"]: d for d in DOCUMENTS}

# Extra official URLs (attachment PDFs) tried when the entry page yields only a
# notice body. Official hosts only.
EXTRA_URLS = {
    "WHO001": ["https://iris.who.int/bitstream/handle/10665/334186/9789240009226-eng.pdf"],
}


def ensure_dirs():
    for p in (RAW_DIR, PROCESSED_DIR, CHUNKS_DIR, MANIFEST_DIR, DOCS_DIR):
        p.mkdir(parents=True, exist_ok=True)
    for d in DOMAIN_DIRS:
        (RAW_DIR / d).mkdir(parents=True, exist_ok=True)


def relpath(p) -> str:
    """Project-root-relative POSIX path."""
    try:
        return Path(p).resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return Path(p).as_posix()


def sha256_file(path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_json(path, default=None):
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def dump_json(path, obj):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
