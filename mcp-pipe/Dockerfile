FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 基础系统依赖：动态库 + server_mcp 监控用到的 sudo/ss/ps 等
# 注意：不安装 docker daemon（docker.io 过重且不含客户端）；docker 客户端见下方静态二进制。
# 不再写 NOPASSWD sudoers：容器以 root 运行，sudo 本就无需密码，免密全开是多余的提权面。
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates curl git \
       build-essential \
       libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 libmagic1 \
       sudo procps iproute2 net-tools \
    && rm -rf /var/lib/apt/lists/*

# Docker 客户端（仅 client，不含 daemon）——通过 DOCKER_HOST 连接只读 docker-socket-proxy，
# 不直接挂载宿主 /var/run/docker.sock，避免容器获得宿主 root 等价能力。
RUN curl -fsSL https://download.docker.com/linux/static/stable/x86_64/docker-27.5.1.tgz \
       | tar -xz -C /usr/local/bin --strip-components=1 docker/docker \
    && docker --version

# 升级 pip，预装通用基础依赖
RUN python -m pip install --upgrade pip \
    && pip install --no-cache-dir websockets python-dotenv mcp fastmcp redis

# 仅复制 requirements（利用缓存，避免每次变更代码就失去构建缓存）
COPY notepad_mcp/requirements.txt /tmp/notepad-requirements.txt
COPY requirements-calculator.txt /tmp/requirements-calculator.txt
COPY xiaozhi-websearch/requirements.txt /tmp/websearch-requirements.txt
COPY server_mcp_vps/requirements.txt /tmp/server-mcp-requirements.txt

# 预装各 MCP 的依赖（notepad + calculator + websearch + server_mcp）
# server_mcp 依赖此前从未被安装，pytz 等只靠其它包的传递依赖蹭得，一旦解析变动即丢失。
RUN pip install --no-cache-dir -r /tmp/notepad-requirements.txt \
    && pip install --no-cache-dir -r /tmp/requirements-calculator.txt \
    && pip install --no-cache-dir -r /tmp/websearch-requirements.txt \
    && pip install --no-cache-dir -r /tmp/server-mcp-requirements.txt \
    # 修复 fastmcp 命名空间污染：fresh 解析会把 fastmcp-slim 作为传递依赖带入，
    # 其文件覆盖 fastmcp==2.7.0 导致 `ImportError: CreateMessageResultWithTools`。
    # 移除 slim 并强制重装干净的 2.7.0（与 websearch 锁定的 mcp==1.9.3 配套）。
    && (pip uninstall -y fastmcp-slim || true) \
    && pip install --no-cache-dir --no-deps --force-reinstall "fastmcp==2.7.0" \
    && python -c "from fastmcp import FastMCP; import pytz; print('build-time import check OK')"

# 运行时仍通过挂载代码目录，保持开发效率
CMD ["bash", "-lc", "/app/scripts/start_mcp_pipe.sh"]
