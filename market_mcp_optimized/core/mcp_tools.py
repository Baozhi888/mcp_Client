"""
MCP Tools Registration for Market MCP Optimized
"""
from typing import Dict, Any, List
from mcp.server.fastmcp import FastMCP

# 使用绝对导入而不是相对导入
from market_mcp_optimized.services.market_service import MarketService
from market_mcp_optimized.services.error_handler import error_handler, ErrorType

# 全局MarketService实例
market_service = MarketService()

def register_mcp_tools(mcp: FastMCP):
    """注册所有MCP工具"""
    
    @mcp.tool()
    async def query_stock_realtime_price(symbol: str) -> Dict[str, Any]:
        """
        查询股票实时价格
        
        Args:
            symbol: 股票代码
            
        Returns:
            股票实时行情数据
        """
        try:
            result = await market_service.get_stock_realtime(symbol)
            return result
        except Exception as e:
            error_response = error_handler.handle_error(
                e, ErrorType.INTERNAL_ERROR, 
                {'tool': 'query_stock_realtime_price', 'symbol': symbol}
            )
            return error_response
    
    @mcp.tool()
    async def query_multiple_symbols_batch(symbols: List[str]) -> Dict[str, Any]:
        """
        批量查询多个股票实时价格
        
        Args:
            symbols: 股票代码列表
            
        Returns:
            批量查询结果
        """
        try:
            result = await market_service.get_multiple_stock_realtime(symbols)
            return result
        except Exception as e:
            error_response = error_handler.handle_error(
                e, ErrorType.INTERNAL_ERROR,
                {'tool': 'query_multiple_symbols_batch', 'symbols': symbols}
            )
            return error_response
    
    @mcp.tool()
    async def query_kline_chart_data(symbol: str, period: str = 'day', count: int = 30) -> Dict[str, Any]:
        """
        查询K线图表数据
        
        Args:
            symbol: 股票代码
            period: K线周期 (5min, 15min, 30min, 60min, day, week, month)
            count: K线数量
            
        Returns:
            K线数据
        """
        try:
            result = await market_service.get_kline_data(symbol, period, count)
            return result
        except Exception as e:
            error_response = error_handler.handle_error(
                e, ErrorType.INTERNAL_ERROR,
                {'tool': 'query_kline_chart_data', 'symbol': symbol, 'period': period}
            )
            return error_response
    
    @mcp.tool()
    async def query_forex_exchange_rate(symbol: str) -> Dict[str, Any]:
        """
        查询外汇汇率
        
        Args:
            symbol: 外汇代码 (如: USD/CNY)
            
        Returns:
            外汇汇率数据
        """
        try:
            result = await market_service.get_forex_rate(symbol)
            return result
        except Exception as e:
            error_response = error_handler.handle_error(
                e, ErrorType.INTERNAL_ERROR,
                {'tool': 'query_forex_exchange_rate', 'symbol': symbol}
            )
            return error_response
    
    @mcp.tool()
    async def query_sector_constituent_stocks(sector: str) -> Dict[str, Any]:
        """
        查询板块成分股
        
        Args:
            sector: 板块名称
            
        Returns:
            板块成分股数据
        """
        try:
            result = await market_service.get_sector_stocks(sector)
            return result
        except Exception as e:
            error_response = error_handler.handle_error(
                e, ErrorType.INTERNAL_ERROR,
                {'tool': 'query_sector_constituent_stocks', 'sector': sector}
            )
            return error_response
    
    @mcp.tool()
    async def get_market_service_status() -> Dict[str, Any]:
        """
        获取市场服务状态
        
        Returns:
            服务状态信息
        """
        try:
            result = market_service.get_service_status()
            return result
        except Exception as e:
            error_response = error_handler.handle_error(
                e, ErrorType.INTERNAL_ERROR,
                {'tool': 'get_market_service_status'}
            )
            return error_response
    
    @mcp.tool()
    async def clear_market_data_cache() -> Dict[str, Any]:
        """
        清空市场数据缓存
        
        Returns:
            清空结果
        """
        try:
            result = market_service.clear_cache()
            return result
        except Exception as e:
            error_response = error_handler.handle_error(
                e, ErrorType.INTERNAL_ERROR,
                {'tool': 'clear_market_data_cache'}
            )
            return error_response
    
    # 返回所有已注册的工具名称
    return [
        'query_stock_realtime_price',
        'query_multiple_symbols_batch',
        'query_kline_chart_data',
        'query_forex_exchange_rate',
        'query_sector_constituent_stocks',
        'get_market_service_status',
        'clear_market_data_cache'
    ]