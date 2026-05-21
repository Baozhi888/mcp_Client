"""
提醒模型 - 定义提醒相关的数据结构和验证规则
================================
Version: 0.1.0
Author: MCP Team
Created: 2024

功能描述:
---------
此模块定义了提醒相关的数据模型，包括提醒类型、状态、优先级等。
提供数据验证和转换功能，确保提醒数据的完整性和正确性。
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from enum import Enum
import uuid
import json
from pydantic import BaseModel, Field, field_validator

# 定义北京时间时区（UTC+8）
BEIJING_TIMEZONE = timezone(timedelta(hours=8))

class ReminderType(str, Enum):
    """提醒类型枚举"""
    SCHEDULED = "scheduled"    # 定时提醒
    RECURRING = "recurring"    # 重复提醒
    CONDITIONAL = "conditional"  # 条件提醒
    TASK = "task"             # 任务提醒

class ReminderPriority(str, Enum):
    """提醒优先级枚举"""
    HIGH = "high"     # 高优先级
    MEDIUM = "medium" # 中优先级
    LOW = "low"       # 低优先级

class ReminderStatus(str, Enum):
    """提醒状态枚举"""
    PENDING = "pending"     # 待处理
    COMPLETED = "completed" # 已完成
    CANCELLED = "cancelled" # 已取消
    FAILED = "failed"      # 失败

class NotifyMethod(str, Enum):
    """通知方式枚举"""
    EMAIL = "email"         # 邮件通知
    SYSTEM = "system"       # 系统通知
    CUSTOM = "custom"       # 自定义通知

class RecurrenceFrequency(str, Enum):
    """重复频率枚举"""
    DAILY = "daily"     # 每天
    WEEKLY = "weekly"   # 每周
    MONTHLY = "monthly" # 每月

class RecurrenceModel(BaseModel):
    """重复规则模型"""
    frequency: RecurrenceFrequency
    interval: int = Field(default=1, ge=1)  # 间隔，默认为1
    days: Optional[List[str]] = None  # 每周的哪几天
    time: str = Field(default="00:00:00")  # 具体时间
    day: Optional[int] = Field(default=None, ge=1, le=31)  # 每月的哪一天

    @field_validator('time')
    @classmethod
    def validate_time(cls, v):
        """验证时间格式"""
        try:
            datetime.strptime(v, "%H:%M:%S")
            return v
        except ValueError:
            raise ValueError("Time must be in format HH:MM:SS")

    @field_validator('days')
    @classmethod
    def validate_days(cls, v, info):
        """验证日期"""
        values = info.data if info else {}
        if values.get('frequency') == RecurrenceFrequency.WEEKLY and not v:
            raise ValueError("Days are required for weekly recurrence")
        if v:
            valid_days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
            if not all(day.lower() in valid_days for day in v):
                raise ValueError(f"Invalid day. Must be one of {valid_days}")
        return v

class ConditionModel(BaseModel):
    """条件模型"""
    type: str
    task_id: Optional[str] = None
    parameters: Optional[Dict] = None

class ReminderModel(BaseModel):
    """提醒模型"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    content: str
    type: ReminderType
    remind_at: Optional[str] = None
    recurrence: Optional[RecurrenceModel] = None
    condition: Optional[ConditionModel] = None
    priority: ReminderPriority = ReminderPriority.MEDIUM
    notify_methods: List[NotifyMethod] = Field(default_factory=lambda: [NotifyMethod.EMAIL])
    created_at: str = Field(default_factory=lambda: datetime.now(BEIJING_TIMEZONE).isoformat())
    status: ReminderStatus = ReminderStatus.PENDING
    last_triggered: Optional[str] = None
    next_trigger: Optional[str] = None
    email_to: Optional[str] = None

    @field_validator('remind_at')
    @classmethod
    def validate_remind_at(cls, v, info):
        """验证提醒时间"""
        values = info.data if info else {}
        if values.get('type') == ReminderType.SCHEDULED and not v:
            raise ValueError("remind_at is required for scheduled reminders")
        if v:
            try:
                remind_time = datetime.fromisoformat(v)
                if remind_time.tzinfo is None:
                    remind_time = remind_time.replace(tzinfo=BEIJING_TIMEZONE)
                current_time = datetime.now(BEIJING_TIMEZONE)
                if remind_time <= current_time:
                    raise ValueError("Remind time must be in the future")
            except ValueError:
                raise ValueError("Invalid remind_at format")
        return v

    @field_validator('recurrence')
    @classmethod
    def validate_recurrence(cls, v, info):
        """验证重复规则"""
        values = info.data if info else {}
        if values.get('type') == ReminderType.RECURRING and not v:
            raise ValueError("recurrence is required for recurring reminders")
        return v

    @field_validator('condition')
    @classmethod
    def validate_condition(cls, v, info):
        """验证条件"""
        values = info.data if info else {}
        if values.get('type') == ReminderType.CONDITIONAL and not v:
            raise ValueError("condition is required for conditional reminders")
        return v

    @field_validator('email_to')
    @classmethod
    def validate_email(cls, v):
        """验证邮箱"""
        # 邮箱字段是可选的，如果没有提供，系统会使用默认邮箱
        return v

    def to_dict(self) -> Dict:
        """转换为字典"""
        data = self.model_dump()

        # 确保枚举值被序列化为字符串
        if 'type' in data and hasattr(data['type'], 'value'):
            data['type'] = data['type'].value
        if 'priority' in data and hasattr(data['priority'], 'value'):
            data['priority'] = data['priority'].value
        if 'status' in data and hasattr(data['status'], 'value'):
            data['status'] = data['status'].value
        if 'notify_methods' in data:
            data['notify_methods'] = [method.value if hasattr(method, 'value') else method
                                    for method in data['notify_methods']]

        # 序列化复杂对象为JSON字符串
        if 'recurrence' in data and data['recurrence'] is not None:
            if isinstance(data['recurrence'], dict):
                data['recurrence'] = json.dumps(data['recurrence'])
        if 'condition' in data and data['condition'] is not None:
            if isinstance(data['condition'], dict):
                data['condition'] = json.dumps(data['condition'])

        return data

    @classmethod
    def from_dict(cls, data: Dict) -> 'ReminderModel':
        """从字典创建实例"""
        # 创建数据副本以避免修改原始数据
        data = data.copy()

        # 处理枚举字段
        if 'type' in data and isinstance(data['type'], str):
            data['type'] = ReminderType(data['type'])
        if 'priority' in data and isinstance(data['priority'], str):
            data['priority'] = ReminderPriority(data['priority'])
        if 'status' in data and isinstance(data['status'], str):
            data['status'] = ReminderStatus(data['status'])
        if 'notify_methods' in data:
            if isinstance(data['notify_methods'], str):
                # 如果是JSON字符串，先解析
                try:
                    notify_methods = json.loads(data['notify_methods'])
                except (json.JSONDecodeError, TypeError):
                    notify_methods = data['notify_methods']
            else:
                notify_methods = data['notify_methods']

            # 转换为枚举
            if isinstance(notify_methods, list):
                data['notify_methods'] = [
                    NotifyMethod(method) if isinstance(method, str) else method
                    for method in notify_methods
                ]

        # 处理JSON字段
        if 'recurrence' in data and isinstance(data['recurrence'], str):
            try:
                data['recurrence'] = json.loads(data['recurrence'])
            except (json.JSONDecodeError, TypeError):
                data['recurrence'] = None
        if 'condition' in data and isinstance(data['condition'], str):
            try:
                data['condition'] = json.loads(data['condition'])
            except (json.JSONDecodeError, TypeError):
                data['condition'] = None

        return cls(**data)

    def should_trigger(self, now: datetime) -> bool:
        """检查是否应该触发"""
        if self.status != ReminderStatus.PENDING:
            return False

        if now.tzinfo is None:
            now = now.replace(tzinfo=BEIJING_TIMEZONE)

        if self.type == ReminderType.SCHEDULED:
            remind_time = datetime.fromisoformat(self.remind_at)
            if remind_time.tzinfo is None:
                remind_time = remind_time.replace(tzinfo=BEIJING_TIMEZONE)
            return remind_time <= now
        elif self.type == ReminderType.RECURRING:
            if not self.next_trigger:
                return False
            next_trigger_time = datetime.fromisoformat(self.next_trigger)
            if next_trigger_time.tzinfo is None:
                next_trigger_time = next_trigger_time.replace(tzinfo=BEIJING_TIMEZONE)
            return next_trigger_time <= now
        elif self.type == ReminderType.CONDITIONAL:
            # 条件提醒的触发逻辑由外部实现
            return False
        elif self.type == ReminderType.TASK:
            # 任务提醒的触发逻辑由外部实现
            return False
        return False

    def calculate_next_trigger(self, now: datetime) -> Optional[str]:
        """计算下次触发时间"""
        if self.type == ReminderType.SCHEDULED:
            return self.remind_at
        elif self.type == ReminderType.RECURRING and self.recurrence:
            return self._calculate_recurrence_next_trigger(now)
        return None

    def _calculate_recurrence_next_trigger(self, now: datetime) -> Optional[str]:
        """计算重复提醒的下次触发时间"""
        if not self.recurrence:
            return None

        if now.tzinfo is None:
            now = now.replace(tzinfo=BEIJING_TIMEZONE)

        frequency = self.recurrence.frequency
        interval = self.recurrence.interval
        time = self.recurrence.time

        if frequency == RecurrenceFrequency.DAILY:
            next_trigger = now.replace(
                hour=int(time[:2]),
                minute=int(time[3:5]),
                second=int(time[6:8])
            )
            if next_trigger <= now:
                next_trigger = next_trigger.replace(day=next_trigger.day + interval)
        elif frequency == RecurrenceFrequency.WEEKLY:
            if not self.recurrence.days:
                return None
            current_weekday = now.weekday()
            next_weekday = min(
                i for i, day in enumerate(self.recurrence.days)
                if day.lower() > ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'][current_weekday].lower()
            )
            days_ahead = next_weekday - current_weekday
            if days_ahead <= 0:
                days_ahead += 7 * interval
            next_trigger = now.replace(
                hour=int(time[:2]),
                minute=int(time[3:5]),
                second=int(time[6:8])
            )
            next_trigger = next_trigger.replace(day=next_trigger.day + days_ahead)
        elif frequency == RecurrenceFrequency.MONTHLY:
            day = self.recurrence.day or 1
            next_trigger = now.replace(
                day=day,
                hour=int(time[:2]),
                minute=int(time[3:5]),
                second=int(time[6:8])
            )
            if next_trigger <= now:
                if now.month == 12:
                    next_trigger = next_trigger.replace(year=now.year + 1, month=1)
                else:
                    next_trigger = next_trigger.replace(month=now.month + interval)
        else:
            return None

        return next_trigger.isoformat() 