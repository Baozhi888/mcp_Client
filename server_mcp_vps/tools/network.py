"""
VPS MCP Network Tools - 网络管理
包含：网络信息、端口检查、防火墙、DNS配置、网络诊断
"""

import re
import os
import shlex
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Dict, Any

from core import mcp, logger, execute_command, build_response


def register_network_tools(mcp_instance):
    """注册网络相关工具"""
    pass


def _safe_host(value: str) -> bool:
    return bool(re.match(r'^[a-zA-Z0-9.\-:]+$', value or ""))


@mcp.tool()
def vps_network_info(server_name: str) -> Dict[str, Any]:
    """
    获取网络接口和路由信息
    Args: server_name - 服务器标识名
    """
    context = f"netinfo_{server_name}"
    logger.info(f"Getting network info for {server_name}")

    commands = {
        "interfaces": "ip addr show",
        "routing": "ip route show",
        "listening": "ss -tuln",
        "dns": "cat /etc/resolv.conf"
    }

    info = {}
    for key, cmd in commands.items():
        result = execute_command(cmd, f"{context}_{key}")
        info[key] = result["output"] if result["success"] else f"Error: {result.get('error')}"

    return build_response(True, server_name=server_name, network=info)


@mcp.tool()
def vps_port_check(server_name: str, host: str, port: int) -> Dict[str, Any]:
    """
    检查端口是否开放
    Args: server_name, host - 目标主机, port - 端口号
    """
    context = f"portcheck_{server_name}"
    logger.info(f"Checking {host}:{port}")

    try:
        port = int(port)
        if not (1 <= port <= 65535):
            raise ValueError()
    except:
        return build_response(False, error=f"Invalid port: {port}", code=7101)

    if not _safe_host(host):
        return build_response(False, error="Invalid host format", code=7102)

    result = execute_command(f"nc -zv -w 2 {shlex.quote(host)} {port} 2>&1", context)
    output = result.get("output", "") + result.get("error", "")
    is_open = "succeeded" in output.lower() or "open" in output.lower()

    info = {"host": host, "port": port, "is_open": is_open, "detail": output[:500]}

    if host in ["localhost", "127.0.0.1"] and is_open:
        lsof = execute_command(f"lsof -i TCP:{port} -sTCP:LISTEN -n -P 2>/dev/null", f"{context}_lsof")
        if lsof["success"]:
            info["process"] = lsof["output"][:500]

    return build_response(True, server_name=server_name, port_status=info)


@mcp.tool()
def vps_firewall_manage(server_name: str, action: str, port: int = None, protocol: str = "tcp") -> Dict[str, Any]:
    """
    管理UFW防火墙
    Args: server_name, action - enable|disable|status|allow|deny, port - 端口号, protocol - tcp|udp
    """
    context = f"firewall_{server_name}"
    valid = ["enable", "disable", "status", "allow", "deny"]

    if action not in valid:
        return build_response(False, error=f"Invalid action. Use: {valid}", code=15001)

    if action == "status":
        cmd = "sudo ufw status verbose"
    elif action == "enable":
        cmd = "sudo ufw --force enable"
    elif action == "disable":
        cmd = "sudo ufw --force disable"
    elif action in ["allow", "deny"]:
        if not port or not (1 <= port <= 65535):
            return build_response(False, error="Valid port required for allow/deny", code=15003)
        if protocol not in ["tcp", "udp"]:
            return build_response(False, error="Protocol must be tcp or udp", code=15004)
        cmd = f"sudo ufw {action} {port}/{protocol}"

    result = execute_command(cmd, context)

    # 获取当前状态
    status = execute_command("sudo ufw status", f"{context}_status")

    if result["success"]:
        return build_response(True, server_name=server_name, action=action, port=port,
                             output=result["output"], current_status=status.get("output", ""))

    return build_response(False, error=result.get("error"), code=15006)


@mcp.tool()
def vps_port_security(server_name: str, scan_type: str = "listening") -> Dict[str, Any]:
    """
    端口安全扫描
    Args: server_name, scan_type - listening|connections|security
    """
    context = f"portscan_{server_name}"
    valid = ["listening", "connections", "security"]

    if scan_type not in valid:
        return build_response(False, error=f"Invalid scan type. Use: {valid}", code=16001)

    info = {}

    if scan_type in ["listening", "security"]:
        result = execute_command("ss -tuln", f"{context}_listen")
        info["listening_ports"] = result["output"].splitlines() if result["success"] else []

    if scan_type in ["connections", "security"]:
        result = execute_command("ss -tun state established", f"{context}_conn")
        info["established"] = result["output"].splitlines() if result["success"] else []

    if scan_type == "security":
        # 检查防火墙状态
        ufw = execute_command("sudo ufw status", f"{context}_ufw")
        info["firewall"] = ufw.get("output", "Unknown")

        # 检查常见危险端口
        vuln_ports = [21, 23, 25, 1433, 3389]
        pattern = "|".join([f":{p}" for p in vuln_ports])
        vuln = execute_command(f"ss -tuln | grep -E '({pattern})'", f"{context}_vuln")
        info["vulnerable_ports"] = vuln["output"].splitlines() if vuln["success"] else []

    return build_response(True, server_name=server_name, scan_type=scan_type, security=info)


@mcp.tool()
def vps_dns_config(server_name: str, action: str, dns_servers: str = None, domain: str = None) -> Dict[str, Any]:
    """
    DNS配置管理
    Args: server_name, action - show|set|test|flush, dns_servers - DNS服务器(逗号分隔), domain - 测试域名
    """
    context = f"dns_{server_name}"
    valid = ["show", "set", "test", "flush"]

    if action not in valid:
        return build_response(False, error=f"Invalid action. Use: {valid}", code=25001)

    if action == "show":
        result = execute_command("cat /etc/resolv.conf", context)
        return build_response(True, server_name=server_name, resolv_conf=result.get("output", ""))

    elif action == "set":
        if not dns_servers:
            return build_response(False, error="DNS servers required", code=25002)

        servers = [s.strip() for s in dns_servers.split(",")]
        for s in servers:
            if not re.match(r'^(\d{1,3}\.){3}\d{1,3}$', s):
                return build_response(False, error=f"Invalid DNS server: {s}", code=25003)

        # 备份
        execute_command("sudo cp /etc/resolv.conf /etc/resolv.conf.backup", f"{context}_backup")

        content = "# Generated by VPS MCP\n" + "\n".join([f"nameserver {s}" for s in servers])
        result = execute_command(f"printf %s {shlex.quote(content)} | sudo tee /etc/resolv.conf", context)

        if result["success"]:
            return build_response(True, server_name=server_name, dns_servers=servers, message="DNS updated")
        return build_response(False, error=result.get("error"), code=25004)

    elif action == "test":
        domain = domain or "google.com"
        if not _safe_host(domain):
            return build_response(False, error="Invalid domain format", code=25005)
        result = execute_command(f"nslookup {shlex.quote(domain)}", context)
        return build_response(True, server_name=server_name, test_domain=domain, result=result.get("output", ""))

    elif action == "flush":
        result = execute_command("sudo systemctl restart systemd-resolved 2>/dev/null || echo 'Flush attempted'", context)
        return build_response(True, server_name=server_name, message="DNS cache flushed")


@mcp.tool()
def vps_network_diagnostic(server_name: str, target: str, test_type: str = "ping") -> Dict[str, Any]:
    """
    网络诊断工具
    Args: server_name, target - 目标地址, test_type - ping|traceroute|mtr
    """
    context = f"netdiag_{server_name}"
    valid = ["ping", "traceroute", "mtr"]

    if test_type not in valid:
        return build_response(False, error=f"Invalid test type. Use: {valid}", code=26001)

    # 验证目标格式
    if not _safe_host(target):
        return build_response(False, error="Invalid target format", code=26002)

    cmd_map = {
        "ping": f"ping -c 5 {shlex.quote(target)}",
        "traceroute": f"traceroute -m 15 {shlex.quote(target)}",
        "mtr": f"mtr -r -c 5 {shlex.quote(target)}"
    }

    result = execute_command(cmd_map[test_type], context)

    # 解析ping结果
    parsed = {}
    if test_type == "ping" and result["success"]:
        output = result["output"]
        loss = re.search(r'(\d+)% packet loss', output)
        if loss:
            parsed["packet_loss"] = f"{loss.group(1)}%"
        timing = re.search(r'min/avg/max.*= ([\d.]+)/([\d.]+)/([\d.]+)', output)
        if timing:
            parsed["timing"] = {"min": f"{timing.group(1)}ms", "avg": f"{timing.group(2)}ms", "max": f"{timing.group(3)}ms"}

    return build_response(result["success"], server_name=server_name, target=target, test_type=test_type,
                         output=result.get("output", "")[:2000], parsed=parsed,
                         error=result.get("error") if not result["success"] else None)
