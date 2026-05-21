"""
数据库优化工具
用于创建和维护数据库索引
"""

import sqlite3
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

INDEXES = {
    'notes': [
        ('idx_notes_title', 'CREATE INDEX IF NOT EXISTS idx_notes_title ON notes(title)'),
        ('idx_notes_category', 'CREATE INDEX IF NOT EXISTS idx_notes_category ON notes(category)'),
        ('idx_notes_created_at', 'CREATE INDEX IF NOT EXISTS idx_notes_created_at ON notes(created_at)'),
        ('idx_notes_tags', 'CREATE INDEX IF NOT EXISTS idx_notes_tags ON notes(tags)'),
        ('idx_notes_reminder_id', 'CREATE INDEX IF NOT EXISTS idx_notes_reminder_id ON notes(reminder_id)')
    ],
    'reminders': [
        ('idx_reminders_status', 'CREATE INDEX IF NOT EXISTS idx_reminders_status ON reminders(status)'),
        ('idx_reminders_remind_at', 'CREATE INDEX IF NOT EXISTS idx_reminders_remind_at ON reminders(remind_at)'),
        ('idx_reminders_next_trigger', 'CREATE INDEX IF NOT EXISTS idx_reminders_next_trigger ON reminders(next_trigger_at)'),
        ('idx_reminders_priority', 'CREATE INDEX IF NOT EXISTS idx_reminders_priority ON reminders(priority)')
    ],
    'files': [
        ('idx_files_name', 'CREATE INDEX IF NOT EXISTS idx_files_name ON files(name)'),
        ('idx_files_type', 'CREATE INDEX IF NOT EXISTS idx_files_type ON files(type)'),
        ('idx_files_note_id', 'CREATE INDEX IF NOT EXISTS idx_files_note_id ON files(note_id)'),
        ('idx_files_created_at', 'CREATE INDEX IF NOT EXISTS idx_files_created_at ON files(created_at)')
    ]
}

async def create_indexes(db_path: str) -> Dict[str, List[str]]:
    """
    创建数据库索引
    
    Args:
        db_path: 数据库文件路径
    
    Returns:
        errors_by_table: 每个表的错误信息列表
    """
    errors_by_table = {}
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 为每个表创建索引
        for table, indexes in INDEXES.items():
            table_errors = []
            for index_name, create_sql in indexes:
                try:
                    cursor.execute(create_sql)
                    logger.info(f"Created index {index_name} for table {table}")
                except Exception as e:
                    error_msg = f"Failed to create index {index_name}: {str(e)}"
                    table_errors.append(error_msg)
                    logger.error(error_msg)
            
            if table_errors:
                errors_by_table[table] = table_errors
        
        conn.commit()
        
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        errors_by_table['connection'] = [str(e)]
        
    finally:
        if 'conn' in locals():
            conn.close()
    
    return errors_by_table

async def optimize_database(db_path: str) -> Dict[str, any]:
    """
    优化数据库
    
    Args:
        db_path: 数据库文件路径
    
    Returns:
        result: 优化结果信息
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 执行VACUUM
        cursor.execute("VACUUM")
        
        # 收集统计信息
        cursor.execute("ANALYZE")
        
        # 获取数据库统计信息
        cursor.execute("PRAGMA page_size")
        page_size = cursor.fetchone()[0]
        
        cursor.execute("PRAGMA page_count")
        page_count = cursor.fetchone()[0]
        
        # 计算数据库大小
        db_size = page_size * page_count
        
        # 获取表统计信息
        stats = {}
        for table in INDEXES.keys():
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            row_count = cursor.fetchone()[0]
            stats[table] = {
                'row_count': row_count
            }
            
            # 获取索引信息
            cursor.execute(f"PRAGMA index_list({table})")
            indexes = cursor.fetchall()
            stats[table]['index_count'] = len(indexes)
        
        return {
            "success": True,
            "database_size": db_size,
            "page_size": page_size,
            "page_count": page_count,
            "tables": stats
        }
        
    except Exception as e:
        logger.error(f"Database optimization failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }
        
    finally:
        if 'conn' in locals():
            conn.close()

async def verify_database_integrity(db_path: str) -> Dict[str, any]:
    """
    验证数据库完整性
    
    Args:
        db_path: 数据库文件路径
    
    Returns:
        result: 验证结果信息
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 检查数据库完整性
        cursor.execute("PRAGMA integrity_check")
        integrity_result = cursor.fetchall()
        
        # 检查外键约束
        cursor.execute("PRAGMA foreign_key_check")
        fk_result = cursor.fetchall()
        
        # 获取表结构信息
        tables_info = {}
        for table in INDEXES.keys():
            cursor.execute(f"PRAGMA table_info({table})")
            columns = cursor.fetchall()
            tables_info[table] = columns
        
        return {
            "success": True,
            "integrity_check": "ok" if integrity_result == [("ok",)] else integrity_result,
            "foreign_key_violations": len(fk_result),
            "tables_info": tables_info
        }
        
    except Exception as e:
        logger.error(f"Database integrity check failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }
        
    finally:
        if 'conn' in locals():
            conn.close()
