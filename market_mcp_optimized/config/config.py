"""
Market MCP Configuration Management
"""
import os
from typing import Optional


class MarketConfig:
    """Configuration class for Market MCP service"""
    
    def __init__(self):
        # API Keys
        self.alpha_vantage_api_key: Optional[str] = os.getenv('ALPHA_VANTAGE_API_KEY')
        self.yahoo_finance_api_key: Optional[str] = os.getenv('YAHOO_FINANCE_API_KEY')
        
        # Database Configuration
        self.database_url: str = os.getenv('MARKET_DB_URL', 'sqlite:///market_data.db')
        
        # Redis Configuration
        self.redis_host: str = os.getenv('MCP_REDIS_HOST', 'localhost')
        self.redis_port: int = int(os.getenv('MCP_REDIS_PORT', 6380))
        self.redis_db: int = int(os.getenv('MCP_REDIS_DB', 2))
        
        # WebSocket Configuration
        self.websocket_host: str = os.getenv('MARKET_WS_HOST', 'localhost')
        self.websocket_port: int = int(os.getenv('MARKET_WS_PORT', 8765))
        
        # Logging Configuration
        self.log_level: str = os.getenv('LOG_LEVEL', 'INFO')
        self.log_file: str = os.getenv('MARKET_LOG_FILE', 'market_mcp_optimized.log')
        
        # Service Configuration
        self.service_name: str = 'market_mcp_optimized'
        self.service_version: str = '1.0.0'
        
        # Market Data Configuration
        self.default_symbols: list = os.getenv('DEFAULT_SYMBOLS', 'AAPL,GOOGL,MSFT').split(',')
        self.update_interval: int = int(os.getenv('UPDATE_INTERVAL', 300))  # seconds
        
        # Cache Configuration
        self.cache_ttl: int = int(os.getenv('CACHE_TTL', 3600))  # seconds


# Global configuration instance
config = MarketConfig()