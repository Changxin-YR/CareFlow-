# CareFlow 康脉智护 —— AI / RAG 子系统

> 基层慢病多病共管与智能随访平台的 **AI Gateway**。
> 契约版本 **CF-CONTRACT-2.0**｜服务端口 **8100**｜运行时模型平台 **百度千帆**

---

## ⚠️ 系统定位（先读这一节）

**CareFlow 不是 AI 医生。**

AI 子系统只负责：**理解 / 提取 / 检索 / 解释 / 总结 / 生成草稿**。

| 由本服务负责 | 由 CareFlow 业务后端负责 |
|---|---|
| 自然语言 → 结构化 Observation | 权限与鉴权 |
| 知识域路由、官方知识检索 | 数据库读写 |
| 基于检索上下文的健康教育 + 真实 Citation | Rule Engine |
| 医生随访草稿 | **Attention Level** |
| 输入/输出的确定性安全校验 | 正式保存、人工确认、审计 |

本服务**不**做诊断、**不**开药、**不**给剂量、**不**建议停药换药、**不**决策 Attention Level、
**不**写业务数据库。所有输出中 `requires_human_confirmation` 恒为 `true`。

---

## 目录

- [1. 快速开始](#1-快速开始)
- [2. 环境变量](#2-环境变量)
- [3. API 一览](#3-api-一览)
- [4. 知识库管线](#4-知识库管线)
- [5. 目录结构](#5-目录结构)
- [6. 测试与评测](#6-测试与评测)
- [7. Docker](#7-docker)
- [8. 关键设计决策](#8-关键设计决策)
- [9. 文档索引](#9-文档索引)
- [10. 当前状态与限制](#10-当前状态与限制)

---

## 1. 快速开始

### 1.1 本地离线跑通（不需要任何外部凭据）

```bash
cd careflow-ai-rag

python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt     # 含知识库管线与测试依赖

cp .env.example .env
# 编辑 .env，把 AI_PROVIDER 改为 mock（离线模式）

python -m uvicorn app.main:app --host 0.0.0.0 --port 8100
```

验证：

```bash
curl http://127.0.0.1:8100/health
curl -X POST http://127.0.0.1:8100/v1/extract \
  -H "Content-Type: application/json" \
  -d '{"text":"今天早上血压158/96，空腹血糖7.2，有点头晕"}'
```

`AI_PROVIDER=mock` 模式下：

- Extraction 走**确定性规则引擎**（正则 + 受控词表），可复现、可断言；
- RAG 的答案是**官方检索片段的原文摘录**（不做生成式改写），Citation 全部来自真实命中；
- Router 走确定性关键词路由；
- **不访问任何外部网络**。

> ⚠️ **Mock 成功 ≠ 千帆验证成功。** 任何交付报告都必须区分两者，
> 详见 [HANDOFF.md](HANDOFF.md) 的 BLOCKED 清单。

### 1.2 接千帆跑通

编辑 `.env`：

```ini
AI_PROVIDER=qianfan
QIANFAN_API_KEY=<你的 API Key>
QIANFAN_APP_ID=<你的 App ID>
QIANFAN_MODEL=ernie-4.0-turbo-8k
QIANFAN_BASE_URL=https://qianfan.baidubce.com
QIANFAN_KB_CORE_ID=<知识库 ID>
...
```

然后：

```bash
python scripts/sync_qianfan.py --dry-run     # 先看会同步什么
python scripts/sync_qianfan.py               # 真同步
python -m uvicorn app.main:app --port 8100
curl "http://127.0.0.1:8100/v1/status?probe=1"   # 真实探测千帆
```

---

## 2. 环境变量

完整模板见 [`.env.example`](.env.example)。关键项：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `APP_ENV` | `development` | `development` 输出人类可读日志，其他值输出单行 JSON |
| `AI_PROVIDER` | `mock` | `mock`（离线）或 `qianfan`（运行时正式） |
| `QIANFAN_API_KEY` / `QIANFAN_APP_ID` | 空 | 千帆凭据。**禁止提交真实密钥** |
| `QIANFAN_MODEL` | `ernie-4.0-turbo-8k` | 对话模型 |
| `QIANFAN_BASE_URL` | `https://qianfan.baidubce.com` | v2 OpenAI 兼容入口 |
| `QIANFAN_AUTH_MODE` | `bearer` | `bearer`（v2）/ `oauth`（旧网关 AK/SK 换 token） |
| `QIANFAN_KB_*_ID` | 空 | 8 个域的知识库 ID；留空则该域退化为本地切片检索 |
| `RAG_TOP_K` | `5` | 默认召回条数 |
| `RAG_MAX_CONTEXT_CHARS` | `12000` | 送入 LLM 的上下文上限 |
| `RAG_SCORE_THRESHOLD` | `0.0` | 检索最低分（0 = 不启用） |
| `RAG_ENABLE_LLM_ROUTER` | `true` | 是否允许 LLM 补充域路由（仅 qianfan 模式生效） |
| `REQUEST_TIMEOUT_SECONDS` | `20` | 单次千帆调用超时 |
| `MAX_RETRIES` | `1` | 重试次数，代码内**硬上限 2**，不存在无限重试 |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `MANIFEST_PATH` / `CHUNKS_PATH` | `knowledge/...` | 知识库产物路径（测试用覆盖点） |

---

## 3. API 一览

契约：**CF-CONTRACT-2.0**。完整字段表与 curl 示例见 [docs/API.md](docs/API.md)。

| 方法 | 路径 | 说明 | 响应结构 |
|---|---|---|---|
| GET | `/health` | 健康检查（运维探针） | **扁平** |
| GET | `/v1/status` | 运行状态与依赖明细 | 信封 |
| POST | `/v1/extract` | 自然语言 → 结构化 Observation | 信封 |
| POST | `/v1/rag/answer` | 官方知识 RAG 问答 + 真实 Citation | 信封 |
| POST | `/v1/followup/draft` | 医生随访草稿 | 信封 |

统一信封（成功）：

```json
{
  "contract_version": "CF-CONTRACT-2.0",
  "request_id": "0f3a...",
  "operation": "extract",
  "success": true,
  "data": { },
  "warnings": [],
  "meta": {
    "provider": "qianfan", "model": "ernie-4.0-turbo-8k",
    "latency_ms": 812, "token_usage": {"total_tokens": 512},
    "domains": ["KB_HTN"], "document_ids": ["HTN001"],
    "degraded": false, "notes": []
  }
}
```

统一信封（失败）：

```json
{
  "contract_version": "CF-CONTRACT-2.0",
  "request_id": "0f3a...",
  "operation": "extract",
  "success": false,
  "error": {"code": "SAFETY_BLOCKED", "message": "...", "details": {"flags": []}},
  "warnings": [],
  "meta": {}
}
```

错误码（10 个，含 HTTP 状态映射）：见 [docs/API.md](docs/API.md#错误码)。

---

## 4. 知识库管线

```bash
python scripts/download_documents.py          # ① 官方文档 → knowledge/raw/（幂等，已下载跳过）
python scripts/verify_sources.py              # ② 校验源 URL / 文件 / SHA256
python scripts/preprocess_documents.py        # ③ 清洗去噪 → knowledge/processed/*.md
python scripts/build_chunks.py                # ④ 结构化语义切片 → knowledge/chunks/chunks.jsonl
python scripts/validate_manifest.py           # ⑤ 硬校验（出错非 0 退出）
python scripts/sync_qianfan.py --dry-run      # ⑥ 同步到千帆知识库（需凭据）
```

已知难点与已验证方案：

- **`www.nhc.gov.cn` 的 WZWS JS 风控**：任何非浏览器客户端（httpx/requests/curl，
  无论 UA 怎么伪装）都会拿到 **HTTP 412**。必须用真实浏览器执行挑战。
  本项目把已验证的抓取器固化在 [`scripts/playwright_fetch.py`](scripts/playwright_fetch.py)，
  并处理了两个关键坑：
  1. **412 不是失败** —— 挑战页几秒后会自动重新导航，必须轮询 `inner_text("body")` 而不是看状态码；
  2. **部分页面正文极短**（如 WS/T 872—2025 只有 383 字符），真实内容在同页**附件 PDF** 里，
     需要解析附件链接并用同一个浏览器上下文下载。
- **付费墙文档不绕过**：`DM002` / `DM003` / `MULTI001` 等标记为 `local_file=PENDING`，
  `status=draft`，并在 [docs/KNOWLEDGE_BASE.md](docs/KNOWLEDGE_BASE.md) 给出人工下载指引。

知识权威等级：`P0` 国家现行卫生标准 > `P1` 国家卫健委正式文件 > `P2` 国家级医学中心 >
`P3` 中华医学会/国家级专业组织 > `P4` WHO 等国际权威补充。
冲突时优先**中国当前有效且适用于基层场景**的正式规范。

生产检索**只使用 `status=active`** 的文档。

---

## 5. 目录结构

```
careflow-ai-rag/
├── app/
│   ├── main.py                     # FastAPI 入口、纯 ASGI 中间件、异常处理
│   ├── api/                        # health / status / extraction / rag / followup
│   ├── core/                       # config / errors / logging / contract / json_utils
│   ├── clients/                    # qianfan（唯一千帆入口）/ mock / base 协议
│   ├── services/                   # manifest / routing / retrieval / rag / extraction
│   │                               # / followup / citation / safety
│   ├── schemas/                    # Pydantic v2 模型（CF-CONTRACT-2.0）
│   └── prompts/                    # 可评审的 Markdown Prompt（含版本号）
├── knowledge/
│   ├── raw/                        # 官方原文（HTML / PDF / DOCX）
│   ├── processed/                  # 清洗后的结构化 Markdown
│   ├── chunks/                     # chunks.jsonl + index_meta.json
│   └── manifest/knowledge_manifest.csv
├── scripts/                        # 下载 / 校验 / 清洗 / 切片 / 同步千帆 / 评测
├── eval/                           # 数据集 + REPORT.md + results/
├── tests/                          # pytest 测试套件
├── docs/                           # API / KNOWLEDGE_BASE / DATA_GAPS / GAP_FIX_REPORT / OCR_WORKFLOW / RAG_ARCHITECTURE / SAFETY
├── Dockerfile
├── README.md · HANDOFF.md · TEST_REPORT.md · CONTRACT_COMPLIANCE.md
└── .env.example
```

---

## 6. 测试与评测

```bash
# 单元 / 集成测试（默认 mock provider，不联网）
python -m pytest tests/ -v

# 覆盖率
python -m pytest tests/ --cov=app --cov-report=term-missing

# 离线评测（生成 eval/REPORT.md 与 eval/results/*.json）
python scripts/evaluate.py --provider mock

# 指定套件
python scripts/evaluate.py --provider mock --suite rag,citation
```

评测套件与用例数：Extraction 32 / Routing 28 / RAG 32 / Citation 22 / No-Evidence 12 /
Safety 24 / Prompt-Injection 18。

> **本项目的评测报告不包含任何"医学准确率"指标。**
> 可客观判定的是字段/数值提取、路由召回、检索命中、Citation 真实性、
> 无证据行为与安全拦截。**医学正确性必须由临床专家评审**，工程评测无法替代。

---

## 7. Docker

```bash
docker build -t careflow-ai-rag:dev .

docker run -d --name careflow-ai-rag \
  -p 8100:8100 \
  --env-file .env \
  careflow-ai-rag:dev

curl http://127.0.0.1:8100/health
```

镜像只安装**运行时依赖**（`requirements.txt`），知识库管线依赖
（playwright / pymupdf / bs4 等）不进入镜像，保持镜像精简。
容器以非 root 用户 `careflow` 运行，内置 `HEALTHCHECK`。

---

## 8. 关键设计决策

| 决策 | 理由 |
|---|---|
| **千帆是唯一模型入口**（`app/clients/qianfan.py`） | 契约硬要求。认证/超时/重试/日志/错误/Token 统计全部收敛在一处 |
| **Mock 是确定性规则引擎，不是"假 LLM"** | 让无凭据环境也能真实跑通整条管线并做可断言测试；`mock` 与 `qianfan` 走同一接口 |
| **Citation 由程序构造，LLM 只输出 `[n]` 编号** | LLM 自由生成引用必然产生幻觉；`source_url` 一律以 manifest 为准，LLM 即使篡改也不生效 |
| **Observation 的 `source_text` 必须能在原文里逐字找到** | LLM 路径下的 grounding 闸门：找不到就丢弃并记入 `meta.dropped_observations` |
| **无 LLM 时 RAG 回退到原文摘录** | 宁可给出可核对的原文，也不生成可能失真的总结 |
| **本地 BM25（中文二元组）作为检索基线** | 不引入向量库依赖即可离线工作；千帆知识库检索作为可选增强，用 RRF 融合 |
| **安全判定用确定性正则，不交给 LLM 裁决** | "让 LLM 决定安全边界"本身就是不可审计的；规则可枚举、可测试、可回归 |
| **`status != active` 的文档不进索引** | 生产不得检索到作废版本 |
| **纯 ASGI 中间件而非 `BaseHTTPMiddleware`** | 避免 contextvar 在任务边界丢失，保证 `request_id` 贯穿日志 |
| **`MAX_RETRIES` 代码内硬上限 2** | 契约要求禁止无限重试 |

---

## 9. 文档索引

| 文档 | 内容 |
|---|---|
| [docs/API.md](docs/API.md) | 端点、字段表、curl 示例、错误码 |
| [docs/RAG_ARCHITECTURE.md](docs/RAG_ARCHITECTURE.md) | 检索链路、BM25/RRF 公式、Citation 校验、降级路径 |
| [docs/SAFETY.md](docs/SAFETY.md) | 硬拦截/软标记/红旗/输出裁剪清单 + **已知局限** |
| [docs/KNOWLEDGE_BASE.md](docs/KNOWLEDGE_BASE.md) | 来源表（34 篇）、权威等级策略、覆盖缺口状态、切片统计 |
| **[docs/GAP_FIX_REPORT.md](docs/GAP_FIX_REPORT.md)** | **缺口修复报告：逐项 RESOLVED/BLOCKED 判定 + 证据链（SHA256/字节/文本层）** |
| [docs/OCR_WORKFLOW.md](docs/OCR_WORKFLOW.md) | **扫描件 OCR 草稿 → 人工校对 → 入库流程**（校对前不得置 active） |
| **[docs/DATA_GAPS.md](docs/DATA_GAPS.md)** | **需要人工获取的官方资料清单（去哪找 + 找到后怎么入库 + 验收标准）** |
| [HANDOFF.md](HANDOFF.md) | 交接说明与 **BLOCKED 清单** |
| [TEST_REPORT.md](TEST_REPORT.md) | 真实执行的测试结果 |
| [CONTRACT_COMPLIANCE.md](CONTRACT_COMPLIANCE.md) | 契约逐条对照 |
| [eval/REPORT.md](eval/REPORT.md) | 评测结果（脚本生成） |

---

## 10. 当前状态与限制

见 [HANDOFF.md](HANDOFF.md)。要点：

- **未经真实凭据验证的部分一律标记 `BLOCKED`**，不伪装为完成；
- 千帆 v2 的**知识库检索/AppBuilder 路径**在不同平台版本间存在差异，
  代码已把路径做成可配置项并做宽容解析，但**需要用当期官方文档核对**；
- 部分官方文档因付费墙**未纳入**知识库，已如实登记为 `PENDING`；
- 安全模块是**确定性正则**，存在同义改写等绕过可能（详见 `docs/SAFETY.md` 已知局限）。

---

## 许可与合规

- 本项目**不绕过任何付费墙或版权限制**抓取未授权全文；
- 知识库仅登记并使用**官方公开发布**的政策、标准与指南；
- 各来源文档的版权归原发布机构所有，本项目仅作检索与引用用途。
