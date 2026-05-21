"""
记事本MCP服务 - 修复版本
================================
Version: 0.2.1-fixed
Type: Storage Service
Priority: High
Author: MCP Team
Created: 2025

修复了4004错误的优化版本，将List[str]类型改为字符串，简化参数。
"""

import asyncio
import base64
import json
import logging
import os
import re
import uuid
import sys
import threading
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple, List, Any

# 修复模块导入路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastmcp import FastMCP
from config import SERVICE_CONFIG, GMAIL_CONFIG, CLOUDFLARE_CONFIG
from services.kv_service import KVService
from services.d1_service import D1Service
from services.file_service import FileService
from services.gmail_service import GmailService
from services.zhipu_service import ZhipuAIService
from models import (
    NoteModel, NoteCategory, NotePriority, FileModel, FileType,
    ReminderModel, ReminderType, ReminderPriority, ReminderStatus,
    NotifyMethod, RecurrenceModel, ConditionModel, RecurrenceFrequency
)

# 定义北京时间时区（UTC+8）
BEIJING_TIMEZONE = timezone(timedelta(hours=8))

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stderr)]
)

logger = logging.getLogger('NOTEPAD_MCP_FIXED')

logger.info("=" * 60)
logger.info("NOTEPAD MCP FIXED SERVICE STARTING")
logger.info("=" * 60)

# Pydantic兼容性处理函数
def safe_model_dump(model):
    """安全地获取模型的字典表示，专为Pydantic v2.11.4+优化"""
    try:
        # 使用Pydantic v2的model_dump方法
        return model.model_dump()
    except AttributeError:
        logger.error(f"Pydantic model_dump方法不可用: {type(model)}")
        return vars(model) if hasattr(model, '__dict__') else {}
    except Exception as e:
        logger.error(f"Pydantic model序列化失败: {e}, model type: {type(model)}")
        return vars(model) if hasattr(model, '__dict__') else {}

def diagnose_environment():
    """诊断环境兼容性问题"""
    import sys
    import platform

    logger.info("=" * 60)
    logger.info("ENVIRONMENT DIAGNOSTICS")
    logger.info("=" * 60)
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Platform: {platform.platform()}")

    # 检查关键依赖
    dependencies = ['fastmcp', 'pydantic', 'asyncio', 'aiohttp']
    for dep in dependencies:
        try:
            __import__(dep)
            logger.info(f"✓ {dep}: Available")
        except ImportError as e:
            logger.error(f"✗ {dep}: Missing - {e}")

    # 检查Pydantic版本
    try:
        import pydantic
        logger.info(f"Pydantic version: {pydantic.VERSION}")
    except:
        logger.warning("Could not determine Pydantic version")

    logger.info("=" * 60)

# 初始化服务组件
# 使用延迟初始化，避免在导入时就创建实例
mcp = FastMCP("notepad_mcp_fixed")
d1_service: Optional[D1Service] = None
kv_service: Optional[KVService] = None
gmail_service: Optional[GmailService] = None
zhipu_service: Optional[ZhipuAIService] = None

# 初始化状态标志
_initialization_complete = False
_initialization_lock = asyncio.Lock()  # 添加异步锁
_initialization_event = asyncio.Event()
redis_service_handler = None
_reminder_scheduler_thread = None
_reminder_scheduler_started_at: Optional[str] = None
_reminder_scheduler_last_run_at: Optional[str] = None
_reminder_scheduler_last_error: Optional[str] = None
_reminder_scheduler_processed_count = 0

# 添加初始化任务状态
_initialization_task = None

_email_cache_lock = asyncio.Lock()
_recent_email_cache: Dict[str, Dict[str, Any]] = {}
EMAIL_ALIAS_PATTERN = re.compile(r'^email_(\d+)$', re.IGNORECASE)
_note_cache_lock = asyncio.Lock()
_recent_note_cache: Dict[str, Dict[str, Any]] = {}
NOTE_ALIAS_PATTERN = re.compile(r'^note_(\d+)$', re.IGNORECASE)
NOTE_LATEST_ALIAS = "note_latest"
ALIAS_CACHE_TTL_SECONDS = int(os.getenv("NOTEPAD_ALIAS_TTL_SECONDS", "86400"))
ALIAS_CACHE_MAX_ITEMS = int(os.getenv("NOTEPAD_ALIAS_CACHE_MAX_ITEMS", "200"))

async def check_initialization():
    """异步检查服务初始化状态，带等待机制"""
    global _initialization_complete, _initialization_task

    if _initialization_complete:
        return True

    # Start or restart initialization task
    if _initialization_task is None or _initialization_task.done():
        async with _initialization_lock:
            if _initialization_task is None or _initialization_task.done():
                if _initialization_task and _initialization_task.done():
                    _initialization_task = None
                logger.info("Starting background service initialization...")
                _initialization_event.clear()
                _initialization_task = asyncio.create_task(initialize_services())

    if not _initialization_event.is_set():
        logger.warning("Service not fully initialized yet, waiting...")

    try:
        await asyncio.wait_for(_initialization_event.wait(), timeout=10.0)
    except asyncio.TimeoutError:
        logger.error("Service initialization timeout after 10 seconds")
        return False

    if not _initialization_complete:
        logger.error("Service initialization completed with errors")
        return False

    return True


def get_d1_service() -> D1Service:
    """获取D1服务的单例实例"""
    global d1_service
    if d1_service is None:
        d1_service = D1Service()
    return d1_service

def get_kv_service() -> KVService:
    """获取KV服务的单例实例"""
    global kv_service
    if kv_service is None:
        kv_service = KVService()
    return kv_service

def get_zhipu_service() -> ZhipuAIService:
    """获取智谱AI服务的单例实例"""
    global zhipu_service
    if zhipu_service is None:
        zhipu_service = ZhipuAIService()
    return zhipu_service

async def ensure_gmail_service() -> Tuple[bool, str]:
    """确保Gmail服务可用（带更清晰的配置与文件检查日志）"""
    global gmail_service

    # 1) 配置开关检查
    if not SERVICE_CONFIG.get('enable_gmail_integration', True):
        logger.info("[GMAIL] Integration disabled by configuration (ENABLE_GMAIL_INTEGRATION=false)")
        return False, "Gmail integration disabled by configuration"

    # 2) 关键文件预检（尽量给出可操作的提示）
    cred_path = GMAIL_CONFIG.get('api_credentials_file')
    token_path = GMAIL_CONFIG.get('token_path')
    server_mode = GMAIL_CONFIG.get('server_mode', True)

    if cred_path and not os.path.exists(cred_path):
        logger.error(f"[GMAIL] Credentials file not found: {cred_path}")
        return False, f"Gmail credentials not found: {cred_path}"

    if server_mode and token_path and not os.path.exists(token_path):
        # 服务器模式下未找到token：直接返回可操作的提示
        logger.error(f"[GMAIL] [SERVER MODE] Token missing: {token_path}. Please run 'notepad_mcp/run_gmail_auth.py' on your local machine and upload token.json.")
        return False, f"Gmail token missing: {token_path}. Generate with run_gmail_auth.py on local and upload token.json."

    # 3) 初始化（或复用）服务
    if gmail_service is None or getattr(gmail_service, 'service', None) is None:
        try:
            gmail_service = GmailService()
            if getattr(gmail_service, 'service', None) is None:
                logger.error("[GMAIL] Service failed to initialize (service is None)")
                return False, "Gmail service not available"
            logger.info("[GMAIL] Gmail service initialized")
            return True, "Gmail service initialized"
        except Exception as e:
            logger.error(f"[GMAIL] Gmail service initialization failed: {e}", exc_info=True)
            return False, f"Gmail service initialization failed: {str(e)}"

    return True, "Gmail service already available"

def check_zhipu_service_availability() -> Tuple[bool, str]:
    """检查智谱AI服务可用性"""
    try:
        # 确保服务已初始化
        service = get_zhipu_service()

        if not hasattr(service, 'api_key') or not service.api_key:
            return False, "Zhipu AI service API key not configured"

        return True, "Zhipu AI service available"
    except Exception as e:
        return False, f"Zhipu AI service initialization failed: {str(e)}"



async def _register_recent_emails_cache(emails: List[Dict[str, Any]], label: Optional[str], query: Optional[str]) -> None:
    """Cache the latest email list and expose email_N aliases."""
    timestamp = datetime.now(timezone.utc).isoformat()
    async with _email_cache_lock:
        _prune_alias_cache_locked(_recent_email_cache)
        for key in list(_recent_email_cache.keys()):
            if EMAIL_ALIAS_PATTERN.match(key):
                _recent_email_cache.pop(key, None)
        for idx, email in enumerate(emails, start=1):
            if not isinstance(email, dict):
                continue
            alias = f"email_{idx}"
            alias_key = alias.lower()
            _recent_email_cache[alias_key] = {
                "id": email.get("id"),
                "label": label or "inbox",
                "query": query,
                "cached_at": timestamp,
                "subject": email.get("subject"),
            }
            email.setdefault("alias", alias)
            email.setdefault("gmail_id", email.get("id"))
            email.setdefault("content_tool_args", {"email_id": alias})

async def _resolve_email_identifier(email_id: str) -> Tuple[str, bool]:
    """Resolve an email alias into a real Gmail message id."""
    if not email_id:
        return email_id, True
    normalized = email_id.strip()
    if not normalized:
        return normalized, True
    if EMAIL_ALIAS_PATTERN.match(normalized):
        alias_key = normalized.lower()
        async with _email_cache_lock:
            entry = _recent_email_cache.get(alias_key)
        if entry and entry.get("id"):
            return entry["id"], True
        return normalized, False
    normalized_lower = normalized.lower()
    async with _email_cache_lock:
        _prune_alias_cache_locked(_recent_email_cache)
        for entry in _recent_email_cache.values():
            cached_id = str(entry.get("id") or "")
            cached_subject = str(entry.get("subject") or "")
            if cached_id == normalized:
                return normalized, True
            if cached_subject and cached_subject.strip().lower() == normalized_lower:
                return cached_id, True
    return normalized, True

def _email_alias_error(email_id: str) -> Dict:
    """Return a standard error payload when an alias cannot be resolved."""
    return {
        "success": False,
        "error": f"无法识别邮件别名 {email_id}。请先调用 get_recent_emails 获取最新列表，并使用返回的 alias（例如 email_1）或原始 Gmail ID。",
    }

async def _get_resolved_email_id(email_id: str, log_label: str) -> Tuple[Optional[str], Optional[Dict]]:
    """Resolve a single email id and return (real_id, error_payload)."""
    resolved_id, ok = await _resolve_email_identifier(email_id)
    if not ok:
        logger.warning(f"[{log_label}] Email alias not found or expired: {email_id}")
        return None, _email_alias_error(email_id)
    if resolved_id != email_id:
        logger.info(f"[{log_label}] Resolved alias {email_id} -> {resolved_id}")
    return resolved_id, None

async def _resolve_email_id_list(email_ids: List[str], log_label: str) -> Tuple[List[str], List[str]]:
    """Resolve a list of ids and return (resolved_ids, unresolved_aliases)."""
    resolved: List[str] = []
    unresolved: List[str] = []
    for raw_id in email_ids:
        rid, ok = await _resolve_email_identifier(raw_id)
        if not ok:
            unresolved.append(raw_id)
        else:
            if rid != raw_id:
                logger.info(f"[{log_label}] Resolved alias {raw_id} -> {rid}")
            resolved.append(rid)
    return resolved, unresolved


def _parse_cached_at(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None


def _prune_alias_cache_locked(cache: Dict[str, Dict[str, Any]]) -> None:
    """Prune expired alias cache entries. Caller must hold the relevant lock."""
    now = datetime.now(timezone.utc)
    for key, entry in list(cache.items()):
        cached_at = _parse_cached_at(entry.get("cached_at") if isinstance(entry, dict) else None)
        if cached_at and (now - cached_at).total_seconds() > ALIAS_CACHE_TTL_SECONDS:
            cache.pop(key, None)

    if len(cache) <= ALIAS_CACHE_MAX_ITEMS:
        return

    ordered = sorted(
        cache.items(),
        key=lambda item: _parse_cached_at(item[1].get("cached_at")) or datetime.min.replace(tzinfo=timezone.utc),
    )
    for key, _ in ordered[: max(0, len(cache) - ALIAS_CACHE_MAX_ITEMS)]:
        cache.pop(key, None)


def _parse_storage_list(raw: Any) -> List[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    if isinstance(raw, str):
        value = raw.strip()
        if not value:
            return []
        try:
            decoded = json.loads(value)
            if isinstance(decoded, list):
                return [str(item).strip() for item in decoded if str(item).strip()]
        except (json.JSONDecodeError, TypeError):
            pass
        return [item.strip() for item in re.split(r"[,，、]+", value) if item.strip()]
    return [str(raw).strip()] if str(raw).strip() else []


def _normalize_note_record(note: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(note, dict):
        return note
    normalized = dict(note)
    normalized["tags"] = _parse_tags(normalized.get("tags"))
    normalized["file_ids"] = _parse_storage_list(normalized.get("file_ids"))
    return normalized


async def _cache_note_alias(note: Optional[Dict[str, Any]], alias: str = NOTE_LATEST_ALIAS, source: str = "note") -> None:
    if not isinstance(note, dict) or not note.get("id"):
        return
    timestamp = datetime.now(timezone.utc).isoformat()
    async with _note_cache_lock:
        _prune_alias_cache_locked(_recent_note_cache)
        _recent_note_cache[alias.lower()] = {
            "id": note.get("id"),
            "title": note.get("title"),
            "source": source,
            "cached_at": timestamp,
        }


async def _register_recent_notes_cache(notes: List[Dict[str, Any]], source: str = "list_recent_notes") -> None:
    timestamp = datetime.now(timezone.utc).isoformat()
    async with _note_cache_lock:
        _prune_alias_cache_locked(_recent_note_cache)
        for key in list(_recent_note_cache.keys()):
            if NOTE_ALIAS_PATTERN.match(key):
                _recent_note_cache.pop(key, None)
        for idx, note in enumerate(notes, start=1):
            if not isinstance(note, dict) or not note.get("id"):
                continue
            alias = f"note_{idx}"
            _recent_note_cache[alias.lower()] = {
                "id": note.get("id"),
                "title": note.get("title"),
                "source": source,
                "cached_at": timestamp,
            }
            note.setdefault("alias", alias)
            note.setdefault("note_id", note.get("id"))
            note.setdefault("get_tool_args", {"note_id": alias})
            note.setdefault("update_tool_args", {"note_id": alias})
        if notes and isinstance(notes[0], dict) and notes[0].get("id"):
            _recent_note_cache[NOTE_LATEST_ALIAS] = {
                "id": notes[0].get("id"),
                "title": notes[0].get("title"),
                "source": source,
                "cached_at": timestamp,
            }


async def _resolve_note_reference(d1, note_ref: str, allow_recent: bool = False) -> Optional[Dict[str, Any]]:
    """Resolve note aliases, UUID variants, ID prefixes, and titles to a note record."""
    if note_ref is None:
        return None
    ref = str(note_ref).strip()
    if not ref:
        return None

    async with _note_cache_lock:
        _prune_alias_cache_locked(_recent_note_cache)
        cache_entry = _recent_note_cache.get(ref.lower())

    if cache_entry and cache_entry.get("id"):
        cached_note = await d1.get_note(cache_entry["id"])
        if cached_note:
            return _normalize_note_record(cached_note)

    direct_note = await d1.get_note(ref)
    if direct_note:
        return _normalize_note_record(direct_note)

    fallback_note = await _get_note_by_id_with_fallback(d1, ref, include_recent=allow_recent)
    if fallback_note:
        return _normalize_note_record(fallback_note)

    return None


async def _resolve_note_id_for_write(d1, note_ref: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    note = await _resolve_note_reference(d1, note_ref, allow_recent=False)
    if not note:
        return None, None
    resolved_id = note.get("id")
    return note, resolved_id
# ==================== 路由1: 笔记管理 ====================

NOTE_MANAGER_ACTIONS = {
    "create": {"required": ["title", "content"]},
    "get": {"required": ["note_id"]},
    "update": {"required": ["note_id"]},
    "delete": {"required": ["note_id"]},
    "append": {"required": ["note_id", "content"]},
    "search": {"required": ["query"]},
    "filter": {},
    "quick_note": {"required": ["content"]},
    "add_tag": {"required": ["note_id", "tags"]},
    "remove_tag": {"required": ["note_id", "tags"]},
    "get_tags": {},
    "statistics": {},
    "create_from_text": {"required": ["content"]}
}

@mcp.tool()
async def notepad_manager(
    action: str,
    note_id: Optional[str] = None,
    title: Optional[str] = None,
    content: Optional[str] = None,
    category: Optional[str] = None,
    priority: Optional[str] = None,
    tags: Optional[str] = None,
    query: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    auto_categorize: bool = True,
    auto_title: bool = True
) -> Dict:
    """
    Purpose: Legacy notebook multiplexer (create/read/update/search/tag utilities)
    When: Use only if dedicated note_* tools cannot satisfy the request

    Supported actions (required fields):
    - create (title, content)
    - get (note_id)
    - update (note_id)
    - delete (note_id)
    - append (note_id, content)
    - search (query)
    - filter (... optional filters)
    - quick_note (content)
    - add_tag (note_id, tags)
    - remove_tag (note_id, tags)
    - get_tags ()
    - statistics ()
    - create_from_text (content)

    Required: action
    Optional: note_id, title, content, category, priority, tags(csv), query, start_date, end_date, auto_categorize, auto_title
    Returns: {"success": bool, ...}
    Notes: Prefer dedicated helpers like create_note/update_note/append_to_note. Tags must be comma-separated; ID lookup uses fallback matching when needed.
    """
    logger.info(f"[NOTEPAD_MANAGER] Action: {action}")

    # 检查初始化状态
    if not await check_initialization():
        return {"success": False, "error": "Service not fully initialized yet. Please try again later."}

    try:
        normalized_action = action.strip().lower() if action else None
        if not normalized_action or normalized_action not in NOTE_MANAGER_ACTIONS:
            return {
                "success": False,
                "error": f"Unsupported action '{action}'. Use one of {sorted(NOTE_MANAGER_ACTIONS.keys())} or dedicated note_* tools."
            }

        d1 = get_d1_service()

        # 标签标准化（支持逗号分隔字符串）
        tags_list = _parse_tags(tags) if tags else []

        action = normalized_action

        if action == "create":
            if not title or not content:
                return {"success": False, "error": "Title and content are required for create action"}

            # 验证内容不为空或只包含空白字符
            title = title.strip()
            content = content.strip()

            if not title:
                return {"success": False, "error": "Title cannot be empty or only whitespace"}

            if not content:
                return {"success": False, "error": "Content cannot be empty or only whitespace"}

            # 转换枚举值（标准化）
            try:
                norm_cat = _normalize_category(category)
                norm_pri = _normalize_priority(priority)
                note_category = NoteCategory(norm_cat)
                note_priority = NotePriority(norm_pri)
            except ValueError as enum_err:
                logger.warning(f"[NOTEPAD_MANAGER] Enum normalization failed: {enum_err}")
                return {"success": False, "error": f"Invalid category or priority: {enum_err}"}

            # 内容长度检查和处理
            MAX_CONTENT_LENGTH = 50000  # 50KB限制
            if len(content) > MAX_CONTENT_LENGTH:
                logger.warning(f"[NOTEPAD_MANAGER] Content length ({len(content)}) exceeds limit ({MAX_CONTENT_LENGTH})")
                # 选择处理方式：截断或分段
                if len(content) > MAX_CONTENT_LENGTH * 2:
                    # 内容过长，分段处理
                    return await _create_segmented_note(d1, title, content, note_category, note_priority, tags_list)
                else:
                    # 轻微超长，截断处理
                    content = content[:MAX_CONTENT_LENGTH] + "\n\n[注意：内容已截断，原文过长]"
                    logger.info(f"[NOTEPAD_MANAGER] Content truncated to {MAX_CONTENT_LENGTH} characters")

            # 生成唯一ID
            note_id = str(uuid.uuid4())
            current_time = datetime.now(BEIJING_TIMEZONE).isoformat()

            note_data = {
                'id': note_id,
                'title': title,
                'content': content,
                'created_at': current_time,
                'updated_at': current_time,
                'category': note_category.value,
                'priority': note_priority.value,
                'tags': ','.join(tags_list) if tags_list else '',
                'reminder_id': None,
                'file_ids': ''
            }

            logger.info(f"[NOTEPAD_MANAGER] Creating note with content length: {len(content)}, title: {title[:50]}...")
            result = await d1.insert_note(note_data)
            if result:
                logger.info(f"[NOTEPAD_MANAGER] Note created successfully: {note_data['id']}")
                note_record = _normalize_note_record(note_data)
                await _cache_note_alias(note_record, NOTE_LATEST_ALIAS, "notepad_manager.create")
                return {
                    "success": True,
                    "note": note_record,
                    "data": note_record,
                    "note_id": note_data["id"],
                    "alias": NOTE_LATEST_ALIAS,
                    "lookup_hint": "Use note_id for exact retrieval; note_latest is valid for the most recently created/listed note in this process.",
                    "message": "Note created successfully"
                }
            else:
                logger.error(f"[NOTEPAD_MANAGER] Failed to create note")
                return {"success": False, "error": "Failed to create note - database insertion failed"}

        elif action == "get":
            if not note_id:
                return {"success": False, "error": "note_id is required for get action"}

            note = await _resolve_note_reference(d1, note_id, allow_recent=True)
            if note:
                await _cache_note_alias(note, NOTE_LATEST_ALIAS, "notepad_manager.get")
                return {"success": True, "note": note, "data": note, "note_id": note.get("id")}
            else:
                d1_error = _d1_error_response(d1, "Failed to get note")
                if d1_error:
                    return d1_error
                return {"success": False, "error": "Note not found"}

        elif action == "update":
            if not note_id:
                return {"success": False, "error": "note_id is required for update action"}

            existing_note, resolved_note_id = await _resolve_note_id_for_write(d1, note_id)
            if not existing_note or not resolved_note_id:
                d1_error = _d1_error_response(d1, "Failed to resolve note")
                if d1_error:
                    return d1_error
                return {"success": False, "error": "Note not found"}

            update_data = {}
            if title is not None:
                new_title = title.strip()
                if not new_title:
                    return {"success": False, "error": "Title cannot be empty"}
                update_data['title'] = new_title
            if content is not None:
                new_content = content.strip()
                if not new_content:
                    return {"success": False, "error": "Content cannot be empty"}
                update_data['content'] = new_content
            if category is not None:
                try:
                    norm_cat = _normalize_category(category)
                    update_data['category'] = NoteCategory(norm_cat).value
                except ValueError:
                    return {"success": False, "error": f"Invalid category: {category}"}
            if priority is not None:
                try:
                    norm_pri = _normalize_priority(priority)
                    update_data['priority'] = NotePriority(norm_pri).value
                except ValueError:
                    return {"success": False, "error": f"Invalid priority: {priority}"}
            if tags is not None:
                update_data['tags'] = ','.join(tags_list)

            if update_data:
                update_data['updated_at'] = datetime.now(BEIJING_TIMEZONE).isoformat()
                result = await d1.update_note(resolved_note_id, update_data)
                if result:
                    updated_note = await d1.get_note(resolved_note_id)
                    updated_note = _normalize_note_record(updated_note) if updated_note else existing_note
                    await _cache_note_alias(updated_note, NOTE_LATEST_ALIAS, "notepad_manager.update")
                    return {"success": True, "note": updated_note, "data": updated_note, "note_id": resolved_note_id, "message": "Note updated successfully"}
                else:
                    return {"success": False, "error": "Failed to update note"}
            else:
                return {"success": False, "error": "No update data provided"}

        elif action == "delete":
            if not note_id:
                return {"success": False, "error": "note_id is required for delete action"}

            note, resolved_note_id = await _resolve_note_id_for_write(d1, note_id)
            if not note or not resolved_note_id:
                d1_error = _d1_error_response(d1, "Failed to resolve note")
                if d1_error:
                    return d1_error
                return {"success": False, "error": "Note not found"}

            result = await d1.delete_note(resolved_note_id)
            if result:
                return {"success": True, "note_id": resolved_note_id, "deleted_title": note.get("title"), "message": "Note deleted successfully"}
            else:
                return {"success": False, "error": "Note not found or failed to delete"}

        elif action == "append":
            if not note_id or content is None:
                return {"success": False, "error": "note_id and content are required for append action"}

            note, resolved_note_id = await _resolve_note_id_for_write(d1, note_id)
            if not note or not resolved_note_id:
                d1_error = _d1_error_response(d1, "Failed to resolve note")
                if d1_error:
                    return d1_error
                return {"success": False, "error": "Note not found"}

            new_content = note.get('content', '') + content

            update_data = {
                'content': new_content,
                'updated_at': datetime.now(BEIJING_TIMEZONE).isoformat()
            }
            
            result = await d1.update_note(resolved_note_id, update_data)
            if result:
                # 获取更新后的笔记以返回最新状态
                updated_note = await d1.get_note(resolved_note_id)
                updated_note = _normalize_note_record(updated_note) if updated_note else None
                if updated_note:
                    await _cache_note_alias(updated_note, NOTE_LATEST_ALIAS, "notepad_manager.append")
                return {"success": True, "note": updated_note, "data": updated_note, "note_id": resolved_note_id, "message": "Content appended successfully"}
            else:
                return {"success": False, "error": "Failed to append content"}

        elif action == "quick_note":
            if not content:
                return {"success": False, "error": "content is required for quick_note action"}

            # 自动生成标题
            if auto_title:
                lines = content.strip().split('\n')
                title = lines[0][:50] if lines[0].strip() else f"笔记 - {datetime.now(BEIJING_TIMEZONE).strftime('%Y-%m-%d %H:%M')}"
            else:
                title = f"快速笔记 - {datetime.now(BEIJING_TIMEZONE).strftime('%Y-%m-%d %H:%M')}"

            # 递归调用可能导致问题，直接实现
            note_data = {
                'id': str(uuid.uuid4()),
                'title': title,
                'content': content,
                'created_at': datetime.now(BEIJING_TIMEZONE).isoformat(),
                'updated_at': datetime.now(BEIJING_TIMEZONE).isoformat(),
                'category': NoteCategory.OTHER.value,
                'priority': NotePriority.MEDIUM.value,
                'tags': '',
                'reminder_id': None,
                'file_ids': ''
            }

            logger.info(f"[NOTEPAD_MANAGER] Creating quick note with content length: {len(content)}")
            result = await d1.insert_note(note_data)  # 修复方法名
            if result:
                logger.info(f"[NOTEPAD_MANAGER] Quick note created successfully: {note_data['id']}")
                note_record = _normalize_note_record(note_data)
                await _cache_note_alias(note_record, NOTE_LATEST_ALIAS, "notepad_manager.quick_note")
                return {"success": True, "note": note_record, "data": note_record, "note_id": note_data["id"], "alias": NOTE_LATEST_ALIAS, "message": "Quick note created successfully"}
            else:
                logger.error(f"[NOTEPAD_MANAGER] Failed to create quick note")
                return {"success": False, "error": "Failed to create quick note"}

        elif action == "search":
            if not query:
                return {"success": False, "error": "query is required for search action"}

            # 实现搜索逻辑
            search_conditions = []
            params = []

            # 基础搜索条件
            search_conditions.append("(title LIKE ? OR content LIKE ?)")
            search_query = f"%{query}%"
            params.extend([search_query, search_query])

            # 添加过滤条件
            if category:
                search_conditions.append("category = ?")
                params.append(category)
            if priority:
                search_conditions.append("priority = ?")
                params.append(priority)
            if tags:
                for tag in tags_list:
                    search_conditions.append("tags LIKE ?")
                    params.append(f"%{tag}%")

            sql = f"SELECT * FROM notes WHERE {' AND '.join(search_conditions)} ORDER BY updated_at DESC"
            result = await d1.execute_query(sql, params)
            if result and result.get('success') is False:
                return _d1_error_response(d1, "Search notes failed") or {"success": False, "error": result.get("error", "Search notes failed")}
            rows = [_normalize_note_record(row) for row in _extract_query_rows(result)]
            await _register_recent_notes_cache(rows, "notepad_manager.search")

            return {"success": True, "data": rows, "notes": rows, "count": len(rows), "alias_hint": "Use note_1, note_2, ... from this result for follow-up note tools."}

        elif action == "filter":
            # 实现过滤逻辑
            conditions = []
            params = []

            if category:
                conditions.append("category = ?")
                params.append(category)
            if priority:
                conditions.append("priority = ?")
                params.append(priority)
            if tags:
                for tag in tags_list:
                    conditions.append("tags LIKE ?")
                    params.append(f"%{tag}%")
            if start_date:
                conditions.append("created_at >= ?")
                params.append(start_date)
            if end_date:
                conditions.append("created_at <= ?")
                params.append(end_date)

            if conditions:
                sql = f"SELECT * FROM notes WHERE {' AND '.join(conditions)} ORDER BY updated_at DESC"
                result = await d1.execute_query(sql, params)
            else:
                sql = "SELECT * FROM notes ORDER BY updated_at DESC LIMIT 50"
                result = await d1.execute_query(sql)

            if result and result.get('success') is False:
                return _d1_error_response(d1, "Filter notes failed") or {"success": False, "error": result.get("error", "Filter notes failed")}
            rows = [_normalize_note_record(row) for row in _extract_query_rows(result)]
            await _register_recent_notes_cache(rows, "notepad_manager.filter")
            return {"success": True, "data": rows, "notes": rows, "count": len(rows), "alias_hint": "Use note_1, note_2, ... from this result for follow-up note tools."}

        elif action == "add_tag":
            if not note_id or not tags:
                return {"success": False, "error": "note_id and tags are required for add_tag action"}

            tag = tags_list[0] if tags_list else tags
            note, resolved_note_id = await _resolve_note_id_for_write(d1, note_id)
            if not note or not resolved_note_id:
                d1_error = _d1_error_response(d1, "Failed to resolve note")
                if d1_error:
                    return d1_error
                return {"success": False, "error": "Note not found"}

            current_tags = _parse_tags(note.get('tags'))

            if tag not in current_tags:
                current_tags.append(tag)
                new_tags = ','.join(current_tags)
                result = await d1.update_note(resolved_note_id, {'tags': new_tags, 'updated_at': datetime.now(BEIJING_TIMEZONE).isoformat()})
                if result:
                    return {"success": True, "note_id": resolved_note_id, "tags": current_tags, "message": f"Tag '{tag}' added successfully"}
                else:
                    return {"success": False, "error": "Failed to add tag"}
            else:
                return {"success": True, "message": f"Tag '{tag}' already exists"}

        elif action == "remove_tag":
            if not note_id or not tags:
                return {"success": False, "error": "note_id and tags are required for remove_tag action"}

            tag = tags_list[0] if tags_list else tags
            note, resolved_note_id = await _resolve_note_id_for_write(d1, note_id)
            if not note or not resolved_note_id:
                d1_error = _d1_error_response(d1, "Failed to resolve note")
                if d1_error:
                    return d1_error
                return {"success": False, "error": "Note not found"}

            current_tags = _parse_tags(note.get('tags'))

            if tag in current_tags:
                current_tags.remove(tag)
                new_tags = ','.join(current_tags)
                result = await d1.update_note(resolved_note_id, {'tags': new_tags, 'updated_at': datetime.now(BEIJING_TIMEZONE).isoformat()})
                if result:
                    return {"success": True, "note_id": resolved_note_id, "tags": current_tags, "message": f"Tag '{tag}' removed successfully"}
                else:
                    return {"success": False, "error": "Failed to remove tag"}
            else:
                return {"success": True, "message": f"Tag '{tag}' not found"}

        elif action == "get_tags":
            # 获取所有标签
            sql = "SELECT DISTINCT tags FROM notes WHERE tags IS NOT NULL AND tags != ''"
            result = await d1.execute_query(sql)
            if result and result.get('success') is False:
                return _d1_error_response(d1, "Get tags failed") or {"success": False, "error": result.get("error", "Get tags failed")}

            all_tags = set()
            for row in _extract_query_rows(result):
                tags_str = row.get('tags', '')
                if tags_str:
                    tags_list_from_db = [tag.strip() for tag in tags_str.split(',') if tag.strip()]
                    all_tags.update(tags_list_from_db)

            return {"success": True, "data": sorted(list(all_tags))}

        elif action == "statistics":
            # 获取统计信息
            stats = {}

            # 笔记总数
            count_rows = _extract_query_rows(await d1.execute_query("SELECT COUNT(*) as count FROM notes"))
            stats['total_notes'] = (count_rows[0].get('count') if count_rows else 0)

            # 按分类统计
            cat_rows = _extract_query_rows(await d1.execute_query("SELECT category, COUNT(*) as count FROM notes GROUP BY category"))
            stats['by_category'] = {row['category']: row['count'] for row in cat_rows}

            # 按优先级统计
            pri_rows = _extract_query_rows(await d1.execute_query("SELECT priority, COUNT(*) as count FROM notes GROUP BY priority"))
            stats['by_priority'] = {row['priority']: row['count'] for row in pri_rows}

            # 最近7天创建的笔记
            seven_days_ago = (datetime.now(BEIJING_TIMEZONE) - timedelta(days=7)).isoformat()
            recent_rows = _extract_query_rows(await d1.execute_query("SELECT COUNT(*) as count FROM notes WHERE created_at >= ?", [seven_days_ago]))
            stats['recent_notes'] = (recent_rows[0].get('count') if recent_rows else 0)

            return {"success": True, "data": stats}

        elif action == "create_from_text":
            # 智能创建笔记，自动分类和提取标签
            if not content:
                return {"success": False, "error": "content is required for create_from_text action"}

            # 自动生成标题
            if not title:
                lines = content.strip().split('\n')
                title = lines[0][:50] if lines[0].strip() else f"笔记 - {datetime.now(BEIJING_TIMEZONE).strftime('%Y-%m-%d %H:%M')}"

            # 智能分类
            if auto_categorize and not category:
                category = _auto_categorize_content(content).value

            # 自动提取标签 - 使用新的智能关键词提取
            if not tags:
                smart_keywords = _extract_smart_keywords(content, max_keywords=5)
                tags = ','.join(smart_keywords)

            # 生成自动摘要
            auto_summary = _generate_auto_summary(content)

            # 创建笔记
            note_category = NoteCategory(category) if category else NoteCategory.OTHER
            note_id = str(uuid.uuid4())
            current_time = datetime.now(BEIJING_TIMEZONE).isoformat()

            note_data = {
                'id': note_id,
                'title': title,
                'content': content,
                'created_at': current_time,
                'updated_at': current_time,
                'category': note_category.value,
                'priority': NotePriority.MEDIUM.value,
                'tags': tags,
                'reminder_id': None,
                'file_ids': ''
            }

            logger.info(f"[NOTEPAD_MANAGER] Creating smart note with content length: {len(content)}")
            result = await d1.insert_note(note_data)
            if result:
                logger.info(f"[NOTEPAD_MANAGER] Smart note created successfully: {note_data['id']}")
                note_record = _normalize_note_record(note_data)
                await _cache_note_alias(note_record, NOTE_LATEST_ALIAS, "notepad_manager.create_from_text")
                return {
                    "success": True,
                    "note": note_record,
                    "data": note_record,
                    "note_id": note_data["id"],
                    "alias": NOTE_LATEST_ALIAS,
                    "message": "Smart note created successfully",
                }
            else:
                logger.error(f"[NOTEPAD_MANAGER] Failed to create smart note")
                return {"success": False, "error": "Failed to create smart note"}

        else:
            return {"success": False, "error": f"Unknown action: {action}"}

    except Exception as e:
        logger.error(f"[NOTEPAD_MANAGER] Error in action {action}: {e}", exc_info=True)
        return {"success": False, "error": str(e)}

# ==================== 路由2: 文件和提醒管理 ====================

@mcp.tool()
async def content_manager(
    action: str,
    file_id: Optional[str] = None,
    reminder_id: Optional[str] = None,
    name: Optional[str] = None,
    content: Optional[str] = None,
    file_type: Optional[str] = None,
    size: Optional[int] = None,
    content_type: Optional[str] = None,
    title: Optional[str] = None,
    remind_at: Optional[str] = None,
    reminder_type: Optional[str] = None,
    priority: Optional[str] = None,
    notify_methods: Optional[str] = None,  # 改为字符串，用逗号分隔
    email_to: Optional[str] = None,
    email_confirmed: bool = False,
    query: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> Dict:
    """
    Purpose: File & Reminder route (upload/download/remove file; create/get/delete reminder; system ops)
    When: Manage files/reminders/system via a single entry

    Supported actions:
    - Files: upload_file, get_file, delete_file
    - Reminders: create_reminder, get_reminder, delete_reminder
    - System: backup_data, get_system_status

    Required: action
    Optional: file_id, reminder_id, name, content, file_type, size, content_type, title, remind_at, reminder_type, priority, notify_methods(str), email_to, query, start_date, end_date
    Returns: {"success": bool, ...}
    Notes: notify_methods is comma-separated (e.g., "email,sms"); file content should be base64 for binary payloads, plain text for UTF-8 documents. Requires Cloudflare D1 + KV credentials in CLOUDFLARE_* configuration.
    """
    logger.info(f"[CONTENT_MANAGER] Action: {action}")

    # 检查初始化状态
    if not await check_initialization():
        return {"success": False, "error": "Service not fully initialized yet. Please try again later."}

    try:
        d1 = get_d1_service()
        kv = get_kv_service()

        # 文件操作
        if action == "upload_file":
            if not all([name, content, file_type, content_type]):
                return {"success": False, "error": "name, content, file_type, content_type are required"}

            # 解析输入内容（优先解码base64）
            raw_bytes: Optional[bytes] = None
            text_payload: Optional[str] = None
            if isinstance(content, str):
                try:
                    raw_bytes = base64.b64decode(content, validate=True)
                except (ValueError, TypeError):
                    text_payload = content
            else:
                raw_bytes = content if isinstance(content, (bytes, bytearray)) else None

            if raw_bytes is None and text_payload is None:
                return {"success": False, "error": "content must be base64 string or UTF-8 text"}

            if raw_bytes is None and text_payload is not None:
                raw_bytes = text_payload.encode('utf-8')

            computed_size = len(raw_bytes or b"")
            recorded_size = size if size is not None else computed_size

            file_data = {
                'id': str(uuid.uuid4()),
                'name': name,
                'type': FileType(file_type).value,
                'size': recorded_size,
                'content_type': content_type,
                'created_at': datetime.now(BEIJING_TIMEZONE).isoformat(),
                'updated_at': datetime.now(BEIJING_TIMEZONE).isoformat(),
                'note_id': None,
                'metadata': {
                    'stored_via': 'kv',
                    'original_encoding': 'base64' if text_payload is None else 'utf-8'
                }
            }

            # 存储文件内容到KV
            kv_key = f"file_content:{file_data['id']}"
            file_data['kv_key'] = kv_key

            await kv.put_value(kv_key, raw_bytes if raw_bytes is not None else text_payload)

            # 存储文件元数据到D1
            result = await d1.insert_file_metadata(file_data)
            if result:
                return {"success": True, "file_id": file_data['id'], "message": "File uploaded successfully"}
            else:
                return {"success": False, "error": "Failed to upload file metadata"}

        elif action == "get_file":
            if not file_id:
                return {"success": False, "error": "file_id is required"}

            # 获取文件元数据
            file_metadata = await d1.get_file_metadata(file_id)
            if not file_metadata:
                return {"success": False, "error": "File not found"}

            # 判断存储介质，并读取内容（统一以base64返回）
            meta = file_metadata.get('metadata') or {}
            stored_via = (meta.get('stored_via') or '').lower()
            kv_key = file_metadata.get('kv_key') or f"file_content:{file_id}"

            import base64
            raw_content = None
            if stored_via == 'r2':
                try:
                    from services.r2_service import get_r2_service
                    r2 = get_r2_service()
                    raw_content = await r2.get_object(kv_key)
                except Exception as re:
                    logger.warning(f"[FILES] R2读取失败，回退KV: {re}")
                    raw_content = await kv.get_file_content(kv_key)
            else:
                raw_content = await kv.get_file_content(kv_key)

            if raw_content is None:
                content_b64 = None
            elif isinstance(raw_content, bytes):
                content_b64 = base64.b64encode(raw_content).decode('utf-8')
            else:
                content_b64 = base64.b64encode(raw_content.encode('utf-8')).decode('utf-8')

            file_data = dict(file_metadata)
            file_data['content'] = content_b64
            file_data['encoding'] = 'base64'

            return {"success": True, "data": file_data}

        elif action == "delete_file":
            if not file_id:
                return {"success": False, "error": "file_id is required"}

            # 删除文件内容/对象（根据存储介质）
            meta = await d1.get_file_metadata(file_id)
            stored_via = (meta.get('metadata', {}) or {}).get('stored_via', '').lower() if meta else ''
            kv_key = (meta or {}).get('kv_key') or f"file_content:{file_id}"
            if stored_via == 'r2':
                try:
                    from services.r2_service import get_r2_service
                    r2 = get_r2_service()
                    await r2.delete_object(kv_key)
                except Exception as de:
                    logger.warning(f"[FILES] 删除R2对象失败: {de}")
            else:
                await kv.delete_value(kv_key)

            # 删除文件元数据
            result = await d1.delete_file(file_id)
            if result:
                return {"success": True, "message": "File deleted successfully"}
            else:
                return {"success": False, "error": "Failed to delete file metadata"}

        # 提醒操作
        elif action == "create_reminder":
            if not title:
                return {"success": False, "error": "title is required for create_reminder"}
            if not email_to:
                logger.info("[REMINDER_CREATE] Clarification required: missing email_to title=%s", title)
                return {
                    "success": False,
                    "needs_clarification": True,
                    "required_field": "email_to",
                    "message": "请先确认提醒邮件发送到哪个邮箱。",
                    "suggested_question": "这个提醒要发送到哪个邮箱？",
                    "next_call_hint": "用户明确说出收件邮箱后，用同一标题和时间再次调用，并传 email_to 与 email_confirmed=true。"
                }
            if not _is_valid_email(email_to):
                logger.info("[REMINDER_CREATE] Clarification required: invalid email_to title=%s email=%s", title, _mask_email(email_to))
                return {
                    "success": False,
                    "needs_clarification": True,
                    "required_field": "email_to",
                    "message": "提醒邮箱格式不正确，请提供一个有效邮箱地址。",
                    "suggested_question": "请确认提醒邮件要发送到哪个有效邮箱？"
                }
            if not email_confirmed:
                logger.info("[REMINDER_CREATE] Clarification required: email not confirmed title=%s email=%s", title, _mask_email(email_to))
                return {
                    "success": False,
                    "needs_clarification": True,
                    "required_field": "email_confirmed",
                    "message": f"请先确认提醒邮件是否发送到 {email_to}。",
                    "suggested_question": f"提醒邮件发送到 {email_to} 吗？如果不是，请告诉我邮箱。",
                    "next_call_hint": "如果用户已在当前对话明确提供或确认这个邮箱，再次调用时传 email_confirmed=true。"
                }

            # 处理notify_methods字符串
            notify_methods_list = []
            if notify_methods:
                notify_methods_list = [method.strip() for method in notify_methods.split(',') if method.strip()]

            reminder_data = {
                'id': str(uuid.uuid4()),
                'title': title,
                'content': content or '',
                'remind_at': remind_at,
                'type': ReminderType(reminder_type).value if reminder_type else ReminderType.SCHEDULED.value,
                'priority': ReminderPriority(priority).value if priority else ReminderPriority.MEDIUM.value,
                'status': ReminderStatus.PENDING.value,
                'created_at': datetime.now(BEIJING_TIMEZONE).isoformat(),
                'updated_at': datetime.now(BEIJING_TIMEZONE).isoformat(),
                'notify_methods': notify_methods_list or [NotifyMethod.EMAIL.value],
                'email_to': email_to,
                'recurrence': None,
                'condition': None
            }

            result = await d1.create_reminder(reminder_data)
            if result:
                return {"success": True, "reminder_id": reminder_data['id'], "message": "Reminder created successfully"}
            else:
                return {"success": False, "error": "Failed to create reminder"}

        elif action == "get_reminder":
            if not reminder_id:
                return {"success": False, "error": "reminder_id is required"}

            reminder = await d1.get_reminder(reminder_id)
            if reminder:
                return {"success": True, "reminder": reminder}
            else:
                return {"success": False, "error": "Reminder not found"}

        elif action == "update_reminder":
            if not reminder_id:
                return {"success": False, "error": "reminder_id is required for update_reminder"}

            update_data = {}
            if title is not None:
                update_data['title'] = title
            if content is not None:
                update_data['content'] = content
            if remind_at is not None:
                update_data['remind_at'] = remind_at
            if reminder_type is not None:
                update_data['type'] = ReminderType(reminder_type).value
            if priority is not None:
                update_data['priority'] = ReminderPriority(priority).value
            if notify_methods is not None:
                notify_methods_list = [method.strip() for method in notify_methods.split(',') if method.strip()]
                update_data['notify_methods'] = notify_methods_list
            if email_to is not None:
                if not _is_valid_email(email_to):
                    return {"success": False, "error": "Invalid email_to"}
                if not email_confirmed:
                    return {
                        "success": False,
                        "needs_clarification": True,
                        "required_field": "email_confirmed",
                        "message": f"请先确认提醒邮件是否发送到 {email_to}。",
                        "suggested_question": f"提醒邮件发送到 {email_to} 吗？如果不是，请告诉我邮箱。"
                    }
                update_data['email_to'] = email_to

            if update_data:
                update_data['updated_at'] = datetime.now(BEIJING_TIMEZONE).isoformat()
                result = await d1.update_reminder(reminder_id, update_data)
                if result:
                    return {"success": True, "message": "Reminder updated successfully"}
                else:
                    return {"success": False, "error": "Failed to update reminder"}
            else:
                return {"success": False, "error": "No update data provided"}

        elif action == "delete_reminder":
            if not reminder_id:
                return {"success": False, "error": "reminder_id is required"}

            result = await d1.delete_reminder(reminder_id)
            if result:
                return {"success": True, "message": "Reminder deleted successfully"}
            else:
                return {"success": False, "error": "Reminder not found or failed to delete"}

        elif action == "search_files":
            if not query:
                return {"success": False, "error": "query is required for search_files action"}

            # 实现文件搜索逻辑
            search_conditions = ["name LIKE ?"]
            params = [f"%{query}%"]

            if file_type:
                search_conditions.append("type = ?")
                params.append(file_type)
            if start_date:
                search_conditions.append("created_at >= ?")
                params.append(start_date)
            if end_date:
                search_conditions.append("created_at <= ?")
                params.append(end_date)

            sql = f"SELECT * FROM files WHERE {' AND '.join(search_conditions)} ORDER BY updated_at DESC"
            result = await d1.execute_query(sql, params)
            rows = _extract_query_rows(result)

            return {"success": True, "data": rows, "count": len(rows)}

        # 系统操作
        elif action == "get_system_status":
            status = {
                "d1_service": "available",
                "kv_service": "available",
                "gmail_service": "checking...",
                "timestamp": datetime.now(BEIJING_TIMEZONE).isoformat()
            }
            return {"success": True, "data": status}

        elif action == "get_usage_stats":
            # 获取使用统计
            stats = {}

            # 文件统计
            result = await d1.execute_query("SELECT COUNT(*) as count, SUM(size) as total_size FROM files")
            file_rows = _extract_query_rows(result)
            file_stats = file_rows[0] if file_rows else {}
            stats['files'] = {
                'total_count': file_stats.get('count', 0),
                'total_size': file_stats.get('total_size', 0)
            }

            # 提醒统计
            rem_rows = _extract_query_rows(await d1.execute_query("SELECT COUNT(*) as count FROM reminders"))
            stats['reminders'] = {
                'total_count': rem_rows[0].get('count', 0) if rem_rows else 0
            }

            # 按状态统计提醒
            status_rows = _extract_query_rows(await d1.execute_query("SELECT status, COUNT(*) as count FROM reminders GROUP BY status"))
            stats['reminders']['by_status'] = {row['status']: row['count'] for row in status_rows}

            return {"success": True, "data": stats}

        elif action == "backup_data":
            # 简单的备份逻辑
            backup_info = {
                "backup_id": str(datetime.now(BEIJING_TIMEZONE).timestamp()),
                "timestamp": datetime.now(BEIJING_TIMEZONE).isoformat(),
                "status": "completed"
            }
            return {"success": True, "data": backup_info}

        else:
            return {"success": False, "error": f"Unknown action: {action}"}

    except Exception as e:
        logger.error(f"[CONTENT_MANAGER] Error in action {action}: {e}", exc_info=True)
        return {"success": False, "error": str(e)}

# ==================== 路由3: 邮件集成管理 ====================

@mcp.tool()
async def email_manager(
    action: str,
    to: Optional[str] = None,
    subject: Optional[str] = None,
    body: Optional[str] = None,
    cc: Optional[str] = None,
    note_id: Optional[str] = None,
    note_object: Optional[Dict] = None,
    file_id: Optional[str] = None,
    reminder_id: Optional[str] = None,
    email_id: Optional[str] = None,
    email_ids: Optional[str] = None,
    mailbox: str = 'inbox',
    max_results: int = 10,
    query: Optional[str] = None,
    email_type: str = "attachment",
    date_range: Optional[str] = None,
    category: Optional[str] = None,
    title: Optional[str] = None,
    content: Optional[str] = None,
    include_summary: Optional[bool] = None
) -> Dict:
    """
    Purpose: Email route (Gmail base + note/file integration)
    When: Send/list/read/trash emails; email notes/files via one entry

    Supported actions:
    - Base: send_email, list_emails, get_email, trash_email, mark_read, mark_unread, batch_trash
    - Notes: send_note_email, send_note_body, send_reminder_email, send_notes_summary, create_note_and_email
    - Files: download_email_attachments, send_email_with_file_attachment, send_file_email

    Required: action
    Optional: to, subject, body, cc, note_id, file_id, reminder_id, email_id, email_ids(csv), mailbox, max_results, query, email_type("body"|"attachment"), date_range, category, title, content
    Returns: {"success": bool, ...}
    Notes: auto ensure_gmail_service; note ID lookup uses fallback matching; supports common office/text attachments. Requires SERVICE_CONFIG.enable_gmail_integration and valid Gmail credentials/token.
    """
    logger.info(f"[EMAIL_MANAGER] Action: {action}")

    try:
        # 确保Gmail服务可用
        is_available, message = await ensure_gmail_service()
        if not is_available and action.startswith(('send_', 'list_', 'get_', 'trash_', 'mark_', 'batch_')):
            return {"success": False, "error": f"Gmail服务不可用: {message}"}

        # Gmail基础操作
        if action == "send_email":
            if not all([to, subject, body]):
                return {"success": False, "error": "to, subject, body are required"}

            result = gmail_service.send_email(to, subject, body, cc)
            return result

        elif action == "list_emails":
            result = gmail_service.list_emails(mailbox, max_results, query)
            return result

        elif action == "get_email":
            if not email_id:
                return {"success": False, "error": "email_id is required"}

            logger.info(f"[EMAIL_MANAGER] Getting email content for ID: {email_id}")
            resolved_id, error = await _get_resolved_email_id(email_id, "EMAIL_MANAGER_GET_EMAIL")
            if error:
                return error

            try:
                result = gmail_service.get_email_content(resolved_id)
                logger.info(f"[EMAIL_MANAGER] Email content result: {result.get('success', False)} (id={resolved_id})")
                if not result.get('success'):
                    logger.warning(f"[EMAIL_MANAGER] Email content failed: {result.get('error')}")
                return result
            except Exception as e:
                logger.error(f"[EMAIL_MANAGER] Exception getting email content: {e}")
                return {"success": False, "error": f"Failed to get email content: {str(e)}"}

        elif action == "trash_email":
            if not email_id:
                return {"success": False, "error": "email_id is required"}

            resolved_id, error = await _get_resolved_email_id(email_id, "EMAIL_MANAGER_TRASH_EMAIL")
            if error:
                return error

            result = gmail_service.trash_email(resolved_id)
            return result

        elif action == "mark_read":
            if not email_id:
                return {"success": False, "error": "email_id is required"}

            resolved_id, error = await _get_resolved_email_id(email_id, "EMAIL_MANAGER_MARK_READ")
            if error:
                return error

            result = gmail_service.mark_as_read(resolved_id)
            return result

        elif action == "mark_unread":
            if not email_id:
                return {"success": False, "error": "email_id is required"}

            resolved_id, error = await _get_resolved_email_id(email_id, "EMAIL_MANAGER_MARK_UNREAD")
            if error:
                return error

            result = gmail_service.mark_as_unread(resolved_id)
            return result

        elif action == "batch_trash":
            if not email_ids:
                return {"success": False, "error": "email_ids string is required"}

            ids_list = _parse_tags(email_ids)
            if not ids_list:
                return {"success": False, "error": "No valid email_ids provided"}

            resolved_ids, unresolved = await _resolve_email_id_list(ids_list, "EMAIL_MANAGER_BATCH_TRASH")
            if unresolved:
                unresolved_str = ", ".join(unresolved)
                return {"success": False, "error": f"无法识别以下邮件别名: {unresolved_str}。请调用 get_recent_emails 刷新列表后再试。"}

            result = gmail_service.batch_trash_emails(resolved_ids)
            return result
        # 笔记邮件集成操作
        elif action == "send_note_email":
            if not (note_id or note_object) or not to:
                return {"success": False, "error": "note_id or note_object and to are required"}
            if not _is_valid_email(to):
                return {"success": False, "error": "Invalid recipient email"}

            note = note_object
            if not note:
                # 获取笔记内容（含回退查找，防止ID被截断/口述识别误差）
                d1 = get_d1_service()
                note = await _resolve_note_reference(d1, note_id, allow_recent=True)
                if not note:
                    logger.warning(f"[EMAIL_MANAGER] Note not found for id={note_id}")
                    return {"success": False, "error": "Note not found"}

            title_val = (note.get('title') or '').strip() or f"未命名笔记({note.get('id','')})"
            content_val = note.get('content', '')

            # 根据email_type决定发送方式
            if email_type == "body":
                email_subject = subject or f"笔记: {title_val}"
                email_body = _format_text_body(f"笔记标题: {title_val}\n\n{content_val}\n\n— 本邮件由记事本服务自动发送")
                result = gmail_service.send_email(to, email_subject, email_body, cc)
            else:  # attachment
                email_subject = subject or f"笔记附件: {title_val}"
                email_body = body or f"请查看附件中的笔记: {title_val}"
                # 实际附件发送
                safe_filename = _safe_filename(title_val, f"note_{note.get('id','')}") + ".txt"
                attachment = {
                    'filename': safe_filename,
                    'content': content_val,
                    'content_type': 'text/plain; charset=utf-8'
                }
                result = gmail_service.send_email_with_attachment(
                    to=to,
                    subject=email_subject,
                    body=_format_text_body(email_body),
                    attachment_data=attachment['content'],
                    attachment_filename=attachment['filename'],
                    attachment_content_type=attachment['content_type'],
                    cc=cc
                )

            return result

        elif action == "send_file_email":
            if not all([file_id, to]):
                return {"success": False, "error": "file_id and to are required"}
            if not _is_valid_email(to):
                return {"success": False, "error": "Invalid recipient email"}

            # 获取文件内容
            file_result = await _invoke_tool(content_manager, "get_file", file_id=file_id)
            if not file_result.get("success"):
                return {"success": False, "error": file_result.get("error", "File not found")}

            file_data = file_result.get("data") or {}
            if not file_data:
                return {"success": False, "error": "File not found"}

            if not file_data.get('content'):
                return {"success": False, "error": "File content not available"}
            file_name = file_data.get('name') or f"file_{file_id}"
            email_subject = subject or f"文件: {file_name}"
            email_body = (body or f"请查看附件中的文件: {file_name}")

            # 实际附件发送
            attachment = {
                'filename': file_name,
                'content': file_data.get('content', ''),
                'content_type': file_data.get('content_type') or 'application/octet-stream'
            }
            result = gmail_service.send_email_with_attachment(
                to=to,
                subject=email_subject,
                body=_format_text_body(email_body),
                attachment_data=attachment['content'],
                attachment_filename=attachment['filename'],
                attachment_content_type=attachment['content_type'],
                cc=cc
            )
            return result

        elif action == "send_note_body":
            if not all([note_id, to]):
                return {"success": False, "error": "note_id and to are required"}
            if not _is_valid_email(to):
                return {"success": False, "error": "Invalid recipient email"}

            # 获取笔记内容（含回退查找）
            d1 = get_d1_service()
            note = await _resolve_note_reference(d1, note_id, allow_recent=True)
            if not note:
                return {"success": False, "error": "Note not found"}

            # 发送笔记内容作为邮件正文
            title_val = (note.get('title') or '').strip() or f"未命名笔记({note.get('id','')})"
            content_val = note.get('content', '')
            email_subject = subject or f"笔记: {title_val}"
            email_body = _format_text_body(f"笔记标题: {title_val}\n\n{content_val}\n\n— 本邮件由记事本服务自动发送")
            result = gmail_service.send_email(to, email_subject, email_body, cc)
            return result

        elif action == "send_reminder_email":
            if not all([reminder_id, to]):
                return {"success": False, "error": "reminder_id and to are required"}

            # 获取提醒内容
            d1 = get_d1_service()
            reminder = await d1.get_reminder(reminder_id)
            if not reminder:
                return {"success": False, "error": "Reminder not found"}

            # 发送提醒邮件
            email_subject = subject or f"提醒: {reminder['title']}"
            email_body = _format_text_body(body or f"提醒标题: {reminder['title']}\n\n{reminder['content']}\n\n提醒时间: {reminder.get('remind_at', '未设置')}")
            result = gmail_service.send_email(to, email_subject, email_body, cc)
            return result

        elif action == "send_notes_summary":
            if not to:
                return {"success": False, "error": "to is required"}

            # 获取笔记摘要
            d1 = get_d1_service()
            conditions = []
            params = []

            if date_range:
                # 解析日期范围，例如 "7days", "1month"
                if date_range == "7days":
                    start_date = (datetime.now(BEIJING_TIMEZONE) - timedelta(days=7)).isoformat()
                elif date_range == "1month":
                    start_date = (datetime.now(BEIJING_TIMEZONE) - timedelta(days=30)).isoformat()
                else:
                    start_date = date_range

                conditions.append("created_at >= ?")
                params.append(start_date)

            if category:
                conditions.append("category = ?")
                params.append(category)

            if conditions:
                sql = f"SELECT * FROM notes WHERE {' AND '.join(conditions)} ORDER BY created_at DESC LIMIT 20"
                result = await d1.execute_query(sql, params)
            else:
                sql = "SELECT * FROM notes ORDER BY created_at DESC LIMIT 20"
                result = await d1.execute_query(sql)

            notes = _extract_query_rows(result)

            # 生成摘要邮件
            email_subject = subject or f"笔记摘要 - {datetime.now(BEIJING_TIMEZONE).strftime('%Y-%m-%d')}"
            email_body = "笔记摘要\n" + "="*50 + "\n\n"

            for note in notes:
                email_body += f"标题: {note['title']}\n"
                email_body += f"分类: {note.get('category', '未分类')}\n"
                email_body += f"创建时间: {note['created_at']}\n"
                email_body += f"内容预览: {note['content'][:100]}...\n"
                email_body += "-" * 30 + "\n\n"

            if not notes:
                email_body += "没有找到符合条件的笔记。\n"

            result = gmail_service.send_email(to, email_subject, email_body, cc)
            return result

        elif action == "download_email_attachments":
            if not email_id:
                return {"success": False, "error": "email_id is required"}

            logger.info(f"[EMAIL_MANAGER] Downloading attachments for email: {email_id}")
            resolved_id, error = await _get_resolved_email_id(email_id, "EMAIL_MANAGER_DOWNLOAD_ATTACHMENTS")
            if error:
                return error

            attachments_result = gmail_service.get_email_attachments(resolved_id)
            if not attachments_result.get("success"):
                return {"success": False, "error": attachments_result.get("error")}

            return attachments_result

        elif action == "send_email_with_file_attachment":
            if not all([to, subject, file_id]):
                return {"success": False, "error": "to, subject, file_id are required"}

            # 获取文件内容
            d1 = get_d1_service()
            kv = get_kv_service()

            # 获取文件元数据
            file_metadata = await d1.get_file(file_id)
            if not file_metadata:
                return {"success": False, "error": "File not found"}

            # 获取文件内容
            kv_key = f"file_content:{file_id}"
            file_content = await kv.get_value(kv_key)
            if not file_content:
                return {"success": False, "error": "File content not found"}

            # 发送带附件的邮件
            email_body = _format_text_body(body or f"请查看附件：{file_metadata['name']}")
            result = gmail_service.send_email_with_attachment(
                to=to,
                subject=subject,
                body=email_body,
                cc=cc,
                attachment_data=file_content,
                attachment_filename=file_metadata['name'],
                attachment_content_type=file_metadata['content_type']
            )

            return result

        elif action == "create_note_and_email":
            if not all([title, content, to]):
                return {"success": False, "error": "title, content, to are required"}

            # 创建笔记
            d1 = get_d1_service()
            note_data = {
                'id': str(uuid.uuid4()),
                'title': title,
                'content': content,
                'created_at': datetime.now(BEIJING_TIMEZONE).isoformat(),
                'updated_at': datetime.now(BEIJING_TIMEZONE).isoformat(),
                'category': NoteCategory.OTHER.value,
                'priority': NotePriority.MEDIUM.value,
                'tags': '',
                'reminder_id': None,
                'file_ids': ''
            }

            logger.info(f"[EMAIL_MANAGER] Creating note with content length: {len(content)}")
            result = await d1.insert_note(note_data)  # 修复方法名
            if not result:
                logger.error(f"[EMAIL_MANAGER] Failed to create note")
                return {"success": False, "error": "Failed to create note"}

            # 确保Gmail可用（create_* 不在通用ensure范围内，这里显式保证）
            is_available, message = await ensure_gmail_service()
            if not is_available:
                return {"success": False, "error": f"Gmail服务不可用: {message}", "note_id": note_data['id']}

            # 发送邮件
            if email_type == "body":
                email_subject = subject or f"笔记: {note_data['title']}"
                email_body = _format_text_body(f"笔记标题: {note_data['title']}\n\n{note_data['content']}\n\n— 本邮件由记事本服务自动发送")
                email_result = gmail_service.send_email(to, email_subject, email_body, cc)
            else:  # attachment
                email_subject = subject or f"笔记附件: {note_data['title']}"
                email_body = _format_text_body(body or f"请查看附件中的笔记: {note_data['title']}")
                safe_filename = _safe_filename(note_data['title'], f"note_{note_data['id']}") + ".txt"
                email_result = gmail_service.send_email_with_attachment(
                    to=to,
                    subject=email_subject,
                    body=email_body,
                    attachment_data=note_data['content'],
                    attachment_filename=safe_filename,
                    attachment_content_type='text/plain; charset=utf-8',
                    cc=cc
                )

            return {
                "success": email_result.get("success", False),
                "note_id": note_data['id'],
                "email_result": email_result
            }

        else:
            return {"success": False, "error": f"Unknown action: {action}"}

    except Exception as e:
        logger.error(f"[EMAIL_MANAGER] Error in action {action}: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@mcp.tool()
async def list_reminders(limit: int = 50, status: Optional[str] = None,
                         start_from: Optional[str] = None) -> Dict:
    """
    Purpose: List reminders with optional status/time filtering
    Optional: limit(50), status("pending"|"completed"|...), start_from(iso datetime)
    Returns: {"success": bool, "reminders": [...], "count": int}
    Notes: Requires Cloudflare D1; results ordered by remind_at desc.
    """
    try:
        d1 = get_d1_service()
        if not await d1.initialize_tables():
            return {"success": False, "error": "D1 database initialization failed"}
        conditions: List[str] = []
        params: List[Any] = []

        if status:
            conditions.append("status = ?")
            params.append(status.lower())
        if start_from:
            conditions.append("remind_at >= ?")
            params.append(start_from)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = (
            "SELECT id, title, content, type, remind_at, priority, status, notify_methods, created_at, updated_at "
            f"FROM reminders {where_clause} ORDER BY datetime(remind_at) DESC LIMIT ?"
        )
        params.append(max(limit, 1))

        result = await d1.execute_query(sql, params)
        if not result or result.get('success') is False:
            error = result.get('error') or result.get('errors') if isinstance(result, dict) else "D1 query failed"
            return {"success": False, "error": str(error)}
        rows = _extract_query_rows(result)

        reminders: List[Dict[str, Any]] = []
        for row in rows:
            entry = dict(row)
            notify_methods = entry.get('notify_methods')
            if isinstance(notify_methods, str):
                try:
                    entry['notify_methods'] = json.loads(notify_methods)
                except json.JSONDecodeError:
                    entry['notify_methods'] = [
                        method.strip()
                        for method in notify_methods.replace('，', ',').replace('、', ',').split(',')
                        if method.strip()
                    ]
            reminders.append(entry)

        return {"success": True, "reminders": reminders, "count": len(reminders)}
    except Exception as e:
        logger.error(f"[LIST_REMINDERS] Error: {e}")
        return {"success": False, "error": str(e)}

# ==================== 路由5: 增强邮件附件功能 ====================

@mcp.tool()
async def send_note_as_email_attachment(
    note_id: str = None,
    to: str = None,
    subject: Optional[str] = None,
    body: Optional[str] = None,
    cc: Optional[str] = None,
    note_object: Optional[Dict] = None
) -> Dict:
    """
    Purpose: Send a note as text attachment
    When: Need note content as file attachment
    Required: note_id, to
    Optional: subject, body, cc
    Returns: {"success": bool, ...}
    Notes: Ensures Gmail; safe filename; text body formatted. Requires Gmail integration to be enabled and configured.
    """
    logger.info(f"[SEND_NOTE_ATTACHMENT] Sending note {note_id} as attachment to {to}")

    try:
        # 邮箱格式校验
        if not _is_valid_email(to):
            return {"success": False, "error": "Invalid recipient email"}

        # 确保Gmail服务可用
        is_available, message = await ensure_gmail_service()
        if not is_available:
            return {"success": False, "error": f"Gmail服务不可用: {message}"}

        note = note_object
        if not note:
            # 获取笔记内容（含回退查找）
            d1 = get_d1_service()
            note = await _resolve_note_reference(d1, note_id, allow_recent=True)
            if not note:
                return {"success": False, "error": "笔记未找到"}

        # 验证笔记内容
        note_title = note.get('title', '无标题笔记').strip()
        note_content = note.get('content', '').strip()

        if not note_content:
            return {"success": False, "error": "笔记内容为空，无法作为附件发送"}

        # 准备邮件内容
        email_subject = subject or f"笔记附件: {note_title}"
        email_body = body or f"""您好，

请查看附件中的笔记内容。

笔记信息：
- 标题: {note_title}
- 创建时间: {note.get('created_at', '未知')}
- 分类: {note.get('category', '未分类')}
- 优先级: {note.get('priority', '中等')}
- 标签: {', '.join(note.get('tags', [])) if note.get('tags') else '无'}

此邮件由小可爱的记事本服务自动发送。"""

        # 创建完整的笔记内容作为附件
        attachment_content = f"""笔记标题: {note_title}
创建时间: {note.get('created_at', '未知')}
最后更新: {note.get('updated_at', '未知')}
分类: {note.get('category', '未分类')}
优先级: {note.get('priority', '中等')}
标签: {', '.join(note.get('tags', [])) if note.get('tags') else '无'}

{'='*50}
笔记内容:
{'='*50}


{note_content}

{'='*50}
由记事本MCP服务生成 - {datetime.now(BEIJING_TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}
"""

        # 验证附件内容不为空
        if len(attachment_content.strip()) < 10:
            return {"success": False, "error": "生成的附件内容过短，可能存在问题"}

        # 创建安全的文件名
        safe_filename = "".join(c for c in note_title if c.isalnum() or c in (' ', '-', '_')).rstrip()
        if not safe_filename:
            safe_filename = f"note_{note_id}"
        safe_filename = f"{safe_filename}.txt"

        # 创建附件
        attachment = {
            'filename': safe_filename,
            'content': attachment_content,
            'content_type': 'text/plain; charset=utf-8'
        }

        logger.info(f"[SEND_NOTE_ATTACHMENT] Attachment created: {safe_filename}, size: {len(attachment_content)} chars")

        # 发送邮件
        result = gmail_service.send_email_with_attachment(
            to=to,
            subject=email_subject,
            body=_format_text_body(email_body),
            attachment_data=attachment['content'],
            attachment_filename=attachment['filename'],
            attachment_content_type=attachment['content_type'],
            cc=cc
        )

        if result.get('success'):
            logger.info(f"[SEND_NOTE_ATTACHMENT] Successfully sent note {note_id} as attachment")
            return {
                "success": True,
                "message_id": result.get('message_id'),
                "note_id": note_id,
                "attachment_filename": safe_filename,
                "attachment_size": len(attachment_content),
                "recipients": result.get('recipients', {})
            }
        else:
            logger.error(f"[SEND_NOTE_ATTACHMENT] Failed to send: {result.get('error')}")
            return {"success": False, "error": result.get('error', 'Unknown error')}

    except Exception as e:
        logger.error(f"[SEND_NOTE_ATTACHMENT] Exception: {e}")
        return {"success": False, "error": str(e)}

@mcp.tool()
async def send_note_as_html_email(
    note_id: str,
    to: str,
    subject: Optional[str] = None,
    cc: Optional[str] = None,
    include_summary: bool = True
) -> Dict:
    """
    Purpose: Send note as rich HTML email (with optional summary)
    Required: note_id, to
    Optional: subject, cc, include_summary(True)
    Returns: {"success": bool, ...}
    Notes: Ensures Gmail; includes optional auto-summary. Requires SERVICE_CONFIG.enable_gmail_integration and valid Gmail credentials/token.
    """
    logger.info(f"[SEND_NOTE_HTML] Sending note {note_id} as HTML email to {to}")

    try:
        # 邮箱格式校验
        if not _is_valid_email(to):
            return {"success": False, "error": "Invalid recipient email"}

        # 确保Gmail服务可用
        is_available, message = await ensure_gmail_service()
        if not is_available:
            return {"success": False, "error": f"Gmail服务不可用: {message}"}

        # 获取笔记内容（含回退查找）
        d1 = get_d1_service()
        note = await _resolve_note_reference(d1, note_id, allow_recent=True)
        if not note:
            return {"success": False, "error": "笔记未找到"}

        # 验证笔记内容
        note_title = note.get('title', '无标题笔记').strip()
        note_content = note.get('content', '').strip()

        if not note_content:
            return {"success": False, "error": "笔记内容为空，无法发送"}

        # 生成自动摘要（如果需要）
        auto_summary = ""
        if include_summary:
            auto_summary = _generate_auto_summary(note_content, max_length=150)

        # 创建精简的HTML邮件内容
        html_body = f"""
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
            <meta charset="utf-8">
            <title>{note_title}</title>
            <style>
                body {{
                    font-family: 'Microsoft YaHei', Arial, sans-serif;
                    line-height: 1.5;
                    color: #333;
                    background: #f5f5f5;
                    margin: 0;
                    padding: 15px;
                }}
                
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    background: white;
                    border-radius: 8px;
                    overflow: hidden;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                }}
                
                .header {{
                    background: linear-gradient(135deg, #667eea, #764ba2);
                    color: white;
                    padding: 20px;
                    text-align: center;
                }}
                
                .title {{
                    font-size: 20px;
                    font-weight: 600;
                    margin: 0 0 15px 0;
                }}
                
                .meta {{
                    display: grid;
                    grid-template-columns: 1fr 1fr;
                    gap: 8px;
                    font-size: 13px;
                }}
                
                .meta-item {{
                    background: rgba(255,255,255,0.15);
                    padding: 8px 12px;
                    border-radius: 4px;
                }}
                
                .tags {{
                    margin-top: 12px;
                }}
                
                .tag {{
                    display: inline-block;
                    background: rgba(255,255,255,0.2);
                    padding: 3px 8px;
                    border-radius: 10px;
                    font-size: 11px;
                    margin: 2px;
                }}
                
                .summary {{
                    background: #f0f9ff;
                    padding: 15px;
                    border-left: 3px solid #0ea5e9;
                }}
                
                .summary h3 {{
                    color: #0c4a6e;
                    font-size: 14px;
                    margin: 0 0 8px 0;
                }}
                
                .summary p {{
                    margin: 0;
                    font-size: 13px;
                    color: #475569;
                }}
                
                .content {{
                    padding: 15px;
                }}
                
                .content h3 {{
                    color: #1e293b;
                    font-size: 14px;
                    margin: 0 0 10px 0;
                    border-bottom: 1px solid #e2e8f0;
                    padding-bottom: 5px;
                }}
                
                .content-text {{
                    white-space: pre-wrap;
                    background: #f8fafc;
                    padding: 12px;
                    border-radius: 4px;
                    border: 1px solid #e2e8f0;
                    font-size: 13px;
                    line-height: 1.6;
                    margin: 0;
                }}
                
                .footer {{
                    background: #f8fafc;
                    padding: 12px;
                    text-align: center;
                    font-size: 11px;
                    color: #64748b;
                    border-top: 1px solid #e2e8f0;
                }}
                
                @media (max-width: 600px) {{
                    .meta {{ grid-template-columns: 1fr; }}
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1 class="title">{note_title}</h1>
                    <div class="meta">
                        <div class="meta-item">创建: {note.get('created_at', '未知')}</div>
                        <div class="meta-item">分类: {note.get('category', '未分类')}</div>
                        <div class="meta-item">优先级: {note.get('priority', '中等')}</div>
                        <div class="meta-item">状态: {note.get('status', '进行中')}</div>
                    </div>
                    {f'''<div class="tags">
                        {"".join([f'<span class="tag">{tag}</span>' for tag in note.get('tags', [])])}
                    </div>''' if note.get('tags') else ''}
                </div>

                {f'''<div class="summary">
                    <h3>📋 摘要</h3>
                    <p>{auto_summary}</p>
                </div>''' if auto_summary else ''}

                <div class="content">
                    <h3>📝 内容</h3>
                    <div class="content-text">{note_content}</div>
                </div>

                <div class="footer">
                    小可爱记事本 · {datetime.now(BEIJING_TIMEZONE).strftime('%Y-%m-%d %H:%M')} · ID: {note_id}
                </div>
            </div>
        </body>
        </html>
        """

        # 创建纯文本版本作为备选
        title_line = '='*50 if len(note_title) < 50 else '='*len(note_title)
        text_body = f"""
{note_title}
{title_line}

📋 笔记信息:
• 创建时间: {note.get('created_at', '未知')}
• 分类: {note.get('category', '未分类')}
• 优先级: {note.get('priority', '中等')}
• 标签: {', '.join(note.get('tags', [])) if note.get('tags') else '无'}

{'📄 摘要:' + chr(10) + auto_summary + chr(10) if auto_summary else ''}

📝 正文内容:
{'-'*30}
{note_content}
{'-'*30}

📧 由记事本MCP服务生成 - {datetime.now(BEIJING_TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}
笔记ID: {note_id}
"""

        # 准备邮件主题
        email_subject = subject or f"📝 笔记: {note_title}"

        logger.info(f"[SEND_NOTE_HTML] Sending HTML email: {email_subject}")

        # 发送HTML邮件
        result = gmail_service.send_email_html(
            to=to,
            subject=email_subject,
            text_body=_format_text_body(text_body),
            html_body=html_body,
            cc=cc
        )

        if result.get('success'):
            logger.info(f"[SEND_NOTE_HTML] Successfully sent HTML email for note {note_id}")
            return {
                "success": True,
                "message_id": result.get('message_id'),
                "note_id": note_id,
                "format": "HTML",
                "include_summary": include_summary,
                "recipients": result.get('recipients', {}),
                "auto_summary": auto_summary if include_summary else None
            }
        else:
            logger.error(f"[SEND_NOTE_HTML] Failed to send: {result.get('error')}")
            return {"success": False, "error": result.get('error', 'Unknown error')}

    except Exception as e:
        logger.error(f"[SEND_NOTE_HTML] Exception: {e}")
        return {"success": False, "error": str(e)}

# ==================== 路由6: 批量操作功能 ====================

@mcp.tool()
async def batch_note_operations(
    operation: str,
    note_ids: str,
    update_data: Optional[Dict] = None,
    email_to: Optional[str] = None
) -> Dict:
    """
    Purpose: Batch note operations (delete/update/export/email)
    Required: operation("delete"|"update"|"export"|"email"), note_ids(csv)
    Optional: update_data, email_to
    Returns: {"success": bool, "data": {...}}
    Notes: Uses ID fallback; validates per operation
    """
    # 解析ID列表
    ids_list = _parse_tags(note_ids) if note_ids else []
    logger.info(f"[BATCH_OPERATIONS] Starting {operation} for {len(ids_list)} notes")

    if not ids_list:
        return {"success": False, "error": "No note IDs provided"}

    try:
        d1 = get_d1_service()
        results = {
            "operation": operation,
            "total_notes": len(ids_list),
            "successful": 0,
            "failed": 0,
            "details": []
        }

        if operation == "delete":
            # 批量删除
            for note_id in ids_list:
                try:
                    note, resolved_note_id = await _resolve_note_id_for_write(d1, note_id)
                    success = await d1.delete_note(resolved_note_id) if resolved_note_id else False
                    if success:
                        results["successful"] += 1
                        results["details"].append({"note_id": resolved_note_id, "input": note_id, "title": (note or {}).get("title"), "status": "success"})
                    else:
                        results["failed"] += 1
                        results["details"].append({"note_id": note_id, "status": "failed", "error": "Delete failed"})
                except Exception as e:
                    results["failed"] += 1
                    results["details"].append({"note_id": note_id, "status": "failed", "error": str(e)})

        elif operation == "update":
            # 批量更新
            if not update_data:
                return {"success": False, "error": "update_data is required for update operation"}

            # 添加更新时间
            update_data['updated_at'] = datetime.now(BEIJING_TIMEZONE).isoformat()

            for note_id in ids_list:
                try:
                    note, resolved_note_id = await _resolve_note_id_for_write(d1, note_id)
                    success = await d1.update_note(resolved_note_id, update_data) if resolved_note_id else False
                    if success:
                        results["successful"] += 1
                        results["details"].append({"note_id": resolved_note_id, "input": note_id, "title": (note or {}).get("title"), "status": "success"})
                    else:
                        results["failed"] += 1
                        results["details"].append({"note_id": note_id, "status": "failed", "error": "Update failed"})
                except Exception as e:
                    results["failed"] += 1
                    results["details"].append({"note_id": note_id, "status": "failed", "error": str(e)})

        elif operation == "export":
            # 批量导出为JSON
            exported_notes = []
            for note_id in ids_list:
                try:
                    note = await _resolve_note_reference(d1, note_id, allow_recent=True)
                    if note:
                        # 生成摘要
                        note['auto_summary'] = _generate_auto_summary(note.get('content', ''))
                        exported_notes.append(note)
                        results["successful"] += 1
                        results["details"].append({"note_id": note.get("id"), "input": note_id, "status": "success"})
                    else:
                        results["failed"] += 1
                        results["details"].append({"note_id": note_id, "status": "failed", "error": "Note not found"})
                except Exception as e:
                    results["failed"] += 1
                    results["details"].append({"note_id": note_id, "status": "failed", "error": str(e)})

            results["exported_data"] = exported_notes
            results["export_timestamp"] = datetime.now(BEIJING_TIMEZONE).isoformat()

        elif operation == "email":
            # 批量发送邮件
            if not email_to:
                return {"success": False, "error": "email_to is required for email operation"}

            # 确保Gmail服务可用
            is_available, message = await ensure_gmail_service()
            if not is_available:
                return {"success": False, "error": f"Gmail服务不可用: {message}"}

            # 收集所有笔记内容
            all_notes = []
            for note_id in ids_list:
                try:
                    note = await _resolve_note_reference(d1, note_id, allow_recent=True)
                    if note:
                        note['auto_summary'] = _generate_auto_summary(note.get('content', ''))
                        all_notes.append(note)
                        results["successful"] += 1
                        results["details"].append({"note_id": note.get("id"), "input": note_id, "status": "success"})
                    else:
                        results["failed"] += 1
                        results["details"].append({"note_id": note_id, "status": "failed", "error": "Note not found"})
                except Exception as e:
                    results["failed"] += 1
                    results["details"].append({"note_id": note_id, "status": "failed", "error": str(e)})

            if all_notes:
                # 创建HTML邮件内容
                html_content = _create_batch_email_html(all_notes)
                text_content = _create_batch_email_text(all_notes)

                email_result = gmail_service.send_email_html(
                    to=email_to,
                    subject=f"📚 批量笔记导出 - {len(all_notes)}篇笔记",
                    text_body=_format_text_body(text_content),
                    html_body=html_content
                )

                results["email_sent"] = email_result.get('success', False)
                results["message_id"] = email_result.get('message_id')

        else:
            return {"success": False, "error": f"Unknown operation: {operation}"}

        logger.info(f"[BATCH_OPERATIONS] Completed {operation}: {results['successful']} success, {results['failed']} failed")
        return {"success": True, "data": results}

    except Exception as e:
        logger.error(f"[BATCH_OPERATIONS] Exception: {e}")
        return {"success": False, "error": str(e)}

def _create_batch_email_html(notes: List[Dict]) -> str:
    """创建批量笔记的HTML邮件内容"""
    html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>批量笔记导出</title>
    <style>
        body {{ font-family: 'Microsoft YaHei', Arial, sans-serif; line-height: 1.6; color: #333; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; }}
        .note-card {{ background: #fff; border: 1px solid #ddd; border-radius: 8px; margin: 20px 0; padding: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .note-title {{ color: #2c3e50; font-size: 20px; margin-bottom: 10px; border-bottom: 2px solid #3498db; padding-bottom: 5px; }}
        .note-meta {{ color: #7f8c8d; font-size: 12px; margin-bottom: 15px; }}
        .note-summary {{ background: #f8f9fa; padding: 10px; border-left: 4px solid #17a2b8; margin: 10px 0; font-style: italic; }}
        .note-content {{ margin-top: 15px; white-space: pre-wrap; }}
        .tags {{ margin-top: 10px; }}
        .tag {{ background: #e9ecef; color: #495057; padding: 2px 6px; border-radius: 3px; font-size: 11px; margin-right: 5px; }}
        .footer {{ text-align: center; margin-top: 40px; padding: 20px; background: #f8f9fa; color: #6c757d; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📚 批量笔记导出</h1>
        <p>共包含 {len(notes)} 篇笔记 | 导出时间: {datetime.now(BEIJING_TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>
"""

    for i, note in enumerate(notes, 1):
        tags_html = ''.join([f'<span class="tag">{tag}</span>' for tag in note.get('tags', [])])
        summary_html = f'<div class="note-summary">📄 摘要: {note.get("auto_summary", "无摘要")}</div>' if note.get('auto_summary') else ''

        html += f"""
    <div class="note-card">
        <div class="note-title">{i}. {note.get('title', '无标题')}</div>
        <div class="note-meta">
            📅 {note.get('created_at', '未知')} | 📂 {note.get('category', '未分类')} | ⭐ {note.get('priority', '中等')}
        </div>
        {summary_html}
        <div class="note-content">{note.get('content', '无内容')}</div>
        <div class="tags">{tags_html}</div>
    </div>
"""

    html += f"""
    <div class="footer">
        <p>📧 此邮件由小可爱的记事本服务自动生成</p>
        <p>🔗 导出的笔记可以随时在系统中查看和管理</p>
    </div>
</body>
</html>
"""
    return html

def _create_batch_email_text(notes: List[Dict]) -> str:
    """创建批量笔记的纯文本邮件内容"""
    separator_line = '='*50
    divider_line = '-'*30

    text = f"""
📚 批量笔记导出
{separator_line}
共包含 {len(notes)} 篇笔记
导出时间: {datetime.now(BEIJING_TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}

"""

    for i, note in enumerate(notes, 1):
        tags_text = ', '.join(note.get('tags', [])) if note.get('tags') else '无'
        summary_text = f"{chr(10)}📄 摘要: {note.get('auto_summary', '无摘要')}{chr(10)}" if note.get('auto_summary') else chr(10)

        text += f"""
{i}. {note.get('title', '无标题')}
{divider_line}
📅 创建时间: {note.get('created_at', '未知')}
📂 分类: {note.get('category', '未分类')}
⭐ 优先级: {note.get('priority', '中等')}
🏷️ 标签: {tags_text}{summary_text}
📝 内容:
{note.get('content', '无内容')}

{separator_line}

"""

    text += """
📧 此邮件由小可爱的记事本服务自动生成
🔗 导出的笔记可以随时在系统中查看和管理
"""
    return text

@mcp.tool()
async def send_file_as_email_attachment(
    file_id: str,
    to: str,
    subject: Optional[str] = None,
    body: Optional[str] = None,
    cc: Optional[str] = None
) -> Dict:
    """
    Purpose: Send stored file as email attachment
    Required: file_id, to, subject
    Optional: body, cc
    Returns: {"success": bool, ...}
    Notes: Ensures Gmail; loads metadata+content via D1/KV. Requires SERVICE_CONFIG.enable_gmail_integration.
    """
    logger.info(f"[SEND_FILE_ATTACHMENT] Sending file {file_id} as attachment to {to}")

    try:
        # 确保Gmail服务可用
        is_available, message = await ensure_gmail_service()
        if not is_available:
            return {"success": False, "error": f"Gmail服务不可用: {message}"}

        # 获取文件元数据和内容
        d1 = get_d1_service()
        kv = get_kv_service()

        file_metadata = await d1.get_file_metadata(file_id)
        if not file_metadata:
            return {"success": False, "error": "文件未找到"}

        # 获取文件内容
        file_content = await kv.get_file_content(file_metadata['kv_key'])
        if not file_content:
            return {"success": False, "error": "文件内容未找到"}

        # 准备邮件内容
        file_name = file_metadata.get('name', '未知文件')
        file_type = file_metadata.get('content_type', 'application/octet-stream')

        email_subject = subject or f"文件附件: {file_name}"
        email_body = body or f"您好，\n\n请查看附件中的文件。\n\n文件名: {file_name}\n文件类型: {file_type}\n文件大小: {file_metadata.get('size', 0)} 字节\n\n此邮件由记事本MCP服务自动发送。"

        # 创建附件
        attachment = {
            'filename': file_name,
            'content': file_content,
            'content_type': file_type
        }

        # 发送邮件
        result = gmail_service.send_email_with_attachment(
            to=to,
            subject=email_subject,
            body=_format_text_body(email_body),
            attachment_data=attachment['content'],
            attachment_filename=attachment['filename'],
            attachment_content_type=attachment['content_type'],
            cc=cc
        )

        if result.get('success'):
            logger.info(f"[SEND_FILE_ATTACHMENT] Successfully sent file {file_id} as attachment")
        else:
            logger.error(f"[SEND_FILE_ATTACHMENT] Failed to send: {result.get('error')}")

        return result

    except Exception as e:
        logger.error(f"[SEND_FILE_ATTACHMENT] Exception: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
async def list_files(limit: int = 20, file_type: Optional[str] = None,
                     name_contains: Optional[str] = None) -> Dict:
    """
    Purpose: Enumerate stored files (metadata only)
    Optional: limit(20), file_type, name_contains
    Returns: {"success": bool, "files": [...], "count": int}
    Notes: Requires Cloudflare D1/KV; no file content returned.
    """
    try:
        d1 = get_d1_service()
        conditions: List[str] = []
        params: List[Any] = []

        if file_type:
            conditions.append("type = ?")
            params.append(FileType(file_type).value if file_type in FileType.__members__ else file_type)
        if name_contains:
            conditions.append("name LIKE ?")
            params.append(f"%{name_contains}%")

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = (
            "SELECT id, name, type, size, content_type, created_at, updated_at, note_id, metadata "
            f"FROM files {where_clause} ORDER BY datetime(updated_at) DESC LIMIT ?"
        )
        params.append(max(limit, 1))

        result = await d1.execute_query(sql, params)
        rows = _extract_query_rows(result)

        files: List[Dict[str, Any]] = []
        for row in rows:
            entry = dict(row)
            meta = entry.get('metadata')
            if isinstance(meta, str):
                try:
                    entry['metadata'] = json.loads(meta)
                except json.JSONDecodeError:
                    entry['metadata'] = {}
            files.append(entry)

        return {"success": True, "files": files, "count": len(files)}
    except Exception as e:
        logger.error(f"[LIST_FILES] Error: {e}")
        return {"success": False, "error": str(e)}
@mcp.tool()
async def save_search_results_to_notepad(
    title: str,
    content: str,
    category: Optional[str] = None,
    tags: Optional[str] = None,
    send_email: Optional[str] = None
) -> Dict:
    """
    Purpose: Save search/aggregation result to note (optional email)
    Required: title, content
    Optional: category, tags(comma string), send_email(email)
    Returns: {"success": bool, ...}
    Notes: Auto-add tag "搜索结果"; normalizes category and tags
    """
    logger.info(f"[SAVE_SEARCH_RESULTS] Saving search results: {title}")

    try:
        # 标签标准化 + 默认标签
        tags_list = _parse_tags(tags) if tags else []
        if '搜索结果' not in tags_list:
            tags_list.append('搜索结果')

        # 分类标准化
        norm_cat = _normalize_category(category)
        note_category = NoteCategory(norm_cat)

        # 保存到数据库
        d1 = get_d1_service()

        response: Dict[str, Any]
        note_record: Dict[str, Any]
        segments_count = 1
        note_id: Optional[str]

        # 超长内容自动分段
        if content and len(content) > 45000:
            logger.info(f"[SAVE_SEARCH_RESULTS] Content length {len(content)} exceeds 45KB, using segmentation")
            seg_result = await _create_segmented_note(d1, title, content, note_category, NotePriority.MEDIUM, tags_list)
            if not seg_result.get('success'):
                return seg_result

            note_id = seg_result.get('note_id')
            note_record = seg_result.get('note') or {}
            if not note_record and note_id:
                note_record = await d1.get_note(note_id) or {}

            segments_count = max(seg_result.get('segments', 0) or 0, 1)

            if note_id and not note_record:
                note_record = {
                    'id': note_id,
                    'title': title,
                    'content': content[:45000],
                    'category': note_category.value,
                    'priority': NotePriority.MEDIUM.value,
                    'tags': ','.join(tags_list)
                }

            response = {
                "success": True,
                "note_id": note_id,
                "note": note_record,
                "title": note_record.get('title', title),
                "category": note_category.value,
                "tags": tags_list,
                "segments": segments_count,
                "sub_note_ids": seg_result.get('sub_note_ids', []),
                "total_length": seg_result.get('total_length'),
                "message": "搜索结果已保存为分段笔记"
            }
        else:
            # 创建笔记数据
            note_data = {
                'id': str(uuid.uuid4()),
                'title': title,
                'content': content,
                'created_at': datetime.now(BEIJING_TIMEZONE).isoformat(),
                'updated_at': datetime.now(BEIJING_TIMEZONE).isoformat(),
                'category': note_category.value,
                'priority': NotePriority.MEDIUM.value,
                'tags': ','.join(tags_list),
                'reminder_id': None,
                'file_ids': ''
            }
            result = await d1.insert_note(note_data)
            if not result:
                return {"success": False, "error": "保存笔记失败"}

            note_id = note_data['id']
            note_record = note_data
            response = {
                "success": True,
                "note_id": note_id,
                "note": note_record,
                "title": title,
                "category": note_category.value,
                "tags": tags_list,
                "message": "搜索结果已保存到记事本",
                "segments": segments_count
            }
        
        # 可选：发送邮件
        if send_email:
            logger.info(f"[SAVE_SEARCH_RESULTS] Sending note to email: {send_email}")
            is_available, message = await ensure_gmail_service()
            note_for_email = response.get('note')
            if is_available and note_for_email:
                email_result = await _invoke_tool(
                    send_note_as_email_attachment,
                    to=send_email,
                    subject=f"搜索结果: {title}",
                    note_object=note_for_email
                )
                response['email_sent'] = email_result.get('success', False)
                response['email_result'] = email_result
            else:
                response['email_sent'] = False
                response['email_result'] = {"success": False, "error": f"Gmail服务不可用: {message}" if not is_available else "笔记数据不可用，无法发送邮件"}

        logger.info(f"[SAVE_SEARCH_RESULTS] Successfully saved note: {response.get('note_id')}")
        return {"success": True, "data": response}

    except Exception as e:
        logger.error(f"[SAVE_SEARCH_RESULTS] Exception: {e}")
        return {"success": False, "error": str(e)}

# ==================== 路由4: LLM工具路由 ====================

@mcp.tool()
async def llm_tool(
    action: str,
    text: Optional[str] = None,
    options: Optional[Dict[str, Any]] = None,
    model_type: Optional[str] = None,
    processing_type: Optional[str] = None,
    mode: Optional[str] = None,
    priority: Optional[str] = None,
    max_length: Optional[int] = None,
) -> Dict:
    """
    Purpose: Text processing/generation via LLM
    When: Need title/summary/tags/categorization or text processing

    Supported actions:
    - process_text, analyze_content, generate_tags, categorize_content, generate_title, extract_summary

    Required: action
    Optional: text, options(dict), model_type, processing_type, mode, priority, max_length
    Returns: {"success": bool, ...}
    Notes: Uses lazy import; availability depends on environment
    """
    logger.info(f"[LLM_TOOL] Action: {action}")

    try:
        # 延迟导入，容忍 IDE 不可解析（运行时可用即可）
        try:
            from services.llm_service import get_llm_service  # noqa: F401
            from models.llm_models import ModelType, ProcessingType, ProcessingMode, ProcessingPriority, ProcessingRequest  # noqa: F401
        except Exception as ie:
            logger.warning(f"[LLM_TOOL] Optional imports not resolved at IDE time: {ie}")
            get_llm_service = None  # type: ignore
            ModelType = ProcessingType = ProcessingMode = ProcessingPriority = ProcessingRequest = None  # type: ignore

        if not get_llm_service:
            return {"success": False, "error": "LLM service not available in this environment"}

        llm = get_llm_service()
        if not llm.is_initialized():
            success = await llm.initialize()
            if not success:
                return {"success": False, "error": "LLM service initialization failed"}

        # 创建处理请求（可选，不强制使用，避免未使用变量告警）
        if text:
            ProcessingRequest(
                text=text,
                model_type=ModelType(model_type) if model_type else ModelType.GPT,
                processing_type=ProcessingType(processing_type) if processing_type else ProcessingType.ANALYSIS,
                mode=ProcessingMode(mode) if mode else ProcessingMode.SYNC,
                priority=ProcessingPriority(priority) if priority else ProcessingPriority.MEDIUM,
                options=options or {}
            )

        if action == "process_text":
            if not text:
                return {"success": False, "error": "text is required for process_text action"}
            result = await llm.process_text(text, **options or {})
            return result

        elif action == "analyze_content":
            if not text:
                return {"success": False, "error": "text is required for analyze_content action"}
            result = await llm.analyze_content(text)
            return result

        elif action == "generate_tags":
            if not text:
                return {"success": False, "error": "text is required for generate_tags action"}
            tags = await llm.generate_tags(text)
            return {"success": True, "tags": tags}

        elif action == "categorize_content":
            if not text:
                return {"success": False, "error": "text is required for categorize_content action"}
            category = await llm.categorize_content(text)
            return {"success": True, "category": category}

        elif action == "generate_title":
            if not text:
                return {"success": False, "error": "text is required for generate_title action"}
            title = await llm.generate_title(text)
            return {"success": True, "title": title}

        elif action == "extract_summary":
            if not text:
                return {"success": False, "error": "text is required for extract_summary action"}
            summary = await llm.extract_summary(text, max_length or 200)
            return {"success": True, "summary": summary}

        else:
            return {"success": False, "error": f"Unknown action: {action}"}

    except Exception as e:
        logger.error(f"[LLM_TOOL] Error in action {action}: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# 统一工具：文本正文格式化、文件名清理、标签/分类/优先级标准化

def _format_text_body(body: str) -> str:
    try:
        body = (body or "").replace("\r\n", "\n").replace("\r", "\n")
        body = body.replace("\n", "\r\n")
        return body
    except Exception:
        return body or ""


def _safe_filename(name: str, fallback: str) -> str:
    base = "".join(c for c in (name or "") if c.isalnum() or c in (" ", "-", "_")).rstrip() or fallback
    return base


def _parse_tags(raw) -> List[str]:
    import re
    if not raw:
        return []
    if isinstance(raw, list):
        it = raw
    else:
        it = re.split(r"[\,\s，、]+", str(raw))
    tags = sorted(set(t.strip() for t in it if t and t.strip()))
    return tags


def _is_valid_email(addr: Optional[str]) -> bool:
    if not addr or not isinstance(addr, str):
        return False
    import re
    # 简化校验：name@domain.tld（支持子域）
    return re.match(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$", addr.strip()) is not None


def _mask_email(addr: Optional[str]) -> str:
    if not addr or "@" not in addr:
        return "<missing>"
    local, domain = addr.split("@", 1)
    if len(local) <= 2:
        masked_local = f"{local[:1]}*"
    else:
        masked_local = f"{local[:2]}***{local[-1:]}"
    return f"{masked_local}@{domain}"


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _reminder_scheduler_config() -> Dict[str, Any]:
    enabled_default = _env_bool("ENABLE_REMINDERS", True)
    interval = int(os.getenv("REMINDER_CHECK_INTERVAL", str(SERVICE_CONFIG.get("reminder_check_interval", 60))).split("#")[0].strip())
    batch_size = int(os.getenv("REMINDER_BATCH_SIZE", "10"))
    grace_minutes = int(os.getenv("REMINDER_SCHEDULER_GRACE_MINUTES", "30"))
    auto_existing = _env_bool("REMINDER_AUTO_PROCESS_EXISTING_OVERDUE", False)
    return {
        "enabled": _env_bool("ENABLE_REMINDER_SCHEDULER", enabled_default),
        "interval": max(10, interval),
        "batch_size": max(1, min(batch_size, 50)),
        "grace_minutes": max(0, grace_minutes),
        "auto_process_existing_overdue": auto_existing,
    }


def _reminder_process_after(started_at: datetime, config: Dict[str, Any]) -> Optional[str]:
    if config.get("auto_process_existing_overdue"):
        return None
    grace = timedelta(minutes=int(config.get("grace_minutes", 30)))
    return (started_at - grace).isoformat()


def _format_reminder_email_body(reminder: Dict[str, Any]) -> str:
    title = reminder.get("title") or "未命名提醒"
    content = reminder.get("content") or ""
    remind_at = reminder.get("remind_at") or "未设置"
    reminder_id = reminder.get("id") or ""
    body = (
        f"提醒标题: {title}\n\n"
        f"{content}\n\n"
        f"提醒时间: {remind_at}\n"
        f"提醒ID: {reminder_id}\n\n"
        "本邮件由记事本 MCP 自动提醒发送。"
    )
    return _format_text_body(body)


async def _process_due_reminders_once(d1: D1Service, gmail: GmailService, config: Dict[str, Any], started_at: datetime) -> Dict[str, Any]:
    global _reminder_scheduler_last_run_at, _reminder_scheduler_last_error, _reminder_scheduler_processed_count

    process_after = _reminder_process_after(started_at, config)
    due_reminders = await d1.get_due_email_reminders(
        limit=int(config["batch_size"]),
        created_after=process_after,
    )
    processed = 0
    failed = 0
    skipped = 0

    for reminder in due_reminders:
        reminder_id = reminder.get("id")
        email_to = (reminder.get("email_to") or "").strip()
        if not reminder_id or not _is_valid_email(email_to):
            skipped += 1
            continue

        if not await d1.claim_reminder_for_processing(reminder_id):
            skipped += 1
            continue

        subject = f"[提醒] {reminder.get('title') or '未命名提醒'}"
        body = _format_reminder_email_body(reminder)
        try:
            result = gmail.send_email(email_to, subject, body)
            if result.get("success"):
                if await d1.mark_reminder_processed(reminder_id, "completed"):
                    processed += 1
                    _reminder_scheduler_processed_count += 1
                else:
                    failed += 1
            else:
                failed += 1
                await d1.mark_reminder_processed(reminder_id, "failed")
                logger.error("[REMINDER_SCHEDULER] Send failed for %s: %s", reminder_id, result.get("error"))
        except Exception as exc:
            failed += 1
            await d1.mark_reminder_processed(reminder_id, "failed")
            logger.error("[REMINDER_SCHEDULER] Exception while sending %s: %s", reminder_id, exc, exc_info=True)

    _reminder_scheduler_last_run_at = datetime.now(BEIJING_TIMEZONE).isoformat()
    _reminder_scheduler_last_error = None
    return {"due": len(due_reminders), "processed": processed, "failed": failed, "skipped": skipped}


async def _reminder_scheduler_loop() -> None:
    global _reminder_scheduler_started_at, _reminder_scheduler_last_error

    config = _reminder_scheduler_config()
    started_at = datetime.now(BEIJING_TIMEZONE)
    _reminder_scheduler_started_at = started_at.isoformat()
    logger.info(
        "[REMINDER_SCHEDULER] Started interval=%ss batch=%s auto_existing=%s grace=%sm",
        config["interval"],
        config["batch_size"],
        config["auto_process_existing_overdue"],
        config["grace_minutes"],
    )

    d1 = D1Service()
    gmail = GmailService()
    while True:
        try:
            if not getattr(gmail, "service", None):
                gmail = GmailService()
            if not getattr(gmail, "service", None):
                raise RuntimeError("Gmail service not available")

            summary = await _process_due_reminders_once(d1, gmail, config, started_at)
            if summary["due"]:
                logger.info("[REMINDER_SCHEDULER] Due processing summary: %s", summary)
        except Exception as exc:
            _reminder_scheduler_last_error = str(exc)
            logger.error("[REMINDER_SCHEDULER] Loop error: %s", exc, exc_info=True)

        await asyncio.sleep(int(config["interval"]))


def start_reminder_scheduler() -> None:
    global _reminder_scheduler_thread

    config = _reminder_scheduler_config()
    if not config["enabled"]:
        logger.info("[REMINDER_SCHEDULER] Disabled by configuration")
        return

    if _reminder_scheduler_thread and _reminder_scheduler_thread.is_alive():
        logger.info("[REMINDER_SCHEDULER] Already running")
        return

    def _runner() -> None:
        asyncio.run(_reminder_scheduler_loop())

    _reminder_scheduler_thread = threading.Thread(target=_runner, name="notepad-reminder-scheduler", daemon=True)
    _reminder_scheduler_thread.start()


def schedule_reminder_scheduler_start(delay_seconds: float = 5.0) -> None:
    config = _reminder_scheduler_config()
    if not config["enabled"]:
        logger.info("[REMINDER_SCHEDULER] Disabled by configuration")
        return
    timer = threading.Timer(delay_seconds, start_reminder_scheduler)
    timer.daemon = True
    timer.start()
    logger.info("[REMINDER_SCHEDULER] Scheduled startup in %.1fs", delay_seconds)


def get_reminder_scheduler_status() -> Dict[str, Any]:
    config = _reminder_scheduler_config()
    return {
        "success": True,
        "enabled": config["enabled"],
        "running": bool(_reminder_scheduler_thread and _reminder_scheduler_thread.is_alive()),
        "started_at": _reminder_scheduler_started_at,
        "last_run_at": _reminder_scheduler_last_run_at,
        "last_error": _reminder_scheduler_last_error,
        "processed_count": _reminder_scheduler_processed_count,
        "config": {
            "interval": config["interval"],
            "batch_size": config["batch_size"],
            "auto_process_existing_overdue": config["auto_process_existing_overdue"],
            "grace_minutes": config["grace_minutes"],
        },
    }


def start_redis_listener_if_enabled() -> None:
    try:
        import os as _os
        from services.redis_service import RedisServiceHandler as _RedisServiceHandler
        _enable = _os.getenv("ENABLE_REDIS_LISTENER", "true").lower() in ("1", "true", "yes", "on")
        if not _enable:
            logger.info("Redis listener disabled by environment variable")
            return

        global redis_service_handler
        if redis_service_handler is None:
            redis_service_handler = _RedisServiceHandler(notepad_service=None)
            redis_service_handler.start_listener()
            logger.info("✓ Redis listener started successfully")
        else:
            logger.info("Redis listener already running")
    except Exception as e:
        logger.error(f"Failed to start Redis listener: {e}")
        logger.info("Service will continue without Redis cross-service communication")


def schedule_redis_listener_start(delay_seconds: float = 3.0) -> None:
    timer = threading.Timer(delay_seconds, start_redis_listener_if_enabled)
    timer.daemon = True
    timer.start()
    logger.info("Redis listener scheduled startup in %.1fs", delay_seconds)


def _sanitize_recognition_error(err: str, code=None) -> str:
    """将底层识别错误转换为中性、对用户友好的提示。"""
    if code in ("1113", 1113, 429):
        return "图像识别服务当前不可用（额度或限流）。稍后将自动重试或请稍后再试。"
    if code == "file_not_found":
        return "图像文件不存在"
    if code == "encode_failed":
        return "图像文件无法读取或已损坏"
    # 默认回退
    return err or "图像识别失败"


def _normalize_category(cat: Optional[str]) -> str:
    # 简化映射，容忍中英文
    mapping = {
        'work': ['work', '工作', '任务'],
        'study': ['study', '学习', '课程'],
        'personal': ['personal', 'person', 'life', '生活', '日常', '个人', '私事', '私人'],
        'other': ['other', '其它', '其他', 'idea', '创意', '灵感']
    }
    if not cat:
        return 'other'
    c = str(cat).strip().lower()
    for key, vals in mapping.items():
        if c in vals:
            return key
    return 'other'


def _normalize_priority(p: Optional[str]) -> str:
    mapping = {
        'high': ['high', '高', '重要'],
        'medium': ['medium', '中', '普通'],
        'low': ['low', '低']
    }
    if not p:
        return 'medium'
    v = str(p).strip().lower()
    for key, vals in mapping.items():
        if v in vals:
            return key
    return 'medium'


# ==================== D1 查询结果辅助 ====================

def _extract_query_rows(result: Optional[Dict]) -> List[Dict]:
    """Flatten Cloudflare D1 execute_query responses into a simple row list."""
    if not result:
        return []

    if isinstance(result, dict):
        # Direct rows e.g. {'results': [...]}
        rows = result.get('results')
        if isinstance(rows, list):
            return rows

        # Nested rows e.g. {'result': [{'results': [...], ...}]}
        container = result.get('result')
        if isinstance(container, list):
            flattened: List[Dict] = []
            for entry in container:
                if isinstance(entry, dict):
                    inner_rows = entry.get('results')
                    if isinstance(inner_rows, list):
                        flattened.extend(inner_rows)
                    elif not entry.get('results') and all(k in entry for k in ('success', 'meta')):
                        continue
                    else:
                        flattened.append(entry)
            return flattened

    return []


def _d1_error_response(d1, default_error: str = "D1 query failed") -> Optional[Dict[str, Any]]:
    error = getattr(d1, "last_error", None)
    if error:
        return {"success": False, "error": f"{default_error}: {error}"}
    return None


def _tool_callable(tool_or_fn):
    """Return the original function for FastMCP-wrapped tools."""
    return getattr(tool_or_fn, "fn", tool_or_fn)


async def _invoke_tool(tool_or_fn, *args, **kwargs):
    result = _tool_callable(tool_or_fn)(*args, **kwargs)
    if asyncio.iscoroutine(result):
        return await result
    return result


# ==================== 初始化工具 ====================

@mcp.tool()
async def notepad_initialize_components():
    """
    Purpose: Initialize DB/KV/Gmail components
    Returns: {"success": bool, ...}
    Notes: Safe to call multiple times; idempotent init
    """
    logger.info("Initializing NotepadService components...")
    try:
        # 初始化数据库表
        d1 = get_d1_service()
        await d1.initialize_tables()

        return {"success": True, "message": "All components initialized successfully"}
    except Exception as e:
        logger.error(f"Component initialization failed: {e}")
        return {"success": False, "error": f"Component initialization failed: {e}"}

# ==================== 辅助函数 ====================

def _auto_categorize_content(content: str) -> NoteCategory:
    """根据内容自动分类"""
    content_lower = content.lower()

    # 工作相关关键词
    work_keywords = ['会议', '项目', '任务', '工作', '报告', '计划', '目标', 'meeting', 'project', 'task', 'work']
    if any(keyword in content_lower for keyword in work_keywords):
        return NoteCategory.WORK

    # 学习相关关键词
    study_keywords = ['学习', '课程', '教程', '笔记', '知识', '技能', 'study', 'learn', 'course', 'tutorial']
    if any(keyword in content_lower for keyword in study_keywords):
        return NoteCategory.STUDY

    # 个人相关关键词
    personal_keywords = ['个人', '生活', '日记', '感想', '心情', 'personal', 'life', 'diary']
    if any(keyword in content_lower for keyword in personal_keywords):
        return NoteCategory.PERSONAL

    # 想法相关关键词
    idea_keywords = ['想法', '创意', '灵感', '点子', 'idea', 'creative', 'inspiration']
    if any(keyword in content_lower for keyword in idea_keywords):
        return NoteCategory.OTHER

    return NoteCategory.OTHER

def _generate_auto_summary(content: str, max_length: int = 200) -> str:
    """生成自动摘要"""
    if not content or len(content.strip()) == 0:
        return ""

    content = content.strip()

    # 如果内容本身就很短，直接返回
    if len(content) <= max_length:
        return content

    # 按句子分割（简单版本）
    import re
    sentences = re.split(r'[。！？.!?]', content)
    sentences = [s.strip() for s in sentences if s.strip()]

    if not sentences:
        # 如果没有找到句子分隔符，直接截取
        return content[:max_length] + "..."

    # 选择最重要的句子（简单实现：取前几句）
    summary = ""
    for sentence in sentences:
        if len(summary + sentence) <= max_length:
            summary += sentence + "。"
        else:
            break

    if not summary:
        # 如果第一句就超长，截取
        summary = sentences[0][:max_length] + "..."

    return summary.strip()

def _extract_smart_keywords(content: str, max_keywords: int = 10) -> List[str]:
    """智能关键词提取"""
    if not content:
        return []

    import re

    # 清理文本
    clean_content = re.sub(r'[^\w\s\u4e00-\u9fff]', ' ', content.lower())
    words = clean_content.split()

    # 中文停用词（简化版）
    stop_words = {
        '的', '了', '在', '是', '我', '你', '他', '她', '它', '们', '这', '那', '有', '和', '与', '或',
        '但', '如果', '因为', '所以', '然后', '而且', '但是', '可以', '能够', '应该', '需要', '必须',
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by',
        'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has', 'had', 'do', 'does', 'did',
        'will', 'would', 'could', 'should', 'may', 'might', 'can', 'this', 'that', 'these', 'those'
    }

    # 统计词频
    word_count = {}
    for word in words:
        if len(word) > 1 and word not in stop_words:
            # 优先处理中文词汇
            if any('\u4e00' <= char <= '\u9fff' for char in word):
                word_count[word] = word_count.get(word, 0) + 2  # 中文词汇权重更高
            else:
                word_count[word] = word_count.get(word, 0) + 1

    # 提取关键词
    keywords = []
    for word, count in sorted(word_count.items(), key=lambda x: x[1], reverse=True):
        if count >= 1:  # 至少出现1次
            keywords.append(word)
        if len(keywords) >= max_keywords:
            break

    return keywords

async def _confirm_note_saved(d1, note_id: str, timeout: float = 3.0, max_retries: int = 6) -> bool:
    """确认笔记已成功保存到数据库，处理异步写入延迟"""
    import time
    import asyncio
    start_time = time.time()

    for attempt in range(max_retries):
        try:
            note = await d1.get_note(note_id)
            if note:
                logger.info(f"[NOTE_CONFIRM] Note {note_id} confirmed saved on attempt {attempt + 1}")
                return True

            # 如果还没找到，等待一段时间再试
            if attempt < max_retries - 1:
                wait_time = min(0.5 * (2 ** attempt), 1.0)  # 指数退避，最多等待1秒
                await asyncio.sleep(wait_time)

        except Exception as e:
            logger.warning(f"[NOTE_CONFIRM] Error checking note {note_id} on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(0.5)

    elapsed = time.time() - start_time
    logger.warning(f"[NOTE_CONFIRM] Note {note_id} not confirmed after {max_retries} attempts ({elapsed:.2f}s)")
    return False


async def _get_note_with_retry(d1, note_id: str, max_retries: int = 3) -> Optional[Dict]:
    """带重试机制的笔记查找，处理时序问题"""
    for attempt in range(max_retries):
        try:
            # 首先尝试直接查找
            note = await d1.get_note(note_id)
            if note:
                logger.info(f"[NOTE_RETRY] Found note {note_id} on attempt {attempt + 1}")
                return note

            # 如果直接查找失败，尝试模糊匹配
            note = await _get_note_by_id_with_fallback(d1, note_id)
            if note:
                logger.info(f"[NOTE_RETRY] Found note {note_id} via fallback on attempt {attempt + 1}")
                return note

            # 如果还找不到，等待后重试
            if attempt < max_retries - 1:
                wait_time = 0.5 * (attempt + 1)  # 递增等待时间
                logger.info(f"[NOTE_RETRY] Note {note_id} not found on attempt {attempt + 1}, waiting {wait_time}s...")
                await asyncio.sleep(wait_time)

        except Exception as e:
            logger.warning(f"[NOTE_RETRY] Error finding note {note_id} on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(0.5)

    logger.warning(f"[NOTE_RETRY] Note {note_id} not found after {max_retries} attempts")
    return None


def _normalize_uuid(note_id: str) -> str:
    """标准化UUID格式，处理LLM可能导致的精度丢失"""

    import re

    if note_id is None:

        return note_id

    raw_id = str(note_id).strip()

    if not raw_id:

        return raw_id

    cleaned = re.sub(r'[^0-9a-zA-Z._-]', '', raw_id)

    uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'

    if '-' in cleaned and re.fullmatch(uuid_pattern, cleaned.lower()):

        return cleaned.lower()

    hex_pattern = r'^[0-9a-fA-F]{32}$'

    if re.fullmatch(hex_pattern, cleaned):

        formatted = f"{cleaned[:8]}-{cleaned[8:12]}-{cleaned[12:16]}-{cleaned[16:20]}-{cleaned[20:32]}"

        return formatted.lower()

    return cleaned

async def _get_note_by_id_with_fallback(d1, note_id: str, include_recent: bool = True) -> Optional[Dict]:
    """Locate a note from common voice-assistant references.

    Supports exact UUID, UUID without hyphens, safe ID prefixes, note_N aliases,
    and title matches. The recent-note fallback is kept for read paths only.
    """
    try:
        if note_id is None:
            return None

        original_id = str(note_id).strip()
        if not original_id:
            return None

        async with _note_cache_lock:
            _prune_alias_cache_locked(_recent_note_cache)
            cached = _recent_note_cache.get(original_id.lower())
        if cached and cached.get("id"):
            note = await d1.get_note(cached["id"])
            if note:
                logger.info(f"[NOTE_FALLBACK] Resolved alias {original_id} -> {cached['id']}")
                return _normalize_note_record(note)

        search_ids = [original_id]
        normalized_id = _normalize_uuid(original_id)
        if normalized_id and normalized_id != original_id:
            logger.info(f"[NOTE_FALLBACK] Normalized note_id from {note_id} to {normalized_id}")
            search_ids.append(normalized_id)

        attempted: List[str] = []
        seen = set()
        for candidate in search_ids:
            candidate = str(candidate).strip()
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            note = await d1.get_note(candidate)
            if note:
                return _normalize_note_record(note)
            attempted.append(candidate)

        def _extract_first_row(query_result):
            rows = _extract_query_rows(query_result)
            return _normalize_note_record(rows[0]) if rows else None

        for search_id in attempted:
            safe_prefix = re.sub(r"[^0-9a-zA-Z._-]", "", str(search_id))
            if len(safe_prefix) >= 6:
                res = await d1.execute_query(
                    "SELECT * FROM notes WHERE id LIKE ? ORDER BY updated_at DESC LIMIT 1",
                    [f"{safe_prefix}%"],
                )
                first_row = _extract_first_row(res)
                if first_row:
                    logger.info(f"[NOTE_FALLBACK] Found note via id prefix for {search_id}")
                    return first_row

            numeric = ''.join(ch for ch in str(search_id) if ch.isdigit() or ch == '.')
            if numeric and numeric.isdigit():
                res = await d1.execute_query(
                    "SELECT * FROM notes WHERE id LIKE ? ORDER BY created_at DESC LIMIT 1",
                    [f"{numeric}.%"],
                )
                first_row = _extract_first_row(res)
                if first_row:
                    logger.info(f"[NOTE_FALLBACK] Found note via numeric prefix for {search_id}")
                    return first_row

            if numeric and '.' in numeric:
                prefix = numeric.rstrip('0').rstrip('.')
                if prefix:
                    res = await d1.execute_query(
                        "SELECT * FROM notes WHERE id LIKE ? ORDER BY created_at DESC LIMIT 1",
                        [f"{prefix}%"],
                    )
                    first_row = _extract_first_row(res)
                    if first_row:
                        logger.info(f"[NOTE_FALLBACK] Found note via decimal prefix for {search_id}")
                        return first_row

        if len(original_id) >= 2:
            res = await d1.execute_query(
                "SELECT * FROM notes WHERE title = ? COLLATE NOCASE ORDER BY updated_at DESC LIMIT 1",
                [original_id],
            )
            title_note = _extract_first_row(res)
            if title_note:
                logger.info(f"[NOTE_FALLBACK] Found note via exact title: {original_id}")
                return title_note

        if len(original_id) >= 3 and not re.fullmatch(r"[0-9a-fA-F._-]+", original_id):
            res = await d1.execute_query(
                "SELECT * FROM notes WHERE title LIKE ? ORDER BY updated_at DESC LIMIT 1",
                [f"%{original_id}%"],
            )
            title_like_note = _extract_first_row(res)
            if title_like_note:
                logger.info(f"[NOTE_FALLBACK] Found note via title keyword: {original_id}")
                return title_like_note

        if include_recent:
            recent_query = (
                "SELECT * FROM notes WHERE datetime(created_at) > datetime('now', '-5 seconds') "
                "ORDER BY created_at DESC LIMIT 1"
            )
            recent_note = _extract_first_row(await d1.execute_query(recent_query))
            if recent_note:
                logger.info(f"[NOTE_FALLBACK] Found recent note created within 5 seconds: {recent_note.get('id')}")
                return recent_note

    except Exception as e:
        logger.warning(f"[NOTE_FALLBACK] Failed to fallback find note {note_id}: {e}")

    return None

async def _create_segmented_note(d1, title: str, content: str, note_category, note_priority, tags_list) -> Dict:
    """创建分段笔记处理长文本"""
    MAX_SEGMENT_LENGTH = 45000  # 每段45KB
    segments = []

    # 分段处理
    for i in range(0, len(content), MAX_SEGMENT_LENGTH):
        segment = content[i:i + MAX_SEGMENT_LENGTH]
        segments.append(segment)

    logger.info(f"[NOTEPAD_MANAGER] Creating segmented note with {len(segments)} segments")

    # 创建主笔记
    main_note_id = str(uuid.uuid4())
    main_content = f"这是一个长文档，已分为 {len(segments)} 个部分。\n\n"
    main_content += f"原文长度: {len(content)} 字符\n"
    main_content += f"分段数量: {len(segments)}\n\n"
    main_content += "--- 第1部分 ---\n\n"
    main_content += segments[0]

    if len(segments) > 1:
        main_content += f"\n\n[继续阅读请查看相关笔记...]"

    main_note_data = {
        'id': main_note_id,
        'title': title,
        'content': main_content,
        'created_at': datetime.now(BEIJING_TIMEZONE).isoformat(),
        'updated_at': datetime.now(BEIJING_TIMEZONE).isoformat(),
        'category': note_category.value,
        'priority': note_priority.value,
        'tags': ','.join(tags_list + ['分段文档', '主文档']) if tags_list else '分段文档,主文档',
        'reminder_id': None,
        'file_ids': ''
    }

    result = await d1.insert_note(main_note_data)
    if not result:
        return {"success": False, "error": "Failed to create main note"}

    # 创建子笔记
    sub_note_ids = []
    for i in range(1, len(segments)):
        sub_note_id = str(uuid.uuid4())  # 避免ID冲突
        sub_title = f"{title} - 第{i+1}部分"
        sub_content = f"--- 第{i+1}部分 ---\n\n{segments[i]}"

        sub_note_data = {
            'id': sub_note_id,
            'title': sub_title,
            'content': sub_content,
            'created_at': datetime.now(BEIJING_TIMEZONE).isoformat(),
            'updated_at': datetime.now(BEIJING_TIMEZONE).isoformat(),
            'category': note_category.value,
            'priority': note_priority.value,
            'tags': ','.join(tags_list + ['分段文档', f'第{i+1}部分', f'主文档:{main_note_id}']) if tags_list else f'分段文档,第{i+1}部分,主文档:{main_note_id}',
            'reminder_id': None,
            'file_ids': ''
        }

        sub_result = await d1.insert_note(sub_note_data)
        if sub_result:
            sub_note_ids.append(sub_note_id)

    logger.info(f"[NOTEPAD_MANAGER] Created segmented note: main={main_note_id}, subs={sub_note_ids}")

    main_note_record = _normalize_note_record(main_note_data)
    await _cache_note_alias(main_note_record, NOTE_LATEST_ALIAS, "segmented_note")

    return {
        "success": True,
        "note_id": main_note_id,
        "note": main_note_record,
        "data": main_note_record,
        "alias": NOTE_LATEST_ALIAS,
        "message": f"Long content created as segmented note with {len(segments)} parts",
        "segments": len(segments),
        "sub_note_ids": sub_note_ids,
        "total_length": len(content)
    }

def _get_file_type_from_extension(extension: str) -> FileType:
    """根据文件扩展名确定文件类型"""
    extension = extension.lower()

    # 文档类型
    if extension in ['pdf']:
        return FileType.DOCUMENT
    elif extension in ['doc', 'docx']:
        return FileType.DOCUMENT
    elif extension in ['xls', 'xlsx', 'csv']:
        return FileType.DOCUMENT
    elif extension in ['ppt', 'pptx']:
        return FileType.DOCUMENT
    elif extension in ['txt', 'md', 'rtf']:
        return FileType.DOCUMENT

    # 图片类型
    elif extension in ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'svg']:
        return FileType.IMAGE

    # 音频类型
    elif extension in ['mp3', 'wav', 'flac', 'aac', 'm4a']:
        return FileType.AUDIO

    # 视频类型
    elif extension in ['mp4', 'avi', 'mov', 'wmv', 'flv', 'mkv']:
        return FileType.VIDEO

    # 默认为其他类型
    else:
        return FileType.OTHER

async def verify_and_init_services():
    """验证配置并初始化所有服务组件"""
    try:
        # 1. 验证配置
        # 简化配置验证，避免导入错误
        try:
            from utils.config_validator import validate_all_configs, ensure_directories

            # 确保必要目录存在
            dir_errors = ensure_directories()
            if dir_errors:
                for error in dir_errors:
                    logger.error(error)
                raise RuntimeError("Failed to create required directories")

            # 验证所有配置
            configs = {
                'GMAIL_CONFIG': GMAIL_CONFIG,
                'SERVICE_CONFIG': SERVICE_CONFIG,
                'CLOUDFLARE_CONFIG': CLOUDFLARE_CONFIG
            }

            is_valid, errors = validate_all_configs(configs)
            if not is_valid:
                for section, section_errors in errors.items():
                    for error in section_errors:
                        logger.warning(f"{section}: {error}")
                logger.warning("Configuration validation failed, but continuing with available services")
            else:
                logger.info("All configurations validated successfully")
        except ImportError as e:
            logger.warning(f"Configuration validator not available: {e}")
            logger.info("Skipping configuration validation, continuing with service initialization")

        # 2. 初始化核心服务
        logger.info("Initializing core services...")

        # 初始化D1服务
        d1_available = False
        try:
            d1_service = get_d1_service()
            await d1_service.initialize_tables()
            d1_available = True
            logger.info("D1 service initialized successfully")
        except Exception as e:
            logger.warning(f"D1 service initialization failed: {e}")
            logger.info("Service will continue without D1 database support")

        # 初始化KV服务
        kv_available = False
        try:
            kv_service = get_kv_service()
            # KV服务在构造函数中已经初始化，只需要检查连接
            kv_available = await kv_service.check_connection()
            logger.info("KV service initialized successfully" if kv_available else "KV service connection failed")
        except Exception as e:
            logger.warning(f"KV service initialization failed: {e}")
            logger.info("Service will continue without KV storage support")

        # 初始化Gmail服务
        gmail_available = False
        try:
            is_available, message = await ensure_gmail_service()
            if is_available:
                gmail_available = True
                logger.info("Gmail service initialized successfully")
            else:
                logger.warning(f"Gmail service initialization skipped: {message}")
        except Exception as e:
            logger.warning(f"Gmail service initialization failed: {e}")
            logger.info("Service will continue without Gmail support")

        # 初始化LLM服务
        llm_available = False
        try:
            # 由于LLM服务模块不存在，跳过LLM服务初始化
            llm_available = False
            logger.info("LLM service skipped (module not available)")
        except Exception as e:
            logger.warning(f"LLM service initialization failed: {e}")
            logger.info("Service will continue without LLM support")

        # 初始化Redis服务处理器（用于跨服务通信）
        redis_available = False
        try:
            import os as _os
            from services.redis_service import RedisServiceHandler as _RedisServiceHandler
            # 通过环境变量控制是否启用监听器，默认启用
            _enable = _os.getenv("ENABLE_REDIS_LISTENER", "true").lower() in ("1", "true", "yes", "on")
            if _enable:
                global redis_service_handler
                redis_service_handler = _RedisServiceHandler(notepad_service=None)
                redis_service_handler.start_listener()
                redis_available = True
                logger.info("✓ Redis service handler started and listening on notepad_requests")
            else:
                logger.info("Redis service handler disabled by environment variable")
        except Exception as e:
            logger.error(f"Redis service handler initialization failed: {e}")
            logger.info("Service will continue without Redis cross-service communication")

        # 4. 验证服务状态
        services_status = {
            "d1_service": "available" if d1_available else "unavailable",
            "kv_service": "available" if kv_available else "unavailable",
            "gmail_service": "available" if gmail_available else "unavailable",
            "llm_service": "available" if llm_available else "unavailable",
            "redis_handler": "available" if redis_available else "unavailable",
            "initialized_at": datetime.now(BEIJING_TIMEZONE).isoformat()
        }

        logger.info("Services status: %s", services_status)

        # 如果至少有基本功能可用，就认为初始化成功
        # 即使所有外部服务都不可用，也可以作为纯记事本工具运行
        return True, services_status

    except Exception as e:
        error_msg = f"Service initialization failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return False, {"error": error_msg}

# ============================================================================
# 独立工具 - 为精确控制提供专门的工具
# 混合模式：保留整合工具的同时，提供关键操作的独立工具
# ============================================================================

@mcp.tool()
async def create_note(title: str, content: str, category: str = "other",
                     priority: str = "medium", tags: Optional[str] = None) -> Dict:
    """
    Purpose: Create a new note
    When: New content needs to be stored
    Required: title, content
    Optional: category("other"|...), priority("medium"|...), tags(csv)
    Returns: {"success": bool, "data": note}
    Notes: Long content may be auto-segmented into multiple notes
    """
    logger.info(f"[CREATE_NOTE] Creating note: {title}")
    try:
        d1 = get_d1_service()

        # 输入标准化
        norm_cat = _normalize_category(category)
        norm_pri = _normalize_priority(priority)
        norm_tags = _parse_tags(tags)

        # 超长分段策略
        if content and len(content) > 45000:
            logger.info(f"[CREATE_NOTE] Content length {len(content)} exceeds 45KB, using segmentation")
            # 复用分段逻辑，需将标准化枚举转换
            note_category = NoteCategory(norm_cat)
            note_priority = NotePriority(norm_pri)
            return await _create_segmented_note(d1, title, content, note_category, note_priority, norm_tags)

        # 构建笔记数据（NoteModel 期望 tags 为 List[str]）
        current_time = datetime.now(BEIJING_TIMEZONE).isoformat()
        note_data = {
            'id': str(uuid.uuid4()),
            'title': title,
            'content': content,
            'category': norm_cat,
            'priority': norm_pri,
            'tags': norm_tags,
            'created_at': current_time,
            'updated_at': current_time,
            'reminder_id': None,
            'file_ids': []
        }

        # 验证分类和优先级（最终防御）
        try:
            NoteCategory(note_data['category'])
            NotePriority(note_data['priority'])
        except ValueError as e:
            return {"success": False, "error": f"Invalid category or priority: {e}"}

        # 创建笔记模型实例
        try:
            note_model = NoteModel(**note_data)
        except Exception as e:
            logger.error(f"[CREATE_NOTE] Failed to create NoteModel: {e}")
            return {"success": False, "error": f"Failed to create note model: {e}"}

        result = await d1.insert_note(safe_model_dump(note_model))

        if result:
            logger.info(f"[CREATE_NOTE] Note created successfully: {note_data['id']}")

            # 🔧 新增：写入确认机制 - 确保笔记真正可查到
            confirmed = await _confirm_note_saved(d1, note_data['id'])
            if not confirmed:
                logger.warning(f"[CREATE_NOTE] Note insertion confirmed but verification failed for: {note_data['id']}")
                # 不返回失败，但记录警告

            note_record = _normalize_note_record(safe_model_dump(note_model))
            await _cache_note_alias(note_record, NOTE_LATEST_ALIAS, "create_note")
            return {
                "success": True,
                "data": note_record,
                "note": note_record,
                "note_id": note_data['id'],
                "alias": NOTE_LATEST_ALIAS,
                "lookup_hint": "Use note_id for exact retrieval; note_latest is valid for the most recently created/listed note in this process.",
            }
        else:
            return {"success": False, "error": "Failed to create note"}

    except Exception as e:
        logger.error(f"[CREATE_NOTE] Error: {e}")
        return {"success": False, "error": str(e)}

@mcp.tool()
async def get_note(note_id: str) -> Dict:
    """
    Purpose: Get a note by ID (with fallback matching)
    When: Need full note detail
    Required: note_id
    Returns: {"success": bool, "data": note}
    Notes: Supports ID prefix/precision fallback
    """
    logger.info(f"[GET_NOTE] Getting note: {note_id}")
    try:
        d1 = get_d1_service()

        note = await _resolve_note_reference(d1, note_id, allow_recent=True)

        if note:
            await _cache_note_alias(note, NOTE_LATEST_ALIAS, "get_note")
            return {"success": True, "data": note, "note": note, "note_id": note.get("id")}
        else:
            # 🔧 改进：提供更详细的错误信息
            d1_error = _d1_error_response(d1, "Failed to get note")
            if d1_error:
                return d1_error
            logger.warning(f"[GET_NOTE] Note not found after all attempts: {note_id}")
            return {"success": False, "error": f"Note not found: {note_id}. Please check if the note was created successfully."}

    except Exception as e:
        logger.error(f"[GET_NOTE] Error: {e}")
        return {"success": False, "error": str(e)}

@mcp.tool()
async def update_note(note_id: str, title: Optional[str] = None,
                     content: Optional[str] = None, category: Optional[str] = None,
                     priority: Optional[str] = None, tags: Optional[str] = None,
                     enable_auto_segment_on_update: bool = False) -> Dict:
    """
    Purpose: Partially update note fields
    When: Modify title/content/category/priority/tags
    Required: note_id
    Optional: title, content, category, priority, tags(csv), enable_auto_segment_on_update(False)
    Returns: {"success": bool, "data": updated_note}
    """
    logger.info(f"[UPDATE_NOTE] Updating note: {note_id}")
    try:
        d1 = get_d1_service()
        existing_note, resolved_note_id = await _resolve_note_id_for_write(d1, note_id)

        if not existing_note or not resolved_note_id:
            d1_error = _d1_error_response(d1, "Failed to resolve note")
            if d1_error:
                return d1_error
            return {"success": False, "error": "Note not found"}

        # 构建更新数据（标准化）
        update_data = {}
        if title is not None:
            update_data['title'] = title
        if content is not None:
            # 可选自动分段：仅当开启开关且内容超长时
            if enable_auto_segment_on_update and len(content) > 45000:
                logger.info(f"[UPDATE_NOTE] Content length {len(content)} exceeds 45KB and auto-segmentation enabled")
                seg_result = await _create_segmented_note(d1, title or existing_note.get('title', ''), content,
                                                          NoteCategory(existing_note.get('category', 'other')),
                                                          NotePriority(existing_note.get('priority', 'medium')),
                                                          _parse_tags(existing_note.get('tags', [])))
                return seg_result
            else:
                update_data['content'] = content
        if category is not None:
            try:
                norm_cat = _normalize_category(category)
                NoteCategory(norm_cat)
                update_data['category'] = norm_cat
            except ValueError:
                return {"success": False, "error": f"Invalid category: {category}"}
        if priority is not None:
            try:
                norm_pri = _normalize_priority(priority)
                NotePriority(norm_pri)
                update_data['priority'] = norm_pri
            except ValueError:
                return {"success": False, "error": f"Invalid priority: {priority}"}
        if tags is not None:
            update_data['tags'] = _parse_tags(tags)

        update_data['updated_at'] = datetime.now(BEIJING_TIMEZONE).isoformat()

        result = await d1.update_note(resolved_note_id, update_data)

        if result:
            # 获取更新后的笔记
            updated_note = await d1.get_note(resolved_note_id)
            updated_note = _normalize_note_record(updated_note) if updated_note else None
            if updated_note:
                await _cache_note_alias(updated_note, NOTE_LATEST_ALIAS, "update_note")
            return {"success": True, "data": updated_note, "note": updated_note, "note_id": resolved_note_id}
        else:
            return {"success": False, "error": "Failed to update note"}

    except Exception as e:
        logger.error(f"[UPDATE_NOTE] Error: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
async def update_note_and_email(
    note_id: str,
    title: Optional[str] = None,
    content: Optional[str] = None,
    category: Optional[str] = None,
    priority: Optional[str] = None,
    tags: Optional[str] = None,
    to: Optional[str] = None,
    subject: Optional[str] = None,
    send_type: str = "attachment",
    cc: Optional[str] = None
) -> Dict:
    """
    Purpose: Atomic update + email (body or attachment)
    When: User asks “update this note then email me (attachment/body)” in one step
    Required: note_id
    Optional: title, content, category, priority, tags(csv), to, subject, send_type("attachment"|"body"), cc
    Returns: {"success": bool, "note": note, "email_result": {...}}
    Notes: Preferred for reliability; ensures Gmail and uses ID fallback
    """
    logger.info(f"[UPDATE_AND_EMAIL] note_id={note_id}, send_type={send_type}")

    try:
        d1 = get_d1_service()
        note, resolved_note_id = await _resolve_note_id_for_write(d1, note_id)
        if not note or not resolved_note_id:
            d1_error = _d1_error_response(d1, "Failed to resolve note")
            if d1_error:
                return d1_error
            return {"success": False, "error": "Note not found"}

        # 1) 执行更新（与 update_note 一致的标准化）
        update_data: Dict[str, Any] = {}
        if title is not None:
            update_data['title'] = title
        if content is not None:
            update_data['content'] = content
        if category is not None:
            norm_cat = _normalize_category(category)
            NoteCategory(norm_cat)
            update_data['category'] = norm_cat
        if priority is not None:
            norm_pri = _normalize_priority(priority)
            NotePriority(norm_pri)
            update_data['priority'] = norm_pri
        if tags is not None:
            update_data['tags'] = _parse_tags(tags)

        if update_data:
            update_data['updated_at'] = datetime.now(BEIJING_TIMEZONE).isoformat()
            ok = await d1.update_note(resolved_note_id, update_data)
            if not ok:
                return {"success": False, "error": "Failed to update note"}

        # 2) 获取最新笔记（容错检索）
        note = await d1.get_note(resolved_note_id)
        note = _normalize_note_record(note) if note else None
        if not note:
            return {"success": False, "error": "Note not found after update"}

        # 3) 若需要发送
        if to:
            if not _is_valid_email(to):
                return {"success": False, "error": "Invalid recipient email"}
            is_available, message = await ensure_gmail_service()
            if not is_available:
                return {"success": False, "error": f"Gmail服务不可用: {message}"}

            title_val = (note.get('title') or '').strip() or f"未命名笔记({note.get('id','')})"
            content_val = note.get('content', '')

            if send_type == "body":
                email_subject = subject or f"笔记: {title_val}"
                email_body = _format_text_body(f"笔记标题: {title_val}\n\n{content_val}\n\n— 本邮件由记事本服务自动发送")
                email_result = gmail_service.send_email(to, email_subject, email_body, cc)
            else:
                email_subject = subject or f"笔记附件: {title_val}"
                email_body = _format_text_body(f"请查看附件中的笔记: {title_val}")
                safe_name = _safe_filename(title_val, f"note_{note.get('id','')}") + ".txt"
                email_result = gmail_service.send_email_with_attachment(
                    to=to,
                    subject=email_subject,
                    body=email_body,
                    attachment_data=content_val,
                    attachment_filename=safe_name,
                    attachment_content_type='text/plain; charset=utf-8',
                    cc=cc
                )

            return {"success": email_result.get('success', False), "note": note, "email_result": email_result}

        # 若未请求发送，仅返回更新后的笔记
        await _cache_note_alias(note, NOTE_LATEST_ALIAS, "update_note_and_email")
        return {"success": True, "note": note, "data": note, "note_id": resolved_note_id}

    except Exception as e:
        logger.error(f"[UPDATE_AND_EMAIL] Exception: {e}")
        return {"success": False, "error": str(e)}

@mcp.tool()
async def delete_note(note_id: str) -> Dict:
    """
    Purpose: Permanently delete a note
    Required: note_id
    Returns: {"success": bool, "message": str}
    """
    logger.info(f"[DELETE_NOTE] Deleting note: {note_id}")
    try:
        d1 = get_d1_service()
        note, resolved_note_id = await _resolve_note_id_for_write(d1, note_id)
        if not note or not resolved_note_id:
            d1_error = _d1_error_response(d1, "Failed to resolve note")
            if d1_error:
                return d1_error
            return {"success": False, "error": "Note not found"}
        result = await d1.delete_note(resolved_note_id)

        if result:
            return {"success": True, "note_id": resolved_note_id, "deleted_title": note.get("title"), "message": "Note deleted successfully"}
        else:
            return {"success": False, "error": "Note not found or failed to delete"}

    except Exception as e:
        logger.error(f"[DELETE_NOTE] Error: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
async def get_note_details(note_id: str, use_fallback: bool = True) -> Dict:
    """
    Purpose: Retrieve a single note by ID (with optional fuzzy fallback)
    Required: note_id
    Optional: use_fallback(True)
    Returns: {"success": bool, "note": {...}}
    Notes: Falls back to numeric-prefix search when enabled
    """
    if not note_id:
        return {"success": False, "error": "note_id is required"}

    try:
        d1 = get_d1_service()
        note = await _resolve_note_reference(d1, note_id, allow_recent=use_fallback)

        if note:
            await _cache_note_alias(note, NOTE_LATEST_ALIAS, "get_note_details")
            return {"success": True, "note": note, "data": note, "note_id": note.get("id")}
        d1_error = _d1_error_response(d1, "Failed to get note details")
        if d1_error:
            return d1_error
        return {"success": False, "error": "Note not found"}
    except Exception as e:
        logger.error(f"[GET_NOTE_DETAILS] Error: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
async def list_recent_notes(limit: int = 20, category: Optional[str] = None,
                           include_content_preview: bool = True) -> Dict:
    """
    Purpose: List recent notes with optional category filter
    Optional: limit(20), category, include_content_preview(True)
    Returns: {"success": bool, "notes": [...]} 
    Notes: Sorted by updated_at desc; previews trimmed to 120 chars when enabled
    """
    try:
        d1 = get_d1_service()
        params: List[Any] = []
        where_clause = ""
        if category:
            where_clause = "WHERE category = ?"
            params.append(_normalize_category(category))

        sql = (
            "SELECT id, title, category, priority, updated_at, created_at, tags, content "
            f"FROM notes {where_clause} ORDER BY datetime(updated_at) DESC LIMIT ?"
        )
        params.append(max(limit, 1))

        result = await d1.execute_query(sql, params)
        if result and result.get('success') is False:
            return _d1_error_response(d1, "List recent notes failed") or {"success": False, "error": result.get("error", "List recent notes failed")}
        rows = _extract_query_rows(result)

        notes: List[Dict[str, Any]] = []
        for row in rows:
            note_entry = _normalize_note_record(dict(row))
            if include_content_preview and note_entry.get('content'):
                preview = note_entry['content'][:120]
                note_entry['content_preview'] = preview
            note_entry.pop('content', None) if include_content_preview else None
            notes.append(note_entry)

        await _register_recent_notes_cache(notes, "list_recent_notes")

        return {
            "success": True,
            "notes": notes,
            "data": notes,
            "count": len(notes),
            "alias_hint": "Use note_1, note_2, ... from this result for follow-up note tools."
        }
    except Exception as e:
        logger.error(f"[LIST_RECENT_NOTES] Error: {e}")
        return {"success": False, "error": str(e)}

@mcp.tool()
async def search_notes(query: str, category: Optional[str] = None,
                      priority: Optional[str] = None, tags: Optional[str] = None) -> Dict:
    """
    搜索笔记 - 独立工具版本

    支持关键词、分类、优先级和标签的组合搜索
    """
    logger.info(f"[SEARCH_NOTES] Searching notes: {query}")
    try:
        d1 = get_d1_service()
        tags_list = _parse_tags(tags) if tags else None
        notes = await d1.search_notes(query, category, priority, tags_list)
        d1_error = _d1_error_response(d1, "Search notes failed")
        if d1_error:
            return d1_error
        notes = [_normalize_note_record(note) for note in (notes or [])]
        await _register_recent_notes_cache(notes, "search_notes")

        return {"success": True, "data": notes, "notes": notes, "count": len(notes), "alias_hint": "Use note_1, note_2, ... from this result for follow-up note tools."}

    except Exception as e:
        logger.error(f"[SEARCH_NOTES] Error: {e}")
        return {"success": False, "error": str(e)}

@mcp.tool()
async def append_to_note(note_id: str, content: str) -> Dict:
    """
    Purpose: Append content to an existing note
    When: Need to add more text to a note without replacing it
    Required: note_id, content
    Returns: {"success": bool, "note": updated_note}
    Notes: This is the preferred way to handle large text inputs by splitting them into chunks.
    """
    logger.info(f"[APPEND_TO_NOTE] Appending to note: {note_id}")
    try:
        if content is None:
            return {"success": False, "error": "content is required"}

        d1 = get_d1_service()
        note, resolved_note_id = await _resolve_note_id_for_write(d1, note_id)
        if not note or not resolved_note_id:
            d1_error = _d1_error_response(d1, "Failed to resolve note")
            if d1_error:
                return d1_error
            return {"success": False, "error": "Note not found"}

        new_content = note.get("content", "") + content
        ok = await d1.update_note(
            resolved_note_id,
            {
                "content": new_content,
                "updated_at": datetime.now(BEIJING_TIMEZONE).isoformat(),
            },
        )
        if not ok:
            return {"success": False, "error": "Failed to append content"}

        updated_note = await d1.get_note(resolved_note_id)
        updated_note = _normalize_note_record(updated_note) if updated_note else None
        if updated_note:
            await _cache_note_alias(updated_note, NOTE_LATEST_ALIAS, "append_to_note")
        return {
            "success": True,
            "note": updated_note,
            "data": updated_note,
            "note_id": resolved_note_id,
            "message": "Content appended successfully",
        }
    except Exception as e:
        logger.error(f"[APPEND_TO_NOTE] Error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@mcp.tool()
async def send_email_simple(to: str, subject: str, body: str, cc: Optional[str] = None) -> Dict:
    """
    Purpose: Send plain text email
    Required: to, subject, body
    Optional: cc
    Returns: {"success": bool, ...}
    Notes: Ensures Gmail; formats text body; validates email. Requires SERVICE_CONFIG.enable_gmail_integration.
    """
    logger.info(f"[SEND_EMAIL] Sending email to: {to}")
    try:
        # 基本邮箱格式校验
        if not _is_valid_email(to):
            return {"success": False, "error": "Invalid recipient email"}

        # 确保Gmail服务可用（统一走 ensure 流程，避免未初始化导致的误报）
        is_available, message = await ensure_gmail_service()
        if not is_available:
            return {"success": False, "error": f"Gmail服务不可用: {message}"}

        result = gmail_service.send_email(
            to=to,
            subject=subject,
            body=_format_text_body(body),
            cc=cc
        )

        return result

    except Exception as e:
        logger.error(f"[SEND_EMAIL] Error: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
async def get_recent_emails(max_results: int = 10, label: str = "inbox",
                           query: Optional[str] = None) -> Dict:
    """
    Purpose: List recent emails
    Optional: max_results(10), label("inbox"|...), query
    Returns: {"success": bool, "data": [emails]}
    Notes: Requires SERVICE_CONFIG.enable_gmail_integration and valid Gmail credentials/token.
    """
    logger.info(f"[GET_EMAILS] Getting emails from: {label}")
    try:
        # 确保Gmail服务可用（统一走 ensure 流程）
        is_available, message = await ensure_gmail_service()
        if not is_available:
            return {"success": False, "error": f"Gmail服务不可用: {message}"}

        result = gmail_service.get_recent_emails(
            max_results=max_results,
            label=label,
            query=query
        )

        if result.get("success"):
            emails = result.get("emails") or []
            await _register_recent_emails_cache(emails, label, query)
            result["emails"] = emails
            result["data"] = emails
            result["cached_at"] = datetime.now(timezone.utc).isoformat()
            result["alias_hint"] = "Use email_1, email_2, ... from this result for get_email_content, mark_email_as_read, and other email tools."
            logger.info(f"[GET_EMAILS] Cached {len(emails)} emails for alias mapping")

        return result

    except Exception as e:
        logger.error(f"[GET_EMAILS] Error: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
async def get_email_content(email_id: str) -> Dict:
    """
    Purpose: Get email content by ID
    Required: email_id
    Returns: {"success": bool, "data": {"id": str, "subject": str, "sender": str, "body": str, ...}}
    """
    logger.info(f"[GET_EMAIL_CONTENT] Getting content for email: {email_id}")
    try:
        # 确保Gmail服务可用
        is_available, message = await ensure_gmail_service()
        if not is_available:
            return {"success": False, "error": f"Gmail服务不可用: {message}"}

        resolved_id, error = await _get_resolved_email_id(email_id, "GET_EMAIL_CONTENT")
        if error:
            return error

        result = gmail_service.get_email_content(resolved_id)

        alias_note = "" if resolved_id == email_id else f" (alias {email_id})"
        if result.get("success"):
            result["email_id"] = resolved_id
            if resolved_id != email_id:
                result["input_alias"] = email_id
            logger.info(f"[GET_EMAIL_CONTENT] Successfully retrieved content for email: {resolved_id}{alias_note}")
        else:
            logger.warning(f"[GET_EMAIL_CONTENT] Failed to retrieve content for email {resolved_id}{alias_note}: {result.get('error')}")

        return result

    except Exception as e:
        logger.error(f"[GET_EMAIL_CONTENT] Error: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
async def mark_email_as_read(email_id: str) -> Dict:
    """
    Purpose: Mark email as read
    Required: email_id
    Returns: {"success": bool, "message": str}
    """
    logger.info(f"[MARK_EMAIL_READ] Marking email as read: {email_id}")
    try:
        is_available, message = await ensure_gmail_service()
        if not is_available:
            return {"success": False, "error": f"Gmail服务不可用: {message}"}

        resolved_id, error = await _get_resolved_email_id(email_id, "MARK_EMAIL_READ")
        if error:
            return error

        result = gmail_service.mark_as_read(resolved_id)
        alias_note = "" if resolved_id == email_id else f" (alias {email_id})"
        if result.get("success"):
            logger.info(f"[MARK_EMAIL_READ] Marked email as read: {resolved_id}{alias_note}")
        else:
            logger.warning(f"[MARK_EMAIL_READ] Failed to mark email {resolved_id} as read: {result.get('error')}")

        return result

    except Exception as e:
        logger.error(f"[MARK_EMAIL_READ] Error: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
async def trash_email(email_id: str) -> Dict:
    """
    Purpose: Move email to trash
    Required: email_id
    Returns: {"success": bool, "message": str}
    """
    logger.info(f"[TRASH_EMAIL] Moving email to trash: {email_id}")
    try:
        is_available, message = await ensure_gmail_service()
        if not is_available:
            return {"success": False, "error": f"Gmail服务不可用: {message}"}

        resolved_id, error = await _get_resolved_email_id(email_id, "TRASH_EMAIL")
        if error:
            return error

        result = gmail_service.trash_email(resolved_id)
        alias_note = "" if resolved_id == email_id else f" (alias {email_id})"
        if result.get("success"):
            logger.info(f"[TRASH_EMAIL] Trashed email: {resolved_id}{alias_note}")
        else:
            logger.warning(f"[TRASH_EMAIL] Failed to trash email {resolved_id}: {result.get('error')}")

        return result

    except Exception as e:
        logger.error(f"[TRASH_EMAIL] Error: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
async def reply_to_email(email_id: str, body: str, html_body: Optional[str] = None,
                       cc: Optional[str] = None) -> Dict:
    """
    Purpose: Reply to an email
    Required: email_id, body
    Optional: html_body, cc
    Returns: {"success": bool, "message": str, "in_reply_to": str}
    """
    logger.info(f"[REPLY_EMAIL] Replying to email: {email_id}")
    try:
        is_available, message = await ensure_gmail_service()
        if not is_available:
            return {"success": False, "error": f"Gmail服务不可用: {message}"}

        resolved_id, error = await _get_resolved_email_id(email_id, "REPLY_EMAIL")
        if error:
            return error

        result = gmail_service.reply_to_email(
            email_id=resolved_id,
            body=body,
            html_body=html_body,
            cc=cc
        )

        alias_note = "" if resolved_id == email_id else f" (alias {email_id})"
        if result.get("success"):
            logger.info(f"[REPLY_EMAIL] Successfully replied to email: {resolved_id}{alias_note}")
        else:
            logger.warning(f"[REPLY_EMAIL] Failed to reply to email {resolved_id}: {result.get('error')}")

        return result

    except Exception as e:
        logger.error(f"[REPLY_EMAIL] Error: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
async def reply_all_to_email(email_id: str, body: str, html_body: Optional[str] = None) -> Dict:
    """
    Purpose: Reply to all recipients of an email
    Required: email_id, body
    Optional: html_body
    Returns: {"success": bool, "message": str, "recipients_count": int}
    """
    logger.info(f"[REPLY_ALL_EMAIL] Replying to all for email: {email_id}")
    try:
        is_available, message = await ensure_gmail_service()
        if not is_available:
            return {"success": False, "error": f"Gmail服务不可用: {message}"}

        resolved_id, error = await _get_resolved_email_id(email_id, "REPLY_ALL_EMAIL")
        if error:
            return error

        result = gmail_service.reply_all_to_email(
            email_id=resolved_id,
            body=body,
            html_body=html_body
        )

        alias_note = "" if resolved_id == email_id else f" (alias {email_id})"
        if result.get("success"):
            logger.info(f"[REPLY_ALL_EMAIL] Successfully replied to all for email: {resolved_id}{alias_note}")
        else:
            logger.warning(f"[REPLY_ALL_EMAIL] Failed to reply-all for email {resolved_id}: {result.get('error')}")

        return result

    except Exception as e:
        logger.error(f"[REPLY_ALL_EMAIL] Error: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
async def gmail_health_check() -> Dict:
    """
    Purpose: Gmail integration health check
    Returns: {"success": bool, "enabled": bool, "server_mode": bool, "api_timeout": int, ...}
    Notes: Includes credentials/token existence and actionable suggestions
    """
    logger.info("[GMAIL_HEALTH] Running Gmail health check")
    try:
        import os
        enabled = SERVICE_CONFIG.get('enable_gmail_integration', True)
        cred_path = GMAIL_CONFIG.get('api_credentials_file')
        token_path = GMAIL_CONFIG.get('token_path')
        server_mode = GMAIL_CONFIG.get('server_mode', True)
        api_timeout = GMAIL_CONFIG.get('api_timeout')

        cred_exists = bool(cred_path and os.path.exists(cred_path))
        token_exists = bool(token_path and os.path.exists(token_path))

        # 默认健康状态
        health = {"success": False, "status": "Not initialized"}
        email_address = None

        # 若启用了集成，则尝试初始化/确保可用
        if enabled:
            ok, msg = await ensure_gmail_service()
        else:
            ok, msg = (False, "Integration disabled by configuration")

        if ok and gmail_service and getattr(gmail_service, 'service', None) is not None:
            try:
                health = gmail_service.check_service_health() or {"success": True, "status": "Unknown"}
                email_address = health.get('email_address')
            except Exception as he:
                logger.warning(f"[GMAIL_HEALTH] check_service_health error: {he}")
                health = {"success": False, "status": str(he)}
        else:
            health = {"success": False, "status": str(msg)}

        result = {
            "success": True,
            "enabled": enabled,
            "server_mode": server_mode,
            "api_timeout": api_timeout,
            "credentials_file": cred_path,
            "token_path": token_path,
            "credentials_exists": cred_exists,
            "token_exists": token_exists,
            "email_address": email_address,
            "health": health,
        }

        suggestions = []
        if not enabled:
            suggestions.append("将 ENABLE_GMAIL_INTEGRATION=true 写入 .env 并重启容器")
        if server_mode and not token_exists:
            suggestions.append("SERVER_MODE=true 时需先本地运行 notepad_mcp/run_gmail_auth.py 生成 token.json 并上传至容器路径")
        if not cred_exists:
            suggestions.append("确保 gmail_credentials.json 存在于配置的 api_credentials_file 路径")
        if suggestions:
            result["suggestions"] = suggestions

        return result
    except Exception as e:
        logger.error(f"[GMAIL_HEALTH] Exception: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@mcp.tool()
async def get_system_status() -> Dict:
    """
    Purpose: System/service status (DB/KV/Gmail/etc.)
    Returns: {"success": bool, ...}
    """
    logger.info("[SYSTEM_STATUS] Checking system status")
    try:
        status = {
            "service_status": {
                "d1_service": False,
                "kv_service": False,
                "gmail_service": False,
                "redis_service": False
            },
            "system_info": {
                "uptime_seconds": 0,
                "version": "0.2.1-fixed"
            },
            "timestamp": datetime.now(BEIJING_TIMEZONE).isoformat()
        }

        # 检查D1服务
        try:
            d1 = get_d1_service()
            status["service_status"]["d1_service"] = await d1.check_connection()
        except:
            pass

        # 检查KV服务
        try:
            kv = get_kv_service()
            status["service_status"]["kv_service"] = await kv.check_connection()
        except:
            pass

        # 检查Gmail服务
        try:
            gmail_available, _message = await ensure_gmail_service()
            if gmail_available and gmail_service:
                health = gmail_service.check_service_health()
                status["service_status"]["gmail_service"] = health.get("success", False)
        except:
            pass

        # 检查Redis服务
        try:
            global redis_service_handler
            if redis_service_handler is None:
                from services.redis_service import RedisServiceHandler as _RedisServiceHandler
                redis_service_handler = _RedisServiceHandler(notepad_service=None)
            redis_conn = redis_service_handler.get_redis_connection()
            if redis_conn:
                redis_conn.ping()
                status["service_status"]["redis_service"] = True
        except:
            pass

        return {"success": True, "data": status}

    except Exception as e:
        logger.error(f"[SYSTEM_STATUS] Error: {e}")
        return {"success": False, "error": str(e)}

# ==================== 路由6: 增强标签管理系统 ====================

@mcp.tool()
async def tag_manager(
    action: str,
    note_id: Optional[str] = None,
    tag_name: Optional[str] = None,
    tags: Optional[str] = None,
    search_query: Optional[str] = None,
    limit: int = 100
) -> Dict:
    """
    Purpose: Enhanced tag management (add/remove/list/search/stats/rename/merge)
    When: Operate tags or query tag stats

    Supported actions: add_tags, remove_tags, get_note_tags, get_all_tags, search_tags, get_tag_stats, rename_tag, merge_tags

    Required: action
    Optional: note_id, tag_name, tags(csv), search_query, limit
    Returns: {"success": bool, ...}
    """
    logger.info(f"[TAG_MANAGER] Action: {action}, note_id: {note_id}, tag_name: {tag_name}, tags: {tags}")

    try:
        d1 = get_d1_service()

        if action == "add_tags":
            if not note_id:
                return {"success": False, "error": "note_id is required for add_tags"}

            # 处理标签输入：支持单个标签与逗号分隔字符串（统一标准化）
            tags_to_add = []
            if tag_name:
                tags_to_add.extend(_parse_tags(tag_name))
            if tags:
                tags_to_add.extend(_parse_tags(tags))

            if not tags_to_add:
                return {"success": False, "error": "No valid tags provided"}

            # 验证笔记存在
            note, resolved_note_id = await _resolve_note_id_for_write(d1, note_id)
            if not note or not resolved_note_id:
                d1_error = _d1_error_response(d1, "Failed to resolve note")
                if d1_error:
                    return d1_error
                return {"success": False, "error": "Note not found"}

            # 获取现有标签
            existing_tags = note.get('tags', [])
            if isinstance(existing_tags, str):
                existing_tags = [tag.strip() for tag in existing_tags.split(',') if tag.strip()]
            elif not isinstance(existing_tags, list):
                existing_tags = []

            # 添加新标签（去重）
            new_tags = list(set(existing_tags + tags_to_add))

            # 更新笔记
            update_result = await d1.update_note(resolved_note_id, {'tags': new_tags})
            if update_result:
                return {
                    "success": True,
                    "message": f"Successfully added {len(tags_to_add)} tags to note",
                    "note_id": resolved_note_id,
                    "added_tags": tags_to_add,
                    "all_tags": new_tags,
                    "note_title": note.get('title', '')[:50]
                }
            else:
                return {"success": False, "error": "Failed to update note with new tags"}

        elif action == "remove_tags":
            if not note_id:
                return {"success": False, "error": "note_id is required for remove_tags"}

            # 处理标签输入
            tags_to_remove = []
            if tag_name:
                tags_to_remove.extend(_parse_tags(tag_name))
            if tags:
                tags_to_remove.extend(_parse_tags(tags))

            if not tags_to_remove:
                return {"success": False, "error": "No valid tags provided"}

            # 验证笔记存在
            note, resolved_note_id = await _resolve_note_id_for_write(d1, note_id)
            if not note or not resolved_note_id:
                d1_error = _d1_error_response(d1, "Failed to resolve note")
                if d1_error:
                    return d1_error
                return {"success": False, "error": "Note not found"}

            # 获取现有标签
            existing_tags = note.get('tags', [])
            if isinstance(existing_tags, str):
                existing_tags = [tag.strip() for tag in existing_tags.split(',') if tag.strip()]
            elif not isinstance(existing_tags, list):
                existing_tags = []

            # 移除指定标签
            new_tags = [tag for tag in existing_tags if tag not in tags_to_remove]
            removed_tags = [tag for tag in tags_to_remove if tag in existing_tags]

            # 更新笔记
            update_result = await d1.update_note(resolved_note_id, {'tags': new_tags})
            if update_result:
                return {
                    "success": True,
                    "message": f"Successfully removed {len(removed_tags)} tags from note",
                    "note_id": resolved_note_id,
                    "removed_tags": removed_tags,
                    "remaining_tags": new_tags,
                    "note_title": note.get('title', '')[:50]
                }
            else:
                return {"success": False, "error": "Failed to update note"}

        elif action == "get_note_tags":
            if not note_id:
                return {"success": False, "error": "note_id is required for get_note_tags"}

            note = await _resolve_note_reference(d1, note_id, allow_recent=True)
            if not note:
                d1_error = _d1_error_response(d1, "Failed to get note tags")
                if d1_error:
                    return d1_error
                return {"success": False, "error": "Note not found"}

            tags = note.get('tags', [])
            if isinstance(tags, str):
                tags = [tag.strip() for tag in tags.split(',') if tag.strip()]
            elif not isinstance(tags, list):
                tags = []

            return {
                "success": True,
                "note_id": note.get("id"),
                "note_title": note.get('title', ''),
                "tags": tags,
                "tag_count": len(tags),
                "category": note.get('category', ''),
                "created_at": note.get('created_at', '')
            }

        elif action == "get_all_tags":
            # 获取所有笔记来统计标签使用情况
            notes = await d1.get_all_notes()
            d1_error = _d1_error_response(d1, "Get all tags failed")
            if d1_error:
                return d1_error
            tag_stats = {}
            category_stats = {}

            for note in notes:
                note_tags = note.get('tags', [])
                if isinstance(note_tags, str):
                    note_tags = [tag.strip() for tag in note_tags.split(',') if tag.strip()]
                elif not isinstance(note_tags, list):
                    note_tags = []

                category = note.get('category', 'other')

                for tag in note_tags:
                    if tag:
                        tag_stats[tag] = tag_stats.get(tag, 0) + 1

                        if tag not in category_stats:
                            category_stats[tag] = {}
                        category_stats[tag][category] = category_stats[tag].get(category, 0) + 1

            # 按使用频率排序
            sorted_tags = sorted(tag_stats.items(), key=lambda x: x[1], reverse=True)

            # 分页限制
            max_items = max(1, int(limit or 100))
            limited_sorted = sorted_tags[:max_items]

            return {
                "success": True,
                "all_tags": [tag for tag, _ in limited_sorted],
                "tag_statistics": dict(limited_sorted),
                "category_distribution": category_stats,
                "total_unique_tags": len(sorted_tags),
                "most_used_tag": limited_sorted[0] if limited_sorted else None,
                "least_used_tags": [tag for tag, count in sorted_tags if count == 1][:max_items]
            }

        elif action == "search_tags":
            if not search_query:
                return {"success": False, "error": "search_query is required for search_tags"}

            # 获取所有标签
            notes = await d1.get_all_notes()
            all_tags = set()
            tag_usage = {}

            for note in notes:
                note_tags = note.get('tags', [])
                if isinstance(note_tags, str):
                    note_tags = [tag.strip() for tag in note_tags.split(',') if tag.strip()]
                elif not isinstance(note_tags, list):
                    note_tags = []

                for tag in note_tags:
                    if tag:
                        all_tags.add(tag)
                        tag_usage[tag] = tag_usage.get(tag, 0) + 1

            # 搜索匹配的标签（支持中英文，不区分大小写）
            query_lower = search_query.lower()
            matching_tags = []

            for tag in all_tags:
                tag_lower = tag.lower()
                if (query_lower in tag_lower or
                    tag_lower.startswith(query_lower) or
                    any(query_lower in word for word in tag_lower.split())):
                    matching_tags.append(tag)

            # 按使用频率排序匹配的标签
            matching_tags.sort(key=lambda x: tag_usage.get(x, 0), reverse=True)

            return {
                "success": True,
                "search_query": search_query,
                "matching_tags": matching_tags,
                "tag_usage": {tag: tag_usage.get(tag, 0) for tag in matching_tags},
                "match_count": len(matching_tags)
            }

        elif action == "get_tag_stats":
            # 获取详细的标签统计信息
            notes = await d1.get_all_notes()

            tag_stats = {}
            category_tags = {}
            priority_tags = {}
            total_notes = len(notes)
            notes_with_tags = 0
            tag_combinations = {}

            for note in notes:
                note_tags = note.get('tags', [])
                if isinstance(note_tags, str):
                    note_tags = [tag.strip() for tag in note_tags.split(',') if tag.strip()]
                elif not isinstance(note_tags, list):
                    note_tags = []

                if note_tags:
                    notes_with_tags += 1

                    # 统计标签组合
                    if len(note_tags) > 1:
                        combo_key = ','.join(sorted(note_tags))
                        tag_combinations[combo_key] = tag_combinations.get(combo_key, 0) + 1

                category = note.get('category', 'other')
                priority = note.get('priority', 'medium')

                for tag in note_tags:
                    if tag:
                        # 总体统计
                        tag_stats[tag] = tag_stats.get(tag, 0) + 1

                        # 分类统计
                        if category not in category_tags:
                            category_tags[category] = {}
                        category_tags[category][tag] = category_tags[category].get(tag, 0) + 1

                        # 优先级统计
                        if priority not in priority_tags:
                            priority_tags[priority] = {}
                        priority_tags[priority][tag] = priority_tags[priority].get(tag, 0) + 1

            # 计算统计数据
            sorted_tags = sorted(tag_stats.items(), key=lambda x: x[1], reverse=True)

            return {
                "success": True,
                "statistics": {
                    "total_unique_tags": len(tag_stats),
                    "total_notes": total_notes,
                    "notes_with_tags": notes_with_tags,
                    "notes_without_tags": total_notes - notes_with_tags,
                    "tagging_rate": notes_with_tags / max(total_notes, 1),
                    "average_tags_per_note": sum(tag_stats.values()) / max(notes_with_tags, 1),
                    "most_used_tags": dict(sorted_tags[:10]),
                    "least_used_tags": dict(sorted_tags[-5:]) if len(sorted_tags) > 5 else {},
                    "tags_by_category": category_tags,
                    "tags_by_priority": priority_tags,
                    "popular_combinations": dict(sorted(tag_combinations.items(), key=lambda x: x[1], reverse=True)[:10])
                }
            }

        elif action == "rename_tag":
            if not tag_name or not tags or not tags[0]:
                return {"success": False, "error": "Both old tag name (tag_name) and new tag name (tags[0]) are required"}

            old_tag = tag_name.strip()
            new_tag = tags[0].strip()

            if old_tag == new_tag:
                return {"success": False, "error": "Old and new tag names are the same"}

            # 获取使用旧标签的所有笔记
            notes = await d1.get_all_notes()
            updated_notes = 0
            affected_notes = []

            for note in notes:
                note_tags = note.get('tags', [])
                if isinstance(note_tags, str):
                    note_tags = [tag.strip() for tag in note_tags.split(',') if tag.strip()]
                elif not isinstance(note_tags, list):
                    note_tags = []

                if old_tag in note_tags:
                    # 替换标签
                    new_tags = [new_tag if tag == old_tag else tag for tag in note_tags]

                    # 更新笔记
                    update_result = await d1.update_note(note['id'], {'tags': new_tags})
                    if update_result:
                        updated_notes += 1
                        affected_notes.append({
                            "note_id": note['id'],
                            "title": note.get('title', '')[:50]
                        })

            return {
                "success": True,
                "message": f"Successfully renamed tag '{old_tag}' to '{new_tag}' in {updated_notes} notes",
                "old_tag": old_tag,
                "new_tag": new_tag,
                "updated_notes": updated_notes,
                "affected_notes": affected_notes[:10]  # 只显示前10个
            }

        elif action == "merge_tags":
            if not tags or len(tags) < 2:
                return {"success": False, "error": "At least 2 tags required for merging (first tag is target)"}

            # 第一个标签作为目标标签，其他的合并到它
            target_tag = tags[0].strip()
            source_tags = [tag.strip() for tag in tags[1:]]

            # 获取使用源标签的所有笔记
            notes = await d1.get_all_notes()
            updated_notes = 0
            affected_notes = []

            for note in notes:
                note_tags = note.get('tags', [])
                if isinstance(note_tags, str):
                    note_tags = [tag.strip() for tag in note_tags.split(',') if tag.strip()]
                elif not isinstance(note_tags, list):
                    note_tags = []

                # 检查是否包含要合并的标签
                has_source_tags = any(tag in source_tags for tag in note_tags)

                if has_source_tags:
                    # 移除源标签，添加目标标签
                    new_tags = [tag for tag in note_tags if tag not in source_tags]
                    if target_tag not in new_tags:
                        new_tags.append(target_tag)

                    # 更新笔记
                    update_result = await d1.update_note(note['id'], {'tags': new_tags})
                    if update_result:
                        updated_notes += 1
                        affected_notes.append({
                            "note_id": note['id'],
                            "title": note.get('title', '')[:50]
                        })

            return {
                "success": True,
                "message": f"Successfully merged {len(source_tags)} tags into '{target_tag}'",
                "target_tag": target_tag,
                "merged_tags": source_tags,
                "updated_notes": updated_notes,
                "affected_notes": affected_notes[:10]
            }

        else:
            return {"success": False, "error": f"Unknown action: {action}"}

    except Exception as e:
        logger.error(f"[TAG_MANAGER] Error in action {action}: {e}", exc_info=True)
        return {"success": False, "error": str(e)}

@mcp.tool()
async def category_manager(
    action: str,
    old_category_name: Optional[str] = None,
    new_category_name: Optional[str] = None
) -> Dict:
    """
    Purpose: Manage note categories (list/stats/rename)
    When: Need to get an overview of categories or perform bulk changes.

    Supported actions:
    - get_all_categories: List all unique categories and their note counts.
    - get_category_stats: Get detailed statistics about category usage.
    - rename_category: Rename a category across all notes.

    Required: action
    Optional: old_category_name, new_category_name (for rename_category)
    Returns: {"success": bool, ...}
    """
    logger.info(f"[CATEGORY_MANAGER] Action: {action}")
    try:
        d1 = get_d1_service()
        notes = await d1.get_all_notes()

        if action == "get_all_categories":
            category_counts = {}
            for note in notes:
                category = note.get('category', 'other')
                category_counts[category] = category_counts.get(category, 0) + 1
            
            sorted_categories = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)
            
            return {
                "success": True,
                "categories": dict(sorted_categories),
                "total_unique_categories": len(category_counts)
            }

        elif action == "get_category_stats":
            category_stats = {}
            total_notes = len(notes)
            notes_with_category = 0

            for note in notes:
                category = note.get('category', 'other')
                if category:
                    notes_with_category += 1
                
                if category not in category_stats:
                    category_stats[category] = {
                        "note_count": 0,
                        "priorities": {},
                        "tags": {}
                    }
                
                category_stats[category]["note_count"] += 1
                
                priority = note.get('priority', 'medium')
                category_stats[category]["priorities"][priority] = category_stats[category]["priorities"].get(priority, 0) + 1
                
                tags = note.get('tags', [])
                if isinstance(tags, str):
                    tags = [tag.strip() for tag in tags.split(',') if tag.strip()]
                
                for tag in tags:
                    category_stats[category]["tags"][tag] = category_stats[category]["tags"].get(tag, 0) + 1

            return {
                "success": True,
                "statistics": {
                    "total_notes": total_notes,
                    "notes_with_category": notes_with_category,
                    "categorization_rate": notes_with_category / max(total_notes, 1),
                    "category_details": category_stats
                }
            }

        elif action == "rename_category":
            if not old_category_name or not new_category_name:
                return {"success": False, "error": "old_category_name and new_category_name are required"}

            if old_category_name == new_category_name:
                return {"success": False, "error": "Old and new category names are the same"}

            updated_notes = 0
            affected_notes = []
            for note in notes:
                if note.get('category') == old_category_name:
                    update_result = await d1.update_note(note['id'], {'category': new_category_name})
                    if update_result:
                        updated_notes += 1
                        affected_notes.append({
                            "note_id": note['id'],
                            "title": note.get('title', '')[:50]
                        })
            
            return {
                "success": True,
                "message": f"Successfully renamed category '{old_category_name}' to '{new_category_name}' in {updated_notes} notes",
                "old_category": old_category_name,
                "new_category": new_category_name,
                "updated_notes_count": updated_notes,
                "affected_notes_preview": affected_notes[:10]
            }

        else:
            return {"success": False, "error": f"Unknown action: {action}"}

    except Exception as e:
        logger.error(f"[CATEGORY_MANAGER] Error in action {action}: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@mcp.tool()
async def smart_tag_suggestions(
    content: str,
    title: Optional[str] = None,
    category: Optional[str] = None,
    existing_tags: Optional[str] = None,
    max_suggestions: int = 5
) -> Dict:
    """
    Purpose: Suggest tags from content/title/context
    Required: content
    Optional: title, category, existing_tags(csv), max_suggestions(5)
    Returns: {"success": bool, "suggested_tags": [...], "tag_scores": {...}}
    Notes: Uses heuristics and system tag similarity
    """
    logger.info(f"[SMART_TAG_SUGGESTIONS] Analyzing content for tag suggestions")

    try:
        import re

        # 合并分析文本
        analysis_text = ""
        if title:
            analysis_text += title + " "
        analysis_text += content

        # 获取现有系统标签作为候选
        d1 = get_d1_service()
        all_notes = await d1.get_all_notes()
        existing_system_tags = set()

        for note in all_notes:
            note_tags = note.get('tags', [])
            if isinstance(note_tags, str):
                note_tags = [tag.strip() for tag in note_tags.split(',') if tag.strip()]
            elif isinstance(note_tags, list):
                existing_system_tags.update(note_tags)

        # 智能关键词提取
        suggested_tags = []

        # 1. 提取#标签
        hashtags = re.findall(r'#([a-zA-Z\u4e00-\u9fa5][a-zA-Z0-9\u4e00-\u9fa5_]*)', analysis_text)
        suggested_tags.extend(hashtags)

        # 2. 关键词匹配（中英文）
        keywords = {
            'work': ['工作', '项目', '任务', '会议', '报告', 'project', 'meeting', 'task', 'work', '办公'],
            'study': ['学习', '研究', '笔记', '课程', '考试', 'study', 'learning', 'course', 'exam', '教育'],
            'personal': ['个人', '生活', '家庭', '健康', 'personal', 'life', 'family', 'health', '日常'],
            'finance': ['财务', '金钱', '投资', '预算', 'finance', 'money', 'investment', 'budget', '理财'],
            'travel': ['旅行', '出行', '旅游', '假期', 'travel', 'trip', 'vacation', 'holiday', '旅程'],
            'technology': ['技术', '编程', '开发', '软件', 'technology', 'programming', 'development', 'software', '科技'],
            'important': ['重要', '紧急', '优先', '关键', 'important', 'urgent', 'priority', 'critical', '必须'],
            'idea': ['想法', '创意', '灵感', '点子', 'idea', 'inspiration', 'creative', 'brainstorm'],
            'plan': ['计划', '规划', '安排', '目标', 'plan', 'planning', 'schedule', 'goal']
        }

        content_lower = analysis_text.lower()
        for tag_category, words in keywords.items():
            for word in words:
                if word.lower() in content_lower:
                    if tag_category not in suggested_tags:
                        suggested_tags.append(tag_category)
                    break

        # 3. 基于现有标签的相似性匹配
        for existing_tag in existing_system_tags:
            if len(existing_tag) > 1:  # 避免单字符标签
                if (existing_tag.lower() in content_lower or
                    any(word in existing_tag.lower() and len(word) > 2 for word in content_lower.split())):
                    if existing_tag not in suggested_tags:
                        suggested_tags.append(existing_tag)

        # 4. 根据分类推荐标签
        if category:
            category_map = {
                'work': ['工作', '项目', '任务', '会议'],
                'study': ['学习', '笔记', '知识', '研究'],
                'personal': ['个人', '生活', '日常', '思考'],
                'idea': ['想法', '创意', '灵感', '计划'],
                'other': ['其他', '杂项', '备忘']
            }

            if category in category_map:
                for cat_tag in category_map[category]:
                    if cat_tag not in suggested_tags:
                        suggested_tags.append(cat_tag)

        # 5. 移除已存在的标签
        if existing_tags:
            existing_tags_list = _parse_tags(existing_tags)
            suggested_tags = [tag for tag in suggested_tags if tag not in existing_tags_list]

        # 6. 计算相关性得分并排序
        tag_scores = {}
        for tag in suggested_tags[:15]:  # 限制计算范围
            score = 0
            tag_lower = tag.lower()

            # 标题匹配得分更高
            if title and tag_lower in title.lower():
                score += 3

            # 内容匹配得分
            content_matches = content_lower.count(tag_lower)
            score += content_matches * 2

            # 已存在系统标签得分更高（说明常用）
            if tag in existing_system_tags:
                score += 1

            # 标签长度适中得分更高
            if 2 <= len(tag) <= 10:
                score += 0.5

            tag_scores[tag] = score

        # 按得分排序并限制数量
        sorted_suggestions = sorted(tag_scores.items(), key=lambda x: x[1], reverse=True)
        final_tags = [tag for tag, score in sorted_suggestions[:max_suggestions] if score > 0]

        return {
            "success": True,
            "suggested_tags": final_tags,
            "tag_scores": dict(sorted_suggestions[:max_suggestions]),
            "analysis_summary": {
                "content_length": len(content),
                "has_title": bool(title),
                "existing_tags_count": len(existing_tags) if existing_tags else 0,
                "system_tags_available": len(existing_system_tags),
                "hashtags_found": len(hashtags)
            }
        }

    except Exception as e:
        logger.error(f"[SMART_TAG_SUGGESTIONS] Error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}

@mcp.tool()
async def recognize_image(image_path: str, prompt: str = "请描述这张图片") -> Dict:
    """
    Purpose: 识别图像内容
    Required: image_path
    Optional: prompt
    Returns: {"success": bool, "data": {...}}
    Notes: 需要图像识别服务可用
    """
    logger.info(f"[VISION] 识别图像: path={image_path}")

    try:
        import os
        # 基础校验：文件路径必须存在
        if not image_path or not os.path.exists(image_path):
            return {"success": False, "error": f"图像文件不存在: {image_path}"}

        # 获取图像识别服务
        vision = get_zhipu_service()  # 底层实现可能调用外部供应商，这里不对外暴露名称

        # 检查服务可用性
        is_available, message = check_zhipu_service_availability()
        if not is_available:
            return {"success": False, "error": f"图像识别服务不可用: {message}"}

        # 调用图像识别功能
        result = vision.recognize_image(image_path, prompt)

        if result.get("success"):
            logger.info("[VISION] 图像识别成功")
            return result
        else:
            logger.error(f"[VISION] 图像识别失败: {_sanitize_recognition_error(result.get('error'), result.get('code'))}")
            # 对外隐藏底层供应商信息
            return {**result, "error": _sanitize_recognition_error(result.get('error'), result.get('code'))}

    except Exception as e:
        logger.error(f"[ZHIPU] 图像识别异常: {e}", exc_info=True)
        return {"success": False, "error": f"图像识别失败: {str(e)}"}

@mcp.tool()
async def zhipu_check_service_health() -> Dict:
    """
    Purpose: Zhipu AI health check
    Returns: {"success": bool, "status": str}
    Notes: Uses service availability check first
    """
    try:
        # 检查服务可用性
        is_available, message = check_zhipu_service_availability()
        if not is_available:
            logger.warning(f"[ZHIPU] 服务不可用: {message}")
            return {
                "success": False,
                "status": message,
                "suggestions": [
                    "请检查 ZHIPU_API_KEY 环境变量是否已设置",
                    "确认 API Key 有效且未过期",
                    "检查网络连接是否正常"
                ]
            }

        # 获取智谱AI服务实例
        zhipu_service = get_zhipu_service()

        # 调用健康检查功能
        result = zhipu_service.check_service_health()

        if result.get("success"):
            logger.info(f"[ZHIPU] 服务健康检查成功，使用模型: {result.get('model_used', 'unknown')}")
        else:
            logger.warning(f"[ZHIPU] 服务健康检查失败: {result.get('status')} - {result.get('details', '')}")

        return result

    except Exception as e:
        logger.error(f"[ZHIPU] 服务健康检查异常: {e}", exc_info=True)
        return {
            "success": False,
            "status": f"健康检查失败: {str(e)}",
            "details": "工具执行过程中发生异常",
            "suggestions": ["请检查日志获取详细错误信息"]
        }

@mcp.tool()
async def process_email_image_attachments(
    email_id: str,
    save_to_notepad: bool = True,
    note_title_prefix: str = "图片识别结果",
    prompt: str = "请描述这张图片的内容"
) -> Dict:
    """
    Purpose: Process email image attachments & optionally save to notes
    Required: email_id
    Optional: save_to_notepad(True), note_title_prefix, prompt
    Returns: {"success": bool, "data": {...}}
    Notes: Ensures Gmail & Zhipu; filters image MIME types/extensions
    """
    logger.info(f"[EMAIL_IMAGE_PROCESSOR] 处理邮件图片附件: email_id={email_id}")

    resolved_id, error = await _get_resolved_email_id(email_id, "EMAIL_IMAGE_PROCESSOR")
    if error:
        return error
    gmail_id = resolved_id
    if gmail_id != email_id:
        logger.info(f"[EMAIL_IMAGE_PROCESSOR] Resolved alias {email_id} -> {gmail_id}")

    try:
        # 确保Gmail服务可用
        is_available, message = await ensure_gmail_service()
        if not is_available:
            return {"success": False, "error": f"Gmail服务不可用: {message}"}

        # 获取智谱AI服务
        zhipu_service = get_zhipu_service()
        is_zhipu_available, zhipu_message = check_zhipu_service_availability()
        if not is_zhipu_available:
            return {"success": False, "error": f"智谱AI服务不可用: {zhipu_message}"}

        # 获取邮件附件
        logger.info(f"[EMAIL_IMAGE_PROCESSOR] 获取邮件附件: {email_id}")
        attachments_result = gmail_service.get_email_attachments(gmail_id)
        if not attachments_result.get("success"):
            return {"success": False, "error": f"获取邮件附件失败: {attachments_result.get('error')}"}

        attachments = attachments_result.get("attachments", [])
        if not attachments:
            return {"success": False, "error": "邮件中没有找到附件"}

        # 筛选图片附件
        image_attachments = []
        supported_image_types = ['image/jpeg', 'image/png', 'image/gif', 'image/bmp', 'image/webp']

        for attachment in attachments:
            content_type = attachment.get('content_type', '').lower()
            filename = attachment.get('filename', '').lower()

            # 通过MIME类型或文件扩展名判断是否为图片
            if content_type in supported_image_types or \
               any(filename.endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']):
                image_attachments.append(attachment)

        if not image_attachments:
            return {"success": False, "error": "邮件中没有找到图片附件"}

        logger.info(f"[EMAIL_IMAGE_PROCESSOR] 找到 {len(image_attachments)} 个图片附件")

        # 处理每个图片附件
        processed_images = []
        d1_service = get_d1_service()
        kv_service = get_kv_service()  # noqa: F841 - used for consistency/future use

        for i, attachment in enumerate(image_attachments):
            try:
                filename = attachment.get('filename', f'attachment_{i}')
                logger.info(f"[EMAIL_IMAGE_PROCESSOR] 处理图片: {filename}")

                # 解码图片数据
                import base64
                image_data = base64.b64decode(attachment['content'])

                # 先保存到记事本文件存储（D1 + KV）
                stored_file_id = None
                try:
                    safe_name = _safe_filename(filename, f"email_attachment_{i}")
                    file_id = str(uuid.uuid4())
                    kv_key = f"file_content:{file_id}"
                    content_type = attachment.get('content_type') or (
                        'image/jpeg' if filename.lower().endswith(('.jpg', '.jpeg')) else
                        'image/png' if filename.lower().endswith('.png') else
                        'image/gif' if filename.lower().endswith('.gif') else
                        'image/bmp' if filename.lower().endswith('.bmp') else
                        'image/webp' if filename.lower().endswith('.webp') else
                        'application/octet-stream'
                    )
                    # 存内容到 KV
                    ok_kv = await kv_service.put_file_content(kv_key, image_data)
                    # 存元数据到 D1
                    file_meta = {
                        'id': file_id,
                        'name': safe_name,
                        'type': 'image',
                        'size': len(image_data),
                        'created_at': datetime.now(BEIJING_TIMEZONE).isoformat(),
                        'updated_at': datetime.now(BEIJING_TIMEZONE).isoformat(),
                        'content_type': content_type,
                        'kv_key': kv_key,
                        'note_id': None,
                        'metadata': {"source": "email_attachment", "email_id": email_id, "gmail_id": gmail_id}
                    }
                    ok_meta = await d1_service.insert_file_metadata(file_meta)
                    if ok_kv and ok_meta:
                        stored_file_id = file_id
                        logger.info(f"[EMAIL_IMAGE_PROCESSOR] 附件已保存到文件库: {stored_file_id}")
                    else:
                        logger.warning(f"[EMAIL_IMAGE_PROCESSOR] 保存附件到文件库失败: KV={ok_kv}, META={ok_meta}")
                except Exception as se:
                    logger.warning(f"[EMAIL_IMAGE_PROCESSOR] 保存附件到文件库异常: {se}")

                # 保存图片到临时文件用于识别
                import tempfile
                import os
                temp_file = None  # noqa: F841 - placeholder for debug/inspection
                with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1]) as tmp_file:
                    tmp_file.write(image_data)
                    temp_file_path = tmp_file.name

                try:
                    # 调用智谱AI进行图像识别（优先使用已保存到文件库的文件名用于日志）
                    logger.info(f"[EMAIL_IMAGE_PROCESSOR] 调用图像识别: {stored_file_id or filename}")
                    recognition_result = zhipu_service.recognize_image(temp_file_path, prompt)

                    if not recognition_result.get("success"):
                        err = recognition_result.get('error')
                        code = recognition_result.get('code')
                        logger.error(f"[EMAIL_IMAGE_PROCESSOR] 图像识别失败: {err} (code={code})")

                        # 智谱额度/限流耗尽时，仍然保存为笔记，标注“识别暂不可用”
                        if save_to_notepad and code in ("1113", 1113, 429):
                            note_title = f"{note_title_prefix}: {filename}"
                            note_content = f"""# 图片识别结果

## 文件信息
- 文件名: {filename}
- 文件大小: {attachment.get('size', 0)} 字节
- 邮件ID: {email_id}

## 识别结果
识别暂不可用（可能是额度耗尽或限流）。

错误信息: {err}

## 识别时间
{datetime.now(BEIJING_TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}

---
*此笔记由邮件图片附件处理功能自动生成*
"""
                            note_data = {
                                'id': str(uuid.uuid4()),
                                'title': note_title,
                                'content': note_content,
                                'created_at': datetime.now(BEIJING_TIMEZONE).isoformat(),
                                'updated_at': datetime.now(BEIJING_TIMEZONE).isoformat(),
                                'category': 'other',
                                'priority': 'medium',
                                'tags': ['图片识别', 'AI分析', '邮件附件', '识别暂不可用'],
                                'reminder_id': None,
                                'file_ids': stored_file_id or ''
                            }


                            insert_result = await d1_service.insert_note(note_data)
                            if insert_result:
                                note_id = note_data['id']
                                logger.info(f"[EMAIL_IMAGE_PROCESSOR] 识别暂不可用，结果已占位保存到笔记: {note_id}")
                                processed_images.append({
                                    "filename": filename,
                                    "success": True,
                                    "description": "识别暂不可用（额度/限流）",
                                    "note_id": note_id,
                                    "usage": {}
                                })
                                continue
                            else:
                                logger.warning(f"[EMAIL_IMAGE_PROCESSOR] 识别暂不可用时保存占位笔记失败")

                        # 默认失败分支（不保存笔记）
                        processed_images.append({
                            "filename": filename,
                            "success": False,
                            "error": err
                        })
                        continue

                    # 获取识别结果
                    recognition_data = recognition_result.get("data", {})
                    description = recognition_data.get("description", "")

                    # 保存到记事本（如果需要）
                    note_id = None
                    if save_to_notepad:
                        # 创建笔记标题
                        note_title = f"{note_title_prefix}: {filename}"
                        # 创建笔记内容
                        note_content = f"""# 图片识别结果

## 文件信息
- 文件名: {filename}
- 文件大小: {attachment.get('size', 0)} 字节
- 邮件ID: {email_id}

## 识别结果
{description}

## 识别时间
{datetime.now(BEIJING_TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}

---
*此笔记由邮件图片附件处理功能自动生成*
"""

                        # 保存笔记
                        note_data = {
                            'id': str(uuid.uuid4()),
                            'title': note_title,
                            'content': note_content,
                            'created_at': datetime.now(BEIJING_TIMEZONE).isoformat(),
                            'updated_at': datetime.now(BEIJING_TIMEZONE).isoformat(),
                            'category': 'other',
                            'priority': 'medium',
                            'tags': ['图片识别', 'AI分析', '邮件附件'],
                            'reminder_id': None,
                            'file_ids': ''
                        }

                        insert_result = await d1_service.insert_note(note_data)
                        if insert_result:
                            note_id = note_data['id']
                            logger.info(f"[EMAIL_IMAGE_PROCESSOR] 识别结果已保存到笔记: {note_id}")
                        else:
                            logger.warning(f"[EMAIL_IMAGE_PROCESSOR] 保存笔记失败")

                    # 添加处理结果
                    processed_images.append({
                        "filename": filename,
                        "success": True,
                        "description": description,
                        "note_id": note_id,
                        "usage": recognition_data.get("usage", {})
                    })

                finally:
                    # 清理临时文件
                    try:
                        if os.path.exists(temp_file_path):
                            os.unlink(temp_file_path)
                    except Exception:
                        pass
            except Exception as e:
                logger.error(f"[EMAIL_IMAGE_PROCESSOR] 处理图片 {filename} 时出错: {e}", exc_info=True)
                processed_images.append({
                    "filename": filename,
                    "success": False,
                    "error": str(e)
                })
                continue

        # 统计结果并返回
        successful_count = sum(1 for img in processed_images if img.get("success"))
        failed_count = len(processed_images) - successful_count
        logger.info(f"[EMAIL_IMAGE_PROCESSOR] 处理完成: 成功 {successful_count}, 失败 {failed_count}")
        return {
            "success": True,
            "email_id": email_id,
            "total_images": len(image_attachments),
            "successful_count": successful_count,
            "failed_count": failed_count,
            "processed_images": processed_images
        }

    except Exception as e:
        logger.error(f"[EMAIL_IMAGE_PROCESSOR] 处理邮件图片附件时出错: {e}", exc_info=True)
        return {"success": False, "error": f"处理邮件图片附件时出错: {str(e)}"}

@mcp.tool()
async def recognize_saved_file(file_id: str, prompt: str = "请描述这张图片") -> Dict:
    """
    Purpose: 使用已保存到文件库的文件进行图像识别
    Required: file_id
    Optional: prompt
    Returns: {"success": bool, ...}
    Notes: 从KV读取内容，落到临时文件后识别；对外不暴露底层供应商名
    """
    try:
        d1 = get_d1_service()
        kv = get_kv_service()
        vision = get_zhipu_service()

        # 读取元数据
        meta = await d1.get_file_metadata(file_id)
        if not meta:
            return {"success": False, "error": "未找到文件元数据"}
        kv_key = meta.get('kv_key')
        if not kv_key:
            return {"success": False, "error": "文件缺少内容键"}

        # 读取内容
        content = await kv.get_file_content(kv_key)
        if content is None:
            return {"success": False, "error": "无法读取文件内容"}

        # 将内容写到临时文件
        import tempfile, os
        suffix = ''
        name = (meta.get('name') or '').lower()
        if '.' in name:
            suffix = f".{name.split('.')[-1]}"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            if isinstance(content, str):
                tmp.write(content.encode('utf-8'))
            else:
                tmp.write(content)
            temp_path = tmp.name

        try:
            # 服务可用性检查
            ok, message = check_zhipu_service_availability()
            if not ok:
                return {"success": False, "error": f"图像识别服务不可用: {message}"}

            # 调用识别
            result = vision.recognize_image(temp_path, prompt)
            if result.get('success'):
                return result
            return {**result, "error": _sanitize_recognition_error(result.get('error'), result.get('code'))}
        finally:
            try:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
            except Exception:
                pass
    except Exception as e:
        logger.error(f"[VISION] recognize_saved_file 异常: {e}", exc_info=True)
        return {"success": False, "error": f"执行失败: {str(e)}"}


@mcp.tool()
async def retry_unrecognized_image_notes(limit: int = 10, prompt: str = "请描述这张图片") -> Dict:
    """
    Purpose: 自动重试“识别暂不可用”的图片笔记
    Optional: limit(默认10), prompt
    Returns: {success, retried, updated, failed}
    策略：
      - 查找包含“识别暂不可用”标签的笔记
      - 解析其 file_ids，从文件库读取并尝试识别
      - 识别成功则更新笔记内容并移除“识别暂不可用”标签
    """
    try:
        d1 = get_d1_service()
        updated = 0
        failed = 0
        retried = 0

        # 获取带标签的笔记（简化使用 get_notes_by_tag）
        notes = await d1.get_notes_by_tag('识别暂不可用')
        if not notes:
            return {"success": True, "retried": 0, "updated": 0, "failed": 0}

        # 限制数量
        notes = notes[: max(0, int(limit))]

        for note in notes:
            try:
                file_ids_raw = note.get('file_ids') or ''
                file_ids = [fid.strip() for fid in file_ids_raw.split(',') if fid.strip()]
                if not file_ids:
                    continue

                # 仅取第一个文件做识别（可扩展为全部）
                file_id = file_ids[0]
                retried += 1
                rec = await _invoke_tool(recognize_saved_file, file_id, prompt)
                if rec.get('success'):
                    desc = rec.get('data', {}).get('description', '')
                    # 生成更新内容（保留原有头信息，替换“识别结果”段）
                    new_content = note.get('content', '')
                    if '## 识别结果' in new_content:
                        head, _, tail = new_content.partition('## 识别结果')
                        # tail 第一行是旧结果标题，替换从此标题起到下一个分隔或结尾
                        new_content = f"{head}## 识别结果\n{desc}\n"
                        if '---' in tail:
                            # 保留时间与尾部说明
                            _, _, after = tail.partition('---')
                            new_content += f"\n---{after}"
                    else:
                        # 没有模板时，直接附加
                        new_content = f"{new_content}\n\n## 识别结果\n{desc}\n"

                    # 去掉标签中的“识别暂不可用”
                    old_tags = note.get('tags') or ''
                    tags = [t for t in old_tags.split(',') if t.strip() and t.strip() != '识别暂不可用']

                    ok = await d1.update_note(note['id'], {
                        'content': new_content,
                        'tags': ','.join(tags) if tags else ''
                    })
                    if ok:
                        updated += 1
                else:
                    failed += 1
            except Exception as ie:
                logger.warning(f"[VISION] 重试单条笔记失败: {ie}")
                failed += 1

        return {"success": True, "retried": retried, "updated": updated, "failed": failed}
    except Exception as e:
        logger.error(f"[VISION] retry_unrecognized_image_notes 异常: {e}", exc_info=True)
        return {"success": False, "error": str(e)}

    except Exception as e:
        logger.error(f"[EMAIL_IMAGE_PROCESSOR] 处理邮件图片附件时出错: {e}", exc_info=True)
        return {"success": False, "error": f"处理邮件图片附件时出错: {str(e)}"}


# ============================================================================
# Voice-friendly MCP tool surface
# ============================================================================

@mcp.tool(name="notepad_note_create", description="创建新笔记。返回 note_id 和 note_latest，后续可直接引用。")
async def notepad_note_create(
    title: str,
    content: str,
    category: str = "other",
    priority: str = "medium",
    tags: Optional[str] = None,
) -> Dict:
    return await _invoke_tool(create_note, title, content, category, priority, tags)


@mcp.tool(name="notepad_note_get", description="读取单篇笔记全文。note_id 支持完整ID、标题、note_1 或 note_latest。")
async def notepad_note_get(note_id: str) -> Dict:
    return await _invoke_tool(get_note, note_id)


@mcp.tool(name="notepad_note_update", description="更新笔记标题、内容、分类、优先级或标签。note_id 支持 note_1/note_latest。")
async def notepad_note_update(
    note_id: str,
    title: Optional[str] = None,
    content: Optional[str] = None,
    category: Optional[str] = None,
    priority: Optional[str] = None,
    tags: Optional[str] = None,
    enable_auto_segment_on_update: bool = False,
) -> Dict:
    return await _invoke_tool(
        update_note,
        note_id,
        title,
        content,
        category,
        priority,
        tags,
        enable_auto_segment_on_update,
    )


@mcp.tool(name="notepad_note_delete", description="删除一篇笔记。note_id 支持完整ID、note_1 或 note_latest。")
async def notepad_note_delete(note_id: str) -> Dict:
    return await _invoke_tool(delete_note, note_id)


@mcp.tool(name="notepad_note_append", description="向现有笔记末尾追加内容，不覆盖原文。")
async def notepad_note_append(note_id: str, content: str) -> Dict:
    return await _invoke_tool(append_to_note, note_id, content)


@mcp.tool(name="notepad_note_list", description="列出最近笔记。返回 note_1、note_2 等别名，便于继续读取或更新。")
async def notepad_note_list(
    limit: int = 20,
    category: Optional[str] = None,
    include_content_preview: bool = True,
) -> Dict:
    return await _invoke_tool(list_recent_notes, limit, category, include_content_preview)


@mcp.tool(name="notepad_note_search", description="按关键词搜索笔记。返回 note_1、note_2 等别名，便于继续操作。")
async def notepad_note_search(
    query: str,
    category: Optional[str] = None,
    priority: Optional[str] = None,
    tags: Optional[str] = None,
) -> Dict:
    return await _invoke_tool(search_notes, query, category, priority, tags)


@mcp.tool(name="notepad_note_tags_get", description="查看一篇笔记的标签。note_id 支持 note_1/note_latest。")
async def notepad_note_tags_get(note_id: str) -> Dict:
    return await _invoke_tool(tag_manager, action="get_note_tags", note_id=note_id)


@mcp.tool(name="notepad_note_tags_add", description="给一篇笔记添加标签。tags 用逗号分隔。")
async def notepad_note_tags_add(note_id: str, tags: str) -> Dict:
    return await _invoke_tool(tag_manager, action="add_tags", note_id=note_id, tags=tags)


@mcp.tool(name="notepad_note_tags_remove", description="从一篇笔记移除标签。tags 用逗号分隔。")
async def notepad_note_tags_remove(note_id: str, tags: str) -> Dict:
    return await _invoke_tool(tag_manager, action="remove_tags", note_id=note_id, tags=tags)


@mcp.tool(name="notepad_tag_list", description="列出记事本中常用标签和使用次数。")
async def notepad_tag_list(limit: int = 100) -> Dict:
    return await _invoke_tool(tag_manager, action="get_all_tags", limit=limit)


@mcp.tool(name="notepad_category_list", description="列出记事本分类和每个分类下的笔记数量。")
async def notepad_category_list() -> Dict:
    return await _invoke_tool(category_manager, action="get_all_categories")


@mcp.tool(name="notepad_email_send", description="发送普通文本邮件。")
async def notepad_email_send(
    to: str,
    subject: str,
    body: str,
    cc: Optional[str] = None,
) -> Dict:
    return await _invoke_tool(send_email_simple, to, subject, body, cc)


@mcp.tool(name="notepad_email_list", description="列出最近邮件。返回 email_1、email_2 等别名，便于继续读取或回复。")
async def notepad_email_list(
    max_results: int = 10,
    label: str = "inbox",
    query: Optional[str] = None,
) -> Dict:
    return await _invoke_tool(get_recent_emails, max_results, label, query)


@mcp.tool(name="notepad_email_read", description="读取邮件正文。email_id 支持 email_1、email_2 等最近邮件别名。")
async def notepad_email_read(email_id: str) -> Dict:
    return await _invoke_tool(get_email_content, email_id)


@mcp.tool(name="notepad_email_mark_read", description="把邮件标记为已读。email_id 支持 email_1 等别名。")
async def notepad_email_mark_read(email_id: str) -> Dict:
    return await _invoke_tool(mark_email_as_read, email_id)


@mcp.tool(name="notepad_email_trash", description="把邮件移到回收站。email_id 支持 email_1 等别名。")
async def notepad_email_trash(email_id: str) -> Dict:
    return await _invoke_tool(trash_email, email_id)


@mcp.tool(name="notepad_email_reply", description="回复一封邮件。email_id 支持 email_1 等别名。")
async def notepad_email_reply(
    email_id: str,
    body: str,
    html_body: Optional[str] = None,
    cc: Optional[str] = None,
) -> Dict:
    return await _invoke_tool(reply_to_email, email_id, body, html_body, cc)


@mcp.tool(name="notepad_email_reply_all", description="回复邮件的所有收件人。email_id 支持 email_1 等别名。")
async def notepad_email_reply_all(
    email_id: str,
    body: str,
    html_body: Optional[str] = None,
) -> Dict:
    return await _invoke_tool(reply_all_to_email, email_id, body, html_body)


@mcp.tool(name="notepad_note_email_attachment", description="把一篇笔记作为 txt 附件发送到邮箱。")
async def notepad_note_email_attachment(
    note_id: str,
    to: str,
    subject: Optional[str] = None,
    body: Optional[str] = None,
    cc: Optional[str] = None,
) -> Dict:
    return await _invoke_tool(send_note_as_email_attachment, note_id, to, subject, body, cc)


@mcp.tool(name="notepad_note_email_html", description="把一篇笔记作为 HTML 邮件正文发送。")
async def notepad_note_email_html(
    note_id: str,
    to: str,
    subject: Optional[str] = None,
    cc: Optional[str] = None,
    include_summary: bool = True,
) -> Dict:
    return await _invoke_tool(send_note_as_html_email, note_id, to, subject, cc, include_summary)


@mcp.tool(name="notepad_note_update_and_email", description="先更新笔记，再把更新后的笔记发送邮件。")
async def notepad_note_update_and_email(
    note_id: str,
    title: Optional[str] = None,
    content: Optional[str] = None,
    category: Optional[str] = None,
    priority: Optional[str] = None,
    tags: Optional[str] = None,
    to: Optional[str] = None,
    subject: Optional[str] = None,
    send_type: str = "attachment",
    cc: Optional[str] = None,
) -> Dict:
    return await _invoke_tool(
        update_note_and_email,
        note_id,
        title,
        content,
        category,
        priority,
        tags,
        to,
        subject,
        send_type,
        cc,
    )


@mcp.tool(name="notepad_search_save", description="把搜索结果或整理后的长文本保存成笔记，可选发送邮件。")
async def notepad_search_save(
    title: str,
    content: str,
    category: Optional[str] = None,
    tags: Optional[str] = None,
    send_email: Optional[str] = None,
) -> Dict:
    return await _invoke_tool(save_search_results_to_notepad, title, content, category, tags, send_email)


@mcp.tool(name="notepad_file_list", description="列出已保存文件的元数据，不返回文件正文。")
async def notepad_file_list(
    limit: int = 20,
    file_type: Optional[str] = None,
    name_contains: Optional[str] = None,
) -> Dict:
    return await _invoke_tool(list_files, limit, file_type, name_contains)


@mcp.tool(name="notepad_file_email_attachment", description="把已保存文件作为邮件附件发送。")
async def notepad_file_email_attachment(
    file_id: str,
    to: str,
    subject: Optional[str] = None,
    body: Optional[str] = None,
    cc: Optional[str] = None,
) -> Dict:
    return await _invoke_tool(send_file_as_email_attachment, file_id, to, subject, body, cc)


@mcp.tool(name="notepad_reminder_create", description="创建邮件提醒。必须在当前对话中向用户确认收件邮箱；不要因为提示词里有默认邮箱就自动代填。未确认时先询问“提醒邮件发送到哪个邮箱？”。如果用户在当前对话里明确说出邮箱，可视为已确认，传 email_to 并将 email_confirmed 设为 true。remind_at 建议使用 ISO 时间字符串。")
async def notepad_reminder_create(
    title: str,
    remind_at: str,
    email_to: Optional[str] = None,
    email_confirmed: bool = False,
    content: Optional[str] = None,
    reminder_type: Optional[str] = None,
    priority: Optional[str] = None,
    notify_methods: Optional[str] = None,
) -> Dict:
    return await _invoke_tool(
        content_manager,
        action="create_reminder",
        title=title,
        content=content,
        remind_at=remind_at,
        reminder_type=reminder_type,
        priority=priority,
        notify_methods=notify_methods,
        email_to=email_to,
        email_confirmed=email_confirmed,
    )


@mcp.tool(name="notepad_reminder_list", description="列出提醒，可按状态和开始时间过滤。")
async def notepad_reminder_list(
    limit: int = 50,
    status: Optional[str] = None,
    start_from: Optional[str] = None,
) -> Dict:
    return await _invoke_tool(list_reminders, limit, status, start_from)


@mcp.tool(name="notepad_reminder_get", description="读取单个提醒详情。")
async def notepad_reminder_get(reminder_id: str) -> Dict:
    return await _invoke_tool(content_manager, action="get_reminder", reminder_id=reminder_id)


@mcp.tool(name="notepad_reminder_update", description="更新提醒标题、内容、时间、优先级或收件邮箱。更新 email_to 前必须向用户确认，并传 email_confirmed=true。")
async def notepad_reminder_update(
    reminder_id: str,
    title: Optional[str] = None,
    remind_at: Optional[str] = None,
    email_to: Optional[str] = None,
    email_confirmed: bool = False,
    content: Optional[str] = None,
    reminder_type: Optional[str] = None,
    priority: Optional[str] = None,
    notify_methods: Optional[str] = None,
) -> Dict:
    return await _invoke_tool(
        content_manager,
        action="update_reminder",
        reminder_id=reminder_id,
        title=title,
        content=content,
        remind_at=remind_at,
        reminder_type=reminder_type,
        priority=priority,
        notify_methods=notify_methods,
        email_to=email_to,
        email_confirmed=email_confirmed,
    )


@mcp.tool(name="notepad_reminder_delete", description="删除一个提醒。")
async def notepad_reminder_delete(reminder_id: str) -> Dict:
    return await _invoke_tool(content_manager, action="delete_reminder", reminder_id=reminder_id)


@mcp.tool(name="notepad_reminder_scheduler_status", description="查看邮件提醒自动调度器是否运行、上次扫描时间和处理数量。")
async def notepad_reminder_scheduler_status() -> Dict:
    return get_reminder_scheduler_status()


@mcp.tool(name="notepad_image_recognize", description="识别本地图片内容。")
async def notepad_image_recognize(
    image_path: str,
    prompt: str = "请描述这张图片",
) -> Dict:
    return await _invoke_tool(recognize_image, image_path, prompt)


@mcp.tool(name="notepad_file_recognize_image", description="识别文件库中已保存图片的内容。")
async def notepad_file_recognize_image(
    file_id: str,
    prompt: str = "请描述这张图片",
) -> Dict:
    return await _invoke_tool(recognize_saved_file, file_id, prompt)


@mcp.tool(name="notepad_email_process_images", description="识别一封邮件里的图片附件，并可保存识别结果到记事本。")
async def notepad_email_process_images(
    email_id: str,
    save_to_notepad: bool = True,
    note_title_prefix: str = "邮件图片识别",
    prompt: str = "请详细描述这张图片的内容",
) -> Dict:
    return await _invoke_tool(
        process_email_image_attachments,
        email_id,
        save_to_notepad,
        note_title_prefix,
        prompt,
    )


@mcp.tool(name="notepad_health_check", description="检查记事本、数据库、KV 和 Gmail 的服务状态。")
async def notepad_health_check() -> Dict:
    system = await _invoke_tool(get_system_status)
    gmail = await _invoke_tool(gmail_health_check)
    return {
        "success": bool(system.get("success") or gmail.get("success")),
        "system": system,
        "gmail": gmail,
    }


VOICE_TOOL_NAMES = (
    "notepad_note_create",
    "notepad_note_get",
    "notepad_note_update",
    "notepad_note_delete",
    "notepad_note_append",
    "notepad_note_list",
    "notepad_note_search",
    "notepad_note_tags_get",
    "notepad_note_tags_add",
    "notepad_note_tags_remove",
    "notepad_tag_list",
    "notepad_category_list",
    "notepad_email_send",
    "notepad_email_list",
    "notepad_email_read",
    "notepad_email_mark_read",
    "notepad_email_trash",
    "notepad_email_reply",
    "notepad_email_reply_all",
    "notepad_note_email_attachment",
    "notepad_note_email_html",
    "notepad_note_update_and_email",
    "notepad_search_save",
    "notepad_file_list",
    "notepad_file_email_attachment",
    "notepad_reminder_create",
    "notepad_reminder_list",
    "notepad_reminder_get",
    "notepad_reminder_update",
    "notepad_reminder_delete",
    "notepad_reminder_scheduler_status",
    "notepad_image_recognize",
    "notepad_file_recognize_image",
    "notepad_email_process_images",
    "notepad_health_check",
)

LEGACY_TOOL_NAMES_TO_HIDE = (
    "append_to_note",
    "batch_note_operations",
    "category_manager",
    "content_manager",
    "create_note",
    "delete_note",
    "email_manager",
    "get_email_content",
    "get_note",
    "get_note_details",
    "get_recent_emails",
    "get_system_status",
    "gmail_health_check",
    "list_files",
    "list_recent_notes",
    "list_reminders",
    "llm_tool",
    "mark_email_as_read",
    "notepad_initialize_components",
    "notepad_manager",
    "process_email_image_attachments",
    "recognize_image",
    "recognize_saved_file",
    "reply_all_to_email",
    "reply_to_email",
    "retry_unrecognized_image_notes",
    "save_search_results_to_notepad",
    "search_notes",
    "send_email_simple",
    "send_file_as_email_attachment",
    "send_note_as_email_attachment",
    "send_note_as_html_email",
    "smart_tag_suggestions",
    "tag_manager",
    "trash_email",
    "update_note",
    "update_note_and_email",
    "zhipu_check_service_health",
)


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _remove_registered_tools(names: Tuple[str, ...]) -> List[str]:
    removed: List[str] = []
    for tool_name in names:
        try:
            mcp.remove_tool(tool_name)
            removed.append(tool_name)
        except Exception as e:
            logger.debug(f"Tool {tool_name} was not removed: {e}")
    return removed


def _configure_tool_surface() -> None:
    surface = os.getenv("NOTEPAD_TOOL_SURFACE", "voice").strip().lower()
    valid_surfaces = {"voice", "legacy", "all", "full", "debug"}
    if surface not in valid_surfaces:
        logger.warning(f"Unknown NOTEPAD_TOOL_SURFACE={surface!r}, falling back to voice")
        surface = "voice"

    if surface == "legacy":
        removed = _remove_registered_tools(VOICE_TOOL_NAMES)
        logger.info(f"Notepad MCP legacy tool surface enabled; hidden {len(removed)} voice aliases")
        return

    expose_legacy = _env_flag("NOTEPAD_EXPOSE_LEGACY_TOOLS", surface in ("all", "full", "debug"))
    if expose_legacy:
        logger.info("Notepad MCP full tool surface enabled; voice aliases and legacy tools are both exposed")
        return

    removed = _remove_registered_tools(LEGACY_TOOL_NAMES_TO_HIDE)
    logger.info(f"Notepad MCP voice tool surface enabled; hidden {len(removed)} legacy/internal tools")


_configure_tool_surface()

async def initialize_services():
    """异步初始化所有服务"""
    global _initialization_complete, d1_service, kv_service, gmail_service, zhipu_service, _initialization_task

    _initialization_complete = False

    try:
        logger.info("Starting asynchronous service initialization...")

        # 1. 诊断环境
        diagnose_environment()

        # 2. 验证配置并初始化服务
        try:
            from services.d1_service import D1Service  # noqa: F401
            from services.kv_service import KVService  # noqa: F401
            logger.info("D1 and KV services imported successfully")
        except ImportError as e:
            logger.warning(f"Could not import services: {e}")
            logger.info("Service will run with limited functionality")

        # 3. 初始化核心服务实例
        logger.info("Initializing core service instances...")
        try:
            # 预热服务实例，但不阻塞
            get_d1_service()
            get_kv_service()
            get_zhipu_service()
            logger.info("Core service instances initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize some service instances: {e}")

        # 4. 检查Gmail服务状态（异步）
        try:
            gmail_ok, gmail_msg = await ensure_gmail_service()
            if gmail_ok:
                logger.info("Gmail service initialized successfully")
            else:
                logger.warning(f"Gmail service not available: {gmail_msg}")
        except Exception as e:
            logger.warning(f"Gmail service initialization failed: {e}")

        # 5. 启动后台服务（如果启用）
        start_redis_listener_if_enabled()
        start_reminder_scheduler()

        # 6. 标记初始化完成
        _initialization_complete = True
        logger.info("✓ All services initialized successfully")

        return True

    except Exception as e:
        _initialization_complete = False
        logger.error(f"Service initialization failed: {e}", exc_info=True)
        return False
    finally:
        _initialization_event.set()
        _initialization_task = None

def main():
    """主函数 - 使用异步初始化和MCP生命周期管理"""
    try:
        logger.info("Starting Notepad MCP server...")

        # 设置初始化标志
        global _initialization_complete, _initialization_task
        _initialization_complete = False
        _initialization_task = None
        _initialization_event.clear()

        # 启动MCP服务 - FastMCP 会处理asyncio循环
        logger.info("启动MCP服务... (stdio)")
        logger.info("Service initialization will be completed on the first tool request")

        # 直接启动MCP服务，初始化将在第一个请求时异步完成
        mcp.run(transport="stdio")

    except Exception as e:
        logger.error(f"主函数执行失败: {e}", exc_info=True)
        # 避免直接退出；交由 mcp-pipe 管理重试
        return


# 为了向后兼容，添加一个同步包装器
async def run_with_init():
    """带完整初始化的运行方式（可选）"""
    try:
        # 先完成初始化
        init_success = await initialize_services()
        if not init_success:
            logger.error("Failed to initialize services")
            return

        # 然后启动MCP服务
        logger.info("Starting MCP server after successful initialization")
        mcp.run(transport="stdio")

    except Exception as e:
        logger.error(f"Failed to run with initialization: {e}", exc_info=True)
        return

if __name__ == "__main__":
    main()
