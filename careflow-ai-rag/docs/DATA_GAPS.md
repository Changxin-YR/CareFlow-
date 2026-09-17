# 数据缺口清单 —— 需要人工获取的官方资料

> 面向：**去外部找资料的人**（不需要懂代码）。
> 每一条都写了「缺什么 / 去哪找 / 怎么判断找对了 / 找到后怎么办」。
>
> 当前状态：30 篇登记，**27 篇可用**，**3 篇付费墙未收录**，
> 另有 **7 篇虽可用但正文严重不足**，**28/30 篇缺 `effective_date`**。
>
> 最后更新：2026-09-17

---

## 目录

- [优先级总览](#优先级总览)
- [缺口 A｜PRIM003 老年人健康管理技术规范（最高价值）](#缺口-aprim003-老年人健康管理技术规范最高价值)
- [缺口 B｜3 份「无文本层扫描件」](#缺口-b3-份无文本层扫描件)
- [缺口 C｜WHO 3 篇只有出版页摘要](#缺口-cwho-3-篇只有出版页摘要)
- [缺口 D｜3 篇付费墙文档](#缺口-d3-篇付费墙文档)
- [缺口 E｜effective_date 28/30 为空](#缺口-eeffective_date-2830-为空)
- [找到文件后的标准入库流程](#找到文件后的标准入库流程)
- [验收标准](#验收标准)

---

## 优先级总览

| 优先级 | 缺口 | 影响 | 需要什么 |
|---|---|---|---|
| **P0** | PRIM003（WS/T 484—2015） | P0 标准 + 老年健康核心场景**完全没有实质正文** | 一份**文字可复制**的全文（PDF 带正确 ToUnicode / 官方 Word / HTML） |
| **P1** | CORE002 / LIFE001 / LIFE008 扫描件 | 三篇 P1 文档只有发布页正文（476 / 1329 / 597 字符） | 带文本层的 PDF，**或** OCR 结果（人工校对后） |
| **P1** | effective_date 28/30 为空 | 契约「版本冲突优先现行有效规范」**无法自动落地** | 各文档的「实施日期」 |
| **P2** | WHO 3 篇 | P4 级，只有出版页摘要（1.4K~2.4K 字符） | WHO 官方全文 PDF |
| **P2** | DM002 / DM003 / MULTI001 | 糖尿病与血脂主题缺 P3 级指南 | 机构采购授权 / 官方免费全文 |

---

## 缺口 A｜PRIM003 老年人健康管理技术规范（最高价值）

| 项 | 内容 |
|---|---|
| **文档编号** | `PRIM003` |
| **标准号** | **WS/T 484—2015** |
| **标题** | 老年人健康管理技术规范 |
| **发布机构** | 国家卫生和计划生育委员会（现国家卫生健康委） |
| **权威等级** | **P0**（国家现行卫生标准，最高等级） |
| **发布/实施** | 发布 2015-11-04 ／ 实施 2016-04-01（已从发布页确认） |
| **官方入口** | https://www.nhc.gov.cn/wjw/c100309/201511/6725aa6b7b6846058e3abf6ab3ee32d4.shtml |
| **现状** | 只有发布页元数据 **281 字符**；正文实质缺失。已贡献 **1 个切片**（元数据而已） |

**为什么缺**：官方 PDF（`knowledge/raw/07_primarycare/PRIM003.pdf`，39 页，3.9 MB）**有文本层但编码损坏** —— ToUnicode CMap 是坏的，抽出的是 `犐犆犛１１．０２０`（本应是 `ICS 11.020`）、`犠犛／犜４８４—２０１５`（本应是 `WS/T 484—2015`）。这类文本若入库会直接污染 Citation，所以**主动弃用**、改用发布页元数据占位。

**需要找什么**（任一即可）：

1. **同一份 PDF 的另一个版本**，带正确的文字层（很多标准在「卫生标准网」「国家标准全文公开系统」上有可复制的版本）
2. **官方 Word / HTML 版全文**
3. **扫描件也可以**，但要能 OCR 且愿意人工校对（见下面「OCR 路径」）

**去哪找**：

- 国家卫生健康委**卫生标准**栏目：https://www.nhc.gov.cn/wjw/c100309/ 搜 `WS/T 484`
- **卫生标准网**：http://wsb.nhc.gov.cn/ （关键词：`老年人健康管理技术规范`）
- **国家标准全文公开系统**：https://openstd.samr.gov.cn/ （部分卫生行业标准可查）
- **国家卫健委标准查询**：https://www.nhc.gov.cn/wjw/wsbzcxpt/ （搜标准号 `WS/T 484-2015`）
- 搜索引擎关键词建议：`WS/T 484-2015 老年人健康管理技术规范 pdf`、`"WS/T 484" 老年人健康管理`
- ⚠️ **不要**用道客巴巴/百度文库等转载站的内容，必须是官方发布或官方授权的电子版

**怎么判断找对了**：

- 打开后能**用鼠标选中并复制**文字（而不是只能选中整张图片）
- 复制出来的第一页应包含 **`ICS 11.020`**、**`WS/T 484—2015`** 这样的**正常 ASCII 文本**
  （如果你复制出来是 `犐犆犛`、`犠犛` 这种怪字，说明还是坏的 ToUnicode，换一个来源）
- 页数应与官方一致（39 页左右）

**找到后**：按 [标准入库流程](#找到文件后的标准入库流程) 操作，编号 `PRIM003`。

---

## 缺口 B｜3 份「无文本层扫描件」

这三篇的官方页面都是**发布通知页**（正文很短），真正内容在同页**附件 PDF** 里，但那些 PDF 是**纯扫描图片、没有文字层**，程序抽不出一个字。

| 编号 | 标题 | 等级 | 页面 | 附件 PDF 现状 |
|---|---|---|---|---|
| `CORE002` | 基层慢性病健康管理服务能力建设指引 | P1 | [nhc 页面](https://www.nhc.gov.cn/jws/c100073/202511/d3b6755fe7004cdeac938bf77b6a4a80.shtml) | 1.85 MB，**抽出 0 字符 / 10 页** |
| `LIFE001` | 高血压等慢性病营养和运动指导原则（2024年版） | P1 | [nhc 页面](https://www.nhc.gov.cn/ylyjs/gzdt/202407/256b4eb8398440a8811344c7be50a333.shtml) | 5.22 MB，**抽出 417 字符 / 14 页** |
| `LIFE008` | 居民体重管理核心知识（2024年版）及释义 | P1 | [nhc 页面](https://www.nhc.gov.cn/ylyjs/gzdt/202407/9ec6136773bc41048a39f275fcc37b44.shtml) | **抽出 117 字符 / 1 页** |

**需要找什么**：任一即可

1. 同一份指南的**带文本层 PDF**（很多食养指南在网上有可复制的版本）
2. **OCR 结果**（见下）

**OCR 路径**（自己动手的方案）：

```
1. 用 PyMuPDF 把 PDF 每页渲染成 300 DPI 的 PNG
2. 用中文 OCR（PaddleOCR / tesseract + chi_sim / 百度/腾讯 OCR API）识别
3. 把识别结果拼成一份 .html 文件（用 <h1>/<h2>/<p> 标出标题与段落）
4. ⚠️ 必须人工校对：OCR 会认错数字（例如 5 当成 S、140 当成 14O），
   而这份知识库是给慢病管理用的，数字必须准确
5. 校对完成后按标准流程入库
```

> 💡 `LIFE001` 那一页其实同时发布了 **4 份**营养和运动指导原则（高血压 / 高血糖症 / 高脂血症 / 高尿酸血症）。
> 目前只收录了与标题同名的《高血压营养和运动指导原则》。如果想补齐另外 3 份，
> 可以作为**新文档**（新编号）加入，而不是替换现有条目 —— 需要与研发确认编号。

---

## 缺口 C｜WHO 3 篇只有出版页摘要

| 编号 | 标题 | 等级 | 官方入口 |
|---|---|---|---|
| `WHO001` | WHO PEN（Package of essential NCD interventions） | P4 | https://www.who.int/publications/i/item/9789240009226 |
| `WHO002` | WHO HEARTS: Technical package for CVD management — Risk-based CVD Management | P4 | https://www.who.int/publications/i/item/9789240001367 |
| `WHO003` | WHO HEARTS: Technical package for CVD management — Healthy-lifestyle counselling | P4 | https://www.who.int/publications/i/item/WHO-NMH-NVI-18-1 |

**为什么缺**：抓取时只拿到了 WHO 出版页（摘要 + 元数据，1.4K~2.4K 字符）。
WHO 已把知识库从 `iris.who.int/bitstream/handle/...` 改成
`iris.who.int/server/api/core/bitstreams/<uuid>/content`，旧链接返回 755 字节的 HTML 错误页。

**去哪找**：

- 打开上面任一官方入口页，页面上通常有 **"Download"** 或 **"PDF"** 按钮 ——
  点进去，地址栏里就是新的 `<uuid>/content` 形式的直链
- 也可以在页面上用 F12 / 「检查元素」，搜索 `bitstreams` 找到直链
- WHO 出版物检索：https://www.who.int/publications （搜 `HEARTS technical package`、`WHO PEN`）

**怎么判断找对了**：下载下来是 **几 MB 的 PDF**，不是 755 字节的 HTML。

**注意**：这三份是**英文**文档。项目约定：
`language=en`、正文保留英文原文、**不做翻译**。

**找到后**：按标准流程入库，注意 `local_file` 指向 `.pdf`。

---

## 缺口 D｜3 篇付费墙文档

契约**明令禁止绕过付费墙或版权限制**，所以这 3 篇只能靠**正规途径**。

| 编号 | 标题 | 等级 | 官方出处 | 为什么没收录 |
|---|---|---|---|---|
| `DM002` | 中国2型糖尿病防治指南（2020年版） | P3 | 中华医学会糖尿病学分会 ／ `rs.yiigle.com/CN2021/1315505.htm` | 出版社付费墙（万方/中华医学期刊网），无官方免费全文 |
| `DM003` | 国家基层糖尿病防治管理指南（2022） | P3 | 中华内科杂志 2022, 61(3):249-262，DOI `10.3760/cma.j.cn112138-20220120-000063` | 同上 |
| `MULTI001` | "三高"共管规范化诊疗中国专家共识（2023版） | P3 | `rs.yiigle.com/CN2021/1467649.htm` | 同上 |

**可行途径**（按推荐顺序）：

1. **机构采购授权**：由 CareFlow 方通过万方 / 中华医学期刊网 / 中国知网购买全文使用权
2. **找免费官方版本**：部分指南会由**国家级中心官网**同步发布免费版，例如
   - 国家基层糖尿病防治管理办公室：http://www.chinadmtc.org.cn/
   - 国家心血管病中心 / 国家基层高血压防治管理办公室：https://hbp-office.nccd.org.cn/
   - 搜索关键词：`国家基层糖尿病防治管理指南 2022 pdf 免费`、`三高共管 专家共识 2023 pdf`
3. **作者团队/学会官网**：中华医学会相关分会官网有时会放出 PDF
4. ⚠️ **不要**用盗版文库站的内容 —— 法律风险且无法保证与官方版本一致

**找到后**：把 `status` 从 `draft` 改为 `active`，`local_file` 指向实际文件，
`sha256` 填写，`notes` 里写清来源与授权说明。见标准流程。

---

## 缺口 E｜effective_date 28/30 为空

**问题**：manifest 的 `effective_date`（实施日期）只有 `HTN001`（2026-03-01）和
`PRIM003`（2016-04-01）填上了。契约要求「**版本冲突时优先中国当前有效且适用于基层场景的正式规范**」，
但没有实施日期就**无法自动判断哪一份是现行有效版本**。

**当前可用信息**：`publish_date` 已有 **23/30**（发布日期通常≠实施日期）。

**要补什么**：每篇文档的**实施日期 / 施行日期 / 生效日期**。

**去哪找**：

| 来源类型 | 实施日期通常在哪儿 |
|---|---|
| 卫生标准（如 WS/T 系列） | 标准**首页的「实施」栏**，或官网标准页的「实施时间」 |
| 国家卫健委政策文件 | 正文**最后一段**（"本意见自 X 年 X 月 X 日起施行"），或文末落款日期 |
| 食养指南 PDF | 封面页或前言 |
| WHO 文档 | 封面 `Published` 日期（注意 WHO 一般只有出版日期，没有实施日期 —— 这一项可留空） |

**还需要注意**：**7 篇连 `publish_date` 都没有**：

```
HTN002   国家基层高血压防治管理指南 2025版        （来源是疾控下载页，无发布日期）
DM002    中国2型糖尿病防治指南（2020年版）        ← 付费墙，见缺口 D
DM003    国家基层糖尿病防治管理指南（2022）        ← 付费墙，见缺口 D
MULTI001 "三高"共管规范化诊疗中国专家共识（2023版） ← 付费墙，见缺口 D
WHO001   WHO PEN                                  （英文出版页，日期格式不同）
WHO002   WHO HEARTS: Risk-based CVD Management
WHO003   WHO HEARTS: Healthy-lifestyle counselling
```

**怎么做**：把找到的日期整理成一张对照表（`文档编号 → 实施日期`）交给研发，
或直接改 manifest 的 `effective_date` 列（格式 `YYYY-MM-DD`）。
**找不到就留空，不要猜测** —— 编造日期比没有日期更危险。

---

## 找到文件后的标准入库流程

> 交给**懂一点命令行**的人做，或者直接交给研发。

### 第 1 步：放文件

把文件放到对应域目录，**文件名必须是 `<文档编号>.<扩展名>`**：

```
knowledge/raw/01_core/CORE002.pdf
knowledge/raw/06_lifestyle/LIFE001.pdf
knowledge/raw/07_primarycare/PRIM003.pdf
knowledge/raw/08_who/WHO001.pdf
```

扩展名只支持 **`.pdf`** 和 **`.html`** 两种。
如果是 OCR 文本或 Word，请先转成 `.html`（用 `<h1>/<h2>/<p>` 标出标题与段落）。

### 第 2 步：更新下载报告（**这一步最容易漏**）

`preprocess_documents.py` 读的是 **`knowledge/raw/_download_report.json`**，**不是 manifest**。
在该文件里找到对应 `document_id` 的那一条，改这几个字段：

```jsonc
{
  "document_id": "PRIM003",
  "local_file": "knowledge/raw/07_primarycare/PRIM003.pdf",  // 指向新文件
  "ext": "pdf",                    // "pdf" 或 "html"
  "content_kind": "pdf",
  "status": "downloaded",
  "bytes": 3934877,                // 实际字节数
  "sha256": "<64位小写十六进制>",   // 见下方命令
  "error": "",
  "annex_pdf": null,               // ⚠️ 必须清空，否则会优先用旧附件
  "secondary_files": []            // ⚠️ 同上，必须清空
}
```

> ⚠️ **两个必踩的坑**：`annex_pdf` 和 `secondary_files` 只要有一个非空，
> `preprocess_documents.py` 就会**优先使用那个旧文件**，你的新文件不会被用上。
> 处理 PRIM003 时我就踩了一次。

算 sha256：

```powershell
# Windows PowerShell
(Get-FileHash "knowledge\raw\07_primarycare\PRIM003.pdf" -Algorithm SHA256).Hash.ToLower()
```

### 第 3 步：更新 manifest

```bash
python scripts/build_manifest.py      # 从报告重新生成 manifest
```

然后手工核对生成的 `knowledge/manifest/knowledge_manifest.csv`：
`local_file`、`sha256`、`status`（付费墙那 3 篇要改成 `active`）、`notes`（写清来源与授权）。

### 第 4 步：重跑管线并验证

```bash
python scripts/extract_publish_dates.py    # 抽发布/实施日期
python scripts/preprocess_documents.py     # 清洗
python scripts/build_chunks.py             # 切片（必须看到 0 verbatim problems）
python scripts/validate_manifest.py        # 必须 VALIDATION PASSED，退出码 0
python scripts/verify_sources.py           # 必须 VERIFY PASSED
python scripts/verify_content_match.py     # 看该文档的 ratio，应 ≥ 0.34（OK）
python -m pytest tests/ -q                 # 期望 497 passed
python scripts/evaluate.py --provider mock # 期望 6 套 100%、RAG ≥96.88%
```

### 第 5 步：提交

```bash
git add knowledge/ && git commit -m "data: 补齐 <文档编号> 官方全文"
git push origin main
```

---

## 验收标准

一篇文档算「补齐成功」，必须**同时**满足：

| # | 标准 | 怎么验证 |
|---|---|---|
| 1 | 本地文件存在且 sha256 与 manifest 一致 | `python scripts/validate_manifest.py` → 退出码 0 |
| 2 | `status=active`（付费墙那 3 篇） | 同上 |
| 3 | 清洗后字符数**明显大于**原来的发布页正文 | 看 `knowledge/processed/_preprocess_report.json` 的 `chars` |
| 4 | **不是乱码** | `python scripts/verify_content_match.py` → 该文档显示 `OK ratio≥0.34`，不是 `MISMATCH` |
| 5 | 切片是**逐字连续片段** | `python scripts/build_chunks.py` → `0 verbatim problems` |
| 6 | 端到端可用 | `python -m pytest tests/test_live_knowledge.py -q` → 全绿 |

---

## 参考：当前全部文档状态一览

| 编号 | 标题（简） | 等级 | 状态 | 字符数 | 缺口 |
|---|---|---|---|---|---|
| CORE001 | 关于加强基层慢性病健康管理服务的指导意见 | P1 | ✅ | 3,264 | — |
| **CORE002** | 基层慢性病健康管理服务能力建设指引 | P1 | ⚠️ | **476** | 缺正文（扫描件）→ 缺口 B |
| CORE003 | 国家基本公共卫生服务规范（第三版） | P1 | ✅ | 81,780 | — |
| CORE004 | 关于做好2025年基本公共卫生服务工作的通知 | P1 | ✅ | 2,452 | — |
| CORE005 | 中国公民健康素养——基本知识与技能（2024年版） | P1 | ✅ | 2,641 | — |
| CORE006 | 中国公民健康素养——基本知识与技能释义（2024年版） | P1 | ✅ | 43,653 | — |
| HTN001 | 基层医疗卫生机构高血压防治管理标准 WS/T 872—2025 | P0 | ✅ | 3,815 | — |
| HTN002 | 国家基层高血压防治管理指南 2025版 | P3 | ✅ | 32,920 | 无发布日期 → 缺口 E |
| HTN003 | 健康中国行动—心脑血管疾病防治行动实施方案 | P1 | ✅ | 4,791 | — |
| DM001 | 健康中国行动——糖尿病防治行动实施方案 | P1 | ✅ | 6,511 | — |
| **DM002** | 中国2型糖尿病防治指南（2020年版） | P3 | ⛔ draft | 0 | 付费墙 → 缺口 D |
| **DM003** | 国家基层糖尿病防治管理指南（2022） | P3 | ⛔ draft | 0 | 付费墙 → 缺口 D |
| COPD001 | 慢性阻塞性肺疾病患者健康服务规范（试行） | P1 | ✅ | 5,307 | — |
| COPD002 | 健康中国行动——慢性呼吸系统疾病防治行动实施方案 | P1 | ✅ | 4,579 | — |
| **MULTI001** | "三高"共管规范化诊疗中国专家共识（2023版） | P3 | ⛔ draft | 0 | 付费墙 → 缺口 D |
| MULTI002 | 中国血脂管理指南（2023年） | P3 | ✅ | 129,552 | — |
| **LIFE001** | 高血压等慢性病营养和运动指导原则（2024年版） | P1 | ⚠️ | **1,329** | 缺正文（扫描件）→ 缺口 B |
| LIFE002 | 成人高血压食养指南（2023年版） | P1 | ✅ | 37,115 | — |
| LIFE003 | 成人糖尿病食养指南（2023年版） | P1 | ✅ | 43,140 | — |
| LIFE004 | 成人高脂血症食养指南（2023年版） | P1 | ✅ | 25,909 | — |
| LIFE005 | 成人高尿酸血症与痛风食养指南（2024年版） | P1 | ✅ | 48,460 | — |
| LIFE006 | 成人肥胖食养指南（2024年版） | P1 | ✅ | 55,999 | — |
| LIFE007 | 成人慢性肾脏病食养指南（2024年版） | P1 | ✅ | 58,829 | — |
| **LIFE008** | 居民体重管理核心知识（2024年版）及释义 | P1 | ⚠️ | **597** | 缺正文（扫描件）→ 缺口 B |
| PRIM001 | 居民电子健康档案首页基本内容（试行） | P1 | ✅ | 5,015 | — |
| PRIM002 | 家庭医生签约基本服务包清单（试行） | P1 | ✅ | 8,330 | — |
| **PRIM003** | 老年人健康管理技术规范 WS/T 484—2015 | **P0** | ⚠️ | **281** | **缺正文（ToUnicode 损坏）→ 缺口 A** |
| **WHO001** | WHO PEN | P4 | ⚠️ | **1,429** | 仅摘要 → 缺口 C |
| **WHO002** | WHO HEARTS: Risk-based CVD Management | P4 | ⚠️ | **2,259** | 仅摘要 → 缺口 C |
| **WHO003** | WHO HEARTS: Healthy-lifestyle counselling | P4 | ⚠️ | **2,419** | 仅摘要 → 缺口 C |

> 字符数 = `knowledge/processed/<编号>.md` 的长度，`knowledge/processed/_preprocess_report.json` 里有完整记录。
