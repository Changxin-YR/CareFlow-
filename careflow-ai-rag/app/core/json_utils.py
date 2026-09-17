"""JSON 解析工具 —— 容忍 LLM 输出的常见格式瑕疵。

LLM 经常把 JSON 包在 ```json 围栏里，或在前后加一句寒暄。
本模块统一处理，并且**明确区分**「JSON 结构错误」与「模型输出为空」，
以便服务层给出正确的错误码与降级路径。
"""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


class JSONParseError(ValueError):
    """无法从模型输出中解析出 JSON 对象。"""


def strip_code_fence(text: str) -> str:
    if not text:
        return ""
    match = _FENCE_RE.search(text)
    if match:
        return match.group(1).strip()
    return text.strip()


def loads_tolerant(text: str) -> Any:
    """尽力把模型输出解析成 Python 对象。

    顺序：直接解析 → 去代码围栏 → 截取最外层 `{...}` / `[...]`。
    """
    if text is None:
        raise JSONParseError("模型输出为空")
    candidates: list[str] = []
    raw = str(text).strip()
    candidates.append(raw)
    stripped = strip_code_fence(raw)
    if stripped != raw:
        candidates.append(stripped)
    for candidate in list(candidates):
        start_obj, end_obj = candidate.find("{"), candidate.rfind("}")
        if start_obj >= 0 and end_obj > start_obj:
            candidates.append(candidate[start_obj : end_obj + 1])
        start_arr, end_arr = candidate.find("["), candidate.rfind("]")
        if start_arr >= 0 and end_arr > start_arr:
            candidates.append(candidate[start_arr : end_arr + 1])

    for candidate in candidates:
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    raise JSONParseError(f"无法解析为 JSON：{raw[:200]!r}")


def ensure_object(text: str) -> dict[str, Any]:
    """解析并断言顶层是对象。"""
    payload = loads_tolerant(text)
    if not isinstance(payload, dict):
        raise JSONParseError(f"顶层应为 JSON 对象，实际为 {type(payload).__name__}")
    return payload


MARKER_RE = re.compile(r"\[(\d{1,2})\]")


def extract_markers(text: str) -> list[int]:
    """提取回答中的 `[n]` 引用编号（去重、保序）。"""
    if not text:
        return []
    seen: list[int] = []
    for match in MARKER_RE.finditer(text):
        value = int(match.group(1))
        if value not in seen:
            seen.append(value)
    return seen


def fold_fullwidth(text: str) -> str:
    """全角 → 半角。

    中文输入法下用户经常输入全角字符
    （``ＢＰ``、``１５８``、``／``、``％``），
    而提取与检索规则都是按半角写的。
    在提取入口统一折叠，可以一次性解决
    ``ＢＰ１５８／９６`` 这类输入。

    折叠范围：``U+FF01~U+FF5E`` → ``U+0021~U+007E``、
    ``U+3000`` → 半角空格。中文字符与其他符号不动。
    """
    if not text:
        return ""
    out: list[str] = []
    for char in text:
        code = ord(char)
        if code == 0x3000:
            out.append(" ")
        elif 0xFF01 <= code <= 0xFF5E:
            out.append(chr(code - 0xFEE0))
        else:
            out.append(char)
    return "".join(out)


def normalize_whitespace(text: str) -> str:
    """用于 source_text grounding 校验：去掉所有空白与常见全角符号差异。"""
    if not text:
        return ""
    # 先折叠全角，保证「原文是全角、抽取结果是半角」时 grounding 仍然成立
    text = fold_fullwidth(text)
    return re.sub(r"\s+", "", text).lower()
