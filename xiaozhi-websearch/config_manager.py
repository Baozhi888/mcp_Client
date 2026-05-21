# 增强的配置管理器 - 兼容原有接口
import json
import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
import threading
from dotenv import load_dotenv

# 加载.env文件
load_dotenv()

logger = logging.getLogger(__name__)

# 原有配置路径，保持向后兼容
CONFIG_PATH = Path.home() / ".xiaozhi_mcp_config.json"

@dataclass
class ServiceConfig:
    """服务配置数据类"""
    # 原有配置保持兼容
    MCP_ENDPOINT: str = ""
    ZHIPU_API_KEY: str = ""

    # 其他搜索API密钥
    TAVILY_API_KEY: str = ""
    NEWS_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    GOOGLE_CX: str = ""
    BING_API_KEY: str = ""
    
    # 性能优化配置
    MAX_CONCURRENT_REQUESTS: int = 10
    REQUEST_TIMEOUT: int = 30
    MAX_RETRY_ATTEMPTS: int = 3
    CACHE_TTL: int = 3600
    MAX_MEMORY_USAGE_MB: int = 512
    MAX_CONTENT_SIZE: int = 10 * 1024 * 1024
    CONNECTION_POOL_SIZE: int = 20
    MAX_RESPONSE_SIZE: int = 8000
    CHUNK_SIZE: int = 8192
    
    # 缓存配置
    MAX_CACHE_SIZE_MB: int = 100
    CACHE_CLEANUP_INTERVAL: int = 3600
    
    # 断路器配置
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 5
    CIRCUIT_BREAKER_RESET_TIMEOUT: int = 60
    CIRCUIT_BREAKER_RECOVERY_THRESHOLD: int = 3
    
    # 日志配置
    LOG_LEVEL: str = "INFO"
    LOG_FILE_PATH: str = "/home/zhouzhou/mcp-calculator/logs/websearch_optimized.log"
    LOG_MAX_SIZE_MB: int = 10
    LOG_BACKUP_COUNT: int = 5
    
    # 健康检查配置
    HEALTH_CHECK_INTERVAL: int = 300
    MEMORY_WARNING_THRESHOLD: float = 0.8
    MEMORY_CRITICAL_THRESHOLD: float = 0.9

class EnhancedConfigManager:
    """增强的配置管理器"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.config = ServiceConfig()
            self.config_file_paths = [
                CONFIG_PATH,  # 保持原有路径优先
                "../.env",  # 项目根目录的 .env（相对于 xiaozhi-websearch 目录）
                "./.env",   # 当前目录的 .env
                "/home/zhouzhou/mcp-calculator/.env",
                "/home/zhouzhou/mcp-calculator/configs/websearch.json",
                "~/.websearch_config.json",
                "./config.json"
            ]
            self.initialized = True
            self._load_all_configs()
    
    def _load_all_configs(self):
        """加载所有配置源"""
        # 1. 加载配置文件
        self._load_from_files()
        
        # 2. 加载环境变量（优先级最高）
        self._load_from_env()
        
        # 3. 验证配置
        self._validate_config()
        
        logger.info("Enhanced configuration loaded successfully")
    
    def _load_from_files(self):
        """从配置文件加载"""
        for file_path in self.config_file_paths:
            expanded_path = Path(file_path).expanduser()
            
            if expanded_path.exists():
                try:
                    if expanded_path.suffix == '.json' or expanded_path.name.endswith('.json'):
                        self._load_json_config(expanded_path)
                    elif expanded_path.name == '.env':
                        self._load_env_file(expanded_path)
                    
                    logger.debug(f"Loaded config from: {expanded_path}")
                except Exception as e:
                    logger.warning(f"Failed to load config from {expanded_path}: {e}")
    
    def _load_json_config(self, file_path: Path):
        """加载JSON配置文件"""
        with open(file_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
        
        # 更新配置
        for key, value in config_data.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
            else:
                logger.debug(f"Unknown config key: {key}")
    
    def _load_env_file(self, file_path: Path):
        """加载.env文件"""
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip().strip('"\'')
                        
                        # 设置到配置对象
                        if hasattr(self.config, key):
                            # 类型转换
                            current_value = getattr(self.config, key)
                            if isinstance(current_value, int):
                                value = int(value)
                            elif isinstance(current_value, float):
                                value = float(value)
                            elif isinstance(current_value, bool):
                                value = value.lower() in ('true', '1', 'yes', 'on')
                            
                            setattr(self.config, key, value)
    
    def _load_from_env(self):
        """从环境变量加载配置"""
        env_mapping = {
            'MCP_ENDPOINT': 'MCP_ENDPOINT',
                'ZHIPU_API_KEY': 'ZHIPU_API_KEY',
            'WEBSEARCH_MAX_MEMORY': 'MAX_MEMORY_USAGE_MB',
            'WEBSEARCH_CACHE_TTL': 'CACHE_TTL',
            'WEBSEARCH_LOG_LEVEL': 'LOG_LEVEL',
            'WEBSEARCH_REQUEST_TIMEOUT': 'REQUEST_TIMEOUT',
            'WEBSEARCH_MAX_CONCURRENT': 'MAX_CONCURRENT_REQUESTS',
            # 添加其他搜索API密钥
            'TAVILY_API_KEY': 'TAVILY_API_KEY',
            'NEWS_API_KEY': 'NEWS_API_KEY',
            'GOOGLE_API_KEY': 'GOOGLE_API_KEY',
            'GOOGLE_CX': 'GOOGLE_CX',
            'BING_API_KEY': 'BING_API_KEY',
        }
        
        for env_key, config_key in env_mapping.items():
            env_value = os.getenv(env_key)
            if env_value and hasattr(self.config, config_key):
                # 类型转换
                current_value = getattr(self.config, config_key)
                if isinstance(current_value, int):
                    env_value = int(env_value)
                elif isinstance(current_value, float):
                    env_value = float(env_value)
                elif isinstance(current_value, bool):
                    env_value = env_value.lower() in ('true', '1', 'yes', 'on')
                
                setattr(self.config, config_key, env_value)
                logger.debug(f"Set {config_key} from environment: {env_value}")
    
    def _validate_config(self):
        """验证配置的有效性"""
        errors = []
        
        # 验证必需的配置
        if not self.config.ZHIPU_API_KEY:
            errors.append("ZHIPU_API_KEY is required")
        
        # 验证数值范围
        if self.config.MAX_MEMORY_USAGE_MB < 64:
            errors.append("MAX_MEMORY_USAGE_MB must be at least 64MB")
        
        if self.config.REQUEST_TIMEOUT < 5:
            errors.append("REQUEST_TIMEOUT must be at least 5 seconds")
        
        if self.config.CACHE_TTL < 60:
            errors.append("CACHE_TTL must be at least 60 seconds")
        
        # 验证并创建日志目录
        log_dir = Path(self.config.LOG_FILE_PATH).parent
        if not log_dir.exists():
            try:
                log_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"Created log directory: {log_dir}")
            except Exception as e:
                errors.append(f"Cannot create log directory {log_dir}: {e}")
        
        if errors:
            error_msg = "Configuration validation failed:\n" + "\n".join(f"- {error}" for error in errors)
            logger.error(error_msg)
            raise ValueError(error_msg)
    
    def get_config_dict(self) -> Dict[str, Any]:
        """获取配置字典（向后兼容）"""
        return asdict(self.config)
    
    def update_config(self, **kwargs) -> bool:
        """动态更新配置"""
        try:
            for key, value in kwargs.items():
                if hasattr(self.config, key):
                    old_value = getattr(self.config, key)
                    setattr(self.config, key, value)
                    logger.info(f"Config updated: {key} = {value} (was: {old_value})")
                else:
                    logger.warning(f"Attempted to set unknown config key: {key}")
                    return False
            
            # 重新验证配置
            self._validate_config()
            return True
        except Exception as e:
            logger.error(f"Failed to update config: {e}")
            return False
    
    def save_config_to_file(self, file_path: Optional[str] = None) -> bool:
        """保存当前配置到文件"""
        if not file_path:
            file_path = str(CONFIG_PATH)
        
        try:
            # 确保目录存在
            Path(file_path).parent.mkdir(parents=True, exist_ok=True)
            
            # 保存配置
            config_dict = asdict(self.config)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(config_dict, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Config saved to: {file_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save config to {file_path}: {e}")
            return False

# 全局增强配置管理器实例
_enhanced_config_manager = None

def get_enhanced_config_manager() -> EnhancedConfigManager:
    """获取增强配置管理器实例"""
    global _enhanced_config_manager
    if _enhanced_config_manager is None:
        _enhanced_config_manager = EnhancedConfigManager()
    return _enhanced_config_manager

# 向后兼容的原有接口
def load_config() -> Dict[str, Any]:
    """向后兼容的配置加载函数"""
    try:
        manager = get_enhanced_config_manager()
        config_dict = manager.get_config_dict()
        
        # 保持原有的字典格式，主要字段向后兼容
        return {
            "MCP_ENDPOINT": config_dict.get("MCP_ENDPOINT", ""),
            "ZHIPU_API_KEY": config_dict.get("ZHIPU_API_KEY", ""),
            # 扩展字段
            **config_dict
        }
    except Exception as e:
        logger.error(f"Failed to load enhanced config, falling back to default: {e}")
        # 失败时仍优先使用 .env/环境变量，避免回退到硬编码凭据
        return {
            "MCP_ENDPOINT": os.getenv("MCP_ENDPOINT", ""),
            "ZHIPU_API_KEY": os.getenv("ZHIPU_API_KEY", ""),
        }

def save_config(config: Dict[str, Any]):
    """向后兼容的配置保存函数"""
    try:
        manager = get_enhanced_config_manager()
        
        # 更新管理器中的配置
        for key, value in config.items():
            if hasattr(manager.config, key):
                setattr(manager.config, key, value)
        
        # 保存到文件
        manager.save_config_to_file()
    except Exception as e:
        logger.error(f"Failed to save enhanced config, using basic save: {e}")
        # 失败时使用原有方式保存
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)

# 新增的增强配置函数
def load_enhanced_config() -> Dict[str, Any]:
    """加载增强配置"""
    return load_config()

def get_performance_config() -> Dict[str, Any]:
    """获取性能相关配置"""
    config = load_config()
    return {
        'MAX_CONCURRENT_REQUESTS': config.get('MAX_CONCURRENT_REQUESTS', 10),
        'REQUEST_TIMEOUT': config.get('REQUEST_TIMEOUT', 30),
        'MAX_RETRY_ATTEMPTS': config.get('MAX_RETRY_ATTEMPTS', 3),
        'CACHE_TTL': config.get('CACHE_TTL', 3600),
        'MAX_MEMORY_USAGE_MB': config.get('MAX_MEMORY_USAGE_MB', 512),
        'MAX_CONTENT_SIZE': config.get('MAX_CONTENT_SIZE', 10 * 1024 * 1024),
        'CONNECTION_POOL_SIZE': config.get('CONNECTION_POOL_SIZE', 20),
        'MAX_RESPONSE_SIZE': config.get('MAX_RESPONSE_SIZE', 8000),
        'CHUNK_SIZE': config.get('CHUNK_SIZE', 8192),
    }

def get_cache_config() -> Dict[str, Any]:
    """获取缓存相关配置"""
    config = load_config()
    return {
        'MAX_CACHE_SIZE_MB': config.get('MAX_CACHE_SIZE_MB', 100),
        'CACHE_CLEANUP_INTERVAL': config.get('CACHE_CLEANUP_INTERVAL', 3600),
        'CACHE_TTL': config.get('CACHE_TTL', 3600),
    }

def get_circuit_breaker_config() -> Dict[str, Any]:
    """获取断路器相关配置"""
    config = load_config()
    return {
        'FAILURE_THRESHOLD': config.get('CIRCUIT_BREAKER_FAILURE_THRESHOLD', 5),
        'RESET_TIMEOUT': config.get('CIRCUIT_BREAKER_RESET_TIMEOUT', 60),
        'RECOVERY_THRESHOLD': config.get('CIRCUIT_BREAKER_RECOVERY_THRESHOLD', 3),
    }
