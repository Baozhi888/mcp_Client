"""
Error Handler for Market MCP Optimized
"""
import logging
from typing import Dict, Any, Optional
from enum import Enum

logger = logging.getLogger(__name__)

class ErrorType(Enum):
    """错误类型枚举"""
    NETWORK_ERROR = "network_error"
    DATA_ERROR = "data_error"
    AUTH_ERROR = "auth_error"
    TIMEOUT_ERROR = "timeout_error"
    API_ERROR = "api_error"
    VALIDATION_ERROR = "validation_error"
    INTERNAL_ERROR = "internal_error"

class MarketErrorHandler:
    """市场数据错误处理器"""
    
    def __init__(self):
        self.error_counts = {}
        self.error_threshold = 3  # 错误阈值
        
    def handle_error(self, error: Exception, error_type: ErrorType, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        处理错误并返回标准化的错误响应
        
        Args:
            error: 异常对象
            error_type: 错误类型
            context: 错误上下文信息
            
        Returns:
            标准化错误响应字典
        """
        error_key = f"{error_type.value}:{str(context.get('source', '')) if context else ''}"
        
        # 更新错误计数
        self.error_counts[error_key] = self.error_counts.get(error_key, 0) + 1
        
        # 记录错误日志
        logger.error(f"Market error [{error_type.value}]: {str(error)}", extra={
            'error_type': error_type.value,
            'context': context,
            'error_count': self.error_counts[error_key]
        })
        
        # 生成用户友好的错误消息
        user_message = self._generate_user_message(error_type, error)
        
        # 生成解决方案建议
        suggestions = self._generate_suggestions(error_type, error)
        
        # 检查是否需要降级或切换数据源
        should_degrade = self.error_counts[error_key] >= self.error_threshold
        
        return {
            'success': False,
            'error': user_message,
            'error_type': error_type.value,
            'original_error': str(error),
            'suggestions': suggestions,
            'should_degrade': should_degrade,
            'error_count': self.error_counts[error_key],
            'context': context or {}
        }
    
    def _generate_user_message(self, error_type: ErrorType, error: Exception) -> str:
        """生成用户友好的错误消息"""
        error_messages = {
            ErrorType.NETWORK_ERROR: "网络连接失败，请检查网络连接",
            ErrorType.DATA_ERROR: "数据格式错误，无法解析返回数据",
            ErrorType.AUTH_ERROR: "认证失败，请检查API密钥配置",
            ErrorType.TIMEOUT_ERROR: "请求超时，请稍后重试",
            ErrorType.API_ERROR: "API调用失败，请稍后重试",
            ErrorType.VALIDATION_ERROR: "参数验证失败，请检查输入参数",
            ErrorType.INTERNAL_ERROR: "内部服务错误，请联系技术支持"
        }
        
        return error_messages.get(error_type, f"未知错误: {str(error)}")
    
    def _generate_suggestions(self, error_type: ErrorType, error: Exception) -> list:
        """生成解决方案建议"""
        suggestions_map = {
            ErrorType.NETWORK_ERROR: [
                "检查网络连接是否正常",
                "确认防火墙设置是否阻止了连接",
                "稍后重试"
            ],
            ErrorType.DATA_ERROR: [
                "检查数据源是否正常",
                "确认API返回格式是否发生变化",
                "联系技术支持"
            ],
            ErrorType.AUTH_ERROR: [
                "检查环境变量中是否正确设置了API密钥",
                "确认API密钥是否有效且未过期",
                "重新配置认证信息"
            ],
            ErrorType.TIMEOUT_ERROR: [
                "网络可能较慢，请稍后重试",
                "尝试减少查询数据量",
                "检查服务器负载情况"
            ],
            ErrorType.API_ERROR: [
                "API服务可能暂时不可用，请稍后重试",
                "检查API调用频率是否超出限制",
                "确认API版本是否兼容"
            ],
            ErrorType.VALIDATION_ERROR: [
                "检查输入参数格式是否正确",
                "确认参数值是否在有效范围内",
                "参考API文档确认参数要求"
            ],
            ErrorType.INTERNAL_ERROR: [
                "服务内部出现错误，请联系技术支持",
                "查看详细日志获取更多信息",
                "稍后重试"
            ]
        }
        
        return suggestions_map.get(error_type, ["请稍后重试", "联系技术支持"])
    
    def should_retry(self, error_type: ErrorType) -> bool:
        """
        判断是否应该重试
        
        Args:
            error_type: 错误类型
            
        Returns:
            是否应该重试
        """
        retryable_errors = [
            ErrorType.NETWORK_ERROR,
            ErrorType.TIMEOUT_ERROR,
            ErrorType.API_ERROR
        ]
        
        return error_type in retryable_errors
    
    def get_error_stats(self) -> Dict[str, Any]:
        """
        获取错误统计信息
        
        Returns:
            错误统计信息字典
        """
        return {
            'error_counts': self.error_counts,
            'total_errors': sum(self.error_counts.values()),
            'threshold': self.error_threshold
        }
    
    def reset_error_count(self, error_key: str):
        """
        重置特定错误的计数
        
        Args:
            error_key: 错误键
        """
        if error_key in self.error_counts:
            del self.error_counts[error_key]
            logger.info(f"Reset error count for {error_key}")
    
    def reset_all_errors(self):
        """重置所有错误计数"""
        count = len(self.error_counts)
        self.error_counts.clear()
        logger.info(f"Reset all {count} error counts")

# 全局错误处理器实例
error_handler = MarketErrorHandler()