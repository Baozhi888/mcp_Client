FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖（如需）
# 如无编译需求，可移除 gcc 以提高构建速度；保留 libmagic1 供 python-magic 使用
RUN apt-get update && apt-get install -y \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# 复制 requirements
COPY requirements.txt ./requirements.txt

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .
# 复制自检脚本（用于容器内连通性测试，可选）
COPY scripts/selfcheck.sh /app/scripts/selfcheck.sh
RUN chmod +x /app/scripts/selfcheck.sh


# 环境变量
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# 启动 notepad 服务（fixed 版本）
CMD ["python", "notepad_mcp_fixed.py"]

