"""
Redis跨服务通信处理模块
处理来自其他MCP服务的请求
"""

import asyncio
import json
import logging
import threading
import time
import traceback
from datetime import datetime
from typing import Dict, Any, Optional
import redis
import os

logger = logging.getLogger('REDIS_SERVICE')

class RedisServiceHandler:
    """Redis跨服务通信处理器"""

    def __init__(self, notepad_service):
        """
        初始化Redis服务处理器

        Args:
            notepad_service: notepad MCP服务实例
        """
        self.notepad_service = notepad_service
        try:
            self.loop = asyncio.get_running_loop()
        except RuntimeError:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
        self.running = False
        self.listener_thread = None
        self._inflight_lock = threading.Lock()
        self._inflight_requests = 0
        self._max_inflight_requests = max(1, int(os.getenv('REDIS_MAX_INFLIGHT_REQUESTS', '10')))
        self._backpressure_sleep_sec = float(os.getenv('REDIS_BACKPRESSURE_SLEEP_SEC', '0.2'))
        self._last_backpressure_log = 0.0

        # 在线状态与告警节流
        self.redis_online = False
        self._downtime_started_at = None
        self._last_error_time = 0.0
        self._last_error_msg = ""
        self._error_throttle_sec = int(os.getenv('REDIS_ERROR_THROTTLE_SEC', '60'))

        # Redis配置 - 与websearch服务保持一致
        self.redis_host = os.getenv('MCP_REDIS_HOST', 'localhost')
        self.redis_port = int(os.getenv('MCP_REDIS_PORT', '6380'))
        self.redis_db = int(os.getenv('MCP_REDIS_DB', '1'))
        self.redis_password = os.getenv('MCP_REDIS_PASSWORD', None)

        # Redis连接池配置 - 性能优化
        self._redis_pool = None
        self._redis_config = {
            'host': self.redis_host,
            'port': self.redis_port,
            'db': self.redis_db,
            'decode_responses': True,
            'socket_timeout': 5,
            'socket_connect_timeout': 5,
            'max_connections': 20,  # 增加连接池大小
            'retry_on_timeout': True,
            'retry_on_error': [redis.ConnectionError, redis.TimeoutError],  # 使用列表，兼容内部 append 行为
            'health_check_interval': 30  # 健康检查间隔
        }
        # 兼容不同版本 redis-py 的 Retry/Backoff 导入（v4: redis.retry/redis.backoff 模块）
        try:
            from redis.retry import Retry as _Retry
            from redis.backoff import ExponentialBackoff as _ExponentialBackoff
            self._redis_config['retry'] = _Retry(_ExponentialBackoff(), 3)
        except Exception:
            # 旧版本或移除顶层导出时，忽略重试设置，保留 retry_on_error/timeout 即可
            pass
        if self.redis_password:
            self._redis_config['password'] = self.redis_password

        logger.info(
            "Redis服务处理器初始化: %s:%s/db%s, max_inflight=%s",
            self.redis_host, self.redis_port, self.redis_db, self._max_inflight_requests
        )

    def get_redis_connection(self):
        """获取Redis连接 - 优化版本"""
        if self._redis_pool is None:
            self._redis_pool = redis.ConnectionPool(**self._redis_config)

        return redis.Redis(connection_pool=self._redis_pool)

    def start_listener(self):
        """启动Redis请求监听器"""
        if self.running:
            logger.warning("Redis监听器已在运行")
            return

        try:
            # 测试Redis连接
            r = self.get_redis_connection()
            r.ping()
            logger.info("Redis连接测试成功")

            # 连接成功，标记在线
            self.redis_online = True
            self._downtime_started_at = None

            self.running = True
            self.listener_thread = threading.Thread(target=self._listen_requests, daemon=True)
            self.listener_thread.start()
            logger.info("Redis请求监听器已启动")

        except Exception as e:
            logger.error(f"启动Redis监听器失败: {e}")
            raise

    def stop_listener(self):
        """停止Redis请求监听器"""
        self.running = False
        if self.listener_thread and self.listener_thread.is_alive():
            self.listener_thread.join(timeout=5)
        logger.info("Redis请求监听器已停止")

    def _listen_requests(self):
        """监听并处理Redis请求"""
        logger.info("开始监听notepad_requests队列...")

        while self.running:
            try:
                if not self._try_acquire_request_slot():
                    self._log_backpressure()
                    time.sleep(self._backpressure_sleep_sec)
                    continue

                r = self.get_redis_connection()

                # 阻塞等待请求（1秒超时，避免长时间阻塞）
                result = r.brpop("notepad_requests", timeout=1)

                if not result:
                    self._release_request_slot()
                    continue

                # 如果之前处于离线状态，此处说明已恢复
                if not self.redis_online:
                    self.redis_online = True
                    downtime = None
                    if self._downtime_started_at:
                        downtime = round(time.time() - self._downtime_started_at, 1)
                    logger.info(f"Redis监听器已恢复在线{f'，离线时长 {downtime}s' if downtime else ''}")
                    self._downtime_started_at = None

                queue_name, request_data = result
                try:
                    request = json.loads(request_data)
                    worker = threading.Thread(
                        target=self._run_request_worker,
                        args=(request,),
                        daemon=True,
                    )
                    worker.start()
                except json.JSONDecodeError as e:
                    self._release_request_slot()
                    logger.error(f"请求数据解析失败: {e}")
                except Exception as e:
                    self._release_request_slot()
                    logger.error(f"处理请求失败: {e}")

            except redis.ConnectionError as e:
                self._release_request_slot()
                # 掉线处理 + 告警节流
                now = time.time()
                msg = f"Redis连接错误: {e}"
                if (now - self._last_error_time > self._error_throttle_sec) or (msg != self._last_error_msg):
                    logger.warning(msg)
                    self._last_error_time = now
                    self._last_error_msg = msg
                if self.redis_online:
                    self.redis_online = False
                    self._downtime_started_at = now
                    logger.warning("Redis监听器离线，开始自动重连...")
                time.sleep(5)  # 连接失败时等待5秒重试
            except Exception as e:
                self._release_request_slot()
                logger.warning(f"监听请求时发生错误: {e}")
                time.sleep(1)

    def _try_acquire_request_slot(self) -> bool:
        with self._inflight_lock:
            if self._inflight_requests >= self._max_inflight_requests:
                return False
            self._inflight_requests += 1
            return True

    def _release_request_slot(self):
        with self._inflight_lock:
            if self._inflight_requests > 0:
                self._inflight_requests -= 1

    def _log_backpressure(self):
        now = time.time()
        if now - self._last_backpressure_log >= 10:
            logger.warning(
                "Redis请求处理达到并发上限: inflight=%s, max=%s",
                self._inflight_requests, self._max_inflight_requests
            )
            self._last_backpressure_log = now

    def _log_future_result(self, future):
        """记录异步任务的结果或异常"""
        try:
            future.result()
        except Exception as e:
            logger.error(f"处理Redis请求的异步任务失败: {e}\n{traceback.format_exc()}")
        finally:
            self._release_request_slot()

    def _run_request_worker(self, request: Dict[str, Any]):
        """Run one Redis request in its own event loop.

        The listener starts before FastMCP owns the main asyncio loop, so using
        run_coroutine_threadsafe against self.loop can enqueue work onto a loop
        that never runs. A short-lived worker loop guarantees every consumed
        Redis request either returns a response or logs a concrete failure.
        """
        try:
            asyncio.run(self._process_request_async(request))
        except Exception as e:
            logger.error(f"处理Redis请求的异步任务失败: {e}\n{traceback.format_exc()}")
        finally:
            self._release_request_slot()

    async def _process_request_async(self, request: Dict[str, Any]):
        """处理具体的跨服务请求（异步）"""
        try:
            request_id = request.get("id")
            action = request.get("action", "")
            params = request.get("params", {})
            from_service = request.get("from_service", "unknown")

            logger.info(f"处理请求 {request_id}: {action} from {from_service}")

            normalized_action = (action or "").lower()
            if normalized_action == "test_connection":
                result = self._handle_test_connection()
            elif normalized_action in ("create", "create_note", "createnote"):
                result = await self._handle_create_note(params)
            elif normalized_action == "get_file":
                result = await self._handle_get_file(params)
            elif normalized_action in ("send_email", "sendmail"):
                result = await self._handle_send_email(params)
            elif normalized_action in ("邮件管理",):
                result = await self._handle_email_management(params)
            else:
                result = {
                    "success": False,
                    "error": f"未知操作: {action}",
                    "supported_actions": [
                        "test_connection", "create", "create_note", "get_file",
                        "send_email", "邮件管理"
                    ]
                }
            self._send_response(request_id, result)

        except Exception as e:
            error_msg = f"处理请求失败: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_msg)
            error_response = {
                "success": False,
                "error": error_msg,
                "timestamp": datetime.now().isoformat()
            }
            self._send_response(request.get("id"), error_response)

    def _send_response(self, request_id: str, response: Dict[str, Any]):
        """发送响应到Redis"""
        try:
            r = self.get_redis_connection()
            response_key = f"response_{request_id}"

            # 添加响应时间戳
            response["response_timestamp"] = datetime.now().isoformat()

            # 发送响应并设置过期时间（5分钟）
            r.lpush(response_key, json.dumps(response, ensure_ascii=False))
            r.expire(response_key, 300)  # 5分钟过期

            logger.info(f"已发送响应: {request_id}")

        except Exception as e:
            logger.error(f"发送响应失败: {e}")

    def _handle_test_connection(self) -> Dict[str, Any]:
        """处理连接测试请求"""
        return {
            "success": True,
            "message": "notepad服务连接正常",
            "service": "notepad_mcp_fixed",
            "timestamp": datetime.now().isoformat()
        }

    async def _handle_create_note(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理创建笔记请求 - 真实调用D1服务"""
        try:
            # 提取参数
            title = params.get("title", "来自WebSearch的搜索结果")
            content = params.get("content", "")
            category = params.get("category", "other")
            tags = params.get("tags", "搜索结果")
            send_email = params.get("send_email")

            logger.info(f"[REDIS_SERVICE] Creating note with title: {title}")

            # 调用真实的D1服务
            from services.d1_service import D1Service
            from datetime import datetime, timezone, timedelta

            # 创建北京时间时区
            BEIJING_TIMEZONE = timezone(timedelta(hours=8))

            # 构建笔记数据
            note_data = {
                'id': str(datetime.now().timestamp()),
                'title': title,
                'content': content,
                'created_at': datetime.now(BEIJING_TIMEZONE).isoformat(),
                'updated_at': datetime.now(BEIJING_TIMEZONE).isoformat(),
                'category': category,
                'priority': 'medium',
                'tags': tags,
                'reminder_id': None,
                'file_ids': ''
            }
            
            d1_service = D1Service()
            result = await d1_service.insert_note(note_data)

            if result:
                response = {
                    "success": True,
                    "note_id": note_data['id'],
                    "title": title,
                    "category": category,
                    "tags": tags,
                    "message": "笔记创建成功"
                }

                # 如果有邮箱参数，记录邮件发送请求
                if send_email:
                    response["email_requested"] = send_email
                    response["message"] += "，邮件发送请求已记录"

                logger.info(f"[REDIS_SERVICE] Note created successfully: {note_data['id']}")
                return response
            else:
                logger.error(f"[REDIS_SERVICE] D1 service failed to create note")
                return {
                    "success": False,
                    "error": "D1服务创建笔记失败"
                }
        except Exception as e:
            logger.error(f"[REDIS_SERVICE] Create note failed: {e}")
            return {
                "success": False,
                "error": f"创建笔记失败: {str(e)}"
            }

    async def _handle_get_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理获取文件请求 - 真实调用KV和D1服务"""
        try:
            file_id = params.get("file_id")
            if not file_id:
                return {"success": False, "error": "缺少file_id参数"}

            logger.info(f"[REDIS_SERVICE] Getting file: {file_id}")

            # 调用真实的D1和KV服务
            from services.d1_service import D1Service
            from services.kv_service import KVService
            
            d1_service = D1Service()
            kv_service = KVService()

            # 获取文件元数据
            file_metadata = await d1_service.get_file_metadata(file_id)
            if not file_metadata:
                return {"success": False, "error": "文件元数据未找到"}

            # 获取文件内容
            file_content = await kv_service.get_file_content(file_metadata['kv_key'])
            if not file_content:
                return {"success": False, "error": "文件内容未找到"}

            return {
                "success": True,
                "file_id": file_id,
                "filename": file_metadata.get('name', '未知文件'),
                "content_type": file_metadata.get('content_type', 'application/octet-stream'),
                "size": file_metadata.get('size', 0),
                "content": file_content,
                "message": "文件获取成功"
            }
        except Exception as e:
            logger.error(f"[REDIS_SERVICE] Get file failed: {e}")
            return {
                "success": False,
                "error": f"获取文件失败: {str(e)}"
            }

    async def _handle_send_email(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理发送邮件请求 - 真实调用Gmail服务"""
        try:
            to_email = params.get("to_email")
            subject = params.get("subject", "来自记事本MCP的邮件")
            content = params.get("content", "")
            note_id = params.get("note_id")
            file_id = params.get("file_id")
            attachment_type = params.get("attachment_type", "text")  # text, note, file

            if not to_email:
                return {"success": False, "error": "缺少收件人邮箱"}

            logger.info(f"[REDIS_SERVICE] Sending email to: {to_email}")

            from services.gmail_service import GmailService
            gmail_service = GmailService()
            
            # 根据附件类型处理
            if attachment_type == "note" and note_id:
                from services.d1_service import D1Service
                d1_service = D1Service()
                note = await d1_service.get_note(note_id)

                if note:
                    attachment = {
                        'filename': f"{note.get('title', '笔记')}.txt",
                        'content': note.get('content', ''),
                        'content_type': 'text/plain; charset=utf-8'
                    }
                    result = gmail_service._send_raw_email(
                        to=to_email,
                        subject=subject,
                        body=content or f"请查看附件中的笔记：{note.get('title', '未知标题')}",
                        attachments=[attachment]
                    )
                else:
                    return {"success": False, "error": "笔记未找到"}

            elif attachment_type == "file" and file_id:
                file_result = await self._handle_get_file({"file_id": file_id})
                if file_result.get("success"):
                    attachment = {
                        'filename': file_result.get('filename', '文件'),
                        'content': file_result.get('content', ''),
                        'content_type': file_result.get('content_type', 'application/octet-stream')
                    }
                    result = gmail_service._send_raw_email(
                        to=to_email,
                        subject=subject,
                        body=content or f"请查看附件中的文件：{file_result.get('filename', '未知文件')}",
                        attachments=[attachment]
                    )
                else:
                    return {"success": False, "error": "文件获取失败"}
            else:
                result = gmail_service._send_raw_email(
                    to=to_email,
                    subject=subject,
                    body=content
                )

            if result.get('success'):
                return {
                    "success": True,
                    "message_id": result.get('message_id'),
                    "message": "邮件发送成功",
                    "to_email": to_email,
                    "subject": subject
                }
            else:
                return {
                    "success": False,
                    "error": f"邮件发送失败: {result.get('error', '未知错误')}"
                }
        except Exception as e:
            logger.error(f"[REDIS_SERVICE] Send email failed: {e}")
            return {
                "success": False,
                "error": f"发送邮件失败: {str(e)}"
            }

    async def _handle_email_management(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理邮件管理请求 - 真实调用Gmail服务"""
        try:
            email_action = params.get("action", "")

            if email_action == "send_email":
                return await self._handle_send_email(params)
            elif email_action == "test_connection":
                # 调用真实的Gmail服务进行连接测试
                from services.gmail_service import GmailService
                gmail_service = GmailService()
                health_result = gmail_service.check_service_health()

                if health_result.get('success'):
                    return {
                        "success": True,
                        "message": "邮件服务连接正常",
                        "details": health_result
                    }
                else:
                    return {
                        "success": False,
                        "error": f"邮件服务连接异常: {health_result.get('error', '未知错误')}"
                    }
            else:
                return {
                    "success": False,
                    "error": f"未知邮件操作: {email_action}",
                    "supported_actions": ["send_email", "test_connection"]
                }
        except Exception as e:
            logger.error(f"[REDIS_SERVICE] Email management failed: {e}")
            return {
                "success": False,
                "error": f"邮件管理失败: {str(e)}"
            }
