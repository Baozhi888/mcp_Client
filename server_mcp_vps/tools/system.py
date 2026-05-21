"""
VPS MCP System Tools - 系统信息与监控
包含：系统信息、资源指标、性能检查、进程管理
"""

import os
import time
from typing import Dict, Any, Optional

import psutil

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import (
    mcp, logger, execute_command, build_response, get_beijing_time,
    task_manager, CURRENT_USER, CURRENT_UID, USER_HOME, ALLOWED_SERVICES
)


def register_system_tools(mcp_instance):
    """注册系统相关工具到MCP实例"""
    pass  # 工具通过装饰器自动注册


@mcp.tool()
def vps_system_info(server_name: str) -> Dict[str, Any]:
    """
    获取VPS系统信息（OS、CPU、内存、磁盘、运行时间）
    Args: server_name - 服务器标识名
    """
    context = f"sysinfo_{server_name}"
    logger.info(f"Getting system info for {server_name}")

    commands = {
        "os_info": "cat /etc/os-release 2>/dev/null || ver",
        "hostname": "hostname",
        "kernel": "uname -r 2>/dev/null || ver",
        "uptime": "uptime",
        "user_info": "whoami && id"
    }

    info = {}
    for key, cmd in commands.items():
        result = execute_command(cmd, f"{context}_{key}")
        info[key] = result["output"] if result["success"] else f"Error: {result.get('error', 'Unknown')}"

    return build_response(True, server_name=server_name, info=info)


@mcp.tool()
def vps_system_metrics(server_name: str) -> Dict[str, Any]:
    """
    获取实时系统资源指标（CPU、内存、磁盘、网络）
    Args: server_name - 服务器标识名
    """
    logger.info(f"Getting metrics for {server_name}")

    try:
        load_avg = os.getloadavg() if hasattr(os, 'getloadavg') else None
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        metrics = {
            "cpu": {
                "percent": psutil.cpu_percent(interval=0.5),
                "count": psutil.cpu_count(),
                "load_avg": load_avg
            },
            "memory": {
                "total_gb": round(mem.total / (1024**3), 2),
                "available_gb": round(mem.available / (1024**3), 2),
                "percent": mem.percent
            },
            "disk": {
                "total_gb": round(disk.total / (1024**3), 2),
                "free_gb": round(disk.free / (1024**3), 2),
                "percent": disk.percent
            },
            "network": {
                "connections": len(psutil.net_connections(kind='inet'))
            }
        }
        return build_response(True, server_name=server_name, metrics=metrics)
    except Exception as e:
        return build_response(False, error=str(e), code=1003)


@mcp.tool()
def vps_performance_check(server_name: str, duration: int = 3) -> Dict[str, Any]:
    """
    综合性能检查（CPU采样、内存、磁盘IO、网络IO、Top进程）
    Args: server_name - 服务器标识名, duration - 采样时长(1-30秒)
    """
    logger.info(f"Performance check for {server_name}, duration={duration}s")
    duration = max(1, min(int(duration), 30))

    perf = {}

    # CPU采样
    try:
        cpu_start = psutil.cpu_percent()
        time.sleep(duration)
        cpu_end = psutil.cpu_percent()
        perf["cpu"] = {
            "usage_percent": round((cpu_start + cpu_end) / 2, 2),
            "core_count": psutil.cpu_count(),
            "load_avg": os.getloadavg() if hasattr(os, 'getloadavg') else None
        }
    except Exception as e:
        perf["cpu"] = {"error": str(e)}

    # 内存
    try:
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        perf["memory"] = {
            "used_percent": mem.percent,
            "swap_percent": swap.percent
        }
    except Exception as e:
        perf["memory"] = {"error": str(e)}

    # Top进程
    try:
        procs = []
        for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
            try:
                info = p.info
                if info['cpu_percent'] > 1 or info['memory_percent'] > 1:
                    procs.append(info)
            except:
                pass
        procs.sort(key=lambda x: x['cpu_percent'], reverse=True)
        perf["top_processes"] = procs[:10]
    except Exception as e:
        perf["top_processes"] = {"error": str(e)}

    return build_response(True, server_name=server_name, performance=perf, duration=duration)


@mcp.tool()
def vps_process_list(server_name: str, filter_pattern: str = None, limit: int = 20) -> Dict[str, Any]:
    """
    列出运行中的进程
    Args: server_name, filter_pattern - 过滤关键词, limit - 最大返回数量
    """
    context = f"proclist_{server_name}"
    logger.info(f"Listing processes, filter={filter_pattern}, limit={limit}")

    cmd = "ps aux"
    if filter_pattern:
        safe = ''.join(c for c in filter_pattern if c.isalnum() or c in '.-_')
        if safe:
            cmd += f" | grep '{safe}' | grep -v grep"
    cmd += f" | head -n {max(1, min(limit, 100))}"

    result = execute_command(cmd, context)

    if result["success"] and result["output"]:
        procs = []
        for line in result["output"].splitlines():
            parts = line.split(maxsplit=10)
            if len(parts) >= 11 and not parts[0].lower() == "user":
                procs.append({
                    "user": parts[0], "pid": parts[1], "cpu": parts[2],
                    "mem": parts[3], "command": parts[10]
                })
        return build_response(True, server_name=server_name, processes=procs, count=len(procs))

    return build_response(False, error=result.get("error", "No processes found"), code=4002)


@mcp.tool()
def vps_process_manage(server_name: str, pid: int, action: str) -> Dict[str, Any]:
    """
    管理进程（终止/杀死/暂停/恢复）
    Args: server_name, pid - 进程ID, action - terminate|kill|suspend|resume
    """
    context = f"procmgr_{server_name}"
    signals = {"terminate": "TERM", "kill": "KILL", "suspend": "STOP", "resume": "CONT"}

    if action not in signals:
        return build_response(False, error=f"Invalid action. Use: {list(signals.keys())}", code=4101)

    try:
        pid = int(pid)
    except ValueError:
        return build_response(False, error=f"Invalid PID: {pid}", code=4102)

    # 检查进程是否存在
    check = execute_command(f"kill -0 {pid}", f"{context}_check")
    if not check["success"]:
        return build_response(False, error=f"Process {pid} not found or no permission", code=4103)

    result = execute_command(f"kill -{signals[action]} {pid}", context)

    if result["success"]:
        return build_response(True, server_name=server_name, message=f"Signal {signals[action]} sent to PID {pid}")

    return build_response(False, error=result.get("error"), code=4104)


@mcp.tool()
def vps_task_status(server_name: str, task_id: str = None) -> Dict[str, Any]:
    """
    查询异步任务状态
    Args: server_name, task_id - 任务ID（空则列出全部）
    """
    logger.info(f"Task status check: {task_id or 'all'}")

    if task_id:
        info = task_manager.get_status(task_id)
        if not info:
            return build_response(False, error=f"Task {task_id} not found", code=8001)
        return build_response(True, server_name=server_name, task=info)

    tasks = task_manager.list_tasks()
    running = len([t for t in tasks if t["status"] == "running"])
    return build_response(True, server_name=server_name, tasks=tasks, total=len(tasks), running=running)


@mcp.tool()
def vps_task_cleanup(server_name: str, max_age_hours: int = 24) -> Dict[str, Any]:
    """
    清理已完成的旧任务记录
    Args: server_name, max_age_hours - 保留时长(1-168小时)
    """
    hours = max(1, min(int(max_age_hours), 168))
    cleaned = task_manager.cleanup(hours)
    return build_response(True, server_name=server_name, cleaned_tasks=cleaned, max_age_hours=hours)
