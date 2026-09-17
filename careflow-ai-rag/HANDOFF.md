# HANDOFF —— CareFlow 康脉智护 AI/RAG 子系统交接说明

> 面向 **CareFlow 总集成人 / 业务后端负责人 / 后续接手 Agent / 运维**。
> 契约 **CF-CONTRACT-2.0**｜服务端口 **8100**｜运行时模型平台 **百度千帆**
>
> 最后更新：**2026-09-17（第 4 轮：bug 清扫）**
> 本文件遵循一条硬规则：**未真实验证的内容一律标记 `BLOCKED`，不伪装为完成。**

---

## 0. 一句话交接

一个**可独立部署、已被 HTTP 端到端验证**的 AI Gateway：

```
30 篇官方文档 → 27 篇 active → 1041 个切片
→ BM25 检索 → 真实 Citation → 三级安全裁剪
→ FastAPI 五端点 → 497 tests passed / 覆盖率 90%
→ Docker 可构建可运行 / Smoke Test 14/14
```

**唯一未完成的环节是「接上真实千帆凭据」** —— 代码与 HTTP 层已完整就绪并测试，
但从未对线上千帆发起过真实请求（无凭据）。标记 `BLOCKED`（见 §6）。

---

## 0.5 在新对话里如何继续（给下一个 Agent 的开场提示词）

新开一个对话，把下面这段**原样**发给 Agent：

```
你是 CareFlow 康脉智护 AI/RAG 子系统的接手工程师。
项目根目录：C:\Users\27363\Desktop\大健康\careflow-ai-rag

第一步（先读，不要改任何东西）：
1. 读 HANDOFF.md（交接总览、BLOCKED 清单、下一步建议）
2. 读 CONTRACT_COMPLIANCE.md（契约逐条对照）
3. 读 TEST_REPORT.md（真实执行结果）
4. 读 docs/ 下四份：API.md / RAG_ARCHITECTURE.md / SAFETY.md / KNOWLEDGE_BASE.md

第二步（先验证现状，再动手）：
  cd C:\Users\27363\Desktop\大健康\careflow-ai-rag
  python -m pytest tests/ -q                  # 期望 497 passed
  python scripts/validate_manifest.py         # 期望 VALIDATION PASSED，退出码 0
  python scripts/verify_sources.py            # 期望 VERIFY PASSED
  python scripts/build_chunks.py              # 期望 0 verbatim problems
  python scripts/evaluate.py --provider mock  # 期望 6 套 100%，RAG 96.88%
  docker build -t careflow-ai-rag:dev .
  docker run -d --name careflow-smoke -p 18100:8100 -e AI_PROVIDER=mock careflow-ai-rag:dev
  python scripts/smoke_test.py --base-url http://127.0.0.1:18100 --expect-knowledge   # 期望 14/14

第三步：按 HANDOFF.md §8 的优先级继续。不要在未验证现状前改代码。

硬约束（不可违反）：
- 运行时 LLM/RAG 平台必须是百度千帆，所有千帆调用只能经过 app/clients/qianfan.py
- 不得用 DeepSeek/OpenAI 客户端替换（AI_PROVIDER=mock 只用于离线开发与测试）
- 严禁自动诊断 / 处方 / 剂量 / 停药换药建议；AI 不决定 Attention Level、不写业务库
- 不得绕过付费墙或版权限制抓取未授权全文
- Citation 必须由程序从真实检索命中构造，source_url 一律以 manifest 为准
- 未真实验证的内容必须标记 BLOCKED，不得伪装为完成
- 改完必须重跑：pytest / validate_manifest / verify_sources / build_chunks / smoke_test
```

> 如果只想继续「千帆真机联调」，把 `QIANFAN_API_KEY` / `QIANFAN_APP_ID` / 模型名 /
> 8 个 `QIANFAN_KB_*_ID` 提供出来，直接执行 §2.3 与 §8 的 P0 项。

---

## 1. 交付清单与状态

| # | 交付物 | 位置 | 状态 |
|---|---|---|---|
| 1 | FastAPI 服务（5 端点） | `app/` | ✅ 已实现并 HTTP 验证 |
| 2 | 契约 CF-CONTRACT-2.0 | `app/core/contract.py` | ✅ |
| 3 | 千帆客户端（唯一入口） | `app/clients/qianfan.py` | ⚠️ 代码就绪，**真机未验证** |
| 4 | 结构化提取 | `app/services/extraction_service.py` | ✅ 规则路径已验证；LLM 路径用 MockTransport 验证 |
| 5 | Domain Router | `app/services/routing_service.py` | ✅ |
| 6 | RAG + 检索 | `app/services/rag_service.py`、`retrieval_service.py` | ✅ 本地检索端到端验证 |
| 7 | Citation 防幻觉 | `app/services/citation_service.py` | ✅ 虚假引用 **0** |
| 8 | Safety | `app/services/safety_service.py` | ✅ 含 76 条回归用例 |
| 9 | FollowUp 草稿 | `app/services/followup_service.py` | ✅ |
| 10 | Knowledge Manifest | `knowledge/manifest/knowledge_manifest.csv` | ✅ 30 行，校验 0 错误 |
| 11 | 切片 | `knowledge/chunks/chunks.jsonl` | ✅ **1041** 个，verbatim 自检 0 问题 |
| 12 | 知识库管线脚本 | `scripts/` | ✅ |
| 13 | 测试 | `tests/`（21 个文件） | ✅ **497 passed / 0 failed / 0 skipped**，覆盖率 **90%** |
| 14 | 离线评测 | `eval/` | ✅ 7 套件，见 `eval/REPORT.md` |
| 15 | Docker | `Dockerfile` | ✅ 构建 + 容器运行 + Smoke 14/14 |
| 16 | 文档 | `README.md` `HANDOFF.md` `TEST_REPORT.md` `CONTRACT_COMPLIANCE.md` `docs/*` | ✅ |
| 17 | **千帆知识库建立** | `scripts/sync_qianfan.py` | ⛔ **BLOCKED** |
| 18 | **千帆 Live 验证** | — | ⛔ **BLOCKED** |

> 注：仓库**尚未初始化 git**。建议接手后立刻 `git init` 并做首次提交，
> 以便后续改动可回滚（当前根目录已无临时脚本残留）。

---

## 2. 启动方法

### 2.1 本地（离线，不需要任何凭据）

```bash
cd careflow-ai-rag
python -m venv .venv && .venv\Scripts\activate      # Windows
pip install -r requirements-dev.txt

copy .env.example .env
# 编辑 .env：AI_PROVIDER=mock

python -m uvicorn app.main:app --host 0.0.0.0 --port 8100
curl http://127.0.0.1:8100/health
```

`mock` 模式行为（**已在真实知识库上验证**）：

* Extraction → 确定性规则引擎，可复现、可断言；
* RAG → **官方检索片段的原文摘录**（不做生成式改写），Citation 全部来自真实命中；
* Router → 确定性关键词路由；
* **零外部网络调用**。

> ⚠️ **Mock 成功 ≠ 千帆验证成功。** 可用 `meta.provider` 区分（`mock` / `qianfan`）。

### 2.2 Docker

```bash
docker build -t careflow-ai-rag:dev .
docker run -d --name careflow-ai-rag -p 8100:8100 --env-file .env careflow-ai-rag:dev
```

镜像只装运行时依赖（不含 playwright / pymupdf 等管线依赖），以非 root 用户
`careflow` 运行，自带 `HEALTHCHECK`。

### 2.3 接入真实千帆（`BLOCKED` 待完成）

```bash
# 1) 填 .env：QIANFAN_API_KEY / QIANFAN_APP_ID / QIANFAN_MODEL / QIANFAN_BASE_URL
#             QIANFAN_KB_CORE_ID ... QIANFAN_KB_WHO_ID（8 个域）

# 2) 探测凭据
python -m uvicorn app.main:app --port 8100
curl "http://127.0.0.1:8100/v1/status?probe=1"

# 3) 同步知识库（先 dry-run）
python scripts/sync_qianfan.py --dry-run
python scripts/sync_qianfan.py

# 4) 用真实 provider 跑评测 + 最终 Smoke Test
python scripts/evaluate.py --provider qianfan
python scripts/smoke_test.py --base-url http://127.0.0.1:8100 --expect-knowledge
```

> 🔴 **联调前必须核对**：千帆知识库检索 / AppBuilder 的 **API 路径在不同平台版本间存在差异**。
> 本仓库把它们做成可配置项并对响应结构做宽容解析，但**没有用真实凭据验证过**。
> 请以当期千帆开放平台文档为准核对：
> * `QianfanClient.DEFAULT_PATHS`（`chat` / `embedding` / `kb_retrieve` / `appbuilder_run`）
> * `scripts/sync_qianfan.py::CREATE_DOC_PATH`

---

## 3. 后端集成方法

### 3.1 五个端点

| 方法 | 路径 | 说明 | 响应结构 |
|---|---|---|---|
| GET | `/health` | 健康探针 | **扁平（无信封）** |
| GET | `/v1/status` | 运行状态 | 信封 |
| POST | `/v1/extract` | 自然语言 → 结构化 Observation | 信封 |
| POST | `/v1/rag/answer` | 官方知识 RAG + 真实 Citation | 信封 |
| POST | `/v1/followup/draft` | 医生随访草稿 | 信封 |

### 3.2 五个必读注意点

1. **`/health` 是扁平结构**；其余 4 个端点是**统一信封**。
2. **`RAG_NO_EVIDENCE` 有两种行为**：默认 `allow_no_evidence=true` → **HTTP 200** +
   `data.insufficient_evidence=true`；设为 `false` → `success=false` + `error.code`。
   **必须检查 `success` 字段，不能只看 HTTP 状态码。**
3. **失败信封的 `operation` 带路径前缀**（如 `v1.rag.answer`），成功路径不带
   （`rag.answer`）。**不要用它做业务分支判断。**
4. **显式传入的 `options.domains`（知识域）语义是"只在这个范围内检索"**：
   * 传了不存在的域 → **422 快速失败**；
   * 传了存在但当前**没有 active 文档**的域 → 返回 **无证据**，**不会**退化成全库检索；
   * 不传 → 全库检索。
5. **每个响应都带恰好 1 个** `X-Request-ID` 与 `X-CF-Contract-Version`。

### 3.3 推荐调用姿势

```jsonc
// POST /v1/extract
{
  "text": "今天早上血压158/96，空腹血糖7.2，有点头晕，在吃硝苯地平30mg每天一次",
  "patient_context": { "patient_ref": "p-10086", "age_years": 66, "sex": "male" },
  "options": { "max_observations": 40 }
}
```

```jsonc
// POST /v1/rag/answer
{
  "query": "高血压患者每天吃盐多少合适？",
  "patient_context": { "patient_ref": "p-10086", "known_conditions": ["HYPERTENSION"] },
  "options": { "top_k": 5, "domains": ["KB_HTN", "KB_LIFESTYLE"], "allow_no_evidence": true }
}
```

```jsonc
// POST /v1/followup/draft —— 结构化数据由后端回传，省一次模型调用
{
  "checkin_text": "血压158/96，最近有点头晕，吃药不太规律",
  "recent_observations": [ /* 上一步 /v1/extract 的结果，患者已确认 */ ],
  "options": { "max_questions": 6 }
}
```

### 3.4 PII 边界（重要）

`patient_context` 只接受最小必要字段，且是 `extra="forbid"`：
传 `name` / `phone` / 身份证 → **直接 422**。
真实身份绑定请由业务后端通过不可逆的 `patient_ref` 完成。
**本服务不检测自由文本里的 PII**，去标识化责任在业务后端。

### 3.5 输入归一化（已实现，集成方需知道）

* 全角字符（`ＢＰ１５８／９６`、`体温３６.８`、`９５％`）会被**折叠成半角**后参与匹配，
  因此中文输入法下的写法同样能正确提取；
* 但 **`source_text` 一律切片自用户原文**（保持全角原样），契约要求它是"用户原文的连续片段"；
* 数值字段（`value`）是归一化后的数字，例如 `{systolic: 158, diastolic: 96}`。

### 3.6 错误码与重试建议

| 错误码 | HTTP | 建议动作 |
|---|---|---|
| `INVALID_INPUT` | 400 | 修正入参，不要重试 |
| `SCHEMA_VALIDATION_FAILED` | 422 | 修正入参，不要重试 |
| `CONTRACT_VERSION_ERROR` | 400 | 检查 `X-CF-Contract-Version` 头 |
| `SAFETY_BLOCKED` | 403 | **不要重试**；把拒绝话术透传给用户 |
| `QIANFAN_RATE_LIMIT` | 429 | 退避重试（1~2 次，指数退避） |
| `QIANFAN_TIMEOUT` | 504 | 可重试 1 次 |
| `QIANFAN_UNAVAILABLE` | 503 | 可重试；持续失败则降级为"稍后再试" |
| `RAG_NO_EVIDENCE` | 200 | 按"无证据"话术展示，不要重试 |
| `KNOWLEDGE_MANIFEST_INVALID` | 500 | 运维介入（知识库产物损坏） |
| `INTERNAL_ERROR` | 500 | 带上 `request_id` 报运维 |

**幂等性**：本服务只读（不写业务库），GET/POST 都可安全重试；
重试时请**保持同一个 `X-Request-ID`**，便于日志串联。

---

## 4. 运维要点

### 4.1 日志

* 生产模式（`APP_ENV != development`）输出**单行 JSON**，可直接采集。
* 固定字段：`request_id` `operation` `provider` `model` `latency_ms`
  `success` `error_code` `domains` `document_ids` `token_usage`。
* **密钥不落日志**（有专门测试）；手机号/身份证正则脱敏；患者原文不完整落日志。

### 4.2 健康检查

* 探针请用 `GET /health`（扁平结构，无需解信封）。
* `status`：`ok` / `degraded` / `error`；manifest 缺失时返回 **503**。
* `qianfan`：`ok`（凭据已配置）/ `not_configured` / `mock` / `error`。
  **`ok` 只代表凭据存在，不代表线上连通**；真连通用
  `GET /v1/status?probe=1`（会消耗配额，不要放进高频探针）。
* ⚠️ `/health` 失败时 `detail` 会带**服务器绝对路径**，公网暴露时请评估。

### 4.3 成本控制

* `/v1/extract` = **1 次**模型调用。
* `/v1/rag/answer` = **1 次**（`RAG_ENABLE_LLM_ROUTER=true` 且查询无确定性命中时最多 +1 次 Router）。
* `/v1/followup/draft` = **1 次**（**复用后端传入的结构化数据，不再调 Extraction LLM**）。
* 无检索命中时**不调用生成模型**（直接返回无证据话术）。
* 普通 CheckIn 全链路 ≤ 3 次模型调用。

### 4.4 关键可调参数

| 环境变量 | 默认 | 说明 |
|---|---|---|
| `RAG_TOP_K` | 5 | 召回条数 |
| `RAG_MAX_CONTEXT_CHARS` | 12000 | 送入 LLM 的上下文上限 |
| `RAG_MIN_MATCHED_TERMS` | 3 | **相关性闸门**：命中词数下限 |
| `RAG_MIN_RELEVANCE_SCORE` | 12.0 | **相关性闸门**：BM25 分下限 |
| `RAG_SCORE_THRESHOLD` | 0.0 | 额外的最低分过滤（默认关闭） |
| `RAG_ENABLE_LLM_ROUTER` | true | 是否允许 LLM 补充域路由 |
| `MAX_RETRIES` | 1 | 千帆重试次数，**代码内硬上限 2** |
| `REQUEST_TIMEOUT_SECONDS` | 20 | 千帆单次超时 |
| `MANIFEST_PATH` / `CHUNKS_PATH` | `knowledge/...` | 知识库产物路径（测试用覆盖点） |

> ⚠️ `RAG_MIN_MATCHED_TERMS` / `RAG_MIN_RELEVANCE_SCORE` 是**按当前语料经验标定**的
> （1041 个切片、平均 596.8 字符）。**换语料或大幅增删文档后必须重新标定**，
> 否则会出现"该答不答"或"不该答乱答"。标定方法见 `TEST_REPORT.md` §6。

### 4.5 知识库更新流程

```bash
python scripts/download_documents.py      # 幂等；Playwright（nhc.gov.cn 有 WZWS 风控）
python scripts/extract_publish_dates.py   # 抽 发布/实施 日期 → knowledge/raw/_dates.json
python scripts/preprocess_documents.py    # 注意：它读 _download_report.json，不是 manifest
python scripts/build_chunks.py            # 自带 verbatim 自检，必须 0 问题
python scripts/validate_manifest.py       # 必须退出码 0
python scripts/verify_sources.py          # 文件完整性校验
python scripts/verify_content_match.py    # 乱码/错源检测（title_bigram_ratio）
python scripts/sync_qianfan.py            # 推送到千帆（BLOCKED 待验证）
# 重启服务（当前没有热重载端点）
```

---

## 5. 已修复的真实缺陷清单（避免重复排查）

四轮下来共修掉 **20+ 个真 bug**。以下按类别归档，**接手后不必重新排查**：

### 5.1 知识库管线（5 个，都会让管线卡死或产出错误数据）

| 缺陷 | 症状 | 根因 |
|---|---|---|
| `preprocess.drop_noise` | 27 篇里 26 篇清洗失败 | 同一次遍历里 `decompose()` 会把后续节点 `attrs` 置为 `None` |
| `build_chunks.parse_blocks` | 处理 PRIM003 时**死循环** | 以 `#` 开头但不是合法标题的行让内层 while 一步不走，`i == j` |
| `build_chunks.pack` | 处理大文档时**死循环 + O(n²)** | 回退标题的 while 把刚弹出的标题又放回 `cur`，循环条件恒成立 |
| `build_chunks.apply_overlap` | **588/1099 条切片不是原文连续片段** | 从上一块**头部**取重叠却把顺序倒转 |
| `join_units` | 切片里平白多出段落分隔 | 长段落切开后用 `"\n\n"` 拼接，应为空串粘连（`glue=True`） |

修复后 verbatim 自检从 **588 条不合格 → 0 条**。

### 5.2 安全（两轮对抗性审查发现）

| 缺陷 | 症状 |
|---|---|
| `DOSAGE_RE` 只认 ASCII 数字 | `每次吃两片。` / `加一片。` / `每天半片。` **完全不被输出侧裁剪**（同义的 `每次吃2片。` 却会被裁）——中文语境下最口语化的剂量建议最不设防 |
| `MED_CHANGE_RE` 缺裸「加」 | `加一片` 两条规则都不命中 |
| `SELF_TREAT_RE` 词表与间距 | `建议自行购药服用。` / `你可以自行去药店买药服用。` 未裁剪 |
| 输入侧可被同义改写绕过 | `这个药每天最大能吃多少毫克` / `把降压药停了行不行` 零 flag |
| 红旗误报 | `如何识别脑卒中早期症状` 这类**科普提问**会被前置"立即拨打 120" |
| **修复副作用**：膳食数值被误裁 | `低盐饮食每日食盐不超过 5 克。` 被当成剂量裁掉 |

最终形态：剂量规则拆成**三级判定** ——
① 剂型（片/粒/丸/袋/支/吸/喷/滴）→ 直接判定；
② 药物质量单位（mg/毫克/IU/单位）+ 服用动词 → 判定；
③ 通用质量/体积单位（克/g/毫升/ml）→ **必须同时**有服用动词与**药物上下文**。
红旗改为两段式：**flag 保留** + 科普提问时**不前置 120 提示**。

> 完整规则、阈值与 12 项「修复后依然存在的局限」见 `docs/SAFETY.md` §9。

### 5.3 检索与 API（第三轮 bug 清扫发现）

| 缺陷 | 症状 | 影响 |
|---|---|---|
| **全角输入提取失败** | `ＢＰ１５８／９６` 血压提取不到；`体温３６.８` 体温提取不到 | 中文输入法高频路径直接失效。修法：入口 `fold_fullwidth()`，但 **`source_text` 仍切片自原文** |
| **`allowed_ids or None`** | 显式指定域但该域无文档 → 空集合是 falsy → **静默放大到全库检索** | 调用方限定的范围被悄悄扩大 |
| **重复响应头** | 异常处理器 + 中间件各加一遍 → 403 响应有 2 组同名头 | 追踪 ID / 契约版本对客户端不可靠 |
| 契约版本 400 缺响应头 | 该分支绕过 `send_wrapper` | 同上 |
| `verify_sources.py` 忽略 `MANIFEST_PATH` | 指向别的 manifest 仍打印 `VERIFY PASSED` | **"假装完成"型缺陷** |
| `documents_for_domains()` 返回 draft 文档 | 检索过滤器混入非 active | 语义错误 |
| BOM / 残留脚本 / 未使用导入 / 过时注释 | — | 整洁性 |

### 5.4 数据质量

| 缺陷 | 症状 | 处置 |
|---|---|---|
| **PRIM003（P0 标准 WS/T 484—2015）文本乱码** | 官方 PDF 的 **ToUnicode CMap 损坏**，抽出 `犐犆犛１１．０２０`（应为 `ICS 11.020`），贡献 60 个切片且 P0 加权最高 | 弃用该 PDF，改用官方发布页 HTML（元数据），**60 乱码切片 → 1**；`title_bigram_ratio` 0.1 → 0.95 |
| **`extract_publish_dates.py` 从未被运行过** | `_dates.json` 不存在 → `publish_date` 只有 3 行有值、`effective_date` 全空 | 跑通 + 扩展抽「实施日期」→ `publish_date` **23/30**、`effective_date` **2/30**，日期一路下发到 Citation |
| LIFE002/003/004 曾是同一份入口页 | 6 篇文档正文重复 | 已改为真实的食养指南 PDF |

### 5.5 一个重要的过程教训

修全角时我**一度把 `json_utils.py` 改坏**（`fold_fullwidth` 定义没落盘，
`normalize_whitespace` 却引用它）→ `ImportError`，**整个测试套件跑不起来**。
`extraction_service ↔ json_utils` 是耦合点，**改这两个文件必须同时保持一致并立刻跑一次 pytest**。

---

## 6. BLOCKED 清单（未真实验证，不得视为完成）

| # | 项 | 阻塞原因 | 解除条件 |
|---|---|---|---|
| B1 | **千帆真实模型调用**（`/v2/chat/completions`） | 无凭据。HTTP 层已用 `httpx.MockTransport` 覆盖 24 个用例 | 提供 `QIANFAN_API_KEY` + `QIANFAN_APP_ID`，跑 `curl /v1/status?probe=1` |
| B2 | **千帆知识库检索 / AppBuilder 路径** | 无凭据 + 各平台版本路径有差异 | 按当期官方文档核对 `QianfanClient.DEFAULT_PATHS` 后真机联调 |
| B3 | `scripts/sync_qianfan.py` 真实同步 | 同上 | 同上 |
| B4 | **真实 RAG（千帆 KB 侧）** | B2 未解除。**本地切片 RAG 已端到端验证**（recall@K 96.7%、虚假引用 0） | 同上 |
| B5 | 真实 LLM 路径的评测数字 | 当前 497 测试与 eval 全部基于 `AI_PROVIDER=mock` | 配好凭据后跑 `evaluate.py --provider qianfan` |

---

## 7. 已知限制（诚实清单）

### 7.1 代码/行为层面

1. **安全判定是确定性正则，不是语义模型**。可被同义改写绕过，规则集合有限。
   `docs/SAFETY.md` §9 列了 **12 项修复后依然存在的局限**（含"剂型直接判定存在理论误伤""必须有药物上下文 ⇒ 未列入词表的药物表述会漏判"等）。
2. **不做急症分诊**。高危红旗只输出 `EMERGENCY_RED_FLAG` 信号，
   真正的急症识别必须由业务后端 Rule Engine 结合结构化数据决策，
   UI 上**不得**把该 flag 渲染成"你处于紧急状态"。
3. **不检测自由文本 PII**，去标识化责任在业务后端。
4. **检索是 BM25 + 可选千帆 KB**，未接本地向量库。语义召回弱于向量检索；
   `recall@K = 96.7%` 是本语料实测值。
5. **知识库无热重载**，更新产物后需重启服务。

### 7.2 数据覆盖缺口（最重要的一组）

| 文档 | 缺口 | 现状 |
|---|---|---|
| `PRIM003`（P0 标准 WS/T 484—2015 老年人健康管理技术规范） | **实质正文缺失**：PDF ToUnicode 损坏、发布页仅 281 字符元数据 | 39 页 PDF 仍在 `knowledge/raw/07_primarycare/PRIM003.pdf`（3.9 MB）待替换干净源 |
| `CORE002` / `LIFE001` / `LIFE008` | 官方附件是**无文本层扫描件**（实测 0 / 417 / 117 字符） | 页面正文极薄（476 / 1329 / 597 字符），需 OCR |
| `WHO001` / `WHO002` / `WHO003` | `iris.who.int` 改版，原 `bitstream/handle/...` 链接返回 755 字节 HTML | 只有出版页摘要（1.4K~2.4K 字符），P4 级 |
| `DM002` / `DM003` / `MULTI001` | **付费墙**（契约禁止绕过） | `status=draft` + `local_file=PENDING` |
| **`effective_date` 28/30 为空** | 无法仅凭 manifest 自动判定"现行有效版本" | 契约「版本冲突优先现行有效规范」目前只能靠 `status` + `authority_level` **缓解**，**未完全落地** |
| `P2`（国家级医学中心）等级为 **0 篇** | 权威等级分布不完整 | 需补充来源 |

**影响**：相关主题的提问会走 `insufficient_evidence=true`。
这是**正确的保守行为**（无答案 > 编造答案），但集成方需知道覆盖边界。

`eval` 的 `RAG-028`（"健康的生活方式指导包括哪些方面"）未通过，**根因就是这个覆盖缺口**，不是检索缺陷。

---

## 8. 下一步建议（按优先级）

| 优先级 | 事项 | 具体做法 |
|---|---|---|
| **P0** | **接千帆凭据跑通 B1~B5** | 核对 `DEFAULT_PATHS` 与 `CREATE_DOC_PATH` → `/v1/status?probe=1` → `sync_qianfan.py` → `evaluate.py --provider qianfan` → 最终 Smoke Test。**在此之前所有"完成"结论都只对 mock 有效。** |
| **P1** | **给 `PRIM003` 找干净源** | 试：国家卫生健康委标准库、卫生标准网、国家标准全文公开系统；目标是带正确 ToUnicode 的 PDF，或可复制的 HTML/Word。这是当前**最高价值的单个数据缺口**（P0 标准 + 老年健康核心场景）。 |
| **P1** | **补 `effective_date`** | 从已下载的 PDF 首页批量抽（标准类文档首页通常有"实施日期"），或对 `HTN002`（nccd 下载页）与 WHO 三篇单独处理。这是让契约「现行有效版本」真正可落地的前提。 |
| **P2** | 三份扫描件 OCR | `CORE002` / `LIFE001` / `LIFE008`：装 OCR（PaddleOCR / tesseract-chi）→ 渲染 PDF 页面 → OCR → **人工校对** → 替换 `local_file` → 重建切片。OCR 结果未经校对不得入库。 |
| **P2** | 重新定位 WHO 全文 PDF | 用 WHO 出版页里的 `iris.who.int/server/api/core/bitstreams/<uuid>/content`（旧 `bitstream/handle/` 已失效）。注意 WHO 文档体量较大。 |
| **P2** | 按真实语料重新标定相关性闸门 | 换语料必须做，方法见 `TEST_REPORT.md` §6 |
| **P2** | 补 P2 级来源 | 国家级医学中心（国家心血管病中心、国家基层糖尿病防治管理办公室等）的正式指南 |
| **P3** | 补 3/5/8 三档 Top-K 扫描 | 契约提到，当前只用配置值 |
| **P3** | 引入向量检索 | 或全面依赖千帆 KB |
| **P3** | 组织临床专家评审安全规则与 Prompt | 医学正确性必须人工评审 |
| **P3** | `git init` + 首次提交 | 当前无版本控制 |
| **P3** | `/health` 增加"是否暴露绝对路径"开关 | 公网部署加固 |

---

## 9. 快速自检清单（接手人第一小时）

```bash
cd careflow-ai-rag

# 1) 环境与测试
python -m pytest tests/ -q                 # 期望 497 passed
python scripts/validate_manifest.py        # 期望 VALIDATION PASSED，退出码 0
python scripts/verify_sources.py           # 期望 VERIFY PASSED
python scripts/build_chunks.py             # 期望 0 verbatim problems

# 2) 评测
python scripts/evaluate.py --provider mock # 期望 6 套 100%、RAG 96.88%、虚假引用 0

# 3) 服务与 Smoke
python -m uvicorn app.main:app --port 8100 &
python scripts/smoke_test.py --expect-knowledge   # 期望 14/14

# 4) 镜像
docker build -t careflow-ai-rag:dev .
```

以上四步全部通过即可认为交付物完整；**第 5 步（真实千帆）需要凭据**。

---

## 10. 文件地图

```
careflow-ai-rag/
├── README.md                     总览与快速开始
├── HANDOFF.md                    ← 本文件
├── TEST_REPORT.md                真实执行结果（497 测试 / 评测 / Docker / Smoke）
├── CONTRACT_COMPLIANCE.md        契约逐条对照（含偏差与豁免）
├── Dockerfile · .env.example · requirements*.txt · pytest.ini
├── app/
│   ├── main.py                   入口、纯 ASGI 中间件、异常处理
│   ├── api/                      health / status / extraction / rag / followup / deps
│   ├── core/                     config / errors / logging_config / contract / json_utils
│   ├── clients/                  qianfan（唯一千帆入口）/ mock / base
│   ├── services/                 manifest / routing / retrieval / rag / extraction
│   │                             / followup / citation / safety
│   ├── schemas/                  Pydantic v2（CF-CONTRACT-2.0）
│   └── prompts/                  5 份可评审 Markdown Prompt（带版本号）
├── knowledge/
│   ├── manifest/knowledge_manifest.csv     30 行
│   ├── raw/                                官方原文 + _download_report.json + _dates.json
│   ├── processed/                          27 篇清洗 Markdown
│   └── chunks/chunks.jsonl                 1041 个切片 + index_meta.json
├── scripts/                      12 个脚本（见 §4.5）
├── eval/                         datasets/(7 套件) + REPORT.md + results/
├── tests/                        21 个测试文件 / 497 用例
└── docs/                         API.md / RAG_ARCHITECTURE.md / SAFETY.md / KNOWLEDGE_BASE.md
```
