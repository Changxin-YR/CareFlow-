# CareFlow 康脉智护 AI/RAG —— 测试报告

> **本文件只记录真实执行结果。**
> 每一项都可在本仓库用文末给出的命令复现。未真实执行的内容一律标注
> `BLOCKED`，不写入"通过"。
>
> 执行时间：2026-09-17（UTC）｜执行环境：见 §1

---

## 1. 执行环境

| 项 | 值 |
|---|---|
| OS | Windows（Docker Desktop 29.7.2，WSL2 后端） |
| Python（宿主） | 3.14.4 |
| Python（容器） | 3.12-slim |
| 关键依赖 | fastapi 0.141.1、pydantic 2.13.5、httpx 0.28.1、uvicorn 0.53.0、pytest 8.3.5 |
| AI Provider（测试） | `mock`（确定性规则引擎，**不访问任何外部网络**） |
| 知识库 | 30 篇登记 / 27 篇 active / 1041 个切片 |

---

## 2. 单元与集成测试

```
$ python -m pytest tests/ -q
497 passed in 3.80s
```

| 测试文件 | 用例数 | 结果 |
|---|---:|---|
| `test_safety_regressions.py` | 76 | ✅ 全通过 |
| `test_safety.py` | 47 | ✅ 全通过 |
| `test_text_normalization.py` | 44 | ✅ 全通过 |
| `test_extraction_service.py` | 37 | ✅ 全通过 |
| `test_schemas.py` | 30 | ✅ 全通过 |
| `test_api_contract.py` | 24 | ✅ 全通过 |
| `test_qianfan_client.py` | 24 | ✅ 全通过 |
| `test_retrieval.py` | 23 | ✅ 全通过 |
| `test_routing.py` | 23 | ✅ 全通过 |
| `test_prompts.py` | 21 | ✅ 全通过 |
| `test_api_rag.py` | 20 | ✅ 全通过 |
| `test_llm_paths.py` | 19 | ✅ 全通过 |
| `test_citation.py` | 17 | ✅ 全通过 |
| `test_api_followup.py` | 16 | ✅ 全通过 |
| `test_manifest_service.py` | 16 | ✅ 全通过 |
| `test_api_extract.py` | 14 | ✅ 全通过 |
| `test_api_health_status.py` | 12 | ✅ 全通过 |
| `test_domain_filter.py` | 11 | ✅ 全通过 |
| `test_live_knowledge.py` | 11 | ✅ 全通过 |
| `test_http_headers.py` | 6 | ✅ 全通过 |
| `test_logging.py` | 6 | ✅ 全通过 |
| **合计** | **497** | **497 passed / 0 failed / 0 skipped** |

契约要求的覆盖项全部命中：Manifest、Schema、Router、Citation Validator、
Safety、Mock Qianfan、Timeout、Invalid JSON、No Evidence、Health API、
Extract API、RAG API、FollowUp API。

覆盖率（`pytest --cov=app`）：

```
TOTAL   2751 stmts   268 miss   90%
```

---

## 3. 真实知识库集成测试（`test_live_knowledge.py`）

这 11 项**不是**夹具测试，而是直接读取 `knowledge/` 下的真实产物：

| 断言 | 结果 |
|---|---|
| manifest 列顺序与契约完全一致 | ✅ |
| document_id 唯一、status/authority_level 合法、source_url 非空 | ✅ |
| **status=active 的行：local_file 存在且 sha256 与文件实际一致** | ✅ |
| 每个 chunk 的 document_id 都在 manifest 中 | ✅ |
| chunk_id 全局唯一 | ✅ |
| chunk 的 authority_level / source_url 与 manifest 一致 | ✅ |
| **非 active 文档的切片不在索引中** | ✅ |
| `/health` 报告 manifest=ok、knowledge=ok | ✅ |
| 真实 RAG 返回的 Citation 可回溯到 manifest（status=active、source_url 一致、quote 是 chunk 原文前缀） | ✅ |
| 无证据问题如实返回 `insufficient_evidence=true` 且无 Citation | ✅ |
| 随访草稿 `requires_human_confirmation=true`、Citation 均为 active 文档 | ✅ |

---

## 4. Knowledge Manifest 校验

```
$ python scripts/validate_manifest.py
manifest: .../knowledge/manifest/knowledge_manifest.csv
checks: {"rows": 30, "active": 27, "draft": 3, "distinct_document_ids": 30,
         "bom": 1, "errors": 0, "warnings": 0}
VALIDATION PASSED
退出码：0
```

校验维度：ID 唯一性、authority_level 合法性、status 合法性、source_url 格式、
受控词表（diseases / scenarios / qianfan_kb）、**active 行的文件存在性与 sha256 一致性**、
`replaced_by` 指向存在性与环检测、UTF-8 BOM。

---

## 5. 切片构建

```
$ python scripts/build_chunks.py
chunks -> knowledge/chunks/chunks.jsonl  total=1041
size stats: {"min": 9, "max": 1109, "mean": 595.8, "under_min": 95, "over_max": 31}
退出码：0   （自带的 verbatim 校验：0 条问题）
```

* 切片参数：目标 500~900 中文字符，overlap 80~150，硬上限 1200。
* **verbatim 自检**：脚本会逐条验证 `content` 是否为清洗后文档的**连续原文片段**。
  首轮跑出 588 条不通过，定位并修复了两处真实缺陷后降到 **0 条**：

  1. `apply_overlap()` 从上一块**头部**取重叠却把顺序倒转，导致拼出的 `content`
     不是连续片段 → 改为从**尾部**倒序取整 unit；
  2. 长段落被 `split_long_text()` 切开后，`join_units()` 用 `"\n\n"` 拼接，
     在原文中平白插入段落分隔 → 为后续片段加 `glue=True` 标记，用空串粘连。

* `under_min=95` 是短章节（标题+一两句话）的自然结果，属于预期；
  `over_max=31` 是"不得切开完整条款/表格"约束优先于长度目标的结果。

---

## 6. 离线评测（`scripts/evaluate.py --provider mock`）

| 套件 | 用例数 | 通过 | 通过率 | 关键指标 |
|---|---:|---:|---:|---|
| extraction | 32 | 32 | 100.00% | field_accuracy=1.0；value_accuracy=1.0；schema_pass_rate=1.0；**hallucination_rate=0.0** |
| routing | 28 | 28 | 100.00% | domain_recall=1.0；domain_precision=0.9643；exact_match_rate=0.9286 |
| rag | 32 | 31 | 96.88% | **recall_at_k=0.9667**；citation_hit_rate=0.9375 |
| citation | 22 | 22 | 100.00% | **false_citation_count=0**；illegal_citation_block_rate=1.0 |
| no_evidence | 12 | 12 | 100.00% | no_evidence_accuracy=1.0 |
| safety | 24 | 24 | 100.00% | block_decision_accuracy=1.0；flag_accuracy=1.0 |
| injection | 18 | 18 | 100.00% | **injection_detection_rate=1.0；injection_bypass_count=0** |

> **本报告不包含任何"医学准确率"指标。** 评测只覆盖可客观判定的工程指标。
> 医学正确性必须由临床专家评审，工程评测无法替代。

已知失败项（如实列出）：

| 用例 | 现象 | 归因 |
|---|---|---|
| `RAG-028`「健康的生活方式指导包括哪些方面？」 | Recall@K 未命中期望文档集（实际命中 CORE006/HTN001/HTN002/LIFE007） | **知识库覆盖不足**，非检索缺陷：`WHO003` 只抓到 WHO 出版页摘要（2.4K 字符），全文 PDF 因 `iris.who.int` 改版下载失败；`LIFE001` 页面正文仅 1.3K 字符且附件为**无文本层扫描件** |

### 评测过程中发现并修复的真实缺陷

| 现象 | 根因 | 处置 |
|---|---|---|
| `no_evidence` 套件在真实语料上大幅失败 | 中文二元组分词下，「今天/怎么/适合」等高词频二元组会在大语料里产生**弱假命中**，被当成"有证据" | 新增**相关性闸门**：`matched_terms >= 3` 或 `bm25_score >= 12.0`（按真实语料标定，可经 `RAG_MIN_MATCHED_TERMS` / `RAG_MIN_RELEVANCE_SCORE` 配置）→ no_evidence 恢复到 100%，同时 rag 召回保持 96.7% |
| `authority_hit_rate` 显示 0.0 | 本批 RAG 用例未声明 `expected_authority_levels`，分母为 0 | 记为 1.0（不适用）并在报告备注，避免误读 |
| **`PRIM003`（P0 标准 WS/T 484—2015）文本层乱码** | 官方 PDF 的 **ToUnicode CMap 损坏**：PyMuPDF 抽出 `犐犆犛１１．０２０`（应为 `ICS 11.020`），pypdf 抽出 `/G21/G22…` 字形名。该文档贡献 60 个切片，构成"高权威加权 × 低可读性"的最危险组合，会污染 Citation | 弃用该 PDF 作为正文来源，改用官方发布页 HTML（标准号/发布日/实施日等权威元数据，281 字符），并在 manifest `notes` 如实登记；同时清理 `_download_report.json` 的 `secondary_files`（否则 preprocess 会优先用 PDF）。**结果：60 个乱码切片 → 1 个**，`verify_content_match.py` 的 `title_bigram_ratio` 从 **0.1 → 0.95**；总切片 1100 → 1041 |
| **全角输入导致提取失败**（中文输入法常见） | `ＢＰ１５８／９６` 血压完全提取不到；`体温３６.８` 体温提取不到（该正则当时写的是字面量 `3[0-9]`，只有 `\d` 才吃全角数字） | 在提取入口统一 `fold_fullwidth()`（全角→半角），并让 grounding 校验用同一套折叠。**注意**：匹配在折叠文本上进行，但 `source_text` **切片自用户原文**（折叠是严格 1:1，下标一一对应），保证契约要求的"source_text 必须是用户原文连续片段"不被破坏。新增 `tests/test_text_normalization.py`（44 用例） |
| 修全角时**一度把 `source_text` 变成折叠后的半角** | 首版实现直接返回折叠文本的片段，`hallucination_rate` 从 0.0 升到 **0.0278**（eval 的 grounding 校验抓到） | 改为"折叠匹配 + 原文切片"；`hallucination_rate` 回到 **0.0**。这是评测套件真实发挥作用的一次 |
| **显式指定知识域、但该域无文档时静默放大到全库检索** | `documents_for_domains()` 返回**空集合**，而代码写的是 `allowed_ids or None` —— 空集合是 falsy，于是变成"不过滤 = 搜全库"。与之前修掉的 `options.domains` 非法值静默丢弃属同一类 | 显式区分"未指定域"与"指定域但无匹配"：后者直接判无证据并记录 note；`documents_for_domains` 改为只返回 `status=active` 文档。新增 `tests/test_domain_filter.py`（11 用例） |
| **错误响应出现重复响应头** | 异常处理器已设置 `X-Request-ID` / `X-CF-Contract-Version`，中间件 `send_wrapper` 又无条件追加一遍 → 403 响应有 2 组同名头。客户端对重复头处理不一致（取第一个 / 拼成 `"a, b"`），会让追踪 ID 与契约版本不可靠 | `send_wrapper` 改为**存在即不追加**；同时契约版本不匹配的 400 分支补齐 `X-CF-Contract-Version`（该分支绕过 `send_wrapper`）。新增 `tests/test_http_headers.py`（6 用例），逐响应断言两个头各出现**恰好 1 次** |
| **`verify_sources.py` 忽略 `MANIFEST_PATH`，会静默校验错的文件** | 该脚本硬编码默认路径，而应用读 `MANIFEST_PATH`。指向另一份 manifest 时会打印 `VERIFY PASSED`，属于"假装完成"型缺陷 | 改为先读 `MANIFEST_PATH` 环境变量，并新增 `--manifest` 参数；未找到 manifest 时非 0 退出 |
| `app/*/__init__.py` 等文件带 UTF-8 BOM | 早期用 PowerShell 写入时带上 BOM | 批量去除；并新增脚本检查所有 `.py` 均为无 BOM 的合法 UTF-8 |
| 残留与冗余 | `scripts/_probe.py`（开发期探针）、`app/main.py` 未使用导入、`build_chunks.py` 未使用 `urlparse`、`download_attachments.py` 未使用局部导入、`build_chunks.py` 中 `apply_overlap` 的过时注释（写 "leading units"，实际取的是"尾部 units"） | 全部清理/修正 |

| manifest 的 `publish_date` 只有 3 行有值、`effective_date` **全 30 行为空** | `scripts/extract_publish_dates.py` **从未被运行过**（`knowledge/raw/_dates.json` 不存在），而且它只抽 `publish_date` 不抽实施日期；`build_manifest.py` 因此拿不到任何页面日期 | ① 跑通并修好抽取脚本；② 扩展它同时抽取「实施日期」（含中文写法 `实施时间 2026年3月1日`，需放宽 HTML 标签间隔到 300 字符）；③ `build_manifest.py` 改为优先使用抽取值。**结果：`publish_date` 3/30 → 23/30；`effective_date` 0/30 → 2/30**（`HTN001=2026-03-01` WS/T 872—2025、`PRIM003=2016-04-01`），8 个 chunk 的 `effective_date` 随之下发到 Citation |
| 上述乱码问题的**检测手段** | — | `scripts/verify_content_match.py` 计算 `title_bigram_ratio`（标题二元组在正文中的出现比例）：正常文档 **0.94~1.0**、乱码文档 **0.1** —— 这是一条**可复用的乱码自动检测闸门**，已写入 `docs/KNOWLEDGE_BASE.md` |

---

## 7. Docker

```
$ docker build -t careflow-ai-rag:dev .
#14 DONE 1.2s
naming to docker.io/library/careflow-ai-rag:dev
sha256:062f5b1698b0f9cbbcef31bb0a92ad6dd8d2ada1cc6a974c4761e56e65750e19
退出码：0
```

```
$ docker run -d --name careflow-smoke -p 18100:8100 \
    -e AI_PROVIDER=mock -e APP_ENV=production careflow-ai-rag:dev
```

| 检查 | 结果 |
|---|---|
| 容器启动、uvicorn 就绪 | ✅ |
| 以非 root 用户 `careflow` 运行 | ✅ |
| 生产模式输出单行 JSON 日志 | ✅ |
| `HEALTHCHECK` 脚本可执行 | ✅ |

---

## 8. 最终 Smoke Test（契约 §33）

对**运行中的 Docker 容器 + 真实知识库**执行 `scripts/smoke_test.py`：

```
$ python scripts/smoke_test.py --base-url http://127.0.0.1:18100 --expect-knowledge
合计 14 项，通过 14 项，失败 0 项
退出码：0
```

| # | 检查项 | 结果 |
|---|---|---|
| 1 | `GET /health` 契约字段齐全且 HTTP 200（status=ok，manifest=ok，knowledge=ok） | ✅ |
| 2 | `GET /v1/status` 统一信封 + 组件状态 | ✅ |
| 3 | 知识库已加载（chunks_total=1041） | ✅ |
| 4 | `POST /v1/extract` 血压/血糖/症状/用药 均被提取且 `source_text` 可溯源 | ✅ |
| 5 | `POST /v1/rag/answer` 返回回答 + 真实 Citation | ✅ |
| 6 | Citation 结构完整（document_id / source_url / quote） | ✅ |
| 7 | Safety：提示词注入 → 403 `SAFETY_BLOCKED` | ✅ |
| 8 | Safety：索取处方 → 403 `SAFETY_BLOCKED` | ✅ |
| 9 | No Evidence：`insufficient_evidence=true` 且无 Citation | ✅ |
| 10 | No Evidence 严格模式：`RAG_NO_EVIDENCE` 错误码 | ✅ |
| 11 | Citation Test：每条引用都来自本轮真实命中 | ✅ |
| 12 | `POST /v1/followup/draft` 摘要/问题/教育/人工确认 | ✅ |
| 13 | 契约版本不匹配 → `CONTRACT_VERSION_ERROR` | ✅ |
| 14 | Schema 校验失败 → `SCHEMA_VALIDATION_FAILED` | ✅ |

---

## 9. 未验证（BLOCKED）

以下内容**没有真实执行**，不得视为通过：

| 项 | 原因 |
|---|---|
| 百度千帆真实模型调用（`/v2/chat/completions`） | 无凭据。HTTP 层已用 `httpx.MockTransport` 覆盖 24 个用例（认证头、超时、429、5xx、401、非法 JSON、Token 统计、密钥不外泄），但**未对线上服务发起过真实请求** |
| 千帆知识库检索 / AppBuilder 路径 | 无凭据 + 各平台版本路径存在差异。路径已做成可配置项并做宽容解析，**需按当期官方文档核对后真机联调** |
| `scripts/sync_qianfan.py` 真实同步 | 同上 |
| OCR 扫描件 PDF | `CORE002` / `LIFE001` / `LIFE008` 的官方附件是无文本层扫描件，未纳入检索（已在 manifest notes 与 `docs/KNOWLEDGE_BASE.md` 登记） |
| 临床正确性 / 医学准确率 | 需临床专家评审，超出工程评测范围 |

---

## 10. 复现命令

```bash
cd careflow-ai-rag

# 1) 单元与集成测试
python -m pytest tests/ -q
python -m pytest tests/ --cov=app --cov-report=term-missing

# 2) 真实知识库产物检查
python scripts/validate_manifest.py
python scripts/build_chunks.py

# 3) 离线评测（生成 eval/REPORT.md 与 eval/results/*.json）
python scripts/evaluate.py --provider mock

# 4) Docker
docker build -t careflow-ai-rag:dev .
docker run -d --name careflow-ai-rag -p 8100:8100 -e AI_PROVIDER=mock careflow-ai-rag:dev

# 5) 最终 Smoke Test
python scripts/smoke_test.py --base-url http://127.0.0.1:8100 --expect-knowledge
```
