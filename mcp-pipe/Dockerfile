FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 基础系统依赖：为部分科学/图形库提供运行所需的动态库
# 注意：尽量保持精简；如有额外依赖再按需追加
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates curl git \
       build-essential \
       libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# 升级 pip，预装通用基础依赖
RUN python -m pip install --upgrade pip \
    && pip install --no-cache-dir websockets python-dotenv mcp fastmcp redis

# 仅复制 requirements（利用缓存，避免每次变更代码就失去构建缓存）
COPY notepad_mcp/requirements.txt /tmp/notepad-requirements.txt
COPY requirements-calculator.txt /tmp/requirements-calculator.txt
COPY xiaozhi-websearch/requirements.txt /tmp/websearch-requirements.txt

# 预装各 MCP 的依赖（notepad + calculator + websearch）
# 如 websearch 依赖较大，首次构建时间会更长
RUN pip install --no-cache-dir -r /tmp/notepad-requirements.txt \
    && pip install --no-cache-dir -r /tmp/requirements-calculator.txt \
    && pip install --no-cache-dir -r /tmp/websearch-requirements.txt

# 运行时仍通过挂载代码目录，保持开发效率
CMD ["bash", "-lc", "/app/scripts/start_mcp_pipe.sh"]
