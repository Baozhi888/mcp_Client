"""
Data Source Manager for Market MCP
"""
import logging
from typing import Dict, Any, List, Optional
from enum import Enum

from .tushare_adapter import TuShareAdapter
from .sina_adapter import SinaAdapter

logger = logging.getLogger(__name__)

class DataSourceType(Enum):
    """数据源类型"""
    TUSHARE = "tushare"
    SINA = "sina"
    DEFAULT = "default"

class DataSourceManager:
    """统一数据源管理器"""
    
    def __init__(self):
        self.tushare_adapter = TuShareAdapter()
        self.sina_adapter = SinaAdapter()
        self.initialized = False
        
        # 数据源优先级配置
        self.priority_config = {
            'stock_realtime': [DataSourceType.SINA, DataSourceType.TUSHARE],
            'stock_kline': [DataSourceType.TUSHARE, DataSourceType.SINA],
            'forex_rate': [DataSourceType.SINA],
            'sector_stocks': [DataSourceType.TUSHARE],
            'default': [DataSourceType.SINA, DataSourceType.TUSHARE]
        }
        
        # 数据源状态监控
        self.source_status = {
            DataSourceType.TUSHARE: {
                'available': True,
                'error_count': 0,
                'last_error': None
            },
            DataSourceType.SINA: {
                'available': True,
                'error_count': 0,
                'last_error': None
            }
        }
        
        # 错误阈值
        self.error_threshold = 3
    
    async def initialize(self):
        """初始化所有数据源"""
        # 初始化TuShare
        tushare_success = self.tushare_adapter.initialize()
        self._update_source_status(DataSourceType.TUSHARE, tushare_success, 
                                 "Initialization failed" if not tushare_success else None)
        
        # 初始化新浪
        try:
            await self.sina_adapter.initialize()
            sina_success = True
        except Exception as e:
            logger.error(f"Sina adapter initialization failed: {e}")
            sina_success = False
        self._update_source_status(DataSourceType.SINA, sina_success,
                                 "Initialization failed" if not sina_success else None)
        
        self.initialized = tushare_success or sina_success
        logger.info(f"Data source manager initialized. TuShare: {tushare_success}, Sina: {sina_success}")
        return self.initialized
    
    async def close(self):
        """关闭所有数据源"""
        try:
            await self.sina_adapter.close()
        except Exception as e:
            logger.error(f"Error closing Sina adapter: {e}")
        
        self.initialized = False
        logger.info("Data source manager closed")
    
    def _update_source_status(self, source_type: DataSourceType, success: bool, error_msg: Optional[str] = None):
        """更新数据源状态"""
        if success:
            self.source_status[source_type]['available'] = True
            self.source_status[source_type]['error_count'] = 0
            self.source_status[source_type]['last_error'] = None
        else:
            self.source_status[source_type]['error_count'] += 1
            self.source_status[source_type]['last_error'] = error_msg
            
            # 如果错误次数超过阈值，标记为不可用
            if self.source_status[source_type]['error_count'] >= self.error_threshold:
                self.source_status[source_type]['available'] = False
                logger.warning(f"Data source {source_type.value} marked as unavailable due to repeated errors")
    
    def _get_priority_list(self, data_type: str) -> List[DataSourceType]:
        """获取指定数据类型的优先级列表"""
        return self.priority_config.get(data_type, self.priority_config['default'])
    
    def _is_source_available(self, source_type: DataSourceType) -> bool:
        """检查数据源是否可用"""
        return self.source_status[source_type]['available']
    
    async def get_stock_realtime(self, symbol: str) -> Dict[str, Any]:
        """获取股票实时行情（带降级机制）"""
        priority_list = self._get_priority_list('stock_realtime')
        
        for source_type in priority_list:
            if not self._is_source_available(source_type):
                continue
                
            try:
                if source_type == DataSourceType.TUSHARE and self.tushare_adapter.initialized:
                    result = await self.tushare_adapter.get_stock_realtime(symbol)
                    if result:
                        self._update_source_status(source_type, True)
                        return {
                            'success': True,
                            'data': result,
                            'source': source_type.value
                        }
                elif source_type == DataSourceType.SINA:
                    result = await self.sina_adapter.get_stock_realtime(symbol)
                    if result:
                        self._update_source_status(source_type, True)
                        return {
                            'success': True,
                            'data': result,
                            'source': source_type.value
                        }
            except Exception as e:
                logger.error(f"Error getting stock realtime data from {source_type.value}: {e}")
                self._update_source_status(source_type, False, str(e))
        
        return {
            'success': False,
            'error': 'All data sources failed',
            'sources_tried': [s.value for s in priority_list]
        }
    
    async def get_kline_data(self, symbol: str, period: str = 'day', count: int = 30) -> Dict[str, Any]:
        """获取K线数据（带降级机制）"""
        priority_list = self._get_priority_list('stock_kline')
        
        for source_type in priority_list:
            if not self._is_source_available(source_type):
                continue
                
            try:
                if source_type == DataSourceType.TUSHARE and self.tushare_adapter.initialized:
                    result = await self.tushare_adapter.get_kline_data(symbol, period, count)
                    if result.get('success'):
                        self._update_source_status(source_type, True)
                        result['source'] = source_type.value
                        return result
                elif source_type == DataSourceType.SINA:
                    result = await self.sina_adapter.get_kline_data(symbol, period, count)
                    if result.get('success'):
                        self._update_source_status(source_type, True)
                        result['source'] = source_type.value
                        return result
            except Exception as e:
                logger.error(f"Error getting kline data from {source_type.value}: {e}")
                self._update_source_status(source_type, False, str(e))
        
        return {
            'success': False,
            'error': 'All data sources failed',
            'sources_tried': [s.value for s in priority_list]
        }
    
    async def get_forex_rate(self, symbol: str) -> Dict[str, Any]:
        """获取外汇汇率（带降级机制）"""
        priority_list = self._get_priority_list('forex_rate')
        
        for source_type in priority_list:
            if not self._is_source_available(source_type):
                continue
                
            try:
                if source_type == DataSourceType.SINA:
                    result = await self.sina_adapter.get_forex_rate(symbol)
                    if result:
                        self._update_source_status(source_type, True)
                        return {
                            'success': True,
                            'data': result,
                            'source': source_type.value
                        }
            except Exception as e:
                logger.error(f"Error getting forex rate from {source_type.value}: {e}")
                self._update_source_status(source_type, False, str(e))
        
        return {
            'success': False,
            'error': 'All data sources failed',
            'sources_tried': [s.value for s in priority_list]
        }
    
    async def get_sector_stocks(self, sector: str) -> Dict[str, Any]:
        """获取板块成分股（带降级机制）"""
        priority_list = self._get_priority_list('sector_stocks')
        
        for source_type in priority_list:
            if not self._is_source_available(source_type):
                continue
                
            try:
                if source_type == DataSourceType.TUSHARE and self.tushare_adapter.initialized:
                    result = await self.tushare_adapter.get_sector_stocks(sector)
                    if result.get('success'):
                        self._update_source_status(source_type, True)
                        result['source'] = source_type.value
                        return result
            except Exception as e:
                logger.error(f"Error getting sector stocks from {source_type.value}: {e}")
                self._update_source_status(source_type, False, str(e))
        
        return {
            'success': False,
            'error': 'All data sources failed',
            'sources_tried': [s.value for s in priority_list]
        }
    
    def get_source_health_report(self) -> Dict[str, Any]:
        """获取数据源健康报告"""
        return {
            'tushare': self.source_status[DataSourceType.TUSHARE],
            'sina': self.source_status[DataSourceType.SINA],
            'overall_status': self.initialized
        }
    
    def reset_source_status(self, source_type: DataSourceType):
        """重置数据源状态"""
        if source_type in self.source_status:
            self.source_status[source_type]['available'] = True
            self.source_status[source_type]['error_count'] = 0
            self.source_status[source_type]['last_error'] = None
            logger.info(f"Reset status for data source {source_type.value}")