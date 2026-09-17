# CareFlow 康脉智护 —— Eval 报告

- 生成时间（UTC）：`2026-09-17T08:59:54+00:00`
- AI Provider：`mock`
- 契约版本：`CF-CONTRACT-2.0`
- 知识库：34 篇（active 28）／2448 个切片

> 说明：本报告**不包含任何「医学准确率」指标**。评测只覆盖
> 可客观判定的工程指标（提取字段/数值、路由召回、检索命中、
> Citation 真实性、无证据行为、安全拦截）。医学正确性必须由临床专家评审。

## 1. 汇总

| 套件 | 用例数 | 通过 | 通过率 | 关键指标 |
|---|---:|---:|---:|---|
| extraction | 32 | 32 | 100.00% | field_accuracy=1.0；value_accuracy=1.0；schema_pass_rate=1.0；hallucination_rate=0.0 |
| routing | 28 | 28 | 100.00% | domain_recall=1.0；domain_precision=0.9643；exact_match_rate=0.9286 |
| rag | 32 | 31 | 96.88% | recall_at_k=0.9667；citation_hit_rate=0.9375；authority_hit_rate=1.0；case_pass_rate=0.9688 |
| citation | 22 | 22 | 100.00% | citation_case_pass_rate=1.0；false_citation_count=0.0；illegal_citation_block_rate=1.0 |
| no_evidence | 12 | 12 | 100.00% | no_evidence_accuracy=1.0 |
| safety | 24 | 24 | 100.00% | block_decision_accuracy=1.0；flag_accuracy=1.0 |
| injection | 18 | 18 | 100.00% | injection_detection_rate=1.0；injection_bypass_count=0.0 |

## 2. 逐套件明细

### extraction

- 用例 32 条，通过 32 条，耗时 7 ms
- `field_accuracy` = **1.0**
- `value_accuracy` = **1.0**
- `schema_pass_rate` = **1.0**
- `hallucination_rate` = **0.0**
- 备注：共提取 36 条 observation，其中非原文 0 条
- 失败：0

### routing

- 用例 28 条，通过 28 条，耗时 1 ms
- `domain_recall` = **1.0**
- `domain_precision` = **0.9643**
- `exact_match_rate` = **0.9286**
- 失败：0

### rag

- 用例 32 条，通过 31 条，耗时 231 ms
- `recall_at_k` = **0.9667**
- `citation_hit_rate` = **0.9375**
- `authority_hit_rate` = **1.0**
- `case_pass_rate` = **0.9688**
- 备注：本批 RAG 用例未声明 expected_authority_levels，authority_hit_rate 不适用（记为 1.0）
- 失败 1 条（最多展示 10 条）：
  - `RAG-028`：["Recall@K 未命中：期望 ['CORE005', 'L03', 'LIFE001', 'WHO003'] 实际 ['CORE006', 'HTN001', 'HTN002', 'LIFE007']"]

### citation

- 用例 22 条，通过 22 条，耗时 4 ms
- `citation_case_pass_rate` = **1.0**
- `false_citation_count` = **0.0**
- `illegal_citation_block_rate` = **1.0**
- 备注：非法引用样本 6 条，全部拦截 = True
- 失败：0

### no_evidence

- 用例 12 条，通过 12 条，耗时 16 ms
- `no_evidence_accuracy` = **1.0**
- 失败：0

### safety

- 用例 24 条，通过 24 条，耗时 0 ms
- `block_decision_accuracy` = **1.0**
- `flag_accuracy` = **1.0**
- 失败：0

### injection

- 用例 18 条，通过 18 条，耗时 0 ms
- `injection_detection_rate` = **1.0**
- `injection_bypass_count` = **0.0**
- 失败：0

## 3. 原始结果

完整逐条结果见 `eval/results/eval_20260917T085954Z.json`。
