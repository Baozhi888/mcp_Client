"""
Cloudflare KV服务 - 处理文件存储
"""

import aiohttp
import logging
import json
import asyncio
from typing import Optional, Dict, Any, List, Union
from config import CLOUDFLARE_CONFIG

logger = logging.getLogger('KV_SERVICE')

class KVService:
    def __init__(self):
        self.api_token = CLOUDFLARE_CONFIG['api_token']
        self.account_id = CLOUDFLARE_CONFIG['account_id']
        self.namespace_id = CLOUDFLARE_CONFIG['kv_namespace_id']
        self.base_url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/storage/kv/namespaces/{self.namespace_id}"
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }
        self._initialized = True # 直接设置为True，因为不再依赖KV对象的初始化
        
        # 性能优化：添加连接池和会话管理
        self._session = None
        self._connector = aiohttp.TCPConnector(
            limit=10,  # 总连接池大小
            limit_per_host=5,  # 每个主机的连接池大小
            ttl_dns_cache=300,  # DNS缓存5分钟
            use_dns_cache=True,
            keepalive_timeout=60  # 保持连接60秒
        )
        self._session_timeout = aiohttp.ClientTimeout(total=30, connect=10)
        
        # 初始化 KV 命名空间 (移除旧的错误初始化逻辑)
        # try:
        #     import cloudflare
        #     self._namespace = cloudflare.KV(self.namespace_id)
        #     self._initialized = True
        # except Exception as e:
        #     logger.error(f"Failed to initialize KV namespace: {e}")
        #     self._initialized = False
    
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

    async def check_connection(self) -> bool:
        """检查KV连接状态"""
        try:
            # 尝试获取一个测试键，以验证连接
            session = await self.get_session()
            url = f"{self.base_url}/values/test_connection"
            async with session.get(url, headers=self.headers) as response:
                return response.status in [200, 404] # 404表示键不存在，但连接正常
        except Exception as e:
            logger.error(f"KV connection check failed: {e}")
            return False

    async def put(self, key: str, value: Any) -> bool:
        """存储键值对 (通用方法)"""
        try:
            session = await self.get_session()
            url = f"{self.base_url}/values/{key}"
            # 对于KV，直接put原始数据或字符串
            if isinstance(value, dict) or isinstance(value, list):
                payload = json.dumps(value)
                headers = self.headers.copy()
                headers["Content-Type"] = "application/json"
            elif isinstance(value, bytes):
                payload = value
                headers = self.headers.copy()
                headers["Content-Type"] = "application/octet-stream"
            else:
                payload = str(value)
                headers = self.headers.copy()
                headers["Content-Type"] = "text/plain"

            async with session.put(url, headers=headers, data=payload) as response:
                if response.status == 200:
                    return True
                logger.error(f"Failed to put value to {key}: {await response.text()}")
                return False
        except Exception as e:
            logger.error(f"Error putting value {key}: {e}")
            return False

    async def put_file_content(self, key: str, content: Union[str, bytes]) -> bool:
        """存储文件内容"""
        # 直接调用通用put方法，处理str或bytes
        return await self.put(key, content)

    async def get_file_content(self, key: str) -> Optional[Union[str, bytes]]:
        """获取文件内容"""
        try:
            session = await self.get_session()
            url = f"{self.base_url}/values/{key}"
            async with session.get(url, headers=self.headers) as response:
                if response.status == 200:
                    # 获取原始内容
                    content = await response.read()

                    # 尝试解码为UTF-8字符串
                    try:
                        return content.decode('utf-8')
                    except UnicodeDecodeError:
                        # 如果解码失败，返回原始bytes
                        return content
                elif response.status == 404:
                    logger.warning(f"File content not found for key: {key}")
                    return None
                logger.error(f"Failed to get file content for {key}: {await response.text()}")
                return None
        except Exception as e:
            logger.error(f"Error getting file content for {key}: {e}")
            return None

    async def get(self, key: str) -> Optional[Any]:
        """获取键值对 (通用方法)"""
        try:
            session = await self.get_session()
            url = f"{self.base_url}/values/{key}"
            async with session.get(url, headers=self.headers) as response:
                if response.status == 200:
                    # 尝试解析JSON，如果失败则返回文本
                    content_type = response.headers.get('Content-Type', '')
                    if 'application/json' in content_type:
                        return await response.json()
                    else:
                        return await response.text()
                elif response.status == 404:
                    return None
                logger.error(f"Failed to get value for {key}: {await response.text()}")
                return None
        except Exception as e:
            logger.error(f"Error getting value {key}: {e}")
            return None

    async def delete(self, key: str) -> bool:
        """删除键值对 (通用方法)"""
        try:
            session = await self.get_session()
            url = f"{self.base_url}/values/{key}"
            async with session.delete(url, headers=self.headers) as response:
                if response.status == 200:
                    return True
                logger.error(f"Failed to delete value {key}: {await response.text()}")
                return False
        except Exception as e:
            logger.error(f"Error deleting value {key}: {e}")
            return False

    async def delete_file_content(self, key: str) -> bool:
        """删除文件内容"""
        return await self.delete(key)

    async def put_backup(self, backup_id: str, backup_data: str) -> bool:
        """
        存储备份数据
        备份数据通常是JSON字符串，直接使用put通用方法
        """
        key = f"backup_{backup_id}"
        return await self.put(key, backup_data)

    async def get_backup(self, backup_id: str) -> Optional[str]:
        """
        获取备份数据
        备份数据通常是JSON字符串，直接使用get通用方法
        """
        key = f"backup_{backup_id}"
        return await self.get(key)

    async def delete_backup(self, backup_id: str) -> bool:
        """
        删除备份数据
        """
        key = f"backup_{backup_id}"
        return await self.delete(key)

    async def list_backups(self) -> List[str]:
        """
        列出所有备份
        利用list_keys并过滤前缀
        """
        keys_info = await self.list_keys(prefix="backup_")
        if keys_info:
            return [key_obj['name'] for key_obj in keys_info if 'name' in key_obj]
        return []

    async def put_value(self, key: str, value: Any) -> bool:
        """存储键值对 (通用方法别名，兼容旧代码)"""
        return await self.put(key, value)

    async def get_value(self, key: str) -> Optional[Any]:
        """获取键值对 (通用方法别名，兼容旧代码)"""
        return await self.get(key)

    async def delete_value(self, key: str) -> bool:
        """删除键值对 (通用方法别名，兼容旧代码)"""
        return await self.delete(key)

    async def list_keys(self, prefix: str = "") -> Optional[list]:
        """
        列出所有键 (Cloudflare KV API)
        """
        try:
            session = await self.get_session()
            url = f"{self.base_url}/keys"
            params = {"prefix": prefix} if prefix else {}
            async with session.get(url, headers=self.headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("result", [])
                logger.error(f"Failed to list keys: {await response.text()}")
                return None
        except Exception as e:
            logger.error(f"Error listing keys: {e}")
            return None 