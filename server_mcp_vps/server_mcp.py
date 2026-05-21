#!/usr/bin/env python3
"""
VPS MCP Server Management Service
=================================
模块化VPS服务器管理工具集

功能模块:
- system: 系统信息、资源监控、进程管理、异步任务
- service: 服务管理、包管理、Docker操作
- network: 网络信息、端口检查、防火墙、DNS、诊断
- files: 文件管理、磁盘使用、日志查看
- security: 安全监控、用户管理、SSH密钥
- backup: 备份创建、恢复、列表

使用方法:
    python server_mcp.py
"""

import sys

# 导入核心模块
from core import mcp, logger, CURRENT_USER, CURRENT_UID, USER_HOME, LLM_LOGS_DIR

# 导入并注册所有工具模块
from tools import system, service, network, files, security, backup


def main():
    """主入口函数"""
    logger.info("=" * 50)
    logger.info("VPS MCP Server Management Service Starting...")
    logger.info("=" * 50)
    logger.info(f"Service: {mcp.name}")
    logger.info(f"User: {CURRENT_USER} (UID: {CURRENT_UID})")
    logger.info(f"Home: {USER_HOME}")
    logger.info(f"Logs: {LLM_LOGS_DIR}")
    logger.info("-" * 50)

    # 统计已注册的工具数量
    tool_modules = ["system", "service", "network", "files", "security", "backup"]
    logger.info(f"Loaded modules: {', '.join(tool_modules)}")
    logger.info("MCP service ready for commands...")
    logger.info("=" * 50)

    try:
        mcp.run(transport="stdio")
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down...")
    except Exception as e:
        logger.error(f"Service error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        logger.info("VPS MCP Service stopped")


if __name__ == "__main__":
    main()
