"""
连接管理模块
负责管理SSH连接和会话
"""

import time
import logging
from typing import Dict, Optional
from config import SSH_CONFIG

class ConnectionManager:
    def __init__(self):
        self.connections: Dict[str, Dict] = {}
        self.logger = logging.getLogger('connection_manager')
        self.logger.setLevel(logging.INFO)
        
        # 创建文件处理器
        handler = logging.FileHandler('connection.log')
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

    def add_connection(self, connection_id: str, connection_info: Dict):
        """添加新连接"""
        if connection_id in self.connections:
            self.logger.warning(f"连接已存在: {connection_id}")
            return False
            
        connection_info['created_at'] = time.time()
        connection_info['last_activity'] = time.time()
        connection_info['error_count'] = 0
        
        self.connections[connection_id] = connection_info
        self.logger.info(f"添加新连接: {connection_id}")
        return True

    def remove_connection(self, connection_id: str):
        """移除连接"""
        if connection_id not in self.connections:
            self.logger.warning(f"连接不存在: {connection_id}")
            return False
            
        try:
            # 关闭连接
            connection = self.connections[connection_id]
            if 'client' in connection:
                connection['client'].close()
            
            del self.connections[connection_id]
            self.logger.info(f"移除连接: {connection_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"移除连接失败: {str(e)}")
            return False

    def update_activity(self, connection_id: str):
        """更新连接活动时间"""
        if connection_id not in self.connections:
            return False
            
        self.connections[connection_id]['last_activity'] = time.time()
        return True

    def record_error(self, connection_id: str, error: Exception):
        """记录连接错误"""
        if connection_id not in self.connections:
            return False
            
        connection = self.connections[connection_id]
        connection['error_count'] += 1
        connection['last_error'] = str(error)
        connection['last_error_time'] = time.time()
        
        self.logger.error(f"连接错误: {connection_id} - {str(error)}")
        
        # 检查是否需要关闭连接
        if connection['error_count'] >= SSH_CONFIG['max_retries']:
            self.logger.warning(f"连接错误次数过多，关闭连接: {connection_id}")
            self.remove_connection(connection_id)
            
        return True

    def cleanup_idle_connections(self):
        """清理空闲连接"""
        current_time = time.time()
        idle_timeout = SSH_CONFIG['timeout']
        
        for connection_id, connection in list(self.connections.items()):
            if current_time - connection['last_activity'] > idle_timeout:
                self.logger.info(f"清理空闲连接: {connection_id}")
                self.remove_connection(connection_id)

    def get_connection_info(self, connection_id: str) -> Optional[Dict]:
        """获取连接信息"""
        return self.connections.get(connection_id)

    def get_all_connections(self) -> Dict[str, Dict]:
        """获取所有连接信息"""
        return self.connections.copy()

# 创建全局连接管理器实例
connection_manager = ConnectionManager() 