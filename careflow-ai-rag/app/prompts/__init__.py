"""Prompt 加载器。

Prompt 以 Markdown 文件形式维护（便于业务/医学同事评审），
本模块负责缓存加载与版本号提取。
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent

AVAILABLE_PROMPTS: dict[str, str] = {
    "extraction_system": "extraction_system.md",
    "rag_system": "rag_system.md",
    "followup_system": "followup_system.md",
    "router_system": "router_system.md",
    "safety_system": "safety_system.md",
}

_VERSION_RE = re.compile(r"^\s*prompt_version:\s*(\S+)", re.MULTILINE)


@lru_cache(maxsize=32)
def load_prompt(name: str) -> str:
    """读取 prompt 全文（缓存）。"""
    filename = AVAILABLE_PROMPTS.get(name, name)
    path = PROMPTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"prompt 文件不存在：{path}")
    return path.read_text(encoding="utf-8")


@lru_cache(maxsize=32)
def prompt_version(name: str) -> str:
    """提取 ``prompt_version: XXX`` 标记。"""
    try:
        content = load_prompt(name)
    except FileNotFoundError:
        return "unknown"
    match = _VERSION_RE.search(content)
    return match.group(1) if match else "unknown"


def clear_prompt_cache() -> None:
    load_prompt.cache_clear()
    prompt_version.cache_clear()


__all__ = ["AVAILABLE_PROMPTS", "PROMPTS_DIR", "clear_prompt_cache", "load_prompt", "prompt_version"]
