"""
Market Data Models
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List


@dataclass
class StockData:
    """Stock market data model"""
    symbol: str
    price: float
    volume: int
    timestamp: datetime
    open_price: Optional[float] = None
    high_price: Optional[float] = None
    low_price: Optional[float] = None
    close_price: Optional[float] = None
    previous_close: Optional[float] = None
    change: Optional[float] = None
    change_percent: Optional[float] = None


@dataclass
class MarketIndex:
    """Market index data model"""
    name: str
    value: float
    change: float
    change_percent: float
    timestamp: datetime


@dataclass
class ForexData:
    """Foreign exchange data model"""
    pair: str
    rate: float
    timestamp: datetime
    bid: Optional[float] = None
    ask: Optional[float] = None


@dataclass
class CryptocurrencyData:
    """Cryptocurrency data model"""
    symbol: str
    name: str
    price: float
    volume_24h: float
    market_cap: float
    timestamp: datetime