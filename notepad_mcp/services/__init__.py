"""
Notepad MCP Services Package
"""

# 导入所有服务模块
from .file_service import FileService
from .kv_service import KVService
from .gmail_service import GmailService
from .redis_service import RedisServiceHandler
from .document_processor import DocumentProcessor, extract_document_content, get_file_type

__all__ = [
    'FileService',
    'KVService',
    'GmailService',
    'RedisServiceHandler',
    'DocumentProcessor',
    'extract_document_content',
    'get_file_type'
]