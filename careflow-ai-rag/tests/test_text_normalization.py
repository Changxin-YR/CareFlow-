"""文本归一化回归测试。

对应真实缺陷：中文输入法下用户常输入**全角字符**（``ＢＰ``、``１５８``、``／``、``％``），
而提取规则是按半角写的，导致

* ``ＢＰ１５８／９６`` → 血压完全提取不到；
* ``体温３６.８`` → 体温提取不到（该正则当时写的是字面量 ``3[0-9]``，只有 ``\\d`` 才吃全角数字）。

修复方式：在提取入口统一 ``fold_fullwidth()``，并让 grounding 校验使用同一套折叠。
"""

from __future__ import annotations

import pytest

from app.core.json_utils import fold_fullwidth, normalize_whitespace
from app.schemas.extraction import Observation, ObservationType
from app.services.extraction_service import is_grounded, rule_extract
from app.services.retrieval_service import normalize_query


# --------------------------------------------------------------------------- #
# fold_fullwidth 本身
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ＢＰ１５８／９６", "BP158/96"),
        ("１５８", "158"),
        ("３６.８", "36.8"),
        ("９５％", "95%"),
        ("Ａ　Ｂ", "A B"),
        ("血压158/96", "血压158/96"),          # 半角不变
        ("高血压", "高血压"),                  # 中文不动
        ("", ""),
    ],
)
def test_fold_fullwidth(raw, expected):
    assert fold_fullwidth(raw) == expected


def test_fold_fullwidth_is_idempotent():
    once = fold_fullwidth("ＢＰ１５８／９６")
    assert fold_fullwidth(once) == once


def test_normalize_whitespace_folds_fullwidth():
    assert normalize_whitespace("血压 １５８／９６") == "血压158/96"
    assert normalize_whitespace("血压158/96") == "血压158/96"


def test_normalize_query_folds_fullwidth():
    assert normalize_query("血压１５８／９６") == "血压158/96"


# --------------------------------------------------------------------------- #
# 提取：全角输入
# --------------------------------------------------------------------------- #
def _observations(text: str) -> list[Observation]:
    return rule_extract(text)


@pytest.mark.parametrize(
    "text",
    [
        "血压158/96",
        "血压158／96",
        "血压１５８／９６",
        "血压１５８/９６",
        "ＢＰ１５８／９６",
        "BP158/96",
        "ｂｐ１５８／９６",
    ],
)
def test_blood_pressure_all_widths(text):
    observations = [o for o in _observations(text) if o.type is ObservationType.BLOOD_PRESSURE]
    assert observations, f"{text!r} 未提取到血压"
    assert observations[0].value == {"systolic": 158, "diastolic": 96}


@pytest.mark.parametrize(
    ("text", "obs_type", "key", "value"),
    [
        ("体温３６.８", ObservationType.BODY_TEMPERATURE, "value", 36.8),
        ("体温36.8", ObservationType.BODY_TEMPERATURE, "value", 36.8),
        ("空腹血糖７.２", ObservationType.BLOOD_GLUCOSE, "value", 7.2),
        ("体重７０公斤", ObservationType.WEIGHT, "value", 70.0),
        ("心率８８", ObservationType.HEART_RATE, "value", 88.0),
        ("血氧饱和度９５％", ObservationType.BLOOD_OXYGEN, "value", 95.0),
        ("糖化血红蛋白７.８％", ObservationType.HBA1C, "value", 7.8),
        ("腰围９８ｃｍ", ObservationType.WAIST, "value", 98.0),
        ("ＢＭＩ２５.６", ObservationType.BMI, "value", 25.6),
    ],
)
def test_numeric_observations_fullwidth(text, obs_type, key, value):
    observations = [o for o in _observations(text) if o.type is obs_type]
    assert observations, f"{text!r} 未提取到 {obs_type.value}"
    assert observations[0].value[key] == pytest.approx(value)


def test_body_temperature_out_of_range_still_ignored():
    # 折叠不能把量程校验弄坏
    assert [o for o in rule_extract("体温５０.０") if o.type is ObservationType.BODY_TEMPERATURE] == []
    assert [o for o in rule_extract("体温２０.０") if o.type is ObservationType.BODY_TEMPERATURE] == []


def test_medication_fullwidth():
    observations = [o for o in _observations("在吃硝苯地平３０ｍｇ每天一次") if o.type is ObservationType.MEDICATION]
    assert observations
    assert observations[0].value["name"] == "硝苯地平"
    assert observations[0].value["dose_text"] == "30mg"


def test_symptom_unaffected_by_folding():
    assert [o for o in rule_extract("最近头晕") if o.type is ObservationType.SYMPTOM]


# --------------------------------------------------------------------------- #
# grounding：原文全角 / source_text 半角，必须仍然成立
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("original", "fragment"),
    [
        ("血压１５８／９６，有点头晕", "血压158/96"),
        ("体温３６.８，还有点咳嗽", "体温36.8"),
        ("空腹血糖７.２", "空腹血糖7.2"),
        ("在吃硝苯地平３０ｍｇ每天一次", "硝苯地平30mg"),
    ],
)
def test_grounding_survives_fullwidth_original(original, fragment):
    observation = Observation(type=ObservationType.OTHER, value={}, source_text=fragment)
    assert is_grounded(observation, original) is True


def test_grounding_still_rejects_fabrication():
    observation = Observation(type=ObservationType.WEIGHT, value={"value": 70}, source_text="体重70")
    assert is_grounded(observation, "今天血压有点高") is False


# --------------------------------------------------------------------------- #
# source_text 必须是**用户原文**的连续片段（契约要求，供患者确认与审计回溯）
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "text",
    [
        "血压１５８／９６有点头晕",
        "在吃硝苯地平３０ｍｇ",
        "体温３６.８，空腹血糖７.２",
        "ＢＰ１５８／９６，有点头晕",
        "没有头晕，血压１３０／８５",
        "血压158/96，空腹血糖7.2",
    ],
)
def test_source_text_is_slice_of_original_text(text):
    for observation in rule_extract(text):
        assert observation.source_text in text, (
            f"source_text={observation.source_text!r} 不在原文 {text!r} 中"
        )


def test_source_text_preserves_fullwidth_characters():
    """折叠只用于匹配，不能把原文的全角字符改成半角后回填给患者。"""
    observations = [o for o in rule_extract("ＢＰ１５８／９６") if o.type is ObservationType.BLOOD_PRESSURE]
    assert observations
    assert observations[0].source_text == "ＢＰ１５８／９６"
    # 数值仍然是归一化后的数字
    assert observations[0].value == {"systolic": 158, "diastolic": 96}


# --------------------------------------------------------------------------- #
# 端到端：全角输入也能被 API 正确处理
# --------------------------------------------------------------------------- #
def test_api_extract_handles_fullwidth(client):
    response = client.post("/v1/extract", json={"text": "ＢＰ１５８／９６，体温３６.８"})
    assert response.status_code == 200
    types = {item["type"] for item in response.json()["data"]["observations"]}
    assert {"BLOOD_PRESSURE", "BODY_TEMPERATURE"} <= types


def test_api_rag_handles_fullwidth_query(client):
    response = client.post("/v1/rag/answer", json={"query": "家庭血压应该怎么测量？"})
    assert response.status_code == 200
    assert response.json()["data"]["answer"]
