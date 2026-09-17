# CareFlow 康脉智护 —— 官方知识库说明

> 面向读者：接手人、运维、医学同事、合规评审
> 本文档所有统计数字均**从真实产物现场计算**，复现方式见文末 §10 统计口径。
> 最近重算：**2026-09-17（第三轮补数据后）**

---

## 目录

1. [概览](#1-概览)
2. [权威等级策略](#2-权威等级策略)
3. [来源总表](#3-来源总表)
4. [下载与还原过程](#4-下载与还原过程)
5. [人工下载清单（未获取条目）](#5-人工下载清单未获取条目)
6. [已知覆盖缺口](#6-已知覆盖缺口)
7. [切片参数与-verbatim-保证](#7-切片参数与-verbatim-保证)
8. [复现命令](#8-复现命令)
9. [与-rag-的衔接](#9-与-rag-的衔接)
10. [统计口径](#10-统计口径)

---

## 1. 概览

### 1.1 核心数字

| 指标 | 数值 | 来源 |
|---|---:|---|
| manifest 登记文档 | **34** | `knowledge_manifest.csv` 行数 |
| `status=active` | **28** | manifest `status` 列 |
| `status=draft` | **6** | 同上（3 篇付费墙 + 3 篇扫描件拆分项） |
| `chunks.jsonl` 行数 | **2451** | 文件行数 |
| **实际参与检索的切片** | **2448** | 仅 active 文档的切片（加载期过滤，见 §2.4） |
| 产出切片的文档数 | **31** | chunks 中 distinct `document_id` |
| 清洗后正文总字符 | **1353633** | `_preprocess_report.json` → `summary.total_chars` |
| 清洗成功 / 无来源 | 31 / 3 | 同上（`ok` / `no_source`） |

> **`2451` 与 `2448` 的差异是预期的**：`LIFE001A` / `LIFE001B` / `LIFE001C` 三篇为 `draft`，
> 各产出 1 个切片，合计 3 个；它们在 `KnowledgeStore._load_chunks()` 加载期被剔除，
> **物理上不进入 BM25 索引**。文件行数是 2451，可检索数是 2448。

**修订记录（历史值，保留作对比）**：

| 指标 | 第二版（t6 时） | **当前** | 变化原因 |
|---|---:|---:|---|
| 登记文档 | 30 | **34** | +4：`LIFE001A`/`LIFE001B`/`LIFE001C`/`LIFE008A` |
| active | 27 | **28** | 新增 4 篇中 1 篇 active（`LIFE008A`），3 篇置 draft |
| draft | 3 | **6** | +3（`LIFE001A/B/C`） |
| 可检索切片 | 1041 | **2448** | WHO 三篇全文入库（+1412）与 LIFE 拆分 |
| 清洗总字符 | 612852 | **1353633** | WHO 三篇由约 2.4K 字符摘要 → 32.4 万 / 36.8 万 / 5.1 万字符全文 |

### 1.2 八个知识域分布

| 知识域 | 文档数 | 切片数 | 主题 |
|---|---:|---:|---|
| `KB_WHO` | 3 | **1412** | WHO 国际补充（**现为完整英文原文**） |
| `KB_LIFESTYLE` | 12 | **467** | 营养、运动、体重、食养指南 |
| `KB_CORE` | 6 | **234** | 基层慢病总体管理、健康素养 |
| `KB_MULTIMORBIDITY` | 2 | **222** | 血脂、多病共管 |
| `KB_HTN` | 3 | **70** | 高血压 |
| `KB_PRIMARYCARE` | 3 | **21** | 基层随访、家庭医生、老年健康 |
| `KB_COPD` | 2 | **16** | 慢阻肺 |
| `KB_DM` | 3 | **9** | 糖尿病 |
| **合计** | **34** | **2451** | |

> > **`KB_WHO` 由 9 个切片跃升为 1412 个**（占全库 57.6%），
> 因为它从"出版页摘要"变成了完整英文原文（85 / 80 / 30 页 PDF）。
> 这带来了两个新问题并均已修复（见 §6.7）：
> ① WHO 缩写查询（`WHO PEN`）因 IDF 极低被相关性闸门拦死；
> ② 路由关键词「基层」过宽，把 WHO 长查询路由到中文基层文档。

> > **`KB_DM` 仍是最薄弱域**：登记 3 篇，其中 2 篇（`DM002`/`DM003`）为
> **无法合法获取**（付费墙），**仅 `DM001` 一篇产出 9 个切片**。
> 糖尿病是基层慢病核心病种，此处仍是**最需要补齐的域**。
> `KB_COPD`（16 切片）与 `KB_PRIMARYCARE`（21 切片）同样偏薄。

### 1.3 文档类型、权威等级与语言分布

| `document_type` | 篇数 | | `authority_level` | 篇数 | | `language` | 篇数 |
|---|---:|---|---|---:|---|---|---:|
| `nhc_policy` | 24 | | `P1` | 24 | | `zh` | 31 |
| `professional_guideline` | 4 | | `P3` | 5 | | `en` | 3 |
| `who_guideline` | 3 | | `P4` | 3 | | | |
| `national_standard` | 2 | | `P0` | 2 | | | |
| `expert_consensus` | 1 | | `P2` | **0** | | | |

> **仍无 `P2` 条目**（国家级医学中心）。等级按实际来源如实标注，
> `P2` 为 0 表示"尚无该等级文档"，**不是遗漏**。
>
> **3 篇英文文档**（WHO 三篇）与其余 31 篇中文语料**语言不一致**。
> 中文查询对英文全文的 BM25 命中依赖英文词（中文按字级 bigram 切分，无法匹配英文），
> 因此跨语言检索能力有限——实测中英文混合查询需靠域过滤与路由收敛，见 §6.7。

---

## 2. 权威等级策略

### 2.1 等级定义

| 等级 | 语义 | 典型来源 | 本库篇数 |
|---|---|---|---:|
| `P0` | 国家现行卫生标准（行业标准 WS/T） | 国家卫生健康委发布的国家标准 | 2 |
| `P1` | 国家卫健委正式文件 | 卫健委通知、指南、服务规范 | 24 |
| `P2` | 国家级医学中心 | 国家心血管病中心等 | **0** |
| `P3` | 中华医学会 / 国家级专业组织 | 学会指南、专家共识 | 5 |
| `P4` | WHO 等国际权威补充 | WHO 技术包 | 3 |

`P0` 的两条：`HTN001`（WS/T 872—2025 基层医疗卫生机构高血压防治管理标准）、
`PRIM003`（WS/T 484—2015 老年人健康管理技术规范）。

### 2.2 冲突处理原则

> **当不同等级来源出现差异时，优先采用「中国当前有效且适用于基层场景的正式规范」。**

理由：本系统服务对象是**基层慢病共管与随访**，因此
① 优先中国现行标准/卫健委文件（P0/P1），② 国际资料（P4）作为补充而非替代。
等级是**排序与解释的依据**，不是自动裁决——最终临床判断仍由医生作出。

> **该原则目前只能"部分落地"**：由于 `effective_date` 仅 2/34 篇有值（见 §6.6），
> 系统**无法自动判定"现行有效版本"**，冲突时只能靠 `status` + `authority_level` 缓解。

### 2.3 代码落地：`AUTHORITY_BOOST`

检索排序对权威等级做**加权**（不是硬过滤），定义于
`app/services/retrieval_service.py`：

```python
AUTHORITY_BOOST: dict[str, float] = {
    "P0": 1.25, "P1": 1.15, "P2": 1.05, "P3": 1.00, "P4": 0.95,
}
```

- 加权发生在**检索打分的最后一步**（`_apply_authority`）：`_score *= AUTHORITY_BOOST[level]`
- 未识别的等级回退系数 `1.0`
- **语义是"同等相关性下高权威优先"，不删除低权威文档**

### 2.4 生产检索只用 `status=active`

`KnowledgeStore._load_chunks()` 在**加载阶段**即过滤：

```python
entry = self.entries.get(chunk.document_id)
if entry is not None and not entry.is_active:
    continue          # superseded / draft / disabled 的切片不入索引
```

因此 `draft` 文档的切片**物理上不进入索引**，比"检索时再过滤"更安全。
这解释了为何文件有 2451 个切片而可检索的只有 **2448** 个。

---

## 3. 来源总表

> 全部字段从 `knowledge/manifest/knowledge_manifest.csv`（UTF-8 with BOM）现场读取；
> 「字符」来自 `_preprocess_report.json`，「切片」从 `chunks.jsonl` 按 `document_id` 统计。
> `—` 表示 manifest 中该字段**为空**（非本文档省略）。

| document_id | 标题 | 发布机构 | 等级 | 版本 | 发布日期 | 有效日期 | 状态 | 知识域 | 语言 | 来源 URL | 本地文件 | 字符 | 切片 |
|---|---|---|---|---|---|---|---|---|---|---|---|---:|---:|
| `CORE001` | 关于加强基层慢性病健康管理服务的指导意见 | 国家卫生健康委等 | P1 | 2025 | 2025-10-29 | — | active | KB_CORE | zh | [链接](https://www.nhc.gov.cn/jws/c100073/202510/3974d142eb1c4dd385b6e880f8617dcc.shtml) | `knowledge/raw/01_core/CORE001.html` | 3264 | 5 |
| `CORE002` | 基层慢性病健康管理服务能力建设指引 | 国家卫生健康委 | P1 | 2025 | 2025-11-20 | — | active | KB_CORE | zh | [链接](https://www.nhc.gov.cn/jws/c100073/202511/d3b6755fe7004cdeac938bf77b6a4a80.shtml) | `knowledge/raw/01_core/CORE002.html` | 476 | 1 |
| `CORE003` | 国家基本公共卫生服务规范（第三版） | 国家卫生计生委 | P1 | 第三版 | 2017-03-28 | — | active | KB_CORE | zh | [链接](https://www.nhc.gov.cn/jws/s3578/201703/d20c37e23e1f4c7db7b8e25f34473e1b.shtml) | `knowledge/raw/01_core/CORE003.html` | 81780 | 151 |
| `CORE004` | 关于做好2025年基本公共卫生服务工作的通知 | 国家卫生健康委等 | P1 | 2025 | 2025-06-26 | — | active | KB_CORE | zh | [链接](https://www.nhc.gov.cn/jws/c100073/202506/14a23782324542f59137bbf24a1c988f.shtml) | `knowledge/raw/01_core/CORE004.html` | 2452 | 4 |
| `CORE005` | 中国公民健康素养——基本知识与技能（2024年版） | 国家卫生健康委 | P1 | 2024版 | 2024-05-30 | — | active | KB_CORE | zh | [链接](https://www.nhc.gov.cn/xcs/c100123/202405/73a4927142f34152abed875634a3c13b.shtml) | `knowledge/raw/01_core/CORE005.html` | 2641 | 3 |
| `CORE006` | 中国公民健康素养——基本知识与技能释义（2024年版） | 国家卫生健康委 | P1 | 2024版 | 2024-05-30 | — | active | KB_CORE | zh | [链接](https://www.nhc.gov.cn/xcs/c100122/202405/f251e896a50a49ff8c632b4b3da93126.shtml) | `knowledge/raw/01_core/CORE006.html` | 43653 | 70 |
| `HTN001` | 基层医疗卫生机构高血压防治管理标准 WS/T 872—2025 | 国家卫生健康委 | P0 | WS/T 872—2025 | 2025-09-30 | 2026-03-01 | active | KB_HTN | zh | [链接](https://www.nhc.gov.cn/wjw/c100309/202509/b601cb822b25461f92f7aa66c03495a8.shtml) | `knowledge/raw/02_hypertension/HTN001.html` | 3815 | 7 |
| `HTN002` | 国家基层高血压防治管理指南 2025版 | 国家心血管病中心 | P3 | 2025版 | 2025-09-24 | — | active | KB_HTN | zh | [链接](https://hbp-office.nccd.org.cn/download.html) | `knowledge/raw/02_hypertension/HTN002.html` | 32920 | 57 |
| `HTN003` | 健康中国行动—心脑血管疾病防治行动实施方案（2023—2030年） | 国家卫生健康委等 | P1 | 2023—2030 | 2023-11-14 | — | active | KB_HTN | zh | [链接](https://www.nhc.gov.cn/ylyjs/gzdt/202311/a40dcf8a65314b818c46c9d1e683b9c3.shtml) | `knowledge/raw/02_hypertension/HTN003.html` | 4791 | 6 |
| `DM001` | 健康中国行动——糖尿病防治行动实施方案（2024—2030年） | 国家卫生健康委等 | P1 | 2024—2030 | 2025-06-06 | — | active | KB_DM | zh | [链接](https://www.nhc.gov.cn/wjw/c100375/202407/752d85bddda5420eb1c1fe3c2772a100.shtml) | `knowledge/raw/03_diabetes/DM001.html` | 6511 | 9 |
| `DM002` | 中国2型糖尿病防治指南（2020年版） | 中华医学会糖尿病学分会 | P3 | 2020版 | 2021-04-27 | — | draft | KB_DM | zh | [链接](https://rs.yiigle.com/CN2021/1315505.htm) | `PENDING` | 0 | 0 |
| `DM003` | 国家基层糖尿病防治管理指南（2022） | 国家基层糖尿病防治管理办公室 | P3 | 2022 | 2022-03-01 | — | draft | KB_DM | zh | [链接](https://drugs.dxy.cn/pc/clinicalGuidelines/pFt03XqSDLS5Swuag1he4yw) | `PENDING` | 0 | 0 |
| `COPD001` | 慢性阻塞性肺疾病患者健康服务规范（试行） | 国家卫生健康委 | P1 | 试行 | 2024-09-13 | — | active | KB_COPD | zh | [链接](https://www.nhc.gov.cn/jws/c100073/202409/ad3c2a8221184272872a31ae400ecd37.shtml) | `knowledge/raw/04_copd/COPD001.html` | 5307 | 10 |
| `COPD002` | 健康中国行动——慢性呼吸系统疾病防治行动实施方案（2024—2030年） | 国家卫生健康委等 | P1 | 2024—2030 | 2024-07-29 | — | active | KB_COPD | zh | [链接](https://www.nhc.gov.cn/ylyjs/gzdt/202407/eee1c5827dc84989907d9e4cb2d24c4b.shtml) | `knowledge/raw/04_copd/COPD002.html` | 4579 | 6 |
| `MULTI001` | “三高”共管规范化诊疗中国专家共识（2023版） | 中华医学会等 | P3 | 2023版 | 2023-07-24 | — | draft | KB_MULTIMORBIDITY | zh | [链接](https://rs.yiigle.com/CN2021/1467649.htm) | `PENDING` | 0 | 0 |
| `MULTI002` | 中国血脂管理指南（2023年） | 中国血脂管理指南修订联合专家委员会 | P3 | 2023 | 2023-04-15 | — | active | KB_MULTIMORBIDITY | zh | [链接](https://www.sinocardiomed.com/wp-content/uploads/2023/04/2023041513592396.pdf) | `knowledge/raw/05_multimorbidity/MULTI002.pdf` | 129552 | 222 |
| `LIFE001` | 高血压营养和运动指导原则（2024年版） | 国家卫生健康委 | P1 | 2024版 | 2024-07-01 | — | active | KB_LIFESTYLE | zh | [链接](https://www.nhc.gov.cn/ylyjs/gzdt/202407/256b4eb8398440a8811344c7be50a333.shtml) | `knowledge/raw/06_lifestyle/LIFE001.html` | 1325 | 2 |
| `LIFE001A` | 高血糖症营养和运动指导原则（2024年版） | 国家卫生健康委 | P1 | 2024版 | 2024-07-01 | — | draft | KB_LIFESTYLE | zh | [链接](https://www.nhc.gov.cn/ylyjs/gzdt/202407/256b4eb8398440a8811344c7be50a333.shtml) | `knowledge/raw/06_lifestyle/LIFE001A.pdf` | 456 | 1 |
| `LIFE001B` | 高脂血症营养和运动指导原则（2024年版） | 国家卫生健康委 | P1 | 2024版 | 2024-07-01 | — | draft | KB_LIFESTYLE | zh | [链接](https://www.nhc.gov.cn/ylyjs/gzdt/202407/256b4eb8398440a8811344c7be50a333.shtml) | `knowledge/raw/06_lifestyle/LIFE001B.pdf` | 472 | 1 |
| `LIFE001C` | 高尿酸血症营养和运动指导原则（2024年版） | 国家卫生健康委 | P1 | 2024版 | 2024-07-01 | — | draft | KB_LIFESTYLE | zh | [链接](https://www.nhc.gov.cn/ylyjs/gzdt/202407/256b4eb8398440a8811344c7be50a333.shtml) | `knowledge/raw/06_lifestyle/LIFE001C.pdf` | 503 | 1 |
| `LIFE002` | 成人高血压食养指南（2023年版） | 国家卫生健康委 | P1 | 2023版 | 2023-01-18 | — | active | KB_LIFESTYLE | zh | [链接](https://www.nhc.gov.cn/sps/c100088/202301/f01895a06c5349ef999f25da833c166d.shtml) | `knowledge/raw/06_lifestyle/LIFE002.html` | 37115 | 62 |
| `LIFE003` | 成人糖尿病食养指南（2023年版） | 国家卫生健康委 | P1 | 2023版 | 2023-01-18 | — | active | KB_LIFESTYLE | zh | [链接](https://www.nhc.gov.cn/sps/c100088/202301/f01895a06c5349ef999f25da833c166d.shtml) | `knowledge/raw/06_lifestyle/LIFE003.html` | 43140 | 74 |
| `LIFE004` | 成人高脂血症食养指南（2023年版） | 国家卫生健康委 | P1 | 2023版 | 2023-01-18 | — | active | KB_LIFESTYLE | zh | [链接](https://www.nhc.gov.cn/sps/c100088/202301/f01895a06c5349ef999f25da833c166d.shtml) | `knowledge/raw/06_lifestyle/LIFE004.html` | 25909 | 42 |
| `LIFE005` | 成人高尿酸血症与痛风食养指南（2024年版） | 国家卫生健康委 | P1 | 2024版 | 2024-02-08 | — | active | KB_LIFESTYLE | zh | [链接](https://www.nhc.gov.cn/sps/c100088/202402/9ba512ba8e314a47a181db11d2fa188d.shtml) | `knowledge/raw/06_lifestyle/LIFE005.html` | 48460 | 81 |
| `LIFE006` | 成人肥胖食养指南（2024年版） | 国家卫生健康委 | P1 | 2024版 | 2024-02-08 | — | active | KB_LIFESTYLE | zh | [链接](https://www.nhc.gov.cn/sps/c100088/202402/9ba512ba8e314a47a181db11d2fa188d.shtml) | `knowledge/raw/06_lifestyle/LIFE006.html` | 55999 | 95 |
| `LIFE007` | 成人慢性肾脏病食养指南（2024年版） | 国家卫生健康委 | P1 | 2024版 | 2024-02-08 | — | active | KB_LIFESTYLE | zh | [链接](https://www.nhc.gov.cn/sps/c100088/202402/9ba512ba8e314a47a181db11d2fa188d.shtml) | `knowledge/raw/06_lifestyle/LIFE007.html` | 58829 | 103 |
| `LIFE008` | 居民体重管理核心知识（2024年版） | 国家卫生健康委 | P1 | 2024版 | 2024-07-02 | — | active | KB_LIFESTYLE | zh | [链接](https://www.nhc.gov.cn/ylyjs/gzdt/202407/9ec6136773bc41048a39f275fcc37b44.shtml) | `knowledge/raw/06_lifestyle/LIFE008.html` | 594 | 1 |
| `LIFE008A` | 居民体重管理核心知识（2024年版）释义 | 国家卫生健康委 | P1 | 2024版 | 2024-07-02 | — | active | KB_LIFESTYLE | zh | [链接](https://www.nhc.gov.cn/ylyjs/gzdt/202407/9ec6136773bc41048a39f275fcc37b44.shtml) | `knowledge/raw/06_lifestyle/LIFE008A.pdf` | 2092 | 4 |
| `PRIM001` | 居民电子健康档案首页基本内容（试行） | 国家卫生健康委 | P1 | 试行 | 2024-06-21 | — | active | KB_PRIMARYCARE | zh | [链接](https://www.nhc.gov.cn/jws/c100073/202406/f6520c3818c34637ab5f9d3d5232aaf3.shtml) | `knowledge/raw/07_primarycare/PRIM001.html` | 5015 | 8 |
| `PRIM002` | 家庭医生签约基本服务包清单（试行） | 国家卫生健康委 | P1 | 试行 | 2025-04-15 | — | active | KB_PRIMARYCARE | zh | [链接](https://www.nhc.gov.cn/jws/c100073/202504/57fa208d505041168bcf192331a129d2.shtml) | `knowledge/raw/07_primarycare/PRIM002.html` | 8330 | 12 |
| `PRIM003` | 老年人健康管理技术规范 WS/T 484—2015 | 国家卫生计生委 | P0 | WS/T 484—2015 | 2015-11-16 | 2016-04-01 | active | KB_PRIMARYCARE | zh | [链接](https://www.nhc.gov.cn/wjw/c100309/201511/6725aa6b7b6846058e3abf6ab3ee32d4.shtml) | `knowledge/raw/07_primarycare/PRIM003.html` | 281 | 1 |
| `WHO001` | WHO PEN (Package of essential NCD interventions) | World Health Organization | P4 | 2nd edition | 2020-09-07 | — | active | KB_WHO | en | [链接](https://www.who.int/publications/i/item/9789240009226) | `knowledge/raw/08_who/WHO001.pdf` | 324419 | 623 |
| `WHO002` | WHO HEARTS: Risk-based CVD Management | World Health Organization | P4 | HEARTS technical package | 2020-07-13 | — | active | KB_WHO | en | [链接](https://www.who.int/publications/i/item/9789240001367) | `knowledge/raw/08_who/WHO002.pdf` | 367779 | 709 |
| `WHO003` | WHO HEARTS: Healthy-lifestyle counselling | World Health Organization | P4 | HEARTS technical package | 2018-05-02 | — | active | KB_WHO | en | [链接](https://www.who.int/publications/i/item/WHO-NMH-NVI-18-1) | `knowledge/raw/08_who/WHO003.pdf` | 51174 | 80 |

### 3.1 表格字段说明

| 列 | manifest 列名 | 说明 |
|---|---|---|
| 发布机构 | `authority` | 发布/归口机构原文 |
| 版本 | `version` | 版本标识（如 `2025`、`第三版`、`WS/T 872—2025`） |
| 发布日期 | `publish_date` | **34/34 全部有值**（第三轮补齐） |
| 有效日期 | `effective_date` | **仅 2/34**（`HTN001` 2026-03-01、`PRIM003` 2016-04-01） |
| 状态 | `status` | `active`(28) / `draft`(6) |
| 知识域 | `qianfan_kb` | 八个 `KB_*` 之一，同时对应千帆知识库 ID |
| 语言 | `language` | `zh`(31) / `en`(3) |
| 本地文件 | `local_file` | 抽取所用的**主**源文件（HTML 或 PDF）；未获取时为 `PENDING` |
| 字符 | — | `_preprocess_report.json` 的清洗后字符数 |
| 切片 | — | 该文档产出的切片数（含 draft 的不可检索切片） |

---

## 4. 下载与还原过程

### 4.1 为什么必须用 Playwright

`www.nhc.gov.cn` 全站启用 **WZWS（网宿）JS 挑战**风控。
任何非浏览器客户端（`httpx` / `requests` / `curl`，无论怎么伪装 UA）都会拿到 **HTTP 412**。

实测结论（已固化在 `scripts/playwright_fetch.py` 模块 docstring）：

| # | 关键点 | 说明 |
|---|---|---|
| 1 | **412 是挑战的第一步，不是失败** | 页面会**自行重新导航**并在完成后返回真实内容。绝不能因 `status == 412` 判定失败 |
| 2 | 不能用 `wait_until="load"` / `"networkidle"` | 挑战期间这些会超时或抛异常 |
| 3 | 正确做法 | `page.goto(url, wait_until="commit")` 后**自己轮询** `await page.inner_text("body")` |
| 4 | 完成判据 | `inner_text("body")` 长度 ≥ `min_text_chars` 且**不匹配** `CHALLENGE_MARKERS` |
| 5 | 下载附件必须复用**同一个 BrowserContext** | 用 `ctx.request.get(...)`；新开 context 则 WAF cookie 不在，照样 412 |

挑战标记：`CHALLENGE_MARKERS = ("$_ts", "wzws", "请稍候", "安全验证", "Checking your browser")`

### 4.2 附件兜底与"文本层"判定

部分官方页面（通知页）**正文只有发布语**，真实内容在同页**附件 PDF** 里。
管线会抽取附件候选（`annex_candidates`），下载后**必须先判断 PDF 是否有可用文本层**：

| 判定 | 处置 | 本库实例 |
|---|---|---|
| 文本层**可用** | 作为正文来源（`input_kind=pdf`） | `CORE003`(89316) `MULTI002` `PRIM001` `PRIM002` `COPD001` `CORE006` `HTN001` `HTN002` `LIFE002`~`LIFE007` `LIFE008A` |
| 文本层**缺失/损坏** | **不纳入检索**，改用页面正文或置 draft | `CORE002` `LIFE001` `LIFE001A/B/C` `LIFE008` `PRIM003` |
| 文本层可用但**内容与标题不符** | 置 `draft`（保留来源记录，不污染 Citation） | `LIFE001A`(0.111) `LIFE001B`(0.111) `LIFE001C`(0.053) |

> **关键事实**：`CORE002` / `LIFE001` / `LIFE008` 的官方附件是**无文本层扫描件**
> （不是"没抓到"）——详见 §6。

### 4.3 下载结果汇总

来自 `knowledge/raw/_download_report.json`：

| `status` | 篇数 | 含义 |
|---|---:|---|
| `downloaded` | **28** | 本次下载成功 |
| `skipped` | **3** | 已有可用本地产物，跳过重复下载 |
| `failed` | **3** | 付费墙 / 登录墙（`DM002`、`DM003`、`MULTI001`） |

`www.nhc.gov.cn` 的各篇均记录
`waf_note = "navigation status 412 (WZWS challenge) but body fully rendered"`
——即**导航状态为 412 但正文已完整渲染**，是 §4.1 机制的直接证据。

### 4.4 WHO 全文的获取（旧 IRIS 链接已失效）

> **最容易走弯路的点之一。**

WHO 三篇本轮从"出版页摘要"升级为**完整英文原文**。失败与成功的路径：

| 链接格式 | 结果 |
|---|---|
| `https://iris.who.int/bitstream/handle/10665/334186/9789240009226-eng.pdf` | **失败**，返回 **755 字节 HTML**（不是 PDF） |
| `https://apps.who.int/iris/bitstream/handle/10665/260422/WHO-NMH-NVI-18.1-eng.pdf` | **失败**，同上，755 字节 HTML |
| **`https://iris.who.int/server/api/core/bitstreams/<uuid>/content`** | **成功**，完整 PDF |

即 **WHO 已把 IRIS 迁移到新版 API 路径**；旧 `bitstream/handle/...` 链接全部失效。
正确做法：从**官方出版页**解析出新的 `/server/api/core/bitstreams/<uuid>/content` 直链。

| document_id | 页数 | 清洗后字符 | 之前（摘要） | `title_bigram_ratio` |
|---|---:|---:|---:|---:|
| `WHO001` | 85 | **324419** | 1429 | 0.857 |
| `WHO002` | 80 | **367779** | 2259 | 0.633 |
| `WHO003` | 30 | **51174** | 2419 | 0.727 |

三份均为**英文原文**（`language=en`），**未翻译**。

---

## 5. 人工下载清单（未获取条目）

以下 6 条 `status=draft`。前 3 条**无任何本地产物**（切片 0）；
后 3 条**文件已保留但内容不可用**（各 1 个不可检索切片）。

| document_id | 标题 | 状态 | 未获取原因（manifest `notes` 原文摘要） | 官方入口 URL |
|---|---|---|---|---|
| `DM002` | 中国2型糖尿病防治指南（2020年版） | **draft** | pending manual download: publisher paywall (Yiigle), no official free full text; 正式出处 中华糖尿病杂志 2021;13(4):315-409, DOI 10.3760/cma.j.cn115791-20210221-00095; pending manual download: waf_or_empty_body: body_len=35 status=401 title=安全验证 | https://rs.yiigle.com/CN2021/1315505.htm |
| `DM003` | 国家基层糖尿病防治管理指南（2022） | **draft** | pending manual download: third-party portal requires login/authorization; 正式出处 中华内科杂志 2022;61(3):249-262, DOI 10.3760/cma.j.cn112138-20220120-000063; pending manual download: paywall_or_login_wall: third-party portal drugs.dxy.cn renders only a preview; full text requires login/membership (paywall not bypassed) | https://drugs.dxy.cn/pc/clinicalGuidelines/pFt03XqSDLS5Swuag1he4yw |
| `MULTI001` | “三高”共管规范化诊疗中国专家共识（2023版） | **draft** | pending manual download: publisher paywall (Yiigle), no official free full text; pending manual download: waf_or_empty_body: body_len=35 status=401 title=安全验证 | https://rs.yiigle.com/CN2021/1467649.htm |
| `LIFE001A` | 高血糖症营养和运动指导原则（2024年版） | **draft** | 官方统一入口页第 2 份附件；扫描件（文本层仅约 391 字符），需 OCR 才能全文入库; 内容与标题不匹配（title_bigram_ratio=0.11）：官方附件为扫描件，文本层仅约 456 字符，需 OCR; official annex PDF downloaded via browser context (WZWS) | https://www.nhc.gov.cn/ylyjs/gzdt/202407/256b4eb8398440a8811344c7be50a333.shtml |
| `LIFE001B` | 高脂血症营养和运动指导原则（2024年版） | **draft** | 官方统一入口页第 3 份附件；扫描件（文本层仅约 405 字符），需 OCR 才能全文入库; 内容与标题不匹配（title_bigram_ratio=0.11）：官方附件为扫描件，文本层仅约 472 字符，需 OCR; official annex PDF downloaded via browser context (WZWS) | https://www.nhc.gov.cn/ylyjs/gzdt/202407/256b4eb8398440a8811344c7be50a333.shtml |
| `LIFE001C` | 高尿酸血症营养和运动指导原则（2024年版） | **draft** | 官方统一入口页第 4 份附件；扫描件（文本层仅约 418 字符），需 OCR 才能全文入库; 内容与标题不匹配（title_bigram_ratio=0.05）：官方附件为扫描件，文本层仅约 503 字符，需 OCR; official annex PDF downloaded via browser context (WZWS) | https://www.nhc.gov.cn/ylyjs/gzdt/202407/256b4eb8398440a8811344c7be50a333.shtml |

### 5.1 建议的人工操作

> **禁止绕过任何付费墙或版权限制。** 以下为合规的正式获取途径。

| document_id | 建议操作 |
|---|---|
| `DM002` | 通过**机构订阅**（图书馆 / 医院订阅的中华医学期刊全文数据库）依法获取。《中华糖尿病杂志》2021;13(4):315-409，DOI `10.3760/cma.j.cn115791-20210221-00095` |
| `DM003` | 同上。《中华内科杂志》2022;61(3):249-262，DOI `10.3760/cma.j.cn112138-20220120-000063`。**或**找国家级中心官网的免费版 |
| `MULTI001` | 同 `DM002`；或改用已收录的 `MULTI002`（中国血脂管理指南 2023）作为多病共管域主要依据 |
| `LIFE001A/B/C` | 官方附件为**无文本层扫描件**。需 **OCR + 人工校对**后改回 `active`；校对前保持 `draft` |

---

## 6. 已知覆盖缺口

> 本节为**诚实清单**。状态严格区分 **已解决 / 部分解决 / 阻塞 / 无法合法获取**，
> 与 [`GAP_FIX_REPORT.md`](./GAP_FIX_REPORT.md) 一致。**不得把 BLOCKED 或无法合法获取写成已解决。**
>
> 🔧 **需要 OCR 的条目（6.2~6.4）有配套操作手册**：[`OCR_WORKFLOW.md`](./OCR_WORKFLOW.md) ——
> 生成草稿 → 逐页对照校对 → 校对产物与 `reviewed:` 标记 → 入库（含两个必踩的坑）。
> **OCR 结果未经人工校对不得置为 `active`。**

### 6.1 状态总览

| document_id | 状态 | 原因 | 影响 |
|---|---|---|---|
| `WHO001` `WHO002` `WHO003` | **已解决** | 改用新 IRIS API 直链取得完整 PDF | 已入库，KB_WHO 1412 切片 |
| `LIFE008A` | **已解决** | 释义附件文本层可用（2092 字符） | 已入库，4 切片 |
| **`PRIM003`** | **阻塞（FAILED）** | 官方 PDF 文字层损坏；**交接文档给的直链与已有文件 SHA256 相同** | 仅 281 字符元数据，1 切片 |
| **`CORE002`** | **阻塞（BLOCKED）** | 官方附件是**纯扫描件**（0 字符/10 页） | 保留发布页正文 476 字符，1 切片 |
| **`LIFE001`** | **部分解决** | 附件为扫描件（388 字符），用发布页正文 | 1325 字符，2 切片 |
| **`LIFE001A/B/C`** | **部分解决**（已置 draft） | 附件为扫描件（456/472/503 字符），内容与标题不符 | 各 1 个**不可检索**切片 |
| **`LIFE008`** | **部分解决** | 附件为单页扫描件（106 字符），用发布页正文 | 594 字符，1 切片 |
| **`DM002`** `DM003` `MULTI001` | **无法合法获取** | 付费墙 / 需机构授权 | 切片 0，已补 DOI 与正式出处 |

### 6.2 PRIM003 —— 阻塞，且"官方完整 PDF"就是同一份坏文件

> **最容易走弯路的点。** 交接文档给的「官方完整 PDF」直链：
> `https://www.nhc.gov.cn/ewebeditor/uploadfile/2016/01/20160128143208616.pdf`
>
> 实测：HTTP 200、`application/pdf`、**3,934,877 字节**、39 页，
> SHA256 = `f8e5ca3ba30fa29632dcc6a8c75573cac1142000858b2d0da4502e9864e4bb40`
> —— **与我们已有文件的 SHA256 完全相同，是同一份文件。**
>
> **即：下一个人不要再去追这个链接，它不会给出更好的文件。**

**该 PDF 文本层损坏的证据**（PyMuPDF 实测，全文 28,418 字符）：

| 码位区间 | 数量 | 含义 |
|---|---:|---|
| `U+00xx` 控制区 | 19,250 | 中文被映射到这里 |
| `U+FFxx` 全角区 | 6,739 | 数字/标点被映射成全角 |
| `U+72xx` | 234 | 26 个英文字母被映射到 CJK 区 |
| 常用汉字（的一是不了…） | **0** | 一个都没有 |

抽取样例：

```
犐犆犛１１．０２０ 犆０１ … 犠犛／犜４８４—２０１５ … 犎犲犪犾狋犺犿犪狀犪犵犲犿犲狀狋
（正确内容应为：ICS 11.020  C01 … WS/T 484—2015 … Health management）
```

**为什么无法程序性还原**：逐字符偏移**不恒定**（26 个字母对应 12 种不同偏移），
说明这是「字形索引 → Unicode」的**错误映射表**，不是简单位移，无法算术反推。

**当前处置**：以官方发布页元数据占位（281 字符），manifest `notes` 记录完整证据链。
**该 39 页 PDF 仍保留在 `knowledge/raw/07_primarycare/PRIM003.pdf` 待人工替换干净源。**

> **处置决策依据**：**不保留乱码正文。** 理由：乱码 Citation 直接违反契约
> 「**真实 Citation > 漂亮回答**」——与其给用户一段 `犐犆犛１１．０２０` 的引用，
> 不如不给。一个**不可读但格式合法**的 Citation 比"无证据"更危险，
> 因为它会让调用方误以为"有官方依据"。

**解决路径（按可行性排序）**（操作步骤见 [`OCR_WORKFLOW.md`](./OCR_WORKFLOW.md)）：
1. **OCR** 该 39 页 PDF → **人工校对数字**（`140` 可能被认成 `14O`）后入库；
2. 找**同一标准的其他官方电子版**（卫生标准网 / 国家标准全文公开系统 / 卫健委标准查询）；
3. 向标准发布机构索取带正确 `ToUnicode` 的电子版。

### 6.3 CORE002 / LIFE001 / LIFE008 —— 阻塞：官方附件是**扫描件**

> **最容易走弯路的点之二。** 这三篇的问题**不是"没抓到"**，
> 而是**官方发布的附件本身就是无文本层扫描件**——所以"替换为官方附件 PDF"**并不能解决**。

| document_id | 官方附件字节 | **文本层** | 处置 |
|---|---:|---:|---|
| `CORE002` | 1,934,953（10 页） | **0 字符** | 保留发布页正文（476 字符，含 `国卫办基层函〔2025〕439号` 等真实公文内容） |
| `LIFE001` | 5,473,222 | 388 字符 | 保留发布页正文（1325 字符） |
| `LIFE008` | 42,903（1 页） | 106 字符 | 保留发布页正文（594 字符） |

**这三份官方 PDF 均保留在 `knowledge/raw/` 下**，可直接用于 OCR。

### 6.4 LIFE001 拆分（部分解决）

按文档要求已拆成 4 个独立 `document_id`，**全部登记、分别保存、分别计算 SHA256**：

| document_id | 标题 | 附件字节 | 文本层 | `title_bigram_ratio` | 状态 |
|---|---|---:|---:|---:|---|
| `LIFE001` | 高血压营养和运动指导原则（2024年版） | 5,473,222 | 388 | 0.353 | active |
| `LIFE001A` | 高血糖症营养和运动指导原则（2024年版） | 6,580,831 | 391 | **0.111** | **draft** |
| `LIFE001B` | 高脂血症营养和运动指导原则（2024年版） | 5,580,591 | 405 | **0.111** | **draft** |
| `LIFE001C` | 高尿酸血症营养和运动指导原则（2024年版） | 5,483,126 | 418 | **0.053** | **draft** |

**关键发现**：4 份官方附件**全部是无文本层扫描件**（每份仅约 400 字符版式文字）。
`title_bigram_ratio` 0.053~0.111 说明**文件内容里几乎找不到标题字样**，证明抓到的不是正文。

**处置**：A/B/C **置为 `draft`**（生产检索只使用 active），文件与 SHA256 保留作为来源记录。
理由：把「内容与标题不匹配」的文件放进检索会污染 Citation，违背契约「真实 Citation > 漂亮回答」。

### 6.5 LIFE008 拆分（已解决）

| document_id | 标题 | 字节 | 正文 | `title_bigram_ratio` | 状态 |
|---|---|---:|---:|---:|---|
| `LIFE008` | 居民体重管理核心知识（2024年版） | 42,903 | 594 字符（发布页公文正文） | 1.0 | active |
| `LIFE008A` | 居民体重管理核心知识（2024年版）**释义** | 155,242 | **2092 字符，文本层可用** | 1.0 | active |

实测查询 `居民如何进行科学体重管理？` → **同时命中 `LIFE008` 与 `LIFE008A`**，引用可追溯。

### 6.6 日期元数据：仍不足以自动判定现行版本

| 字段 | 有值 | 说明 |
|---|---:|---|
| `publish_date` | **34/34** | 第三轮补齐，且修好了「注册表日期进不了 manifest」的 bug |
| `effective_date` | **2/34** | `PRIM003`=2016-04-01、`HTN001`=2026-03-01 |
| `replaced_by` | **0/34** | 仍全空 |

> **`effective_date` 32/34 为空是"正常现象，不是数据错误"**：
> 原文没有明确写「实施/施行/生效日期」的文档一律留空。
> 契约明令**禁止**用 `publish_date` 冒充、用网页发布日期代替、或按经验猜测。
>
> 并已新增**自动化不变量测试** `test_no_publish_date_was_used_as_effective_date`：
> 任何文档若 `effective_date == publish_date` 即判定"疑似冒充"并让测试失败。

**仍然存在的开放局限（重要，未解决）**：

> **`effective_date` 仍 32/34 为空 ⇒ 目前无法仅凭 manifest 自动判定"现行有效版本"。**
>
> 直接后果：契约中「**版本冲突时优先中国当前有效且适用于基层场景的正式规范**」
> （见 §2.2）**目前无法完全落地**。
>
> **缓解措施（当前做法）**：① 用 `status` 把废止版本标为 `superseded`（加载期即排除）；
> ② 用 `authority_level` 做权威加权。两者**只能缓解，不能替代**基于日期的现行性判定。

### 6.7 补入 WHO 全文后新发现的检索问题（已修复）

`KB_WHO` 从 9 切片暴涨到 1412 切片，暴露了两个新问题，**均已修复**：

| # | 问题 | 根因 | 修法 |
|---|---|---|---|
| 1 | **`WHO PEN 是什么？` 命中 0** | `who`/`pen` 出现在 1300+ 个 WHO 切片（页眉页脚），IDF 极低 → BM25 分仅 **4.39**，被 `score >= 12` 闸门拒绝。**绝对分阈值对"短缩写 + 大语料"天然失效** | 闸门增加**查询词覆盖率**分支，并要求 `matched >= 2`（否则"明天股市会涨还是跌"这类会被放行） |
| 2 | **WHO 长查询被路由到中文基层文档** | `KB_PRIMARYCARE` 关键词含裸「基层」，路由返回 `['KB_PRIMARYCARE','KB_WHO']`，中文基层文档凭中文词挤掉英文 WHO 文档 | 把裸「基层」换成 `基层医疗卫生机构`/`基层医疗`/`基层卫生`；「基层」是泛用限定词，单独出现不足以判定域 |

**修复后闸门**：`matched >= 3` **或** `score >= 12` **或** `(matched >= 2 且 coverage >= 0.8)`

标定结果（真实语料实测）：

| 规则 | 保住需要证据的查询 | 误留无关查询 |
|---|---|---|
| 旧规则 | 31/34 | **0/10** |
| 加 `coverage>=0.8`（无 `matched` 约束） | 33/34 | **4/10**（不可接受） |
| **最终规则** | **31/34** | **0/10** |

修法效果：`WHO PEN 对基层非传染性疾病管理提出了什么框架？` → `domains=['KB_WHO']`，
命中 **WHO001**，3 条 P4 引用全部可追溯。

### 6.8 其他已知问题

- **`P2` 等级 0 篇**：国家级医学中心来源尚未纳入（见 §1.3）。
- **`KB_DM` 仅 9 切片**：核心病种覆盖最薄弱（见 §1.2）。
- **3 篇英文与 31 篇中文混库**：跨语言检索能力有限（见 §1.3）。
- **`replaced_by` 全空**：无法机读表达"被哪一版取代"，只能靠 `status` 列。
- **`rag` 评测 1 个用例未通过**：`RAG-028` 期望文档集含 `LIFE001`（仍是扫描件），
  **属知识库覆盖不足，非检索缺陷**。

---

## 7. 切片参数与 verbatim 保证

### 7.1 参数（`knowledge/chunks/index_meta.json` → `params`）

| 参数 | 值 |
|---|---|
| 目标长度 | **500 ~ 900** 中文字符 |
| 重叠 | **80 ~ 150** 字符（`overlap_min_chars=80`，`overlap_chars=120`） |
| 硬上限 | **1200** 字符 |
| 切分边界 | `heading/paragraph/table-row only; never inside a clause or table row` |
| 内容策略 | `verbatim contiguous slice of knowledge/processed/<id>.md` |

结构顺序：**一级标题 → 二级标题 → 三级标题 → 段落**；
标题**不会孤立落在切片尾部**，也不会在没有后续内容时作为切片开头。

### 7.2 重叠与表格约束

- 重叠通过**重复上一块的整 unit（段落行）**实现 → **句子与表格行不会被切成两半**
- 表格**整体保留**；超大表格只在**行边界**切分，且**重复表头行**
- 遇到标题即停止向后取重叠（**不跨越标题边界**）
- **每个 unit 携带它在原文中的真实前置分隔符（`gap`）**，
  `join_units` 按真实分隔符拼接 —— 保证 `content` 与原文逐字一致（见 §7.4 缺陷 3）

### 7.3 verbatim 自检：2451/2451 通过

`scripts/build_chunks.py` 自带 verbatim 自检，逐条验证
`content` 是否为清洗后文档的**连续原文片段**。

**当前结果**（`index_meta.json` → `verification.verbatim_problems`）：

```json
"verification": { "verbatim_problems": [] }
```

即 **0 条问题，2451/2451 通过**（含 3 个 draft 切片）。

> 该结论已由我**独立复核**（不依赖脚本自身断言）：
> 对全部 2451 条切片断言 `chunk["content"] in open("knowledge/processed/<document_id>.md")`，
> 结果 **0 条失败**（命令见 §10 的 C3）。

### 7.4 修复过的真实缺陷

| # | 缺陷 | 症状 | 修复 |
|---|---|---|---|
| 1 | `apply_overlap()` 顺序倒转 | 原实现从前往后遍历上一块并 `insert(0, k)`，导致**重叠部分顺序被倒转**，`content` 不再是原文连续片段 | 改为从尾部倒着取整 unit（`for k in reversed(prev)`），遇标题即停 |
| 2 | `join_units()` 平白插入段落分隔 | 长段落被切开后，后续片段用空行拼接，**在原文中多出一个空行** | 新增 `glue=True` 标记，对 glue 片段用**空串粘连** |
| 3 | **`join_units` 对标题块凭空插空行** | 补入 WHO 全文后报 `WHO001-0509: content is not a verbatim slice`。WHO PDF 中有些行以 `####` 开头（流程图文字）被误判为标题块，`join_units` 一律用空行重连，而原文只有单个换行 | **让每个 unit 携带原文中的真实前置分隔符（`gap`）**，按真实分隔符拼接。修复后 verbatim **2451/2451 全部通过** |

> **遗留文档缺陷（不影响行为，但会误导读者）**：
> `build_chunks.py` 模块 docstring 仍写着
> "Overlap is taken by repeating whole **leading** blocks of the previous chunk"，
> 与修复后的实际行为（取上一块**末尾** unit）**不一致**。建议同步修正 docstring。

### 7.5 `title_bigram_ratio` —— 可复用的乱码/错源自动检测闸门

> **本项目最有价值的自动化质量检查手段**，由 `scripts/verify_content_match.py` 提供。

**原理**：把 manifest 的**登记标题**与下载文件的**开头正文**分别切成字符二元组（bigram），计算重叠率：

```python
ratio = |bigrams(registry_title) ∩ bigrams(head[:4000])| / |bigrams(registry_title)|
```

**判定阈值**（源码第 68 行）：

| 标记 | 条件 | 含义 |
|---|---|---|
| `OK  ` | `ratio >= 0.34` | 正文与标题高度重合 → 来源正确且**文本可读** |
| `??  ` | `0.15 <= ratio < 0.34` | 需人工复核 |
| `MISMATCH` | `ratio < 0.15` | 来源错误、正文缺失、**或编码损坏** |

**为什么能捕获乱码**：编码损坏会把标题字符变成完全不同的码位
（`WS/T` → `犠犛／犜`），二元组交集骤降为 0。

**当前实测（34 篇）**：

| 判定 | 篇数 | document_id（ratio） |
|---|---:|---|
| `OK`（≥0.34） | **26** | 多数为 1.0；`PRIM003(0.95)` `WHO001(0.857)` `WHO003(0.727)` `WHO002(0.633)` `LIFE001(0.353)` 等 |
| `??`（0.15~0.34） | **0** | — |
| `MISMATCH`（<0.15） | **8** | `CORE002(0.0)` `DM002(0.0)` `DM003(0.0)` `MULTI001(0.0)` **`LIFE001C(0.053)` `LIFE001A(0.111)` `LIFE001B(0.111)`** |

> **必须如实说明**：`MISMATCH` 的这些条目**全部是已知缺口，不是新增问题**——
> `CORE002` 发布页正文不含标题（已知缺口）；`DM002`/`DM003`/`MULTI001` 为 PENDING 无来源；
> **`LIFE001A/B/C` 正是该闸门"抓出来"的**——它们的低 ratio 直接证明了附件是无文本层扫描件，
> 从而支撑了"置为 draft"的决策。
>
> **该闸门的局限**：它比较的是**抓取到的原始文件开头**，
> **不是**清洗后的 Markdown，也**不是**最终切片。
> 因此 `ratio` 高**不能**保证 preprocess/chunks 阶段产出了足量内容——
> 例如 `PRIM003` 现在 `ratio=0.95`（元数据页与标题高度重合），
> 但它**只有 281 字符**。必须与 §7.3 的 verbatim 自检
> 以及 `_preprocess_report.json` 的 `chars` 列**配合使用**。

### 7.6 `content` 不写入 URL 与文件路径

**结论：`content` 字段不包含文件路径，也不包含由抓取过程注入的 URL。**

| 检查 | 结果 |
|---|---|
| 含**本地文件路径**（`knowledge/`、`C:\` 等）的切片 | **0 / 2451** |
| 含 `http://` 或 `https://` 的切片 | 少量（官方正文中的参考文献/引用书目，属原文内容） |

**关于 `preprocess_documents.py` 是否剔除 URL——已到脚本核实，结论是"部分成立"**：

| 对象 | 处理 | 核实位置 |
|---|---|---|
| 导航栏 / 面包屑 / 分享 / 页脚 | **整体剔除** | `DROP_TAGS`、`DROP_CLASS_PAT` |
| 正文 `<a>` 锚点 | **只保留锚文本，丢弃 `href`** | `element_md()` 对 `a` 无专门分支，仅递归取文本 |
| 正文 `<img>` 图片引用 | **保留 `src`** | `element_md()`：输出 Markdown 图片语法 |
| 正文参考文献里的裸 URL | **保留**（属原文内容，不应删除） | — |

> 因此**不能说"脚本会把 URL 全部剔除"**。准确表述是：
> **导航类链接被剔除；正文锚点的 `href` 被丢弃；URL 只在正文本身含有时才保留。**

---

## 8. 复现命令

### 8.1 脚本清单

| 脚本 | 用途 | 需要联网 | 需要凭据 |
|---|---|---|---|
| `scripts/download_documents.py` | 抓取官方页面 + 附件 PDF | 是 | 否（Playwright） |
| `scripts/playwright_fetch.py` | WZWS 挑战突破（被上者调用） | 是 | 否 |
| `scripts/download_attachments.py` | 附件 PDF 下载兜底 | 是 | 否 |
| `scripts/extract_publish_dates.py` | 抽发布/实施日期 → `_dates.json` | 否 | 否 |
| `scripts/build_manifest.py` | 生成 manifest CSV（UTF-8 BOM） | 否 | 否 |
| `scripts/preprocess_documents.py` | HTML/PDF → Markdown 清洗 | 否 | 否 |
| `scripts/build_chunks.py` | 切片 + verbatim 自检 | 否 | 否 |
| `scripts/validate_manifest.py` | manifest 结构与枚举校验 | 否 | 否 |
| `scripts/verify_sources.py` | 来源核验（尊重 `MANIFEST_PATH`，支持 `--manifest`） | 仅 `--online` | 否 |
| `scripts/verify_content_match.py` | `title_bigram_ratio` 乱码/错源闸门 | 否 | 否 |
| `scripts/sync_qianfan.py` | 同步到千帆（按域聚合上传） | 是 | **需千帆凭据** |
| `scripts/evaluate.py` | 离线评测 → `eval/REPORT.md` | 否（mock） | 否 |
| `scripts/smoke_test.py` | 端到端 Smoke Test（14 项） | 否 | 否 |

> **`scripts/sync_qianfan.py` 的真实同步路径尚未用凭据验证（BLOCKED）**——
> 该脚本自身 docstring 已标注：千帆接口在不同平台版本间路径与入参存在差异，
> 上线前必须按当期官方文档核对。同步粒度为**按域聚合为整篇文档上传**，**不是逐 chunk 上传**。

### 8.2 按真实顺序复现

```bash
# 1) 采集（需要联网；www.nhc.gov.cn 走 Playwright 突破 WZWS）
python scripts/download_documents.py

# 2) 抽日期 + 生成 manifest
python scripts/extract_publish_dates.py
python scripts/build_manifest.py

# 3) 清洗（离线）
python scripts/preprocess_documents.py

# 4) 切片 + verbatim 自检（离线）
python scripts/build_chunks.py

# 5) 校验（离线）
python scripts/validate_manifest.py       # 必须 VALIDATION PASSED
python scripts/verify_sources.py          # 必须 VERIFY PASSED
python scripts/verify_content_match.py    # 乱码/错源闸门
```

**依赖说明**：第 1 步需 `requirements-knowledge.txt`（Playwright + PyMuPDF + BeautifulSoup）；
其余只需 `requirements.txt`。**全流程在 `AI_PROVIDER=mock` 下即可完成，不需要千帆凭据。**

> **幂等性**：`build_chunks.py` 可重复运行且结果稳定——
> 实测重跑输出与 `index_meta.json` 完全一致：
> `total=2451`，`size stats {"min": 9, "max": 1200, "mean": 559.9, "under_min": 311, "over_max": 62}`。

### 8.3 本次实测输出（原文粘贴）

> 以下均为 **2026-09-17（第三轮补数据后）** 在本仓库实际执行的真实输出。

**`python scripts/validate_manifest.py`**：

```
checks: {"rows": 34, "active": 28, "draft": 6, "distinct_document_ids": 34, "bom": 1, "errors": 0, "warnings": 0}
VALIDATION PASSED
```

**`python scripts/verify_sources.py`**：

```
offline errors:   0
offline warnings: 0
VERIFY PASSED
```

**`python -m pytest tests/test_live_knowledge.py`**：

```
11 passed in 0.31s
```

**`python scripts/verify_content_match.py`** ——34 篇判定摘要（完整输出写入
`knowledge/raw/_content_check.json`）：

```
OK       ：26 篇（多数 ratio=1.0；PRIM003 0.95 / WHO001 0.857 / LIFE008A 1.0 …）
??       ： 0 篇
MISMATCH ： 8 篇（CORE002 0.0、DM002 0.0、DM003 0.0、MULTI001 0.0、
                 LIFE001C 0.053、LIFE001A 0.111、LIFE001B 0.111）
```

> `MISMATCH` 各篇均为**已知缺口**（见 §7.5），非错源。

**全仓测试**（`python -m pytest tests/`）：

```
521 passed in 4.51s
```

（**历史值**：第二轮修复后 `436 passed`；第三轮 `497 passed`；更早（产物就绪前）`399 passed, 11 skipped`。）

**评测**（`python scripts/evaluate.py --provider mock`）：

```
extraction   cases=32   pass=32   rate=100.00%  hallucination_rate=0.0
routing      cases=28   pass=28   rate=100.00%  domain_recall=1.0
rag          cases=32   pass=31   rate=96.88%   recall_at_k=0.9667
citation     cases=22   pass=22   rate=100.00%  false_citation_count=0.0
no_evidence  cases=12   pass=12   rate=100.00%  no_evidence_accuracy=1.0
safety       cases=24   pass=24   rate=100.00%  block_decision_accuracy=1.0
injection    cases=18   pass=18   rate=100.00%  injection_bypass_count=0.0
```

---

## 9. 与 RAG 的衔接

### 9.1 chunk 字段 → `RetrievedChunk` 映射

| chunk 字段 | `RetrievedChunk` | 说明 |
|---|---|---|
| `chunk_id` | 是（`chunk_id`） | 全局唯一（`<document_id>-<序号>`） |
| `document_id` | 是（`document_id`） | 关联 manifest |
| `title` / `section` / `section_path` | 是（同名） | 章节层级，供 Citation 定位 |
| `authority` / `authority_level` / `version` / `effective_date` | 是（同名） | 权威信息 |
| `source_url` | 是（`source_url`） | **Citation 以 manifest 为准**（manifest 优先） |
| `content` | 是（`content`） | verbatim 原文片段 → `Citation.quote` 的来源 |
| `diseases` / `scenarios` | 不进入 schema | 仅用于 manifest 域过滤（`documents_for_domains`） |
| `char_count` | 不进入 schema | 构建期统计 |
| — | 额外 `score` | 检索期打分（RRF 融合 + 权威加权后） |
| — | 额外 `retrieval_source` | `local_bm25` 或千帆 KB |

> **chunk 里没有 `publish_date`**（放的是 `effective_date`）。chunk schema 是既有契约
> （`RetrievalService`/`CitationService` 依赖），新增字段需同步改多处。
> `publish_date` 已在 **manifest 与 Citation 输出链路**上可用。
> **如确需下发到 chunk，请先确认。**

### 9.2 Citation 只能来自 `status=active` 文档

`CitationService._validate()` 的三重校验（详见
[`RAG_ARCHITECTURE.md` §5](./RAG_ARCHITECTURE.md)）要求：
文档**存在于 manifest** 且 **`status == "active"`**，否则引用被丢弃并记入
`data.dropped_citations`（`reason` = `document_not_in_manifest` / `document_not_active`）。

配合 §2.4 的**加载期过滤**，形成双重保障：
**draft 文档既进不了索引，也过不了引用校验。**
这正是 `LIFE001A/B/C` 被置 draft 的意义——它们的不可靠内容**不可能出现在任何 Citation 中**。

### 9.3 相关性闸门与权威加权

| 参数 | 默认值 | 环境变量 | 作用 |
|---|---:|---|---|
| `rag_min_relevance_score` | **12.0** | `RAG_MIN_RELEVANCE_SCORE` | BM25 绝对分下限 |
| `rag_min_matched_terms` | **3** | `RAG_MIN_MATCHED_TERMS` | 命中词数下限 |

**当前完整闸门**（第三轮修订，见 §6.7）：

```
matched >= 3  或  score >= 12  或  (matched >= 2 且 coverage >= 0.8)
```

> **这些是经验校准值，换语料必须重新标定。**
> 它们与 BM25 原始分数量级强相关；更换分词方式、语料规模或语言分布后可能过松或过严。
> 标定方法：用 `eval/datasets/rag_cases.jsonl` 与 `no_evidence_cases.jsonl`
> 跑 `scripts/evaluate.py`，观察命中率与无证据率的变化。
>
> `who`/`pen` 被 `score>=12` 拦死的案例（§6.7）就是
> **绝对分阈值对"短缩写 + 大语料"失效**的实证。

---

## 10. 统计口径

> 本文档所有数字的复现方式。命令均在仓库根目录执行（Python 3.14）。

### 10.1 核心计数（§1、§3）

| 数字 | 口径 | 命令 |
|---|---:|---|
| 登记 34 / active 28 / draft 6 | manifest 行数与 `status` 列计数 | **C1** |
| `chunks.jsonl` 2451 | 文件非空行数 | **C2** |
| **可检索 2448** | chunks 按 `document_id` join manifest 的 `status`，只数 `active` | **C2** |
| 产出切片的文档 31 | chunks 中 `document_id` 去重计数 | **C2** |
| 清洗总字符 1353633 | `_preprocess_report.json` → `summary.total_chars` | **C1** |
| 各 `KB_*` 文档数/切片数 | manifest `qianfan_kb` 计数 + chunks join | **C1**/**C2** |
| `publish_date` 34/34、`effective_date` 2/34 | 非空值计数 | **C1** |

**C1** — manifest 统计：

```bash
python -c "import csv,collections;r=list(csv.DictReader(open('knowledge/manifest/knowledge_manifest.csv',encoding='utf-8-sig')));print('rows',len(r));print(collections.Counter(x['status'] for x in r));print(collections.Counter(x['qianfan_kb'] for x in r));print('pub',sum(1 for x in r if x['publish_date'].strip()),'eff',sum(1 for x in r if x['effective_date'].strip()))"
```

**C2** — 切片统计（含「可检索」口径）：

```bash
python -c "import csv,json;rows=list(csv.DictReader(open('knowledge/manifest/knowledge_manifest.csv',encoding='utf-8-sig')));st={r['document_id']:r['status'] for r in rows};c=[json.loads(l) for l in open('knowledge/chunks/chunks.jsonl',encoding='utf-8') if l.strip()];print('lines',len(c));print('active',sum(1 for x in c if st[x['document_id']]=='active'));print('draft',sum(1 for x in c if st[x['document_id']]!='active'))"
```

### 10.2 verbatim 独立复核（§7.3）

**C3** — 不依赖脚本自身断言，逐条验证 `content` 是 `knowledge/processed/<id>.md` 的连续子串：

```bash
python -c "import json;from pathlib import Path;c=[json.loads(l) for l in open('knowledge/chunks/chunks.jsonl',encoding='utf-8') if l.strip()];s={f.stem:f.read_text(encoding='utf-8') for f in Path('knowledge/processed').glob('*.md')};bad=[x['chunk_id'] for x in c if x['content'] not in s[x['document_id']]];print('checked',len(c),'failures',len(bad),bad[:5])"
```

### 10.3 切片长度分布（§7.1）

```bash
python -c "import json;print(json.load(open('knowledge/chunks/index_meta.json',encoding='utf-8'))['size_stats'])"
```

### 10.4 PDF 文本层字符数（§4.2、§6.3）

用 PyMuPDF 逐页 `get_text("text")` 求和：

```bash
python -c "import pymupdf,glob;[print(p, len(''.join(pg.get_text('text') for pg in pymupdf.open(p)))) for p in glob.glob('knowledge/raw/**/*.pdf',recursive=True)]"
```

### 10.5 下载状态（§4.3）

```bash
python -c "import json;d=json.load(open('knowledge/raw/_download_report.json',encoding='utf-8'));print(d['summary'])"
```

### 10.6 质量闸门判定（§7.5）

```bash
python scripts/verify_content_match.py
```

### 10.7 验证命令（§8.3）

```bash
python scripts/validate_manifest.py
python scripts/verify_sources.py
python -m pytest tests/test_live_knowledge.py -q
python -m pytest tests/
python scripts/evaluate.py --provider mock
```

### 10.8 本文档中未使用的数据源

为避免误导，明确列出本文**没有**引用/推断的内容：

- **没有**任何"医学准确率"指标——语料正确性需临床专家评审，自动化指标无法覆盖
- **没有**使用外部权威排名或第三方评估结果
- **没有**使用第三方转载或绕过付费墙取得的全文
- `effective_date` 相关结论**仅陈述有值行数与依据**，未对缺失做推断
- **没有**验证 `sync_qianfan.py` 的真实同步行为（路径未经凭据验证，BLOCKED）

---

## 相关文档

- [`GAP_FIX_REPORT.md`](./GAP_FIX_REPORT.md) —— 本轮缺口修复的逐项判定与证据（**缺口状态的权威来源**）
- [`DATA_GAPS.md`](./DATA_GAPS.md) —— 给"去找资料的人"的行动清单（含每条的当前状态）
- [`OCR_WORKFLOW.md`](./OCR_WORKFLOW.md) —— **扫描件 OCR 草稿生成 → 人工校对 → 入库流程**（校对后才可置 active）
- [`RAG_ARCHITECTURE.md`](./RAG_ARCHITECTURE.md) —— 检索链路、BM25/RRF、Citation 校验、降级矩阵
- [`API.md`](./API.md) —— 端点契约、`domains` 与 `patient_context` 约束、输入归一化
- [`SAFETY.md`](./SAFETY.md) —— 安全边界与已知局限
- `knowledge/chunks/index_meta.json` —— 切片参数与自检结果的机器可读版本
