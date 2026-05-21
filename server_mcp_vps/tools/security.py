"""
VPS MCP Security Tools - 安全管理
包含：安全监控、用户管理、SSH密钥管理
"""

import re
import os
import shlex
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Dict, Any

from core import mcp, logger, execute_command, build_response


def register_security_tools(mcp_instance):
    """注册安全相关工具"""
    pass


# 系统用户（禁止操作）
SYSTEM_USERS = ["root", "daemon", "bin", "sys", "nobody", "www-data", "sshd", "mysql", "postgres"]


def _safe_username(username: str) -> bool:
    return bool(re.match(r'^[a-z_][a-z0-9_-]*$', username or ""))


def _safe_group(group: str) -> bool:
    return bool(re.match(r'^[a-z_][a-z0-9_-]*$', group or ""))


@mcp.tool()
def vps_security_monitor(server_name: str, check_type: str = "all") -> Dict[str, Any]:
    """
    安全监控检查
    Args: server_name, check_type - all|auth_failures|ssh_attacks|disk|network
    """
    context = f"secmon_{server_name}"
    logger.info(f"Security monitoring: {check_type}")

    checks = {}

    if check_type in ["all", "auth_failures"]:
        result = execute_command(
            "sudo grep -i 'failed\\|failure\\|invalid' /var/log/auth.log 2>/dev/null | tail -n 15",
            f"{context}_auth"
        )
        checks["auth_failures"] = {
            "entries": result["output"].splitlines() if result["success"] else [],
            "count": len(result["output"].splitlines()) if result["success"] else 0
        }

    if check_type in ["all", "ssh_attacks"]:
        result = execute_command(
            "sudo grep -i 'sshd.*failed\\|sshd.*invalid' /var/log/auth.log 2>/dev/null | tail -n 15",
            f"{context}_ssh"
        )
        checks["ssh_attacks"] = {
            "entries": result["output"].splitlines() if result["success"] else [],
            "count": len(result["output"].splitlines()) if result["success"] else 0
        }

    if check_type in ["all", "disk"]:
        result = execute_command("df -h | awk '$5 > 80 {print $0}'", f"{context}_disk")
        checks["disk_high_usage"] = {
            "partitions": result["output"].splitlines() if result["success"] else [],
            "count": len(result["output"].splitlines()) if result["success"] else 0
        }

    if check_type in ["all", "network"]:
        result = execute_command("ss -tuln | grep -E ':22|:80|:443|:3306|:6379'", f"{context}_net")
        checks["listening_services"] = {
            "ports": result["output"].splitlines() if result["success"] else [],
            "count": len(result["output"].splitlines()) if result["success"] else 0
        }

    return build_response(True, server_name=server_name, check_type=check_type, security=checks)


@mcp.tool()
def vps_user_manage(server_name: str, username: str, action: str, password: str = None, groups: str = None) -> Dict[str, Any]:
    """
    用户账户管理
    Args: server_name, username, action - create|delete|lock|unlock|info, password - 密码(创建时), groups - 用户组
    """
    context = f"usermgr_{server_name}"
    valid = ["create", "delete", "lock", "unlock", "info"]

    if action not in valid:
        return build_response(False, error=f"Invalid action. Use: {valid}", code=19001)

    # 验证用户名格式
    if not _safe_username(username):
        return build_response(False, error="Invalid username format", code=19002)

    # 禁止操作系统用户
    if username in SYSTEM_USERS:
        return build_response(False, error=f"Cannot manage system user: {username}", code=19003)

    if action == "info":
        id_result = execute_command(f"id {username}", f"{context}_id")
        groups_result = execute_command(f"groups {username}", f"{context}_groups")
        lastlog_result = execute_command(f"lastlog -u {username} 2>/dev/null", f"{context}_lastlog")

        if id_result["success"]:
            return build_response(True, server_name=server_name, username=username, user_info={
                "id": id_result["output"],
                "groups": groups_result.get("output", "N/A"),
                "last_login": lastlog_result.get("output", "N/A")
            })
        return build_response(False, error=f"User {username} not found", code=19010)

    elif action == "create":
        if not password:
            return build_response(False, error="Password required for user creation", code=19004)

        # 检查用户是否存在
        check = execute_command(f"id {username}", f"{context}_check")
        if check["success"]:
            return build_response(False, error=f"User {username} already exists", code=19005)

        # 创建用户
        result = execute_command(f"sudo useradd -m -s /bin/bash {username}", context)
        if not result["success"]:
            return build_response(False, error=result.get("error"), code=19007)

        # 设置密码
        passwd_result = execute_command(f"printf %s {shlex.quote(f'{username}:{password}')} | sudo chpasswd", f"{context}_passwd")
        if not passwd_result["success"]:
            return build_response(False, error="Failed to set password", code=19006)

        # 添加到组
        if groups:
            for g in groups.split(","):
                group = g.strip()
                if not _safe_group(group):
                    return build_response(False, error=f"Invalid group name: {group}", code=19013)
                execute_command(f"sudo usermod -a -G {shlex.quote(group)} {shlex.quote(username)}", f"{context}_group")

        return build_response(True, server_name=server_name, username=username, action=action,
                             message=f"User {username} created", groups=groups)

    elif action == "delete":
        check = execute_command(f"id {username}", f"{context}_check")
        if not check["success"]:
            return build_response(False, error=f"User {username} not found", code=19008)

        result = execute_command(f"sudo userdel -r {username}", context)
        if result["success"]:
            return build_response(True, server_name=server_name, username=username,
                                 message=f"User {username} deleted")
        return build_response(False, error=result.get("error"), code=19009)

    elif action in ["lock", "unlock"]:
        check = execute_command(f"id {username}", f"{context}_check")
        if not check["success"]:
            return build_response(False, error=f"User {username} not found", code=19011)

        flag = "-L" if action == "lock" else "-U"
        result = execute_command(f"sudo usermod {flag} {username}", context)
        if result["success"]:
            return build_response(True, server_name=server_name, username=username,
                                 message=f"User {username} {action}ed")
        return build_response(False, error=result.get("error"), code=19012)


@mcp.tool()
def vps_ssh_key_manage(server_name: str, username: str, action: str, public_key: str = None) -> Dict[str, Any]:
    """
    SSH密钥管理
    Args: server_name, username, action - add|list|generate, public_key - SSH公钥(add时需要)
    """
    context = f"sshkey_{server_name}"
    valid = ["add", "list", "generate"]

    if action not in valid:
        return build_response(False, error=f"Invalid action. Use: {valid}", code=20001)

    if not _safe_username(username):
        return build_response(False, error="Invalid username format", code=20006)

    # 检查用户是否存在
    check = execute_command(f"id {shlex.quote(username)}", f"{context}_check")
    if not check["success"]:
        return build_response(False, error=f"User {username} not found", code=20002)

    # 获取用户主目录
    home_result = execute_command(f"getent passwd {shlex.quote(username)} | cut -d: -f6", f"{context}_home")
    if not home_result["success"]:
        return build_response(False, error="Failed to get user home directory", code=20003)

    user_home = home_result["output"].strip()
    ssh_dir = f"{user_home}/.ssh"
    auth_keys = f"{ssh_dir}/authorized_keys"

    if action == "add":
        if not public_key:
            return build_response(False, error="Public key required", code=20004)

        # 验证公钥格式
        if not (public_key.startswith("ssh-rsa ") or public_key.startswith("ssh-ed25519 ")):
            return build_response(False, error="Invalid public key format", code=20005)

        # 创建.ssh目录
        execute_command(f"sudo mkdir -p {shlex.quote(ssh_dir)}", f"{context}_mkdir")
        execute_command(f"printf %s {shlex.quote(public_key + chr(10))} | sudo tee -a {shlex.quote(auth_keys)}", context)

        # 设置权限
        execute_command(f"sudo chmod 700 {shlex.quote(ssh_dir)}", f"{context}_chmod1")
        execute_command(f"sudo chmod 600 {shlex.quote(auth_keys)}", f"{context}_chmod2")
        execute_command(f"sudo chown -R {shlex.quote(username)}:{shlex.quote(username)} {shlex.quote(ssh_dir)}", f"{context}_chown")

        return build_response(True, server_name=server_name, username=username,
                             message="SSH key added", key_file=auth_keys)

    elif action == "list":
        if os.path.exists(auth_keys):
            result = execute_command(f"sudo cat {shlex.quote(auth_keys)}", context)
            keys = result["output"].strip().split('\n') if result["success"] and result["output"].strip() else []
            return build_response(True, server_name=server_name, username=username,
                                 keys=keys, count=len(keys))
        return build_response(True, server_name=server_name, username=username,
                             keys=[], count=0, message="No authorized_keys file")

    elif action == "generate":
        key_file = f"{ssh_dir}/id_rsa"

        execute_command(f"sudo mkdir -p {shlex.quote(ssh_dir)}", f"{context}_mkdir")
        result = execute_command(
            f"sudo ssh-keygen -t rsa -b 4096 -f {shlex.quote(key_file)} -N '' -C {shlex.quote(f'{username}@{server_name}')}",
            context
        )

        if result["success"]:
            execute_command(f"sudo chmod 700 {shlex.quote(ssh_dir)}", f"{context}_chmod1")
            execute_command(f"sudo chmod 600 {shlex.quote(key_file)}", f"{context}_chmod2")
            execute_command(f"sudo chmod 644 {shlex.quote(key_file + '.pub')}", f"{context}_chmod3")
            execute_command(f"sudo chown -R {shlex.quote(username)}:{shlex.quote(username)} {shlex.quote(ssh_dir)}", f"{context}_chown")

            pubkey = execute_command(f"sudo cat {shlex.quote(key_file + '.pub')}", f"{context}_pubkey")

            return build_response(True, server_name=server_name, username=username,
                                 message="SSH key pair generated",
                                 private_key_path=key_file,
                                 public_key_path=f"{key_file}.pub",
                                 public_key=pubkey.get("output", ""))

        return build_response(False, error=result.get("error"), code=20008)
