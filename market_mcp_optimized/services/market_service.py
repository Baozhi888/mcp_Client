"""
Market Service for Market MCP Optimized
"""
import logging
from typing import Dict, Any, List
from datetime import datetime, timedelta

from ..data.adapters.data_source_manager import DataSourceManager
from ..utils.helpers import validate_symbols

logger = logging.getLogger(__name__)

class MarketService:
    """市场数据服务核心类"""
    
    def __init__(self):
        self.data_source_manager = DataSourceManager()
        self.initialized = False
        
        # 缓存相关
        self.cache = {}
        self.cache_ttl = 300  # 5分钟缓存
    
    async def initialize(self):
        """初始化服务"""
        success = await self.data_source_manager.initialize()
        self.initialized = success
        logger.info(f"Market service initialized: {success}")
        return success
    
    async def close(self):
        """关闭服务"""
        await self.data_source_manager.close()
        self.initialized = False
        logger.info("Market service closed")
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """检查缓存是否有效"""
        if cache_key not in self.cache:
            return False
        cached_time = self.cache[cache_key]['timestamp']
        return (datetime.now() - cached_time).total_seconds() < self.cache_ttl
    
    def _get_cache_key(self, operation: str, **kwargs) -> str:
        """生成缓存键"""
        return f"{operation}:{str(sorted(kwargs.items()))}"
    
    async def get_stock_realtime(self, symbol: str) -> Dict[str, Any]:
        """获取单只股票实时行情"""
        if not self.initialized:
            return {'success': False, 'error': 'Service not initialized'}
        
        # 检查缓存
        cache_key = self._get_cache_key('stock_realtime', symbol=symbol)
        if self._is_cache_valid(cache_key):
            logger.debug(f"Using cached data for stock realtime {symbol}")
            return self.cache[cache_key]['data']
        
        # 获取数据
        result = await self.data_source_manager.get_stock_realtime(symbol)
        
        # 缓存结果
        if result.get('success'):
            self.cache[cache_key] = {
                'data': result,
                'timestamp': datetime.now()
            }
        
        return result
    
    async def get_multiple_stock_realtime(self, symbols: List[str]) -> Dict[str, Any]:
        """获取多只股票实时行情"""
        if not self.initialized:
            return {'success': False, 'error': 'Service not initialized'}
        
        if not validate_symbols(symbols):
            return {'success': False, 'error': 'Invalid symbols'}
        
        results = {}
        success_count = 0
        failed_count = 0
        
        # 并发获取多只股票数据
        tasks = [self.get_stock_realtime(symbol) for symbol in symbols[:10]]  # 限制并发数
        task_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for symbol, result in zip(symbols[:10], task_results):
            if isinstance(result, Exception):
                results[symbol] = {'success': False, 'error': str(result)}
                failed_count += 1
            else:
                results[symbol] = result
                if result.get('success'):
                    success_count += 1
                else:
                    failed_count += 1
        
        return {
            'success': True,
            'data': results,
            'metadata': {
                'total': len(symbols[:10]),
                'success_count': success_count,
                'failed_count': failed_count
            }
        }
    
    async def get_kline_data(self, symbol: str, period: str = 'day', count: int = 30) -> Dict[str, Any]:
        """获取K线数据"""
        if not self.initialized:
            return {'success': False, 'error': 'Service not initialized'}
        
        # 参数验证
        valid_periods = ['5min', '15min', '30min', '60min', 'day', 'week', 'month']
        if period not in valid_periods:
            return {'success': False, 'error': f'Invalid period. Valid periods: {valid_periods}'}
        
        if not isinstance(count, int) or count < 1 or count > 1000:
            return {'success': False, 'error': 'Count must be between 1 and 1000'}
        
        # 检查缓存
        cache_key = self._get_cache_key('kline_data', symbol=symbol, period=period, count=count)
        if self._is_cache_valid(cache_key):
            logger.debug(f"Using cached data for kline {symbol}")
            return self.cache[cache_key]['data']
        
        # 获取数据
        result = await self.data_source_manager.get_kline_data(symbol, period, count)
        
        # 缓存结果
        if result.get('success'):
            self.cache[cache_key] = {
                'data': result,
                'timestamp': datetime.now()
            }
        
        return result
    
    async def get_forex_rate(self, symbol: str) -> Dict[str, Any]:
        """获取外汇汇率"""
        if not self.initialized:
            return {'success': False, 'error': 'Service not initialized'}
        
        # 检查缓存
        cache_key = self._get_cache_key('forex_rate', symbol=symbol)
        if self._is_cache_valid(cache_key):
            logger.debug(f"Using cached data for forex {symbol}")
            return self.cache[cache_key]['data']
        
        # 获取数据
        result = await self.data_source_manager.get_forex_rate(symbol)
        
        # 缓存结果
        if result.get('success'):
            self.cache[cache_key] = {
                'data': result,
                'timestamp': datetime.now()
            }
        
        return result
    
    async def get_sector_stocks(self, sector: str) -> Dict[str, Any]:
        """获取板块成分股"""
        if not self.initialized:
            return {'success': False, 'error': 'Service not initialized'}
        
        if not sector or not isinstance(sector, str):
            return {'success': False, 'error': 'Invalid sector'}
        
        # 检查缓存
        cache_key = self._get_cache_key('sector_stocks', sector=sector)
        if self._is_cache_valid(cache_key):
            logger.debug(f"Using cached data for sector {sector}")
            return self.cache[cache_key]['data']
        
        # 获取数据
        result = await self.data_source_manager.get_sector_stocks(sector)
        
        # 缓存结果
        if result.get('success'):
            self.cache[cache_key] = {
                'data': result,
                'timestamp': datetime.now()
            }
        
        return result
    
    async def get_batch_data(self, symbols: List[str], data_type: str = 'realtime') -> Dict[str, Any]:
        """批量获取数据"""
        if not self.initialized:
            return {'success': False, 'error': 'Service not initialized'}
        
        if not validate_symbols(symbols):
            return {'success': False, 'error': 'Invalid symbols'}
        
        if data_type == 'realtime':
            return await self.get_multiple_stock_realtime(symbols)
        else:
            return {'success': False, 'error': f'Unsupported data type: {data_type}'}
    
    def get_service_status(self) -> Dict[str, Any]:
        """获取服务状态"""
        return {
            'initialized': self.initialized,
            'cache_size': len(self.cache),
            'data_source_health': self.data_source_manager.get_source_health_report(),
            'timestamp': datetime.now().isoformat()
        }
    
    def clear_cache(self):
        """清空缓存"""
        cache_count = len(self.cache)
        self.cache.clear()
        logger.info(f"Cleared {cache_count} cached items")
        return {'success': True, 'cleared_items': cache_count}