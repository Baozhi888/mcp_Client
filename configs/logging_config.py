import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime

def setup_logging(name, log_file=None, level=logging.INFO, log_dir=None):
    """配置日志系统，支持日志轮转
    
    Args:
        name: 服务名称，如 'notepad_mcp', 'server_mcp'
        log_file: 日志文件名，如果为None则根据服务名自动生成
        level: 日志级别
        log_dir: 日志目录（可选），不传则用默认logs目录
    """
    # 创建日志目录
    if log_dir is None:
        log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # 如果没有指定日志文件名，根据服务名生成
    if log_file is None:
        log_file = f"{name}_{datetime.now().strftime('%Y%m')}.log"
    
    log_path = os.path.join(log_dir, log_file)
    
    # 创建日志记录器
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # 清除现有的处理器
    if logger.handlers:
        logger.handlers.clear()
    
    # 创建 RotatingFileHandler
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    
    # 设置格式化器
    formatter = logging.Formatter(
        '[%(asctime)s] - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    
    # 添加处理器
    logger.addHandler(file_handler)
    
    # 同时输出到控制台
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    return logger
