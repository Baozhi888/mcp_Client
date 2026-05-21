"""
主服务模块
整合所有功能模块，提供服务入口
"""

import os
import sys
import time
import signal
import logging
import threading
from typing import Optional
from config import SERVICE_MONITOR_CONFIG, LOG_CONFIG
from monitor import service_monitor
from connection_manager import connection_manager
from error_handler import error_handler

class MCPService:
    def __init__(self):
        self.running = False
        self.cleanup_thread: Optional[threading.Thread] = None
        
        # 设置日志
        self._setup_logging()
        
        # 注册信号处理器
        self._register_signal_handlers()
        
    def _setup_logging(self):
        """设置日志系统"""
        if not os.path.exists('logs'):
            os.makedirs('logs')
            
        logging.basicConfig(
            level=logging.INFO,
            format=LOG_CONFIG['log_format'],
            handlers=[
                logging.FileHandler(LOG_CONFIG['log_file']),
                logging.StreamHandler()
            ]
        )
        
        self.logger = logging.getLogger('mcp_service')
        
    def _register_signal_handlers(self):
        """注册信号处理器"""
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)
        
    def _handle_shutdown(self, signum, frame):
        """处理关闭信号"""
        self.logger.info(f"收到关闭信号: {signum}")
        self.stop()
        
    def start(self):
        """启动服务"""
        if self.running:
            self.logger.warning("服务已经在运行")
            return
            
        self.running = True
        self.logger.info("启动MCP服务")
        
        # 启动清理线程
        self.cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            daemon=True
        )
        self.cleanup_thread.start()
        
        try:
            # 主服务循环
            while self.running:
                # 检查服务健康状态
                if not service_monitor.check_health():
                    self.logger.error("服务健康检查失败")
                    self.stop()
                    break
                    
                # 检查资源使用情况
                if not service_monitor.check_resources():
                    self.logger.warning("资源使用率过高")
                    
                # 清理空闲连接
                connection_manager.cleanup_idle_connections()
                
                # 休眠一段时间
                time.sleep(1)
                
        except Exception as e:
            error_handler.handle_error(e)
            self.stop()
            
    def stop(self):
        """停止服务"""
        if not self.running:
            return
            
        self.logger.info("停止MCP服务")
        self.running = False
        
        # 关闭所有连接
        for connection_id in list(connection_manager.get_all_connections().keys()):
            connection_manager.remove_connection(connection_id)
            
        # 等待清理线程结束
        if self.cleanup_thread and self.cleanup_thread.is_alive():
            self.cleanup_thread.join(timeout=5)
            
    def _cleanup_loop(self):
        """清理循环"""
        while self.running:
            try:
                # 清理空闲连接
                connection_manager.cleanup_idle_connections()
                
                # 休眠一段时间
                time.sleep(SERVICE_MONITOR_CONFIG['health_check_interval'])
                
            except Exception as e:
                error_handler.handle_error(e)
                
def main():
    """主函数"""
    service = MCPService()
    service.start()
    
if __name__ == '__main__':
    main() 