"""
Market MCP Utility Functions
"""
import logging
import json
from datetime import datetime
from typing import Any, Dict


def setup_logging(log_level: str = "INFO", log_file: str = "market_mcp_optimized.log") -> logging.Logger:
    """Set up logging for the Market MCP service"""
    logger = logging.getLogger("market_mcp_optimized")
    logger.setLevel(log_level)
    
    # Create file handler
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(log_level)
    
    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # Add handlers to logger
    if not logger.handlers:
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
    
    return logger


def serialize_market_data(data: Any) -> str:
    """Serialize market data to JSON string"""
    def json_serializer(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
    
    return json.dumps(data, default=json_serializer, indent=2)


def validate_symbols(symbols: list) -> bool:
    """Validate stock symbols"""
    if not isinstance(symbols, list):
        return False
    
    for symbol in symbols:
        if not isinstance(symbol, str):
            return False
        if len(symbol) == 0 or len(symbol) > 10:
            return False
            
    return True


def format_currency(amount: float, currency: str = "USD") -> str:
    """Format currency values"""
    if currency == "USD":
        return f"${amount:,.2f}"
    elif currency == "EUR":
        return f"€{amount:,.2f}"
    elif currency == "GBP":
        return f"£{amount:,.2f}"
    else:
        return f"{amount:,.2f} {currency}"