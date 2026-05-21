"""
文件模型 - 定义文件相关的数据结构和验证规则
================================
Version: 0.1.0
Author: MCP Team
Created: 2024

功能描述:
---------
此模块定义了文件相关的数据模型，包括文件信息、类型、大小等。
提供数据验证和转换功能，确保文件数据的完整性和正确性。
"""

from datetime import datetime
from typing import Dict, Optional
from enum import Enum
import uuid
from pydantic import BaseModel, Field, field_validator

class FileType(str, Enum):
    """文件类型枚举"""
    TEXT = "text"           # 文本文件
    IMAGE = "image"         # 图片文件
    DOCUMENT = "document"   # 文档文件
    AUDIO = "audio"         # 音频文件
    VIDEO = "video"         # 视频文件
    OTHER = "other"         # 其他文件

class FileModel(BaseModel):
    """文件模型"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    type: FileType
    size: int
    content_type: str
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    kv_key: str = Field(default_factory=lambda: f"file_{uuid.uuid4()}")
    note_id: Optional[str] = None
    metadata: Dict = Field(default_factory=dict)

    @field_validator('created_at', 'updated_at')
    @classmethod
    def validate_datetime(cls, v):
        """验证时间格式"""
        try:
            datetime.fromisoformat(v)
            return v
        except ValueError:
            raise ValueError("Time must be in ISO 8601 format (YYYY-MM-DDTHH:MM:SS)")

    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        """验证文件名"""
        if not v.strip():
            raise ValueError("File name cannot be empty")
        if len(v) > 255:
            raise ValueError("File name is too long")
        return v

    @field_validator('size')
    @classmethod
    def validate_size(cls, v):
        """验证文件大小"""
        if v <= 0:
            raise ValueError("File size must be positive")
        if v > 100 * 1024 * 1024:  # 100MB
            raise ValueError("File size exceeds limit")
        return v

    @field_validator('content_type')
    @classmethod
    def validate_content_type(cls, v):
        """验证内容类型"""
        if not v.strip():
            raise ValueError("Content type cannot be empty")
        return v

    def to_dict(self) -> Dict:
        """转换为字典"""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: Dict) -> 'FileModel':
        """从字典创建实例"""
        return cls(**data)

    def update(self, data: Dict) -> None:
        """更新文件信息"""
        for key, value in data.items():
            if hasattr(self, key):
                setattr(self, key, value)
        self.updated_at = datetime.now().isoformat()

    def set_note(self, note_id: str) -> None:
        """设置关联笔记"""
        self.note_id = note_id
        self.updated_at = datetime.now().isoformat()

    def remove_note(self) -> None:
        """移除关联笔记"""
        self.note_id = None
        self.updated_at = datetime.now().isoformat()

    def add_metadata(self, key: str, value: str) -> None:
        """添加元数据"""
        self.metadata[key] = value
        self.updated_at = datetime.now().isoformat()

    def remove_metadata(self, key: str) -> None:
        """移除元数据"""
        if key in self.metadata:
            del self.metadata[key]
            self.updated_at = datetime.now().isoformat()

    def get_metadata(self, key: str) -> Optional[str]:
        """获取元数据"""
        return self.metadata.get(key)

    def clear_metadata(self) -> None:
        """清空元数据"""
        self.metadata.clear()
        self.updated_at = datetime.now().isoformat() 