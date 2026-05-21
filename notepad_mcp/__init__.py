"""
记事本MCP服务包
"""

__version__ = '0.1.0'
__author__ = 'MCP Team'
__description__ = '提供记事本、提醒和文件存储功能的MCP服务'

from .models.reminder import (
    ReminderModel,
    ReminderType,
    ReminderPriority,
    ReminderStatus,
    NotifyMethod,
    RecurrenceModel,
    RecurrenceFrequency,
    ConditionModel
)

from .models.note import (
    NoteModel,
    NoteCategory,
    NotePriority
)

from .models.file import (
    FileModel,
    FileType
)

__all__ = [
    # 提醒相关
    'ReminderModel',
    'ReminderType',
    'ReminderPriority',
    'ReminderStatus',
    'NotifyMethod',
    'RecurrenceModel',
    'RecurrenceFrequency',
    'ConditionModel',
    
    # 笔记相关
    'NoteModel',
    'NoteCategory',
    'NotePriority',
    
    # 文件相关
    'FileModel',
    'FileType'
] 