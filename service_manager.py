#!/usr/bin/env python3
"""
智能服务管理器 - 管理多个MCP服务的启动和监控
=======================================
Version: 1.0.0
Author: MCP Team
"""

import os
import sys
import subprocess
import time
import signal
import logging
import threading
import asyncio
from pathlib import Path
from typing import Dict, List, Optional
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('service_manager')

class ServiceManager:
    """智能服务管理器"""
    
    def __init__(self):
        self.services: Dict[str, subprocess.Popen] = {}
        self.service_logs: Dict[str, List[str]] = {}
        self.service_threads: Dict[str, threading.Thread] = {}
        self.running = False
        self.max_restarts = 5
        self.restart_delay = 10  # 秒
        
    def get_service_scripts(self) -> List[str]:
        """获取需要启动的服务脚本"""
        scripts_str = os.environ.get('MCP_SCRIPTS', '')
        if not scripts_str:
            logger.warning("MCP_SCRIPTS environment variable not set")
            return []
        
        scripts = scripts_str.split()
        logger.info(f"Found {len(scripts)} services to manage: {scripts}")
        return scripts
    
    def start_service(self, script_path: str) -> bool:
        """启动单个服务"""
        try:
            script_name = Path(script_path).stem
            
            # 检查服务是否已经在运行
            if script_name in self.services and self.services[script_name].poll() is None:
                logger.info(f"Service {script_name} is already running")
                return True
            
            logger.info(f"Starting service: {script_name}")
            
            # 启动服务进程
            process = subprocess.Popen(
                [sys.executable, script_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8'
            )
            
            self.services[script_name] = process
            self.service_logs[script_name] = []
            
            # 启动日志监控线程
            log_thread = threading.Thread(
                target=self.monitor_service_logs,
                args=(script_name, process),
                daemon=True
            )
            log_thread.start()
            self.service_threads[script_name] = log_thread
            
            logger.info(f"Service {script_name} started (PID: {process.pid})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start service {script_path}: {e}")
            return False
    
    def monitor_service_logs(self, service_name: str, process: subprocess.Popen):
        """监控服务日志"""
        while True:
            try:
                # 监控标准输出
                output = process.stdout.readline()
                if output:
                    self.service_logs[service_name].append(f"[STDOUT] {output.strip()}")
                    # 保持日志数量在合理范围内
                    if len(self.service_logs[service_name]) > 1000:
                        self.service_logs[service_name] = self.service_logs[service_name][-500:]
                
                # 监控错误输出
                error = process.stderr.readline()
                if error:
                    self.service_logs[service_name].append(f"[ERROR] {error.strip()}")
                    # 保持日志数量在合理范围内
                    if len(self.service_logs[service_name]) > 1000:
                        self.service_logs[service_name] = self.service_logs[service_name][-500:]
                
                # 检查进程是否结束
                if process.poll() is not None:
                    logger.warning(f"Service {service_name} has exited with code: {process.returncode}")
                    break
                    
                time.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Error monitoring logs for {service_name}: {e}")
                break
    
    def restart_service(self, service_name: str) -> bool:
        """重启服务"""
        try:
            # 停止现有服务
            if service_name in self.services:
                process = self.services[service_name]
                if process.poll() is None:
                    logger.info(f"Stopping service {service_name}")
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        logger.warning(f"Force killing service {service_name}")
                        process.kill()
                
                del self.services[service_name]
                if service_name in self.service_threads:
                    del self.service_threads[service_name]
            
            # 查找脚本路径
            scripts = self.get_service_scripts()
            script_path = None
            for script in scripts:
                if Path(script).stem == service_name:
                    script_path = script
                    break
            
            if not script_path:
                logger.error(f"Script path not found for service {service_name}")
                return False
            
            # 等待一段时间再重启
            logger.info(f"Waiting {self.restart_delay}s before restarting {service_name}")
            time.sleep(self.restart_delay)
            
            # 重启服务
            return self.start_service(script_path)
            
        except Exception as e:
            logger.error(f"Failed to restart service {service_name}: {e}")
            return False
    
    def monitor_services(self):
        """监控所有服务的状态"""
        restart_counts = {}
        
        while self.running:
            try:
                for service_name, process in list(self.services.items()):
                    if process.poll() is not None:
                        logger.warning(f"Service {service_name} has exited with code: {process.returncode}")
                        
                        # 检查重启次数
                        restart_counts[service_name] = restart_counts.get(service_name, 0) + 1
                        
                        if restart_counts[service_name] <= self.max_restarts:
                            logger.info(f"Restarting service {service_name} (attempt {restart_counts[service_name]})")
                            self.restart_service(service_name)
                        else:
                            logger.error(f"Service {service_name} has exceeded maximum restart attempts ({self.max_restarts})")
                            # 清理服务
                            if service_name in self.services:
                                del self.services[service_name]
                            if service_name in self.service_threads:
                                del self.service_threads[service_name]
                
                time.sleep(5)  # 每5秒检查一次
                
            except Exception as e:
                logger.error(f"Error in service monitoring: {e}")
                time.sleep(5)
    
    def start_all_services(self):
        """启动所有服务"""
        scripts = self.get_service_scripts()
        
        for script in scripts:
            self.start_service(script)
            time.sleep(2)  # 服务间启动间隔
    
    def stop_all_services(self):
        """停止所有服务"""
        logger.info("Stopping all services...")
        
        for service_name, process in self.services.items():
            try:
                if process.poll() is None:
                    logger.info(f"Stopping service {service_name}")
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        logger.warning(f"Force killing service {service_name}")
                        process.kill()
            except Exception as e:
                logger.error(f"Error stopping service {service_name}: {e}")
        
        self.services.clear()
        self.service_threads.clear()
        logger.info("All services stopped")
    
    def get_service_status(self) -> Dict:
        """获取所有服务状态"""
        status = {}
        for service_name, process in self.services.items():
            status[service_name] = {
                'pid': process.pid,
                'running': process.poll() is None,
                'returncode': process.returncode,
                'log_count': len(self.service_logs.get(service_name, []))
            }
        return status
    
    def run(self):
        """运行服务管理器"""
        self.running = True
        
        # 注册信号处理
        def signal_handler(sig, frame):
            logger.info("Received interrupt signal, shutting down...")
            self.running = False
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        try:
            # 启动所有服务
            self.start_all_services()
            
            # 启动监控线程
            monitor_thread = threading.Thread(target=self.monitor_services, daemon=True)
            monitor_thread.start()
            
            logger.info("Service manager started successfully")
            
            # 主循环
            while self.running:
                # 打印服务状态
                status = self.get_service_status()
                logger.info(f"Service status: {status}")
                time.sleep(30)  # 每30秒打印一次状态
                
        except KeyboardInterrupt:
            logger.info("Service manager interrupted by user")
        except Exception as e:
            logger.error(f"Service manager error: {e}")
        finally:
            # 停止所有服务
            self.stop_all_services()
            logger.info("Service manager stopped")

def main():
    """主函数"""
    manager = ServiceManager()
    manager.run()

if __name__ == "__main__":
    main()