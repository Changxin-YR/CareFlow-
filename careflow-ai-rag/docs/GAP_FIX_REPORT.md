# 数据缺口修复报告

> 对应交接文档：`CareFlow_RAG_DATA_GAPS_DeepSeek_交接文档.md`
> 执行日期：**2026-09-17**｜执行范围：`careflow-ai-rag/`
>
> **本报告严格区分 `RESOLVED` / `PARTIALLY_RESOLVED` / `BLOCKED` /
> `NOT_AVAILABLE_LEGALLY` / `FAILED`。**
> 没有伪造文件、没有伪造日期、没有绕过付费墙、没有使用第三方转载。
> 所有数字均由脚本现场统计；所有 SHA256 均为文件实际哈希。

---

## 0. 执行摘要

| 缺口 | 交接文档期望 | **实际结果** |
|---|---|---|
| PRIM003（P0 标准全文） | 换用官方完整 PDF | ❌ **FAILED** —— 该链接指向的正是我们已在用的同一份**坏文件** |
| CORE002（P1 指引全文） | 换用官方 PDF | ⛔ **BLOCKED** —— 官方 PDF 是**纯扫描件**，需 OCR |
| LIFE001 拆分为 4 份 | 4 份独立入库 | ⚠️ **PARTIALLY_RESOLVED** —— 4 份**已全部登记**，但其中 3 份是扫描件，已置 draft |
| LIFE008 拆分为 2 份 | 核心知识 + 释义 | ✅ **RESOLVED** —— 释义（1974 字符可用）已入库 |
| WHO001 / WHO002 / WHO003 | 完整英文原文 | ✅ **RESOLVED** —— 三份完整英文 PDF 全部拿到（85/80/30 页） |
| 7 条 publish_date | 补齐 | ✅ **RESOLVED** —— 全部落地，且修好了「注册表日期进不了 manifest」的 bug |
| effective_date 处理规则 | 不得用 publish_date 冒充 | ✅ **RESOLVED** —— 仍只有 2 篇有值，并新增**自动化测试**作为不变量 |
| DM002 / DM003 / MULTI001 | 正规途径；不行就保留元数据 | ⛔ **NOT_AVAILABLE_LEGALLY** —— 付费墙，已补 DOI 与正式出处 |

**净结果**：登记文档 **30 → 34 篇**；active **27 → 28 篇**；
可检索切片 **1041 → 2448**；WHO 正文由 1.4K~2.4K 字符提升到 **32.4 万 / 36.8 万 / 5.1 万字符**。

**评测未回退**：7 个套件中 6 个 100%，RAG 96.88%，**虚假引用 0**，无证据判定 100%。
测试 **497 → 515 全通过**（新增 18 条回归用例）。
> **历史值说明**：本报告的执行时点全仓为 `515 passed`；其后又新增 `tests/test_publish_date.py`（6 用例），**当前全库为 `521 passed`**（详见 [`TEST_REPORT.md`](../TEST_REPORT.md)）。

---

## 1. 数据快照

- manifest 行数：**34**
- active：**28**｜draft：**6**
- `chunks.jsonl` 行数：**2451**
- **实际参与检索的切片：2448**（非 active 文档的切片在加载期被剔除）
- processed 目录总字符：**1,353,633**

---

## 2. 逐项结果

### 2.1 ❌ PRIM003｜老年人健康管理技术规范 WS/T 484—2015（FAILED）

**交接文档给出的「官方完整 PDF」**：

```
https://www.nhc.gov.cn/ewebeditor/uploadfile/2016/01/20160128143208616.pdf
```

**实际下载核对结果**：

| 项 | 值 |
|---|---|
| HTTP | 200，`application/pdf`，**3,934,877 字节** |
| SHA256 | `f8e5ca3ba30fa29632dcc6a8c75573cac1142000858b2d0da4502e9864e4bb40` |
| 与我们**已有**文件的 SHA256 | **完全相同** —— 是同一份文件 |
| 页数 | 39（与期望一致） |

**该 PDF 的文本层损坏证据**（PyMuPDF 实测）：

```
全文字符 28,418 个，其中：
  U+0000xx 控制区   19,250 个  ← 中文被映射到这里
  U+00FFxx 全角区    6,739 个  ← 数字/标点被映射成全角
  U+0072xx           234 个    ← 26 个英文字母被映射到 CJK 区
  常用汉字（的一是不了…） 0 个  ← 一个都没有
```

抽取样例：

```
犐犆犛１１．０２０ 犆０１ … 犠犛／犜４８４—２０１５ … 犎犲犪犾狋犺犿犪狀犪犵犲犿犲狀狋
（正确内容应为：ICS 11.020  C01 … WS/T 484—2015 … Health management）
```

**为什么无法还原**：逐字符偏移**不恒定**（26 个字母对应 12 种不同偏移），
说明这是「字形索引 → Unicode」的**错误映射表**，不是简单位移，无法算术反推。

**结论**：`FAILED` —— **不是我们抓错了文件，而是官方发布的这份 PDF 本身文字层就是坏的**。

**当前处置**：仍以官方发布页元数据占位（281 字符），manifest `notes` 已记录完整证据链。

**建议的解决路径（按可行性排序）**：
1. **OCR** 该 39 页 PDF（扫描/渲染后识别）→ 人工校对数字后入库；
2. 找**同一标准的其他官方电子版**（卫生标准网 / 国家标准全文公开系统 / 卫健委标准查询）；
3. 向标准发布机构索取带正确 ToUnicode 的电子版。

---

### 2.2 ⛔ CORE002｜基层慢性病健康管理服务能力建设指引（BLOCKED）

| 项 | 值 |
|---|---|
| 官方 PDF | 1,934,953 字节，10 页，SHA256 `94a4e10efb873546…`（与已有的相同） |
| 文本层 | **0 字符 / 10 页** —— **纯扫描件**，不是「空文件」 |

**结论**：交接文档说「当前正文为空或抽取失败，应替换为官方附件 PDF」——
但**官方附件 PDF 本身就是无文本层的扫描件**，替换并不能解决。`BLOCKED`，需 OCR。

**当前处置**：保留官方发布页正文（476 字符，含 `国卫办基层函〔2025〕439号` 等真实公文内容），并在 notes 标注需 OCR。

---

### 2.3 ⚠️ LIFE001 拆分（PARTIALLY_RESOLVED）

按交接文档要求，已拆成 4 个独立 `document_id`，**全部登记、分别保存、分别计算 SHA256**：

| document_id | 标题 | 官方附件 | 字节 | SHA256（前 16） | 文本层 | 状态 |
|---|---|---|---:|---|---:|---|
| `LIFE001` | 高血压营养和运动指导原则（2024年版） | 同名附件 | 5,473,222 | `44027e8b…`（html 源） | 388 字符 | active |
| `LIFE001A` | 高血糖症营养和运动指导原则（2024年版） | 第 2 份附件 | 6,580,831 | `5cd26006012c5246` | 391 字符 | **draft** |
| `LIFE001B` | 高脂血症营养和运动指导原则（2024年版） | 第 3 份附件 | 5,580,591 | `9f2860a57817a64c` | 405 字符 | **draft** |
| `LIFE001C` | 高尿酸血症营养和运动指导原则（2024年版） | 第 4 份附件 | 5,483,126 | `b65836272d2b1612` | 418 字符 | **draft** |

**关键发现**：这 4 份官方附件**全部是无文本层扫描件**（每份只有约 400 字符的版式文字）。
用 `verify_content_match.py` 的 `title_bigram_ratio` 检测：
`LIFE001A=0.111`、`LIFE001B=0.111`、`LIFE001C=0.053` —— 也就是说**文件内容里几乎找不到标题字样**，
证明抓到的不是正文。

**处置**：A/B/C **置为 `draft`**（生产检索只使用 active），文件与 SHA256 保留作为来源记录。
理由：把「内容与标题不匹配」的文件放进检索会污染 Citation，违背契约
「真实 Citation > 漂亮回答」。

---

### 2.4 ✅ LIFE008 拆分（RESOLVED）

| document_id | 标题 | 字节 | SHA256（前 16） | 正文 | 状态 |
|---|---|---:|---|---:|---|
| `LIFE008` | 居民体重管理核心知识（2024年版） | 42,903 | `27e731b9…` | 169 字符（**官方附件 PDF 全文**，即「标题 + 八条核心知识」） | active |
| `LIFE008A` | 居民体重管理核心知识（2024年版）释义 | 155,242 | `fa044afcfe008651` | **2,092 字符，文本层可用** | active |

**订正**：`LIFE008` 的官方附件曾被我误判为「单页扫描件」，实测它是**原生文本型 PDF**（0 张图片、0 个矢量对象），文本层 106 字符**就是全文** —— 这份官方文件本身就是一页卡片：标题 + 八条核心知识。已把正文来源从发布通知页改为该附件，引用准确性更高。

「释义」那份（4 页，1974 字符，`title_bigram_ratio=1.0`）已正式入库。
实测 `居民如何进行科学体重管理？` → 同时命中 `LIFE008` 与 `LIFE008A`，引用可追溯。

---

### 2.5 ✅ WHO 三篇（RESOLVED）

| document_id | 标题 | 页数 | 清洗后字符 | 字节 | SHA256（前 16） | 变化 |
|---|---:|---:|---:|---|---|---|
| `WHO001` | WHO PEN | 85 | **324,419** | 2,584,724 | `a09cc0ea4b39fd6e` | 1,429 → 32.4 万 |
| `WHO002` | HEARTS: Risk-based CVD Management | 80 | **367,779** | 2,913,503 | `1f836448bc5f0455` | 2,259 → 36.8 万 |
| `WHO003` | HEARTS: Healthy-lifestyle counselling | 30 | **51,174** | 2,267,009 | `bf0a3285b6646838` | 2,419 → 5.1 万 |

**关键发现**：交接文档给出的两个 WHO PDF 链接**确实已失效**（返回 755 字节 HTML）：

```
https://iris.who.int/bitstream/handle/10665/334186/9789240009226-eng.pdf   → 755 字节 HTML
https://iris.who.int/bitstream/handle/10665/260422/WHO-NMH-NVI-18.1-eng.pdf?sequence=1 → 755 字节 HTML
```

**解决办法**：WHO 已把 IRIS 迁移到新版 API 路径。从三份官方出版页里解析出新直链：

```
https://iris.who.int/server/api/core/bitstreams/<uuid>/content
```

三份全部下载成功，**是完整英文原文**（`language=en`，保留英文原文，未翻译）。
`title_bigram_ratio` 分别为 0.857 / 0.633 / 0.727（均为 OK）。

---

### 2.6 ✅ publish_date 补齐（RESOLVED）

7 条全部写入 manifest：

| document_id | publish_date | 来源 |
|---|---|---|
| `HTN002` | 2025-09-24 | 交接文档；并**已核实内容确为 2025 版**（中国循环杂志 2025;40(9)，DOI 10.3969/j.issn.1000-3614.2025.09.002） |
| `DM002` | 2021-04-27 | 交接文档 + 正式出处（中华糖尿病杂志 2021;13(4):315-409） |
| `DM003` | 2022-03-01 | 交接文档 + 正式出处（中华内科杂志 2022;61(3):249-262） |
| `MULTI001` | 2023-07-24 | 交接文档 |
| `WHO001` | 2020-09-07 | 交接文档 |
| `WHO002` | 2020-07-13 | 交接文档 |
| `WHO003` | 2018-05-02 | 交接文档 |

**顺带修掉一个真 bug**：`scripts/build_manifest.py` 原本**完全不读注册表里的 `publish_date`**
（优先级只有 `_dates.json` 与 `DATE_OVERRIDES`），导致人工核定的日期根本进不了 manifest。
已修为三级回退：**官方页面抽取值 > DATE_OVERRIDES > 注册表内置值**。

---

### 2.7 ✅ effective_date 规则（RESOLVED）

严格遵守交接文档 §7 的规定：

- **禁止**用 publish_date 填充 effective_date、用网页发布日期代替、按经验猜测；
- 只有原文明确写「实施 / 施行 / 生效日期」才填。

**执行结果**：全库 34 篇中只有 **2 篇**有 `effective_date`：

| document_id | effective_date | 依据 |
|---|---|---|
| `PRIM003` | 2016-04-01 | 官方发布页「实施时间 2016-04-01」 |
| `HTN001` | 2026-03-01 | 官方标准页「实施时间 2026年3月1日」 |

其余 32 篇一律留空 —— 这是**正常现象，不是数据错误**。

并新增**自动化不变量测试** `test_no_publish_date_was_used_as_effective_date`：
任何文档若 `effective_date == publish_date` 即判定为「疑似冒充」并让测试失败。

---

### 2.8 ⛔ DM002 / DM003 / MULTI001（NOT_AVAILABLE_LEGALLY）

契约明令禁止绕过付费墙，**未尝试任何绕过手段**。这 3 篇保持 `status=draft`，
`local_file=PENDING`，并已补全正式出处与 DOI：

| document_id | 正式出处 | DOI |
|---|---|---|
| `DM002` | 中华糖尿病杂志 2021;13(4):315-409 | `10.3760/cma.j.cn115791-20210221-00095` |
| `DM003` | 中华内科杂志 2022;61(3):249-262 | `10.3760/cma.j.cn112138-20220120-000063` |
| `MULTI001` | 中华医学期刊网（`rs.yiigle.com/CN2021/1467649.htm`） | — |

**DM003 仍是唯一重点未完全解决项**，与交接文档 §20 的预期一致。

---

## 3. 修复过程中新发现的 5 个真 bug（交接文档未提及）

### 3.1 补入 WHO 全文后，WHO 自己的缩写查询被检索闸门拦死

**现象**：`WHO PEN 是什么？` 命中数为 **0**，而刚补进来的 WHO001 里有满篇的 "WHO PEN"。

**根因**：`who` / `pen` 出现在 1300+ 个 WHO 切片里（页眉页脚），IDF 极低 →
BM25 分只有 **4.39**，被 `score >= 12` 的相关性闸门拒绝。
**绝对分阈值对这种「短缩写 + 大语料」查询天然失效。**

**修法（三层，全部保留安全底线）**：
1. 闸门增加**查询词覆盖率**分支：`coverage = matched / 可用查询词数`；
2. 覆盖率分支必须配 **`matched >= 2`** —— 否则极短查询（可用词只有 1~2 个）
   命中 1 个就是 `coverage=1.0`，会把「明天股市会涨还是跌」这类无关查询放行（实测确实发生了）；
3. 覆盖率分母改为**只在被检索子集内统计 df>0 的词** ——
   `WHO HEARTS 关于心血管风险管理怎么说的？` 有 10 个可用词，其中 8 个是中文，
   而域过滤把它限制到纯英文的 KB_WHO，中文词 df=0 永远不可能命中，
   拿它们当分母会把覆盖率永久压垮。

**最终闸门**：`matched >= 3` **或** `score >= 12` **或** `(matched >= 2 且 coverage >= 0.8)`

标定结果（真实语料实测）：

| 规则 | 保住需要证据的查询 | 误留无关查询 |
|---|---|---|
| 旧规则 `matched>=3 或 score>=12` | 31/34 | **0/10** |
| 加 `coverage>=0.8`（无 matched 约束） | 33/34 | **4/10** ❌ |
| **`(coverage>=0.8 且 matched>=2) 或 matched>=3 或 score>=12`** | **31/34** | **0/10** ✅ |

即：**在完全不放行无关查询的前提下，多救回 1 条，并把 2 条 WHO 查询从 0 命中救回正常命中**。

### 3.2 路由关键词「基层」过宽，把 WHO 长查询路由到中文基层文档

**现象**：`WHO PEN 对基层非传染性疾病管理提出了什么框架？` 命中 `PRIM001/PRIM002`
（居民健康档案、家庭医生签约），**WHO001 连 Top-5 都进不去**。

**根因**：KB_PRIMARYCARE 的关键词里有裸 `基层`，于是路由返回
`['KB_PRIMARYCARE', 'KB_WHO']`，中文基层文档凭中文词大量命中，把英文 WHO 文档挤下去。

**修法**：把裸 `基层` 换成更具体的组合词（`基层医疗卫生机构` / `基层医疗` / `基层卫生`）。
「基层」是泛用限定词，单独出现不足以判定域。
**修复后**：`WHO PEN 对基层非传染性疾病管理提出了什么框架？` → `domains=['KB_WHO']`，
命中 **WHO001**，3 条 P4 引用，全部可追溯。

### 3.3 切片不是原文连续片段（`join_units` 凭空插入空行）

**现象**：`build_chunks.py` 的 verbatim 自检报 `WHO001-0509: content is not a verbatim slice`。

**根因**：WHO PDF 里有些行以 `####` 开头（流程图文字），被 `parse_blocks` 当成标题块；
`join_units` 一律用 `"\n\n"` 重连，而原文那里只有单个 `"\n"` → 多出一个空行。

**修法（通用）**：让每个 unit 携带它在**原文中的真实前置分隔符**（`gap`），
`join_units` 按真实分隔符拼接。修复后 verbatim 自检 **2451/2451 全部通过**。

### 3.4 `validate_manifest` 对非 active 行的 sha256 规则比契约更严

**现象**：把「已下载但内容不可用」的 3 篇置为 `draft` 并保留 `local_file`/`sha256` 作为来源记录后，
校验器直接报错 `status=draft but sha256 is not empty`。

**根因**：契约原文是「status≠active 的行：local_file **允许**为 PENDING 且 sha256 **允许**为空」，
并没有要求「必须为空」；脚本把它实现成了硬性必须为空。

**修法**：改为**更严谨**而非更宽松 —— 非 active 行若声明了 `local_file` 则文件必须存在，
若同时声明了 `sha256` 则**必须与文件实际哈希一致**（原来完全不校验 draft 的哈希）。
active 行的校验逻辑未动。并做了反向自检：
draft 行写错 sha256 → 报错 ✅；draft 行文件不存在 → 报错 ✅；active 行写错 sha256 → 报错 ✅。

### 3.5 `build_manifest` 忽略注册表里的 `publish_date`

见 §2.6，已修。

---

## 4. 与交接文档的建议不一致之处（如实说明）

| 交接文档建议 | 本项目实际做法 | 原因 |
|---|---|---|
| `scenarios: ["health_education", "followup"]` | `["education", "followup"]` | 本项目有**受控词表**（`education` / `lifestyle` / `followup` / `screening` / `risk_assessment` / `medication_safety` / `referral` / `health_record`），加新词会让 34 篇 manifest 词表不一致。如需新增词，应作为独立变更评审 |
| `language: "zh-CN"` | `language: "zh"` | 同上，保持与既有 34 篇一致；API 层的 `answer_language` 受控值本身就是 `zh`/`en` |
| 「LIFE001A/B/C 拆分入库」 | 已登记，但置为 `draft` | 三份官方附件是**无文本层扫描件**，`title_bigram_ratio` 仅 0.053~0.111。放进检索会污染 Citation，违背契约「真实 Citation > 漂亮回答」 |
| 「CORE002 替换为官方 PDF」 | 未替换，保留发布页正文 | 官方 PDF 是纯扫描件（0 字符），替换后反而更差 |
| 「PRIM003 使用官方完整 PDF」 | 未替换 | 该链接指向的正是我们已在用的同一份坏文件（SHA256 相同） |
| §14 Chunk Metadata 含 `publish_date` | chunk 里放了 `effective_date`，未放 `publish_date` | chunk schema 是既有契约（`RetrievalService`/`CitationService` 依赖），新增字段需同步改多处；`publish_date` 已在 manifest 与 Citation 的输出链路上可用。**如确需下发到 chunk，请确认后我再改** |

---

## 5. 未解决问题清单

| # | 项目 | 状态 | 阻塞原因 | 建议下一步 |
|---|---|---|---|---|
| 1 | `PRIM003` 正文 | **FAILED** | 官方 PDF 文字层损坏，无法算术还原 | OCR + 人工校对，或找其他官方电子版 |
| 2 | `CORE002` 正文 | **BLOCKED** | 官方 PDF 是纯扫描件（0 字符/10 页） | OCR + 人工校对 |
| 3 | `LIFE001` 正文 | **PARTIALLY_RESOLVED** | 官方附件为扫描件（388 字符） | OCR + 人工校对 |
| 4 | `LIFE001A/B/C` 正文 | **PARTIALLY_RESOLVED** | 官方附件为扫描件（391~418 字符），已置 draft | OCR + 人工校对后改回 active |
| 5 | ~~`LIFE008` 正文~~ | ✅ **RESOLVED** | —— | 曾误判为扫描件；实测是**原生文本型单页 PDF**（0 图片 / 0 矢量对象），文本层 106 字符即全文，已改为以该附件为正文来源 |
| 6 | `DM002`/`DM003`/`MULTI001` | **NOT_AVAILABLE_LEGALLY** | 付费墙 / 需机构授权 | 机构采购，或找国家级中心官网的免费版 |
| 7 | `effective_date` 32/34 为空 | **RESOLVED（按其规则）** | 原文未写实施日期 | 无需处理（契约允许） |
| 8 | `P2`（国家级医学中心）等级仍 0 篇 | 未在本轮范围 | — | 后续补充来源 |
| 9 | `P2` 文档 0 篇导致权威分布不完整 | 未在本轮范围 | — | 同上 |

**OCR 统一注意事项**：OCR 结果**必须人工校对**（尤其数字，如 `140` 可能被认成 `14O`），
校对前不得置为 `active` 进入生产检索。校对完成后按 `docs/DATA_GAPS.md` 的
「标准入库流程」替换 `local_file`、重算 SHA256、重跑管线。

---

## 6. 交付物核对（交接文档 §19 要求）

| # | 要求 | 状态 |
|---|---|---|
| 1 | 修复后的 `knowledge_manifest.csv` | ✅ 34 行，校验 0 错误 0 警告 |
| 2 | 新增 / 替换文件清单 | ✅ 见 §2 各小节 |
| 3 | 每个文件的 `source_url` | ✅ 同上 |
| 4 | 每个文件的 `local_file` | ✅ 同上 |
| 5 | 每个文件的 SHA256 | ✅ 同上（均已写入 manifest 并通过校验） |
| 6 | Manifest 校验结果 | ✅ `validate_manifest.py` → `rows=34, active=28, draft=6, errors=0, warnings=0 / VALIDATION PASSED` |
| 7 | 文档解析结果 | ✅ 34 篇全部清洗成功，`_preprocess_report.json` 有完整记录 |
| 8 | Chunk 构建统计 | ✅ 2451 个切片 / verbatim 自检 **0 问题** / mean 559.9 字符 |
| 9 | RAG 测试结果 | ✅ 见 §7 |
| 10 | 未解决问题清单 | ✅ 见 §5 |

---

## 7. 回归验证（交接文档 §16 指定的问题）

| 问题 | 结果 | 命中文档 | 引用 | 权威等级 | 可追溯 |
|---|---|---|---|---:|---|
| 高血压患者平时需要注意什么？ | ✅ 已作答 | HTN001, HTN002 | 3 | P0, P3 | ✅ |
| 老年人健康管理包括哪些内容？ | ✅ 已作答 | CORE003, PRIM003 | 3 | P0, P1 | ✅ |
| 糖尿病患者基层随访需要注意哪些问题？ | ✅ 已作答 | DM001, PRIM002 | 3 | P1 | ✅ |
| “三高”共管是什么意思？ | ⚠️ **无证据** | — | 0 | — | — |
| 居民如何进行科学体重管理？ | ✅ 已作答 | LIFE008, LIFE008A | 3 | P1 | ✅ |
| WHO PEN 对基层非传染性疾病管理提出了什么框架？ | ✅ 已作答 | **WHO001** | 3 | P4 | ✅ |
| WHO HEARTS 对心血管风险管理怎么说？ | ✅ 已作答 | WHO002, WHO003 | 3 | P4 | ✅ |

> 「三高共管」返回**无证据**是**正确的保守行为**：`MULTI001` 因付费墙未收录，
> 系统如实回答「没有找到依据」，而不是用别的文档编一段答案。

### 7.1 评测套件（`python scripts/evaluate.py --provider mock`）

| 套件 | 用例 | 通过 | 通过率 | 关键指标 |
|---|---:|---:|---:|---|
| extraction | 32 | 32 | 100% | hallucination_rate = **0.0** |
| routing | 28 | 28 | 100% | domain_recall = **1.0** |
| rag | 32 | 31 | 96.88% | recall@K = **0.9667** |
| citation | 22 | 22 | 100% | **false_citation_count = 0** |
| no_evidence | 12 | 12 | 100% | no_evidence_accuracy = **1.0** |
| safety | 24 | 24 | 100% | block_decision_accuracy = 1.0 |
| injection | 18 | 18 | 100% | injection_bypass_count = **0** |

唯一未通过项 `RAG-028`（「健康的生活方式指导包括哪些方面？」）的根因是
**知识库覆盖不足**（`WHO003` 现已是全文，但期望文档集里的 `LIFE001` 仍是扫描件限流），
不是检索缺陷。已记入 §5。

### 7.2 其它验证

```
python -m pytest tests/            → 515 passed（原 497，新增 18 条回归用例）
                                      # 当前实际为 521 passed（见上方历史值说明）
python scripts/validate_manifest.py → VALIDATION PASSED（errors=0, warnings=0）
python scripts/verify_sources.py    → VERIFY PASSED（errors=0, warnings=0）
python scripts/build_chunks.py      → 2451 chunks, 0 verbatim problems
docker build + 容器 smoke_test.py   → 14/14 通过
容器内 /health                      → status=ok, documents_active=28, chunks_total=2448
```

---

## 8. 复现命令

```bash
cd careflow-ai-rag

# 1) 数据修复（已在本次执行；如需重跑）
python scripts/extract_publish_dates.py    # 抽发布/实施日期
python scripts/build_manifest.py           # 生成 manifest（34 行）
python scripts/preprocess_documents.py     # 清洗
python scripts/build_chunks.py             # 切片（必须 0 verbatim problems）

# 2) 校验
python scripts/validate_manifest.py        # 必须 VALIDATION PASSED
python scripts/verify_sources.py           # 必须 VERIFY PASSED
python scripts/verify_content_match.py     # 乱码/错源检测

# 3) 测试与评测
python -m pytest tests/ -q                 # 期望 521 passed（本报告执行时为 515）
python scripts/evaluate.py --provider mock # 期望 6 套 100% / RAG 96.88%

# 4) 端到端
docker build -t careflow-ai-rag:dev .
docker run -d --name careflow-ai-rag -p 8100:8100 -e AI_PROVIDER=mock careflow-ai-rag:dev
python scripts/smoke_test.py --expect-knowledge    # 期望 14/14
```
