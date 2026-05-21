"""
Cloudflare D1数据库服务 - 处理结构化数据存储
"""

import aiohttp
import logging
import asyncio
from typing import Optional, List, Dict, Any
from config import CLOUDFLARE_CONFIG, DB_SCHEMA
import json
from datetime import datetime
from models import NoteCategory, NotePriority, FileType

logger = logging.getLogger('D1_SERVICE')

def async_retry(retries=3, delay=1, backoff=2):
    """
    一个异步重试装饰器，用于包装aiohttp请求。
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            _delay = delay
            for i in range(retries):
                try:
                    return await func(*args, **kwargs)
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    logger.warning(f"请求失败 (尝试 {i+1}/{retries}): {e}. 将在 {_delay}s 后重试...")
                    if i == retries - 1:
                        logger.error(f"函数 {func.__name__} 在 {retries} 次尝试后最终失败。")
                        raise  # 在最后一次尝试后重新引发异常
                    await asyncio.sleep(_delay)
                    _delay *= backoff
        return wrapper
    return decorator

class D1Service:
    def __init__(self):
        self.api_token = CLOUDFLARE_CONFIG.get('api_token')
        self.account_id = CLOUDFLARE_CONFIG.get('account_id')
        self.database_id = CLOUDFLARE_CONFIG.get('d1_database_id')

        if not all([self.api_token, self.account_id, self.database_id]):
            logger.critical("D1 Service is not configured. Please check your .env file for CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID, and D1_DATABASE_ID.")
            missing = [k for k, v in {'api_token': self.api_token, 'account_id': self.account_id, 'database_id': self.database_id}.items() if not v]
            raise ValueError(f"D1 Service configuration is incomplete. Missing: {', '.join(missing)}")

        self.base_url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/d1/database/{self.database_id}"
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }
        self._initialized = False
        # 性能优化：添加连接池和会话管理
        self._session = None
        self.last_error = None
        self._connector = aiohttp.TCPConnector(
            limit=10,  # 总连接池大小
            limit_per_host=5,  # 每个主机的连接池大小
            ttl_dns_cache=300,  # DNS缓存5分钟
            use_dns_cache=True,
            keepalive_timeout=60  # 保持连接60秒
        )
        self._session_timeout = aiohttp.ClientTimeout(total=30, connect=10)
    
    async def get_session(self):
        """获取复用的aiohttp会话"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                connector=self._connector,
                timeout=self._session_timeout,
                headers={'User-Agent': 'Notepad-MCP-Service/1.0'}
            )
        return self._session
    
    async def close(self):
        """关闭会话和连接器"""
        if self._session and not self._session.closed:
            await self._session.close()
        if self._connector:
            await self._connector.close()
    
    def __del__(self):
        """析构函数，确保资源清理"""
        if hasattr(self, '_session') and self._session and not self._session.closed:
            try:
                asyncio.create_task(self.close())
            except:
                pass

    def _extract_rows(self, result: Optional[Dict]) -> List[Dict]:
        """Flatten Cloudflare D1 responses into a plain row list."""
        if not isinstance(result, dict):
            return []

        rows = result.get('results')
        if isinstance(rows, list):
            return rows

        container = result.get('result')
        if isinstance(container, list):
            flattened: List[Dict] = []
            for entry in container:
                if not isinstance(entry, dict):
                    continue
                inner_rows = entry.get('results')
                if isinstance(inner_rows, list):
                    flattened.extend(inner_rows)
                elif not entry.get('results') and all(k in entry for k in ('success', 'meta')):
                    continue
                else:
                    flattened.append(entry)
            return flattened

        return []

    def _parse_list_field(self, value: Any) -> List[str]:
        if not value:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return []
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            except (json.JSONDecodeError, TypeError):
                pass
            return [item.strip() for item in raw.replace('，', ',').replace('、', ',').split(',') if item.strip()]
        return [str(value).strip()] if str(value).strip() else []

    def _normalize_note_fields(self, note_data: Dict) -> Dict:
        normalized = dict(note_data)
        normalized['tags'] = self._parse_list_field(normalized.get('tags'))
        normalized['file_ids'] = self._parse_list_field(normalized.get('file_ids'))
        return normalized

    def _result_change_count(self, result: Optional[Dict]) -> Optional[int]:
        if not isinstance(result, dict):
            return None
        metas = []
        if isinstance(result.get('meta'), dict):
            metas.append(result['meta'])
        container = result.get('result')
        if isinstance(container, list):
            for entry in container:
                if isinstance(entry, dict) and isinstance(entry.get('meta'), dict):
                    metas.append(entry['meta'])
        for meta in metas:
            changes = meta.get('changes')
            if changes is not None:
                try:
                    return int(changes)
                except (TypeError, ValueError):
                    return None
        return None

    async def _get_table_columns(self, table_name: str) -> List[str]:
        result = await self.execute_query(f"PRAGMA table_info({table_name})")
        return [str(row.get('name')) for row in self._extract_rows(result) if row.get('name')]

    async def _apply_schema_migrations(self) -> bool:
        reminder_columns = await self._get_table_columns('reminders')
        if 'updated_at' not in reminder_columns:
            logger.info("Adding missing reminders.updated_at column")
            result = await self.execute_query("ALTER TABLE reminders ADD COLUMN updated_at TEXT")
            if not result or result.get('success') is False:
                logger.error(f"Failed to add reminders.updated_at: {result}")
                return False

            result = await self.execute_query(
                "UPDATE reminders SET updated_at = COALESCE(created_at, datetime('now')) "
                "WHERE updated_at IS NULL OR updated_at = ''"
            )
            if not result or result.get('success') is False:
                logger.error(f"Failed to backfill reminders.updated_at: {result}")
                return False

        return True

    @async_retry()
    async def execute_query(self, query: str, params: List[Any] = None) -> Optional[Dict]:
        """执行SQL查询，增加了重试和超时机制，优化连接复用"""
        try:
            session = await self.get_session()
            url = f"{self.base_url}/query"
            data = {
                "sql": query,
                "params": params or []
            }
            async with session.post(url, headers=self.headers, json=data) as response:
                if response.status >= 500:
                    # 对于服务器错误，触发重试
                    logger.warning(f"D1服务器错误 (Status: {response.status}), 将会重试...")
                    response.raise_for_status()

                if response.status == 200:
                    payload = await response.json()
                    if isinstance(payload, dict) and payload.get('success') is False:
                        self.last_error = payload.get('error') or str(payload.get('errors') or payload)
                    else:
                        self.last_error = None
                    return payload
                
                error_text = await response.text()
                logger.error(f"执行查询失败 (Status: {response.status}): {error_text}")
                self.last_error = f"D1 API Error (HTTP {response.status}): {error_text}"
                # 对于客户端错误（如4xx），不应该重试，直接返回失败
                return {"success": False, "error": self.last_error}

        except aiohttp.ClientError as e:
            self.last_error = str(e)
            logger.error(f"查询执行时发生客户端错误: {e}")
            raise  # 重新引发异常以触发重试
        except asyncio.TimeoutError:
            self.last_error = "D1 query timeout"
            logger.error("查询执行超时")
            raise  # 重新引发异常以触发重试
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"执行查询时发生未知错误: {e}")
            return None # 对于未知错误，返回None

    async def initialize_tables(self) -> bool:
        """初始化数据库表"""
        if self._initialized:
            return True
        try:
            # 创建表
            for table_name, schema in DB_SCHEMA.items():
                logger.info(f"Creating table {table_name} if not exists...")
                result = await self.execute_query(schema)
                if not result or result.get('success') is False:
                    logger.error(f"Failed to create table {table_name}: {result}")
                    return False

            if not await self._apply_schema_migrations():
                return False
            
            # 创建索引（包括全文搜索索引）
            indexes = [
                # 笔记表基础索引
                "CREATE INDEX IF NOT EXISTS idx_notes_category ON notes(category)",
                "CREATE INDEX IF NOT EXISTS idx_notes_priority ON notes(priority)",
                "CREATE INDEX IF NOT EXISTS idx_notes_created_at ON notes(created_at)",
                "CREATE INDEX IF NOT EXISTS idx_notes_updated_at ON notes(updated_at)",
                
                # 全文搜索索引 - 提高搜索性能
                "CREATE INDEX IF NOT EXISTS idx_notes_title_fts ON notes(title)",
                "CREATE INDEX IF NOT EXISTS idx_notes_content_fts ON notes(content)",
                "CREATE INDEX IF NOT EXISTS idx_notes_tags_search ON notes(tags)",
                
                # 复合索引 - 优化常见查询组合
                "CREATE INDEX IF NOT EXISTS idx_notes_category_priority ON notes(category, priority)",
                "CREATE INDEX IF NOT EXISTS idx_notes_category_updated ON notes(category, updated_at DESC)",
                "CREATE INDEX IF NOT EXISTS idx_notes_priority_updated ON notes(priority, updated_at DESC)",
                
                # 提醒表索引
                "CREATE INDEX IF NOT EXISTS idx_reminders_status ON reminders(status)",
                "CREATE INDEX IF NOT EXISTS idx_reminders_remind_at ON reminders(remind_at)",
                "CREATE INDEX IF NOT EXISTS idx_reminders_type ON reminders(type)",
                "CREATE INDEX IF NOT EXISTS idx_reminders_priority ON reminders(priority)",
                "CREATE INDEX IF NOT EXISTS idx_reminders_status_remind ON reminders(status, remind_at)",
                "CREATE INDEX IF NOT EXISTS idx_reminders_updated_at ON reminders(updated_at)",
                
                # 文件表索引
                "CREATE INDEX IF NOT EXISTS idx_files_type ON files(type)",
                "CREATE INDEX IF NOT EXISTS idx_files_created_at ON files(created_at)",
                "CREATE INDEX IF NOT EXISTS idx_files_note_id ON files(note_id)",
                "CREATE INDEX IF NOT EXISTS idx_files_name_search ON files(name)"
            ]
            
            for index in indexes:
                logger.info(f"Creating index: {index}")
                result = await self.execute_query(index)
                if not result or result.get('success') is False:
                    logger.error(f"Failed to create index: {result}")
                    return False
            
            self._initialized = True
            logger.info("All D1 database tables and indexes (including FTS) initialized successfully.")
            return True
        except Exception as e:
            logger.error(f"Error initializing tables: {e}")
            return False

    async def _ensure_initialized(self):
        """确保D1服务已初始化"""
        if not self._initialized:
            await self.initialize_tables()

    async def insert_note(self, note_data: Dict) -> Optional[str]:
        """插入笔记"""
        await self._ensure_initialized()
        
        # 导入调试日志器
        from diagnostic_tools import DebugLogger
        debug_logger = DebugLogger()
        
        logger.info(f"[D1_SERVICE] Starting note insertion with data: id={note_data.get('id')}, title={note_data.get('title')}")
        
        # 验证必要字段
        required_fields = ['id', 'title', 'content', 'created_at', 'updated_at']
        missing_fields = [field for field in required_fields if not note_data.get(field)]
        if missing_fields:
            error_msg = f"Missing required fields: {', '.join(missing_fields)}"
            logger.error(f"[D1_SERVICE] {error_msg}")
            debug_logger.log_error_details('D1Service', 'insert_note', ValueError(error_msg), {'note_data': note_data})
            return None

        query = """
            INSERT INTO notes (id, title, content, created_at, updated_at, category, priority, tags, reminder_id, file_ids)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        logger.debug(f"[D1_SERVICE] Prepared SQL query for note insertion: {query}")
        
        # 处理tags数据格式 - 支持字符串和列表两种格式
        tags_value = note_data.get('tags', '')
        if isinstance(tags_value, str):
            # 如果是字符串，直接使用
            tags_param = tags_value
        elif isinstance(tags_value, list):
            # 如果是列表，转换为逗号分隔的字符串
            tags_param = ','.join(tags_value)
        else:
            # 其他类型，转换为字符串
            tags_param = str(tags_value) if tags_value else ''
        
        # 处理file_ids数据格式
        file_ids_value = note_data.get('file_ids', '')
        if isinstance(file_ids_value, str):
            file_ids_param = file_ids_value
        elif isinstance(file_ids_value, list):
            file_ids_param = ','.join(file_ids_value)
        else:
            file_ids_param = str(file_ids_value) if file_ids_value else ''
        
        params = [
            note_data['id'],
            note_data['title'],
            note_data['content'],
            note_data['created_at'],
            note_data['updated_at'],
            note_data.get('category'),
            note_data.get('priority'),
            tags_param,
            note_data.get('reminder_id'),
            file_ids_param
        ]
        
        # 记录SQL查询用于调试
        debug_logger.log_sql_query(query, params)
        logger.info(f"[D1_SERVICE] Inserting note: {note_data['id']}, tags: {tags_param}")
        
        try:
            result = await self.execute_query(query, params)
            if result and result.get('success') is not False:
                debug_logger.log_sql_query(query, params, result)
                logger.info(f"[D1_SERVICE] Note inserted successfully: {note_data['id']}")
                return note_data['id']
            else:
                error_msg = result.get('error', 'Unknown error') if result else 'No response'
                debug_logger.log_sql_query(query, params, result, error_msg)
                logger.error(f"[D1_SERVICE] Failed to insert note: {error_msg}")
                return None
        except Exception as e:
            debug_logger.log_error_details('D1Service', 'insert_note', e, {'note_data': note_data})
            logger.error(f"[D1_SERVICE] Exception inserting note: {e}")
            return None

    async def get_note(self, note_id: str) -> Optional[Dict]:
        """获取笔记"""
        await self._ensure_initialized()
        query = "SELECT * FROM notes WHERE id = ?"
        result = await self.execute_query(query, [note_id])
        if result and result.get('success') is not False:
            rows = self._extract_rows(result)
            if rows:
                return self._normalize_note_fields(rows[0])
        return None

    async def update_note(self, note_id: str, update_data: Dict) -> bool:
        """更新笔记"""
        await self._ensure_initialized()
        
        # 构建动态更新查询
        set_clauses = []
        params = []
        
        # 处理可更新的字段
        if 'title' in update_data:
            set_clauses.append("title = ?")
            params.append(update_data['title'])
        if 'content' in update_data:
            set_clauses.append("content = ?")
            params.append(update_data['content'])
        if 'category' in update_data:
            set_clauses.append("category = ?")
            params.append(update_data['category'])
        if 'priority' in update_data:
            set_clauses.append("priority = ?")
            params.append(update_data['priority'])
        if 'tags' in update_data:
            set_clauses.append("tags = ?")
            # 处理tags格式
            tags_value = update_data['tags']
            if isinstance(tags_value, list):
                params.append(','.join(tags_value))
            else:
                params.append(str(tags_value) if tags_value else '')
        if 'file_ids' in update_data:
            set_clauses.append("file_ids = ?")
            # 处理file_ids格式
            file_ids_value = update_data['file_ids']
            if isinstance(file_ids_value, list):
                params.append(','.join(file_ids_value))
            else:
                params.append(str(file_ids_value) if file_ids_value else '')
        if 'reminder_id' in update_data:
            set_clauses.append("reminder_id = ?")
            params.append(update_data['reminder_id'])
        
        # 总是更新updated_at字段
        set_clauses.append("updated_at = ?")
        from datetime import datetime, timezone, timedelta
        BEIJING_TIMEZONE = timezone(timedelta(hours=8))
        params.append(datetime.now(BEIJING_TIMEZONE).isoformat())
        
        if not set_clauses:
            logger.warning(f"[D1_SERVICE] No valid fields to update for note {note_id}")
            return False
        
        # 添加WHERE条件的参数
        params.append(note_id)
        
        query = f"UPDATE notes SET {', '.join(set_clauses)} WHERE id = ?"
        
        logger.info(f"[D1_SERVICE] Updating note {note_id} with {len(set_clauses)} fields")
        
        try:
            result = await self.execute_query(query, params)
            if result and result.get('success') is not False:
                changes = self._result_change_count(result)
                if changes is not None and changes < 1:
                    logger.warning(f"[D1_SERVICE] Update matched no rows for note {note_id}")
                    return False
                logger.info(f"[D1_SERVICE] Note {note_id} updated successfully")
                return True
            else:
                error_msg = result.get('error', 'Unknown error') if result else 'No response'
                logger.error(f"[D1_SERVICE] Failed to update note {note_id}: {error_msg}")
                return False
        except Exception as e:
            logger.error(f"[D1_SERVICE] Exception updating note {note_id}: {e}")
            return False

    async def delete_note(self, note_id: str) -> bool:
        """删除笔记"""
        await self._ensure_initialized()
        query = "DELETE FROM notes WHERE id = ?"
        result = await self.execute_query(query, [note_id])
        if not result or result.get('success') is False:
            return False
        changes = self._result_change_count(result)
        if changes is not None:
            return changes > 0
        return True

    async def create_reminder(self, reminder_data: Dict) -> Optional[str]:
        """创建提醒"""
        await self._ensure_initialized()
        query = """
            INSERT INTO reminders (
                id, title, content, type, remind_at, recurrence, condition,
                priority, notify_methods, email_to, last_triggered_at, next_trigger_at,
                created_at, updated_at, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        # 处理notify_methods序列化
        notify_methods = reminder_data.get('notify_methods', ['email'])
        if isinstance(notify_methods, list):
            notify_methods_json = json.dumps(notify_methods)
        else:
            notify_methods_json = notify_methods

        params = [
            reminder_data['id'],
            reminder_data['title'],
            reminder_data['content'],
            reminder_data.get('type', 'scheduled'),
            reminder_data.get('remind_at'),
            reminder_data.get('recurrence'),  # JSON字符串或None
            reminder_data.get('condition'),   # JSON字符串或None
            reminder_data.get('priority', 'medium'),
            notify_methods_json,  # JSON字符串
            reminder_data.get('email_to'),
            reminder_data.get('last_triggered_at'),
            reminder_data.get('next_trigger_at'),
            reminder_data['created_at'],
            reminder_data.get('updated_at', reminder_data['created_at']),
            reminder_data.get('status', 'pending')
        ]
        result = await self.execute_query(query, params)
        return reminder_data['id'] if result and result.get('success') is not False else None

    async def get_pending_reminders(self) -> List[Dict]:
        """获取待处理的提醒"""
        await self._ensure_initialized()
        query = """
            SELECT * FROM reminders
            WHERE status = 'pending'
              AND remind_at IS NOT NULL
              AND datetime(remind_at) <= datetime('now')
            ORDER BY datetime(remind_at) ASC
        """
        result = await self.execute_query(query)
        return self._extract_rows(result) if result else []

    async def get_due_email_reminders(self, limit: int = 10, created_after: Optional[str] = None) -> List[Dict]:
        """获取到期且有明确邮件收件人的提醒。"""
        # Scheduler hot path: the table is created by normal service initialization.
        # Avoid running DDL/index initialization on every background polling instance.
        conditions = [
            "status = 'pending'",
            "remind_at IS NOT NULL",
            "datetime(remind_at) <= datetime('now')",
            "email_to IS NOT NULL",
            "TRIM(email_to) != ''",
            "(type IS NULL OR type = 'scheduled')",
        ]
        params: List[Any] = []
        if created_after:
            conditions.append("datetime(created_at) >= datetime(?)")
            params.append(created_after)
        params.append(max(1, int(limit)))
        query = f"""
            SELECT * FROM reminders
            WHERE {' AND '.join(conditions)}
            ORDER BY datetime(remind_at) ASC
            LIMIT ?
        """
        result = await self.execute_query(query, params)
        return self._extract_rows(result) if result else []

    async def claim_reminder_for_processing(self, reminder_id: str) -> bool:
        """抢占一条待处理提醒，避免多个进程重复发送。"""
        # Scheduler hot path; avoid repeated schema initialization before a small update.
        now = datetime.now().isoformat()
        result = await self.execute_query(
            "UPDATE reminders SET status = ?, updated_at = ? WHERE id = ? AND status = 'pending'",
            ['processing', now, reminder_id],
        )
        if not result or result.get('success') is False:
            return False
        changes = self._result_change_count(result)
        return changes is None or changes > 0

    async def mark_reminder_processed(self, reminder_id: str, status: str) -> bool:
        """标记提醒处理结果。status 通常为 completed 或 failed。"""
        # Scheduler hot path; avoid repeated schema initialization before a small update.
        now = datetime.now().isoformat()
        result = await self.execute_query(
            """
            UPDATE reminders
            SET status = ?, last_triggered_at = ?, updated_at = ?
            WHERE id = ? AND status = 'processing'
            """,
            [status, now, now, reminder_id],
        )
        if not result or result.get('success') is False:
            return False
        changes = self._result_change_count(result)
        return changes is None or changes > 0

    async def update_reminder_status(self, reminder_id: str, status: str) -> bool:
        """更新提醒状态"""
        await self._ensure_initialized()
        query = "UPDATE reminders SET status = ?, updated_at = ? WHERE id = ?"
        result = await self.execute_query(query, [status, datetime.now().isoformat(), reminder_id])
        return bool(result and result.get('success') is not False)

    async def insert_file_metadata(self, file_data: Dict) -> bool:
        """插入文件元数据"""
        await self._ensure_initialized()
        query = """
            INSERT INTO files (id, name, type, size, created_at, updated_at, content_type, kv_key, note_id, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = [
            file_data['id'],
            file_data['name'],
            file_data['type'],
            file_data['size'],
            file_data['created_at'],
            file_data['updated_at'],
            file_data.get('content_type', 'application/octet-stream'),
            file_data['kv_key'],
            file_data.get('note_id'),
            json.dumps(file_data.get('metadata', {}))
        ]
        result = await self.execute_query(query, params)
        return bool(result and result.get('success') is not False)

    async def get_file_metadata(self, file_id: str) -> Optional[Dict]:
        """获取文件元数据"""
        await self._ensure_initialized()
        query = "SELECT * FROM files WHERE id = ?"
        result = await self.execute_query(query, [file_id])

        # 处理Cloudflare D1的嵌套返回格式
        file_data = None
        if result and result.get('result'):
            result_data = result['result']
            # 检查是否是嵌套格式
            if isinstance(result_data, list) and len(result_data) > 0:
                if isinstance(result_data[0], dict) and 'results' in result_data[0]:
                    # Cloudflare D1嵌套格式
                    if result_data[0]['results'] and len(result_data[0]['results']) > 0:
                        file_data = result_data[0]['results'][0]
                else:
                    # 标准格式
                    file_data = result_data[0]

        if file_data:
            # 安全地处理时间字段
            try:
                if 'created_at' in file_data and file_data['created_at']:
                    file_data['created_at'] = datetime.fromisoformat(file_data['created_at']).isoformat()
            except (ValueError, TypeError):
                pass

            try:
                if 'updated_at' in file_data and file_data['updated_at']:
                    file_data['updated_at'] = datetime.fromisoformat(file_data['updated_at']).isoformat()
            except (ValueError, TypeError):
                pass

            # 安全地处理metadata字段
            if 'metadata' in file_data and file_data['metadata']:
                try:
                    file_data['metadata'] = json.loads(file_data['metadata'])
                except (json.JSONDecodeError, TypeError):
                    file_data['metadata'] = {}
            else:
                file_data['metadata'] = {}
            return file_data
        return None

    async def update_reminder(self, reminder_id: str, update_data: Dict) -> bool:
        """按字段更新提醒。"""
        await self._ensure_initialized()
        allowed_fields = {
            'title', 'content', 'remind_at', 'type', 'recurrence', 'condition',
            'priority', 'notify_methods', 'email_to', 'status', 'next_trigger_at',
        }
        set_clauses: List[str] = []
        params: List[Any] = []
        for field, value in update_data.items():
            if field not in allowed_fields:
                continue
            if field == 'notify_methods' and isinstance(value, list):
                value = json.dumps(value)
            set_clauses.append(f"{field} = ?")
            params.append(value)

        if not set_clauses:
            return False

        set_clauses.append("updated_at = ?")
        params.append(update_data.get('updated_at', datetime.now().isoformat()))
        params.append(reminder_id)
        query = f"UPDATE reminders SET {', '.join(set_clauses)} WHERE id = ?"
        result = await self.execute_query(query, params)
        if not result or result.get('success') is False:
            return False
        changes = self._result_change_count(result)
        return changes is None or changes > 0

    async def get_reminder(self, reminder_id: str) -> Optional[Dict]:
        """获取提醒"""
        await self._ensure_initialized()
        query = "SELECT * FROM reminders WHERE id = ?"
        result = await self.execute_query(query, [reminder_id])

        # 处理Cloudflare D1的嵌套返回格式
        reminder_data = None
        if result and result.get('result'):
            result_data = result['result']
            # 检查是否是嵌套格式
            if isinstance(result_data, list) and len(result_data) > 0:
                if isinstance(result_data[0], dict) and 'results' in result_data[0]:
                    # Cloudflare D1嵌套格式
                    if result_data[0]['results'] and len(result_data[0]['results']) > 0:
                        reminder_data = result_data[0]['results'][0]
                else:
                    # 标准格式
                    reminder_data = result_data[0]

        if reminder_data:
            # 安全地处理JSON字段
            if 'notify_methods' in reminder_data and reminder_data['notify_methods']:
                reminder_data['notify_methods'] = self._parse_list_field(reminder_data['notify_methods'])
            else:
                reminder_data['notify_methods'] = []

            if 'recurrence' in reminder_data and reminder_data['recurrence']:
                try:
                    reminder_data['recurrence'] = json.loads(reminder_data['recurrence'])
                except (json.JSONDecodeError, TypeError):
                    reminder_data['recurrence'] = None

            if 'condition' in reminder_data and reminder_data['condition']:
                try:
                    reminder_data['condition'] = json.loads(reminder_data['condition'])
                except (json.JSONDecodeError, TypeError):
                    reminder_data['condition'] = None
            return reminder_data
        return None

    async def check_connection(self) -> bool:
        """检查数据库连接状态"""
        try:
            # 执行简单查询测试连接
            result = await self.execute_query("SELECT 1")
            if not result:
                logger.error("Database connection check failed: No result returned")
                return False
            if result.get('success') is False:
                logger.error(f"Database connection check failed: {result.get('errors', [])}")
                return False
            return True
        except Exception as e:
            logger.error(f"Database connection check failed: {e}")
            return False

    async def search_notes(self, query: str, category: Optional[str] = None, priority: Optional[str] = None, tags: Optional[List[str]] = None) -> List[Dict]:
        """增强搜索笔记功能 - 支持更灵活的搜索"""
        await self._ensure_initialized()
        
        # 基础查询
        conditions = []
        params = []
        
        # 文本搜索 - 支持标题和内容搜索
        if query and query.strip():
            # 分词搜索，支持多个关键词
            keywords = query.strip().split()
            if len(keywords) == 1:
                # 单关键词搜索
                conditions.append("(title LIKE ? OR content LIKE ?)")
                search_term = f"%{keywords[0]}%"
                params.extend([search_term, search_term])
            else:
                # 多关键词搜索 - 支持AND和OR逻辑
                keyword_conditions = []
                for keyword in keywords:
                    keyword_conditions.append("(title LIKE ? OR content LIKE ?)")
                    search_term = f"%{keyword}%"
                    params.extend([search_term, search_term])
                conditions.append("(" + " OR ".join(keyword_conditions) + ")")
        
        # 分类筛选 - 支持字符串和枚举
        if category and category.strip():
            conditions.append("category = ?")
            if hasattr(category, 'value'):  # 如果是枚举类型
                params.append(category.value)
            else:  # 如果是字符串
                params.append(category)
        
        # 优先级筛选 - 支持字符串和枚举
        if priority and priority.strip():
            conditions.append("priority = ?")
            if hasattr(priority, 'value'):  # 如果是枚举类型
                params.append(priority.value)
            else:  # 如果是字符串
                params.append(priority)
        
        # 标签筛选 - 改进标签搜索逻辑
        if tags:
            tag_conditions = []
            for tag in tags:
                if tag and tag.strip():
                    # 支持逗号分隔的标签字符串搜索
                    tag_conditions.append("tags LIKE ?")
                    params.append(f"%{tag.strip()}%")
            if tag_conditions:
                conditions.append("(" + " OR ".join(tag_conditions) + ")")
        
        # 构建完整SQL
        if conditions:
            sql_query = f"SELECT * FROM notes WHERE {' AND '.join(conditions)} ORDER BY updated_at DESC LIMIT 50"
        else:
            sql_query = "SELECT * FROM notes ORDER BY updated_at DESC LIMIT 50"
        
        logger.info(f"[D1_SERVICE] Enhanced search query: {sql_query} with {len(params)} params")
        
        try:
            result = await self.execute_query(sql_query, params)
            if result and result.get('success') is not False:
                notes = [self._normalize_note_fields(note_data) for note_data in self._extract_rows(result)]
                logger.info(f"[D1_SERVICE] Found {len(notes)} notes matching search criteria")
                return notes

            return []
        except Exception as e:
            logger.error(f"[D1_SERVICE] Search notes failed: {e}")
            return []

    async def filter_notes(self, category: Optional[NoteCategory] = None, priority: Optional[NotePriority] = None, tags: Optional[List[str]] = None, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Dict]:
        """过滤笔记"""
        await self._ensure_initialized()
        sql_query = "SELECT * FROM notes WHERE 1=1"
        params = []

        if category:
            sql_query += " AND category = ?"
            params.append(category.value)

        if priority:
            sql_query += " AND priority = ?"
            params.append(priority.value)

        if tags:
            tag_conditions = []
            for tag in tags:
                tag_conditions.append("tags LIKE ?")
                params.append(f"%{tag}%")
            if tag_conditions:
                sql_query += " AND (" + " OR ".join(tag_conditions) + ")"

        if start_date:
            sql_query += " AND created_at >= ?"
            params.append(start_date)

        if end_date:
            sql_query += " AND created_at <= ?"
            params.append(end_date)

        sql_query += " ORDER BY updated_at DESC LIMIT 100"
        result = await self.execute_query(sql_query, params)
        if result and result.get('success') is not False:
            return [self._normalize_note_fields(note_data) for note_data in self._extract_rows(result)]
        return []

    async def search_files(self, query: str, type: Optional[FileType] = None, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Dict]:
        """搜索文件"""
        await self._ensure_initialized()
        conditions = ["name LIKE ?"]
        params = [f"%{query}%"]
        
        if type:
            conditions.append("type = ?")
            params.append(type.value)
        if start_date:
            conditions.append("created_at >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("created_at <= ?")
            params.append(end_date)
        
        query = f"SELECT * FROM files WHERE {' AND '.join(conditions)}"
        result = await self.execute_query(query, params)
        return result.get('result', []) if result else []

    async def get_all_tags(self) -> List[str]:
        """获取所有标签"""
        await self._ensure_initialized()
        query = "SELECT DISTINCT tags FROM notes"
        result = await self.execute_query(query)
        rows = self._extract_rows(result)
        if not rows:
            return []
        
        all_tags = set()
        for row in rows:
            if row.get('tags'):
                all_tags.update(self._parse_list_field(row['tags']))
        return sorted(all_tags)

    async def get_statistics(self) -> Dict:
        """获取统计信息"""
        await self._ensure_initialized()
        stats = {}
        
        # 获取笔记统计
        note_stats = await self.execute_query("""
            SELECT 
                COUNT(*) as total_notes,
                COUNT(CASE WHEN category = 'work' THEN 1 END) as work_notes,
                COUNT(CASE WHEN category = 'personal' THEN 1 END) as personal_notes,
                COUNT(CASE WHEN category = 'study' THEN 1 END) as study_notes,
                COUNT(CASE WHEN category = 'other' THEN 1 END) as other_notes
            FROM notes
        """)
        if note_stats and note_stats.get('result'):
            stats['notes'] = note_stats['result'][0]
        
        # 获取提醒统计
        reminder_stats = await self.execute_query("""
            SELECT 
                COUNT(*) as total_reminders,
                COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending_reminders,
                COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_reminders,
                COUNT(CASE WHEN status = 'cancelled' THEN 1 END) as cancelled_reminders
            FROM reminders
        """)
        if reminder_stats and reminder_stats.get('result'):
            stats['reminders'] = reminder_stats['result'][0]
        
        # 获取文件统计
        file_stats = await self.execute_query("""
            SELECT 
                COUNT(*) as total_files,
                COUNT(CASE WHEN type = 'document' THEN 1 END) as document_files,
                COUNT(CASE WHEN type = 'image' THEN 1 END) as image_files,
                COUNT(CASE WHEN type = 'audio' THEN 1 END) as audio_files,
                COUNT(CASE WHEN type = 'video' THEN 1 END) as video_files,
                COUNT(CASE WHEN type = 'other' THEN 1 END) as other_files,
                SUM(size) as total_size
            FROM files
        """)
        if file_stats and file_stats.get('result'):
            stats['files'] = file_stats['result'][0]
        
        return stats

    async def get_usage_statistics(self) -> Dict:
        """获取使用统计"""
        await self._ensure_initialized()
        usage_stats = {}
        
        # 获取最近7天的笔记创建统计
        note_creation = await self.execute_query("""
            SELECT 
                date(created_at) as date,
                COUNT(*) as count
            FROM notes
            WHERE created_at >= datetime('now', '-7 days')
            GROUP BY date(created_at)
            ORDER BY date
        """)
        if note_creation and note_creation.get('result'):
            usage_stats['note_creation'] = note_creation['result']
        
        # 获取最近7天的提醒触发统计
        reminder_triggers = await self.execute_query("""
            SELECT 
                date(last_triggered_at) as date,
                COUNT(*) as count
            FROM reminders
            WHERE last_triggered_at >= datetime('now', '-7 days')
            GROUP BY date(last_triggered_at)
            ORDER BY date
        """)
        if reminder_triggers and reminder_triggers.get('result'):
            usage_stats['reminder_triggers'] = reminder_triggers['result']
        
        # 获取最近7天的文件上传统计
        file_uploads = await self.execute_query("""
            SELECT 
                date(created_at) as date,
                COUNT(*) as count,
                SUM(size) as total_size
            FROM files
            WHERE created_at >= datetime('now', '-7 days')
            GROUP BY date(created_at)
            ORDER BY date
        """)
        if file_uploads and file_uploads.get('result'):
            usage_stats['file_uploads'] = file_uploads['result']
        
        return usage_stats

    async def get_all_notes(self) -> List[Dict]:
        """获取所有笔记"""
        await self._ensure_initialized()
        result = await self.execute_query("SELECT * FROM notes ORDER BY updated_at DESC LIMIT 500")
        return [self._normalize_note_fields(row) for row in self._extract_rows(result)] if result else []

    async def get_all_reminders(self) -> List[Dict]:
        """获取所有提醒"""
        await self._ensure_initialized()
        result = await self.execute_query("SELECT * FROM reminders")
        return result.get('result', []) if result else []

    async def get_all_files(self) -> List[Dict]:
        """获取所有文件"""
        await self._ensure_initialized()
        result = await self.execute_query("SELECT * FROM files")
        return result.get('result', []) if result else []

    async def delete_reminder(self, reminder_id: str) -> bool:
        """删除提醒"""
        await self._ensure_initialized()
        query = "DELETE FROM reminders WHERE id = ?"
        result = await self.execute_query(query, [reminder_id])
        if not result or result.get('success') is False:
            return False
        changes = self._result_change_count(result)
        if changes is not None:
            return changes > 0
        return True

    async def delete_file_metadata(self, file_id: str) -> bool:
        """删除文件元数据"""
        await self._ensure_initialized()
        query = "DELETE FROM files WHERE id = ?"
        result = await self.execute_query(query, [file_id])
        return bool(result)
    
    async def get_notes_by_tag(self, tag: str) -> List[Dict]:
        """根据标签获取笔记"""
        await self._ensure_initialized()
        # 使用LIKE操作符搜索包含指定标签的笔记
        query = "SELECT * FROM notes WHERE tags LIKE ? ORDER BY updated_at DESC"
        search_pattern = f"%{tag}%"
        result = await self.execute_query(query, [search_pattern])
        
        notes = []
        if result and result.get('success') is not False:
            # 处理不同的返回格式
            rows = []
            if 'results' in result:
                rows = result['results']
            elif 'result' in result:
                rows = result['result']
            
            for note_data in rows:
                # 处理tags和file_ids格式
                if 'tags' in note_data and note_data['tags']:
                    if isinstance(note_data['tags'], str):
                        try:
                            note_data['tags'] = json.loads(note_data['tags'])
                        except json.JSONDecodeError:
                            note_data['tags'] = [tag.strip() for tag in note_data['tags'].split(',') if tag.strip()]
                    elif not isinstance(note_data['tags'], list):
                        note_data['tags'] = []
                else:
                    note_data['tags'] = []
                
                if 'file_ids' in note_data and note_data['file_ids']:
                    if isinstance(note_data['file_ids'], str):
                        try:
                            note_data['file_ids'] = json.loads(note_data['file_ids'])
                        except json.JSONDecodeError:
                            note_data['file_ids'] = [fid.strip() for fid in note_data['file_ids'].split(',') if fid.strip()]
                    elif not isinstance(note_data['file_ids'], list):
                        note_data['file_ids'] = []
                else:
                    note_data['file_ids'] = []
                
                notes.append(note_data)
        return notes
    
    async def get_notes_by_tags(self, tags: List[str], match_all: bool = False) -> List[Dict]:
        """根据多个标签获取笔记"""
        await self._ensure_initialized()
        
        if not tags:
            return []
        
        # 构建查询条件
        conditions = []
        params = []
        
        for tag in tags:
            conditions.append("tags LIKE ?")
            params.append(f"%{tag}%")
        
        # 根据match_all参数决定使用AND还是OR连接条件
        operator = " AND " if match_all else " OR "
        where_clause = operator.join(conditions)
        
        query = f"SELECT * FROM notes WHERE {where_clause} ORDER BY updated_at DESC"
        result = await self.execute_query(query, params)
        
        notes = []
        if result and result.get('success') is not False:
            # 处理不同的返回格式
            rows = []
            if 'results' in result:
                rows = result['results']
            elif 'result' in result:
                rows = result['result']
            
            for note_data in rows:
                # 处理tags和file_ids格式
                if 'tags' in note_data and note_data['tags']:
                    if isinstance(note_data['tags'], str):
                        try:
                            note_data['tags'] = json.loads(note_data['tags'])
                        except json.JSONDecodeError:
                            note_data['tags'] = [tag.strip() for tag in note_data['tags'].split(',') if tag.strip()]
                    elif not isinstance(note_data['tags'], list):
                        note_data['tags'] = []
                else:
                    note_data['tags'] = []
                
                if 'file_ids' in note_data and note_data['file_ids']:
                    if isinstance(note_data['file_ids'], str):
                        try:
                            note_data['file_ids'] = json.loads(note_data['file_ids'])
                        except json.JSONDecodeError:
                            note_data['file_ids'] = [fid.strip() for fid in note_data['file_ids'].split(',') if fid.strip()]
                    elif not isinstance(note_data['file_ids'], list):
                        note_data['file_ids'] = []
                else:
                    note_data['file_ids'] = []
                
                notes.append(note_data)
        return notes
