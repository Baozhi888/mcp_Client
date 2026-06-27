#!/bin/bash

# MCP 服务管理脚本
# 确定脚本所在目录，供后续路径引用
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"


# 设置错误处理
set -e
trap 'handle_error $? $LINENO' ERR

# Redis配置
REDIS_CONTAINER_NAME="mcp-redis"
REDIS_PORT="6380"
REDIS_PASSWORD="${MCP_REDIS_PASSWORD:-change_this_to_a_strong_password}"  # 如需密码请通过环境变量设置
REDIS_DATA_DIR="$SCRIPT_DIR/redis-data"

# 错误处理函数
handle_error() {
    local exit_code=$1
    local line_number=$2
    echo -e "${RED}错误：命令执行失败 (行号: $line_number, 退出码: $exit_code)${NC}"
    exit $exit_code
}

# 日志函数
log() {
    local level=$1
    local message=$2
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "[$timestamp] [$level] $message"
}

# 检查Docker是否可用
check_docker() {
    if ! command -v docker &> /dev/null; then
        log "ERROR" "未找到 Docker，请先安装 Docker"
        exit 1
    fi

    if ! docker info &> /dev/null; then
        log "ERROR" "Docker 服务未运行，请启动 Docker 服务"
        exit 1
    fi
}

# 启动Redis容器
start_redis() {
    log "INFO" "启动 Redis 容器..."

    # 检查Docker
    check_docker

    # 检查容器是否已存在
    if docker ps -a --format "table {{.Names}}" | grep -q "^${REDIS_CONTAINER_NAME}$"; then
        if docker ps --format "table {{.Names}}" | grep -q "^${REDIS_CONTAINER_NAME}$"; then
            log "INFO" "Redis 容器已在运行"
            return 0
        else
            log "INFO" "启动已存在的 Redis 容器"
            docker start "$REDIS_CONTAINER_NAME"
            return 0
        fi
    fi

    # 创建数据目录
    mkdir -p "$REDIS_DATA_DIR"

    # 构建Redis启动命令
    local redis_cmd="redis-server --appendonly yes --port 6379"
    if [ -n "$REDIS_PASSWORD" ]; then
        redis_cmd="$redis_cmd --requirepass $REDIS_PASSWORD"
    fi

    # 启动新的Redis容器
    docker run -d \
        --name "$REDIS_CONTAINER_NAME" \
        --restart unless-stopped \
        -p "${REDIS_PORT}:6379" \
        -v "${REDIS_DATA_DIR}:/data" \
        redis:7-alpine \
        sh -c "$redis_cmd"

    # 等待Redis启动
    local retry=0
    while [ $retry -lt 10 ]; do
        if docker exec "$REDIS_CONTAINER_NAME" redis-cli ${REDIS_PASSWORD:+-a "$REDIS_PASSWORD"} ping &> /dev/null; then
            log "INFO" "Redis 容器启动成功，端口: $REDIS_PORT"
            return 0
        fi
        sleep 1
        retry=$((retry + 1))
    done

    log "ERROR" "Redis 容器启动失败"
    return 1
}

# 停止Redis容器
stop_redis() {
    log "INFO" "停止 Redis 容器..."

    if docker ps --format "table {{.Names}}" | grep -q "^${REDIS_CONTAINER_NAME}$"; then
        docker stop "$REDIS_CONTAINER_NAME"
        log "INFO" "Redis 容器已停止"
    else
        log "WARN" "Redis 容器未运行"
    fi
}

# 检查Redis状态
check_redis_status() {
    log "INFO" "检查 Redis 状态..."

    if ! command -v docker &> /dev/null; then
        log "WARN" "Docker 未安装，无法检查 Redis 状态"
        return 1
    fi

    if docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -q "^${REDIS_CONTAINER_NAME}"; then
        log "INFO" "Redis 容器正在运行"
        docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep "^${REDIS_CONTAINER_NAME}"

        # 测试Redis连接
        if docker exec "$REDIS_CONTAINER_NAME" redis-cli ${REDIS_PASSWORD:+-a "$REDIS_PASSWORD"} ping &> /dev/null; then
            log "INFO" "Redis 服务响应正常"
        else
            log "WARN" "Redis 容器运行但服务无响应"
        fi
    else
        log "WARN" "Redis 容器未运行"
        return 1
    fi
}

# 重启Redis容器
restart_redis() {
    log "INFO" "重启 Redis 容器..."
    stop_redis
    sleep 2
    start_redis
}

# 查看Redis日志
view_redis_logs() {
    log "INFO" "查看 Redis 日志..."

    if ! docker ps --format "table {{.Names}}" | grep -q "^${REDIS_CONTAINER_NAME}$"; then
        log "ERROR" "Redis 容器未运行"
        return 1
    fi

    echo -e "${GREEN}显示 Redis 容器日志${NC}"
    echo -e "${YELLOW}按 Ctrl+C 退出日志查看${NC}"
    echo "----------------------------------------"
    docker logs -f "$REDIS_CONTAINER_NAME"
}

# 清理Redis数据
cleanup_redis() {
    log "WARN" "清理 Redis 数据..."
    read -p "确定要清理所有 Redis 数据吗？(y/N): " confirm

    if [[ $confirm == [yY] || $confirm == [yY][eE][sS] ]]; then
        stop_redis
        docker rm -f "$REDIS_CONTAINER_NAME" 2>/dev/null || true
        rm -rf "$REDIS_DATA_DIR"
        log "INFO" "Redis 数据已清理"
    else
        log "INFO" "取消清理操作"
    fi
}

# 检查并安装依赖（兼容 WSL/Windows 混合环境）
check_dependencies() {
    log "INFO" "检查 Python 依赖..."

    # 检查 pip 是否可用
    if ! command -v pip3 &> /dev/null; then
        log "ERROR" "未找到 pip3，请先安装 Python3 和 pip3"
        exit 1
    fi

    # 检查虚拟环境
    if [ ! -d "$SCRIPT_DIR/.myenv" ]; then
        log "INFO" "创建 Python 虚拟环境..."
        python3 -m venv "$SCRIPT_DIR/.myenv"
    fi

    # 激活虚拟环境（优先使用 bash 激活脚本）
    if [ -f "$SCRIPT_DIR/.myenv/bin/activate" ]; then
        source "$SCRIPT_DIR/.myenv/bin/activate"
    elif [ -f "$SCRIPT_DIR/.myenv/Scripts/activate" ]; then
        # Git Bash/WSL 下也可用的激活脚本
        source "$SCRIPT_DIR/.myenv/Scripts/activate"
    else
        log "WARNING" "未找到虚拟环境激活脚本，继续执行但可能会有问题"
    fi

    # 检查 requirements.txt 是否存在
    REQ_FILE_POSIX="$SCRIPT_DIR/requirements.txt"
    if [ ! -f "$REQ_FILE_POSIX" ]; then
        log "ERROR" "未找到 requirements.txt 文件: $REQ_FILE_POSIX"
        exit 1
    fi

    # 安装/更新依赖（如使用 Windows Python.exe，则转换路径）
    log "INFO" "安装/更新 Python 依赖..."
    if [[ "$PYTHON_EXEC" == *.exe ]] && command -v wslpath >/dev/null 2>&1; then
        REQ_FILE_WIN=$(wslpath -w "$REQ_FILE_POSIX")
        "$PYTHON_EXEC" -m pip install -r "$REQ_FILE_WIN"
    else
        "$PYTHON_EXEC" -m pip install -r "$REQ_FILE_POSIX"
    fi

    # 检查关键依赖（确保使用同一 Python 解释器）
    if ! "$PYTHON_EXEC" -c "import dotenv" &> /dev/null; then
        log "ERROR" "安装依赖失败，请检查 pip 安装日志"
        exit 1
    fi

    log "INFO" "依赖检查完成"
}

# 加载环境变量（安全方式，支持包含空格和特殊字符的值）
if [ -f .env ]; then
    # 使用 set -a 自动导出变量，source 加载 .env
    set -a
    # shellcheck disable=SC1091
    source .env 2>/dev/null || true
    set +a
fi

# 默认日志级别
LOG_LEVEL=${LOG_LEVEL:-INFO}

# 服务名称
SERVICE_NAME="MCP Service"
SCRIPT_NAME="mcp_pipe.py"
LOG_DIR="logs"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Python 可执行文件（使用虚拟环境 Python）
# Windows系统使用Scripts目录，Linux/Mac使用bin目录
if [ -f "$SCRIPT_DIR/.myenv/Scripts/python.exe" ]; then
    PYTHON_EXEC="$SCRIPT_DIR/.myenv/Scripts/python.exe"
elif [ -f "$SCRIPT_DIR/.myenv/bin/python3" ]; then
    PYTHON_EXEC="$SCRIPT_DIR/.myenv/bin/python3"
else
    log "ERROR" "未找到虚拟环境 Python 可执行文件，请检查 .myenv 路径"
    exit 1
fi

# 检查是否以 root 权限运行（Windows环境跳过此检查）
check_root() {
    # 在Windows环境下跳过root权限检查
    # 检查是否在WSL或Windows环境中运行
    if [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]] || [[ "$(uname -s)" == MINGW* ]] || [[ -n "$WSL_DISTRO_NAME" ]] || [[ "$(uname -r)" == *Microsoft* ]] || [[ "$(uname -r)" == *microsoft* ]]; then
        return 0
    fi

    if [ "$EUID" -ne 0 ]; then
        log "ERROR" "此脚本必须以 root 权限运行，请使用 sudo"
        exit 1
    fi
}

# 检查服务状态
check_status() {
    log "INFO" "检查 $SERVICE_NAME 状态..."
    if pgrep -f "$PYTHON_EXEC $SCRIPT_NAME" > /dev/null; then
        log "INFO" "服务正在运行"
        ps aux | grep "$PYTHON_EXEC $SCRIPT_NAME" | grep -v grep
    else
        log "WARN" "服务未运行"
    fi
}

# 启动服务
start_service() {
    log "INFO" "启动 $SERVICE_NAME..."
    if pgrep -f "$PYTHON_EXEC $SCRIPT_NAME" > /dev/null; then
        log "WARN" "服务已在运行"
        return 1
    fi

    # 首先启动Redis
    log "INFO" "启动 Redis 服务..."
    start_redis

    # 检查依赖
    check_dependencies

    # 设置Redis环境变量
    export MCP_REDIS_HOST="localhost"
    export MCP_REDIS_PORT="$REDIS_PORT"
    export MCP_REDIS_DB="1"
    if [ -n "$REDIS_PASSWORD" ]; then
        export MCP_REDIS_PASSWORD="$REDIS_PASSWORD"
    fi

    # 确保日志目录存在
    mkdir -p "$LOG_DIR"
    chmod 755 "$LOG_DIR"

    # 启动所有MCP服务通过mcp_pipe.py统一管理
    # 使用环境变量MCP_SCRIPTS，如果未设置则使用默认值
    local scripts="${MCP_SCRIPTS:-calculator.py notepad_mcp/notepad_mcp_fixed.py xiaozhi-websearch/websearch_optimized.py}"
    
    # 启动服务
    LOG_FILE="$LOG_DIR/mcp_service_$(date +%Y%m%d_%H%M%S).log"
    LOG_LEVEL=$LOG_LEVEL nohup "$PYTHON_EXEC" "$SCRIPT_NAME" $scripts >> "$LOG_FILE" 2>&1 &

    # 等待主服务启动
    local retry=0
    while [ $retry -lt 5 ]; do
        if pgrep -f "$PYTHON_EXEC $SCRIPT_NAME" > /dev/null; then
            log "INFO" "主服务启动成功，日志输出到 $LOG_FILE"
            return 0
        fi
        sleep 1
        retry=$((retry + 1))
    done

    log "ERROR" "主服务启动失败，请检查日志文件 $LOG_FILE"
    tail -n 10 "$LOG_FILE"
    return 1
}

# 停止服务
stop_service() {
    log "INFO" "停止 $SERVICE_NAME..."
    if pkill -f "$PYTHON_EXEC $SCRIPT_NAME"; then
        log "INFO" "服务已停止"
    else
        log "WARN" "服务未运行"
    fi

    # 询问是否停止Redis
    read -p "是否同时停止 Redis 容器？(y/N): " stop_redis_confirm
    if [[ $stop_redis_confirm == [yY] || $stop_redis_confirm == [yY][eE][sS] ]]; then
        stop_redis
    fi
}

# 重启服务
restart_service() {
    log "INFO" "重启 $SERVICE_NAME..."
    stop_service
    sleep 2
    start_service
}

# 检查服务状态（包含Redis）
check_full_status() {
    log "INFO" "检查完整服务状态..."

    # 检查MCP服务状态
    check_status

    echo ""

    # 检查Redis状态
    check_redis_status
}

# 查看日志
view_logs() {
    log "INFO" "查看服务日志..."
    if [ ! -d "$LOG_DIR" ]; then
        log "ERROR" "日志目录不存在"
        return 1
    fi

    # 显示所有可用的日志文件
    echo -e "${YELLOW}可用的日志文件：${NC}"
    ls -lh "$LOG_DIR"/mcp_service_*.log 2>/dev/null | sort -r

    # 使用最新的日志文件
    latest_log=$(ls -t "$LOG_DIR"/mcp_service_*.log 2>/dev/null | head -n1)
    if [ -n "$latest_log" ]; then
        echo -e "${GREEN}显示最新日志文件: $latest_log${NC}"
        echo -e "${YELLOW}按 Ctrl+C 退出日志查看${NC}"
        echo "----------------------------------------"
        tail -f "$latest_log"
    else
        log "ERROR" "未找到日志文件"
        return 1
    fi
}

# 查看特定日志
view_specific_log() {
    local log_file="$1"
    if [ ! -f "$log_file" ]; then
        log "ERROR" "日志文件不存在: $log_file"
        return 1
    fi

    echo -e "${GREEN}显示日志文件: $log_file${NC}"
    echo -e "${YELLOW}按 Ctrl+C 退出日志查看${NC}"
    echo "----------------------------------------"
    tail -f "$log_file"
}

# 清理旧日志
cleanup_logs() {
    log "INFO" "清理旧日志文件..."
    find "$LOG_DIR" -name "mcp_service_*.log" -mtime +7 -delete
}

# 查看行情服务日志
view_market_logs() {
    log "INFO" "查看行情服务日志..."
    if [ ! -d "$LOG_DIR" ]; then
        log "ERROR" "日志目录不存在"
        return 1
    fi
    echo -e "${YELLOW}可用的行情日志文件：${NC}"
    ls -lh "$LOG_DIR"/market_mcp_*.log 2>/dev/null | sort -r
    latest_log=$(ls -t "$LOG_DIR"/market_mcp_*.log 2>/dev/null | head -n1)
    if [ -n "$latest_log" ]; then
        echo -e "${GREEN}显示最新行情日志文件: $latest_log${NC}"
        echo -e "${YELLOW}按 Ctrl+C 退出日志查看${NC}"
        echo "----------------------------------------"
        tail -f "$latest_log"
    else
        log "ERROR" "未找到行情日志文件"
        return 1
    fi
}

# 显示帮助信息
show_help() {
    echo "使用方法: $0 {start|stop|restart|status|logs|marketlogs|log <文件名>|cleanup|redis-start|redis-stop|redis-restart|redis-status|redis-logs|redis-cleanup|help}"
    echo ""
    echo "MCP服务命令:"
    echo "  start   - 启动MCP服务（自动启动Redis）"
    echo "  stop    - 停止MCP服务（可选择停止Redis）"
    echo "  restart - 重启MCP服务"
    echo "  status  - 查看MCP服务状态"
    echo "  logs    - 查看最新MCP日志"
    echo "  marketlogs - 查看最新行情日志"
    echo "  log <文件名> - 查看指定日志文件"
    echo "  cleanup - 清理旧日志文件"
    echo ""
    echo "Redis服务命令:"
    echo "  redis-start   - 启动Redis容器"
    echo "  redis-stop    - 停止Redis容器"
    echo "  redis-restart - 重启Redis容器"
    echo "  redis-status  - 查看Redis状态"
    echo "  redis-logs    - 查看Redis日志"
    echo "  redis-cleanup - 清理Redis数据"
    echo ""
    echo "其他命令:"
    echo "  fullstatus - 查看完整服务状态（MCP + Redis）"
    echo "  help       - 显示此帮助信息"
    echo ""
    echo "Redis配置:"
    echo "  容器名称: $REDIS_CONTAINER_NAME"
    echo "  端口: $REDIS_PORT"
    echo "  数据目录: $REDIS_DATA_DIR"
}

# 主命令处理
case "$1" in
    start)
        check_root
        start_service
        ;;
    stop)
        check_root
        stop_service
        ;;
    restart)
        check_root
        restart_service
        ;;
    status)
        check_status
        ;;
    fullstatus)
        check_full_status
        ;;
    logs)
        view_logs
        ;;
    marketlogs)
        view_market_logs
        ;;
    log)
        if [ -z "$2" ]; then
            log "ERROR" "请指定日志文件名"
            show_help
            exit 1
        fi
        view_specific_log "$2"
        ;;
    cleanup)
        cleanup_logs
        ;;
    redis-start)
        start_redis
        ;;
    redis-stop)
        stop_redis
        ;;
    redis-restart)
        restart_redis
        ;;
    redis-status)
        check_redis_status
        ;;
    redis-logs)
        view_redis_logs
        ;;
    redis-cleanup)
        cleanup_redis
        ;;
    help|*)
        show_help
        ;;
esac

exit 0
