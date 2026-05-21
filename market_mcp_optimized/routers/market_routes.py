"""
Market MCP API Routes
"""
from typing import List, Optional
import asyncio

from ..services.market_service import MarketDataService, MarketAnalysisService
from ..models.market_models import StockData, MarketIndex, ForexData, CryptocurrencyData


class MarketRoutes:
    """API routes for market data services"""
    
    def __init__(self):
        self.market_data_service = MarketDataService()
        self.analysis_service = MarketAnalysisService(self.market_data_service)
        
    async def get_stock_data(self, symbols: List[str]) -> List[StockData]:
        """Get stock data for specified symbols"""
        return await self.market_data_service.get_stock_data(symbols)
    
    async def get_market_indices(self) -> List[MarketIndex]:
        """Get major market indices"""
        return await self.market_data_service.get_market_indices()
    
    async def get_forex_rates(self, pairs: List[str]) -> List[ForexData]:
        """Get foreign exchange rates"""
        return await self.market_data_service.get_forex_rates(pairs)
    
    async def get_crypto_data(self, symbols: List[str]) -> List[CryptocurrencyData]:
        """Get cryptocurrency data"""
        return await self.market_data_service.get_crypto_data(symbols)
    
    async def get_top_gainers(self, symbols: List[str], limit: int = 5) -> List[StockData]:
        """Get top gaining stocks"""
        return await self.analysis_service.get_top_gainers(symbols, limit)
    
    async def get_top_losers(self, symbols: List[str], limit: int = 5) -> List[StockData]:
        """Get top losing stocks"""
        return await self.analysis_service.get_top_losers(symbols, limit)
    
    async def get_market_summary(self) -> dict:
        """Get market summary"""
        return await self.analysis_service.get_market_summary()