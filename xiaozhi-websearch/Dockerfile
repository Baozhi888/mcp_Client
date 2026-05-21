FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
# 如无本地扩展编译需求，可移除 gcc 以降低镜像构建时间与体积
#RUN apt-get update && apt-get install -y \
#    gcc \
#    && rm -rf /var/lib/apt/lists/*

# 复制requirements文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 创建缓存目录
# 复制自检脚本（依赖 redis 包）
COPY scripts/selfcheck.sh /app/scripts/selfcheck.sh
RUN chmod +x /app/scripts/selfcheck.sh

RUN mkdir -p /app/cache

# 设置环境变量
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# 暴露端口（如果需要）
EXPOSE 8000

# 启动命令
CMD ["python", "websearch_optimized.py"]
