"""
配置验证工具
用于验证各个服务组件的配置是否正确
"""

import os
from typing import Dict, Tuple, List

def validate_gmail_config(config: Dict) -> Tuple[bool, List[str]]:
    """验证Gmail配置"""
    errors = []
    required_fields = ['credentials_path', 'token_path', 'scopes']
    
    for field in required_fields:
        if field not in config:
            errors.append(f"Missing required field: {field}")
    
    if 'credentials_path' in config and not os.path.exists(config['credentials_path']):
        errors.append(f"Credentials file not found at: {config['credentials_path']}")
    
    return not bool(errors), errors

def validate_service_config(config: Dict) -> Tuple[bool, List[str]]:
    """验证服务基础配置"""
    errors = []
    required_fields = ['host', 'port', 'debug', 'data_dir']
    
    for field in required_fields:
        if field not in config:
            errors.append(f"Missing required field: {field}")
    
    if 'port' in config:
        try:
            port = int(config['port'])
            if not (1024 <= port <= 65535):
                errors.append("Port must be between 1024 and 65535")
        except ValueError:
            errors.append("Port must be a valid integer")
            
    return not bool(errors), errors

def validate_cloudflare_config(config: Dict) -> Tuple[bool, List[str]]:
    """验证Cloudflare配置"""
    errors = []
    required_fields = ['account_id', 'namespace_id', 'database_id', 'api_token']
    
    for field in required_fields:
        if field not in config:
            errors.append(f"Missing required field: {field}")
            
    return not bool(errors), errors

def ensure_directories() -> List[str]:
    """确保必要的目录存在"""
    errors = []
    required_dirs = [
        'data',
        'logs',
        'cache',
        'temp'
    ]
    
    for dir_name in required_dirs:
        dir_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), dir_name)
        try:
            os.makedirs(dir_path, exist_ok=True)
        except Exception as e:
            errors.append(f"Failed to create directory {dir_path}: {str(e)}")
            
    return errors

def validate_all_configs(configs: Dict) -> Tuple[bool, Dict[str, List[str]]]:
    """验证所有配置"""
    validation_funcs = {
        'GMAIL_CONFIG': validate_gmail_config,
        'SERVICE_CONFIG': validate_service_config,
        'CLOUDFLARE_CONFIG': validate_cloudflare_config
    }
    
    all_errors = {}
    is_valid = True
    
    for config_name, config_data in configs.items():
        if config_name in validation_funcs:
            valid, errors = validation_funcs[config_name](config_data)
            if not valid:
                is_valid = False
                all_errors[config_name] = errors
                
    return is_valid, all_errors
