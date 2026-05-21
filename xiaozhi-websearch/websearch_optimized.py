# 优化版网络搜索服务 - 高性能MCP实现
from mcp.server.fastmcp import FastMCP
import sys
import logging
import json
import requests
from datetime import datetime, timedelta
import traceback
from bs4 import BeautifulSoup
import asyncio
import aiohttp
import time
from typing import Any, Dict, List, Optional, Union
from urllib.parse import quote
import base64
from concurrent.futures import ThreadPoolExecutor
import threading
from functools import wraps, lru_cache
import hashlib
import re
import os
from pathlib import Path
import uuid

try:
    from dotenv import load_dotenv
    load_dotenv()
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except Exception:
    pass

# 可选：Redis 二级缓存（跨重启保持）
try:
    import redis  # type: ignore
except Exception:
    redis = None  # type: ignore

_redis_cache_client = None
_redis_cache_config_key = None
_redis_cache_lock = threading.Lock()


def _get_redis_cache_client():
    """按环境变量获取可用的 Redis 客户端（可禁用）。"""
    global _redis_cache_client, _redis_cache_config_key
    # 允许通过 WEBSEARCH_REDIS_CACHE_DISABLE 关闭
    disabled = os.getenv("WEBSEARCH_REDIS_CACHE_DISABLE", "").lower() in ("1", "true", "yes", "on")
    if disabled or redis is None:
        return None
    try:
        host = os.getenv("MCP_REDIS_HOST", "localhost")
        port = int(os.getenv("MCP_REDIS_PORT", "6380"))
        db = int(os.getenv("MCP_REDIS_DB", "1"))
        password = os.getenv("MCP_REDIS_PASSWORD")
        config_key = (host, port, db, password)
        with _redis_cache_lock:
            if _redis_cache_client is not None and _redis_cache_config_key == config_key:
                return _redis_cache_client
            client = redis.Redis(
                host=host, port=port, db=db, password=password,
                decode_responses=True, socket_timeout=3, socket_connect_timeout=3,
                health_check_interval=30
            )
            client.ping()
            _redis_cache_client = client
            _redis_cache_config_key = config_key
            return client
    except Exception:
        with _redis_cache_lock:
            _redis_cache_client = None
            _redis_cache_config_key = None
        return None


def _get_websearch_cache_ttl(default_ttl: int) -> int:
    try:
        return int(os.getenv("WEBSEARCH_CACHE_TTL", str(default_ttl)))
    except Exception:
        return default_ttl


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _get_notepad_bridge_timeout(requested: Optional[int] = None, default: int = 8) -> int:
    """Return a short, bounded Redis wait to keep voice calls responsive."""
    try:
        value = requested if requested and int(requested) > 0 else os.getenv("WEBSEARCH_NOTEPAD_TIMEOUT_SECONDS", default)
        return max(1, min(int(value), 30))
    except Exception:
        return default


# 性能监控
import psutil
import gc

# 配置UTF-8编码
if sys.platform == 'win32':
    sys.stderr.reconfigure(encoding='utf-8')
    sys.stdout.reconfigure(encoding='utf-8')

# 配置日志（支持环境变量指定日志文件，默认仅输出到stderr）
log_handlers = [logging.StreamHandler(sys.stderr)]
log_file = os.getenv('WEBSEARCH_LOG_FILE')
if log_file:
    try:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        log_handlers.insert(0, logging.FileHandler(log_file, encoding='utf-8'))
    except OSError as exc:
        sys.stderr.write(f"[websearch] Unable to open log file {log_file}: {exc}\n")

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=log_handlers
)

logger = logging.getLogger('websearch_optimized')

# 性能配置
class PerformanceConfig:
    MAX_CONCURRENT_REQUESTS = 10
    REQUEST_TIMEOUT = 30
    MAX_RETRY_ATTEMPTS = 3
    CACHE_TTL = 3600  # 1小时缓存
    MAX_MEMORY_USAGE_MB = int(os.getenv("WEBSEARCH_MAX_MEMORY", "256"))
    MAX_CONTENT_SIZE = int(os.getenv("WEBSEARCH_MAX_CONTENT_MB", "5")) * 1024 * 1024
    CONNECTION_POOL_SIZE = 20
    MAX_RESPONSE_SIZE = 8000
    CHUNK_SIZE = 8192

# 增强的会话管理器
class SessionManager:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.session = requests.Session()
            
            # 高级连接池配置
            from urllib3.util.retry import Retry
            retry_strategy = Retry(
                total=PerformanceConfig.MAX_RETRY_ATTEMPTS,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["HEAD", "GET", "OPTIONS"],
                backoff_factor=0.3
            )
            
            adapter = requests.adapters.HTTPAdapter(
                pool_connections=PerformanceConfig.CONNECTION_POOL_SIZE,
                pool_maxsize=PerformanceConfig.CONNECTION_POOL_SIZE,
                max_retries=retry_strategy,
                pool_block=False
            )
            
            self.session.mount('http://', adapter)
            self.session.mount('https://', adapter)
            
            # 优化的请求头
            self.session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            })
            
            # 连接统计
            self.connection_stats = {
                'total_requests': 0,
                'failed_requests': 0,
                'retry_count': 0,
                'avg_response_time': 0.0
            }
            self.stats_lock = threading.Lock()
            self.initialized = True
    
    def get_session(self):
        return self.session
    
    def record_request(self, success: bool, response_time: float, retries: int = 0):
        """记录请求统计"""
        with self.stats_lock:
            self.connection_stats['total_requests'] += 1
            if not success:
                self.connection_stats['failed_requests'] += 1
            self.connection_stats['retry_count'] += retries
            
            # 计算平均响应时间
            current_avg = self.connection_stats['avg_response_time']
            total_requests = self.connection_stats['total_requests']
            new_avg = (current_avg * (total_requests - 1) + response_time) / total_requests
            self.connection_stats['avg_response_time'] = new_avg
    
    def get_connection_stats(self) -> Dict:
        """获取连接统计信息"""
        with self.stats_lock:
            stats = self.connection_stats.copy()
            stats['success_rate'] = 1 - (stats['failed_requests'] / max(stats['total_requests'], 1))
            return stats

# 高级缓存管理器
class CacheManager:
    def __init__(self):
        self.cache = {}
        self.cache_times = {}
        self.cache_sizes = {}  # 跟踪每个缓存项的大小
        self.access_times = {}  # LRU支持
        self.lock = threading.RLock()
        self.max_cache_size = int(os.getenv("WEBSEARCH_CACHE_MAX_MB", "32")) * 1024 * 1024
        self.current_cache_size = 0
        self.hit_count = 0
        self.miss_count = 0
    
    def _generate_key(self, query: str, search_type: str = "general") -> str:
        """生成缓存键（归一化以提升命中率）"""
        try:
            # 1) 基本归一化：小写 + 去多余空白
            q = (query or "").lower().strip()
            q = re.sub(r"\s+", " ", q)
            # 2) 去噪：移除常见无关标点（保留字母数字与空格）
            q = "".join(ch for ch in q if ch.isalnum() or ch.isspace())
            q = re.sub(r"\s+", " ", q).strip()
            st = (search_type or "general").lower().strip()
            content = f"{q}:{st}"
        except Exception:
            # 出错时回退到原逻辑
            content = f"{query}:{search_type}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def _estimate_size(self, data: Dict) -> int:
        """估算数据大小"""
        import sys
        try:
            return sys.getsizeof(json.dumps(data, ensure_ascii=False))
        except:
            return len(str(data)) * 2  # 简单估算
    
    def _evict_lru(self, needed_space: int):
        """基于LRU策略驱逐缓存"""
        if not self.access_times:
            return
        
        # 按访问时间排序，最久未访问的在前
        sorted_keys = sorted(self.access_times.keys(), key=lambda k: self.access_times[k])
        
        freed_space = 0
        for key in sorted_keys:
            if freed_space >= needed_space:
                break
                
            item_size = self.cache_sizes.get(key, 0)
            self.cache.pop(key, None)
            self.cache_times.pop(key, None)
            self.cache_sizes.pop(key, None)
            self.access_times.pop(key, None)
            
            freed_space += item_size
            self.current_cache_size -= item_size
            
        logger.info(f"LRU eviction freed {freed_space} bytes")
    
    def get(self, query: str, search_type: str = "general") -> Optional[Dict]:
        """获取缓存（先查本地，再查 Redis 二级缓存）"""
        key = self._generate_key(query, search_type)
        with self.lock:
            if key in self.cache:
                cache_time = self.cache_times.get(key, 0)
                if time.time() - cache_time < PerformanceConfig.CACHE_TTL:
                    # 更新访问时间
                    self.access_times[key] = time.time()
                    self.hit_count += 1
                    logger.debug(f"Cache hit for query: {query[:50]}... (memory)")
                    return self.cache[key].copy()
                else:
                    self._remove_cache_item(key)

        # 本地 miss，尝试 Redis 二级缓存
        r = _get_redis_cache_client()
        if r is not None:
            try:
                rkey = f"ws:{key}"
                val = r.get(rkey)
                if val:
                    try:
                        data = json.loads(val)
                        with self.lock:
                            # 回灌一份到本地缓存以便后续快速命中
                            self.cache[key] = data.copy()
                            self.cache_times[key] = time.time()
                            self.cache_sizes[key] = self._estimate_size(data)
                            self.access_times[key] = time.time()
                            self.current_cache_size += self.cache_sizes[key]
                            self.hit_count += 1
                        logger.debug(f"Cache hit for query: {query[:50]}... (redis)")
                        return data
                    except Exception:
                        pass
            except Exception:
                pass

        with self.lock:
            self.miss_count += 1
        return None
    
    def _remove_cache_item(self, key: str):
        """移除单个缓存项"""
        item_size = self.cache_sizes.get(key, 0)
        self.cache.pop(key, None)
        self.cache_times.pop(key, None)
        self.cache_sizes.pop(key, None)
        self.access_times.pop(key, None)
        self.current_cache_size -= item_size
    
    def set(self, query: str, result: Dict, search_type: str = "general"):
        """设置缓存（内存 + 可选 Redis 二级缓存）"""
        key = self._generate_key(query, search_type)

        # 估算数据大小
        result_size = self._estimate_size(result)

        # 如果单个项目过大，不缓存
        if result_size > self.max_cache_size // 10:  # 不超过总缓存的10%
            logger.warning(f"Item too large for cache: {result_size} bytes")
            return

        with self.lock:
            # 检查是否需要释放空间
            available_space = self.max_cache_size - self.current_cache_size
            if result_size > available_space:
                needed_space = result_size - available_space + (self.max_cache_size // 10)  # 额外释放10%
                self._evict_lru(needed_space)

            # 如果key已存在，先移除旧的
            if key in self.cache:
                self._remove_cache_item(key)

            # 添加新缓存
            self.cache[key] = result.copy()  # 存储副本
            self.cache_times[key] = time.time()
            self.cache_sizes[key] = result_size
            self.access_times[key] = time.time()
            self.current_cache_size += result_size

            logger.debug(f"Cache set for query: {query[:50]}... (size: {result_size} bytes)")

        # 写入 Redis 二级缓存
        r = _get_redis_cache_client()
        if r is not None:
            try:
                ttl = _get_websearch_cache_ttl(PerformanceConfig.CACHE_TTL)
                rkey = f"ws:{key}"
                r.setex(rkey, ttl, json.dumps(result, ensure_ascii=False))
            except Exception:
                pass

        return None




















    
    def clear_expired(self):
        """清理过期缓存"""
        current_time = time.time()
        with self.lock:
            expired_keys = [
                key for key, cache_time in self.cache_times.items()
                if current_time - cache_time >= PerformanceConfig.CACHE_TTL
            ]
            
            freed_size = 0
            for key in expired_keys:
                freed_size += self.cache_sizes.get(key, 0)
                self._remove_cache_item(key)
                
            if expired_keys:
                logger.info(f"Cleared {len(expired_keys)} expired entries, freed {freed_size} bytes")
    
    def get_cache_stats(self) -> Dict:
        """获取缓存统计"""
        with self.lock:
            total_requests = self.hit_count + self.miss_count
            hit_rate = self.hit_count / max(total_requests, 1)
            
            return {
                'cache_size_bytes': self.current_cache_size,
                'cache_size_mb': self.current_cache_size / 1024 / 1024,
                'cached_items': len(self.cache),
                'hit_count': self.hit_count,
                'miss_count': self.miss_count,
                'hit_rate': hit_rate,
                'max_cache_size_mb': self.max_cache_size / 1024 / 1024
            }
    
    def optimize_memory(self):
        """内存优化：强制清理和压缩"""
        with self.lock:
            # 清理过期项
            self.clear_expired()
            
            # 如果仍然使用过多内存，清理最久未访问的50%
            if self.current_cache_size > self.max_cache_size * 0.8:
                target_items = len(self.cache) // 2
                if target_items > 0:
                    sorted_keys = sorted(self.access_times.keys(), key=lambda k: self.access_times[k])
                    for key in sorted_keys[:target_items]:
                        self._remove_cache_item(key)
                    logger.info(f"Memory optimization: removed {target_items} least accessed items")

# 增强的性能监控
class PerformanceMonitor:
    def __init__(self):
        self.start_time = time.time()
        self.request_count = 0
        self.error_count = 0
        self.response_times = []  # 保存最近的响应时间
        self.max_response_times = 1000  # 最多保存1000个响应时间
        self.memory_samples = []  # 内存使用样本
        self.max_memory_samples = 100
        self.lock = threading.Lock()
        
        # 添加定时采样
        self.sample_thread = threading.Thread(target=self._periodic_sampling, daemon=True)
        self.sample_thread.start()
    
    def _periodic_sampling(self):
        """定期采样内存使用"""
        while True:
            try:
                time.sleep(60)  # 每分钟采样一次
                memory_usage = psutil.Process().memory_info().rss / 1024 / 1024
                
                with self.lock:
                    self.memory_samples.append({
                        'timestamp': time.time(),
                        'memory_mb': memory_usage
                    })
                    
                    # 保持样本数量限制
                    if len(self.memory_samples) > self.max_memory_samples:
                        self.memory_samples.pop(0)
                        
                    # 内存预警
                    if memory_usage > PerformanceConfig.MAX_MEMORY_USAGE_MB * 0.8:
                        logger.warning(f"High memory usage detected: {memory_usage:.1f}MB")
                        
            except Exception as e:
                logger.error(f"Memory sampling error: {e}")
    
    def record_request(self, response_time: float = None):
        with self.lock:
            self.request_count += 1
            if response_time is not None:
                self.response_times.append(response_time)
                # 保持响应时间样本数量限制
                if len(self.response_times) > self.max_response_times:
                    self.response_times.pop(0)
    
    def record_error(self):
        with self.lock:
            self.error_count += 1
    
    def get_stats(self) -> Dict:
        current_time = time.time()
        uptime = current_time - self.start_time
        current_memory = psutil.Process().memory_info().rss / 1024 / 1024
        
        with self.lock:
            # 计算响应时间统计
            response_stats = {}
            if self.response_times:
                import statistics
                response_stats = {
                    'avg_response_time': statistics.mean(self.response_times),
                    'median_response_time': statistics.median(self.response_times),
                    'min_response_time': min(self.response_times),
                    'max_response_time': max(self.response_times),
                    'p95_response_time': statistics.quantiles(self.response_times, n=20)[18] if len(self.response_times) >= 20 else max(self.response_times)
                }
            
            # 内存趋势分析
            memory_trend = "stable"
            if len(self.memory_samples) >= 3:
                recent_samples = self.memory_samples[-3:]
                if all(recent_samples[i]['memory_mb'] > recent_samples[i-1]['memory_mb'] for i in range(1, len(recent_samples))):
                    memory_trend = "increasing"
                elif all(recent_samples[i]['memory_mb'] < recent_samples[i-1]['memory_mb'] for i in range(1, len(recent_samples))):
                    memory_trend = "decreasing"
            
            return {
                "uptime_seconds": uptime,
                "total_requests": self.request_count,
                "total_errors": self.error_count,
                "error_rate": self.error_count / max(self.request_count, 1),
                "current_memory_mb": current_memory,
                "memory_trend": memory_trend,
                "requests_per_second": self.request_count / max(uptime, 1),
                **response_stats
            }
    
    def check_memory_limit(self) -> bool:
        """检查内存使用是否超限"""
        try:
            memory_usage = psutil.Process().memory_info().rss / 1024 / 1024
            if memory_usage > PerformanceConfig.MAX_MEMORY_USAGE_MB:
                logger.warning(f"Memory usage {memory_usage:.1f}MB exceeds limit {PerformanceConfig.MAX_MEMORY_USAGE_MB}MB")
                
                # 尝试内存优化
                cache_manager.optimize_memory()
                gc.collect()
                
                # 再次检查
                new_memory_usage = psutil.Process().memory_info().rss / 1024 / 1024
                logger.info(f"After optimization: {new_memory_usage:.1f}MB (freed: {memory_usage - new_memory_usage:.1f}MB)")
                
                return new_memory_usage <= PerformanceConfig.MAX_MEMORY_USAGE_MB
            return True
        except Exception as e:
            logger.error(f"Memory check failed: {e}")
            return True  # 失败时允许继续
    
    def get_health_status(self) -> Dict:
        """获取服务健康状态"""
        stats = self.get_stats()
        cache_stats = cache_manager.get_cache_stats()
        connection_stats = session_manager.get_connection_stats()
        
        # 健康状态评估
        health_score = 100
        warnings = []
        
        # 错误率检查
        if stats['error_rate'] > 0.1:  # 10%错误率
            health_score -= 30
            warnings.append("High error rate detected")
        
        # 内存使用检查
        if stats['current_memory_mb'] > PerformanceConfig.MAX_MEMORY_USAGE_MB * 0.8:
            health_score -= 20
            warnings.append("High memory usage")
        
        # 响应时间检查
        if 'avg_response_time' in stats and stats['avg_response_time'] > 10:
            health_score -= 20
            warnings.append("Slow response times")
        
        # 缓存命中率检查
        if cache_stats['hit_rate'] < 0.3:  # 命中率低于30%
            health_score -= 10
            warnings.append("Low cache hit rate")
        
        health_status = "healthy"
        if health_score < 70:
            health_status = "degraded"
        if health_score < 50:
            health_status = "unhealthy"
        
        return {
            "status": health_status,
            "score": max(0, health_score),
            "warnings": warnings,
            "stats": stats,
            "cache_stats": cache_stats,
            "connection_stats": connection_stats,
            "timestamp": datetime.now().isoformat()
        }

# 断路器模式实现
class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, reset_timeout: int = 60, recovery_threshold: int = 3):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.recovery_threshold = recovery_threshold
        
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.success_count = 0
        self.lock = threading.Lock()
    
    def call(self, func, *args, **kwargs):
        """执行函数调用，包含断路器逻辑"""
        with self.lock:
            if self.state == "OPEN":
                if time.time() - self.last_failure_time > self.reset_timeout:
                    self.state = "HALF_OPEN"
                    self.success_count = 0
                    logger.info("Circuit breaker transitioning to HALF_OPEN")
                else:
                    raise Exception("Circuit breaker is OPEN")
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise
    
    def _on_success(self):
        """成功回调"""
        with self.lock:
            if self.state == "HALF_OPEN":
                self.success_count += 1
                if self.success_count >= self.recovery_threshold:
                    self.state = "CLOSED"
                    self.failure_count = 0
                    logger.info("Circuit breaker CLOSED - service recovered")
            elif self.state == "CLOSED":
                self.failure_count = 0
    
    def _on_failure(self):
        """失败回调"""
        with self.lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            if self.failure_count >= self.failure_threshold:
                if self.state != "OPEN":
                    self.state = "OPEN"
                    logger.warning(f"Circuit breaker OPEN - too many failures ({self.failure_count})")
    
    def get_state(self) -> Dict:
        """获取断路器状态"""
        with self.lock:
            return {
                "state": self.state,
                "failure_count": self.failure_count,
                "last_failure_time": self.last_failure_time,
                "success_count": self.success_count if self.state == "HALF_OPEN" else 0
            }

# 重试机制装饰器
def enhanced_retry(max_attempts: int = 3, backoff_factor: float = 1.0, exceptions: tuple = (Exception,)):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        wait_time = backoff_factor * (2 ** attempt)
                        logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {wait_time:.1f}s...")
                        time.sleep(wait_time)
                    else:
                        logger.error(f"All {max_attempts} attempts failed. Last error: {e}")
            
            raise last_exception
        return wrapper
    return decorator

# 超时装饰器
def timeout_decorator(timeout_seconds: int = 30):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            import signal
            
            def timeout_handler(signum, frame):
                raise TimeoutError(f"Function {func.__name__} timed out after {timeout_seconds} seconds")
            
            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(timeout_seconds)
            
            try:
                result = func(*args, **kwargs)
                signal.alarm(0)  # 取消定时器
                return result
            except Exception as e:
                signal.alarm(0)  # 确保取消定时器
                raise
            finally:
                signal.signal(signal.SIGALRM, old_handler)
        return wrapper
    return decorator

# 错误分类和处理
class ErrorHandler:
    def __init__(self):
        self.error_counts = {}
        self.error_patterns = {
            'network': ['ConnectionError', 'Timeout', 'ConnectTimeout', 'ReadTimeout'],
            'api_limit': ['429', 'rate limit', 'quota exceeded'],
            'auth': ['401', 'Unauthorized', 'Invalid API key'],
            'server': ['500', '502', '503', '504', 'Internal Server Error'],
            'client': ['400', '404', 'Bad Request', 'Not Found']
        }
        self.recovery_strategies = {
            'network': self._handle_network_error,
            'api_limit': self._handle_rate_limit,
            'auth': self._handle_auth_error,
            'server': self._handle_server_error,
            'client': self._handle_client_error
        }
        self.lock = threading.Lock()
    
    def classify_error(self, error: Exception) -> str:
        """分类错误类型"""
        error_str = str(error).lower()
        error_type = type(error).__name__
        
        for category, patterns in self.error_patterns.items():
            if any(pattern.lower() in error_str or pattern.lower() in error_type.lower() 
                   for pattern in patterns):
                return category
        
        return 'unknown'
    
    def handle_error(self, error: Exception, context: str = "") -> Dict:
        """处理错误并返回恢复建议"""
        error_type = self.classify_error(error)
        
        with self.lock:
            self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1
        
        recovery_func = self.recovery_strategies.get(error_type, self._handle_unknown_error)
        return recovery_func(error, context)
    
    def _handle_network_error(self, error: Exception, context: str) -> Dict:
        """处理网络错误"""
        return {
            "error_type": "network",
            "severity": "medium",
            "retry_recommended": True,
            "wait_time": 2.0,
            "message": "网络连接问题，建议重试",
            "context": context
        }
    
    def _handle_rate_limit(self, error: Exception, context: str) -> Dict:
        """处理速率限制错误"""
        return {
            "error_type": "api_limit",
            "severity": "low",
            "retry_recommended": True,
            "wait_time": 10.0,
            "message": "API调用频率过高，稍后重试",
            "context": context
        }
    
    def _handle_auth_error(self, error: Exception, context: str) -> Dict:
        """处理认证错误"""
        return {
            "error_type": "auth",
            "severity": "high",
            "retry_recommended": False,
            "wait_time": 0,
            "message": "认证失败，请检查API密钥配置",
            "context": context,
            "action_required": "检查配置文件中的API密钥"
        }
    
    def _handle_server_error(self, error: Exception, context: str) -> Dict:
        """处理服务器错误"""
        return {
            "error_type": "server",
            "severity": "medium",
            "retry_recommended": True,
            "wait_time": 5.0,
            "message": "服务器临时错误，建议重试",
            "context": context
        }
    
    def _handle_client_error(self, error: Exception, context: str) -> Dict:
        """处理客户端错误"""
        return {
            "error_type": "client",
            "severity": "high",
            "retry_recommended": False,
            "wait_time": 0,
            "message": "请求格式错误，需要修正参数",
            "context": context
        }
    
    def _handle_unknown_error(self, error: Exception, context: str) -> Dict:
        """处理未知错误"""
        return {
            "error_type": "unknown",
            "severity": "high",
            "retry_recommended": False,
            "wait_time": 1.0,
            "message": f"未知错误: {str(error)}",
            "context": context
        }
    
    def get_error_stats(self) -> Dict:
        """获取错误统计"""
        with self.lock:
            total_errors = sum(self.error_counts.values())
            return {
                "total_errors": total_errors,
                "error_breakdown": self.error_counts.copy(),
                "most_common_error": max(self.error_counts.items(), key=lambda x: x[1])[0] if self.error_counts else None
            }

# 健康检查
class HealthChecker:
    def __init__(self):
        self.checks = {
            'memory': self._check_memory,
            'disk': self._check_disk,
            'api_connectivity': self._check_api_connectivity,
            'cache': self._check_cache
        }
        self.last_check_results = {}
        self.lock = threading.Lock()
    
    def _check_memory(self) -> Dict:
        """检查内存使用"""
        try:
            memory_usage = psutil.Process().memory_info().rss / 1024 / 1024
            max_memory = PerformanceConfig.MAX_MEMORY_USAGE_MB
            
            status = "healthy"
            if memory_usage > max_memory * 0.9:
                status = "critical"
            elif memory_usage > max_memory * 0.7:
                status = "warning"
            
            return {
                "status": status,
                "memory_usage_mb": memory_usage,
                "memory_limit_mb": max_memory,
                "usage_percentage": (memory_usage / max_memory) * 100
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def _check_disk(self) -> Dict:
        """检查磁盘空间"""
        try:
            disk_usage = psutil.disk_usage('/')
            free_percentage = (disk_usage.free / disk_usage.total) * 100
            
            status = "healthy"
            if free_percentage < 5:
                status = "critical"
            elif free_percentage < 15:
                status = "warning"
            
            return {
                "status": status,
                "free_space_gb": disk_usage.free / 1024 / 1024 / 1024,
                "total_space_gb": disk_usage.total / 1024 / 1024 / 1024,
                "free_percentage": free_percentage
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def _check_api_connectivity(self) -> Dict:
        """检查API连接性"""
        try:
            # 简单的连接测试
            import socket
            socket.create_connection(("8.8.8.8", 53), timeout=3)
            return {"status": "healthy", "message": "Internet connectivity OK"}
        except Exception as e:
            return {"status": "error", "message": f"No internet connectivity: {e}"}
    
    def _check_cache(self) -> Dict:
        """检查缓存状态"""
        try:
            cache_stats = cache_manager.get_cache_stats()
            cache_size_mb = cache_stats['cache_size_mb']
            max_cache_mb = cache_stats['max_cache_size_mb']
            
            status = "healthy"
            if cache_size_mb > max_cache_mb * 0.9:
                status = "warning"
            
            return {
                "status": status,
                "cache_usage_mb": cache_size_mb,
                "cache_items": cache_stats['cached_items'],
                "hit_rate": cache_stats['hit_rate']
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def run_health_checks(self) -> Dict:
        """执行所有健康检查"""
        results = {}
        overall_status = "healthy"
        
        for check_name, check_func in self.checks.items():
            try:
                result = check_func()
                results[check_name] = result
                
                if result['status'] == 'critical':
                    overall_status = "critical"
                elif result['status'] in ['warning', 'error'] and overall_status == "healthy":
                    overall_status = "warning"
                    
            except Exception as e:
                results[check_name] = {"status": "error", "message": str(e)}
                if overall_status == "healthy":
                    overall_status = "warning"
        
        with self.lock:
            self.last_check_results = results.copy()
        
        return {
            "overall_status": overall_status,
            "checks": results,
            "timestamp": datetime.now().isoformat()
        }

# 全局实例
session_manager = SessionManager()
cache_manager = CacheManager()
performance_monitor = PerformanceMonitor()
circuit_breaker = CircuitBreaker()
error_handler = ErrorHandler()
health_checker = HealthChecker()

# 创建MCP服务器
mcp = FastMCP("websearch_optimized")

# 紧凑工具描述以减小握手负载（不减少工具数量）
_DOC_MAX = int(os.getenv("MCP_TOOL_DOC_MAX_CHARS", "280"))

def _compact_doc(doc: str) -> str:
    try:
        s = " ".join((doc or "").split())
        if _DOC_MAX > 0 and len(s) > _DOC_MAX:
            return s[:_DOC_MAX-3] + "..."
        return s
    except Exception:
        return doc or ""

_original_tool = mcp.tool

def _compact_tool_decorator(*dargs, **dkwargs):
    # 兼容 @mcp.tool 和 @mcp.tool(...)
    if dargs and callable(dargs[0]) and len(dargs) == 1 and not dkwargs:
        func = dargs[0]
        try:
            func.__doc__ = _compact_doc(func.__doc__)
        except Exception:
            pass
        return _original_tool()(func)
    def _decorator(func):
        try:
            func.__doc__ = _compact_doc(func.__doc__)
        except Exception:
            pass
        return _original_tool(*dargs, **dkwargs)(func)
    return _decorator

mcp.tool = _compact_tool_decorator

@mcp.tool()
def ping_notepad_via_redis(timeout_seconds: int = 8) -> dict:
    """
    Ping Notepad via Redis - Check cross-MCP connectivity
    通过Redis Ping记事本服务 - 检查跨MCP连通性

    Sends a `test_connection` request to notepad service via Redis and
    waits for response up to timeout_seconds.
    """
    try:
        r = _get_redis_connection()
        if not r:
            return {"success": False, "error": "Redis连接失败"}

        request_id = str(uuid.uuid4())
        request = {
            "id": request_id,
            "action": "test_connection",
            "params": {},
            "timestamp": datetime.now().isoformat(),
            "from_service": "websearch"
        }

        timeout_seconds = _get_notepad_bridge_timeout(timeout_seconds)
        r.lpush("notepad_requests", json.dumps(request, ensure_ascii=False))
        response_key = f"response_{request_id}"
        resp = r.brpop(response_key, timeout=timeout_seconds)
        if not resp:
            return {"success": False, "error": "等待记事本服务响应超时"}

        response = json.loads(resp[1])
        response["via"] = "redis"
        return response
    except Exception as e:
        return {"success": False, "error": str(e)}

# 装饰器：性能监控
def monitor_performance(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        performance_monitor.record_request()
        
        try:
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time
            logger.debug(f"{func.__name__} executed in {execution_time:.3f}s")
            return result
        except Exception as e:
            performance_monitor.record_error()
            execution_time = time.time() - start_time
            logger.error(f"{func.__name__} failed in {execution_time:.3f}s: {e}")
            raise
    return wrapper

# 装饰器：缓存支持
def cached_search(search_type: str = "general"):
    def decorator(func):
        @wraps(func)
        def wrapper(query: str, *args, **kwargs):
            # 尝试从缓存获取
            cached_result = cache_manager.get(query, search_type)
            if cached_result:
                return cached_result
            
            # 执行搜索
            result = func(query, *args, **kwargs)
            
            # 缓存结果（仅当成功时）
            if result.get("success"):
                cache_manager.set(query, result, search_type)
            
            return result
        return wrapper
    return decorator

# 装饰器：内存检查
def check_memory(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not performance_monitor.check_memory_limit():
            return {
                "success": False,
                "error": "Memory usage exceeds limit, operation cancelled"
            }
        return func(*args, **kwargs)
    return wrapper

# 统一配置管理
class EnhancedConfig:
    """增强的配置管理类"""
    
    def __init__(self):
        # 性能配置
        self.MAX_CONCURRENT_REQUESTS = 10
        self.REQUEST_TIMEOUT = 30
        self.MAX_RETRY_ATTEMPTS = 3
        self.CACHE_TTL = 3600
        self.MAX_MEMORY_USAGE_MB = 512
        self.MAX_CONTENT_SIZE = 10 * 1024 * 1024
        self.CONNECTION_POOL_SIZE = 20
        self.MAX_RESPONSE_SIZE = 8000
        self.CHUNK_SIZE = 8192
        
        # 缓存配置
        self.MAX_CACHE_SIZE_MB = 100
        self.CACHE_CLEANUP_INTERVAL = 3600
        
        # 断路器配置
        self.CIRCUIT_BREAKER_FAILURE_THRESHOLD = 5
        self.CIRCUIT_BREAKER_RESET_TIMEOUT = 60
        self.CIRCUIT_BREAKER_RECOVERY_THRESHOLD = 3
        
        # 健康检查配置
        self.HEALTH_CHECK_INTERVAL = 300
        self.MEMORY_WARNING_THRESHOLD = 0.8
        self.MEMORY_CRITICAL_THRESHOLD = 0.9
        
        # API配置
        self.ZHIPU_API_KEY = ""
        
    def update_from_dict(self, config_dict: Dict):
        """从字典更新配置"""
        for key, value in config_dict.items():
            if hasattr(self, key):
                setattr(self, key, value)

# 配置管理
def load_enhanced_config() -> Dict:
    """加载增强配置"""
    try:
        # 首先尝试加载原有配置
        from config_manager import load_config
        base_config = load_config()
        
        # 创建增强配置实例
        enhanced_config = EnhancedConfig()
        
        # 从环境变量加载配置
        import os
        env_configs = {
            'ZHIPU_API_KEY': os.getenv('ZHIPU_API_KEY', base_config.get('ZHIPU_API_KEY', '')),
            'MAX_MEMORY_USAGE_MB': int(os.getenv('WEBSEARCH_MAX_MEMORY', enhanced_config.MAX_MEMORY_USAGE_MB)),
            'REQUEST_TIMEOUT': int(os.getenv('WEBSEARCH_TIMEOUT', enhanced_config.REQUEST_TIMEOUT)),
            'CACHE_TTL': int(os.getenv('WEBSEARCH_CACHE_TTL', enhanced_config.CACHE_TTL)),
        }
        
        # 更新配置
        enhanced_config.update_from_dict(env_configs)
        
        # 验证必需的配置项
        if not enhanced_config.ZHIPU_API_KEY:
            logger.error("Missing required config: ZHIPU_API_KEY")
            raise ValueError("Missing required config: ZHIPU_API_KEY")
        
        # 返回配置字典
        return {
            'ZHIPU_API_KEY': enhanced_config.ZHIPU_API_KEY,
            'performance': {
                'MAX_CONCURRENT_REQUESTS': enhanced_config.MAX_CONCURRENT_REQUESTS,
                'REQUEST_TIMEOUT': enhanced_config.REQUEST_TIMEOUT,
                'MAX_RETRY_ATTEMPTS': enhanced_config.MAX_RETRY_ATTEMPTS,
                'CACHE_TTL': enhanced_config.CACHE_TTL,
                'MAX_MEMORY_USAGE_MB': enhanced_config.MAX_MEMORY_USAGE_MB,
                'MAX_CONTENT_SIZE': enhanced_config.MAX_CONTENT_SIZE,
                'CONNECTION_POOL_SIZE': enhanced_config.CONNECTION_POOL_SIZE,
                'MAX_RESPONSE_SIZE': enhanced_config.MAX_RESPONSE_SIZE,
                'CHUNK_SIZE': enhanced_config.CHUNK_SIZE,
            },
            'cache': {
                'MAX_CACHE_SIZE_MB': enhanced_config.MAX_CACHE_SIZE_MB,
                'CACHE_CLEANUP_INTERVAL': enhanced_config.CACHE_CLEANUP_INTERVAL,
            },
            'circuit_breaker': {
                'FAILURE_THRESHOLD': enhanced_config.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
                'RESET_TIMEOUT': enhanced_config.CIRCUIT_BREAKER_RESET_TIMEOUT,
                'RECOVERY_THRESHOLD': enhanced_config.CIRCUIT_BREAKER_RECOVERY_THRESHOLD,
            },
            'health': {
                'CHECK_INTERVAL': enhanced_config.HEALTH_CHECK_INTERVAL,
                'MEMORY_WARNING_THRESHOLD': enhanced_config.MEMORY_WARNING_THRESHOLD,
                'MEMORY_CRITICAL_THRESHOLD': enhanced_config.MEMORY_CRITICAL_THRESHOLD,
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to load enhanced config: {e}")
        raise

# 添加配置管理工具
@mcp.tool()
def get_configuration_info() -> dict:
    """
    Get Configuration Information - Retrieve current service configuration details
    获取配置信息 - 获取当前服务的配置信息
    
    Use this tool when you need to:
    - Check current service settings and parameters
    - Verify API configuration status
    - Review performance and cache settings
    - Debug configuration issues
    
    Returns detailed configuration information including performance parameters and cache settings.
    Sensitive information like API keys are automatically masked for security.
    """
    try:
        config = load_enhanced_config()
        
        # 隐藏敏感信息
        safe_config = config.copy()
        if 'ZHIPU_API_KEY' in safe_config:
            api_key = safe_config['ZHIPU_API_KEY']
            safe_config['ZHIPU_API_KEY'] = f"{api_key[:8]}..." if len(api_key) > 8 else "***"
        
        return {
            "success": True,
            "configuration": safe_config,
            "config_source": "enhanced_config_manager",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"获取配置信息失败: {e}")
        return {"success": False, "error": str(e)}

@mcp.tool()
def update_configuration_parameter(parameter_name: str, parameter_value: str) -> dict:
    """
    Update Configuration Parameter - Dynamically update service configuration parameters
    更新配置参数 - 动态更新服务配置参数
    
    Use this tool when you need to:
    - Adjust service performance parameters in real-time
    - Modify timeout, memory limits, or cache settings
    - Tune concurrent request limits
    - Update circuit breaker thresholds
    
    Supported parameters: REQUEST_TIMEOUT, MAX_MEMORY_USAGE_MB, CACHE_TTL, 
    MAX_CONCURRENT_REQUESTS, MAX_RESPONSE_SIZE, CIRCUIT_BREAKER_FAILURE_THRESHOLD, 
    CIRCUIT_BREAKER_RESET_TIMEOUT
    
    :param parameter_name: Name of the parameter to update
    :param parameter_value: New value for the parameter
    :return: Update result with old and new values
    """
    try:
        # 支持更新的参数列表
        updatable_params = {
            'REQUEST_TIMEOUT': int,
            'MAX_MEMORY_USAGE_MB': int, 
            'CACHE_TTL': int,
            'MAX_CONCURRENT_REQUESTS': int,
            'MAX_RESPONSE_SIZE': int,
            'CIRCUIT_BREAKER_FAILURE_THRESHOLD': int,
            'CIRCUIT_BREAKER_RESET_TIMEOUT': int,
        }
        
        if parameter_name not in updatable_params:
            return {
                "success": False,
                "error": f"Parameter '{parameter_name}' is not updatable",
                "available_parameters": list(updatable_params.keys())
            }
        
        # 类型转换
        param_type = updatable_params[parameter_name]
        try:
            converted_value = param_type(parameter_value)
        except ValueError:
            return {
                "success": False,
                "error": f"Invalid value type for {parameter_name}, expected {param_type.__name__}"
            }
        
        # 更新全局配置对象
        if parameter_name in ['REQUEST_TIMEOUT', 'MAX_RETRY_ATTEMPTS']:
            setattr(PerformanceConfig, parameter_name, converted_value)
        elif parameter_name == 'MAX_MEMORY_USAGE_MB':
            PerformanceConfig.MAX_MEMORY_USAGE_MB = converted_value
        elif parameter_name == 'CACHE_TTL':
            PerformanceConfig.CACHE_TTL = converted_value
        elif parameter_name == 'MAX_CONCURRENT_REQUESTS':
            PerformanceConfig.MAX_CONCURRENT_REQUESTS = converted_value
        elif parameter_name == 'MAX_RESPONSE_SIZE':
            PerformanceConfig.MAX_RESPONSE_SIZE = converted_value
        elif parameter_name == 'CIRCUIT_BREAKER_FAILURE_THRESHOLD':
            circuit_breaker.failure_threshold = converted_value
        elif parameter_name == 'CIRCUIT_BREAKER_RESET_TIMEOUT':
            circuit_breaker.reset_timeout = converted_value
        
        logger.info(f"Configuration updated: {parameter_name} = {converted_value}")
        
        return {
            "success": True,
            "message": f"Parameter {parameter_name} updated to {converted_value}",
            "parameter": parameter_name,
            "old_value": "unknown",
            "new_value": converted_value,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        error_msg = f"配置更新失败: {str(e)}"
        logger.error(error_msg)
        return {"success": False, "error": error_msg}

# 优化的搜索结果处理
def optimize_search_content(content_list: List[str], max_size: int = None) -> List[str]:
    """优化搜索结果内容"""
    if not content_list:
        return content_list
    
    max_size = max_size or PerformanceConfig.MAX_RESPONSE_SIZE
    total_size = sum(len(content) for content in content_list)
    
    if total_size <= max_size:
        return content_list
    
    # 智能压缩：保留重要信息
    reduction_ratio = max_size / total_size
    optimized_list = []
    
    for content in content_list:
        if not content.strip():
            continue
            
        target_length = max(int(len(content) * reduction_ratio), 100)
        
        if len(content) <= target_length:
            optimized_list.append(content)
        else:
            # 智能截断：优先保留开头和结尾
            half_length = target_length // 2
            if target_length > 200:
                truncated = content[:half_length] + "\n...\n" + content[-half_length:]
            else:
                truncated = content[:target_length-3] + "..."
            optimized_list.append(truncated)
    
    return optimized_list

# 智能搜索路由
@mcp.tool()
def intelligent_web_search_assistant(search_query: str) -> dict:
    """
    Intelligent Web Search Assistant - Optimized version with advanced performance features
    智能联网搜索助手 - 优化版
    
    **Use this tool when:**
    - User asks about information beyond AI training data (after 2024)
    - User needs real-time information: weather, stock prices, exchange rates, traffic
    - User asks for latest news, policies, or technology developments
    - User needs current status of specific topics, people, or companies
    - AI knowledge base lacks relevant information or may be outdated
    - User explicitly requests to search or query latest information
    
    **Performance Features:**
    - Smart caching mechanism (1-hour cache for identical queries)
    - Connection pool reuse for improved network efficiency
    - Memory usage monitoring to prevent overflow
    - Concurrent request limiting for system stability
    - Intelligent result compression to avoid oversized responses
    
    **Auto-trigger Examples:**
    - "What's the weather today?"
    - "Latest AI technology developments"
    - "What happened in 2024?"
    - "Current Bitcoin price"
    - "What time is it now?"
    
    :param search_query: User's original search query
    :return: Intelligent search results with automatic routing
    """
    try:
        logger.info(f"Processing intelligent search: {search_query[:100]}...")
        
        # 智能路由判断
        query_lower = search_query.lower()
        
        # 定义关键词类别
        categories = {
            'academic': ['论文', '文献', '研究', '学术', 'paper', 'research', 'study'],
            'news': ['新闻', '时事', '头条', '最新消息', '突发', 'news'],
            'tech': ['教程', '文档', '开发', '编程', 'API', 'tutorial', 'documentation'],
            'general': []  # 默认类别
        }
        
        # 确定搜索类型
        search_type = 'general'
        for category, keywords in categories.items():
            if any(keyword in query_lower for keyword in keywords):
                search_type = category
                break
        
        # 根据类型选择搜索策略
        if search_type == 'academic':
            return 学术文献搜索_优化版(search_query)
        elif search_type == 'news':
            return 新闻搜索_优化版(search_query)
        elif search_type == 'tech':
            return 技术文档搜索_优化版(search_query)
        else:
            return 通用搜索_优化版(search_query)
            
    except Exception as e:
        error_msg = f"智能搜索失败: {str(e)}"
        logger.error(f"{error_msg}\n{traceback.format_exc()}")
        return {"success": False, "error": error_msg, "query": search_query}

def _execute_search(query_text: str, search_type: str, max_results: int, query_modifier: str = "", content_length: int = 300) -> dict:
    """统一的搜索执行函数"""
    try:
        logger.info(f"Executing {search_type} search: {query_text[:50]}...")

        # 使用多搜索引擎服务
        from multi_search_engine import multi_search_engine

        # 构建查询
        search_query = f"({query_text}) {query_modifier}".strip()

        search_result = multi_search_engine.search(
            query=search_query,
            search_type=search_type,
            max_results=max_results
        )

        if not search_result.get('success'):
            return {
                "success": False,
                "error": search_result.get('error', '搜索失败'),
                "query": query_text,
                "available_engines": search_result.get('available_engines', [])
            }

        # 优化结果处理
        optimized_content = []
        results = search_result.get('results', [])
        sources = []

        for i, item in enumerate(results, 1):
            title = item.get('title', f'结果 {i}')
            url = item.get('url', '')
            content = item.get('content', '')
            source = item.get('source', '')

            # 内容优化
            if len(content) > content_length:
                content = content[:content_length] + "..."

            result_text = f"**{i}. {title}**\n{content}\n🔗 {url}\n📍 来源: {source}"
            optimized_content.append(result_text)

            sources.append({
                "title": title,
                "url": url,
                "source": source
            })

        search_engine = search_result.get('search_engine', '未知')
        final_content = f"关于'{query_text}'的搜索结果（使用{search_engine}搜索引擎）：\n\n" + "\n\n".join(optimized_content)

        logger.info(f"{search_type.capitalize()} search completed: {len(optimized_content)} results using {search_engine}")

        return {
            "success": True,
            "content": final_content,
            "sources": sources,
            "query": query_text,
            "type": f"{search_type}_search",
            "search_engine": search_engine,
            "cached": False
        }

    except Exception as e:
        error_msg = f"{search_type.capitalize()} search failed: {str(e)}"
        logger.error(error_msg)
        return {"success": False, "error": error_msg, "query": query_text}

@monitor_performance
@cached_search("general")
@check_memory
def 通用搜索_优化版(query_text: str) -> dict:
    """优化版通用搜索"""
    return _execute_search(query_text, "general", 6)

@monitor_performance
@cached_search("news")
@check_memory
def 新闻搜索_优化版(query_text: str) -> dict:
    """优化版新闻搜索 - 支持多搜索引擎自动切换"""
    return _execute_search(query_text, "news", 8, query_modifier="新闻 OR 最新消息", content_length=400)

@monitor_performance
@cached_search("academic")
@check_memory
def 学术文献搜索_优化版(query_text: str) -> dict:
    """优化版学术文献搜索 - 支持多搜索引擎自动切换"""
    return _execute_search(query_text, "academic", 6, query_modifier="论文 OR paper OR research OR study", content_length=600)

@monitor_performance
@cached_search("tech")
@check_memory
def 技术文档搜索_优化版(query_text: str) -> dict:
    """优化版技术文档搜索 - 支持多搜索引擎自动切换"""
    return _execute_search(query_text, "tech", 6, query_modifier="tutorial OR documentation OR guide OR API OR code", content_length=500)

# 文件下载优化
@monitor_performance
@check_memory
def download_file_optimized(url: str, filename: str = None) -> dict:
    """优化的文件下载功能"""
    try:
        logger.info(f"Starting optimized file download: {url}")
        
        session = session_manager.get_session()
        
        # 首先检查文件大小
        head_response = session.head(url, timeout=10)
        content_length = head_response.headers.get('content-length')
        
        if content_length:
            file_size = int(content_length)
            if file_size > PerformanceConfig.MAX_CONTENT_SIZE:
                return {
                    "success": False,
                    "error": f"File too large: {file_size} bytes (max: {PerformanceConfig.MAX_CONTENT_SIZE})"
                }
        
        # 流式下载
        response = session.get(url, timeout=30, stream=True)
        response.raise_for_status()
        
        # 获取文件名
        if not filename:
            from urllib.parse import urlparse
            parsed_url = urlparse(url)
            filename = parsed_url.path.split('/')[-1] or f"download_{int(time.time())}"
        
        # 流式读取内容
        content_chunks = []
        total_size = 0
        
        for chunk in response.iter_content(chunk_size=PerformanceConfig.CHUNK_SIZE):
            if chunk:
                content_chunks.append(chunk)
                total_size += len(chunk)
                
                # 检查大小限制
                if total_size > PerformanceConfig.MAX_CONTENT_SIZE:
                    return {
                        "success": False,
                        "error": f"File too large during download: {total_size} bytes"
                    }
        
        file_content = b''.join(content_chunks)
        content_type = response.headers.get('content-type', 'application/octet-stream')
        
        # 编码为base64
        encoded_content = base64.b64encode(file_content).decode('utf-8')
        
        logger.info(f"File download completed: {filename}, size: {total_size} bytes")
        
        return {
            "success": True,
            "filename": filename,
            "content": encoded_content,
            "content_type": content_type,
            "size": total_size
        }
        
    except Exception as e:
        error_msg = f"文件下载失败: {str(e)}"
        logger.error(error_msg)
        return {"success": False, "error": error_msg}

# 性能监控工具
@mcp.tool()
def get_performance_statistics() -> dict:
    """
    Get Performance Statistics - Retrieve detailed service performance metrics
    获取性能统计 - 获取详细的服务性能统计信息
    
    Use this tool when you need to:
    - Monitor service performance and health
    - Analyze request patterns and response times
    - Check memory usage trends and optimization opportunities
    - Review cache hit rates and effectiveness
    - Monitor network connection statistics
    - Check circuit breaker status and error rates
    
    Returns comprehensive statistics including:
    - Basic performance metrics: request count, error rate, response time
    - Memory usage patterns and trends
    - Cache hit rate and usage statistics
    - Network connection statistics
    - Circuit breaker status and failure patterns
    """
    try:
        # 基础统计
        basic_stats = performance_monitor.get_stats()
        
        # 缓存统计
        cache_stats = cache_manager.get_cache_stats()
        
        # 连接统计
        connection_stats = session_manager.get_connection_stats()
        
        # 断路器状态
        circuit_breaker_stats = circuit_breaker.get_state()
        
        # 错误统计
        error_stats = error_handler.get_error_stats()
        
        # 综合统计
        comprehensive_stats = {
            "service_info": {
                "name": "websearch_optimized",
                "version": "2.0",
                "timestamp": datetime.now().isoformat()
            },
            "performance": basic_stats,
            "cache": cache_stats,
            "connections": connection_stats,
            "circuit_breaker": circuit_breaker_stats,
            "errors": error_stats
        }
        
        return {
            "success": True,
            "statistics": comprehensive_stats
        }
        
    except Exception as e:
        logger.error(f"获取性能统计失败: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_search_runtime_stats() -> dict:
    """Quick runtime snapshot for search service (requests, cache, connections, circuit breaker)."""
    try:
        runtime = {
            "timestamp": datetime.now().isoformat(),
            "requests": performance_monitor.get_stats(),
            "cache": cache_manager.get_cache_stats(),
            "connections": session_manager.get_connection_stats(),
            "circuit_breaker": circuit_breaker.get_state(),
        }
        return {"success": True, "runtime": runtime}
    except Exception as exc:
        logger.error("获取运行时统计失败: %s", exc)
        return {"success": False, "error": str(exc)}


@mcp.tool()
def update_cache_settings(cache_ttl: Optional[int] = None, max_cache_size_mb: Optional[int] = None) -> dict:
    """Update cache TTL or maximum cache size (MB)."""
    if cache_ttl is None and max_cache_size_mb is None:
        return {"success": False, "error": "至少提供 cache_ttl 或 max_cache_size_mb"}

    updates: Dict[str, Any] = {}

    if cache_ttl is not None:
        if cache_ttl <= 0:
            return {"success": False, "error": "cache_ttl 必须为正整数"}
        PerformanceConfig.CACHE_TTL = cache_ttl
        updates["cache_ttl"] = cache_ttl

    if max_cache_size_mb is not None:
        if max_cache_size_mb <= 0:
            return {"success": False, "error": "max_cache_size_mb 必须为正数"}
        max_bytes = int(max_cache_size_mb * 1024 * 1024)
        with cache_manager.lock:
            cache_manager.max_cache_size = max_bytes
            if cache_manager.current_cache_size > max_bytes:
                cache_manager.optimize_memory()
        updates["max_cache_size_mb"] = max_cache_size_mb

    updates["current_cache"] = cache_manager.get_cache_stats()

    return {
        "success": True,
        "message": "缓存配置已更新",
        "updates": updates,
    }


@mcp.tool()
def check_notepad_bridge() -> dict:
    """Check Redis bridge connectivity to notepad service."""
    try:
        redis_conn = _get_redis_connection()
        if not redis_conn:
            return {"success": False, "error": "Redis连接失败或未配置"}

        ping_result = redis_conn.ping()

        try:
            queue_length = redis_conn.llen("notepad_requests")
        except Exception:
            queue_length = None

        pending_responses = 0
        try:
            for _ in redis_conn.scan_iter("response_*", count=100):
                pending_responses += 1
                if pending_responses >= 100:
                    break
        except Exception:
            pending_responses = None

        pool = getattr(redis_conn, "connection_pool", None)
        conn_kwargs = getattr(pool, "connection_kwargs", {}) if pool else {}

        return {
            "success": True,
            "ping": bool(ping_result),
            "queue_length": queue_length,
            "pending_responses_sample": pending_responses,
            "connection": {
                "host": conn_kwargs.get("host"),
                "port": conn_kwargs.get("port"),
                "db": conn_kwargs.get("db"),
            },
        }
    except Exception as exc:
        logger.error("检查记事本桥接失败: %s", exc)
        return {"success": False, "error": str(exc)}


@mcp.tool()
def get_health_status() -> dict:
    """
    Get Health Status - Retrieve comprehensive service health check results
    获取健康状态 - 获取服务健康状态检查结果
    
    Use this tool when you need to:
    - Perform routine health checks on the service
    - Diagnose performance issues or system problems
    - Monitor system resource usage and availability
    - Get recommendations for service optimization
    - Check overall service status before critical operations
    
    Health checks include:
    - Memory usage verification and limits
    - Disk space availability check
    - API connectivity and authentication status
    - Cache system status and performance
    - Overall health score and system recommendations
    """
    try:
        health_status = performance_monitor.get_health_status()
        detailed_health = health_checker.run_health_checks()
        
        # 合并健康状态信息
        combined_health = {
            "service_health": health_status,
            "system_health": detailed_health,
            "recommendations": []
        }
        
        # 生成改进建议
        if health_status["score"] < 80:
            for warning in health_status["warnings"]:
                if "memory" in warning.lower():
                    combined_health["recommendations"].append("考虑重启服务或清理缓存以释放内存")
                elif "error" in warning.lower():
                    combined_health["recommendations"].append("检查网络连接和API配置")
                elif "cache" in warning.lower():
                    combined_health["recommendations"].append("优化查询模式以提高缓存命中率")
        
        return {
            "success": True,
            "health_report": combined_health
        }
        
    except Exception as e:
        logger.error(f"获取健康状态失败: {e}")
        return {"success": False, "error": str(e)}

@mcp.tool()
def get_cache_details() -> dict:
    """
    Get Cache Details - View detailed cache information and performance metrics
    获取缓存详情 - 查看详细的缓存信息和性能指标

    Use this tool when you need to:
    - Analyze cache performance and hit rates
    - Monitor memory usage by cache system
    - Review cached items and their access patterns
    - Optimize cache configuration based on usage patterns
    - Debug cache-related performance issues

    Returns comprehensive cache analytics including:
    - Cache size and memory usage statistics
    - Hit rate and access pattern analysis
    - Individual cache item information
    - Performance recommendations
    """
    try:
        cache_stats = cache_manager.get_cache_stats()

        # 获取详细的缓存项信息
        with cache_manager.lock:
            cache_items = []
            current_time = time.time()

            for key in list(cache_manager.cache.keys())[:10]:  # 显示前10个缓存项
                cache_time = cache_manager.cache_times.get(key, 0)
                access_time = cache_manager.access_times.get(key, 0)
                size = cache_manager.cache_sizes.get(key, 0)
                age = current_time - cache_time
                last_access = current_time - access_time

                cache_items.append({
                    "key": key[:16] + "..." if len(key) > 16 else key,
                    "age_seconds": round(age, 1),
                    "last_access_seconds": round(last_access, 1),
                    "size_bytes": size,
                    "size_kb": round(size / 1024, 1)
                })

        # 性能分析
        performance_analysis = {
            "efficiency": "excellent" if cache_stats['hit_rate'] > 0.7 else
                         "good" if cache_stats['hit_rate'] > 0.5 else
                         "needs_improvement",
            "memory_usage": "optimal" if cache_stats['cache_size_mb'] < 50 else
                           "moderate" if cache_stats['cache_size_mb'] < 80 else
                           "high",
            "recommendations": []
        }

        if cache_stats['hit_rate'] < 0.5:
            performance_analysis["recommendations"].append("考虑增加缓存TTL或优化查询模式")
        if cache_stats['cache_size_mb'] > 80:
            performance_analysis["recommendations"].append("考虑清理缓存或增加内存限制")
        if cache_stats['cached_items'] > 1000:
            performance_analysis["recommendations"].append("缓存项过多，建议优化缓存策略")

        return {
            "success": True,
            "cache_statistics": cache_stats,
            "cache_items_sample": cache_items,
            "performance_analysis": performance_analysis,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        error_msg = f"获取缓存详情失败: {e}"
        logger.error(error_msg)
        return {"success": False, "error": error_msg}

@mcp.tool()
def clear_cache() -> dict:
    """
    Clear Cache - Manually clean expired cache and perform memory optimization
    清理缓存 - 手动清理过期缓存和执行内存优化
    
    Use this tool when you need to:
    - Free up memory by removing expired cache entries
    - Force garbage collection to optimize memory usage
    - Clear cache when data might be stale or outdated
    - Resolve memory-related performance issues
    - Perform routine maintenance on cache system
    
    Operations performed:
    - Remove expired cache entries
    - Execute LRU (Least Recently Used) cache cleanup
    - Force Python garbage collection
    - Optimize overall memory usage patterns
    """
    try:
        # 记录清理前状态
        before_stats = cache_manager.get_cache_stats()
        before_memory = psutil.Process().memory_info().rss / 1024 / 1024
        
        # 执行清理
        cache_manager.clear_expired()
        cache_manager.optimize_memory()
        gc.collect()  # 强制垃圾回收
        
        # 记录清理后状态
        after_stats = cache_manager.get_cache_stats()
        after_memory = psutil.Process().memory_info().rss / 1024 / 1024
        
        freed_cache = before_stats['cache_size_mb'] - after_stats['cache_size_mb']
        freed_memory = before_memory - after_memory
        
        logger.info(f"Cache cleanup completed: freed {freed_cache:.1f}MB cache, {freed_memory:.1f}MB memory")
        
        return {
            "success": True,
            "message": "缓存清理完成",
            "cleanup_results": {
                "cache_freed_mb": freed_cache,
                "memory_freed_mb": freed_memory,
                "items_before": before_stats['cached_items'],
                "items_after": after_stats['cached_items'],
                "items_removed": before_stats['cached_items'] - after_stats['cached_items']
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        error_msg = f"缓存清理失败: {e}"
        logger.error(error_msg)
        return {"success": False, "error": error_msg}

@mcp.tool()
def get_error_analysis() -> dict:
    """
    Get Error Analysis - Retrieve detailed error analysis report
    获取错误分析 - 获取详细的错误分析报告
    
    Use this tool when you need to:
    - Analyze error patterns and trends
    - Identify the most common types of failures
    - Get recommendations for error resolution
    - Monitor circuit breaker status and failure rates
    - Troubleshoot service reliability issues
    
    Analysis includes:
    - Error type distribution and frequency
    - Error trend analysis over time
    - Recovery recommendations based on error patterns
    - Circuit breaker status and configuration
    - Specific suggestions for common error types (network, API limits, authentication)
    """
    try:
        error_stats = error_handler.get_error_stats()
        circuit_stats = circuit_breaker.get_state()
        
        # 生成错误分析
        analysis = {
            "error_summary": error_stats,
            "circuit_breaker_status": circuit_stats,
            "analysis": {
                "most_frequent_error": error_stats.get('most_common_error', 'None'),
                "total_error_count": error_stats.get('total_errors', 0),
                "circuit_breaker_active": circuit_stats['state'] != 'CLOSED'
            },
            "recommendations": []
        }
        
        # 生成建议
        if error_stats.get('total_errors', 0) > 10:
            analysis["recommendations"].append("错误数量较高，建议检查网络连接和API配置")
        
        if circuit_stats['state'] == 'OPEN':
            analysis["recommendations"].append("断路器已开启，服务正在保护模式，请检查下游服务")
        elif circuit_stats['state'] == 'HALF_OPEN':
            analysis["recommendations"].append("断路器在半开状态，正在尝试恢复")
        
        most_common = error_stats.get('most_common_error')
        if most_common == 'network':
            analysis["recommendations"].append("网络错误频发，检查网络连接稳定性")
        elif most_common == 'api_limit':
            analysis["recommendations"].append("API限流错误，考虑降低请求频率")
        elif most_common == 'auth':
            analysis["recommendations"].append("认证错误，检查API密钥配置")
        
        return {
            "success": True,
            "error_analysis": analysis,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"错误分析失败: {e}")
        return {"success": False, "error": str(e)}

@mcp.tool()
def reset_circuit_breaker() -> dict:
    """
    Reset Circuit Breaker - Manually reset circuit breaker status
    重置断路器 - 手动重置断路器状态
    
    Use this tool when you need to:
    - Reset circuit breaker after confirming downstream service recovery
    - Force circuit breaker to closed state during maintenance
    - Clear accumulated failure counts
    - Resume normal service operation after fixing issues
    - Override circuit breaker protection for testing
    
    This operation should only be performed after confirming that:
    - The underlying service issues have been resolved
    - Downstream services are healthy and responsive
    - The root cause of failures has been addressed
    """
    try:
        old_state = circuit_breaker.get_state()
        
        # 重置断路器
        with circuit_breaker.lock:
            circuit_breaker.state = "CLOSED"
            circuit_breaker.failure_count = 0
            circuit_breaker.success_count = 0
            circuit_breaker.last_failure_time = None
        
        new_state = circuit_breaker.get_state()
        
        logger.info(f"Circuit breaker manually reset from {old_state['state']} to {new_state['state']}")
        
        return {
            "success": True,
            "message": "断路器已重置",
            "old_state": old_state,
            "new_state": new_state,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        error_msg = f"重置断路器失败: {e}"
        logger.error(error_msg)
        return {"success": False, "error": error_msg}

# 集成原有功能的优化版本
@mcp.tool()
@monitor_performance
@check_memory
def search_and_save_to_notepad_optimized(search_query: str, note_title: str = None, category: str = "Search Results", tags: str = "search,web") -> dict:
    """Search and Save to Notepad (Optimized) - Execute web search and save formatted results to notepad
    
    This tool automatically performs web search and saves the results in a formatted manner to your notepad.
    Use this tool when you want to save search results for later reference or sharing.
    
    Parameters:
    - search_query: The query to search for
    - note_title: Optional title for the note (auto-generated if not provided)
    - category: Category for organizing the note (default: "Search Results")
    - tags: Comma-separated tags for the note (default: "search,web")
    """
    try:
        # 执行优化搜索
        search_result = intelligent_web_search_assistant(search_query)
        
        if not search_result.get("success", False):
            return {
                "success": False,
                "error": "搜索失败",
                "search_error": search_result.get("error", "未知错误")
            }
        
        # 格式化搜索结果
        search_content = search_result.get("content", "")
        sources = search_result.get("sources", [])
        
        if not note_title:
            note_title = f"Search Results: {search_query[:50]}"
        
        # 构建笔记内容
        note_content = f"""# {note_title}

**Search Query**: {search_query}
**Search Time**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Search Type**: {search_result.get('type', 'general')}
**Cached Result**: {search_result.get('cached', False)}

## Search Results

{search_content}

## Information Sources

"""
        
        # 添加来源链接
        for i, source in enumerate(sources, 1):
            note_content += f"{i}. [{source.get('title', '未知标题')}]({source.get('url', '#')})\n"
        
        note_content += f"\n---\n*此笔记由优化版网络搜索自动生成*"
        
        save_result: Dict[str, Any] = {"success": False, "error": "未尝试保存", "method": None}

        try:
            valid_categories = {"work", "personal", "study", "other"}
            normalized_category = (category or "study").strip().lower()
            if normalized_category not in valid_categories:
                normalized_category = "study"

            if isinstance(tags, list):
                tag_set = {t.strip() for t in tags if str(t).strip()}
            elif isinstance(tags, str):
                tag_set = {t.strip() for t in tags.split(",") if t.strip()}
            else:
                tag_set = set()

            tag_set.update({"搜索结果", "AI助手", "自动保存"})
            tags_str = ", ".join(sorted(tag_set))

            # 首先尝试通过 Redis 与记事本服务通信
            try:
                redis_result = _send_note_to_redis(
                    title=note_title,
                    content=note_content,
                    category=normalized_category,
                    tags=tags_str,
                )

                if redis_result.get("success"):
                    redis_result.setdefault("method", "redis_mcp")
                    redis_result.setdefault("message", "笔记已成功保存到记事本服务")
                    logger.info("Successfully saved note via Redis: %s", redis_result.get("note_id"))
                    save_result = redis_result
                else:
                    logger.warning("Redis communication failed: %s", redis_result.get("error"))
                    save_result = redis_result

            except Exception as redis_error:  # pragma: no cover - defensive
                logger.warning("Redis communication error: %s", redis_error)
                save_result = {"success": False, "error": str(redis_error), "method": "redis_mcp"}

            # 默认不再模拟成功，避免“助手说保存了但记事本找不到”的假成功。
            # 需要演示模式时可显式设置 WEBSEARCH_ALLOW_SIMULATED_NOTE_SAVE=true。
            if not save_result.get("success") and _env_flag("WEBSEARCH_ALLOW_SIMULATED_NOTE_SAVE", False):
                simulated_id = f"note_simulated_{int(time.time())}"
                logger.info("Using simulated notepad save: %s", simulated_id)
                save_result = {
                    "success": True,
                    "note_id": simulated_id,
                    "message": "笔记已模拟保存（记事本服务不可用时的备选方案）",
                    "method": "simulated",
                    "note_data": {
                        "title": note_title,
                        "category": normalized_category,
                        "tags": tags_str,
                        "content_length": len(note_content),
                        "search_engine": search_result.get('search_engine', '未知'),
                        "sources_count": search_result.get('sources_count', 0),
                    },
                }

        except Exception as save_error:
            logger.error("Note saving error: %s", save_error)
            save_result = {
                "success": False,
                "error": f"笔记保存失败: {save_error}",
                "note_id": None,
                "method": "redis_mcp",
            }

        truncated_content = (
            search_content[:500] + "..." if len(search_content) > 500 else search_content
        )

        if not save_result.get("success"):
            logger.warning(
                "Note save failed | method=%s | error=%s",
                save_result.get("method"),
                save_result.get("error"),
            )
            return {
                "success": False,
                "error": save_result.get("error", "笔记保存失败"),
                "note_save": save_result,
                "note_title": note_title,
                "search_content": truncated_content,
                "sources_count": len(sources),
                "performance_optimized": True,
            }

        logger.info(
            "Note saved | method=%s | note_id=%s | length=%s",
            save_result.get("method"),
            save_result.get("note_id"),
            len(note_content),
        )

        return {
            "success": True,
            "message": save_result.get("message", "搜索结果已成功保存到笔记本（优化版）"),
            "note_id": save_result.get("note_id"),
            "note_title": note_title,
            "search_content": truncated_content,
            "sources_count": len(sources),
            "performance_optimized": True,
            "save_method": save_result.get("method"),
            "note_save": save_result,
        }
        
    except Exception as e:
        error_msg = f"优化版搜索并保存失败: {str(e)}"
        logger.error(f"{error_msg}\n{traceback.format_exc()}")
        return {"success": False, "error": error_msg, "query": search_query}

# 定期清理任务
def periodic_cleanup():
    """定期清理任务"""
    while True:
        try:
            time.sleep(3600)  # 每小时执行一次
            cache_manager.clear_expired()
            gc.collect()
            logger.info("Periodic cleanup completed")
        except Exception as e:
            logger.error(f"Periodic cleanup failed: {e}")

# Redis通信辅助函数
def _get_redis_connection():
    """获取Redis连接 - 支持多种配置自动检测"""
    try:
        import redis

        # 多种Redis配置，按优先级尝试
        redis_configs = [
            {
                'name': 'Environment Config',
                'host': os.getenv('MCP_REDIS_HOST', 'localhost'),
                'port': int(os.getenv('MCP_REDIS_PORT', '6380')),
                'db': int(os.getenv('MCP_REDIS_DB', '1')),
                'password': os.getenv('MCP_REDIS_PASSWORD')
            },
            {
                'name': 'Docker Compose Redis',
                'host': 'redis',
                'port': 6379,
                'db': int(os.getenv('MCP_REDIS_DB', '1')),
                'password': os.getenv('MCP_REDIS_PASSWORD')
            },
            {
                'name': 'Standard Docker Mapping',
                'host': 'localhost',
                'port': 6380,
                'db': 1,
                'password': os.getenv('MCP_REDIS_PASSWORD')
            },
            {
                'name': 'Standard Docker Mapping DB0',
                'host': 'localhost',
                'port': 6380,
                'db': 0,
                'password': os.getenv('MCP_REDIS_PASSWORD')
            },
            {
                'name': 'Local Redis Default',
                'host': 'localhost',
                'port': 6379,
                'db': 1,
                'password': None
            }
        ]

        for config in redis_configs:
            try:
                bridge_timeout = _get_notepad_bridge_timeout()
                redis_config = {
                    'host': config['host'],
                    'port': config['port'],
                    'db': config['db'],
                    'decode_responses': True,
                    'socket_timeout': bridge_timeout + 2,
                    'socket_connect_timeout': 5,
                    'retry_on_timeout': True
                }

                if config['password']:
                    redis_config['password'] = config['password']

                r = redis.Redis(**redis_config)
                r.ping()  # 测试连接

                logger.info(f"Redis connected using {config['name']}: {config['host']}:{config['port']}/db{config['db']}")
                return r

            except Exception as e:
                logger.debug(f"Redis config {config['name']} failed: {e}")
                continue

        logger.error("All Redis configurations failed")
        return None

    except ImportError:
        logger.error("Redis library not installed: pip install redis")
        return None
    except Exception as e:
        logger.error(f"Redis connection error: {e}")
        return None

def _send_note_to_redis(title: str, content: str, category: str, tags: str) -> dict:
    """通过Redis向记事本服务发送创建笔记请求"""
    try:
        r = _get_redis_connection()
        if not r:
            return {"success": False, "error": "Redis连接失败"}

        # 生成请求ID
        request_id = str(uuid.uuid4())

        # 构建请求 - 使用与记事本服务兼容的格式
        request = {
            "id": request_id,
            "action": "create_note",
            "params": {
                "title": title,
                "content": content,
                "category": category,
                "tags": tags,
                "priority": "medium"  # 添加默认优先级
            },
            "timestamp": datetime.now().isoformat(),
            "from_service": "websearch"
        }

        # 发送请求到notepad_requests队列
        response_key = f"response_{request_id}"
        r.delete(response_key)
        r.lpush("notepad_requests", json.dumps(request, ensure_ascii=False))
        logger.info(f"Sent note creation request to Redis: {request_id}")

        try:
            response_data = r.brpop(response_key, timeout=_get_notepad_bridge_timeout())
            if response_data:
                response = json.loads(response_data[1])
                response.setdefault("method", "redis_mcp")
                logger.info("Received response from notepad service (success=%s)", response.get("success"))
                return response
            return {"success": False, "error": "等待记事本服务响应超时", "method": "redis_mcp"}
        except Exception as wait_error:
            logger.error("Error waiting for response: %s", wait_error)
            return {"success": False, "error": f"等待响应时出错: {wait_error}", "method": "redis_mcp"}
        finally:
            try:
                r.delete(response_key)
            except Exception:
                pass

    except Exception as e:
        logger.error(f"Redis communication error: {e}")
        return {"success": False, "error": str(e)}


# ============================================================================
# Voice-friendly MCP tool surface
# ============================================================================

@mcp.tool(name="websearch_search", description="联网搜索当前信息，自动选择通用、新闻、学术或技术搜索。")
def websearch_search(search_query: str) -> dict:
    return intelligent_web_search_assistant(search_query)


@mcp.tool(name="websearch_save_to_notepad", description="联网搜索并把真实保存结果写入记事本；保存失败会返回失败。")
def websearch_save_to_notepad(
    search_query: str,
    note_title: str = None,
    category: str = "study",
    tags: str = "search,web",
) -> dict:
    return search_and_save_to_notepad_optimized(search_query, note_title, category, tags)


@mcp.tool(name="websearch_health_check", description="检查联网搜索服务健康状态、内存、缓存和外部连通性。")
def websearch_health_check() -> dict:
    return get_health_status()


@mcp.tool(name="websearch_runtime_stats", description="查看联网搜索运行时统计，包括请求、缓存、连接和断路器状态。")
def websearch_runtime_stats() -> dict:
    return get_search_runtime_stats()


@mcp.tool(name="websearch_notepad_bridge_check", description="检查搜索服务到记事本服务的 Redis 桥接状态，不等待记事本写入。")
def websearch_notepad_bridge_check() -> dict:
    return check_notepad_bridge()


@mcp.tool(name="websearch_cache_clear", description="清理联网搜索缓存并触发内存回收。")
def websearch_cache_clear() -> dict:
    return clear_cache()


VOICE_TOOL_NAMES = (
    "websearch_search",
    "websearch_save_to_notepad",
    "websearch_health_check",
    "websearch_runtime_stats",
    "websearch_notepad_bridge_check",
    "websearch_cache_clear",
)

LEGACY_TOOL_NAMES_TO_HIDE = (
    "ping_notepad_via_redis",
    "get_configuration_info",
    "update_configuration_parameter",
    "intelligent_web_search_assistant",
    "get_performance_statistics",
    "get_search_runtime_stats",
    "update_cache_settings",
    "check_notepad_bridge",
    "get_health_status",
    "get_cache_details",
    "clear_cache",
    "get_error_analysis",
    "reset_circuit_breaker",
    "search_and_save_to_notepad_optimized",
)


def _remove_registered_tools(names: tuple) -> List[str]:
    removed: List[str] = []
    tool_manager = getattr(mcp, "_tool_manager", None)
    tools = getattr(tool_manager, "_tools", None)
    if not isinstance(tools, dict):
        logger.warning("FastMCP tool manager internals unavailable; cannot trim websearch tool surface")
        return removed

    for tool_name in names:
        if tools.pop(tool_name, None) is not None:
            removed.append(tool_name)
    return removed


def _configure_tool_surface() -> None:
    surface = os.getenv("WEBSEARCH_TOOL_SURFACE", "voice").strip().lower()
    valid_surfaces = {"voice", "legacy", "all", "full", "debug"}
    if surface not in valid_surfaces:
        logger.warning("Unknown WEBSEARCH_TOOL_SURFACE=%r, falling back to voice", surface)
        surface = "voice"

    if surface == "legacy":
        removed = _remove_registered_tools(VOICE_TOOL_NAMES)
        logger.info("Websearch legacy tool surface enabled; hidden %s voice aliases", len(removed))
        return

    expose_legacy = _env_flag("WEBSEARCH_EXPOSE_LEGACY_TOOLS", surface in ("all", "full", "debug"))
    if expose_legacy:
        logger.info("Websearch full tool surface enabled; voice aliases and legacy tools are both exposed")
        return

    removed = _remove_registered_tools(LEGACY_TOOL_NAMES_TO_HIDE)
    logger.info("Websearch voice tool surface enabled; hidden %s legacy/admin tools", len(removed))


_configure_tool_surface()

# 启动后台清理线程
cleanup_thread = threading.Thread(target=periodic_cleanup, daemon=True)
cleanup_thread.start()

logger.info("Websearch optimized service initialized successfully")

if __name__ == "__main__":
    mcp.run(transport="stdio")
