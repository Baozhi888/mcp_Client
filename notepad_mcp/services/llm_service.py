"""
LLM Service stub - provides minimal interface for optional LLM functionality
"""
from typing import Dict, Any


class LLMService:
    """Stub LLM service for optional functionality"""
    
    def __init__(self):
        self._initialized = False
    
    def is_initialized(self) -> bool:
        return self._initialized
    
    async def initialize(self) -> bool:
        self._initialized = True
        return True
    
    async def process_text(self, text: str, **options) -> Dict[str, Any]:
        return {"success": False, "error": "LLM service not implemented"}
    
    async def analyze_content(self, text: str) -> Dict[str, Any]:
        return {"success": False, "error": "LLM service not implemented"}
    
    async def generate_tags(self, text: str) -> list:
        return []
    
    async def categorize_content(self, text: str) -> str:
        return "未分类"
    
    async def generate_title(self, text: str) -> str:
        return "自动生成标题"
    
    async def extract_summary(self, text: str, max_length: int = 200) -> str:
        return text[:max_length] + "..." if len(text) > max_length else text


def get_llm_service() -> LLMService:
    """Get LLM service instance"""
    return LLMService()