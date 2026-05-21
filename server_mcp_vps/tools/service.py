"""
VPS MCP Service Tools - 服务与包管理
包含：服务状态、服务管理、健康检查、包管理、Docker操作
"""

import re
import os
import shlex
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Dict, Any, Optional

from core import (
    mcp, logger, execute_command, build_response,
    task_manager, ALLOWED_SERVICES, USER_HOME
)


def register_service_tools(mcp_instance):
    """注册服务相关工具"""
    pass


def _safe_unit_name(value: str) -> bool:
    return bool(re.match(r"^[a-zA-Z0-9_.@:-]+$", value or ""))


def _safe_container_name(value: str) -> bool:
    return bool(re.match(r"^[a-zA-Z0-9_.:-]+$", value or ""))


@mcp.tool()
def vps_service_status(server_name: str, service_name: str) -> Dict[str, Any]:
    """
    检查服务状态
    Args: server_name, service_name - 服务名(nginx/mysql/docker等)
    """
    context = f"svc_status_{server_name}"
    logger.info(f"Checking service '{service_name}'")

    if not _safe_unit_name(service_name):
        return build_response(False, error=f"Invalid service name: {service_name}", code=2104)

    if "*" not in ALLOWED_SERVICES and service_name not in ALLOWED_SERVICES:
        return build_response(False, error=f"Service '{service_name}' not allowed", code=2102)

    result = execute_command(f"sudo systemctl status {shlex.quote(service_name)}", context)
    output = result.get("output", "").lower()

    status = {
        "service_name": service_name,
        "is_active": "active (" in output,
        "is_running": "active (running)" in output,
        "is_enabled": "enabled;" in output,
        "is_failed": "failed" in output,
        "raw_output": result.get("output", "")[:500]
    }

    return build_response(True, server_name=server_name, status=status)


@mcp.tool()
def vps_service_manage(server_name: str, service_name: str, action: str) -> Dict[str, Any]:
    """
    管理系统服务
    Args: server_name, service_name, action - start|stop|restart|enable|disable|reload
    """
    context = f"svc_mgr_{server_name}"
    valid = ["start", "stop", "restart", "enable", "disable", "reload"]

    if action not in valid:
        return build_response(False, error=f"Invalid action. Use: {valid}", code=2101)

    if not _safe_unit_name(service_name):
        return build_response(False, error=f"Invalid service name: {service_name}", code=2104)

    if "*" not in ALLOWED_SERVICES and service_name not in ALLOWED_SERVICES:
        return build_response(False, error=f"Service '{service_name}' not allowed", code=2102)

    result = execute_command(f"sudo systemctl {action} {shlex.quote(service_name)}", context)

    if result["success"]:
        return build_response(True, server_name=server_name, service=service_name, action=action,
                             message=f"Service {service_name} {action} completed")

    return build_response(False, error=result.get("error"), code=2103)


@mcp.tool()
def vps_service_health(server_name: str, service_list: str = "common") -> Dict[str, Any]:
    """
    批量检查服务健康状态
    Args: server_name, service_list - common|web|database|all 或逗号分隔的服务名
    """
    context = f"svc_health_{server_name}"
    logger.info(f"Health check: {service_list}")

    groups = {
        "common": ["ssh", "cron", "rsyslog"],
        "web": ["nginx", "apache2"],
        "database": ["mysql", "postgresql", "redis"],
        "docker": ["docker"]
    }

    if service_list in groups:
        services = groups[service_list]
    elif service_list == "all":
        services = [s for g in groups.values() for s in g]
    else:
        services = [s.strip() for s in service_list.split(",")]

    invalid = [svc for svc in services if not _safe_unit_name(svc)]
    if invalid:
        return build_response(False, error=f"Invalid service names: {invalid}", code=2104)

    status_map = {}
    healthy = True

    for svc in services:
        result = execute_command(f"sudo systemctl is-active {shlex.quote(svc)}", f"{context}_{svc}")
        is_active = result["success"] and result["output"].strip() == "active"
        if not is_active:
            healthy = False
        status_map[svc] = {"is_active": is_active, "output": result["output"].strip()}

    return build_response(True, server_name=server_name, overall_healthy=healthy,
                         services=status_map, checked=len(services))


@mcp.tool()
def vps_package_manage(server_name: str, package_name: str, action: str, async_mode: bool = False) -> Dict[str, Any]:
    """
    管理系统软件包
    Args: server_name, package_name, action - install|remove|update|info, async_mode - 异步执行
    """
    context = f"pkg_{action}_{server_name}"
    valid = ["install", "remove", "update", "info"]

    if action not in valid:
        return build_response(False, error=f"Invalid action. Use: {valid}", code=3001)

    if not re.match(r"^[a-zA-Z0-9.+\-]+$", package_name):
        return build_response(False, error=f"Invalid package name: {package_name}", code=3002)

    if action == "info":
        result = execute_command(f"apt-cache show {package_name}", context)
        if result["success"]:
            return build_response(True, server_name=server_name, package=package_name, info=result["output"][:2000])
        return build_response(False, error=result.get("error"), code=3004)

    cmd_map = {
        "install": f"sudo apt-get update -qq && sudo apt-get install -y {package_name}",
        "remove": f"sudo apt-get remove -y {package_name}",
        "update": f"sudo apt-get update -qq && sudo apt-get install --only-upgrade -y {package_name}"
    }
    cmd = cmd_map[action]

    if async_mode and action in ["install", "update"]:
        task_id = task_manager.submit(f"Package {action}: {package_name}", cmd, context, timeout=1800)
        return build_response(True, server_name=server_name, task_id=task_id, async_mode=True,
                             message=f"Package {action} started. Use vps_task_status to check.")

    result = execute_command(cmd, context)
    if result["success"]:
        return build_response(True, server_name=server_name, package=package_name, action=action,
                             message=f"Package {action} completed")
    return build_response(False, error=result.get("error"), code=3004)


@mcp.tool()
def vps_docker_manage(server_name: str, action: str, container: str = None) -> Dict[str, Any]:
    """
    管理Docker容器
    Args: server_name, action - list|start|stop|restart|logs|stats, container - 容器名
    """
    context = f"docker_{action}_{server_name}"
    valid = ["list", "start", "stop", "restart", "logs", "stats"]

    if action not in valid:
        return build_response(False, error=f"Invalid action. Use: {valid}", code=6001)

    if action == "list":
        cmd = "sudo docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"
    elif action == "stats":
        if container and not _safe_container_name(container):
            return build_response(False, error=f"Invalid container name: {container}", code=6004)
        cmd = f"sudo docker stats --no-stream {shlex.quote(container) if container else ''}"
    elif action == "logs":
        if not container:
            return build_response(False, error="Container name required for logs", code=6002)
        if not _safe_container_name(container):
            return build_response(False, error=f"Invalid container name: {container}", code=6004)
        cmd = f"sudo docker logs --tail 100 {shlex.quote(container)}"
    else:
        if not container:
            return build_response(False, error=f"Container name required for {action}", code=6002)
        if not _safe_container_name(container):
            return build_response(False, error=f"Invalid container name: {container}", code=6004)
        cmd = f"sudo docker {action} {shlex.quote(container)}"

    result = execute_command(cmd, context)

    if result["success"]:
        return build_response(True, server_name=server_name, action=action, container=container,
                             output=result["output"][:3000])

    return build_response(False, error=result.get("error"), code=6003)


@mcp.tool()
def vps_async_docker_deploy(server_name: str, operation: str, service: str = None, compose_file: str = None) -> Dict[str, Any]:
    """
    异步Docker部署操作（适合耗时操作）
    Args: server_name, operation - pull|build|up|down|restart, service - 服务名, compose_file - compose文件路径
    """
    context = f"docker_deploy_{server_name}"
    valid = ["pull", "build", "up", "down", "restart"]

    if operation not in valid:
        return build_response(False, error=f"Invalid operation. Use: {valid}", code=14001)

    if compose_file:
        if not os.path.isabs(compose_file):
            compose_file = os.path.join(USER_HOME, compose_file)
        base = f"sudo docker-compose -f {shlex.quote(compose_file)}"
    else:
        base = "sudo docker-compose"

    if service and not _safe_container_name(service):
        return build_response(False, error=f"Invalid service name: {service}", code=14002)

    service_arg = shlex.quote(service) if service else ""

    cmd_map = {
        "pull": f"{base} pull",
        "build": f"{base} build",
        "up": f"{base} up -d {service_arg}",
        "down": f"{base} down",
        "restart": f"{base} restart {service_arg}"
    }

    task_id = task_manager.submit(f"Docker {operation}: {service or 'all'}", cmd_map[operation], context, timeout=2400)

    return build_response(True, server_name=server_name, task_id=task_id, operation=operation,
                         message=f"Docker {operation} started. Use vps_task_status to check.")
