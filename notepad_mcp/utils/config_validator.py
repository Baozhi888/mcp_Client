"""
配置验证工具
用于验证各个服务组件的配置是否正确
"""

import os
import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

class ConfigValidationError(Exception):
    """配置验证错误"""
    pass

def validate_gmail_config(config: Dict) -> Tuple[bool, List[str]]:
    """
    验证Gmail配置是否正确
    
    Args:
        config: Gmail配置字典
    
    Returns:
        (is_valid, errors): 配置是否有效及错误信息列表
    """
    errors = []
    
    # 检查必需文件
    required_files = {
        'api_credentials_file': 'Gmail API凭证文件',
        'token_path': 'Gmail Token文件'
    }
    
    for key, desc in required_files.items():
        file_path = config.get(key)
        if not file_path:
            errors.append(f"缺少{desc}路径配置")
            continue
            
        if not os.path.exists(file_path):
            errors.append(f"{desc}不存在: {file_path}")
            # 检查目录是否存在
            dir_path = os.path.dirname(file_path)
            if not os.path.exists(dir_path):
                errors.append(f"{desc}的目录不存在: {dir_path}")

    # 检查必需的配置项
    required_configs = {
        'server_mode': 'Gmail服务模式',
        'max_emails_to_fetch': '最大获取邮件数',
        'reconnect_timeout': '重连超时时间',
        'max_attachment_size': '最大附件大小',
        'api_timeout': 'API超时时间'
    }
    
    for key, desc in required_configs.items():
        if key not in config:
            errors.append(f"缺少{desc}配置项")
            continue
            
        # 类型检查
        if key in ['max_emails_to_fetch', 'reconnect_timeout', 'max_attachment_size', 'api_timeout']:
            if not isinstance(config[key], int) or config[key] <= 0:
                errors.append(f"{desc}必须是正整数")
    
    # 检查授权码（在服务器模式下必需）
    if config.get('server_mode') and not config.get('authorization_code'):
        errors.append("服务器模式下需要提供授权码")
    
    return len(errors) == 0, errors

def validate_database_config(config: Dict) -> Tuple[bool, List[str]]:
    """
    验证数据库配置是否正确
    
    Args:
        config: 数据库配置字典
    
    Returns:
        (is_valid, errors): 配置是否有效及错误信息列表
    """
    errors = []
    
    # 检查数据库路径
    db_path = config.get('path')
    if not db_path:
        errors.append("缺少数据库路径配置")
    else:
        # 检查数据库目录是否存在
        db_dir = os.path.dirname(db_path)
        if not os.path.exists(db_dir):
            try:
                os.makedirs(db_dir, exist_ok=True)
                logger.info(f"已创建数据库目录: {db_dir}")
            except Exception as e:
                errors.append(f"无法创建数据库目录: {e}")
    
    # 检查连接池配置
    pool_configs = {
        'pool_size': '连接池大小',
        'max_connections': '最大连接数',
        'connection_timeout': '连接超时时间'
    }
    
    for key, desc in pool_configs.items():
        value = config.get(key)
        if not value:
            errors.append(f"缺少{desc}配置")
        elif not isinstance(value, int) or value <= 0:
            errors.append(f"{desc}必须是正整数")
            
    # 验证最大连接数必须大于连接池大小
    if config.get('max_connections', 0) <= config.get('pool_size', 0):
        errors.append("最大连接数必须大于连接池大小")
    
    # 检查备份路径
    backup_path = config.get('backup_path')
    if backup_path:
        if not os.path.exists(backup_path):
            try:
                os.makedirs(backup_path, exist_ok=True)
                logger.info(f"已创建备份目录: {backup_path}")
            except Exception as e:
                errors.append(f"无法创建备份目录: {e}")
    
    return len(errors) == 0, errors

def validate_service_config(config: Dict) -> Tuple[bool, List[str]]:
    """
    验证服务配置是否正确
    
    Args:
        config: 服务配置字典
    
    Returns:
        (is_valid, errors): 配置是否有效及错误信息列表
    """
    errors = []
    
    # 数据库配置验证
    if 'database' not in config:
        errors.append("缺少数据库配置部分")
    else:
        is_valid, db_errors = validate_database_config(config['database'])
        errors.extend(db_errors)
    
    # 文件配置验证
    if 'max_file_size' not in config:
        errors.append("缺少最大文件大小配置")
    elif not isinstance(config['max_file_size'], int) or config['max_file_size'] <= 0:
        errors.append("最大文件大小必须是正整数")
    
    # 性能配置验证
    if config.get('cache_enabled'):
        if 'cache_ttl' not in config:
            errors.append("启用缓存时必须配置TTL")
        elif not isinstance(config['cache_ttl'], int) or config['cache_ttl'] <= 0:
            errors.append("缓存TTL必须是正整数")
    
    # 重试配置验证
    retry_configs = {
        'max_retries': '最大重试次数',
        'retry_delay': '重试延迟时间'
    }
    
    for key, desc in retry_configs.items():
        value = config.get(key)
        if value is None:
            errors.append(f"缺少{desc}配置")
        elif not isinstance(value, int) or value < 0:
            errors.append(f"{desc}必须是非负整数")
    
    return len(errors) == 0, errors

def validate_cloudflare_config(config: Dict) -> Tuple[bool, List[str]]:
    """
    验证Cloudflare配置是否正确
    
    Args:
        config: Cloudflare配置字典
    
    Returns:
        (is_valid, errors): 配置是否有效及错误信息列表
    """
    errors = []
    
    required_configs = {
        'api_token': 'API Token',
        'account_id': '账户ID',
        'kv_namespace_id': 'KV命名空间ID',
        'd1_database_id': 'D1数据库ID'
    }
    
    for key, desc in required_configs.items():
        if not config.get(key):
            errors.append(f"缺少{desc}配置")
            
    return len(errors) == 0, errors

def validate_all_configs(configs: Dict) -> Tuple[bool, Dict[str, List[str]]]:
    """
    验证所有配置
    
    Args:
        configs: 包含所有配置的字典
    
    Returns:
        (is_valid, errors_by_section): 配置是否全部有效及各部分的错误信息
    """
    all_errors = {}
    
    # 验证Gmail配置
    is_valid, errors = validate_gmail_config(configs.get('GMAIL_CONFIG', {}))
    if errors:
        all_errors['gmail'] = errors
    
    # 验证服务配置
    is_valid, errors = validate_service_config(configs.get('SERVICE_CONFIG', {}))
    if errors:
        all_errors['service'] = errors
    
    # 验证Cloudflare配置
    is_valid, errors = validate_cloudflare_config(configs.get('CLOUDFLARE_CONFIG', {}))
    if errors:
        all_errors['cloudflare'] = errors
    
    return len(all_errors) == 0, all_errors

def ensure_directories() -> List[str]:
    """
    确保所有必需的目录存在
    
    Returns:
        errors: 创建目录过程中的错误信息列表
    """
    errors = []
    required_dirs = [
        ('data', '数据目录'),
        ('logs', '日志目录'),
        ('backup', '备份目录'),
        ('.google_key', 'Google认证目录')
    ]
    
    for dir_name, desc in required_dirs:
        dir_path = os.path.join(os.path.dirname(__file__), '..', dir_name)
        if not os.path.exists(dir_path):
            try:
                os.makedirs(dir_path, exist_ok=True)
                logger.info(f"已创建{desc}: {dir_path}")
            except Exception as e:
                errors.append(f"创建{desc}失败: {e}")
    
    return errors
