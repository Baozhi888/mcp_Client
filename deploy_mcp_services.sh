#!/bin/bash

# MCP服务部署脚本
# 用于在服务器上部署Redis跨服务通信的MCP服务

set -e

echo "🚀 开始部署MCP服务..."

REDIS_PASSWORD="${MCP_REDIS_PASSWORD:-change_this_to_a_strong_password}"

# 检查Docker和Docker Compose
if ! command -v docker &> /dev/null; then
    echo "❌ Docker未安装，请先安装Docker"
    exit 1
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "❌ Docker Compose未安装，请先安装Docker Compose"
    exit 1
fi

# 创建环境变量文件
if [ ! -f .env ]; then
    echo "📝 创建环境变量文件..."
    cat > .env << EOF
# Redis配置
MCP_REDIS_HOST=redis
MCP_REDIS_PORT=6379
MCP_REDIS_DB=1
MCP_REDIS_PASSWORD=$REDIS_PASSWORD

# API密钥 - 请填入你的实际密钥
GOOGLE_API_KEY=your_google_api_key_here
GOOGLE_CSE_ID=your_google_cse_id_here
TAVILY_API_KEY=your_tavily_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
NEWSAPI_KEY=your_newsapi_key_here

# 其他配置
PYTHONUNBUFFERED=1
EOF
    echo "✅ 环境变量文件已创建，请编辑 .env 文件填入你的API密钥"
fi

# 停止现有服务
echo "🛑 停止现有服务..."
docker-compose down 2>/dev/null || docker compose down 2>/dev/null || true

# 清理旧镜像（可选）
read -p "是否清理旧的Docker镜像？(y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "🧹 清理旧镜像..."
    docker system prune -f
fi

# 构建和启动服务
echo "🔨 构建和启动服务..."
if command -v docker-compose &> /dev/null; then
    docker-compose up -d --build
else
    docker compose up -d --build
fi

# 等待服务启动
echo "⏳ 等待服务启动..."
sleep 10

# 检查服务状态
echo "📊 检查服务状态..."
if command -v docker-compose &> /dev/null; then
    docker-compose ps
else
    docker compose ps
fi

# 检查Redis连接
echo "🔍 检查Redis连接..."
if docker exec mcp-redis redis-cli -a "$REDIS_PASSWORD" ping > /dev/null 2>&1; then
    echo "✅ Redis服务正常"
else
    echo "❌ Redis服务异常"
fi

# 显示日志
echo "📋 显示服务日志..."
if command -v docker-compose &> /dev/null; then
    docker-compose logs --tail=20
else
    docker compose logs --tail=20
fi

echo ""
echo "🎉 MCP服务部署完成!"
echo ""
echo "📋 服务信息:"
echo "   Redis: localhost:6380 (密码: $REDIS_PASSWORD)"
echo "   记事本MCP: mcp-notepad 容器"
echo "   搜索MCP: mcp-websearch 容器"
echo ""
echo "🔧 管理命令:"
echo "   查看日志: docker-compose logs -f [service_name]"
echo "   重启服务: docker-compose restart [service_name]"
echo "   停止服务: docker-compose down"
echo "   进入容器: docker exec -it [container_name] bash"
echo ""
echo "🧪 测试命令:"
echo "   测试Redis: docker exec mcp-redis redis-cli -a \"$REDIS_PASSWORD\" ping"
echo "   查看队列: docker exec mcp-redis redis-cli -a \"$REDIS_PASSWORD\" llen notepad_requests"
echo ""
echo "⚠️  注意事项:"
echo "   1. 请确保在 .env 文件中填入正确的API密钥"
echo "   2. 防火墙需要开放6380端口（如果需要外部访问Redis）"
echo "   3. 生产环境建议修改Redis密码"
