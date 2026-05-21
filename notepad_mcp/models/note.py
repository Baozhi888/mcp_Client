"""
笔记模型 - 定义笔记相关的数据结构和验证规则
================================
Version: 0.1.0
Author: MCP Team
Created: 2024

功能描述:
---------
此模块定义了笔记相关的数据模型，包括笔记内容、标签、分类等。
提供数据验证和转换功能，确保笔记数据的完整性和正确性。
"""

from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum
import uuid
from pydantic import BaseModel, Field, field_validator

class NoteCategory(str, Enum):
    """笔记分类枚举"""
    WORK = "work"         # 工作
    PERSONAL = "personal" # 个人
    STUDY = "study"      # 学习
    OTHER = "other"      # 其他

class NotePriority(str, Enum):
    """笔记优先级枚举"""
    HIGH = "high"     # 高优先级
    MEDIUM = "medium" # 中优先级
    LOW = "low"       # 低优先级

class NoteModel(BaseModel):
    """笔记模型"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    content: str
    category: NoteCategory = NoteCategory.OTHER
    priority: NotePriority = NotePriority.MEDIUM
    tags: List[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    reminder_id: Optional[str] = None
    file_ids: List[str] = Field(default_factory=list)

    @field_validator('title')
    @classmethod
    def validate_title(cls, v):
        """验证标题"""
        if not v.strip():
            raise ValueError("Title cannot be empty")
        if len(v) > 200:
            raise ValueError("Title is too long")
        return v

    @field_validator('content')
    @classmethod
    def validate_content(cls, v):
        """验证内容"""
        if not v.strip():
            raise ValueError("Content cannot be empty")
        return v

    @field_validator('tags')
    @classmethod
    def validate_tags(cls, v):
        """验证标签"""
        if v:
            # 移除重复标签
            v = list(set(v))
            # 验证标签
            for tag in v:
                # 去除首尾空格
                tag = tag.strip()
                # 验证标签不为空
                if not tag:
                    raise ValueError("Tag cannot be empty")
                # 验证标签长度
                if len(tag) > 50:
                    raise ValueError(f"Tag '{tag}' is too long (max 50 characters)")
                # 验证标签不包含非法字符（允许中英文、数字、下划线、连字符）
                import re
                if not re.match(r'^[\w\u4e00-\u9fff\-]+$', tag):
                    raise ValueError(f"Tag '{tag}' contains invalid characters")
        return v

    def to_dict(self) -> Dict:
        """转换为字典"""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: Dict) -> 'NoteModel':
        """从字典创建实例"""
        return cls(**data)

    def update(self, data: Dict) -> None:
        """更新笔记"""
        for key, value in data.items():
            if hasattr(self, key):
                setattr(self, key, value)
        self.updated_at = datetime.now().isoformat()

    def add_tag(self, tag: str) -> None:
        """添加标签"""
        # 验证标签
        tag = tag.strip()
        if not tag:
            raise ValueError("Tag cannot be empty")
        if len(tag) > 50:
            raise ValueError(f"Tag '{tag}' is too long (max 50 characters)")
        # 验证标签不包含非法字符
        import re
        if not re.match(r'^[\w\u4e00-\u9fff\-]+$', tag):
            raise ValueError(f"Tag '{tag}' contains invalid characters")
        
        # 添加标签（避免重复）
        if tag not in self.tags:
            self.tags.append(tag)
            self.updated_at = datetime.now().isoformat()

    def remove_tag(self, tag: str) -> None:
        """移除标签"""
        tag = tag.strip()
        if tag in self.tags:
            self.tags.remove(tag)
            self.updated_at = datetime.now().isoformat()

    def add_file(self, file_id: str) -> None:
        """添加文件"""
        if file_id not in self.file_ids:
            self.file_ids.append(file_id)
            self.updated_at = datetime.now().isoformat()

    def remove_file(self, file_id: str) -> None:
        """移除文件"""
        if file_id in self.file_ids:
            self.file_ids.remove(file_id)
            self.updated_at = datetime.now().isoformat()

    def set_reminder(self, reminder_id: str) -> None:
        """设置提醒"""
        self.reminder_id = reminder_id
        self.updated_at = datetime.now().isoformat()

    def remove_reminder(self) -> None:
        """移除提醒"""
        self.reminder_id = None
        self.updated_at = datetime.now().isoformat() 