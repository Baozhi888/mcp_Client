"""
VPS MCP Files Tools - 文件与日志管理
包含：文件操作、磁盘使用、日志查看、日志搜索
"""

import os
import re
import shlex
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Dict, Any, Optional

from core import mcp, logger, execute_command, build_response, USER_HOME


def register_files_tools(mcp_instance):
    """注册文件相关工具"""
    pass


# 受保护路径
PROTECTED_PATHS = [
    r'^/$',
    r'^/etc$', r'^/boot$', r'^/root$', r'^/usr/bin$', r'^/bin$', r'^/sbin$',
    r'^/etc/passwd$', r'^/etc/shadow$', r'^/etc/sudoers$'
]


def is_protected_path(path: str) -> bool:
    abs_path = os.path.abspath(path)
    return any(re.search(p, abs_path) for p in PROTECTED_PATHS)


def resolve_path(path: str) -> str:
    """解析路径（相对路径转为基于USER_HOME的绝对路径）"""
    if not os.path.isabs(path):
        return os.path.join(USER_HOME, path)
    return path


@mcp.tool()
def vps_file_manage(server_name: str, path: str, action: str, target: str = None) -> Dict[str, Any]:
    """
    文件和目录管理
    Args: server_name, path - 文件路径, action - list|create_dir|delete|move|chmod, target - 目标路径或权限
    """
    context = f"filemgr_{server_name}"
    valid = ["list", "create_dir", "delete", "move", "chmod"]

    if action not in valid:
        return build_response(False, error=f"Invalid action. Use: {valid}", code=9001)

    resolved = resolve_path(path)

    # 安全检查
    if action == "delete" and is_protected_path(resolved):
        return build_response(False, error=f"Cannot delete protected path: {resolved}", code=9005)

    if action == "list":
        cmd = f"ls -la {shlex.quote(resolved)}"
    elif action == "create_dir":
        cmd = f"mkdir -p {shlex.quote(resolved)}"
    elif action == "delete":
        cmd = f"rm -rf {shlex.quote(resolved)}"
    elif action == "move":
        if not target:
            return build_response(False, error="Target path required for move", code=9002)
        target_path = resolve_path(target)
        cmd = f"mv {shlex.quote(resolved)} {shlex.quote(target_path)}"
    elif action == "chmod":
        if not target:
            return build_response(False, error="Permission mode required for chmod", code=9002)
        if target == "777":
            return build_response(False, error="777 permissions not allowed", code=9007)
        if not re.match(r'^[0-7]{3,4}$', str(target)):
            return build_response(False, error="Invalid permission mode", code=9008)
        cmd = f"chmod {target} {shlex.quote(resolved)}"

    result = execute_command(cmd, context)

    if result["success"]:
        return build_response(True, server_name=server_name, action=action, path=resolved,
                             output=result["output"][:2000])

    return build_response(False, error=result.get("error"), code=9003)


@mcp.tool()
def vps_disk_usage(server_name: str, path: str = "/") -> Dict[str, Any]:
    """
    分析磁盘使用情况
    Args: server_name, path - 分析目录路径
    """
    context = f"diskusage_{server_name}"
    resolved = resolve_path(path)

    # 总大小
    quoted = shlex.quote(resolved)
    du_result = execute_command(f"du -sh {quoted} 2>/dev/null", f"{context}_total")
    total = du_result["output"].split()[0] if du_result["success"] else "Unknown"

    # Top 10 大文件/目录
    top_result = execute_command(f"du -h {quoted}/* 2>/dev/null | sort -rh | head -n 10", f"{context}_top")
    top_items = top_result["output"].splitlines() if top_result["success"] else []

    # 磁盘分区信息
    df_result = execute_command("df -h", f"{context}_df")

    return build_response(True, server_name=server_name, path=resolved, total_size=total,
                         top_items=top_items, disk_partitions=df_result.get("output", ""))


@mcp.tool()
def vps_log_view(server_name: str, log_file: str, lines: int = 100, filter_pattern: str = None) -> Dict[str, Any]:
    """
    查看日志文件
    Args: server_name, log_file - 日志文件路径, lines - 显示行数, filter_pattern - 过滤关键词
    """
    context = f"logview_{server_name}"
    resolved = resolve_path(log_file)

    if not os.path.exists(resolved):
        return build_response(False, error=f"Log file not found: {resolved}", code=5001)

    lines = max(1, min(int(lines), 5000))
    cmd = f"tail -n {lines} {shlex.quote(resolved)}"

    if filter_pattern:
        safe = ''.join(c for c in filter_pattern if c.isalnum() or c in '.-_ ')
        if safe:
            cmd += f" | grep --color=never {shlex.quote(safe)}"

    result = execute_command(cmd, context)

    if result["success"]:
        entries = result["output"].splitlines() if result["output"] else []
        return build_response(True, server_name=server_name, log_file=resolved,
                             entries=entries, count=len(entries))

    return build_response(False, error=result.get("error"), code=5002)


@mcp.tool()
def vps_log_search(server_name: str, log_file: str, pattern: str, context_lines: int = 0) -> Dict[str, Any]:
    """
    在日志文件中搜索
    Args: server_name, log_file - 日志路径, pattern - 搜索模式, context_lines - 上下文行数
    """
    ctx = f"logsearch_{server_name}"
    resolved = resolve_path(log_file)

    if not os.path.exists(resolved):
        return build_response(False, error=f"Log file not found: {resolved}", code=5004)

    context_lines = max(0, min(int(context_lines), 10))
    cmd = f"grep --color=never"
    if context_lines > 0:
        cmd += f" -C {context_lines}"
    cmd += f" {shlex.quote(pattern)} {shlex.quote(resolved)}"

    result = execute_command(cmd, ctx)

    if result["success"]:
        matches = result["output"].splitlines() if result["output"] else []
        return build_response(True, server_name=server_name, log_file=resolved, pattern=pattern,
                             matches=matches, count=len(matches))

    # grep返回1表示没有匹配
    if result["code"] == 1:
        return build_response(True, server_name=server_name, log_file=resolved, pattern=pattern,
                             matches=[], count=0, message="No matches found")

    return build_response(False, error=result.get("error"), code=5005)


@mcp.tool()
def vps_system_logs(server_name: str, log_type: str = "syslog", lines: int = 100, filter_pattern: str = None) -> Dict[str, Any]:
    """
    查看系统日志
    Args: server_name, log_type - syslog|auth|kern|nginx|docker, lines - 行数, filter_pattern - 过滤词
    """
    context = f"syslogs_{server_name}"

    log_paths = {
        "syslog": ["/var/log/syslog", "/var/log/messages"],
        "auth": ["/var/log/auth.log", "/var/log/secure"],
        "kern": ["/var/log/kern.log"],
        "nginx": ["/var/log/nginx/error.log", "/var/log/nginx/access.log"],
        "docker": ["/var/log/docker.log"],
    }

    if log_type not in log_paths:
        return build_response(False, error=f"Unknown log type. Available: {list(log_paths.keys())}", code=5101)

    lines = max(1, min(int(lines), 2000))

    # docker 日志：容器化部署下 journald 通常不可用，直接走 docker logs <container>
    if log_type == "docker":
        target = filter_pattern.strip() if filter_pattern else None
        if not target:
            return build_response(False, error="docker log type requires filter_pattern as container name", code=5104)
        if not re.match(r"^[a-zA-Z0-9_.:-]+$", target):
            return build_response(False, error=f"Invalid container name: {target}", code=5105)
        cmd = f"sudo docker logs --tail {lines} {shlex.quote(target)} 2>&1"
        log_file = f"docker:{target}"
        # filter_pattern 已用作容器名，避免再 grep 自己
        result = execute_command(cmd, context)
        if result["success"]:
            entries = result["output"].splitlines() if result["output"] else []
            return build_response(True, server_name=server_name, log_type=log_type, log_file=log_file,
                                 entries=entries, count=len(entries))
        return build_response(False, error=result.get("error"), code=5103,
                             blocked_rule=result.get("blocked_rule"))

    # 其他日志走文件 tail
    log_file = None
    for path in log_paths[log_type]:
        if os.path.exists(path):
            log_file = path
            break
    if not log_file:
        return build_response(False, error=f"No {log_type} log file found", code=5102)
    cmd = f"sudo tail -n {lines} {shlex.quote(log_file)}"

    if filter_pattern:
        safe = ''.join(c for c in filter_pattern if c.isalnum() or c in '.-_ ')
        if safe:
            cmd += f" | grep --color=never -i {shlex.quote(safe)}"

    result = execute_command(cmd, context)

    if result["success"]:
        entries = result["output"].splitlines() if result["output"] else []
        return build_response(True, server_name=server_name, log_type=log_type, log_file=log_file,
                             entries=entries, count=len(entries))

    return build_response(False, error=result.get("error"), code=5103)
