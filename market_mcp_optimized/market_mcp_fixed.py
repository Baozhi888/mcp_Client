"""
Market MCP Optimized - Main Entry Point
"""
import asyncio
import logging
import os
import sys
from typing import List
from dotenv import load_dotenv

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 加载.env文件
load_dotenv()

from mcp.server.fastmcp import FastMCP

# 使用绝对导入而不是相对导入
from market_mcp_optimized.config.config import config
from market_mcp_optimized.utils.helpers import setup_logging
from market_mcp_optimized.services.market_service import MarketService
from market_mcp_optimized.core.mcp_tools import register_mcp_tools

# 全局服务实例
market_service = MarketService()
mcp = FastMCP("MarketManagerOptimized")

class MarketMCPOptimized:
    """Main class for the optimized Market MCP service"""
    
    def __init__(self):
        # Set up logging
        self.logger = setup_logging(config.log_level, config.log_file)
        self.logger.info("Initializing Market MCP Optimized Service")
        
        # Service status
        self.running = False
        
    async def initialize_service(self):
        """Initialize the market service"""
        try:
            success = await market_service.initialize()
            if success:
                self.logger.info("Market service initialized successfully")
                return True
            else:
                self.logger.error("Failed to initialize market service")
                return False
        except Exception as e:
            self.logger.error(f"Error initializing market service: {e}")
            return False
    
    async def start(self):
        """Start the Market MCP service"""
        self.logger.info("Starting Market MCP Optimized Service")
        
        # Initialize the service
        if not await self.initialize_service():
            raise RuntimeError("Failed to initialize market service")
        
        self.running = True
        self.logger.info("Market MCP Optimized Service started successfully")
        
    async def stop(self):
        """Stop the Market MCP service"""
        self.logger.info("Stopping Market MCP Optimized Service")
        self.running = False
        
        # Clean up resources
        try:
            await market_service.close()
        except Exception as e:
            self.logger.error(f"Error closing market service: {e}")
        
        self.logger.info("Market MCP Optimized Service stopped")
    
    def is_running(self) -> bool:
        """Check if the service is running"""
        return self.running

async def main():
    """Main function to run the Market MCP service"""
    # Initialize logging first
    logger = setup_logging(config.log_level, config.log_file)
    logger.info("Starting Market MCP Optimized Service")
    
    # Create service instance
    service = MarketMCPOptimized()
    
    try:
        # Initialize the service
        await service.start()
        
        # Register MCP tools
        registered_tools = register_mcp_tools(mcp)
        logger.info(f"Registered {len(registered_tools)} MCP tools: {', '.join(registered_tools)}")
        
        # Run the MCP server
        logger.info("Starting MCP server...")
        await mcp.run()
        
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down...")
    except Exception as e:
        logger.error(f"Unexpected error in main: {e}", exc_info=True)
    finally:
        # Clean shutdown
        await service.stop()
        logger.info("Service shutdown complete")

if __name__ == "__main__":
    asyncio.run(main())