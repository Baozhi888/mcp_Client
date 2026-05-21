"""
配置文件 - 包含所有服务配置项
"""

import os
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

# 获取当前脚本的目录
current_dir = os.path.dirname(os.path.abspath(__file__))
# 获取项目根目录 (notepad_mcp的上级目录)
project_root = os.path.dirname(current_dir)
# 构建根目录下的.env文件路径
root_env_path = os.path.join(project_root, '.env')

# 加载环境变量 - 优先从项目根目录的.env文件加载
if os.path.exists(root_env_path):
    load_dotenv(root_env_path, override=True)
    logger.info(f"Loaded .env from project root: {root_env_path}")
else:
    logger.warning(f"Root .env file not found at: {root_env_path}")

# 然后加载当前目录的.env文件（如果存在）
current_env = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
if os.path.exists(current_env):
    load_dotenv(current_env, override=True)

# 布尔环境变量解析辅助：容忍空值/空白并支持多种真值写法

def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    val = val.strip()
    if val == '':
        return default
    return val.lower() in ('1', 'true', 'yes', 'on')

# Cloudflare配置
CLOUDFLARE_CONFIG = {
    'api_token': os.getenv('CLOUDFLARE_API_TOKEN'),
    'account_id': os.getenv('CLOUDFLARE_ACCOUNT_ID'),
    'kv_namespace_id': os.getenv('KV_NAMESPACE_ID'),
    'd1_database_id': os.getenv('D1_DATABASE_ID')
}

# 调试信息：打印加载的环境变量值
logger.info(f"Loaded CLOUDFLARE_API_TOKEN: {CLOUDFLARE_CONFIG['api_token'] is not None}")
logger.info(f"Loaded CLOUDFLARE_ACCOUNT_ID: {CLOUDFLARE_CONFIG['account_id']}")
logger.info(f"Loaded KV_NAMESPACE_ID: {CLOUDFLARE_CONFIG['kv_namespace_id']}")
logger.info(f"Loaded D1_DATABASE_ID: {CLOUDFLARE_CONFIG['d1_database_id']}")

# Gmail配置
# 获取当前脚本的目录
current_dir = os.path.dirname(os.path.abspath(__file__))
default_cred_file = os.path.join(current_dir, '.google_key', 'gmail_credentials.json')
default_token_file = os.path.join(current_dir, '.google_key', 'token.json')

# 如果环境变量中有配置，优先使用环境变量
env_cred_file = os.getenv('GMAIL_API_CREDENTIALS_FILE')
env_token_file = os.getenv('TOKEN_PATH')

# 如果环境变量路径是相对路径且不存在，尝试相对于当前目录解析
if env_cred_file and not os.path.isabs(env_cred_file) and not os.path.exists(env_cred_file):
    env_cred_file = os.path.join(os.path.dirname(current_dir), env_cred_file)

if env_token_file and not os.path.isabs(env_token_file) and not os.path.exists(env_token_file):
    env_token_file = os.path.join(os.path.dirname(current_dir), env_token_file)

GMAIL_CONFIG = {
    'api_credentials_file': env_cred_file if env_cred_file and os.path.exists(env_cred_file) else default_cred_file,
    'token_path': env_token_file if env_token_file else default_token_file,
    'server_mode': _env_bool('SERVER_MODE', True),
    'max_emails_to_fetch': int(os.getenv('MAX_EMAILS_TO_FETCH', '20')),
    'reconnect_timeout': int(os.getenv('RECONNECT_TIMEOUT', '120')),
    'max_attachment_size': 25 * 1024 * 1024,  # 25MB
    'authorization_code': os.getenv('AUTHORIZATION_CODE', ''),
    'api_timeout': int(os.getenv('GMAIL_API_TIMEOUT', '60')), # 新增：Gmail API 调用超时时间
    'sender_name': os.getenv('GMAIL_SENDER_NAME', '').strip(),
    'sender_email': os.getenv('GMAIL_SENDER_EMAIL', '').strip(),
}

# 服务配置
SERVICE_CONFIG = {
    # 数据库配置
    'database': {
        'path': os.getenv('DATABASE_PATH', os.path.join(current_dir, 'data', 'notepad.db')),
        'pool_size': int(os.getenv('DB_POOL_SIZE', '5')),
        'max_connections': int(os.getenv('DB_MAX_CONNECTIONS', '20')),
        'connection_timeout': int(os.getenv('DB_CONNECTION_TIMEOUT', '30')),
        'enable_wal': os.getenv('DB_ENABLE_WAL', 'true').lower() == 'true',
        'backup_path': os.getenv('DB_BACKUP_PATH', os.path.join(current_dir, 'backup')),
        'auto_vacuum': os.getenv('DB_AUTO_VACUUM', 'true').lower() == 'true',
    },
    
    # 文件存储配置
    'max_file_size': int(os.getenv('MAX_FILE_SIZE', str(10 * 1024 * 1024)).split('#')[0].strip()),
    'allowed_file_types': [s.strip() for s in os.getenv('ALLOWED_FILE_TYPES', '').split(',')] if os.getenv('ALLOWED_FILE_TYPES') else [],
    
    # 提醒和邮件配置
    'reminder_check_interval': int(os.getenv('REMINDER_CHECK_INTERVAL', str(60)).split('#')[0].strip()),
    'enable_gmail_integration': _env_bool('ENABLE_GMAIL_INTEGRATION', True),
    'email_retry_count': int(os.getenv('EMAIL_RETRY_COUNT', '3')),
    'email_retry_delay': int(os.getenv('EMAIL_RETRY_DELAY', '5')),

    # 备份和优化配置
    'auto_backup_notes': _env_bool('AUTO_BACKUP_NOTES', True),
    'backup_interval': int(os.getenv('BACKUP_INTERVAL', '86400')),  # 默认24小时
    'smart_categorization': _env_bool('SMART_CATEGORIZATION', False),

    # 性能优化配置
    'cache_enabled': _env_bool('ENABLE_CACHE', True),
    'cache_ttl': int(os.getenv('CACHE_TTL', '3600')),
    'tag_cache_ttl': int(os.getenv('TAG_CACHE_TTL', '300')),  # 标签缓存TTL，默认5分钟
    'max_search_results': int(os.getenv('MAX_SEARCH_RESULTS', '100')),
    'search_timeout': int(os.getenv('SEARCH_TIMEOUT', '10')),

    # Redis配置
    'redis_host': os.getenv('MCP_REDIS_HOST', 'localhost'),
    'redis_port': int(os.getenv('MCP_REDIS_PORT', '6380')),
    'redis_db': int(os.getenv('MCP_REDIS_DB', '1')),
    'redis_password': os.getenv('MCP_REDIS_PASSWORD'),
    
    # 错误处理配置
    'max_retries': int(os.getenv('MAX_RETRIES', '3')),
    'retry_delay': int(os.getenv('RETRY_DELAY', '1')),
    'error_notification_email': os.getenv('ERROR_NOTIFICATION_EMAIL', ''),
}

logger.info(f"Loaded MAX_FILE_SIZE: {SERVICE_CONFIG['max_file_size']}")
logger.info(f"Loaded ALLOWED_FILE_TYPES: {SERVICE_CONFIG['allowed_file_types']}")
logger.info(f"Loaded REMINDER_CHECK_INTERVAL: {SERVICE_CONFIG['reminder_check_interval']}")

# 数据库表结构
DB_SCHEMA = {
    'notes': '''
        CREATE TABLE IF NOT EXISTS notes (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            content TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            category TEXT,
            priority TEXT,
            tags TEXT,
            reminder_id TEXT,
            file_ids TEXT
        )
    ''',
    'reminders': '''
        CREATE TABLE IF NOT EXISTS reminders (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            content TEXT,
            remind_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            type TEXT,
            recurrence TEXT,
            condition TEXT,
            priority TEXT,
            notify_methods TEXT,
            email_to TEXT,
            last_triggered_at TEXT,
            next_trigger_at TEXT
        )
    ''',
    'files': '''
        CREATE TABLE IF NOT EXISTS files (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            size INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            content_type TEXT,
            kv_key TEXT NOT NULL,
            note_id TEXT,
            metadata TEXT
        )
    '''
}

# 日志配置
LOG_CONFIG = {
    'level': os.getenv('LOG_LEVEL', 'INFO').split('#')[0].strip(),
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    'file': 'notepad_mcp.log',
    'encoding': 'utf-8' # 添加编码设置
}

def validate_config():
    """
    验证配置完整性
    包括必需的配置项、文件路径、目录权限等
    
    Returns:
        bool: 配置是否有效
    
    Raises:
        ConfigurationError: 当配置验证失败时抛出
    """
    from utils.error_handler import ConfigurationError
    errors = []
    
    # 验证Cloudflare配置
    cloudflare_keys = ['api_token', 'account_id', 'kv_namespace_id', 'd1_database_id']
    missing_keys = [key for key in cloudflare_keys if not CLOUDFLARE_CONFIG.get(key)]
    if missing_keys:
        errors.append(f"Missing required Cloudflare configuration: {', '.join(missing_keys)}")
    
    # 验证Gmail配置
    if SERVICE_CONFIG['enable_gmail_integration']:
        if not os.path.exists(GMAIL_CONFIG['api_credentials_file']):
            errors.append(f"Gmail credentials file not found: {GMAIL_CONFIG['api_credentials_file']}")
        
        token_dir = os.path.dirname(GMAIL_CONFIG['token_path'])
        if not os.path.exists(token_dir):
            try:
                os.makedirs(token_dir, exist_ok=True)
                logger.info(f"Created token directory: {token_dir}")
            except Exception as e:
                errors.append(f"Cannot create token directory: {str(e)}")
        
        # 验证Gmail配置参数
        if GMAIL_CONFIG['max_emails_to_fetch'] <= 0:
            errors.append("max_emails_to_fetch must be positive")
        if GMAIL_CONFIG['reconnect_timeout'] <= 0:
            errors.append("reconnect_timeout must be positive")
        if GMAIL_CONFIG['api_timeout'] <= 0:
            errors.append("api_timeout must be positive")
    
    # 验证数据库配置
    db_config = SERVICE_CONFIG['database']
    try:
        db_dir = os.path.dirname(db_config['path'])
        if not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            logger.info(f"Created database directory: {db_dir}")
        
        # 验证数据库目录是否可写
        test_file = os.path.join(db_dir, '.write_test')
        try:
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
        except Exception as e:
            errors.append(f"Database directory is not writable: {str(e)}")
        
        # 验证连接池配置
        if db_config['pool_size'] <= 0:
            errors.append("Database pool_size must be positive")
        if db_config['max_connections'] < db_config['pool_size']:
            errors.append("max_connections cannot be less than pool_size")
        if db_config['connection_timeout'] <= 0:
            errors.append("connection_timeout must be positive")
            
    except Exception as e:
        errors.append(f"Database directory validation failed: {str(e)}")
    
    # 验证文件存储配置
    if SERVICE_CONFIG['max_file_size'] <= 0:
        errors.append("max_file_size must be positive")
    
    # 验证提醒和邮件配置
    if SERVICE_CONFIG['reminder_check_interval'] <= 0:
        errors.append("reminder_check_interval must be positive")
    if SERVICE_CONFIG['email_retry_count'] <= 0:
        errors.append("email_retry_count must be positive")
    if SERVICE_CONFIG['email_retry_delay'] <= 0:
        errors.append("email_retry_delay must be positive")
    
    # 验证性能优化配置
    if SERVICE_CONFIG['cache_ttl'] <= 0:
        errors.append("cache_ttl must be positive")
    if SERVICE_CONFIG['max_search_results'] <= 0:
        errors.append("max_search_results must be positive")
    if SERVICE_CONFIG['search_timeout'] <= 0:
        errors.append("search_timeout must be positive")
    
    if errors:
        error_message = "\n".join(errors)
        logger.error(f"Configuration validation failed:\n{error_message}")
        raise ConfigurationError(
            message="Configuration validation failed",
            code="INVALID_CONFIG",
            details={"errors": errors}
        )
    
    logger.info("All configuration validations passed successfully")
    return True

# Only run validation if explicitly called
def check_configuration():
    """
    Run configuration validation. This function should be called by services that need full validation.
    Gmail authentication only needs basic Gmail configuration and does not need full validation.
    """
    if not validate_config():
        logger.error("Configuration validation failed")
    else:
        logger.info("Configuration validation successful")
