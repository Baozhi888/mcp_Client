"""
Retry Manager for Market MCP Optimized
"""
import asyncio
import logging
import random
from typing import Callable, Any, Optional
from functools import wraps

logger = logging.getLogger(__name__)

class RetryManager:
    """重试管理器"""
    
    def __init__(self, max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 60.0):
        """
        初始化重试管理器
        
        Args:
            max_retries: 最大重试次数
            base_delay: 基础延迟时间（秒）
            max_delay: 最大延迟时间（秒）
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
    
    async def retry_async(self, func: Callable, *args, **kwargs) -> Any:
        """
        异步重试执行函数
        
        Args:
            func: 要执行的函数
            *args: 函数参数
            **kwargs: 函数关键字参数
            
        Returns:
            函数执行结果
            
        Raises:
            Exception: 如果所有重试都失败，则抛出最后一个异常
        """
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                if attempt < self.max_retries:
                    delay = self._calculate_delay(attempt)
                    logger.warning(f"Attempt {attempt + 1} failed for {func.__name__}: {e}. Retrying in {delay:.2f}s...")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"All {self.max_retries + 1} attempts failed for {func.__name__}: {e}")
        
        raise last_exception
    
    def retry_sync(self, func: Callable, *args, **kwargs) -> Any:
        """
        同步重试执行函数
        
        Args:
            func: 要执行的函数
            *args: 函数参数
            **kwargs: 函数关键字参数
            
        Returns:
            函数执行结果
            
        Raises:
            Exception: 如果所有重试都失败，则抛出最后一个异常
        """
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                if attempt < self.max_retries:
                    delay = self._calculate_delay(attempt)
                    logger.warning(f"Attempt {attempt + 1} failed for {func.__name__}: {e}. Retrying in {delay:.2f}s...")
                    asyncio.sleep(delay)  # 注意：在同步函数中使用asyncio.sleep可能不是最佳选择
                else:
                    logger.error(f"All {self.max_retries + 1} attempts failed for {func.__name__}: {e}")
        
        raise last_exception
    
    def _calculate_delay(self, attempt: int) -> float:
        """
        计算延迟时间（指数退避+抖动）
        
        Args:
            attempt: 当前尝试次数
            
        Returns:
            延迟时间（秒）
        """
        # 指数退避
        delay = self.base_delay * (2 ** attempt)
        
        # 添加随机抖动（±25%）
        jitter = random.uniform(0.75, 1.25)
        delay *= jitter
        
        # 限制最大延迟
        return min(delay, self.max_delay)
    
    def retry_decorator(self, exceptions: tuple = (Exception,)):
        """
        重试装饰器
        
        Args:
            exceptions: 需要重试的异常类型元组
            
        Returns:
            装饰器函数
        """
        def decorator(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                last_exception = None
                
                for attempt in range(self.max_retries + 1):
                    try:
                        if asyncio.iscoroutinefunction(func):
                            return await func(*args, **kwargs)
                        else:
                            # 如果是同步函数，在执行器中运行
                            loop = asyncio.get_event_loop()
                            return await loop.run_in_executor(None, func, *args, **kwargs)
                    except exceptions as e:
                        last_exception = e
                        if attempt < self.max_retries:
                            delay = self._calculate_delay(attempt)
                            logger.warning(f"Attempt {attempt + 1} failed for {func.__name__}: {e}. Retrying in {delay:.2f}s...")
                            await asyncio.sleep(delay)
                        else:
                            logger.error(f"All {self.max_retries + 1} attempts failed for {func.__name__}: {e}")
                
                raise last_exception
            
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                last_exception = None
                
                for attempt in range(self.max_retries + 1):
                    try:
                        return func(*args, **kwargs)
                    except exceptions as e:
                        last_exception = e
                        if attempt < self.max_retries:
                            delay = self._calculate_delay(attempt)
                            logger.warning(f"Attempt {attempt + 1} failed for {func.__name__}: {e}. Retrying in {delay:.2f}s...")
                            # 注意：在同步函数中使用time.sleep而不是asyncio.sleep
                            import time
                            time.sleep(delay)
                        else:
                            logger.error(f"All {self.max_retries + 1} attempts failed for {func.__name__}: {e}")
                
                raise last_exception
            
            # 根据原函数是否为异步函数返回相应的包装器
            return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
        
        return decorator

# 全局重试管理器实例
retry_manager = RetryManager()

# 便捷装饰器
def retry_on_failure(max_retries: int = 3, base_delay: float = 1.0, exceptions: tuple = (Exception,)):
    """
    便捷重试装饰器
    
    Args:
        max_retries: 最大重试次数
        base_delay: 基础延迟时间
        exceptions: 需要重试的异常类型
        
    Returns:
        装饰器函数
    """
    manager = RetryManager(max_retries, base_delay)
    return manager.retry_decorator(exceptions)