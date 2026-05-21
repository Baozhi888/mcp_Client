"""
错误处理工具
用于统一处理错误和异常
"""

import logging
import traceback
from typing import Optional, Dict, Any
from functools import wraps
from datetime import datetime

logger = logging.getLogger(__name__)

class MCPError(Exception):
    """MCP基础异常类"""
    def __init__(self, message: str, code: str = None, details: Dict = None):
        self.message = message
        self.code = code or 'UNKNOWN_ERROR'
        self.details = details or {}
        super().__init__(message)

class DatabaseError(MCPError):
    """数据库错误"""
    pass

class ServiceError(MCPError):
    """服务错误"""
    pass

class ConfigurationError(MCPError):
    """配置错误"""
    pass

def handle_errors(func):
    """错误处理装饰器"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except MCPError as e:
            logger.error(f"{e.__class__.__name__}: {e.message}")
            return {
                "status": "error",
                "code": e.code,
                "message": e.message,
                "details": e.details
            }
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                "status": "error",
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
                "details": {"error": str(e)}
            }
    return wrapper

def log_error(error: Exception, context: Dict[str, Any] = None):
    """
    记录错误信息
    
    Args:
        error: 异常对象
        context: 上下文信息
    """
    error_info = {
        "timestamp": datetime.now().isoformat(),
        "type": error.__class__.__name__,
        "message": str(error),
        "traceback": traceback.format_exc(),
        "context": context or {}
    }
    
    logger.error(f"Error occurred: {error_info['type']}")
    logger.error(f"Message: {error_info['message']}")
    if context:
        logger.error(f"Context: {context}")
    logger.error(f"Traceback:\n{error_info['traceback']}")
    
    return error_info

def format_error_response(error: Exception, code: str = None) -> Dict:
    """
    格式化错误响应
    
    Args:
        error: 异常对象
        code: 错误代码
    
    Returns:
        Dict: 格式化的错误响应
    """
    if isinstance(error, MCPError):
        return {
            "status": "error",
            "code": error.code,
            "message": error.message,
            "details": error.details
        }
    else:
        return {
            "status": "error",
            "code": code or "INTERNAL_ERROR",
            "message": str(error),
            "details": {"type": error.__class__.__name__}
        }

def is_transient_error(error: Exception) -> bool:
    """
    判断是否为临时性错误
    
    Args:
        error: 异常对象
        
    Returns:
        bool: 是否为临时性错误
    """
    transient_errors = (
        'ConnectionError',
        'TimeoutError',
        'OperationalError',
        'ResourceUnavailable',
        'ServiceUnavailable'
    )
    
    return (
        error.__class__.__name__ in transient_errors or
        isinstance(error, ConnectionError) or
        isinstance(error, TimeoutError)
    )

async def retry_operation(operation, max_retries: int = 3, delay: int = 1):
    """
    重试操作
    
    Args:
        operation: 要重试的操作
        max_retries: 最大重试次数
        delay: 重试延迟（秒）
        
    Returns:
        操作结果
    """
    import asyncio
    
    for attempt in range(max_retries):
        try:
            return await operation()
        except Exception as e:
            if not is_transient_error(e) or attempt == max_retries - 1:
                raise
            
            logger.warning(f"Operation failed (attempt {attempt + 1}/{max_retries}): {e}")
            await asyncio.sleep(delay * (attempt + 1))  # 指数退避
    
    raise RuntimeError(f"Operation failed after {max_retries} attempts")
