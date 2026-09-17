# CareFlow 康脉智护 —— 官方知识库说明

> 面向读者：接手人、运维、医学同事、合规评审
> 本文档中的所有统计数字均**从真实产物现场计算**，复现方式见文末 [§10 统计口径](#10-统计口径)。
> 生成日期：2026-09-17

---

## 目录

1. [概览](#1-概览)
2. [权威等级策略](#2-权威等级策略)
3. [来源总表](#3-来源总表)
4. [下载与还原过程](#4-下载与还原过程)
5. [人工下载清单（未获取条目）](#5-人工下载清单未获取条目)
6. [已知覆盖缺口](#6-已知覆盖缺口)
7. [切片参数与 verbatim 保证](#7-切片参数与-verbatim-保证)
8. [复现命令](#8-复现命令)
9. [与 RAG 的衔接](#9-与-rag-的衔接)
10. [统计口径](#10-统计口径)

---

## 1. 概览

### 1.1 核心数字

| 指标 | 数值 | 来源 |
|---|---:|---|
| manifest 登记文档 | **30** | `knowledge_manifest.csv` 行数 |
| `status=active` | **27** | manifest `status` 列 |
| `status=draft` | **3** | 同上（全部为付费墙/登录墙，未获取） |
| 切片总数 | **1041** | `knowledge/chunks/chunks.jsonl` 行数 |
| 产出切片的文档数 | **27** | chunks 中 distinct `document_id` |
| 清洗后正文总字符 | **612852** | `_preprocess_report.json` → `summary.total_chars` |
| 本地检索索引 | BM25 内存索引（启动时从 chunks 重建） | `app/services/retrieval_service.py` |

> **一致性**：登记 30 = active 27 + draft 3；切片来自且仅来自 27 篇 active 文档。
> 3 篇 draft 文档**切片数为 0**（详见 [§5](#5-人工下载清单未获取条目)）。
>
> **修订记录（2026-09-17）**：原先 `PRIM003` 以损坏的 PDF 为正文来源，
> 产出 **60 个乱码切片**（详见 [§6.5](#65-prim003-的已处置记录原-pdf-文本层编码损坏)）。
> 弃用该 PDF、改用官方发布页 HTML 后，切片总数 **1100 → 1041**、
> 总字符 **645646 → 612852**。
### 1.2 八个知识域分布

| 知识域 | 文档数 | 切片数 | 主题 |
|---|---:|---:|---|
| `KB_LIFESTYLE` | 8 | **460** | 营养、运动、体重、食养指南 |
| `KB_CORE` | 6 | **234** | 基层慢病总体管理、健康素养 |
| `KB_MULTIMORBIDITY` | 2 | **222** | 血脂、多病共管 |
| `KB_HTN` | 3 | **70** | 高血压 |
| `KB_PRIMARYCARE` | 3 | **21** | 基层随访、家庭医生、老年健康 |
| `KB_COPD` | 2 | **16** | 慢阻肺 |
| `KB_DM` | 3 | **9** | 糖尿病 |
| `KB_WHO` | 3 | **9** | WHO 国际补充 |
| **合计** | **30** | **1041** | |

> ⚠️ **`KB_PRIMARYCARE` 因 PRIM003 处置而大幅缩小：80 → 21 切片**。
> 该域 3 篇中，`PRIM003`（P0 标准 WS/T 484—2015）现在只剩 **1 个切片（281 字符元数据）**。
> 详见 [§6.5](#65-prim003-的已处置记录原-pdf-文本层编码损坏)。
>
> ⚠️ **`KB_DM` 覆盖薄弱**：登记 3 篇，其中 2 篇（`DM002`、`DM003`）为 draft 未获取，
> **仅 `DM001` 一篇产出 9 个切片**。糖尿病是基层慢病核心病种，这里是**最需要补齐的域**。
> `KB_COPD`（16 切片 / 2 篇）与 `KB_WHO`（9 切片 / 3 篇）同样偏薄。
### 1.3 文档类型与权威等级分布

| `document_type` | 篇数 | | `authority_level` | 篇数 |
|---|---:|---|---|---:|
| `nhc_policy` | 20 | | `P0` | 2 |
| `professional_guideline` | 4 | | `P1` | 20 |
| `who_guideline` | 3 | | `P2` | **0** |
| `national_standard` | 2 | | `P3` | 5 |
| `expert_consensus` | 1 | | `P4` | 3 |

> ⚠️ **当前语料中没有 `P2` 条目**（国家级医学中心）。等级并非按制度齐备填充，
> 而是按实际来源如实标注；`P2` 留空表示"尚无该等级文档"，不是遗漏。

---

## 2. 权威等级策略

### 2.1 等级定义

| 等级 | 语义 | 典型来源 | 本库篇数 |
|---|---|---|---:|
| `P0` | 国家现行卫生标准（行业标准 WS/T） | 国家卫生健康委发布的国家标准 | 2 |
| `P1` | 国家卫健委正式文件 | 卫健委通知、指南、服务规范 | 20 |
| `P2` | 国家级医学中心 | 国家心血管病中心等 | **0** |
| `P3` | 中华医学会 / 国家级专业组织 | 学会指南、专家共识 | 5 |
| `P4` | WHO 等国际权威补充 | WHO 技术包 | 3 |

`P0` 的两条：`HTN001`（WS/T 872—2025 基层医疗卫生机构高血压防治管理标准）、
`PRIM003`（WS/T 484—2015 老年人健康管理技术规范）。

### 2.2 冲突处理原则

> **当不同等级来源出现差异时，优先采用「中国当前有效且适用于基层场景的正式规范」。**

理由：本系统的服务对象是**基层慢病共管与随访**，因此
① 优先中国现行标准/卫健委文件（P0/P1），② 国际资料（P4）作为补充而非替代。
等级是**排序与解释的依据**，不是自动裁决——最终临床判断仍由医生作出。

### 2.3 代码落地：`AUTHORITY_BOOST`

检索排序对权威等级做**加权**（不是硬过滤），定义于
`app/services/retrieval_service.py`：

```python
AUTHORITY_BOOST: dict[str, float] = {
    "P0": 1.25,
    "P1": 1.15,
    "P2": 1.05,
    "P3": 1.00,
    "P4": 0.95,
}
```

- 加权发生在**检索打分的最后一步**（`_apply_authority`）：`_score *= AUTHORITY_BOOST[level]`
- 未识别的等级回退系数 `1.0`
- **语义是"同等相关性下高权威优先"，不删除低权威文档**

### 2.4 生产检索只用 `status=active`

`KnowledgeStore._load_chunks()` 在**加载阶段**即做过滤：

```python
# 只索引 active 文档的切片 —— 生产检索禁用 superseded/draft/disabled
entry = self.entries.get(chunk.document_id)
if entry is not None and not entry.is_active:
    continue
```

因此 `superseded` / `draft` / `disabled` 文档的切片**物理上不进入 BM25 索引**，
比"检索时再过滤"更安全。这也解释了为什么 3 篇 draft 文档虽然登记在 manifest，
却对检索完全不可见。

---

## 3. 来源总表

> 全部字段从 `knowledge/manifest/knowledge_manifest.csv`（UTF-8 with BOM）现场读取；
> 「切片数」从 `knowledge/chunks/chunks.jsonl` 按 `document_id` 统计。
> `—` 表示 manifest 中该字段**为空**（非本文档省略）。

| document_id | 标题 | 发布机构 | 等级 | 版本 | 发布日期 | 有效日期 | 状态 | 知识域 | 来源 URL | 本地文件 | 切片数 |
|---|---|---|---|---|---|---|---|---|---|---|---:|
| `CORE001` | 关于加强基层慢性病健康管理服务的指导意见 | 国家卫生健康委等 | P1 | 2025 | 2025-10-29 | — | active | KB_CORE | [链接](https://www.nhc.gov.cn/jws/c100073/202510/3974d142eb1c4dd385b6e880f8617dcc.shtml) | `knowledge/raw/01_core/CORE001.html` | 5 |
| `CORE002` | 基层慢性病健康管理服务能力建设指引 | 国家卫生健康委 | P1 | 2025 | 2025-11-20 | — | active | KB_CORE | [链接](https://www.nhc.gov.cn/jws/c100073/202511/d3b6755fe7004cdeac938bf77b6a4a80.shtml) | `knowledge/raw/01_core/CORE002.html` | 1 |
| `CORE003` | 国家基本公共卫生服务规范（第三版） | 国家卫生计生委 | P1 | 第三版 | 2017-03-28 | — | active | KB_CORE | [链接](https://www.nhc.gov.cn/jws/s3578/201703/d20c37e23e1f4c7db7b8e25f34473e1b.shtml) | `knowledge/raw/01_core/CORE003.html` | 151 |
| `CORE004` | 关于做好2025年基本公共卫生服务工作的通知 | 国家卫生健康委等 | P1 | 2025 | 2025-06-26 | — | active | KB_CORE | [链接](https://www.nhc.gov.cn/jws/c100073/202506/14a23782324542f59137bbf24a1c988f.shtml) | `knowledge/raw/01_core/CORE004.html` | 4 |
| `CORE005` | 中国公民健康素养——基本知识与技能（2024年版） | 国家卫生健康委 | P1 | 2024版 | 2024-05-30 | — | active | KB_CORE | [链接](https://www.nhc.gov.cn/xcs/c100123/202405/73a4927142f34152abed875634a3c13b.shtml) | `knowledge/raw/01_core/CORE005.html` | 3 |
| `CORE006` | 中国公民健康素养——基本知识与技能释义（2024年版） | 国家卫生健康委 | P1 | 2024版 | 2024-05-30 | — | active | KB_CORE | [链接](https://www.nhc.gov.cn/xcs/c100122/202405/f251e896a50a49ff8c632b4b3da93126.shtml) | `knowledge/raw/01_core/CORE006.html` | 70 |
| `HTN001` | 基层医疗卫生机构高血压防治管理标准 WS/T 872—2025 | 国家卫生健康委 | P0 | WS/T 872—2025 | 2025-09-30 | 2026-03-01 | active | KB_HTN | [链接](https://www.nhc.gov.cn/wjw/c100309/202509/b601cb822b25461f92f7aa66c03495a8.shtml) | `knowledge/raw/02_hypertension/HTN001.html` | 7 |
| `HTN002` | 国家基层高血压防治管理指南 2025版 | 国家心血管病中心 | P3 | 2025版 | — | — | active | KB_HTN | [链接](https://hbp-office.nccd.org.cn/download.html) | `knowledge/raw/02_hypertension/HTN002.html` | 57 |
| `HTN003` | 健康中国行动—心脑血管疾病防治行动实施方案（2023—2030年） | 国家卫生健康委等 | P1 | 2023—2030 | 2023-11-14 | — | active | KB_HTN | [链接](https://www.nhc.gov.cn/ylyjs/gzdt/202311/a40dcf8a65314b818c46c9d1e683b9c3.shtml) | `knowledge/raw/02_hypertension/HTN003.html` | 6 |
| `DM001` | 健康中国行动——糖尿病防治行动实施方案（2024—2030年） | 国家卫生健康委等 | P1 | 2024—2030 | 2025-06-06 | — | active | KB_DM | [链接](https://www.nhc.gov.cn/wjw/c100375/202407/752d85bddda5420eb1c1fe3c2772a100.shtml) | `knowledge/raw/03_diabetes/DM001.html` | 9 |
| `DM002` | 中国2型糖尿病防治指南（2020年版） | 中华医学会糖尿病学分会 | P3 | 2020版 | — | — | draft | KB_DM | [链接](https://rs.yiigle.com/CN2021/1315505.htm) | `PENDING` | 0 |
| `DM003` | 国家基层糖尿病防治管理指南（2022） | 国家基层糖尿病防治管理办公室 | P3 | 2022 | — | — | draft | KB_DM | [链接](https://drugs.dxy.cn/pc/clinicalGuidelines/pFt03XqSDLS5Swuag1he4yw) | `PENDING` | 0 |
| `COPD001` | 慢性阻塞性肺疾病患者健康服务规范（试行） | 国家卫生健康委 | P1 | 试行 | 2024-09-13 | — | active | KB_COPD | [链接](https://www.nhc.gov.cn/jws/c100073/202409/ad3c2a8221184272872a31ae400ecd37.shtml) | `knowledge/raw/04_copd/COPD001.html` | 10 |
| `COPD002` | 健康中国行动——慢性呼吸系统疾病防治行动实施方案（2024—2030年） | 国家卫生健康委等 | P1 | 2024—2030 | 2024-07-29 | — | active | KB_COPD | [链接](https://www.nhc.gov.cn/ylyjs/gzdt/202407/eee1c5827dc84989907d9e4cb2d24c4b.shtml) | `knowledge/raw/04_copd/COPD002.html` | 6 |
| `MULTI001` | “三高”共管规范化诊疗中国专家共识（2023版） | 中华医学会等 | P3 | 2023版 | — | — | draft | KB_MULTIMORBIDITY | [链接](https://rs.yiigle.com/CN2021/1467649.htm) | `PENDING` | 0 |
| `MULTI002` | 中国血脂管理指南（2023年） | 中国血脂管理指南修订联合专家委员会 | P3 | 2023 | 2023-04-15 | — | active | KB_MULTIMORBIDITY | [链接](https://www.sinocardiomed.com/wp-content/uploads/2023/04/2023041513592396.pdf) | `knowledge/raw/05_multimorbidity/MULTI002.pdf` | 222 |
| `LIFE001` | 高血压等慢性病营养和运动指导原则（2024年版） | 国家卫生健康委 | P1 | 2024版 | 2024-07-01 | — | active | KB_LIFESTYLE | [链接](https://www.nhc.gov.cn/ylyjs/gzdt/202407/256b4eb8398440a8811344c7be50a333.shtml) | `knowledge/raw/06_lifestyle/LIFE001.html` | 2 |
| `LIFE002` | 成人高血压食养指南（2023年版） | 国家卫生健康委 | P1 | 2023版 | 2023-01-18 | — | active | KB_LIFESTYLE | [链接](https://www.nhc.gov.cn/sps/c100088/202301/f01895a06c5349ef999f25da833c166d.shtml) | `knowledge/raw/06_lifestyle/LIFE002.html` | 62 |
| `LIFE003` | 成人糖尿病食养指南（2023年版） | 国家卫生健康委 | P1 | 2023版 | 2023-01-18 | — | active | KB_LIFESTYLE | [链接](https://www.nhc.gov.cn/sps/c100088/202301/f01895a06c5349ef999f25da833c166d.shtml) | `knowledge/raw/06_lifestyle/LIFE003.html` | 74 |
| `LIFE004` | 成人高脂血症食养指南（2023年版） | 国家卫生健康委 | P1 | 2023版 | 2023-01-18 | — | active | KB_LIFESTYLE | [链接](https://www.nhc.gov.cn/sps/c100088/202301/f01895a06c5349ef999f25da833c166d.shtml) | `knowledge/raw/06_lifestyle/LIFE004.html` | 42 |
| `LIFE005` | 成人高尿酸血症与痛风食养指南（2024年版） | 国家卫生健康委 | P1 | 2024版 | 2024-02-08 | — | active | KB_LIFESTYLE | [链接](https://www.nhc.gov.cn/sps/c100088/202402/9ba512ba8e314a47a181db11d2fa188d.shtml) | `knowledge/raw/06_lifestyle/LIFE005.html` | 81 |
| `LIFE006` | 成人肥胖食养指南（2024年版） | 国家卫生健康委 | P1 | 2024版 | 2024-02-08 | — | active | KB_LIFESTYLE | [链接](https://www.nhc.gov.cn/sps/c100088/202402/9ba512ba8e314a47a181db11d2fa188d.shtml) | `knowledge/raw/06_lifestyle/LIFE006.html` | 95 |
| `LIFE007` | 成人慢性肾脏病食养指南（2024年版） | 国家卫生健康委 | P1 | 2024版 | 2024-02-08 | — | active | KB_LIFESTYLE | [链接](https://www.nhc.gov.cn/sps/c100088/202402/9ba512ba8e314a47a181db11d2fa188d.shtml) | `knowledge/raw/06_lifestyle/LIFE007.html` | 103 |
| `LIFE008` | 居民体重管理核心知识（2024年版）及释义 | 国家卫生健康委 | P1 | 2024版 | 2024-07-02 | — | active | KB_LIFESTYLE | [链接](https://www.nhc.gov.cn/ylyjs/gzdt/202407/9ec6136773bc41048a39f275fcc37b44.shtml) | `knowledge/raw/06_lifestyle/LIFE008.html` | 1 |
| `PRIM001` | 居民电子健康档案首页基本内容（试行） | 国家卫生健康委 | P1 | 试行 | 2024-06-21 | — | active | KB_PRIMARYCARE | [链接](https://www.nhc.gov.cn/jws/c100073/202406/f6520c3818c34637ab5f9d3d5232aaf3.shtml) | `knowledge/raw/07_primarycare/PRIM001.html` | 8 |
| `PRIM002` | 家庭医生签约基本服务包清单（试行） | 国家卫生健康委 | P1 | 试行 | 2025-04-15 | — | active | KB_PRIMARYCARE | [链接](https://www.nhc.gov.cn/jws/c100073/202504/57fa208d505041168bcf192331a129d2.shtml) | `knowledge/raw/07_primarycare/PRIM002.html` | 12 |
| `PRIM003` | 老年人健康管理技术规范 WS/T 484—2015 | 国家卫生计生委 | P0 | WS/T 484—2015 | 2015-11-16 | 2016-04-01 | active | KB_PRIMARYCARE | [链接](https://www.nhc.gov.cn/wjw/c100309/201511/6725aa6b7b6846058e3abf6ab3ee32d4.shtml) | `knowledge/raw/07_primarycare/PRIM003.html` | 1 |
| `WHO001` | WHO PEN (Package of essential NCD interventions) | World Health Organization | P4 | 2nd edition | — | — | active | KB_WHO | [链接](https://www.who.int/publications/i/item/9789240009226) | `knowledge/raw/08_who/WHO001.html` | 2 |
| `WHO002` | WHO HEARTS: Risk-based CVD Management | World Health Organization | P4 | HEARTS technical package | — | — | active | KB_WHO | [链接](https://www.who.int/publications/i/item/9789240001367) | `knowledge/raw/08_who/WHO002.html` | 3 |
| `WHO003` | WHO HEARTS: Healthy-lifestyle counselling | World Health Organization | P4 | HEARTS technical package | — | — | active | KB_WHO | [链接](https://www.who.int/publications/i/item/WHO-NMH-NVI-18-1) | `knowledge/raw/08_who/WHO003.html` | 4 |

### 3.1 表格字段说明

| 列 | manifest 列名 | 说明 |
|---|---|---|
| 发布机构 | `authority` | 发布/归口机构原文 |
| 版本 | `version` | 版本标识（如 `2025`、`第三版`、`WS/T 872—2025`） |
| 发布日期 | `publish_date` | **23/30 行有值**（见下） |
| 有效日期 | `effective_date` | **2/30 行有值**（`HTN001` 2026-03-01、`PRIM003` 2016-04-01） |
| 状态 | `status` | `active` / `superseded` / `draft` / `disabled` |
| 知识域 | `qianfan_kb` | 八个 `KB_*` 之一，同时对应千帆知识库 ID |
| 本地文件 | `local_file` | 抽取所用的**主**源文件（HTML 或 PDF） |

> **日期字段现状（已改善，仍不完整）**：
> `publish_date` **23/30 行有值**（由 `scripts/extract_publish_dates.py` 抽取）；
> 为空的 7 行恰好是：3 篇 PENDING（`DM002`/`DM003`/`MULTI001`）
> 与 4 篇无机读发布日期的来源（`HTN002` 期刊版、`WHO001`/`WHO002`/`WHO003` 出版页）。
> `effective_date` 仅 **2/30**（`HTN001`、`PRIM003`），`replaced_by` **0/30**。
>
> **残余影响与开放局限**（完整分析见 [§6.6](#66-日期元数据已从全空改善但仍不足以自动判定现行版本)）：
> ① 28/30 文档的 Citation `effective_date` 为空串（仅 `HTN001`、`PRIM003` 两个文档的 8 个切片携带）；
> ② **`effective_date` 仍不足以自动判定"现行有效版本"**，
> 因此契约「版本冲突优先现行有效规范」目前只能靠 `status` + `authority_level` 缓解，无法完全落地。
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
| 4 | 完成判据 | `inner_text("body")` 的长度 ≥ `min_text_chars` 且**不匹配** `CHALLENGE_MARKERS` |
| 5 | 下载附件必须复用**同一个 BrowserContext** | 用 `ctx.request.get(...)`；新开 context 则 WAF cookie 不在，照样 412 |

挑战标记常量：

```python
CHALLENGE_MARKERS = ("$_ts", "wzws", "请稍候", "安全验证", "Checking your browser")
```

### 4.2 附件兜底（页面正文极短时）

部分官方页面（通知页）**正文只有发布语**，真实内容在同页**附件 PDF** 里。
管线会从页面抽取附件候选链接（`annex_candidates`），下载后判断 PDF 是否**有文本层**，
有则作为正文来源。

实测：**多个附件 PDF 是扫描件（无文本层）**，抽取字符数极低，
因此**未纳入检索**，页面正文作为来源（详见 [§6](#6-已知覆盖缺口)）。

| document_id | 附件 PDF | PDF 可抽取字符 | 是否纳入检索 |
|---|---|---:|---|
| `CORE003` | `01_core/CORE003.pdf`（101 页） | 89316 | ✅ 纳入（`input_kind=pdf`） |
| `MULTI002` | `05_multimorbidity/MULTI002.pdf`（35 页） | 118851 | ✅ 纳入（整篇即 PDF） |
| **`PRIM003`** | `07_primarycare/PRIM003.pdf`（39 页） | 32176（**乱码**） | ❌ **已弃用**（`ToUnicode` 损坏，改用发布页 HTML；见 [§6.5](#65-prim003-的已处置记录原-pdf-文本层编码损坏)） |
| `HTN002` | `02_hypertension/HTN002.pdf` | 33286 | ✅ 纳入（`input_kind=pdf`） |
| `PRIM001` | `07_primarycare/PRIM001.pdf` | 4463 | ✅ 纳入（`input_kind=pdf`） |
| `COPD001` | `04_copd/COPD001.pdf` | 4695 | ✅ 纳入（`input_kind=pdf`） |
| `CORE006` | `01_core/CORE006.pdf` | 43817 | ✅ 纳入（`input_kind=pdf`） |
| `LIFE002`~`LIFE007` | `06_lifestyle/LIFE00x.pdf` | 26508 ~ 52198 | ✅ 纳入（`input_kind=pdf`） |
| **`CORE002`** | `01_core/CORE002.pdf`（10 页） | **0** | ❌ **扫描件，未纳入** |
| **`LIFE001`** | `06_lifestyle/LIFE001.pdf`（14 页） | **417** | ❌ **扫描件，未纳入** |
| **`LIFE008`** | `06_lifestyle/LIFE008.pdf`（1 页） | **117** | ❌ **扫描件，未纳入** |

### 4.2.1 扫描件附件仍然留存，未做 OCR

`CORE002` / `LIFE001` / `LIFE008` 三份附件 PDF **仍保留在 `knowledge/raw/` 下**，
未被删除也未纳入检索。它们的存在是为了**后续人工 OCR** 时可直接复用，
不必重新抓取（也避免再次触发 WZWS 风控）。

> 当前状态：**未 OCR，全文不在检索范围内**（影响见 [§6.1](#61-有页面但正文极短--附件为扫描件)）。
> 这三份 PDF 是本次抓取**保留下来**的原始证据，请勿在清理磁盘时误删。

### 4.3 下载结果汇总

来自 `knowledge/raw/_download_report.json`（`generated_at = 2026-09-17T05:42:46+00:00`）：

| `status` | 篇数 | 含义 |
|---|---:|---|
| `downloaded` | **23** | 本次下载成功 |
| `skipped` | **4** | 已有可用本地产物，跳过重复下载 |
| `failed` | **3** | 付费墙 / 登录墙（`DM002`、`DM003`、`MULTI001`） |

`www.nhc.gov.cn` 的 19 篇均记录
`waf_note = "navigation status 412 (WZWS challenge) but body fully rendered"`
——即**导航状态为 412 但正文已完整渲染**，这正是 §4.1 所述机制的直接证据。

---

## 5. 人工下载清单（未获取条目）

以下 3 条 `status=draft`，**均未纳入检索**（切片数 0）。
"未获取原因"为 manifest `notes` 列**原文摘录**。

| document_id | 标题 | 未获取原因（manifest notes 原文） | 官方入口 URL |
|---|---|---|---|
| `DM002` | 中国2型糖尿病防治指南（2020年版） | pending manual download: publisher paywall (Yiigle), no official free full text; pending manual download: waf_or_empty_body: body_len=35 status=401 title=安全验证 | https://rs.yiigle.com/CN2021/1315505.htm |
| `DM003` | 国家基层糖尿病防治管理指南（2022） | pending manual download: third-party portal requires login/authorization; pending manual download: paywall_or_login_wall: third-party portal drugs.dxy.cn renders only a preview; full text requires login/membership (paywall not bypassed) | https://drugs.dxy.cn/pc/clinicalGuidelines/pFt03XqSDLS5Swuag1he4yw |
| `MULTI001` | “三高”共管规范化诊疗中国专家共识（2023版） | pending manual download: publisher paywall (Yiigle), no official free full text; pending manual download: waf_or_empty_body: body_len=35 status=401 title=安全验证 | https://rs.yiigle.com/CN2021/1467649.htm |

### 5.1 建议的人工操作

> ⚠️ **禁止绕过任何付费墙或版权限制。** 以下操作为合规的正式获取途径。

| document_id | 建议操作 |
|---|---|
| `DM002` | 通过**机构订阅**（图书馆 / 医院订阅的中华医学期刊全文数据库）依法获取《中国2型糖尿病防治指南（2020年版）》全文；或改用**已公开发布且可自由获取**的替代来源（如卫健委/疾控发布的糖尿病防治行动方案，`DM001` 已在库） |
| `DM003` | 由**具备资质的同事登录**丁香园临床指南栏目获取授权全文；或向国家基层糖尿病防治管理办公室索取公开版本。**当前状态是"需要登录授权"，不是"无法获取"** |
| `MULTI001` | 同 `DM002`，通过机构订阅获取《"三高"共管规范化诊疗中国专家共识（2023版）》；或改用已收录的 `MULTI002`（中国血脂管理指南 2023）作为多病共管域的主要依据 |

**获取后的入库步骤**：把全文放入 `knowledge/raw/<分区>/`，
在 manifest 中更新 `local_file` / `sha256`，将 `status` 改为 `active`，
然后重跑 `preprocess_documents.py` → `build_chunks.py` → `validate_manifest.py`。

---

## 6. 已知覆盖缺口

> 本节为**诚实清单**：以下内容**当前不在检索范围内**，不应被"1041 切片"的整体数字掩盖。

### 6.1 有页面但正文极短 / 附件为扫描件

| document_id | 清洗后字符 | 情况 | 影响 |
|---|---:|---|---|
| `CORE002` | **476** | 页面仅发布正文；附件 PDF 10 页**无文本层**（0 字符） | 全文缺失，仅 1 个切片 |
| `LIFE008` | **597** | 页面仅发布正文；附件 PDF 1 页**无文本层**（117 字符） | 全文缺失，仅 1 个切片 |
| `LIFE001` | **1329** | 页面仅发布正文；附件 PDF 14 页**无文本层**（417 字符） | 全文缺失，仅 2 个切片 |
| `WHO001` | **1429** | 仅抓到 WHO 出版页摘要 | 无 PEN 完整技术包 |
| `WHO002` | **2259** | 同上 | 无完整技术包 |
| `WHO003` | **2419** | 同上 | 无完整技术包 |

**修复途径**：对扫描件做**人工 OCR**（或采购带文本层的版本）后作为正文来源重新入库。
已登记的官方入口：`CORE002` / `LIFE001` / `LIFE008` 的附件 PDF 均在 `knowledge/raw/` 下留存，
可直接用于 OCR。`LIFE008` 的同页《释义》附件亦**未收录**。

### 6.2 WHO：`iris.who.int` 改版导致 PDF 链接失效

`WHO001` / `WHO002` / `WHO003` 都尝试过抓取全文 PDF，均失败。
`_download_report.json` 中 `checks` 字段记录了**真实错误原文**：

```
WHO001: html payload too small: 755 bytes | playwright fallback: pdf fetch not a pdf: status=200 bytes=755
WHO002: html payload too small: 755 bytes | playwright fallback: pdf fetch not a pdf: status=200 bytes=755
WHO003: html payload too small: 755 bytes | playwright fallback: pdf fetch not a pdf: status=200 bytes=755
```

即：旧式 `apps.who.int/iris/bitstream/handle/...` 链接返回的不是 PDF，
而是一个 **755 字节的 HTML**（`iris.who.int` 已改版，走新的
`/server/api/core/bitstreams/<uuid>/content` 形式）。

结果：**WHO 三个域只有出版页摘要（约 1.4K~2.4K 字符）**，
`KB_WHO` 合计仅 **9 个切片**，且全部为英文摘要页，**不是可引用的完整技术包内容**。

> 修复途径：改用新的 `iris.who.int/server/api/core/bitstreams/.../content` URL 重新抓取，
> 并把 WHO 三个域降级为"补充参考"，不要依赖它们支撑临床结论。

### 6.3 清洗后字符数极值

| | document_id | 字符数 | 说明 |
|---|---|---:|---|
| **最短** | `PRIM003` | **281** | 已弃用损坏 PDF，改为发布页元数据（见 6.5） |
| | `CORE002` | 476 | 附件扫描件无文本层（见 6.1） |
| | `LIFE008` | 597 | 同上 |
| | `LIFE001` | 1329 | 同上 |
| **最长** | `MULTI002` | **129552** | 中国血脂管理指南（2023），整篇 PDF 全文 |
| | `CORE003` | 81780 | 国家基本公共卫生服务规范（第三版），101 页 |
| | `LIFE007` | 58829 | 成人慢性肾脏病食养指南（2024年版） |

**极值比约 461 倍**（129552 / 281）——语料长度分布极不均匀，
这直接影响切片数的分布（`MULTI002` 一篇就占 222/1041 = **21.3%** 的切片）。

### 6.4 切片长度分布

来自 `knowledge/chunks/index_meta.json` → `size_stats`（由 `build_chunks.py` 运行输出）：

| 指标 | 值 | 目标 | 达标 |
|---|---:|---|---|
| `min` | **9** | ≥ 500 | ❌（尾部残片） |
| `max` | **1109** | ≤ 900（硬上限 1200） | ⚠️ 超过目标但**未超硬上限** |
| `mean` | **596.8** | 500~900 | ✅ |
| `under_min`（< 500） | **93** | 越少越好 | ⚠️ 占 8.9% |
| `over_max`（> 900） | **31** | 越少越好 | ⚠️ 占 2.8% |

- **最小切片**：`HTN002-0057`（HTN002，9 字符，内容为"声明不存在利益冲突"）
- **最大切片**：`MULTI002-0033`（MULTI002，1109 字符）

> `under_min=93` 主要来自**文档尾部残片**与**PDF 抽取出的短标题行**——
> 为保证 `content` 是连续原文、且不跨越标题边界，短尾段无法与后文合并，
> 因此保留为独立切片。这是一项**已知的质量折中**，不是缺陷：
> 短切片虽小，但仍是可引用的原文证据。

### 6.5 `PRIM003` 的已处置记录（原 PDF 文本层编码损坏）

> ✅ **已处置（2026-09-17）**：本项原为本文档标出的"最值得优先处理的单项质量问题"，现已修复。

**原问题**：`PRIM003`（WS/T 484—2015，39 页 PDF）虽然**有**文本层（32176 字符），
但抽取出的文字**字符编码错乱**。实测样例（`_content_check.json` 的 `head` 字段）：

```
犐犆犛１１．０２０ 犆０１ !"#$%&'()*+,- 犠犛／犜４８４—２０１５ ./#01234567 犎
```

应为 `ICS 11.020 C 01 WS/T 484—2015`。**根因**：该 PDF 的 **`ToUnicode` CMap 损坏**——
中文字体使用自定义编码且映射表缺失，抽取器只能按码位硬映射；
用 `pypdf` 抽取会得到 `/G21/G22…` 字形名，同样是编码缺失的表现。

**风险**：`P0` 等级 × 32 176 字符乱码 × **60 个切片** = 高权威加权放大了低可读性内容，
**可能污染 Citation**。当时 `title_bigram_ratio` 仅 **0.1**（其余多为 0.94~1.0）。

**处置方式**：
1. **弃用该 PDF 作为正文来源**（不再进入 preprocess / chunks）；
2. 改用**官方发布页 HTML** 作为来源（含标准号 `WS/T 484-2015`、
   发布时间 `2015-11-04`、实施时间 `2016-04-01` 等权威元数据）；
3. manifest 的 `notes` 如实登记原因；
4. 清理 `_download_report.json` 的 `secondary_files`（否则 preprocess 会优先选用该 PDF）。

**处置结果（实测）**：

| 指标 | 处置前 | 处置后 |
|---|---:|---:|
| `PRIM003` 切片数 | 60（乱码） | **1** |
| `PRIM003` 清洗后字符 | 33075 | **281** |
| `input_kind` | `pdf` | **`html`** |
| `local_file` | `.../PRIM003.pdf` | **`.../PRIM003.html`** |
| `title_bigram_ratio` | 0.1（`MISMATCH`） | **0.95（`OK`）** |
| 全库切片总数 | 1100 | **1041** |
| `KB_PRIMARYCARE` 切片 | 80 | **21** |

### 6.5.1 由此产生的新覆盖缺口（未解决）

**`PRIM003` 现在只剩 281 字符的元数据**——内容是标准号/发布时间/实施时间表格
加一个指向 PDF 的链接，**没有任何标准正文**。

即：处置解决了"乱码污染"，但**并未让该标准的实质内容可检索**：

- 处置前：乱码 32176 字符（不可用）
- 处置后：编码正常但 281 字符（**同样无实质内容**）

**结论：`KB_PRIMARYCARE` 的 P0 标准 WS/T 484—2015 实质内容当前不在检索范围内。**

> **处置决策依据（已采纳，方案②）**：**不保留乱码正文，改用公告页元数据占位。**
>
> 理由：乱码 Citation 直接违反契约「**真实 Citation > 漂亮回答**」——
> 与其给用户一段 `犐犆犛１１．０２０` 的引用，不如不给。
> 一个**不可读但格式合法**的 Citation 比"无证据"更危险，
> 因为它会让调用方与用户误以为"有官方依据"。
>
> 因此本库当前的取舍是：**宁可只有元数据、并如实标记内容缺失，
> 也不让损坏内容进入 Citation 链路。**

那份 39 页 PDF（`knowledge/raw/07_primarycare/PRIM003.pdf`，文本层 32176 字符）
**仍保留在磁盘上**，仅因 `ToUnicode` 损坏而未被采用。

> **如需全文，二选一**：
> ① 取得**带正确 `ToUnicode` 映射**的官方 PDF（或另一来源的干净版本）；
> ② 若确无干净源，则由人工**录入/校对**关键条款后入库。
>
> 在此之前，涉及老年人健康管理技术规范的问题会走"无证据"路径
> （`insufficient_evidence = true`），这是**正确的保守行为**，不是故障。
### 6.6 日期元数据：已从"全空"改善，但仍不足以自动判定现行版本

**此前状态**：`publish_date` 仅 3/30、`effective_date` **0/30**。
**根因（已修复的真实 bug）**：`scripts/extract_publish_dates.py` **此前从未被运行过**，
`knowledge/raw/_dates.json` **根本不存在**，因此 manifest 的日期列没有任何数据来源。

**修复内容**：
1. 修好并**实际运行** `scripts/extract_publish_dates.py`，产出 `knowledge/raw/_dates.json`；
2. 扩展该脚本使其**同时抽取「实施日期」**（此前只有发布日期）；
3. `scripts/build_manifest.py` 改为**优先使用抽取值**。

**当前实测状态**：

| 字段 | 有值行数 | 说明 |
|---|---:|---|
| `publish_date` | **23/30** | 由 `_dates.json` 抽取；为空 7 行 = 3 篇 PENDING + `HTN002` + 3 篇 WHO 出版页 |
| `effective_date` | **2/30** | `HTN001` = `2026-03-01`（WS/T 872—2025）、`PRIM003` = `2016-04-01` |
| `replaced_by` | **0/30** | 仍全空 |
| **带 `effective_date` 的切片** | **8 个** | 仅 `HTN001` 与 `PRIM003` 两个文档的切片携带该字段 |

> ✅ 这一项已从"日期全空"改善为"主要发布日期可得、少量实施日期可得"。

**⛔ 仍然存在的开放局限（重要）**：

> **`effective_date` 仍有 28/30 为空 ⇒ 目前无法仅凭 manifest 自动判定"现行有效版本"。**
>
> 直接后果：契约中「**版本冲突时优先中国当前有效且适用于基层场景的正式规范**」
> 这一条（见 [§2.2](#22-冲突处理原则)）**目前无法完全落地**——
> 当同一主题存在多个版本（例如某指南的 2020 版与 2025 版同时入库）时，
> 系统没有足够的机读依据判断哪一版"现行有效"，
> 只能依赖 `version` 文本与人工登记。
>
> **缓解措施（当前做法）**：
> ① 用 `status` 列把废止版本标为 `superseded`（`KnowledgeStore` 在加载期即排除，见 [§2.4](#24-生产检索只用-statusactive)）；
> ② 用 `authority_level` 做权威加权（见 [§2.3](#23-代码落地authority_boost)）。
> 这两者**只能缓解，不能替代**基于日期的现行性判定。
>
> **补全路径**：继续扩展 `extract_publish_dates.py` 的实施日期抽取规则，
> 覆盖其余 26 篇（PDF 附件与出版页的实施日期通常出现在"实施日期""自…起施行"等表述附近）。

### 6.7 其他已知问题

- **`P2` 等级为空**：国家级医学中心来源尚未纳入（见 [§1.3](#13-文档类型与权威等级分布)）。
- **`KB_DM` 仅 9 切片**：核心病种覆盖最薄弱（见 [§1.2](#12-八个知识域分布)）。
- **WHO 三篇为英文**：与 `KB_*` 其余中文语料**语言不一致**，
  中文查询对英文摘要的 BM25 命中率低（中文按字级 bigram 切分，无法匹配英文词）；
  实测 `KB_WHO` 仅 9 切片，检索价值有限。
- **`replaced_by` 全空**：无法用机读方式表达"被哪一版取代"，只能靠 `status` 列。

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

### 7.3 verbatim 自检：1041/1041 通过

`scripts/build_chunks.py` 自带 verbatim 自检，逐条验证
`content` 是否为清洗后文档的**连续原文片段**。

**当前结果（`index_meta.json` → `verification.verbatim_problems`）：**

```json
"verification": { "verbatim_problems": [] }
```

即 **0 条问题，1041/1041 通过**。

> 该结论已由我**独立复核**（不依赖脚本自身的断言）：
> 对全部 1041 条切片断言 `chunk["content"] in open("knowledge/processed/<document_id>.md")`，
> 结果 **0 条失败**（命令见 [§10](#10-统计口径) C3）。

### 7.4 修复过的两个真实缺陷

| # | 缺陷 | 症状 | 修复 |
|---|---|---|---|
| 1 | `apply_overlap()` 顺序倒转 | 原实现从前往后遍历上一块并 `insert(0, k)`，导致**重叠部分顺序被倒转**，拼出的 `content` 不再是原文连续片段（**直接损害 Citation 可信度**） | 改为**从尾部倒着取**整 unit（`for k in reversed(prev)`），保证连续且顺序不变；遇标题即停 |
| 2 | `join_units()` 平白插入段落分隔 | 长段落被切开后，后续片段用 `"\n\n"` 拼接，**在原文中平白多出一个段落分隔**，使 `content` 不再是逐字连续 | 新增 `glue=True` 标记（`pi > 0` 的后续片段），对 glue 片段用**空串粘连** |

修复后的关键代码：

```python
# 缺陷 1
for k in reversed(prev):
    if units[k]["kind"] == "heading":
        break
    ...
    carried.insert(0, k)

# 缺陷 2
if parts and not unit.get("glue"):
    parts.append("\n\n")
```

> ⚠️ **遗留文档缺陷（不影响行为，但会误导读者）**：
> `build_chunks.py` 模块 docstring 第 13–15 行仍写着
> "Overlap is taken by repeating whole **leading** blocks of the previous chunk"，
> 与修复后的实际行为（取上一块**末尾** unit）**不一致**。建议同步修正 docstring。

### 7.5 `title_bigram_ratio` —— 可复用的乱码/错源自动检测闸门

> 🔑 **这是本项目最有价值的自动化质量检查手段**，由 `scripts/verify_content_match.py` 提供。
> 它正是发现 PRIM003 乱码问题的工具（见 [§6.5](#65-prim003-的已处置记录原-pdf-文本层编码损坏)）。

**原理**：把 manifest 的**登记标题**与下载文件的**开头正文**分别切成字符二元组（bigram），
计算重叠率：

```python
ratio = |bigrams(registry_title) ∩ bigrams(head[:4000])| / |bigrams(registry_title)|
```

**判定阈值**（源码 `verify_content_match.py` 第 68 行）：

| 输出标记 | 条件 | 含义 |
|---|---|---|
| `OK  ` | `ratio >= 0.34` | 正文与标题高度重合 → 来源正确且**文本可读** |
| `??  ` | `0.15 <= ratio < 0.34` | 需人工复核 |
| `MISMATCH` | `ratio < 0.15` | 来源错误、正文缺失、**或编码损坏** |

**为什么它能捕获乱码**：编码损坏会把标题字符变成完全不同的码位
（`WS/T` → `犠犛／犜`），二元组交集骤降为 0。PRIM003 在处置前为
`ratio=0.1`（`MISMATCH`），处置后为 **`ratio=0.95`（`OK`）**——
即该闸门**明确验证了修复生效**。

**当前实测全量结果**（`python scripts/verify_content_match.py`）：

| 判定 | 篇数 | document_id（ratio） |
|---|---:|---|
| `OK`（≥0.34） | **25** | CORE001(1.0) CORE003(1.0) CORE004(1.0) CORE005(1.0) CORE006(1.0) HTN001(1.0) HTN002(1.0) HTN003(1.0) DM001(1.0) COPD001(1.0) COPD002(1.0) MULTI002(1.0) LIFE002(1.0) LIFE003(1.0) LIFE004(1.0) LIFE005(1.0) LIFE006(1.0) LIFE007(1.0) PRIM001(1.0) PRIM002(1.0) WHO001(0.971) PRIM003(0.95) WHO003(0.939) WHO002(0.867) LIFE008(0.833) |
| `??`（0.15~0.34） | **1** | LIFE001 (0.286) |
| `MISMATCH`（<0.15） | **4** | CORE002 (0.0)、DM002 (0.0)、DM003 (0.0)、MULTI001 (0.0) |

> **合计 25 + 1 + 4 = 30**，与 manifest 行数一致。

**必须如实说明的 `ratio=0.0` / 低值条目**——它们**不是**新问题，均为已知缺口：

| document_id | ratio | 性质 |
|---|---:|---|
| `CORE002` | **0.0** | 发布页正文**不含标题文字**（内容极薄，仅 476 字符）。属**已知覆盖缺口**（见 [§6.1](#61-有页面但正文极短--附件为扫描件)），非错源 |
| `DM002` | **0.0** | **PENDING**（付费墙，无来源，`source` 为空） |
| `DM003` | **0.0** | **PENDING**（登录墙） |
| `MULTI001` | **0.0** | **PENDING**（付费墙） |
| `LIFE001` | **0.286** | `??` 复核区。正文来自附件 PDF 且标题与正文措辞不同，内容经查为**正确的指导原则正文**，非错源 |

> ⚠️ **该闸门的局限**：它比较的是**抓取到的原始文件开头**，
> **不是**清洗后的 Markdown，也**不是**最终切片。
> 因此 `ratio` 高**不能**保证 preprocess/chunks 阶段产出了足量内容——
> 极端例子：`CORE002` 的 PDF 是扫描件（`ratio` 低是"意外正确"），
> 而若某文档**抓取正常但清洗后只留极少内容**，该闸门不会报警。
> 建议与 [§7.3](#73-verbatim-自检10411041-通过) 的 verbatim 自检、
> 以及 `_preprocess_report.json` 的 `chars` 列**配合使用**。

### 7.6 `content` 不写入 URL 与文件路径

**结论：`content` 字段不包含文件路径，也不包含由抓取过程注入的 URL。**
实测（切片总数 **1041**）：

| 检查 | 结果 |
|---|---|
| 含**本地文件路径**（`knowledge/`、`C:\` 等）的切片 | **0 / 1041** |
| 含 `http://` 或 `https://` 的切片 | **14 / 1041** |

那 14 条**不是导航链接残留**，而是**官方文档正文里的参考文献/引用书目**，
例如 `CORE006`（健康素养释义）的参考文献列表：

```
…[20]中华人民共和国国务院.农药管理条例[EB/OL].(2023-12-05)[2024-04-29].http://www.fgs.moa.gov.cn/flfg/…
```

分布：`CORE006` 8 条、`MULTI002` 2 条、`HTN002`/`WHO001`/`WHO002`/`WHO003` 各 1 条。

**关于 `preprocess_documents.py` 是否剔除 URL——已到脚本核实，结论是"部分成立"：**

| 对象 | 处理 | 核实位置 |
|---|---|---|
| 导航栏 / 面包屑 / 分享 / 页脚 | ✅ **整体剔除** | `DROP_TAGS`、`DROP_CLASS_PAT`（含 `nav`/`crumb`/`bread`/`share`/`footer`/`related`/`pagination` 等） |
| 正文 `<a>` 锚点 | ✅ **只保留锚文本，丢弃 `href`** | `element_md()` 对 `a` 无专门分支，仅递归取文本（实测 markdown 链接语法 `[..](http..)` = **0 处**） |
| 正文 `<img>` 图片引用 | ❌ **保留 `src`** | `element_md()`：`out.append(f"![{alt}]({src})")`；实测 **30 处**图片引用，WHO 三篇各 5 处 |
| 正文参考文献里的裸 URL | ❌ **保留**（属原文内容，不应删除） | 即上表 14 条 |

> 因此**不能说"脚本会把 URL 全部剔除"**。准确表述是：
> **导航类链接被剔除；正文锚点的 `href` 被丢弃；URL 只在正文本身含有时才保留（参考文献、图片 src）。**
> 标记为 `![](...)` 的图片引用共有 **15 个切片**包含，虽不含 URL 语义但会占用上下文长度。

## 8. 复现命令

### 8.1 真实存在的脚本

| 脚本 | 存在 | 用途 | 需要联网 | 需要凭据 |
|---|---|---|---|---|
| `scripts/download_documents.py` | ✅ | 抓取官方页面 + 附件 PDF | ✅ | ❌（Playwright 浏览器） |
| `scripts/playwright_fetch.py` | ✅ | WZWS 挑战突破（被上者调用） | ✅ | ❌ |
| `scripts/download_attachments.py` | ✅ | 附件 PDF 下载兜底 | ✅ | ❌ |
| `scripts/preprocess_documents.py` | ✅ | HTML/PDF → Markdown 清洗 | ❌（读本地） | ❌ |
| `scripts/build_chunks.py` | ✅ | 切片 + verbatim 自检 | ❌ | ❌ |
| `scripts/build_manifest.py` | ✅ | 生成 manifest CSV（UTF-8 BOM） | ❌ | ❌ |
| `scripts/validate_manifest.py` | ✅ | manifest 结构与枚举校验 | ❌ | ❌ |
| `scripts/extract_publish_dates.py` | ✅ | 从原始文件抽取发布日期 | ❌ | ❌ |
| `scripts/sync_qianfan.py` | ✅ | 把本地知识库同步到千帆（按域聚合上传） | ✅ | ✅ **需要千帆凭据** |
| `scripts/verify_sources.py` | ✅ | 来源核验 | ❌ | ❌ |
| `scripts/evaluate.py` | ✅ | 离线评测（生成 `eval/REPORT.md`） | ❌（mock） | ❌ |

> ⚠️ **`scripts/sync_qianfan.py` 的真实同步路径尚未用凭据验证（BLOCKED）**——
> 该脚本自身 docstring 已明确标注：千帆知识库接口在不同平台版本间路径与入参存在差异，
> 上线前必须按当期官方文档核对 `QianfanClient.DEFAULT_PATHS["kb_retrieve"]` /
> `["appbuilder_run"]` 与 `CREATE_DOC_PATH`。
> 同步粒度为**按域聚合为整篇文档上传**（每个 `KB_*` 一篇），**不是逐 chunk 上传**；
> 仓库中存在 `knowledge/manifest/_sync_qianfan_report.json` 记录同步结果。

### 8.2 按真实顺序复现

```bash
# ① 采集（需要联网；www.nhc.gov.cn 走 Playwright 突破 WZWS）
python scripts/download_documents.py

# ② 清洗（离线）
python scripts/preprocess_documents.py

# ③ 切片 + verbatim 自检（离线）
python scripts/build_chunks.py

# ④ 校验 manifest（离线）
python scripts/validate_manifest.py

# ⑤ 验证真实产物被服务正确加载（离线，需先有 ② ③ 产物）
python -m pytest tests/test_live_knowledge.py -q

# ⑥ 生成 manifest（仅在需要重建登记表时）
python scripts/build_manifest.py
```

**依赖说明**：
- ① 需要 `requirements-knowledge.txt`（Playwright + PyMuPDF + BeautifulSoup）与已安装浏览器内核
- ②③④⑤ 只需 `requirements.txt`
- **全流程在 `AI_PROVIDER=mock` 下即可完成**，**不需要千帆凭据**；
  只有实际调用千帆（RAG 生成、KB 检索）时才需要凭据

> **幂等性**：`build_chunks.py` 可重复运行且结果稳定——
> 实测重跑输出与 `index_meta.json` 完全一致：
> `total=1041`，`size stats {"min": 9, "max": 1109, "mean": 596.8, "under_min": 93, "over_max": 31}`。

### 8.3 本次实测输出（原文粘贴）

> 以下均为 **2026-09-17（PRIM003 处置后）** 在本仓库实际执行的真实输出。

**`python scripts/validate_manifest.py`**：

```
manifest: C:\Users\27363\Desktop\大健康\careflow-ai-rag\knowledge\manifest\knowledge_manifest.csv
checks: {"rows": 30, "active": 27, "draft": 3, "distinct_document_ids": 30, "bom": 1, "errors": 0, "warnings": 0}
VALIDATION PASSED
```

**`python -m pytest tests/test_live_knowledge.py`**：

```
...........                                                              [100%]
11 passed in 0.31s
```

> 这 11 项此前因"真实知识库产物不存在"而全部 `skip`，**现已全部通过**——
> 说明管线产物不仅存在，且能被服务层正确加载、检索并产出**可验证的 Citation**。

**`python scripts/verify_content_match.py`**（质量闸门，见 [§7.5](#75-title_bigram_ratio--可复用的乱码错源自动检测闸门)）
——输出较长，以下为 30 篇的判定摘要（完整逐篇输出含正文前 260 字符，写入
`knowledge/raw/_content_check.json`）：

```
OK   CORE001  ratio=1.0     OK   CORE003  ratio=1.0     OK   CORE004  ratio=1.0
OK   CORE005  ratio=1.0     OK   CORE006  ratio=1.0     OK   HTN001   ratio=1.0
OK   HTN002   ratio=1.0     OK   HTN003   ratio=1.0     OK   DM001    ratio=1.0
OK   COPD001  ratio=1.0     OK   COPD002  ratio=1.0     OK   MULTI002 ratio=1.0
OK   LIFE002  ratio=1.0     OK   LIFE003  ratio=1.0     OK   LIFE004  ratio=1.0
OK   LIFE005  ratio=1.0     OK   LIFE006  ratio=1.0     OK   LIFE007  ratio=1.0
OK   PRIM001  ratio=1.0     OK   PRIM002  ratio=1.0     OK   WHO001   ratio=0.971
OK   PRIM003  ratio=0.95    OK   WHO003   ratio=0.939    OK   WHO002   ratio=0.867
OK   LIFE008  ratio=0.833
??   LIFE001  ratio=0.286
MISMATCH CORE002  ratio=0.0    MISMATCH DM002  ratio=0.0
MISMATCH DM003   ratio=0.0     MISMATCH MULTI001  ratio=0.0
-> knowledge/raw/_content_check.json
```

> 统计：`OK` **25** 篇、`??` **1** 篇、`MISMATCH` **4** 篇 = 30。
> `MISMATCH` 的 4 篇均为**已知缺口**（`CORE002` 发布页无标题文字；`DM002`/`DM003`/`MULTI001` 为 PENDING 无来源），
> **不是**错源或新增问题。

**全仓测试**（`python -m pytest tests/`）：

```
497 passed in 4.17s
```

（**历史值**：产物就绪前为 `399 passed, 11 skipped`；第三轮修复前为 `436 passed`。）
## 9. 与 RAG 的衔接

### 9.1 chunk 字段 → `RetrievedChunk` 映射

切片文件字段与 `app/schemas/common.py::RetrievedChunk` 的对应关系：

| chunk 字段 | `RetrievedChunk` | 说明 |
|---|---|---|
| `chunk_id` | ✅ `chunk_id` | 全局唯一（`<document_id>-<序号>`） |
| `document_id` | ✅ `document_id` | 关联 manifest |
| `title` / `section` / `section_path` | ✅ 同名 | 章节层级，供 Citation 定位 |
| `authority` / `authority_level` / `version` / `effective_date` | ✅ 同名 | 权威信息 |
| `source_url` | ✅ `source_url` | **Citation 以 manifest 为准**（manifest 优先） |
| `content` | ✅ `content` | verbatim 原文片段 → 成为 `Citation.quote` 的来源 |
| `diseases` / `scenarios` | ❌ 不进入 schema | 仅用于 manifest 域过滤（`documents_for_domains`） |
| `char_count` | ❌ 不进入 schema | 构建期统计 |
| — | ➕ `score` | 检索期打分（RRF 融合 + 权威加权后） |
| — | ➕ `retrieval_source` | `local_bm25` 或千帆 KB |

### 9.2 Citation 只能来自 `status=active` 文档

`CitationService._validate()` 的三重校验（详见
[`RAG_ARCHITECTURE.md` §5](./RAG_ARCHITECTURE.md)）要求：
文档**存在于 manifest** 且 **`status == "active"`**，否则引用被丢弃并记入
`data.dropped_citations`（`reason` 为 `document_not_in_manifest` / `document_not_active`）。

配合 §2.4 的**加载期过滤**，形成双重保障：
**draft 文档既进不了索引，也过不了引用校验。**

### 9.3 相关性闸门与权威加权

除 `AUTHORITY_BOOST`（§2.3）外，检索还有**两道相关性闸门**，
定义于 `app/core/config.py` 并经 `app/services/retrieval_service.py` 生效：

| 参数 | 默认值 | 环境变量 | 作用 |
|---|---:|---|---|
| `rag_min_relevance_score` | **12.0** | `RAG_MIN_RELEVANCE_SCORE` | 低于此分的命中被丢弃 |
| `rag_min_matched_terms` | **3** | `RAG_MIN_MATCHED_TERMS` | 命中词数低于此值被丢弃 |

> ⚠️ **这两个值是经验校准值，换语料必须重新标定。**
> 它们与 BM25 的原始分数量级强相关；更换分词方式、语料规模或语言分布后，
> `12.0` 与 `3` 可能过松（引入噪声）或过严（召回骤降）。
> 标定方法：用 `eval/datasets/rag_cases.jsonl` 与 `no_evidence_cases.jsonl`
> 跑 `scripts/evaluate.py`，观察命中率与无证据率的变化。
>
> ⚠️ **文档缺口**：`RAG_MIN_RELEVANCE_SCORE` 与 `RAG_MIN_MATCHED_TERMS`
> **不在 `.env.example` 中**（已核实）。虽然代码内默认值可用，
> 但运维无法从模板发现这两个可调项，建议补入 `.env.example`。

---

## 10. 统计口径

> 本文档所有数字的复现方式。命令均在仓库根目录执行（Python 3.14）。

### 10.1 核心计数（§1、§3）

| 数字 | 口径 | 命令 |
|---|---:|---|
| 登记 30 / active 27 / draft 3 | manifest 行数与 `status` 列计数 | **C1** |
| 切片 **1041** | `chunks.jsonl` 行数（非空行） | **C2** |
| 产出切片的文档 27 | chunks 中 `document_id` 去重计数 | **C2** |
| 清洗总字符 **612852** | `_preprocess_report.json` → `summary.total_chars`（已与逐篇 `chars` 求和交叉验证一致） | **C1** |
| 各 `KB_*` 文档数 | manifest `qianfan_kb` 计数 | **C1** |
| 各 `KB_*` 切片数 | chunks 按 `document_id` join manifest 的 `qianfan_kb` 后计数 | **C2** |

**C1** — manifest 统计：

```bash
python -c "import csv,collections;r=list(csv.DictReader(open('knowledge/manifest/knowledge_manifest.csv',encoding='utf-8-sig')));print('rows',len(r));print(collections.Counter(x['status'] for x in r));print(collections.Counter(x['qianfan_kb'] for x in r));print(collections.Counter(x['authority_level'] for x in r))"
```

**C2** — 切片统计：

```bash
python -c "import json,collections;c=[json.loads(l) for l in open('knowledge/chunks/chunks.jsonl',encoding='utf-8') if l.strip()];print('chunks',len(c));print(collections.Counter(x['document_id'] for x in c))"
```

### 10.2 verbatim 独立复核（§7.3）

**C3** — 不依赖脚本自身断言，逐条验证 `content` 是 `knowledge/processed/<id>.md` 的连续子串：

```bash
python -c "import json;from pathlib import Path;c=[json.loads(l) for l in open('knowledge/chunks/chunks.jsonl',encoding='utf-8') if l.strip()];s={f.stem:f.read_text(encoding='utf-8') for f in Path('knowledge/processed').glob('*.md')};bad=[x['chunk_id'] for x in c if x['content'] not in s[x['document_id']]];print('checked',len(c),'failures',len(bad),bad[:5])"
```

### 10.3 切片长度分布（§6.4）

取自 `knowledge/chunks/index_meta.json` → `size_stats`，
该文件由 `scripts/build_chunks.py` 每次运行重写（值可复现）：

```bash
python -c "import json;print(json.load(open('knowledge/chunks/index_meta.json',encoding='utf-8'))['size_stats'])"
```

### 10.4 PDF 文本层字符数（§4.2、§6.1、§6.5）

用 PyMuPDF 逐页 `get_text("text")` 求和；`annex_pdf_chars` 亦记录于
`_download_report.json`：

```bash
python -c "import pymupdf,pathlib;[print(p.name, len(''.join(pg.get_text('text') for pg in pymupdf.open(str(p))))) for p in map(pathlib.Path,['knowledge/raw/01_core/CORE002.pdf','knowledge/raw/06_lifestyle/LIFE001.pdf','knowledge/raw/06_lifestyle/LIFE008.pdf'])]"
```

### 10.5 下载状态与错误原文（§4.3、§6.2）

```bash
python -c "import json,collections;d=json.load(open('knowledge/raw/_download_report.json',encoding='utf-8'));print(d['summary']);[print(x['document_id'],x['checks']) for x in d['documents'] if x.get('checks')]"
```

### 10.6 URL / 路径检查（§7.6）

```bash
python -c "import json,re;c=[json.loads(l) for l in open('knowledge/chunks/chunks.jsonl',encoding='utf-8') if l.strip()];print('with_url',sum(1 for x in c if re.search(r'https?://',x['content'])));print('with_path',sum(1 for x in c if re.search(r'(knowledge/|[A-Za-z]:\\\\\\\\)',x['content'])))"
```

### 10.7 验证命令（§8.3）

```bash
python scripts/validate_manifest.py
python -m pytest tests/test_live_knowledge.py -q
python scripts/verify_content_match.py     # title_bigram_ratio 质量闸门（§7.5）
python -m pytest
```

### 10.8 本文档中**未**使用的数据源

为避免误导，明确列出本文**没有**引用/推断的内容：

- ❌ **没有**任何"医学准确率"指标——语料正确性需临床专家评审，自动化指标无法覆盖
- ❌ **没有**使用外部权威排名或第三方评估结果
- ❌ `effective_date` / `replaced_by` 相关结论**仅陈述有值行数**（2/30 与 0/30），未对缺失做推断
- ❌ **没有**验证 `sync_qianfan.py` 的真实同步行为——该脚本已存在，但其千帆同步路径未经凭据验证（BLOCKED），故本文只描述其存在与粒度，不描述其线上行为

---

## 相关文档

- [`RAG_ARCHITECTURE.md`](./RAG_ARCHITECTURE.md) —— 检索链路、BM25/RRF、Citation 校验、降级矩阵
- [`API.md`](./API.md) —— 端点契约、`domains` 与 `patient_context` 约束
- [`SAFETY.md`](./SAFETY.md) —— 安全边界与已知局限
- `knowledge/chunks/index_meta.json` —— 切片参数与自检结果的机器可读版本
