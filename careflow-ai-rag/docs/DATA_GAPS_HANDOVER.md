# CareFlow RAG 知识库缺口补全与 DeepSeek 执行交接文档

> 用途：本文件可直接交给 DeepSeek，作为当前 CareFlow RAG 知识库缺失资料、元数据补全、原文替换与 Manifest 修复的执行基线。  
> 原则：只使用官方、正规、可追溯来源；不得为了“补齐字段”而伪造发布日期、实施日期、正文或 PDF。

---

# 1. 当前任务目标

请在现有 CareFlow RAG 项目基础上，继续补全知识库中已经识别出的数据缺口，重点完成以下工作：

1. 替换错误、空白、网页壳、摘要页或不完整扫描件。
2. 补全可以可靠确认的 `publish_date`。
3. 只有在原文明确出现“实施 / 施行 / 生效日期”时，才填写 `effective_date`。
4. 补全 WHO 3 份完整英文原文。
5. 对 LIFE001、LIFE008 这类“一个页面包含多个附件”的情况进行合理拆分。
6. 维护并修复 `knowledge/manifest/knowledge_manifest.csv`。
7. 更新 `local_file`、`sha256`、`status`、`source_url` 等字段。
8. 重新执行 Manifest 校验、文档预处理、Chunk 构建及 RAG 检索验证。
9. 不得绕过付费墙、版权限制或使用盗版站。

---

# 2. 最高优先级：PRIM003

## PRIM003｜老年人健康管理技术规范 WS/T 484—2015

当前问题：

- 项目中现有文件疑似只是网页正文或抓取错误内容。
- 原文件只有约 281 字符，不是完整国家标准。
- 正确文件应为约 39 页 PDF。

应修复为：

```text
document_id = PRIM003
title = 老年人健康管理技术规范
standard_no = WS/T 484—2015
authority = 国家卫生计生委 / 国家卫生健康委标准体系
authority_level = P0
publish_date = 2015-11-04
effective_date = 2016-04-01
language = zh-CN
status = active
```

官方来源：

- 国家卫健委标准页面  
  https://www.nhc.gov.cn/wjw/c100309/201511/6725aa6b7b6846058e3abf6ab3ee32d4.shtml

- 官方完整 PDF  
  https://www.nhc.gov.cn/ewebeditor/uploadfile/2016/01/20160128143208616.pdf

执行要求：

1. 下载官方 PDF。
2. 替换当前错误的 PRIM003 本地文件。
3. 重新计算 SHA256。
4. 更新 Manifest。
5. 确认 PDF 页数、首页标准号、发布日期和实施日期正确。
6. 重新进行文档解析和 Chunk 构建。

---

# 3. P1：缺失或不完整正文

## CORE002｜基层慢性病健康管理服务能力建设指引

当前问题：

- 当前正文为空或抽取失败。
- 应替换为国家卫健委正式附件 PDF。

建议元数据：

```text
publish_date = 2025-11-20
document_date = 2025-11-14
effective_date = 空
authority = 国家卫生健康委办公厅
authority_level = P1
language = zh-CN
status = active
```

官方页面：

https://www.nhc.gov.cn/jws/c100073/202511/d3b6755fe7004cdeac938bf77b6a4a80.shtml

官方 PDF：

https://www.nhc.gov.cn/jws/c100073/202511/d3b6755fe7004cdeac938bf77b6a4a80/files/%E9%99%84%E4%BB%B6%EF%BC%9A%E5%9F%BA%E5%B1%82%E6%85%A2%E6%80%A7%E7%97%85%E5%81%A5%E5%BA%B7%E7%AE%A1%E7%90%86%E6%9C%8D%E5%8A%A1%E8%83%BD%E5%8A%9B%E5%BB%BA%E8%AE%BE%E6%8C%87%E5%BC%95-20251120153850169.pdf

执行要求：

- 下载官方 PDF。
- 替换当前空文件或异常抽取结果。
- 重新解析正文。
- 保留标题层级、章节号、表格和关键上下文。

---

# 4. LIFE001 需要拆分，不允许互相覆盖

原项目中 LIFE001 实际对应的是一组“慢性病营养和运动指导原则”。

国家卫健委正式页面包含 4 份独立附件：

```text
LIFE001   高血压营养和运动指导原则（2024年版）
LIFE001A  高血糖症营养和运动指导原则（2024年版）
LIFE001B  高脂血症营养和运动指导原则（2024年版）
LIFE001C  高尿酸血症营养和运动指导原则（2024年版）
```

统一建议元数据：

```text
publish_date = 2024-07-01
document_date = 2024-06-17
effective_date = 空
authority = 国家卫生健康委办公厅
authority_level = P1
language = zh-CN
status = active
```

官方统一入口：

https://www.nhc.gov.cn/ylyjs/gzdt/202407/256b4eb8398440a8811344c7be50a333.shtml

执行要求：

1. 不允许用其中一份文件覆盖 LIFE001。
2. 为 4 份文件分别建立独立 `document_id`。
3. 每份文件单独保存。
4. 每份文件单独计算 SHA256。
5. 根据内容设置 disease / scenario。
6. 所有文件都必须保持来源可追溯。

---

# 5. LIFE008｜居民体重管理核心知识

LIFE008 实际包含至少两份正式附件：

```text
1. 居民体重管理核心知识（2024年版）
2. 居民体重管理核心知识（2024年版）释义
```

建议拆分：

```text
LIFE008   居民体重管理核心知识（2024年版）
LIFE008A  居民体重管理核心知识（2024年版）释义
```

建议元数据：

```text
publish_date = 2024-07-02
document_date = 2024-06-27
effective_date = 空
authority = 国家卫生健康委办公厅
authority_level = P1
language = zh-CN
status = active
```

官方页面：

https://www.nhc.gov.cn/ylyjs/gzdt/202407/9ec6136773bc41048a39f275fcc37b44.shtml

执行要求：

- 不要继续使用仅有少量字符的页面抓取结果。
- 优先下载页面提供的正式附件。
- “核心知识”和“释义”分别入库。

---

# 6. 需要补全的发布日期

以下日期可以进入 Manifest 的 `publish_date`。

| document_id | 文档 | publish_date | effective_date |
|---|---|---:|---:|
| HTN002 | 国家基层高血压防治管理指南 2025版 | 2025-09-24 | 空 |
| DM002 | 中国2型糖尿病防治指南（2020年版） | 2021-04-27 | 空 |
| DM003 | 国家基层糖尿病防治管理指南（2022） | 2022-03-01 | 空 |
| MULTI001 | “三高”共管规范化诊疗中国专家共识（2023版） | 2023-07-24 | 空 |
| WHO001 | WHO PEN | 2020-09-07 | 空 |
| WHO002 | HEARTS: Risk-based CVD Management | 2020-07-13 | 空 |
| WHO003 | HEARTS: Healthy-lifestyle counselling | 2018-05-02 | 空 |

可以直接用于修补：

```csv
document_id,publish_date,effective_date
HTN002,2025-09-24,
DM002,2021-04-27,
DM003,2022-03-01,
MULTI001,2023-07-24,
WHO001,2020-09-07,
WHO002,2020-07-13,
WHO003,2018-05-02,
```

---

# 7. effective_date 的处理规则

这是本次修复中必须严格执行的一条规则。

## 禁止行为

不得因为 Manifest 中大量 `effective_date` 为空，就：

- 用 `publish_date` 填充 `effective_date`；
- 用网页发布日期代替实施日期；
- 根据经验猜测实施日期；
- 自行生成“默认生效日期”。

## 正确规则

只有满足以下条件之一时，才允许填写：

```text
原文明确写明：
- 自 XXXX 年 XX 月 XX 日起实施
- 自 XXXX 年 XX 月 XX 日起施行
- 实施日期
- 生效日期
```

否则：

```text
effective_date = 空
```

因此大量指南、共识、WHO 文件的 `effective_date` 为空是正常现象，不属于数据错误。

---

# 8. WHO 三份文档必须使用完整英文原文

## WHO001｜WHO PEN

正式名称：

```text
WHO package of essential noncommunicable (PEN)
disease interventions for primary health care
```

建议元数据：

```text
document_id = WHO001
authority = World Health Organization
authority_level = P4
publish_date = 2020-09-07
effective_date = 空
language = en
status = active
```

WHO 官方页面：

https://www.who.int/publications/i/item/9789240009226

完整 PDF：

https://iris.who.int/bitstream/handle/10665/334186/9789240009226-eng.pdf

应为完整英文 PDF，不要只保存摘要网页。

---

## WHO002｜HEARTS: Risk-based CVD Management

建议元数据：

```text
document_id = WHO002
authority = World Health Organization
authority_level = P4
publish_date = 2020-07-13
effective_date = 空
language = en
status = active
```

官方页面：

https://www.who.int/publications/i/item/9789240001367

执行要求：

- 从 WHO 官方页面下载正式文档。
- 不使用第三方转载 PDF。
- 保留英文原文，不翻译后替换原文。

---

## WHO003｜HEARTS: Healthy-lifestyle counselling

建议元数据：

```text
document_id = WHO003
authority = World Health Organization
authority_level = P4
publish_date = 2018-05-02
effective_date = 空
language = en
status = active
```

官方页面：

https://www.who.int/publications/i/item/WHO-NMH-NVI-18-1

官方 PDF：

https://iris.who.int/bitstream/handle/10665/260422/WHO-NMH-NVI-18.1-eng.pdf?sequence=1

执行要求：

- 使用完整英文原文。
- 不使用只有摘要、HTML 页面、几十字正文的版本。

---

# 9. DM002 / DM003 / MULTI001 的版权处理

## DM002｜中国2型糖尿病防治指南（2020年版）

正式出处：

```text
中华糖尿病杂志
2021
13(4):315-409
DOI: 10.3760/cma.j.cn115791-20210221-00095
```

建议来源：

https://rs.yiigle.com/CN2021/1315505.htm

若中华医学会体系页面能够合法读取正文，则允许：

- 从正规页面抽取；
- 保存为内部结构化文本；
- 保留原始 URL；
- 记录来源。

禁止：

- 从盗版 PDF 网站下载；
- 绕过登录或付费机制；
- 使用来历不明的网盘资源。

---

## DM003｜国家基层糖尿病防治管理指南（2022）

正式出处：

```text
中华内科杂志
2022
61(3):249-262
DOI: 10.3760/cma.j.cn112138-20220120-000063
publish_date = 2022-03-01
```

当前状态：

> 这是目前仍然需要谨慎处理的核心缺口之一。

如果无法从正规公开渠道获得完整正文：

```text
不要伪造全文
不要绕过付费墙
不要使用盗版来源
```

允许保留：

- 正式元数据；
- DOI；
- 正式出处；
- 核验 URL；
- 状态说明。

如果项目的 `status` 设计允许，可以根据实际情况设置：

```text
draft
或 disabled
```

直到拿到合法全文后再设为可生产检索状态。

---

## MULTI001｜“三高”共管规范化诊疗中国专家共识（2023版）

建议元数据：

```text
publish_date = 2023-07-24
effective_date = 空
authority_level = P3
```

正式入口：

https://rs.yiigle.com/CN2021/1467649.htm

如果官方页面正文可以正常读取：

- 优先使用官方 HTML 正文；
- 保留来源；
- 不再寻找盗版 PDF。

---

# 10. HTN002

## 国家基层高血压防治管理指南 2025版

项目原规划官方入口：

https://hbp-office.nccd.org.cn/download.html

建议：

```text
document_id = HTN002
title = 国家基层高血压防治管理指南 2025版
publish_date = 2025-09-24
effective_date = 空
language = zh-CN
status = active
```

注意：

- 如果官方下载页存在多个版本，要确认文件确实为 2025 版。
- 下载后检查封面、版本、页数、正文标题。
- 不要仅保存下载页 HTML。

---

# 11. Manifest 必须维护的关键字段

项目中的：

```text
knowledge/manifest/knowledge_manifest.csv
```

至少保证以下字段正确：

```text
document_id
title
authority
authority_level
document_type
version
publish_date
effective_date
replaced_by
status
diseases
scenarios
language
source_url
local_file
sha256
qianfan_kb
notes
```

状态只允许项目约定的值：

```text
active
superseded
draft
disabled
```

生产检索只允许：

```text
status = active
```

---

# 12. 文档下载后的验证要求

每下载一份文件，都必须执行以下检查：

## 12.1 文件级检查

```text
文件存在
文件大小合理
不是 HTML 假装 PDF
不是 0 字节
不是错误页
不是登录页
不是验证码页
不是只有摘要
```

## 12.2 内容级检查

至少检查：

```text
标题正确
发布机构正确
版本正确
发布日期正确
页数合理
正文不是乱码
正文不是空白
```

## 12.3 Manifest 检查

```text
document_id 唯一
source_url 非空
local_file 存在
sha256 正确
authority_level 合法
status 合法
language 正确
版本关系正确
```

---

# 13. 文档预处理要求

不要把 PDF 直接粗暴切成固定长度文本。

应：

1. 去除重复页眉页脚。
2. 保留章节标题。
3. 保留章节编号。
4. 保留表格标题。
5. 保留数字、单位和范围。
6. 每个 Chunk 尽量只表达一个主题。
7. 禁止把整本 PDF 作为一个 Chunk。
8. 禁止切断关键条款。
9. 每个 Chunk 必须携带 `document_id`。
10. 每个 Chunk 保留 source / section / authority 等 Metadata。
11. 保存清洗后的中间文本，方便人工抽查。
12. 不修改原文事实。

---

# 14. 建议的 Metadata

每个 Chunk 至少携带：

```json
{
  "document_id": "HTN002",
  "title": "文档名称",
  "authority": "发布机构",
  "authority_level": "P1",
  "version": "版本",
  "publish_date": "YYYY-MM-DD",
  "effective_date": null,
  "diseases": ["HYPERTENSION"],
  "scenarios": ["health_education", "followup"],
  "language": "zh-CN",
  "section": "章节名称",
  "source_url": "https://..."
}
```

---

# 15. 修复后必须重新运行的流程

完成知识文件修复后，按以下顺序执行：

```text
1. verify_sources
2. validate_manifest
3. preprocess_documents
4. build_chunks
5. sync_qianfan / 同步知识库
6. evaluate
7. RAG 回归测试
```

如果项目脚本名不同，则以现有代码为准，但整体顺序不能省略。

---

# 16. RAG 验证重点

至少针对以下问题进行回归测试：

```text
高血压患者平时需要注意什么？
老年人健康管理包括哪些内容？
糖尿病患者基层随访需要注意哪些问题？
“三高”共管是什么意思？
居民如何进行科学体重管理？
WHO PEN 对基层非传染性疾病管理提出了什么框架？
```

检查：

```text
是否命中正确知识域
是否优先命中高权威资料
是否返回真实 Citation
Citation 是否能追溯到 document_id
回答是否和原文一致
是否出现模型自行补充医疗事实
```

---

# 17. 最终修复状态目标

目标结果：

```text
PRIM003
→ 使用 39 页国家标准原始 PDF
→ 已解决

CORE002
→ 使用国家卫健委正式 PDF
→ 已解决

LIFE001
→ 拆分为 4 份正式指导原则
→ 已解决

LIFE008
→ 拆分“核心知识”和“释义”
→ 已解决

HTN002
→ 补 publish_date
→ 使用 2025 版正式文件

WHO001
→ 完整英文原文
→ 已解决

WHO002
→ 完整英文原文
→ 已解决

WHO003
→ 完整英文原文
→ 已解决

DM002
→ 使用正规可读取来源
→ 原则上可解决

MULTI001
→ 使用中华医学会正规正文
→ 原则上可解决

DM003
→ 若没有合法完整全文
→ 保留元数据，但不得伪造 / 盗版补齐
→ 当前唯一重点未完全解决项
```

---

# 18. DeepSeek 执行约束

你不是只生成报告，而是要在现有项目中实际执行修复。

必须：

```text
读取当前项目
检查现有 Manifest
检查 knowledge/raw
检查 processed/chunks
检查现有下载文件
确认每一项当前实际状态
下载可以合法获得的官方资料
替换错误文件
新增需要拆分的文件
更新 Manifest
计算 SHA256
重新预处理
重新构建 Chunk
重新同步知识库
重新运行测试
输出修复报告
```

禁止：

```text
伪造文件
伪造日期
伪造 SHA256
用 publish_date 冒充 effective_date
盗版下载
绕过付费墙
用第三方博客替代官方来源
为了测试通过而删除校验逻辑
把失败项直接标记为成功
```

---

# 19. 最终交付要求

最终至少输出：

```text
1. 修复后的 knowledge_manifest.csv
2. 新增 / 替换文件清单
3. 每个文件的 source_url
4. 每个文件的 local_file
5. 每个文件的 SHA256
6. Manifest 校验结果
7. 文档解析结果
8. Chunk 构建统计
9. RAG 测试结果
10. 未解决问题清单
```

报告建议明确区分：

```text
RESOLVED
PARTIALLY_RESOLVED
BLOCKED
NOT_AVAILABLE_LEGALLY
FAILED
```

不要把 `BLOCKED` 或 `NOT_AVAILABLE_LEGALLY` 写成 PASS。

---

# 20. 一句话执行目标

> 在不伪造医疗资料、不使用盗版、不绕过版权限制的前提下，把 CareFlow RAG 当前已知的知识库缺口尽可能全部补齐；用国家卫健委、中华医学会、WHO 等正规来源替换空文件、网页壳和摘要文件，修复 Manifest、重新处理文档与 Chunk，并完成一次完整的 RAG 回归验证。DM003 如果仍无法合法取得完整全文，应如实保留为未完全解决项，而不是强行补齐。
