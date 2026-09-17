# OCR 草稿的校对与入库流程

> 适用对象：**官方发布的文件本身没有可用文字层**，只能靠 OCR 的那几篇。
>
> 当前共有 **6 篇**处于这个状态，合计约 **107 页**：
>
> | document_id | 页数 | 官方源的问题 |
> |---|---:|---|
> | `PRIM003`（P0 标准 WS/T 484—2015） | 39 | PDF 的 ToUnicode CMap **全坏**：中文→U+00xx 控制区、数字→全角、字母→U+72xx |
> | `CORE002` | 10 | 官方附件是**纯扫描件**（PyMuPDF 抽取 0 字符） |
> | `LIFE001` | 14 | 扫描件（文本层仅 388 字符） |
> | `LIFE001A` | 16 | 扫描件（391 字符） |
> | `LIFE001B` | 14 | 扫描件（405 字符） |
> | `LIFE001C` | 14 | 扫描件（418 字符） |
> >
> ℹ️ **`LIFE008` 曾经被误判为扫描件，实测是原生文本型单页 PDF**
> （0 张图片、0 个矢量对象，文本层 106 字符即全文）—— 它**不需要 OCR**，已从本清单移除。
>
> ⚠️ **其余这些官方 PDF 是权威原文，不是「抓错了」。** 换链接、重下载都解决不了 ——
> PRIM003 那份「官方完整 PDF」的 SHA256 与我们已有的文件**完全相同**。

---

## 1. 为什么 OCR 结果不能直接入库

契约与项目规则都要求：**真实 Citation > 漂亮回答**，而 OCR 会**确定性地产出数字错误**：

| OCR 常见错误 | 后果 |
|---|---|
| `140` → `14O`、`0` → `O`、`1` → `l` | 血压/血糖/剂量数值错误 —— **在慢病管理里是不可接受的** |
| `—` / `–` / `-` → `一` | 日期区间、标准号被改（如 `2023—2030` → `2023一2030`） |
| 多栏排版读序错乱 | 句子被拼错，语义改变 |
| 表格结构丢失 | 数字与单位错位 |

所以项目中：**OCR 草稿一律放在 `knowledge/ocr/`，不进入 manifest / processed / chunks，
默认 `status=draft` 的文档也不会被生产检索命中。**

---

## 2. 生成 OCR 草稿

```bash
# 先看会处理哪些文档
python scripts/ocr_documents.py --dry-run

# 全量 OCR（约 108 页，10 分钟左右）
python scripts/ocr_documents.py

# 只处理某几篇
python scripts/ocr_documents.py --only CORE002 LIFE008
python scripts/ocr_documents.py --force      # 已存在也重跑
```

产出：

```
knowledge/ocr/<document_id>.txt      # 逐页 OCR 文本，页与页之间用 <!-- page N --> 分隔
knowledge/ocr/_ocr_report.json       # 每篇的页数/字符数/空白页数/耗时
```

脚本会自动做**确定性的无损修正**：把「数字之间的一」改回破折号（`2023一2030` → `2023—2030`）。
除此之外**不做任何语义改写**。

---

## 3. 人工校对流程

### 3.1 逐页对照

```powershell
# 把 PDF 渲染成图片，方便与 OCR 文本并排看
python -c "
import pymupdf, pathlib
src = pathlib.Path('knowledge/raw/01_core/CORE002.pdf')
out = pathlib.Path('knowledge/ocr/_preview/CORE002'); out.mkdir(parents=True, exist_ok=True)
with pymupdf.open(src) as doc:
    for i in range(doc.page_count):
        doc[i].get_pixmap(dpi=150).save(out / f'{i+1:03d}.png')
print('已生成预览图:', out)
"
```

也可以直接用 Edge / Chrome 打开 PDF，与 `knowledge/ocr/<ID>.txt` 左右对照。

### 3.2 校对重点（按风险从高到低）

| 优先级 | 检查项 | 说明 |
|---|---|---|
| **P0** | **所有数字** | 血压值、血糖值、剂量、年龄、频次、阈值、`mmol/L`/`mg` 等。**这是唯一会真正伤害患者的部分。** |
| **P0** | 否定词 | `不`/`无`/`禁`/`避免` 漏掉会逆转语义 |
| P1 | 标准号 / 文号 | `WS/T 484—2015`、`国卫办基层函〔2025〕439号` |
| P1 | 日期 | 发布/实施日期 |
| P1 | 章节号 | `3.2.2.1` 这类编号错位会影响条款引用 |
| P1 | 表格 | 列名与数值是否对上 |
| P2 | 标点/空格 | 可选，不影响检索 |

### 3.3 校对产物

校对完成后，把**校对后的文本**保存为：

```
knowledge/ocr/<document_id>.reviewed.txt
```

并在文件顶部保留一行说明：

```
# reviewed: yes | reviewer: <姓名> | date: YYYY-MM-DD | source: <官方 URL>
```

未标注 `reviewed: yes` 的文件**不会被入库脚本接受**。

---

## 4. 入库（校对通过后）

`knowledge/ocr/*.txt` 不是管线支持的输入格式（管线只支持 `.pdf` / `.html`），
所以需要把它转成一个 `<ID>.html`：

```powershell
python -c "
import pathlib, html
doc_id = 'CORE002'
text = pathlib.Path(f'knowledge/ocr/{doc_id}.reviewed.txt').read_text(encoding='utf-8')
assert 'reviewed: yes' in text.splitlines()[0:3].__str__(), '未标记 reviewed，拒绝入库'
body = []
for para in text.split('\n'):
    p = para.strip()
    if not p or p.startswith('<!--') or p.startswith('#'):
        continue
    body.append(f'<p>{html.escape(p)}</p>')
out = pathlib.Path(f'knowledge/raw/{doc_id}.html')
out.write_text('<html><head><meta charset=\"utf-8\"></head><body>' + '\n'.join(body) + '</body></html>', encoding='utf-8')
print('已写出', out)
"
```

然后按以下顺序重跑（**与 `docs/DATA_GAPS.md` §标准入库流程一致**）：

```bash
# 1) 改 knowledge/raw/_download_report.json 里该文档的：
#      local_file → knowledge/raw/<ID>.html
#      ext → "html"、content_kind → "html"
#      bytes / sha256 → 新文件的实际值
#      annex_pdf → null、secondary_files → []      ← 两个必踩的坑
# 2) 若该文档此前是 draft（如 LIFE001A/B/C），从 build_manifest.py 的 FORCE_DRAFT 里移除
python scripts/build_manifest.py
python scripts/preprocess_documents.py
python scripts/build_chunks.py          # 必须 0 verbatim problems
python scripts/validate_manifest.py     # 必须 VALIDATION PASSED
python scripts/verify_sources.py        # 必须 VERIFY PASSED
python scripts/verify_content_match.py  # 该文档的 title_bigram_ratio 应 ≥ 0.34（OK）
python -m pytest tests/ -q
python scripts/evaluate.py --provider mock
```

**验收**：该文档在 `verify_content_match.py` 里的判定要从 `MISMATCH` 变成 `OK`，
并且 `build_chunks.py` 报告 0 个 verbatim 问题。

---

## 5. 当前状态一览

| document_id | OCR 草稿 | 人工校对 | 入库 | 备注 |
|---|---|---|---|---|
| PRIM003 | ✅ 已生成 | ⬜ 待办 | ⬜ 待办 | P0 标准，**优先级最高**；39 页 |
| CORE002 | ✅ 已生成 | ⬜ 待办 | ⬜ 待办 | 10 页 |
| LIFE001 | ✅ 已生成 | ⬜ 待办 | ⬜ 待办 | 当前用官方发布页公文正文（1325 字符） |
| LIFE001A | ✅ 已生成 | ⬜ 待办 | ⬜ 待办 | 现为 `draft`，校对后才可改 active |
| LIFE001B | ✅ 已生成 | ⬜ 待办 | ⬜ 待办 | 同上 |
| LIFE001C | ✅ 已生成 | ⬜ 待办 | ⬜ 待办 | 同上 |

> 状态以 `knowledge/ocr/_ocr_report.json` 为准，上表在生成草稿后更新。

---

## 6. 一句话

> **OCR 草稿已经把「不可读」变成「可校对」。**
> 但从草稿到入库之间，**必须有一次人工数字校对** —— 这一步不能省，也不能自动化。
