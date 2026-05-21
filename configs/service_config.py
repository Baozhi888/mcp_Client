"""
服务配置模块
包含服务监控、资源限制等配置项
"""

# 服务监控配置
SERVICE_MONITOR_CONFIG = {
    'health_check_interval': 60,  # 健康检查间隔（秒）
    'resource_check_interval': 300,  # 资源检查间隔（秒）
    'error_window': 3600,  # 错误窗口期（秒）
    'max_errors': 10,  # 最大错误次数
    'max_auth_retries': 3,  # 最大认证重试次数
    'reconnect_delay': 5,  # 重连延迟（秒）
    'recovery_timeout': 300,  # 恢复超时（秒）
}

# 资源限制配置
RESOURCE_LIMITS = {
    'max_cpu_percent': 80,  # 最大CPU使用率
    'max_memory_percent': 80,  # 最大内存使用率
    'max_disk_percent': 90,  # 最大磁盘使用率
    'max_process_count': 100,  # 最大进程数
    'max_thread_count': 200,  # 最大线程数
    'max_file_handles': 1000,  # 最大文件句柄数
}

# SSH配置
SSH_CONFIG = {
    'timeout': 3600,  # SSH超时时间（秒）
    'max_retries': 3,  # 最大重试次数
    'keepalive_interval': 60,  # 保活间隔（秒）
}
