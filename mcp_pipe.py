"""
MCP Pipe Service - MCP服务通信管道
================================
Version: 0.2.0
Type: Communication Service
Priority: Critical
Author: MCP Team
Created: 2024
Requires: WebSocket Support

功能描述:
---------
此服务作为MCP系统的核心通信组件，负责管理和协调多个MCP服务之间
的通信。提供可靠的双向数据传输、自动重连、错误处理等功能，确保
MCP服务之间的稳定通信。

主要特性:
--------
1. 双向数据管道
2. 多服务并发支持
3. 自动重连机制
4. 错误恢复
5. 日志记录
6. 信号处理
7. 环境变量配置
8. 安全通信

配置要求:
--------
- Python >= 3.7
- WebSocket支持
- 环境变量:
  * MCP_ENDPOINT: WebSocket服务端点
  * LOG_LEVEL: 日志级别

通信协议:
--------
- 输入: 标准输入流
- 输出: WebSocket消息
- 格式: UTF-8编码文本

重连策略:
--------
- 初始等待时间: 1秒
- 最大等待时间: 60秒
- 指数退避算法
- 随机抖动

使用方法:
--------
python mcp_pipe.py <mcp_script1> [<mcp_script2> ...]

参数说明:
--------
- mcp_script: MCP服务脚本路径
- 支持同时运行多个服务

示例:
----
1. 单服务:
   python mcp_pipe.py notepad_mcp/notepad_mcp_fixed.py

2. 多服务:
   python mcp_pipe.py calculator.py notepad_mcp/notepad_mcp_fixed.py xiaozhi-websearch/websearch_optimized.py server_mcp_vps/server_mcp.py

注意事项:
--------
1. 确保环境变量正确设置
2. 所有脚本需要实现标准IO接口
3. 建议使用supervisor管理
4. 注意日志文件轮转

相关服务:
--------
- MCP_LOG: 日志服务
- 所有使用此管道的MCP服务
"""

import asyncio
import websockets
import subprocess
import logging
import os
import signal
import sys
import random
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.environ.get('LOG_LEVEL', 'INFO').upper(), logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('MCP_PIPE')

# Reconnection settings
INITIAL_BACKOFF = 2  # Initial wait time in seconds
MAX_BACKOFF = 120  # Maximum wait time in seconds
MAX_RECONNECT_ATTEMPTS = 50  # Maximum reconnection attempts before giving up (increased for stability)

# 超时配置（可通过环境变量覆盖）
WS_OPEN_TIMEOUT = int(os.environ.get('MCP_WS_OPEN_TIMEOUT', 30))  # WebSocket 连接超时
WS_PING_INTERVAL = int(os.environ.get('MCP_WS_PING_INTERVAL', 30))  # Ping 间隔
WS_PING_TIMEOUT = int(os.environ.get('MCP_WS_PING_TIMEOUT', 120))  # Ping 超时（增加到120秒，适应行情查询）
STARTUP_DELAY = float(os.environ.get('MCP_STARTUP_DELAY', 0))  # 启动延迟（秒）

# 需要额外启动延迟的服务列表（可通过环境变量配置）
HEAVY_SERVICES = os.environ.get('MCP_HEAVY_SERVICES', 'aktools').split(',')
HEAVY_SERVICE_DELAY = float(os.environ.get('MCP_HEAVY_SERVICE_DELAY', 3))  # 重型服务额外启动延迟


async def pipe_websocket_to_process(websocket, process, script_name):
    """Read data from WebSocket and write to process stdin"""
    try:
        while True:
            message = await websocket.recv()
            logger.debug(f"[{script_name}] << {message[:120]}...")
            if isinstance(message, bytes):
                message = message.decode('utf-8')
            process.stdin.write(message + '\n')
            process.stdin.flush()
    except Exception as e:
        logger.error(f"[{script_name}] Error in WebSocket to process pipe: {e}")
        raise
    finally:
        if not process.stdin.closed:
            process.stdin.close()


async def pipe_process_to_websocket(process, websocket, script_name):
    """Read data from process stdout and send to WebSocket"""
    try:
        while True:
            data = await asyncio.get_event_loop().run_in_executor(
                None, process.stdout.readline
            )
            if not data:
                logger.info(f"[{script_name}] Process has ended output")
                break
            if isinstance(data, bytes):
                data = data.decode('utf-8', errors='replace')
            logger.debug(f"[{script_name}] >> {data[:120]}...")
            await websocket.send(data)
    except Exception as e:
        logger.error(f"[{script_name}] Error in process to WebSocket pipe: {e}")
        raise


async def pipe_process_stderr_to_terminal(process, script_name):
    """Read data from process stderr and print to terminal"""
    try:
        while True:
            data = await asyncio.get_event_loop().run_in_executor(
                None, process.stderr.readline
            )
            if not data:
                logger.info(f"[{script_name}] Process has ended stderr output")
                break
            if isinstance(data, bytes):
                data = data.decode('utf-8', errors='replace')
            sys.stderr.write(f"[{script_name}][stderr] {data}")
            sys.stderr.flush()
    except Exception as e:
        logger.error(f"[{script_name}] Error in process stderr pipe: {e}")
        raise


async def connect_with_retry_for_script(uri, mcp_script):
    """Connect to WebSocket server with retry mechanism for one MCP script"""
    reconnect_attempt = 0
    backoff = INITIAL_BACKOFF
    consecutive_failures = 0
    max_consecutive_failures = 5

    while True:
        try:
            if reconnect_attempt > 0:
                # 增加随机抖动避免同步重连
                jitter = random.uniform(0.5, 1.5)
                wait_time = min(backoff * jitter, MAX_BACKOFF)
                logger.info(f"[{mcp_script}] Waiting {wait_time:.2f}s before reconnection attempt {reconnect_attempt}...")
                await asyncio.sleep(wait_time)

            await connect_to_server(uri, mcp_script)

            # 连接成功，重置计数器
            reconnect_attempt = 0
            backoff = INITIAL_BACKOFF
            consecutive_failures = 0

        except Exception as e:
            reconnect_attempt += 1
            consecutive_failures += 1
            
            # Check if we've exceeded maximum reconnection attempts
            if reconnect_attempt >= MAX_RECONNECT_ATTEMPTS:
                logger.error(f"[{mcp_script}] Maximum reconnection attempts ({MAX_RECONNECT_ATTEMPTS}) exceeded. Entering long sleep mode.")
                # 进入长睡眠模式，避免频繁重连
                await asyncio.sleep(300)  # 5分钟长睡眠
                reconnect_attempt = 0  # 重置计数器，给服务恢复机会
                continue
            
            # 如果连续失败次数过多，增加额外延迟
            if consecutive_failures >= max_consecutive_failures:
                logger.warning(f"[{mcp_script}] Too many consecutive failures ({consecutive_failures}), adding extra delay")
                await asyncio.sleep(30)  # 额外30秒延迟
            
            logger.warning(f"[{mcp_script}] Connection closed (attempt {reconnect_attempt}): {e}")
            backoff = min(backoff * 1.5, MAX_BACKOFF)  # 减缓退避速度


async def connect_to_server(uri, mcp_script):
    """Connect to WebSocket server and establish bidirectional communication with `mcp_script`"""
    logger.info(f"[{mcp_script}] Connecting to WebSocket server...")

    # 检查是否需要额外启动延迟（重型服务如aktools）
    is_heavy_service = any(svc in mcp_script for svc in HEAVY_SERVICES if svc.strip())
    if is_heavy_service:
        logger.info(f"[{mcp_script}] 检测到重型服务，增加 {HEAVY_SERVICE_DELAY}s 启动延迟...")
        await asyncio.sleep(HEAVY_SERVICE_DELAY)
    elif STARTUP_DELAY > 0:
        await asyncio.sleep(STARTUP_DELAY)

    try:
        async with websockets.connect(
            uri,
            open_timeout=WS_OPEN_TIMEOUT,
            ping_interval=WS_PING_INTERVAL,
            ping_timeout=WS_PING_TIMEOUT,
            close_timeout=5,
            max_queue=1024
        ) as websocket:
            logger.info(f"[{mcp_script}] Successfully connected to WebSocket server")

            # Normalize script path for cross-platform compatibility
            normalized_mcp_script = mcp_script.replace("\\", "/")

            # Start mcp_script process
            process = subprocess.Popen(
                [sys.executable, normalized_mcp_script],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8'
            )
            logger.info(f"[{mcp_script}] Started process PID: {process.pid}")

            try:
                await asyncio.gather(
                    pipe_websocket_to_process(websocket, process, mcp_script),
                    pipe_process_to_websocket(process, websocket, mcp_script),
                    pipe_process_stderr_to_terminal(process, mcp_script),
                )
            finally:
                logger.warning(f"[{mcp_script}] MCP子进程异常或退出，准备自动重启...")
                try:
                    process.terminate()
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                logger.info(f"[{mcp_script}] Process terminated")
                
    except websockets.exceptions.ConnectionClosed as e:
        logger.warning(f"[{mcp_script}] WebSocket connection closed: {e}")
        raise
    except websockets.exceptions.InvalidStatusCode as e:
        logger.error(f"[{mcp_script}] WebSocket connection failed with status code {e.status_code}")
        raise
    except Exception as e:
        logger.error(f"[{mcp_script}] WebSocket connection error: {e}")
        raise


async def main(mcp_scripts, endpoint_url):
    """管理多个 MCP 脚本并发运行"""
    tasks = []
    for script in mcp_scripts:
        tasks.append(asyncio.create_task(connect_with_retry_for_script(endpoint_url, script)))

    # 等待所有任务完成（正常情况下是不会退出的，除非所有脚本都退出或异常）
    await asyncio.gather(*tasks)


def signal_handler(sig, frame):
    logger.info("Received interrupt signal, shutting down...")
    sys.exit(0)


if __name__ == "__main__":
    # 注册 SIGINT 信号处理
    signal.signal(signal.SIGINT, signal_handler)

    # 支持从命令行参数或环境变量读取MCP脚本列表
    if len(sys.argv) < 2:
        # 尝试从环境变量读取
        env_scripts = os.environ.get('MCP_SCRIPTS', '')
        if env_scripts:
            mcp_scripts = env_scripts.split()
            logger.info(f"Loading MCP scripts from environment variable: {mcp_scripts}")
        else:
            logger.error("Usage: python mcp_pipe.py <mcp_script1.py> [<mcp_script2.py> ...]")
            logger.error("Or set MCP_SCRIPTS environment variable (space-separated)")
            sys.exit(1)
    else:
        mcp_scripts = sys.argv[1:]
        logger.info(f"Loading MCP scripts from command line: {mcp_scripts}")

    endpoint_url = os.environ.get('MCP_ENDPOINT')
    if not endpoint_url:
        logger.error("Please set the MCP_ENDPOINT environment variable")
        sys.exit(1)

    try:
        asyncio.run(main(mcp_scripts, endpoint_url))
    except KeyboardInterrupt:
        logger.info("Program interrupted by user")
    except Exception as e:
        logger.error(f"Program execution error: {e}")
