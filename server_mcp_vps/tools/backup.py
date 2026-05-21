"""
VPS MCP Backup Tools - 备份管理
包含：备份创建、备份恢复
"""

import os
import re
import shlex
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from typing import Dict, Any

import pytz

from core import mcp, logger, execute_command, build_response, USER_HOME, BEIJING_TZ


def register_backup_tools(mcp_instance):
    """注册备份相关工具"""
    pass


BACKUP_DIR = os.path.join(USER_HOME, "backups")


def _safe_db_name(value: str) -> bool:
    return bool(re.match(r"^[a-zA-Z0-9_$.-]+$", value or ""))


def _safe_backup_name(value: str) -> bool:
    return bool(re.match(r"^[a-zA-Z0-9_.-]+$", value or ""))


@mcp.tool()
def vps_backup_create(server_name: str, backup_type: str, target: str, name: str = None, compress: bool = True) -> Dict[str, Any]:
    """
    创建备份
    Args: server_name, backup_type - mysql|postgresql|files|config, target - 数据库名或路径, name - 备份名, compress - 压缩
    """
    context = f"backup_{server_name}"
    valid = ["mysql", "postgresql", "files", "config"]

    if backup_type not in valid:
        return build_response(False, error=f"Invalid type. Use: {valid}", code=21001)

    # 创建备份目录
    execute_command(f"mkdir -p {shlex.quote(BACKUP_DIR)}", f"{context}_mkdir")

    # 生成备份文件名
    if not name:
        timestamp = datetime.now(BEIJING_TZ).strftime('%Y%m%d_%H%M%S')
        name = f"{backup_type}_{timestamp}"
    elif not _safe_backup_name(name):
        return build_response(False, error=f"Invalid backup name: {name}", code=21003)

    backup_file = os.path.join(BACKUP_DIR, name)

    if backup_type == "mysql":
        if not _safe_db_name(target):
            return build_response(False, error=f"Invalid database name: {target}", code=21004)
        ext = ".sql.gz" if compress else ".sql"
        if compress:
            cmd = f"sudo mysqldump --single-transaction --routines --triggers {shlex.quote(target)} | gzip > {shlex.quote(backup_file + ext)}"
        else:
            cmd = f"sudo mysqldump --single-transaction --routines --triggers {shlex.quote(target)} > {shlex.quote(backup_file + ext)}"
        final_file = f"{backup_file}{ext}"

    elif backup_type == "postgresql":
        if not _safe_db_name(target):
            return build_response(False, error=f"Invalid database name: {target}", code=21004)
        ext = ".sql.gz" if compress else ".sql"
        if compress:
            cmd = f"sudo -u postgres pg_dump {shlex.quote(target)} | gzip > {shlex.quote(backup_file + ext)}"
        else:
            cmd = f"sudo -u postgres pg_dump {shlex.quote(target)} > {shlex.quote(backup_file + ext)}"
        final_file = f"{backup_file}{ext}"

    elif backup_type == "files":
        if not os.path.exists(target):
            return build_response(False, error=f"Source path not found: {target}", code=21002)
        ext = ".tar.gz" if compress else ".tar"
        parent = os.path.dirname(target)
        base = os.path.basename(target)
        if compress:
            cmd = f"tar -czf {shlex.quote(backup_file + ext)} -C {shlex.quote(parent)} {shlex.quote(base)}"
        else:
            cmd = f"tar -cf {shlex.quote(backup_file + ext)} -C {shlex.quote(parent)} {shlex.quote(base)}"
        final_file = f"{backup_file}{ext}"

    elif backup_type == "config":
        ext = ".tar.gz" if compress else ".tar"
        paths = "/etc /var/spool/cron"
        if compress:
            cmd = f"sudo tar -czf {shlex.quote(backup_file + ext)} {paths} 2>/dev/null || true"
        else:
            cmd = f"sudo tar -cf {shlex.quote(backup_file + ext)} {paths} 2>/dev/null || true"
        final_file = f"{backup_file}{ext}"

    result = execute_command(cmd, context)

    if result["success"]:
        # 获取文件大小
        size_result = execute_command(f"ls -lh {shlex.quote(final_file)} | awk '{{print $5}}'", f"{context}_size")
        size = size_result["output"].strip() if size_result["success"] else "Unknown"

        return build_response(True, server_name=server_name, backup_type=backup_type,
                             target=target, backup_file=final_file, size=size,
                             compressed=compress, message="Backup created successfully")

    return build_response(False, error=result.get("error"), code=21003)


@mcp.tool()
def vps_backup_restore(server_name: str, backup_file: str, restore_type: str, target: str = None) -> Dict[str, Any]:
    """
    从备份恢复
    Args: server_name, backup_file - 备份文件路径, restore_type - mysql|postgresql|files, target - 目标库名或路径
    """
    context = f"restore_{server_name}"
    valid = ["mysql", "postgresql", "files"]

    if restore_type not in valid:
        return build_response(False, error=f"Invalid type. Use: {valid}", code=22001)

    if not os.path.exists(backup_file):
        return build_response(False, error=f"Backup file not found: {backup_file}", code=22002)

    is_compressed = backup_file.endswith('.gz')

    if restore_type == "mysql":
        if not target:
            return build_response(False, error="Database name required for MySQL restore", code=22003)

        # 创建数据库
        if not _safe_db_name(target):
            return build_response(False, error=f"Invalid database name: {target}", code=22006)
        execute_command(f"sudo mysql -e {shlex.quote(f'CREATE DATABASE IF NOT EXISTS {target}')}", f"{context}_createdb")

        if is_compressed:
            cmd = f"gunzip -c {shlex.quote(backup_file)} | sudo mysql {shlex.quote(target)}"
        else:
            cmd = f"sudo mysql {shlex.quote(target)} < {shlex.quote(backup_file)}"

    elif restore_type == "postgresql":
        if not target:
            return build_response(False, error="Database name required for PostgreSQL restore", code=22004)

        if not _safe_db_name(target):
            return build_response(False, error=f"Invalid database name: {target}", code=22006)
        execute_command(f"sudo -u postgres createdb {shlex.quote(target)} 2>/dev/null || true", f"{context}_createdb")

        if is_compressed:
            cmd = f"gunzip -c {shlex.quote(backup_file)} | sudo -u postgres psql {shlex.quote(target)}"
        else:
            cmd = f"sudo -u postgres psql {shlex.quote(target)} < {shlex.quote(backup_file)}"

    elif restore_type == "files":
        target = target or USER_HOME
        execute_command(f"mkdir -p {shlex.quote(target)}", f"{context}_mkdir")

        if is_compressed:
            cmd = f"tar -xzf {shlex.quote(backup_file)} -C {shlex.quote(target)}"
        else:
            cmd = f"tar -xf {shlex.quote(backup_file)} -C {shlex.quote(target)}"

    result = execute_command(cmd, context)

    if result["success"]:
        return build_response(True, server_name=server_name, restore_type=restore_type,
                             backup_file=backup_file, target=target,
                             message="Restore completed successfully")

    return build_response(False, error=result.get("error"), code=22005)


@mcp.tool()
def vps_backup_list(server_name: str) -> Dict[str, Any]:
    """
    列出现有备份
    Args: server_name - 服务器标识名
    """
    context = f"backuplist_{server_name}"

    if not os.path.exists(BACKUP_DIR):
        return build_response(True, server_name=server_name, backups=[], count=0,
                             message="No backup directory found")

    result = execute_command(f"ls -lh {shlex.quote(BACKUP_DIR)}", context)

    if result["success"]:
        lines = result["output"].splitlines()
        backups = [l for l in lines if not l.startswith("total")]
        return build_response(True, server_name=server_name, backup_dir=BACKUP_DIR,
                             backups=backups, count=len(backups))

    return build_response(False, error=result.get("error"), code=21010)
