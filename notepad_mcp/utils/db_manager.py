"""
数据库连接管理器
用于管理数据库连接池和连接生命周期
"""

import sqlite3
import asyncio
import logging
import threading
import queue
from typing import Optional, List, Dict
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class DatabaseConnectionPool:
    """数据库连接池"""
    
    def __init__(self, db_path: str, pool_size: int = 5, max_overflow: int = 10,
                 timeout: int = 30, enable_wal: bool = True):
        """
        初始化连接池
        
        Args:
            db_path: 数据库文件路径
            pool_size: 连接池基础大小
            max_overflow: 允许的最大额外连接数
            timeout: 获取连接的超时时间（秒）
            enable_wal: 是否启用WAL模式
        """
        self.db_path = db_path
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.timeout = timeout
        self.enable_wal = enable_wal
        
        # 连接池和计数器
        self._pool = queue.Queue(maxsize=pool_size)
        self._overflow = 0
        self._overflow_lock = threading.Lock()
        
        # 连接跟踪
        self._active_connections: Dict[int, datetime] = {}
        self._conn_lock = threading.Lock()
        
        # 初始化连接池
        for _ in range(pool_size):
            conn = self._create_connection()
            if conn:
                self._pool.put(conn)
    
    def _create_connection(self) -> Optional[sqlite3.Connection]:
        """创建新的数据库连接"""
        try:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            
            # 启用WAL模式
            if self.enable_wal:
                conn.execute("PRAGMA journal_mode=WAL")
            
            # 启用外键约束
            conn.execute("PRAGMA foreign_keys=ON")
            
            # 设置超时
            conn.execute(f"PRAGMA busy_timeout={self.timeout * 1000}")
            
            return conn
            
        except Exception as e:
            logger.error(f"Failed to create database connection: {e}")
            return None
    
    def get_connection(self) -> Optional[sqlite3.Connection]:
        """
        获取数据库连接
        
        Returns:
            sqlite3.Connection: 数据库连接对象
        """
        try:
            # 先尝试从连接池获取
            conn = self._pool.get(timeout=self.timeout)
            
            # 验证连接是否有效
            try:
                conn.execute("SELECT 1")
            except (sqlite3.OperationalError, sqlite3.ProgrammingError):
                # 连接已失效，创建新连接
                conn = self._create_connection()
            
            if conn:
                with self._conn_lock:
                    self._active_connections[id(conn)] = datetime.now()
            
            return conn
            
        except queue.Empty:
            # 连接池为空，尝试创建额外连接
            with self._overflow_lock:
                if self._overflow < self.max_overflow:
                    self._overflow += 1
                    conn = self._create_connection()
                    if conn:
                        with self._conn_lock:
                            self._active_connections[id(conn)] = datetime.now()
                        return conn
            
            logger.error("Failed to get database connection: pool exhausted")
            return None
    
    def return_connection(self, conn: sqlite3.Connection):
        """
        归还数据库连接
        
        Args:
            conn: 要归还的连接对象
        """
        if not conn:
            return
        
        conn_id = id(conn)
        
        try:
            # 移除活动连接记录
            with self._conn_lock:
                self._active_connections.pop(conn_id, None)
            
            # 验证连接是否仍然有效
            try:
                conn.execute("SELECT 1")
                # 如果连接池未满，归还连接
                try:
                    self._pool.put_nowait(conn)
                    return
                except queue.Full:
                    pass
            except (sqlite3.OperationalError, sqlite3.ProgrammingError):
                pass
            
            # 如果是溢出连接或连接无效，则关闭
            with self._overflow_lock:
                if self._overflow > 0:
                    self._overflow -= 1
            
            try:
                conn.close()
            except:
                pass
                
        except Exception as e:
            logger.error(f"Error returning database connection: {e}")
            try:
                conn.close()
            except:
                pass
    
    def cleanup_stale_connections(self, max_age: int = 3600):
        """
        清理过期连接
        
        Args:
            max_age: 连接最大存活时间（秒）
        """
        now = datetime.now()
        stale_conns = []
        
        # 识别过期连接
        with self._conn_lock:
            for conn_id, start_time in self._active_connections.items():
                if (now - start_time).total_seconds() > max_age:
                    stale_conns.append(conn_id)
        
        # 关闭过期连接
        for conn_id in stale_conns:
            with self._conn_lock:
                if conn_id in self._active_connections:
                    try:
                        conn = [c for c in self._pool.queue if id(c) == conn_id][0]
                        self.return_connection(conn)
                    except:
                        self._active_connections.pop(conn_id, None)
    
    def close_all(self):
        """关闭所有连接"""
        # 清空连接池
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                try:
                    conn.close()
                except:
                    pass
            except queue.Empty:
                break
        
        # 关闭所有活动连接
        with self._conn_lock:
            for conn_id in list(self._active_connections.keys()):
                try:
                    conn = [c for c in self._pool.queue if id(c) == conn_id][0]
                    conn.close()
                except:
                    pass
            self._active_connections.clear()
        
        # 重置溢出计数
        with self._overflow_lock:
            self._overflow = 0
    
    def get_status(self) -> Dict:
        """
        获取连接池状态
        
        Returns:
            Dict: 连接池状态信息
        """
        return {
            'pool_size': self.pool_size,
            'available_connections': self._pool.qsize(),
            'active_connections': len(self._active_connections),
            'overflow_connections': self._overflow,
            'max_overflow': self.max_overflow
        }

class DatabaseConnection:
    """数据库连接上下文管理器"""
    
    def __init__(self, pool: DatabaseConnectionPool):
        self.pool = pool
        self.conn = None
        self.cursor = None
    
    async def __aenter__(self):
        """进入上下文"""
        self.conn = self.pool.get_connection()
        if not self.conn:
            raise RuntimeError("Failed to get database connection")
        self.cursor = self.conn.cursor()
        return self.cursor
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """退出上下文"""
        if self.cursor:
            try:
                self.cursor.close()
            except:
                pass
        
        if exc_type is None:
            # 如果没有异常，提交事务
            try:
                self.conn.commit()
            except:
                pass
        else:
            # 有异常，回滚事务
            try:
                self.conn.rollback()
            except:
                pass
        
        # 归还连接
        if self.conn:
            self.pool.return_connection(self.conn)

# 全局连接池实例
_connection_pool: Optional[DatabaseConnectionPool] = None

def get_connection_pool(db_path: str, **kwargs) -> DatabaseConnectionPool:
    """
    获取数据库连接池实例
    
    Args:
        db_path: 数据库文件路径
        **kwargs: 连接池配置参数
    
    Returns:
        DatabaseConnectionPool: 连接池实例
    """
    global _connection_pool
    
    if _connection_pool is None:
        _connection_pool = DatabaseConnectionPool(db_path, **kwargs)
    
    return _connection_pool

async def execute_query(query: str, params: tuple = None) -> Dict:
    """
    执行数据库查询
    
    Args:
        query: SQL查询语句
        params: 查询参数
    
    Returns:
        Dict: 查询结果
    """
    if not _connection_pool:
        raise RuntimeError("Database connection pool not initialized")
    
    async with DatabaseConnection(_connection_pool) as cursor:
        try:
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            
            if query.strip().upper().startswith(('SELECT', 'PRAGMA')):
                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()
                result = [dict(zip(columns, row)) for row in rows]
                return {'success': True, 'results': result}
            else:
                return {'success': True, 'affected_rows': cursor.rowcount}
                
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            return {'success': False, 'error': str(e)}
