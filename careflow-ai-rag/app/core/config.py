"""CareFlow 康脉智护 —— 全局配置。

所有运行期配置都从环境变量 / `.env` 读取，代码中不出现任何真实密钥。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

try:  # python-dotenv 是可选依赖；缺失时退化为纯环境变量
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - 仅在极简环境下触发
    load_dotenv = None  # type: ignore[assignment]


PROJECT_ROOT = Path(__file__).resolve().parents[2]

#: 八个知识域 —— 与 knowledge_manifest.csv 的 qianfan_kb 列一一对应
KB_IDS: tuple[str, ...] = (
    "KB_CORE",
    "KB_HTN",
    "KB_DM",
    "KB_COPD",
    "KB_MULTIMORBIDITY",
    "KB_LIFESTYLE",
    "KB_PRIMARYCARE",
    "KB_WHO",
)

#: 受控词表 —— 疾病
DISEASE_VOCAB: tuple[str, ...] = (
    "HYPERTENSION",
    "DIABETES",
    "COPD",
    "DYSLIPIDEMIA",
    "OBESITY",
    "HYPERURICEMIA",
    "CKD",
    "ELDERLY_HEALTH",
    "GENERAL_HEALTH",
    "MULTIMORBIDITY",
    "LIFESTYLE",
    "PRIMARY_CARE",
    "CARDIOVASCULAR",
)

#: 受控词表 —— 场景
SCENARIO_VOCAB: tuple[str, ...] = (
    "followup",
    "education",
    "screening",
    "risk_assessment",
    "medication_safety",
    "lifestyle",
    "referral",
    "health_record",
)

#: 权威等级，优先级从左到右递减
AUTHORITY_LEVELS: tuple[str, ...] = ("P0", "P1", "P2", "P3", "P4")
AUTHORITY_RANK: dict[str, int] = {lvl: idx for idx, lvl in enumerate(AUTHORITY_LEVELS)}

#: manifest status 允许值；生产检索只使用 active
DOCUMENT_STATUSES: tuple[str, ...] = ("active", "superseded", "draft", "disabled")
RETRIEVABLE_STATUSES: tuple[str, ...] = ("active",)

AI_PROVIDERS: tuple[str, ...] = ("mock", "qianfan")

MANIFEST_COLUMNS: tuple[str, ...] = (
    "document_id",
    "title",
    "authority",
    "authority_level",
    "document_type",
    "version",
    "publish_date",
    "effective_date",
    "replaced_by",
    "status",
    "diseases",
    "scenarios",
    "language",
    "source_url",
    "local_file",
    "sha256",
    "qianfan_kb",
    "notes",
)


def _load_env_file() -> None:
    """加载项目根目录的 .env（不覆盖已有环境变量）。"""
    if load_dotenv is None:  # pragma: no cover
        return
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=False)


def _str(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip()


def _int(name: str, default: int) -> int:
    raw = _str(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    raw = _str(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    raw = _str(name).lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on", "y"}


def _path(name: str, default: Path) -> Path:
    raw = _str(name)
    if not raw:
        return default
    candidate = Path(raw)
    return candidate if candidate.is_absolute() else (PROJECT_ROOT / candidate)


@dataclass(frozen=True)
class Settings:
    """不可变配置快照。`load_settings()` 负责构造与缓存。"""

    app_env: str = "development"
    ai_provider: str = "mock"
    log_level: str = "INFO"

    # --- 百度千帆 / AppBuilder ---
    qianfan_api_key: str = ""
    qianfan_app_id: str = ""
    qianfan_model: str = "ernie-4.0-turbo-8k"
    qianfan_base_url: str = "https://qianfan.baidubce.com"
    qianfan_embedding_model: str = "bge-large-zh"
    qianfan_oauth_url: str = "https://aip.baidubce.com/oauth/2.0/token"
    qianfan_auth_mode: str = "bearer"
    qianfan_kb_ids: dict[str, str] = field(default_factory=dict)

    # --- RAG ---
    rag_top_k: int = 5
    rag_max_context_chars: int = 12000
    rag_score_threshold: float = 0.0
    #: 相关性闸门（经验校准值，换语料需重新标定）：
    #: 原始 BM25 分低于该值，或命中词数不足，则判定为"无证据"
    rag_min_relevance_score: float = 12.0
    rag_min_matched_terms: int = 3
    rag_enable_llm_router: bool = True

    # --- HTTP 客户端 ---
    request_timeout_seconds: int = 20
    max_retries: int = 1

    # --- 路径 ---
    project_root: Path = PROJECT_ROOT
    manifest_path: Path = PROJECT_ROOT / "knowledge" / "manifest" / "knowledge_manifest.csv"
    chunks_path: Path = PROJECT_ROOT / "knowledge" / "chunks" / "chunks.jsonl"
    prompts_dir: Path = PROJECT_ROOT / "app" / "prompts"
    logs_dir: Path = PROJECT_ROOT / "logs"

    # --- 服务 ---
    host: str = "0.0.0.0"
    port: int = 8100

    # ------------------------------------------------------------------
    @property
    def is_qianfan(self) -> bool:
        return self.ai_provider == "qianfan"

    @property
    def qianfan_configured(self) -> bool:
        """是否具备真实调用千帆的最小凭据。"""
        return bool(self.qianfan_api_key and self.qianfan_app_id)

    @property
    def qianfan_kb_configured(self) -> bool:
        return any(self.qianfan_kb_ids.values())

    def kb_id_for(self, kb_name: str) -> str:
        return self.qianfan_kb_ids.get(kb_name, "")

    def redacted(self) -> dict[str, object]:
        """用于 /v1/status 的安全视图 —— 绝不回显密钥。"""
        return {
            "app_env": self.app_env,
            "ai_provider": self.ai_provider,
            "log_level": self.log_level,
            "qianfan_model": self.qianfan_model,
            "qianfan_base_url": self.qianfan_base_url,
            "qianfan_auth_mode": self.qianfan_auth_mode,
            "qianfan_app_id_set": bool(self.qianfan_app_id),
            "qianfan_api_key_set": bool(self.qianfan_api_key),
            "qianfan_kb_ids": {
                name: ("SET" if value else "") for name, value in self.qianfan_kb_ids.items()
            },
            "rag_top_k": self.rag_top_k,
            "rag_min_relevance_score": self.rag_min_relevance_score,
            "rag_min_matched_terms": self.rag_min_matched_terms,
            "rag_max_context_chars": self.rag_max_context_chars,
            "rag_enable_llm_router": self.rag_enable_llm_router,
            "request_timeout_seconds": self.request_timeout_seconds,
            "max_retries": self.max_retries,
        }


def _build_settings() -> Settings:
    _load_env_file()

    provider = _str("AI_PROVIDER", "mock").lower()
    if provider not in AI_PROVIDERS:
        provider = "mock"

    kb_ids = {name: _str(f"QIANFAN_{name}_ID") for name in KB_IDS}

    return Settings(
        app_env=_str("APP_ENV", "development"),
        ai_provider=provider,
        log_level=_str("LOG_LEVEL", "INFO").upper(),
        qianfan_api_key=_str("QIANFAN_API_KEY"),
        qianfan_app_id=_str("QIANFAN_APP_ID"),
        qianfan_model=_str("QIANFAN_MODEL", "ernie-4.0-turbo-8k"),
        qianfan_base_url=_str("QIANFAN_BASE_URL", "https://qianfan.baidubce.com").rstrip("/"),
        qianfan_embedding_model=_str("QIANFAN_EMBEDDING_MODEL", "bge-large-zh"),
        qianfan_oauth_url=_str("QIANFAN_OAUTH_URL", "https://aip.baidubce.com/oauth/2.0/token"),
        qianfan_auth_mode=(_str("QIANFAN_AUTH_MODE", "bearer").lower() or "bearer"),
        qianfan_kb_ids=kb_ids,
        rag_top_k=max(1, _int("RAG_TOP_K", 5)),
        rag_max_context_chars=max(500, _int("RAG_MAX_CONTEXT_CHARS", 12000)),
        rag_score_threshold=_float("RAG_SCORE_THRESHOLD", 0.0),
        rag_min_relevance_score=_float("RAG_MIN_RELEVANCE_SCORE", 12.0),
        rag_min_matched_terms=max(1, _int("RAG_MIN_MATCHED_TERMS", 3)),
        rag_enable_llm_router=_bool("RAG_ENABLE_LLM_ROUTER", True),
        request_timeout_seconds=max(1, _int("REQUEST_TIMEOUT_SECONDS", 20)),
        max_retries=min(2, max(0, _int("MAX_RETRIES", 1))),
        manifest_path=_path("MANIFEST_PATH", PROJECT_ROOT / "knowledge" / "manifest" / "knowledge_manifest.csv"),
        chunks_path=_path("CHUNKS_PATH", PROJECT_ROOT / "knowledge" / "chunks" / "chunks.jsonl"),
        host=_str("HOST", "0.0.0.0"),
        port=_int("PORT", 8100),
    )


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    """返回缓存的配置快照。"""
    return _build_settings()


def reload_settings() -> Settings:
    """清缓存并重新读取环境变量（测试与热更新使用）。"""
    load_settings.cache_clear()
    return load_settings()
