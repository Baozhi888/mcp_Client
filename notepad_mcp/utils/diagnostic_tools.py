"""
诊断工具模块
用于记录和分析系统运行状态
"""

import logging
import json
import traceback
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger('DIAGNOSTIC_TOOLS')

class DebugLogger:
    """调试日志记录器"""
    
    def __init__(self):
        self.logger = logger
    
    def log_sql_query(self, query: str, params: list, result: Optional[Dict] = None, 
                      error: Optional[str] = None) -> None:
        """记录SQL查询"""
        log_data = {
            'timestamp': datetime.now().isoformat(),
            'type': 'sql_query',
            'query': query,
            'params': params
        }
        
        if result is not None:
            log_data['result'] = result
        if error is not None:
            log_data['error'] = error
            
        self.logger.debug(f"SQL Query Log: {json.dumps(log_data, ensure_ascii=False)}")
    
    def log_api_request(self, service: str, method: str, params: Dict = None,
                       response: Any = None, error: str = None) -> None:
        """记录API请求"""
        log_data = {
            'timestamp': datetime.now().isoformat(),
            'type': 'api_request',
            'service': service,
            'method': method
        }
        
        if params is not None:
            # 过滤敏感信息
            filtered_params = self._filter_sensitive_data(params)
            log_data['params'] = filtered_params
            
        if response is not None:
            log_data['response'] = response
            
        if error is not None:
            log_data['error'] = error
            
        self.logger.debug(f"API Request Log: {json.dumps(log_data, ensure_ascii=False)}")
    
    def log_error_details(self, service: str, operation: str, error: Exception,
                         context: Dict = None) -> None:
        """记录详细错误信息"""
        log_data = {
            'timestamp': datetime.now().isoformat(),
            'type': 'error',
            'service': service,
            'operation': operation,
            'error': {
                'type': type(error).__name__,
                'message': str(error),
                'traceback': traceback.format_exc()
            }
        }
        
        if context is not None:
            # 过滤敏感信息
            filtered_context = self._filter_sensitive_data(context)
            log_data['context'] = filtered_context
            
        self.logger.error(f"Error Details Log: {json.dumps(log_data, ensure_ascii=False)}")
    
    def _filter_sensitive_data(self, data: Dict) -> Dict:
        """过滤敏感信息"""
        sensitive_keys = ['password', 'token', 'secret', 'key', 'auth', 'credential']
        
        if not isinstance(data, dict):
            return data
            
        filtered = {}
        for key, value in data.items():
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                filtered[key] = '***FILTERED***'
            elif isinstance(value, dict):
                filtered[key] = self._filter_sensitive_data(value)
            elif isinstance(value, list):
                filtered[key] = [self._filter_sensitive_data(item) if isinstance(item, dict)
                               else item for item in value]
            else:
                filtered[key] = value
                
        return filtered
