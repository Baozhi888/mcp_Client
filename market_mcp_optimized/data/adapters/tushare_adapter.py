"""
TuShare Data Adapter for Market MCP
"""
import os
import logging
import time
import asyncio
from typing import Dict, Any, Optional
import tushare as ts
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

class TuShareAdapter:
    """TuShare数据源适配器"""
    
    def __init__(self):
        self.token = os.getenv('TUSHARE_TOKEN')
        self.pro = None
        self.initialized = False
        self.executor = ThreadPoolExecutor(max_workers=3)
        
        # 配置超时时间
        self.timeout = int(os.getenv('TUSHARE_TIMEOUT', 30))
        self.quick_timeout = int(os.getenv('TUSHARE_QUICK_TIMEOUT', 15))
        
        # 缓存
        self.cache = {}
        self.cache_ttl = 300  # 5分钟缓存
        
    def initialize(self) -> bool:
        """初始化TuShare连接"""
        if not self.token:
            logger.warning("TUSHARE_TOKEN not set, TuShare features will be disabled")
            return False
            
        try:
            ts.set_token(self.token)
            self.pro = ts.pro_api()
            
            # 测试连接
            test_df = self.pro.trade_cal(exchange='SSE', start_date='20240101', end_date='20240102')
            if test_df is not None and not test_df.empty:
                self.initialized = True
                logger.info("TuShare initialized successfully")
                return True
            else:
                logger.error("TuShare connection test failed")
                return False
        except Exception as e:
            logger.error(f"TuShare initialization failed: {e}")
            return False
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """检查缓存是否有效"""
        if cache_key not in self.cache:
            return False
        cached_time = self.cache[cache_key]['timestamp']
        return (time.time() - cached_time) < self.cache_ttl
    
    def _get_cache_key(self, api_name: str, **kwargs) -> str:
        """生成缓存键"""
        return f"{api_name}:{str(sorted(kwargs.items()))}"
    
    async def query_with_cache(self, api_name: str, use_quick_timeout: bool = False, **kwargs) -> Any:
        """带缓存的查询"""
        cache_key = self._get_cache_key(api_name, **kwargs)
        
        # 检查缓存
        if self._is_cache_valid(cache_key):
            logger.debug(f"Using cached data for {api_name}")
            return self.cache[cache_key]['data']
        
        # 执行查询
        result = await self._execute_query(api_name, use_quick_timeout, **kwargs)
        
        # 缓存结果
        if result is not None:
            self.cache[cache_key] = {
                'data': result,
                'timestamp': time.time()
            }
        
        return result
    
    async def _execute_query(self, api_name: str, use_quick_timeout: bool = False, **kwargs) -> Any:
        """执行TuShare查询"""
        if not self.initialized or not self.pro:
            raise Exception("TuShare not initialized")
        
        timeout = self.quick_timeout if use_quick_timeout else self.timeout
        
        def sync_query():
            return self.pro.query(api_name, **kwargs)
        
        try:
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(self.executor, sync_query),
                timeout=timeout
            )
            return result
        except asyncio.TimeoutError:
            raise Exception(f"TuShare query timeout after {timeout}s for {api_name}")
        except Exception as e:
            logger.error(f"TuShare query error for {api_name}: {e}")
            raise
    
    async def get_stock_realtime(self, symbol: str) -> Dict[str, Any]:
        """获取股票实时行情"""
        try:
            # TuShare不直接提供实时行情，这里使用日线数据作为示例
            ts_code = self._format_ts_code(symbol)
            df = await self.query_with_cache('daily', ts_code=ts_code, limit=1)
            if df is not None and not df.empty:
                row = df.iloc[0]
                return {
                    'symbol': symbol,
                    'price': float(row['close']),
                    'open': float(row['open']),
                    'high': float(row['high']),
                    'low': float(row['low']),
                    'volume': int(row['vol']),
                    'amount': float(row.get('amount', 0)),
                    'date': row['trade_date']
                }
            return {}
        except Exception as e:
            logger.error(f"Error getting stock realtime data for {symbol}: {e}")
            return {}
    
    async def get_kline_data(self, symbol: str, period: str = 'daily', count: int = 30) -> Dict[str, Any]:
        """获取K线数据"""
        try:
            ts_code = self._format_ts_code(symbol)
            api_name = 'daily' if period == 'daily' else 'weekly' if period == 'weekly' else 'monthly'
            
            df = await self.query_with_cache(api_name, ts_code=ts_code, limit=count)
            if df is not None and not df.empty:
                kline_data = []
                for _, row in df.iterrows():
                    kline_data.append({
                        'date': row['trade_date'],
                        'open': float(row['open']),
                        'high': float(row['high']),
                        'low': float(row['low']),
                        'close': float(row['close']),
                        'volume': int(row['vol'])
                    })
                return {'success': True, 'data': kline_data}
            return {'success': False, 'error': 'No data found'}
        except Exception as e:
            logger.error(f"Error getting kline data for {symbol}: {e}")
            return {'success': False, 'error': str(e)}
    
    async def get_sector_stocks(self, sector: str) -> Dict[str, Any]:
        """获取板块成分股"""
        try:
            # 这里需要根据具体的板块名称查找对应的指数代码
            # 简化实现，实际需要更复杂的映射
            df = await self.query_with_cache('index_member', index_code=sector)
            if df is not None and not df.empty:
                stocks = []
                for _, row in df.iterrows():
                    stocks.append({
                        'symbol': row['con_code'].split('.')[0],  # 去除后缀
                        'name': row['con_name']
                    })
                return {'success': True, 'data': stocks}
            return {'success': False, 'error': 'No data found'}
        except Exception as e:
            logger.error(f"Error getting sector stocks for {sector}: {e}")
            return {'success': False, 'error': str(e)}
    
    def _format_ts_code(self, symbol: str) -> str:
        """格式化股票代码为TuShare标准格式"""
        if symbol.isdigit():
            if symbol.startswith('6'):
                return f'{symbol}.SH'
            elif symbol.startswith(('0', '3')):
                return f'{symbol}.SZ'
        if '.' in symbol:
            return symbol.upper()
        return symbol
    
    def get_status(self) -> Dict[str, Any]:
        """获取适配器状态"""
        return {
            'initialized': self.initialized,
            'token_set': bool(self.token),
            'cache_size': len(self.cache),
            'timeout': self.timeout,
            'quick_timeout': self.quick_timeout
        }