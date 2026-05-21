"""
Cache Service for Market MCP Optimized
"""
import logging
from typing import Any, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class CacheService:
    """缓存服务类"""
    
    def __init__(self, default_ttl: int = 300):
        """
        初始化缓存服务
        
        Args:
            default_ttl: 默认缓存过期时间（秒）
        """
        self.default_ttl = default_ttl
        self.cache = {}
        self.stats = {
            'hits': 0,
            'misses': 0,
            'sets': 0,
            'deletes': 0
        }
    
    def get(self, key: str) -> Optional[Any]:
        """
        获取缓存值
        
        Args:
            key: 缓存键
            
        Returns:
            缓存值，如果不存在或过期则返回None
        """
        if key not in self.cache:
            self.stats['misses'] += 1
            return None
        
        item = self.cache[key]
        if datetime.now() > item['expires_at']:
            # 缓存过期，删除并返回None
            del self.cache[key]
            self.stats['misses'] += 1
            return None
        
        self.stats['hits'] += 1
        return item['value']
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        设置缓存值
        
        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间（秒），如果为None则使用默认值
            
        Returns:
            设置是否成功
        """
        try:
            expires_at = datetime.now() + timedelta(seconds=ttl or self.default_ttl)
            self.cache[key] = {
                'value': value,
                'expires_at': expires_at,
                'created_at': datetime.now()
            }
            self.stats['sets'] += 1
            return True
        except Exception as e:
            logger.error(f"Error setting cache key {key}: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """
        删除缓存项
        
        Args:
            key: 缓存键
            
        Returns:
            删除是否成功
        """
        if key in self.cache:
            del self.cache[key]
            self.stats['deletes'] += 1
            return True
        return False
    
    def exists(self, key: str) -> bool:
        """
        检查缓存键是否存在且未过期
        
        Args:
            key: 缓存键
            
        Returns:
            是否存在且未过期
        """
        if key not in self.cache:
            return False
        
        if datetime.now() > self.cache[key]['expires_at']:
            # 过期则删除
            del self.cache[key]
            return False
        
        return True
    
    def clear(self) -> int:
        """
        清空所有缓存
        
        Returns:
            清空的缓存项数量
        """
        count = len(self.cache)
        self.cache.clear()
        logger.info(f"Cleared {count} cache items")
        return count
    
    def get_stats(self) -> dict:
        """
        获取缓存统计信息
        
        Returns:
            统计信息字典
        """
        total_requests = self.stats['hits'] + self.stats['misses']
        hit_rate = (self.stats['hits'] / total_requests * 100) if total_requests > 0 else 0
        
        return {
            'total_items': len(self.cache),
            'hits': self.stats['hits'],
            'misses': self.stats['misses'],
            'hit_rate': f"{hit_rate:.2f}%",
            'sets': self.stats['sets'],
            'deletes': self.stats['deletes']
        }
    
    def cleanup_expired(self) -> int:
        """
        清理过期的缓存项
        
        Returns:
            清理的过期项数量
        """
        now = datetime.now()
        expired_keys = [
            key for key, item in self.cache.items() 
            if now > item['expires_at']
        ]
        
        for key in expired_keys:
            del self.cache[key]
        
        logger.debug(f"Cleaned up {len(expired_keys)} expired cache items")
        return len(expired_keys)
    
    def get_size(self) -> int:
        """
        获取缓存大小
        
        Returns:
            缓存项数量
        """
        return len(self.cache)
    
    def get_keys(self) -> list:
        """
        获取所有缓存键
        
        Returns:
            缓存键列表
        """
        # 清理过期项后再返回键列表
        self.cleanup_expired()
        return list(self.cache.keys())

# 全局缓存服务实例
cache_service = CacheService()