"""
LLM Models stub - provides minimal model definitions for optional LLM functionality
"""
from enum import Enum
from typing import Dict, Any
from dataclasses import dataclass


class ModelType(Enum):
    """LLM model types"""
    GPT = "gpt"
    CLAUDE = "claude"
    GEMINI = "gemini"


class ProcessingType(Enum):
    """Processing types"""
    ANALYSIS = "analysis"
    GENERATION = "generation"
    SUMMARIZATION = "summarization"
    CLASSIFICATION = "classification"


class ProcessingMode(Enum):
    """Processing modes"""
    SYNC = "sync"
    ASYNC = "async"
    BATCH = "batch"


class ProcessingPriority(Enum):
    """Processing priorities"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


@dataclass
class ProcessingRequest:
    """LLM processing request"""
    text: str
    model_type: ModelType = ModelType.GPT
    processing_type: ProcessingType = ProcessingType.ANALYSIS
    mode: ProcessingMode = ProcessingMode.SYNC
    priority: ProcessingPriority = ProcessingPriority.MEDIUM
    options: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.options is None:
            self.options = {}