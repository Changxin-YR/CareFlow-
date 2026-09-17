# CareFlow 康脉智护 —— AI Gateway API 契约说明

> **契约版本：`CF-CONTRACT-2.0`**
> 适用范围：`careflow-ai-rag` 服务（FastAPI，默认 `0.0.0.0:8100`）
> 本文档中的所有请求/响应示例均来自对源码的实际调用验证，非手写推测。

---

## 1. 服务定位与服务边界

CareFlow AI Gateway 是**基层慢病多病共管与智能随访平台**的 AI/RAG 子系统。

### 1.1 本服务负责

- 自然语言**理解**与结构化**提取**
- 官方知识库**检索**（RAG）
- 基于证据的**解释**与**总结**
- 随访**草稿生成**
- 安全**信号**输出（红旗提示、需人工确认标记）

### 1.2 本服务明确不负责

> 以下职责**全部属于 CareFlow 业务后端**，本服务既不实现也不代理：

| 职责 | 归属 |
|---|---|
| 权限与鉴权 | 业务后端 |
| 数据库读写、正式保存 | 业务后端 |
| Rule Engine 业务规则 | 业务后端 |
| **Attention Level（关注等级）判定** | 业务后端 |
| 人工确认流程与审计留痕 | 业务后端 |
| 患者身份绑定（姓名/身份证/手机号） | 业务后端（本服务只接受 `patient_ref`） |

**本服务不是 AI 医生**：不诊断、不开药、不调药、不给剂量、不建议停药换药。
详见 [`SAFETY.md`](./SAFETY.md)。

---

## 2. 端点总览

| 方法 | 路径 | operation（成功信封） | 说明 |
|---|---|---|---|
| `GET` | `/health` | —（扁平结构，无信封） | 健康检查（运维探针） |
| `GET` | `/v1/status` | `status` | 运行状态与依赖明细 |
| `POST` | `/v1/extract` | `extract` | 自然语言 → 结构化 Observation |
| `POST` | `/v1/rag/answer` | `rag.answer` | 基于官方知识库的 RAG 问答（带真实 Citation） |
| `POST` | `/v1/followup/draft` | `followup.draft` | 医生随访草稿（永远需人工确认） |

`GET /v1/status` 的 `data.endpoints` 字段会返回运行时端点清单，业务后端可据此做能力探测，
**不要在客户端硬编码端点列表**。

自动生成的交互式文档由 FastAPI 提供：`/docs`（Swagger UI）、`/redoc`、`/openapi.json`。

---

## 3. 通用约定

### 3.1 请求头

| 请求头 | 必填 | 说明 |
|---|---|---|
| `Content-Type: application/json` | POST 必填 | 缺失或非 JSON 会得到校验失败 |
| `X-Request-ID` | 可选 | 调用方链路 ID。**不传则服务端生成**（`uuid4().hex[:16]`）。回显在响应头与响应体 `request_id` |
| `X-CF-Contract-Version` | 可选 | 声明期望契约版本。缺省视为兼容。传了不受支持的值 → `CONTRACT_VERSION_ERROR`（HTTP 400） |
| `X-CF-Keepalive` | 可选 | 轻量存活探测标记，`/health` 兼容处理 |

**契约版本校验的作用范围**：中间件对**以 `/v1` 开头的路径**校验 `X-CF-Contract-Version`。
`/health` **不参与校验**——运维探针不应被契约版本阻塞。

### 3.2 响应头

所有响应都会带上：

| 响应头 | 说明 |
|---|---|
| `X-Request-ID` | 本次请求 ID（与响应体 `request_id` 一致） |
| `X-CF-Contract-Version` | 服务当前契约版本 |

> ✅ **每个响应恰好各带 1 个这两个头**（已实测，含全部异常路径）：
> 服务端保证**不重复附加**同名头，因此调用方可以安全地直接读取单值。
>
> | 场景 | HTTP | `X-Request-ID` | `X-CF-Contract-Version` |
> |---|---:|---:|---:|
> | 成功（`/v1/rag/answer`） | 200 | 1 | 1 |
> | `/health`（不校验契约版本） | 200 | 1 | 1 |
> | 契约版本不匹配 | **400** | 1 | 1 |
> | Schema 校验失败 | **422** | 1 | 1 |
>
> 也就是说：**契约版本 400 分支同样带回这两个头**，
> 调用方在错误路径上依然能拿到 `request_id` 与契约版本。

### 3.3 统一响应信封

`/v1/*` 的成功响应：

```json
{
  "contract_version": "CF-CONTRACT-2.0",
  "request_id": "97a0e90712584ea2",
  "operation": "extract",
  "success": true,
  "data": { },
  "warnings": [],
  "meta": { }
}
```

失败响应：

```json
{
  "contract_version": "CF-CONTRACT-2.0",
  "request_id": "eb8362bbd0cd43ae",
  "operation": "v1.rag.answer",
  "success": false,
  "error": {
    "code": "SAFETY_BLOCKED",
    "message": "安全策略拦截：检测到指令覆盖尝试，本系统不接受此类请求。",
    "details": { "flags": ["PROMPT_INJECTION:指令覆盖尝试"] }
  },
  "warnings": [],
  "meta": {}
}
```

> ⚠️ **`operation` 字段在成功与失败路径下取值规则不同**（已实测确认）：
> - **成功**：由端点显式指定，如 `extract`、`rag.answer`、`followup.draft`、`status`；
> - **失败**：由异常处理器按 URL 路径推导（`request.url.path.strip("/").replace("/", ".")`），
>   因此 `/v1/rag/answer` 会得到 **`v1.rag.answer`**（带 `v1.` 前缀）。
>   无法推导时（如契约版本校验失败）取固定值 `unknown`。
>
> 客户端**不要用 `operation` 做主分支判断**；应依据 HTTP 状态码与 `error.code`。

### 3.4 `meta` 字段

成功响应（以及失败时若服务层已构造数据）的 `meta` 携带可观测性信息：

| 字段 | 说明 |
|---|---|
| `contract_version` / `service_version` | 契约版本 / 服务版本（`0.1.0`） |
| `provider` / `model` | 实际使用的 LLM 提供方与模型名 |
| `latency_ms` | 模型/规则引擎耗时 |
| `token_usage` | `{prompt_tokens, completion_tokens, total_tokens}` |
| `prompt_version` | Prompt 版本号（如 `RAG-2.0`、`EXTRACT-2.0`、`FOLLOWUP-2.0`） |
| `domains` | 本轮路由命中的知识域 |
| `document_ids` | 本轮 Citation 涉及的文档 ID（排序去重） |
| `degraded` | **`true` 表示本轮发生了降级**（如 LLM 失败回退原文摘录、千帆 KB 不可用） |
| `notes` | 人可读的降级/提示原因列表 |
| `routing` | 仅 RAG/随访：路由明细（`domains`、`matched_keywords`、`method`、`reason`、`llm_used`、`llm_error`） |

`/v1/extract` 额外在 `meta` 中追加：

- `observation_count`：提取到的观察条目数
- `dropped_observations`：被丢弃的观察（最多 20 条，供审计）

> **运维要点**：业务后端应把 `meta.degraded == true` 纳入监控。降级不会让请求失败，
> 但意味着回答质量下降（例如 LLM 不可用时返回的是**官方原文摘录**而非生成式回答）。

---

## 4. `GET /health` —— 健康检查

**扁平结构，不套用统一信封**（契约明文的五个键：`contract_version`、`status`、`qianfan`、`manifest`、`knowledge`）。

**不校验契约版本**。

### 请求

```bash
curl -s http://127.0.0.1:8100/health
```

### 响应（知识库就绪）

```json
{
  "contract_version": "CF-CONTRACT-2.0",
  "status": "ok",
  "qianfan": "ok",
  "manifest": "ok",
  "knowledge": "ok",
  "service": "careflow-ai-rag",
  "version": "0.1.0",
  "provider": "qianfan",
  "time": "2026-09-17T05:31:02+00:00",
  "detail": {
    "qianfan_detail": "",
    "manifest_error": "",
    "chunks_error": "",
    "documents_total": 30,
    "documents_active": 30,
    "chunks_total": 842,
    "uptime_seconds": 30.906
  }
}
```

### 响应（知识库缺失 —— 实测，HTTP 503）

```json
{
  "contract_version": "CF-CONTRACT-2.0",
  "status": "error",
  "qianfan": "ok",
  "manifest": "missing",
  "knowledge": "missing",
  "service": "careflow-ai-rag",
  "version": "0.1.0",
  "provider": "mock",
  "time": "2026-09-17T05:31:02+00:00",
  "detail": {
    "qianfan_detail": "mock provider（不访问外部网络，不代表千帆可用）",
    "manifest_error": "manifest 不存在：...\\knowledge\\manifest\\knowledge_manifest.csv",
    "chunks_error": "chunks 不存在：...\\knowledge\\chunks\\chunks.jsonl",
    "documents_total": 0,
    "documents_active": 0,
    "chunks_total": 0,
    "uptime_seconds": 30.906
  }
}
```

### 状态判定逻辑（源码 `app/api/health.py`）

```
manifest in {missing, degraded}  → overall = degraded
knowledge in {missing, empty}    → overall = degraded
manifest == missing              → overall = error   （覆盖前两条）
否则                              → overall = ok
```

- `overall == "error"` 时 HTTP 状态码为 **503**，否则 **200**。
- `qianfan` 字段的取值来自 `client.health()`。**`AI_PROVIDER=mock` 时它返回 `ok` 但含义是
  "未访问外部网络"**，`qianfan_detail` 会明确说明，不代表千帆真实可用。
- 健康检查内部**不会因依赖异常而 500**：`client.health()` 抛错会被捕获并降级为 `error` + 详情。

> ⚠️ `detail.manifest_error` / `detail.chunks_error` 包含服务器**绝对路径**。
> 若 `/health` 暴露到公网，建议在网关层裁剪该字段。

---

## 5. `GET /v1/status` —— 运行状态

### 查询参数

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `probe` | bool | `false` | 是否**真实探测千帆**（会消耗配额） |

### 请求

```bash
curl -s "http://127.0.0.1:8100/v1/status"
curl -s "http://127.0.0.1:8100/v1/status?probe=true"
```

### 响应（实测片段）

```json
{
  "contract_version": "CF-CONTRACT-2.0",
  "request_id": "ba5dce68ae124ac0",
  "operation": "status",
  "success": true,
  "data": {
    "service": "careflow-ai-rag",
    "version": "0.1.0",
    "contract_version": "CF-CONTRACT-2.0",
    "app_env": "development",
    "ai_provider": "mock",
    "started_at": "2026-09-17T05:30:32+00:00",
    "uptime_seconds": 30.923,
    "components": [
      { "name": "manifest",   "status": "missing", "detail": "manifest 不存在：…", "extra": { "active": 0 } },
      { "name": "knowledge",  "status": "missing", "detail": "chunks 不存在：…",   "extra": { "indexed_documents": 0 } },
      { "name": "qianfan",    "status": "ok",      "detail": "mock provider（不访问外部网络，不代表千帆可用）", "extra": { "model": "ernie-4.0-turbo-8k" } },
      { "name": "llm_client", "status": "ok",      "detail": "provider=mock", "extra": {} },
      { "name": "safety",     "status": "ok",      "detail": "规则引擎已加载（输入硬拦截 + 输出裁剪 + 红旗提示）", "extra": {} }
    ],
    "manifest": {
      "path": "…\\knowledge\\manifest\\knowledge_manifest.csv",
      "documents_total": 0,
      "documents_active": 0,
      "by_status": {},
      "by_authority_level": {},
      "by_kb": {},
      "problems": []
    },
    "knowledge": {
      "path": "…\\knowledge\\chunks\\chunks.jsonl",
      "chunks_total": 0,
      "chunks_by_kb": {},
      "indexed_documents": 0
    },
    "qianfan": {
      "status": "ok",
      "detail": "mock provider（不访问外部网络，不代表千帆可用）",
      "base_url": "https://qianfan.baidubce.com",
      "model": "ernie-4.0-turbo-8k",
      "app_id_set": false,
      "api_key_set": false,
      "kb_ids": { "KB_CORE": "", "KB_HTN": "", "KB_DM": "", "KB_COPD": "",
                  "KB_MULTIMORBIDITY": "", "KB_LIFESTYLE": "", "KB_PRIMARYCARE": "", "KB_WHO": "" },
      "kb_configured": false
    },
    "config": { "…": "见下文" },
    "endpoints": ["GET /health", "GET /v1/status", "POST /v1/extract",
                  "POST /v1/rag/answer", "POST /v1/followup/draft"]
  },
  "warnings": [],
  "meta": { }
}
```

### `config` —— 已脱敏的配置视图

`data.config` 来自 `Settings.redacted()`，**绝不回显密钥明文**，只暴露布尔标记：

```json
{
  "app_env": "development",
  "ai_provider": "mock",
  "log_level": "INFO",
  "qianfan_model": "ernie-4.0-turbo-8k",
  "qianfan_base_url": "https://qianfan.baidubce.com",
  "qianfan_auth_mode": "bearer",
  "qianfan_app_id_set": false,
  "qianfan_api_key_set": false,
  "qianfan_kb_ids": { "KB_HTN": "" },
  "rag_top_k": 5,
  "rag_max_context_chars": 12000,
  "rag_enable_llm_router": true,
  "request_timeout_seconds": 20,
  "max_retries": 1
}
```

`qianfan_app_id_set` / `qianfan_api_key_set` 为 `bool`；`qianfan_kb_ids` 中已配置的项显示为 `"SET"`，
未配置为空字符串。**该端点可以安全地暴露给运维面板，但不应暴露给终端用户。**

---

## 6. `POST /v1/extract` —— 结构化提取

将患者自然语言健康记录转换为结构化 `Observation`。

### 请求体

| 字段 | 类型 | 必填 | 约束 |
|---|---|---|---|
| `text` | string | ✅ | `1..4000` 字符，不可为纯空白 |
| `patient_context` | object | ❌ | 见 §9 |
| `options.include_model_meta` | bool | ❌ | 默认 `true` |
| `options.include_retrieval_hints` | bool | ❌ | 默认 `false` |
| `options.max_observations` | int | ❌ | `1..200`，默认 `40` |

请求模型为 **`StrictModel`（`extra="forbid"`）**：传入未知字段直接 **HTTP 422**，不会被静默忽略。

### 请求

```bash
curl -sX POST http://127.0.0.1:8100/v1/extract \
  -H "Content-Type: application/json" \
  -d '{
    "text": "今天血压135/85，吃了二甲双胍，早上走了一小时。",
    "patient_context": { "age_years": 62, "sex": "male", "known_conditions": ["HYPERTENSION"] }
  }'
```

### 响应（实测，HTTP 200）

```json
{
  "contract_version": "CF-CONTRACT-2.0",
  "request_id": "97a0e90712584ea2",
  "operation": "extract",
  "success": true,
  "data": {
    "observations": [
      {
        "type": "BLOOD_PRESSURE",
        "value": { "systolic": 135, "diastolic": 85 },
        "unit": "mmHg",
        "confidence": 0.98,
        "source_text": "血压135/85",
        "needs_confirmation": false,
        "observed_at": null
      },
      {
        "type": "MEDICATION",
        "value": { "name": "二甲双胍" },
        "unit": "",
        "confidence": 0.85,
        "source_text": "吃了二甲双胍",
        "needs_confirmation": true,
        "observed_at": null
      }
    ],
    "unmatched_text": "今天 ， ，早上走了一小时。",
    "observation_types": ["BLOOD_PRESSURE", "MEDICATION"],
    "needs_patient_confirmation": true,
    "safety": { "…": "见 §10" },
    "model": {
      "provider": "mock", "model": "rule-engine", "latency_ms": 0,
      "attempts": 1, "prompt_version": "EXTRACT-2.0",
      "usage": { "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0 }
    }
  },
  "warnings": [],
  "meta": {
    "observation_count": 2,
    "dropped_observations": [],
    "…": "其他可观测性字段见 §3.4"
  }
}
```

### 关键字段语义

- **`source_text`**：必须是用户原文中的**连续片段**，用于患者确认与审计回溯。
  **这是提取可信度的基础**——业务后端做人工确认时应逐条比对 `source_text` 与 `text`。
- **`needs_confirmation`**：该条建议由患者/医生确认后才入库。
  例如上例中 `MEDICATION` 为 `true`（用药信息需确认），`BLOOD_PRESSURE` 为 `false`（数值明确）。
- **`unmatched_text`**：未能结构化的剩余文本，**不要丢弃**——可能包含未覆盖的临床信息。
- **`needs_patient_confirmation`**：整体标记，当前恒为 `true`（契约要求人工介入）。
- **`observation_types`**：白名单内的**允许类型**集合（见下）。

### 输入归一化：匹配折叠全角，但 `source_text` 保留用户原文

> ⚠️ **这是集成方会直接观察到的行为**，务必按此实现患者确认界面。

**规则**：入口统一对输入做**全角 → 半角折叠**，用于**规则匹配与检索**；
但 `source_text` **切片自用户原文**，因此**保留用户输入时的全角写法**。

```python
fold_fullwidth(text)   # ＢＰ１５８／９６ -> BP158/96   （严格 1:1）
rule_extract(text)     # 匹配在折叠文本上；source_text = original[match.start():match.end()]
```

**折叠范围**（`app/core/json_utils.py::fold_fullwidth`）：

| 范围 | 处理 |
|---|---|
| `U+FF01 ~ U+FF5E` | → `U+0021 ~ U+007E`（全角 ASCII → 半角，`code - 0xFEE0`） |
| `U+3000` | → 半角空格 |
| 其他（含中文字符） | **不动** |

**为什么可以这样切片**：`fold_fullwidth` 是**严格 1:1 的字符替换**
（每个全角字符映射到恰好一个半角字符），折叠文本与原文**下标一一对应**，
因此在折叠文本上匹配得到的 `[start, end)` 可以直接用于切原文。

**实测样例**（全角输入，输出 `source_text` 仍是全角原文）：

| 请求 `text` | 提取结果 `value` | 返回的 `source_text` |
|---|---|---|
| `ＢＰ１５８／９６` | `{"systolic": 158, "diastolic": 96}` | **`ＢＰ１５８／９６`**（全角保留） |
| `体温３６.８` | `{"value": 36.8}` | **`体温３６.８`**（全角保留） |
| `血压１４０／９０` | `{"systolic": 140, "diastolic": 90}` | **`血压１４０／９０`**（全角保留） |

**对集成方的两个直接含义**：

1. **不要**对 `source_text` 做全角/半角归一化再与原文比对——
   它**本来就是原文的全角写法**，可直接在 `text` 中做子串定位以高亮回显。
2. 若前端需要展示规范化后的数值，请使用 `value`（已结构化，`158` 而非 `１５８`），
   **不要**解析 `source_text`。

> **可信度保证**：`source_text` 还必须能**在用户原文中逐字找到**，
> 否则该条观察会被丢弃并记入 `meta.dropped_observations`
> （`reason = "ungrounded_source_text"`，见 `app/services/extraction_service.py::is_grounded`）。

### `ObservationType` 白名单

不在白名单内的内容**一律不得**出现在输出中（防止模型自行发明字段）：

```
BLOOD_PRESSURE  BLOOD_GLUCOSE  HBA1C          BLOOD_LIPID   URIC_ACID
WEIGHT          HEIGHT         BMI            WAIST         HEART_RATE
BLOOD_OXYGEN    BODY_TEMPERATURE  PEAK_FLOW   SYMPTOM       MEDICATION
ADHERENCE       SMOKING        ALCOHOL        EXERCISE      DIET
SLEEP           MOOD           FOLLOWUP_EVENT OTHER
```

### 容错设计（重要）

`Observation` 继承 **`TolerantModel`（`extra="ignore"`）**，且对模型输出做了防御性归一化：

- `value` 若被模型写成标量/字符串 → 自动包装为 `{"value": ...}`；
- `confidence` 非数值 → 回落 `0.5`，并被夹到 `[0.0, 1.0]`；
- `BLOOD_PRESSURE` 缺少 `systolic`/`diastolic` 对或标量 → 自动置 `needs_confirmation = true`。

即：**LLM 输出的轻微格式偏差不会让请求失败，而是转为"需确认"或默认值**，
同时 `meta.dropped_observations` 记录被丢弃的条目。业务后端应把 `dropped_observations` 非空视为质量信号。

---

## 7. `POST /v1/rag/answer` —— RAG 问答（带真实 Citation）

完整链路与设计见 [`RAG_ARCHITECTURE.md`](./RAG_ARCHITECTURE.md)。

### 请求体

| 字段 | 类型 | 必填 | 约束 / 默认 |
|---|---|---|---|
| `query` | string | ✅ | `1..2000` 字符，不可为纯空白 |
| `patient_context` | object | ❌ | 见 §9 |
| `options.top_k` | int | ❌ | `1..20`，默认取 `RAG_TOP_K`（5） |
| `options.domains` | string[] | ❌ | 显式指定知识域；为空则由 Domain Router 决定（见下方注意） |
| `options.answer_language` | `"zh"` \| `"en"` | ❌ | 默认 `"zh"` |
| `options.require_citations` | bool | ❌ | 默认 `true` |
| `options.max_context_chars` | int | ❌ | `500..40000`，默认取 `RAG_MAX_CONTEXT_CHARS`（12000） |
| `options.include_retrieved` | bool | ❌ | 默认 `true`（是否回传检索命中原文） |
| `options.allow_no_evidence` | bool | ❌ | **默认 `true`**（见 §7.2） |
| `options.min_score` | float | ❌ | `0.0..1.0`，默认取 `RAG_SCORE_THRESHOLD`（0.0） |

> ✅ **`options.domains` 的非法值现在返回 422（2026-09-17 修复）**：
> 修复前，传入 `{"domains": ["KB_FAKE"]}` 会返回 **HTTP 200** 且 `data.domains = []`
> ——非法域被静默丢弃，**静默地把检索范围放大到全库**。
>
> **现在** `RagOptions` 与 `FollowUpOptions` 都挂了 `validate_domains()` 校验器（实测）：
>
> | 请求 | HTTP | `error.code` |
> |---|---:|---|
> | `{"domains": ["KB_FAKE"]}` | **422** | `SCHEMA_VALIDATION_FAILED` |
> | `{"domains": ["KB_HTP"]}`（拼写错误） | **422** | `SCHEMA_VALIDATION_FAILED` |
> | `{"domains": ["KB_HTN"]}` | 200 | — |
>
> 422 错误详情示例（实测）：
>
> ```
> Value error, 未知知识域 ['KB_FAKE']，可选值：['KB_CORE', 'KB_HTN', 'KB_DM',
> 'KB_COPD', 'KB_MULTIMORBIDITY', 'KB_LIFESTYLE', 'KB_PRIMARYCARE', 'KB_WHO']
> ```
>
> **行为变化的意义**：域名拼写错误现在**快速失败**，不再静默放宽检索范围，
> 调用方可以放心依赖 `domains` 收敛结果范围。
>
> 回归测试：`test_unknown_domain_rejected_at_schema_level`、`test_valid_domains_accepted`、
> `test_unknown_domain_rejected_for_followup`、`test_api_rejects_unknown_domain`。
>
> 合法的域取值只有 8 个：`KB_CORE`、`KB_HTN`、`KB_DM`、`KB_COPD`、
> `KB_MULTIMORBIDITY`、`KB_LIFESTYLE`、`KB_PRIMARYCARE`、`KB_WHO`。

> **边界约束均已实测确认**：`top_k` 取 `0`/`21` → 422（`greater_than_equal`/`less_than_equal`），
> 取 `20` → 200；`min_score=1.5` → 422；`max_context_chars=499` → 422；
> `answer_language="fr"` → 422（`literal_error`）；`query` 2001 字符 → 422（`string_too_long`）。

### 请求

```bash
curl -sX POST http://127.0.0.1:8100/v1/rag/answer \
  -H "Content-Type: application/json" \
  -d '{
    "query": "高血压患者每天应该吃多少盐？",
    "patient_context": { "age_years": 62, "sex": "male" },
    "options": { "top_k": 5, "include_retrieved": true }
  }'
```

### 响应（实测，知识库为空时的无证据路径，HTTP 200）

```json
{
  "contract_version": "CF-CONTRACT-2.0",
  "request_id": "8487d7657305416e",
  "operation": "rag.answer",
  "success": true,
  "data": {
    "answer": "现有官方资料中没有检索到足以回答这个问题的内容，因此我不能给出具体回答。\n\n建议：\n1. 换一种更具体的问法…",
    "insufficient_evidence": true,
    "citations": [],
    "retrieved": [],
    "domains": ["KB_HTN", "KB_LIFESTYLE"],
    "context_chars": 0,
    "dropped_citations": [],
    "safety": {
      "blocked": false, "block_reason": "", "flags": [], "redactions": [],
      "injection_detected": false, "advice_seeking": false,
      "requires_human_confirmation": true
    },
    "model": { "provider": "mock", "model": "no-evidence", "prompt_version": "RAG-2.0", "…": "…" }
  },
  "warnings": [],
  "meta": {
    "domains": ["KB_HTN", "KB_LIFESTYLE"],
    "document_ids": [],
    "degraded": false,
    "notes": ["retrieval returned 0 hits"],
    "routing": {
      "domains": ["KB_HTN", "KB_LIFESTYLE"],
      "reason": "确定性关键词命中：KB_HTN(高血压,血压); KB_LIFESTYLE(盐)",
      "method": "deterministic"
    }
  }
}
```

### 7.1 `data` 字段

| 字段 | 说明 |
|---|---|
| `answer` | 回答正文，可含 `[1]` 形式引用编号 |
| `insufficient_evidence` | `true` 表示证据不足（此时 `citations` 必为 `[]`） |
| `citations` | **Citation 数组，由服务端程序化构造**（见下） |
| `retrieved` | 本轮真实检索命中（`include_retrieved=false` 时为空） |
| `domains` | 本轮生效的知识域 |
| `context_chars` | 送入模型的上下文字符数 |
| `dropped_citations` | **被校验器拒绝的非法引用**（保留审计证据） |
| `safety` | 安全报告，见 §10 |
| `model` | 模型元数据 |

### Citation 结构

```json
{
  "document_id": "HTN001",
  "chunk_id": "HTN001-0032",
  "title": "国家基层高血压防治管理指南（2020版）",
  "section": "5.2 生活方式干预",
  "authority": "国家卫生健康委员会",
  "authority_level": "P0",
  "version": "2020",
  "effective_date": "2020-12-01",
  "source_url": "http://www.nhc.gov.cn/…",
  "quote": "……（检索命中片段的原文截取，最多 160 字符）"
}
```

> **反幻觉保证**：`quote` 是**检索命中片段的原文截取**，`source_url`/`title`/`authority` 取自
> manifest，**均非模型生成**。LLM 只允许输出 `[n]` 编号与 `used_chunk_ids`，
> 由 `CitationService` 还原为真实文档；编造的编号或 chunk_id 会被删除并记录到 `dropped_citations`。
> 详见 [`RAG_ARCHITECTURE.md` §4](./RAG_ARCHITECTURE.md)。

### `dropped_citations[].reason` 取值

| reason | 含义 |
|---|---|
| `marker_out_of_range` | LLM 引用的 `[n]` 编号超出本轮命中数量 |
| `chunk_not_retrieved_this_round` | 声明的 `chunk_id` 不在本轮检索结果中 |
| `missing_document_id` | 命中缺少 `document_id` |
| `document_not_in_manifest` | 文档不存在于 manifest（疑似幻觉） |
| `document_not_active` | 文档存在但 `status != active` |
| `chunk_document_mismatch` | chunk 归属与声明的 `document_id` 不一致 |
| `manifest_source_url_missing` | manifest 中 `source_url` 缺失或非 `http` 开头 |

### 7.2 无证据策略（关键行为）

| `options.allow_no_evidence` | 行为 |
|---|---|
| `true`（默认） | **HTTP 200**，`success=true`，`data.insufficient_evidence=true`，`citations=[]`，`answer` 为安全兜底话术 |
| `false` | **HTTP 200**，`success=false`，`error.code = "RAG_NO_EVIDENCE"` |

> ⚠️ **注意 `allow_no_evidence=false` 时 HTTP 状态码仍是 200**。
> 这是契约的有意设计：`ErrorCode.RAG_NO_EVIDENCE` 在 `ERROR_HTTP_STATUS` 中显式映射为 `200`，
> 因为"无证据"被定义为**有意义的空答案**，而非传输层失败。
> **客户端必须检查 `success` 字段，不能只看 HTTP 状态码。**
>
> 但注意：当 `RAG_NO_EVIDENCE` 由**未捕获异常处理器**抛出时（属于 `CareFlowError`），
> 走的是 `_careflow_error` 分支，其 `status_code=exc.http_status` 同样为 200。
> 实测确认返回 `HTTP 200` + `success:false`。

### 7.3 安全拦截

若查询命中提示词注入/越权/索取处方规则，请求在检索前即被拦截：

```json
{
  "contract_version": "CF-CONTRACT-2.0",
  "request_id": "eb8362bbd0cd43ae",
  "operation": "v1.rag.answer",
  "success": false,
  "error": {
    "code": "SAFETY_BLOCKED",
    "message": "安全策略拦截：检测到指令覆盖尝试，本系统不接受此类请求。",
    "details": { "flags": ["PROMPT_INJECTION:指令覆盖尝试"] }
  },
  "warnings": [],
  "meta": {}
}
```

**HTTP 403**。规则清单见 [`SAFETY.md`](./SAFETY.md)。

---

## 8. `POST /v1/followup/draft` —— 医生随访草稿

### 请求体

| 字段 | 类型 | 必填 | 约束 / 默认 |
|---|---|---|---|
| `checkin_text` | string | ✅ | `1..4000` 字符，不可为纯空白 |
| `patient_context` | object | ❌ | 见 §9 |
| `recent_observations` | Observation[] | ❌ | 最多 100 条 |
| `options.top_k` | int | ❌ | `1..20` |
| `options.domains` | string[] | ❌ | 显式知识域（**非法值返回 422**，见 §7 注意） |
| `options.answer_language` | `"zh"`\|`"en"` | ❌ | 默认 `"zh"` |
| `options.include_education` | bool | ❌ | 默认 `true` |
| `options.max_questions` | int | ❌ | `1..15`，默认 `6` |
| `options.include_retrieved` | bool | ❌ | 默认 `false`（注意：与其他端点默认相反） |

### 请求

```bash
curl -sX POST http://127.0.0.1:8100/v1/followup/draft \
  -H "Content-Type: application/json" \
  -d '{ "checkin_text": "这几天有点头晕，血压145/92，药按时吃了。" }'
```

### 响应（实测，HTTP 200）

```json
{
  "contract_version": "CF-CONTRACT-2.0",
  "request_id": "30b3102cff414827",
  "operation": "followup.draft",
  "success": true,
  "data": {
    "summary": "这几天有点头晕，血压145/92，药按时吃了。本次记录包含：血压 145/92 mmHg；症状 头晕。",
    "questions": [
      "最近家庭血压测量是否规律？测量前是否静坐 5 分钟？",
      "这个症状持续多久了？有没有加重或缓解的诱因？",
      "家里有没有血压计？最近一周测了几次？",
      "最近两周有没有出现头晕、胸闷、气短、乏力等不适？",
      "目前服用的药物是否按时服用？有没有漏服或自行调整？",
      "最近的饮食口味偏咸吗？每天食盐大约多少？"
    ],
    "education": "本次未检索到足够的官方资料支撑健康教育要点，请医生补充。",
    "citations": [],
    "observations": [
      { "type": "BLOOD_PRESSURE", "value": { "systolic": 145, "diastolic": 92 },
        "unit": "mmHg", "confidence": 0.98, "source_text": "血压145/92", "needs_confirmation": false },
      { "type": "SYMPTOM", "value": { "name": "头晕", "present": true, "keyword": "头晕" },
        "unit": "", "confidence": 0.8, "source_text": "头晕", "needs_confirmation": true }
    ],
    "domains": ["KB_HTN"],
    "retrieved": [],
    "requires_human_confirmation": true,
    "safety": {
      "blocked": false, "block_reason": "", "flags": ["OUT_OF_TARGET_BLOOD_PRESSURE"],
      "redactions": [], "injection_detected": false, "advice_seeking": false,
      "requires_human_confirmation": true
    },
    "model": { "provider": "mock", "model": "rule-engine", "prompt_version": "FOLLOWUP-2.0" }
  },
  "warnings": [],
  "meta": { "domains": ["KB_HTN"], "notes": ["dropped_citations=0"], "…": "…" }
}
```

### 关键契约保证

> **`data.requires_human_confirmation` 恒为 `true`。**
> 这不是模型输出，而是端点**强制覆写**（`app/api/followup.py`）：
> ```python
> result["data"]["requires_human_confirmation"] = True
> ```
> 随访草稿**永远**是草稿，必须经医生确认后才能成为正式随访记录。

### 字段说明

| 字段 | 说明 |
|---|---|
| `summary` | 本次随访记录摘要 |
| `questions` | 建议医生追问的问题（最多 `max_questions`） |
| `education` | 健康教育要点；**证据不足时会明确说明"请医生补充"，不会编造** |
| `citations` | 与 RAG 相同的真实 Citation |
| `observations` | 从 `checkin_text` 结构化出的观察（复用 Extraction 管线） |
| `requires_human_confirmation` | **恒为 `true`** |

### 随访特有的安全标记

除通用红旗外，随访服务会对**异常指标**追加确定性标记（`safety.flags`）：

| flag | 含义 |
|---|---|
| `OUT_OF_TARGET_BLOOD_PRESSURE` | 血压读数超出目标范围 |
| `LOW_BLOOD_GLUCOSE_READING` | 低血糖读数 |
| `OUT_OF_TARGET_FASTING_GLUCOSE` | 空腹血糖超标 |
| `OUT_OF_TARGET_POSTPRANDIAL_GLUCOSE` | 餐后血糖超标 |
| `LOW_BLOOD_OXYGEN_READING` | 血氧偏低 |
| `EMERGENCY_RED_FLAG` | 命中高风险红旗（**始终保留**，含科普场景） |
| `EMERGENCY_KNOWLEDGE_FRAME` | **2026-09-17 新增**：科普框架提问且无急性标记 → **不前置 120 话术** |

> 这些是**信号**，不是 Attention Level 判定。关注等级由 CareFlow 业务后端的 Rule Engine 决定。

#### 红旗的两段式行为（`EMERGENCY_KNOWLEDGE_FRAME`）

2026-09-17 起，红旗区分「急性自述」与「科普提问」，避免对科普问句前置"立即拨打 120"：

| 场景 | `EMERGENCY_RED_FLAG` | `EMERGENCY_KNOWLEDGE_FRAME` | 前置 120 |
|---|---|---|---|
| 急性自述（`我现在胸痛大汗`） | ✅ | — | ✅ |
| 在场他人急症（`家人突然晕倒了`） | ✅ | — | ✅ |
| 科普提问（`如何识别脑卒中早期症状言语不清`） | ✅ **保留** | ✅ | ❌ |
| 科普提问但含急性标记 | ✅ | — | ✅ |

实测响应（科普场景）：

```json
"safety": { "flags": ["EMERGENCY_KNOWLEDGE_FRAME", "EMERGENCY_RED_FLAG"], ... }
```

> **业务后端注意事项**：
> 1. `EMERGENCY_RED_FLAG` 在科普场景下**依然存在**，可继续用于 Rule Engine 判断；
> 2. `EMERGENCY_KNOWLEDGE_FRAME` **仅**用于抑制"立即拨打 120"这一段前置话术；
> 3. 判定入口是 `SafetyService.emergency_notice_required(flags)`，
>    它等价于 `EMERGENCY_RED_FLAG in flags and EMERGENCY_KNOWLEDGE_FRAME not in flags`；
> 4. **本服务不做急症分诊**，急症识别必须由业务后端结合结构化数据自主决策；
> 5. 请不要把 `EMERGENCY_RED_FLAG` 直接渲染为"你处于紧急状态"的强断言。

---

## 9. `patient_context` —— 最小必要患者上下文

```json
{
  "patient_ref": "p_7f3a91",
  "age_years": 62,
  "sex": "male",
  "known_conditions": ["HYPERTENSION", "DIABETES"],
  "locale": "zh"
}
```

| 字段 | 约束 |
|---|---|
| `patient_ref` | 最长 64 字符，业务后端的**不可逆引用 ID** |
| `age_years` | `0..130` |
| `sex` | `male` \| `female` \| `other` \| `unknown` |
| `known_conditions` | 最多 20 项 |
| `locale` | `zh` \| `en`，默认 `zh` |

### 🔒 隐私硬约束

> **`patient_context` 不接受姓名、身份证、手机号、住址等直接标识符。**
> 请求模型为 `extra="forbid"`，传入 `name`、`phone`、`id_card` 等字段会直接 **HTTP 422 被拒**。
>
> 真实的身份绑定由 CareFlow 业务后端通过 `patient_ref` 完成。
> 这样设计使得本服务**即使在日志或链路追踪中泄露，也不包含可识别个人身份的信息（PII）**。
>
> **业务后端在调用本服务前必须先完成去标识化**，不要把原始病历或含 PII 文本直接送入。

---

## 10. `safety` 对象

所有生成类端点的 `data.safety` 结构一致：

```json
{
  "blocked": false,
  "block_reason": "",
  "flags": [],
  "redactions": [],
  "injection_detected": false,
  "advice_seeking": false,
  "requires_human_confirmation": true
}
```

| 字段 | 说明 |
|---|---|
| `blocked` | 输出侧是否因裁剪过多被整体替换为安全话术 |
| `block_reason` | 阻断原因（人可读） |
| `flags` | 命中的标记集合（`PROMPT_INJECTION:*`、`EMERGENCY_RED_FLAG`、`EMERGENCY_KNOWLEDGE_FRAME`、`ADVICE_SEEKING_*`、`BLOCKED_*`、`CONTEXT_INJECTION_SUSPECTED:*`、`OUT_OF_TARGET_*` 等） |
| `redactions` | 输出侧被裁剪的类别：`diagnosis` / `medication_change` / `self_treat` / `dosage` |
| `injection_detected` | 输入侧是否检测到注入 |
| `advice_seeking` | 是否在寻求诊疗建议 |
| `requires_human_confirmation` | **恒为 `true`** |

**只暴露信号，不给出临床决策**。完整规则见 [`SAFETY.md`](./SAFETY.md)。

---

## 11. 错误码

`error.code` 取值来自 `ErrorCode` 枚举，与 HTTP 状态码的映射：

| `error.code` | HTTP | 触发场景 |
|---|---:|---|
| `INVALID_INPUT` | 400 | 输入不合法（业务层判定） |
| `SCHEMA_VALIDATION_FAILED` | 422 | 请求体不符合 Schema，**含额外字段** |
| `QIANFAN_TIMEOUT` | 504 | 千帆请求超时（超过 `REQUEST_TIMEOUT_SECONDS`） |
| `QIANFAN_RATE_LIMIT` | 429 | 千帆限流（QPS/配额） |
| `QIANFAN_UNAVAILABLE` | 503 | 鉴权失败、服务端错误、网络异常、非 JSON 响应 |
| `RAG_NO_EVIDENCE` | **200** | 检索未命中且 `allow_no_evidence=false` |
| `KNOWLEDGE_MANIFEST_INVALID` | 500 | manifest 结构/内容非法 |
| `SAFETY_BLOCKED` | 403 | 命中安全硬拦截规则 |
| `CONTRACT_VERSION_ERROR` | 400 | `X-CF-Contract-Version` 不受支持 |
| `INTERNAL_ERROR` | 500 | 未捕获异常 |

### 校验失败示例（实测，HTTP 422）

```bash
curl -sX POST http://127.0.0.1:8100/v1/extract \
  -H "Content-Type: application/json" \
  -d '{ "text": "x", "bogus_field": 1 }'
```

```json
{
  "contract_version": "CF-CONTRACT-2.0",
  "request_id": "c08ce7823b1043ca",
  "operation": "v1.extract",
  "success": false,
  "error": {
    "code": "SCHEMA_VALIDATION_FAILED",
    "message": "请求体不符合 CF-CONTRACT-2.0 Schema",
    "details": {
      "errors": [
        { "loc": ["body", "bogus_field"], "type": "extra_forbidden",
          "msg": "Extra inputs are not permitted" }
      ]
    }
  },
  "warnings": [],
  "meta": {}
}
```

`details.errors` 已清洗为 `{loc, type, msg}` 三元组，并**截断到最多 20 条**。

### 契约版本不匹配示例（实测，HTTP 400）

```bash
curl -sX POST http://127.0.0.1:8100/v1/rag/answer \
  -H "Content-Type: application/json" \
  -H "X-CF-Contract-Version: CF-CONTRACT-1.0" \
  -d '{ "query": "x" }'
```

```json
{
  "contract_version": "CF-CONTRACT-2.0",
  "request_id": "3574d7a943be426a",
  "operation": "unknown",
  "success": false,
  "error": {
    "code": "CONTRACT_VERSION_ERROR",
    "message": "不支持的契约版本：CF-CONTRACT-1.0",
    "details": { "requested": "CF-CONTRACT-1.0",
                 "supported": ["CF-CONTRACT-2.0"],
                 "current": "CF-CONTRACT-2.0" }
  },
  "warnings": [],
  "meta": {}
}
```

### 内部错误

`INTERNAL_ERROR` 的 `message` 是固定话术，**不泄露堆栈**；
调用方应记录 `request_id` 并联系运维（完整堆栈只写入服务端日志）。

---

## 12. 集成注意事项（业务后端必读）

1. **始终检查 `success`，不要只看 HTTP 状态码。**
   `RAG_NO_EVIDENCE` 返回 200 但 `success=false`；反之 `/health` 无 `success` 字段。
2. **`operation` 在失败时带 `v1.` 前缀**，不要用它做分支判断。
3. **`requires_human_confirmation` 永远是 `true`**：本服务的任何输出都不是可直接采信的结论。
4. **不要把 `answer` 视为医学结论**。它是"基于官方资料的说明"。
   `citations` 为空时**必须**向用户明示"无官方依据"。
5. **必须把 `meta.degraded` 纳入监控**。降级意味着回答可能来自原文摘录而非生成式模型。
6. **`dropped_citations` 非空是质量告警信号**：说明模型产生了幻觉引用，已被删除。
7. **`patient_context` 严禁携带 PII**，否则 422。
8. **请求超时应大于 `REQUEST_TIMEOUT_SECONDS`**（默认 20s），因为服务端最多重试 `MAX_RETRIES` 次。
9. **携带 `X-Request-ID`** 以便端到端排查；服务端会原样回显。
10. `patient_ref` 必须是**不可逆**引用；不要传原始病历号。

---

## 13. 相关文档

- [`RAG_ARCHITECTURE.md`](./RAG_ARCHITECTURE.md) —— 检索管线、Citation 校验、降级策略
- [`SAFETY.md`](./SAFETY.md) —— 安全边界、拦截规则、输出裁剪
