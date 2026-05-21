"""
Sina Finance Data Adapter for Market MCP
"""
import logging
import asyncio
import aiohttp
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class SinaAdapter:
    """新浪财经数据源适配器"""
    
    def __init__(self):
        self.session = None
        self.timeout = 20  # 20秒超时
        self.initialized = False
        
    async def initialize(self):
        """初始化适配器"""
        if self.session is None:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self.session = aiohttp.ClientSession(timeout=timeout)
            self.initialized = True
            logger.info("Sina adapter initialized")
    
    async def close(self):
        """关闭适配器"""
        if self.session:
            await self.session.close()
            self.session = None
            self.initialized = False
    
    async def get_stock_realtime(self, symbol: str) -> Dict[str, Any]:
        """获取股票实时行情"""
        if not self.initialized:
            await self.initialize()
            
        try:
            # 格式化股票代码
            formatted_symbol = self._format_stock_code(symbol)
            url = f"http://hq.sinajs.cn/list={formatted_symbol}"
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    text = await response.text()
                    text = text.encode('latin1').decode('gbk')  # 处理编码
                    
                    # 解析返回数据
                    if '=\"\"' in text or '未上市' in text:
                        return {}
                    
                    data_str = text.split('=\"')[1].split('\";')[0]
                    fields = data_str.split(',')
                    
                    if len(fields) >= 32:
                        return {
                            'symbol': symbol,
                            'name': fields[0],
                            'open': float(fields[1]) if fields[1] else 0.0,
                            'pre_close': float(fields[2]) if fields[2] else 0.0,
                            'price': float(fields[3]) if fields[3] else 0.0,
                            'high': float(fields[4]) if fields[4] else 0.0,
                            'low': float(fields[5]) if fields[5] else 0.0,
                            'volume': int(float(fields[8])) if fields[8] else 0,
                            'amount': float(fields[9]) if fields[9] else 0.0,
                            'date': fields[30] if len(fields) > 30 else '',
                            'time': fields[31] if len(fields) > 31 else ''
                        }
                else:
                    logger.warning(f"Sina API returned status {response.status} for {symbol}")
                    return {}
        except Exception as e:
            logger.error(f"Error getting stock realtime data from Sina for {symbol}: {e}")
            return {}
    
    async def get_forex_rate(self, symbol: str) -> Dict[str, Any]:
        """获取外汇汇率"""
        if not self.initialized:
            await self.initialize()
            
        try:
            # 格式化外汇代码
            formatted_symbol = symbol.replace('/', '').lower()
            url = f"http://hq.sinajs.cn/list=fx_s{formatted_symbol}"
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    text = await response.text()
                    text = text.encode('latin1').decode('gbk')  # 处理编码
                    
                    # 解析返回数据
                    if '=\"\"' in text:
                        return {}
                    
                    data_str = text.split('=\"')[1].split('\";')[0]
                    fields = data_str.split(',')
                    
                    if len(fields) >= 10:
                        return {
                            'symbol': symbol,
                            'name': fields[9] if len(fields) > 9 else symbol,
                            'price': float(fields[1]) if fields[1] else 0.0,
                            'bid': float(fields[2]) if fields[2] else 0.0,
                            'ask': float(fields[3]) if fields[3] else 0.0,
                            'high': float(fields[4]) if fields[4] else 0.0,
                            'low': float(fields[5]) if fields[5] else 0.0,
                            'open': float(fields[6]) if fields[6] else 0.0,
                            'pre_close': float(fields[7]) if fields[7] else 0.0,
                            'time': fields[0] if fields[0] else ''
                        }
                else:
                    logger.warning(f"Sina forex API returned status {response.status} for {symbol}")
                    return {}
        except Exception as e:
            logger.error(f"Error getting forex rate from Sina for {symbol}: {e}")
            return {}
    
    async def get_kline_data(self, symbol: str, period: str = 'day', count: int = 30) -> Dict[str, Any]:
        """获取K线数据"""
        if not self.initialized:
            await self.initialize()
            
        try:
            # 格式化股票代码
            formatted_symbol = self._format_stock_code(symbol)
            
            # 根据周期选择不同的API
            if period in ['5min', '15min', '30min', '60min']:
                # 分钟K线
                url = f"http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getMinuteKLineData?symbol={formatted_symbol}"
            else:
                # 日K线
                url = f"http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getKLineData?symbol={formatted_symbol}&scale=240&datalen={count}"
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    text = await response.text()
                    
                    # 简单解析JSON数据（实际需要更完善的解析）
                    if text.startswith('[') and text.endswith(']'):
                        # 这里简化处理，实际需要JSON解析
                        return {'success': True, 'data': [], 'raw': text[:200]}  # 返回部分原始数据
                    
                    return {'success': False, 'error': 'Invalid data format'}
                else:
                    logger.warning(f"Sina kline API returned status {response.status} for {symbol}")
                    return {'success': False, 'error': f'HTTP {response.status}'}
        except Exception as e:
            logger.error(f"Error getting kline data from Sina for {symbol}: {e}")
            return {'success': False, 'error': str(e)}
    
    def _format_stock_code(self, symbol: str) -> str:
        """格式化股票代码"""
        if symbol.isdigit():
            if symbol.startswith('6'):
                return f'sh{symbol}'
            elif symbol.startswith(('0', '3')):
                return f'sz{symbol}'
        return symbol.lower()
    
    def get_status(self) -> Dict[str, Any]:
        """获取适配器状态"""
        return {
            'initialized': self.initialized,
            'session_active': self.session is not None,
            'timeout': self.timeout
        }