# 生产环境配置文件
import os
from typing import Dict, Any

class ProductionConfig:
    """生产环境配置管理"""
    
    def __init__(self):
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """加载配置"""
        return {
            # 服务端点配置
            "services": {
                "notepad": {
                    "url": os.getenv("NOTEPAD_SERVICE_URL", "http://localhost:8001"),
                    "endpoints": {
                        "notepad": "/notepad",
                        "email": "/email",
                        "health": "/health"
                    }
                },
                "websearch": {
                    "url": os.getenv("WEBSEARCH_SERVICE_URL", "http://localhost:8002"),
                    "endpoints": {
                        "search": "/search",
                        "health": "/health"
                    }
                }
            },
            
            # 请求配置
            "request": {
                "timeout": int(os.getenv("REQUEST_TIMEOUT", "30")),
                "max_retries": int(os.getenv("MAX_RETRIES", "3")),
                "retry_delay": float(os.getenv("RETRY_DELAY", "1.0"))
            },
            
            # 文件处理配置
            "file": {
                "max_size": int(os.getenv("MAX_FILE_SIZE", "25000000")),  # 25MB
                "allowed_types": [
                    "image/jpeg", "image/png", "image/gif", "image/webp",
                    "application/pdf", "application/msword", 
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "application/vnd.ms-excel",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "application/vnd.ms-powerpoint",
                    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    "text/plain", "text/csv", "application/json",
                    "application/zip", "application/x-zip-compressed",
                    "application/x-rar-compressed", "application/x-7z-compressed"
                ],
                "download_timeout": int(os.getenv("DOWNLOAD_TIMEOUT", "60"))
            },
            
            # 邮件配置
            "email": {
                "max_attachments": int(os.getenv("MAX_EMAIL_ATTACHMENTS", "10")),
                "max_total_size": int(os.getenv("MAX_EMAIL_SIZE", "25000000"))  # 25MB
            },
            
            # 搜索配置
            "search": {
                "default_depth": os.getenv("SEARCH_DEPTH", "basic"),
                "max_results": int(os.getenv("MAX_SEARCH_RESULTS", "10")),
                "timeout": int(os.getenv("SEARCH_TIMEOUT", "30"))
            },
            
            # 日志配置
            "logging": {
                "level": os.getenv("LOG_LEVEL", "INFO"),
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                "file": os.getenv("LOG_FILE", "websearch_enhanced.log")
            },
            
            # 安全配置
            "security": {
                "allowed_domains": os.getenv("ALLOWED_DOMAINS", "").split(",") if os.getenv("ALLOWED_DOMAINS") else [],
                "blocked_domains": os.getenv("BLOCKED_DOMAINS", "").split(",") if os.getenv("BLOCKED_DOMAINS") else [],
                "api_key": os.getenv("API_KEY", ""),
                "rate_limit": int(os.getenv("RATE_LIMIT", "100"))  # requests per minute
            }
        }
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        keys = key.split(".")
        value = self.config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def get_service_url(self, service: str, endpoint: str = "") -> str:
        """获取服务URL"""
        base_url = self.get(f"services.{service}.url")
        if not base_url:
            raise ValueError(f"Service {service} not configured")
        
        if endpoint:
            endpoint_path = self.get(f"services.{service}.endpoints.{endpoint}")
            if endpoint_path:
                return f"{base_url}{endpoint_path}"
            else:
                return f"{base_url}/{endpoint}"
        
        return base_url
    
    def is_file_allowed(self, content_type: str, size: int) -> tuple[bool, str]:
        """检查文件是否允许"""
        max_size = self.get("file.max_size")
        allowed_types = self.get("file.allowed_types")
        
        if size > max_size:
            return False, f"文件大小超过限制 ({max_size} bytes)"
        
        if content_type not in allowed_types:
            return False, f"不支持的文件类型: {content_type}"
        
        return True, "文件检查通过"
    
    def is_domain_allowed(self, url: str) -> tuple[bool, str]:
        """检查域名是否允许"""
        from urllib.parse import urlparse
        
        try:
            domain = urlparse(url).netloc.lower()
            
            blocked_domains = self.get("security.blocked_domains")
            if blocked_domains and domain in blocked_domains:
                return False, f"域名被阻止: {domain}"
            
            allowed_domains = self.get("security.allowed_domains")
            if allowed_domains and domain not in allowed_domains:
                return False, f"域名不在允许列表中: {domain}"
            
            return True, "域名检查通过"
            
        except Exception as e:
            return False, f"域名解析失败: {str(e)}"

# 全局配置实例
config = ProductionConfig()

# 配置验证函数
def validate_config() -> tuple[bool, list]:
    """验证配置"""
    errors = []
    
    # 检查必需的服务URL
    try:
        notepad_url = config.get_service_url("notepad")
        if not notepad_url.startswith("http"):
            errors.append("Invalid notepad service URL")
    except Exception as e:
        errors.append(f"Notepad service configuration error: {e}")
    
    # 检查文件大小限制
    max_file_size = config.get("file.max_size")
    if max_file_size <= 0:
        errors.append("Invalid max file size")
    
    # 检查超时设置
    timeout = config.get("request.timeout")
    if timeout <= 0:
        errors.append("Invalid request timeout")
    
    return len(errors) == 0, errors

# 环境变量模板
ENV_TEMPLATE = """
# 生产环境配置模板
# 复制此文件为 .env 并填入实际值

# 服务端点
NOTEPAD_SERVICE_URL=http://localhost:8001
WEBSEARCH_SERVICE_URL=http://localhost:8002

# 请求配置
REQUEST_TIMEOUT=30
MAX_RETRIES=3
RETRY_DELAY=1.0

# 文件处理
MAX_FILE_SIZE=25000000
DOWNLOAD_TIMEOUT=60

# 邮件配置
MAX_EMAIL_ATTACHMENTS=10
MAX_EMAIL_SIZE=25000000

# 搜索配置
SEARCH_DEPTH=basic
MAX_SEARCH_RESULTS=10
SEARCH_TIMEOUT=30

# 日志配置
LOG_LEVEL=INFO
LOG_FILE=websearch_enhanced.log

# 安全配置（可选）
# ALLOWED_DOMAINS=example.com,trusted-site.com
# BLOCKED_DOMAINS=malicious-site.com,spam-site.com
# API_KEY=your-api-key-here
# RATE_LIMIT=100
"""

if __name__ == "__main__":
    # 配置测试
    is_valid, errors = validate_config()
    
    if is_valid:
        print("✅ 配置验证通过")
        print(f"📍 Notepad服务: {config.get_service_url('notepad')}")
        print(f"⏱️  请求超时: {config.get('request.timeout')}秒")
        print(f"📁 最大文件大小: {config.get('file.max_size')} bytes")
    else:
        print("❌ 配置验证失败:")
        for error in errors:
            print(f"   - {error}")
    
    # 生成环境变量模板
    with open("xiaozhi-websearch/.env.template", "w", encoding="utf-8") as f:
        f.write(ENV_TEMPLATE)
    print("\n📝 已生成环境变量模板: .env.template")
