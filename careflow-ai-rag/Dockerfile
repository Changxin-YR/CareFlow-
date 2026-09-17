# CareFlow 康脉智护 AI Gateway（CF-CONTRACT-2.0）
# 只安装运行时依赖 —— 知识库管线依赖（playwright / pymupdf 等）不入镜像。
#
# 构建：docker build -t careflow-ai-rag:dev .

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    APP_ENV=production \
    AI_PROVIDER=qianfan \
    HOST=0.0.0.0 \
    PORT=8100

WORKDIR /app

# 先装依赖，利用镜像层缓存
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 应用代码与知识库产物
COPY app/ ./app/
COPY knowledge/ ./knowledge/
COPY scripts/ ./scripts/
COPY .env.example ./.env.example

# 以非 root 运行
RUN useradd --create-home --shell /usr/sbin/nologin careflow \
    && chown -R careflow:careflow /app
USER careflow

EXPOSE 8100

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import json,urllib.request,sys; \
r=json.load(urllib.request.urlopen('http://127.0.0.1:8100/health', timeout=4)); \
sys.exit(0 if r.get('status') in ('ok','degraded') else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100", "--log-level", "info"]
