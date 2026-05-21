"""
文件服务 - 处理文件相关的操作
"""

import base64
import logging
from typing import Optional, Tuple
from config import SERVICE_CONFIG

logger = logging.getLogger('FILE_SERVICE')

class FileService:
    @staticmethod
    def validate_file_type(file_type: str) -> bool:
        """验证文件类型是否允许"""
        return file_type in SERVICE_CONFIG['allowed_file_types']

    @staticmethod
    def validate_file_size(size: int) -> bool:
        """验证文件大小是否在限制范围内"""
        return 0 < size <= SERVICE_CONFIG['max_file_size']

    @staticmethod
    def encode_file_content(content: str) -> Optional[str]:
        """将文件内容编码为base64"""
        try:
            return base64.b64encode(content.encode()).decode()
        except Exception as e:
            logger.error(f"Error encoding file content: {e}")
            return None

    @staticmethod
    def decode_file_content(encoded_content: str) -> Optional[str]:
        """将base64编码的文件内容解码"""
        try:
            return base64.b64decode(encoded_content.encode()).decode()
        except Exception as e:
            logger.error(f"Error decoding file content: {e}")
            return None

    @staticmethod
    def get_file_extension(file_name: str) -> str:
        """获取文件扩展名"""
        return file_name.split('.')[-1].lower() if '.' in file_name else ''

    @staticmethod
    def validate_file_name(file_name: str) -> bool:
        """验证文件名是否合法"""
        # 检查文件名长度
        if not 1 <= len(file_name) <= 255:
            return False
        
        # 检查是否包含非法字符
        illegal_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
        return not any(char in file_name for char in illegal_chars)

    @staticmethod
    def get_file_info(file_name: str, file_type: str, size: int) -> Tuple[bool, Optional[str]]:
        """获取文件信息并验证"""
        if not FileService.validate_file_name(file_name):
            return False, "Invalid file name"
        
        if not FileService.validate_file_type(file_type):
            return False, "Unsupported file type"
        
        if not FileService.validate_file_size(size):
            return False, "File size exceeds limit"
        
        return True, None 