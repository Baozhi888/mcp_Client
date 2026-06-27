"""
VPS MCP Core Module - 核心功能模块
包含：日志配置、安全检查、命令执行、异步任务管理
"""

import os
import re
import sys
import logging
from logging.handlers import RotatingFileHandler
import subprocess
import threading
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List
from concurrent.futures import ThreadPoolExecutor

import pytz

try:
    import pwd
except ImportError:
    pwd = None

try:
    import psutil
    from dotenv import load_dotenv
    from mcp.server.fastmcp import FastMCP
except ImportError as e:
    print(f"CRITICAL: Missing packages: {e}")
    sys.exit(1)

# ============ 时区配置 ============
BEIJING_TZ = pytz.timezone('Asia/Shanghai')

def get_beijing_time() -> str:
    return datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S CST')

class BeijingFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        return datetime.fromtimestamp(record.created, BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S CST')

# ============ 用户上下文 ============
try:
    if pwd:
        CURRENT_USER = pwd.getpwuid(os.geteuid()).pw_name
        CURRENT_UID = os.geteuid()
    else:
        CURRENT_USER = os.environ.get('USERNAME', os.environ.get('USER', 'unknown'))
        CURRENT_UID = 0
except (OSError, AttributeError, KeyError):
    CURRENT_USER = os.environ.get('USER', os.environ.get('USERNAME', 'unknown'))
    CURRENT_UID = 0

USER_HOME = os.path.expanduser("~")
LLM_LOGS_DIR = os.path.join(USER_HOME, "llm_logs")
os.makedirs(LLM_LOGS_DIR, exist_ok=True)

# 加载环境变量
load_dotenv(os.path.join(USER_HOME, ".env"))

# ============ 日志配置 ============
def setup_logging(name: str, level: int = logging.INFO) -> logging.Logger:
    logger_instance = logging.getLogger(name)
    logger_instance.setLevel(level)
    logger_instance.handlers.clear()

    log_file = os.path.join(LLM_LOGS_DIR, f"{name}.log")
    formatter = BeijingFormatter(f'%(asctime)s - %(levelname)s - {CURRENT_USER} - %(message)s')

    try:
        fh = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=3, encoding='utf-8')
        fh.setFormatter(formatter)
        logger_instance.addHandler(fh)
    except Exception:
        pass

    ch = logging.StreamHandler(sys.stderr)
    ch.setFormatter(formatter)
    logger_instance.addHandler(ch)

    return logger_instance

LOG_LEVEL = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
logger = setup_logging('vps_server_mcp', level=LOG_LEVEL)
audit_logger = setup_logging('vps_audit', level=logging.INFO)

# ============ FastMCP 实例 ============
mcp = FastMCP("VPSServerMonitor")

# ============ 安全配置 ============
# 每条规则为 (label, regex)。label 用于审计日志和返回给客户端，便于排查误伤。
FORBIDDEN_PATTERNS = [
    ("rm_root", r'\brm\s+(-[rf]+|--[a-zA-Z-]+)\s+/\S*'),
    ("dd_overwrite", r'\bdd\b.*if=/dev/.*of=/'),
    ("mkfs", r'(?<![\w-])mkfs\b(?!\w)'),
    # 收紧：只匹配 Windows 风格的磁盘格式化 (format C:)，避免误伤 docker --format 等长选项
    ("format_disk", r'(?<![\w-])format\s+[a-zA-Z]:'),
    ("fdisk", r'(?<![\w-])fdisk\b(?!\w)'),
    ("parted", r'(?<![\w-])parted\b(?!\w)'),
    ("fork_bomb", r':\(\)\{\s*:\s*\|\s*:&\s*\};:'),
    ("chmod_777_root", r'\bchmod\s+777\s+/'),
    ("iptables_flush", r'\biptables\s+-F\b'),
    ("killall_9", r'\bkillall\s+-9\b'),
    ("init_0", r'\binit\s+0\b'),
    # 收紧：只拦截真正的 shutdown 命令（开头或分号后），避免误伤 grep/log 文本里的 shutdown 字眼
    ("shutdown_now", r'(?:^|[;&|]\s*)shutdown\s+(?:-[hHrR]\s+)?(?:now|\+?\d)'),
    # 收紧：halt 必须独立成令，不允许 --halt 长选项或路径子串
    ("halt", r'(?:^|[;&|]\s*)halt(?:\s+-[fpn]+)?\s*$'),
]

SAFE_OPERATIONS = [
    r'^ls\s+', r'^cat\s+', r'^head\s+', r'^tail\s+', r'^grep\s+', r'^find\s+',
    r'^du\s+', r'^df\s+', r'^free\s+', r'^ps\s+', r'^top\s+',
    r'^uname\s+', r'^hostname\s*$', r'^whoami\s*$', r'^id\s*$', r'^uptime\s*$',
    r'^systemctl\s+status\s+', r'^systemctl\s+is-active\s+',
]

ALLOWED_SERVICES = os.getenv("ALLOWED_SERVICES", "*").split(",")

RESOURCE_LIMITS = {
    "max_cpu_percent": int(os.getenv("MAX_CPU_PERCENT", "90")),
    "max_memory_percent": int(os.getenv("MAX_MEMORY_PERCENT", "90")),
    "max_disk_percent": int(os.getenv("MAX_DISK_PERCENT", "95")),
    "max_command_timeout": int(os.getenv("MAX_COMMAND_TIMEOUT", "120")),
    "max_command_output_chars": int(os.getenv("MAX_COMMAND_OUTPUT_CHARS", "200000")),
}

# ============ 安全检查函数 ============
def audit_log(context: str, action: str, status: str, details: str = ""):
    message = f"[{context}] {action}: {status}"
    if details:
        message += f" - {details}"
    audit_logger.info(message)

def match_dangerous_rule(command: str) -> Optional[str]:
    """返回首个命中的规则标签，未命中返回 None。"""
    for label, pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return label
    return None

def is_dangerous_command(command: str) -> bool:
    return match_dangerous_rule(command) is not None

def is_safe_operation(command: str) -> bool:
    return any(re.search(p, command, re.IGNORECASE) for p in SAFE_OPERATIONS)

def check_system_resources() -> Tuple[bool, str]:
    try:
        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory().percent
        disk = psutil.disk_usage('/').percent

        if cpu > RESOURCE_LIMITS["max_cpu_percent"]:
            return False, f"CPU: {cpu:.1f}%"
        if mem > RESOURCE_LIMITS["max_memory_percent"]:
            return False, f"Memory: {mem:.1f}%"
        if disk > RESOURCE_LIMITS["max_disk_percent"]:
            return False, f"Disk: {disk:.1f}%"
        return True, "OK"
    except Exception as e:
        return False, str(e)

def limit_output(value: Optional[str]) -> str:
    if not value:
        return ""
    limit = RESOURCE_LIMITS["max_command_output_chars"]
    if len(value) <= limit:
        return value.strip()
    return (value[:limit] + f"\n...[truncated {len(value) - limit} chars]").strip()

def execute_command(command: str, context: str = "exec") -> Dict[str, Any]:
    """安全执行命令的核心函数"""
    # 安全检查
    matched_rule = match_dangerous_rule(command)
    if matched_rule:
        audit_log(context, "execute", "blocked", f"Dangerous[{matched_rule}]: {command}")
        return {
            "success": False, "code": -3,
            "error": f"Dangerous command blocked (rule: {matched_rule})",
            "blocked_rule": matched_rule,
            "command_preview": command[:200],
        }

    can_proceed, msg = check_system_resources()
    if not can_proceed:
        audit_log(context, "execute", "blocked", f"Resource: {msg}")
        return {"success": False, "code": -5, "error": f"Resource limit: {msg}"}

    logger.info(f"[{context}] Executing: {command}")

    try:
        process = subprocess.run(
            command, shell=True, capture_output=True, text=True,
            timeout=RESOURCE_LIMITS["max_command_timeout"], cwd=USER_HOME
        )

        result = {
            "success": process.returncode == 0,
            "code": process.returncode,
            "output": limit_output(process.stdout),
            "error": limit_output(process.stderr) if process.returncode != 0 and process.stderr else None
        }

        audit_log(context, "execute", "success" if result["success"] else "failed", f"RC:{process.returncode}")
        return result

    except subprocess.TimeoutExpired:
        audit_log(context, "execute", "timeout", command)
        return {"success": False, "code": -1, "error": "Command timeout"}
    except Exception as e:
        audit_log(context, "execute", "error", str(e))
        return {"success": False, "code": -2, "error": str(e)}

# ============ 响应构建器 ============
def build_response(success: bool, data: Dict = None, error: str = None, code: int = 0, **kwargs) -> Dict[str, Any]:
    """统一构建响应格式"""
    resp = {
        "success": success,
        "beijing_time": get_beijing_time(),
        "code": code if not success else 0
    }
    if data:
        resp.update(data)
    if error:
        resp["error"] = error
    resp.update(kwargs)
    return resp

# ============ 异步任务管理器 ============
class AsyncTaskManager:
    def __init__(self, max_workers=3):
        self.tasks = {}
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.lock = threading.Lock()

    def submit(self, name: str, command: str, context: str, timeout: int = 3600) -> str:
        task_id = str(uuid.uuid4())[:8]
        task_info = {
            "task_id": task_id,
            "task_name": name,
            "command": command,
            "status": "running",
            "start_time": get_beijing_time(),
            "end_time": None,
            "result": None,
            "error": None
        }
        with self.lock:
            self.tasks[task_id] = task_info
        self.executor.submit(self._run, task_id, command, timeout)
        return task_id

    def _run(self, task_id: str, command: str, timeout: int):
        try:
            proc = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout, cwd=USER_HOME)
            result = {
                "success": proc.returncode == 0,
                "code": proc.returncode,
                "output": limit_output(proc.stdout),
                "error": limit_output(proc.stderr) if proc.stderr else None
            }
            with self.lock:
                if task_id in self.tasks:
                    self.tasks[task_id].update({"status": "completed", "end_time": get_beijing_time(), "result": result})
        except subprocess.TimeoutExpired:
            with self.lock:
                if task_id in self.tasks:
                    self.tasks[task_id].update({"status": "timeout", "end_time": get_beijing_time(), "error": f"Timeout {timeout}s"})
        except Exception as e:
            with self.lock:
                if task_id in self.tasks:
                    self.tasks[task_id].update({"status": "failed", "end_time": get_beijing_time(), "error": str(e)})

    def get_status(self, task_id: str) -> Optional[Dict]:
        with self.lock:
            return self.tasks.get(task_id)

    def list_tasks(self, status_filter: str = None) -> List[Dict]:
        with self.lock:
            tasks = list(self.tasks.values())
        if status_filter:
            tasks = [t for t in tasks if t["status"] == status_filter]
        return sorted(tasks, key=lambda x: x["start_time"], reverse=True)

    def cleanup(self, max_age_hours: int = 24) -> int:
        current = datetime.now(BEIJING_TZ)
        removed = 0
        with self.lock:
            to_remove = []
            for tid, info in self.tasks.items():
                if info["status"] in ["completed", "failed", "timeout"]:
                    try:
                        start = datetime.strptime(info["start_time"], '%Y-%m-%d %H:%M:%S CST')
                        start = BEIJING_TZ.localize(start)
                        if (current - start).total_seconds() / 3600 > max_age_hours:
                            to_remove.append(tid)
                    except:
                        pass
            for tid in to_remove:
                del self.tasks[tid]
                removed += 1
        return removed

# 全局任务管理器
task_manager = AsyncTaskManager(max_workers=3)
