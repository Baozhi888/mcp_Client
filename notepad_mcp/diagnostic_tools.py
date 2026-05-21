"""
诊断工具模块 - 用于调试和验证记事本MCP服务
"""

import os
import json
import logging
import asyncio
import aiohttp
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from dataclasses import dataclass, asdict

from config import CLOUDFLARE_CONFIG, GMAIL_CONFIG, SERVICE_CONFIG
from services.d1_service import D1Service
from services.kv_service import KVService
from services.gmail_service import GmailService

logger = logging.getLogger('DIAGNOSTIC_TOOLS')

@dataclass
class DiagnosticReport:
    """诊断报告数据结构"""
    timestamp: str
    component: str
    status: str
    errors: List[str]
    suggestions: List[str]
    config_status: Dict[str, bool]
    details: Dict[str, Any]

@dataclass
class TestResult:
    """测试结果数据结构"""
    test_name: str
    success: bool
    duration: float
    error_message: Optional[str]
    details: Dict[str, Any]

class ConfigValidator:
    """配置验证器"""
    
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.suggestions = []
    
    def validate_cloudflare_config(self) -> Dict[str, Any]:
        """验证Cloudflare配置"""
        logger.info("[CONFIG_VALIDATOR] Validating Cloudflare configuration...")
        
        config_status = {}
        required_configs = {
            'api_token': CLOUDFLARE_CONFIG.get('api_token'),
            'account_id': CLOUDFLARE_CONFIG.get('account_id'),
            'kv_namespace_id': CLOUDFLARE_CONFIG.get('kv_namespace_id'),
            'd1_database_id': CLOUDFLARE_CONFIG.get('d1_database_id')
        }
        
        for key, value in required_configs.items():
            if not value:
                config_status[key] = False
                self.errors.append(f"Missing Cloudflare {key}")
                self.suggestions.append(f"Set {key.upper()} in your .env file")
            else:
                config_status[key] = True
                logger.info(f"[CONFIG_VALIDATOR] ✓ {key} is configured")
        
        return {
            'status': 'valid' if all(config_status.values()) else 'invalid',
            'config_status': config_status,
            'errors': self.errors.copy(),
            'suggestions': self.suggestions.copy()
        }
    
    def validate_gmail_config(self) -> Dict[str, Any]:
        """验证Gmail配置"""
        logger.info("[CONFIG_VALIDATOR] Validating Gmail configuration...")
        
        config_status = {}
        
        # 检查凭证文件
        cred_file = GMAIL_CONFIG.get('api_credentials_file')
        if cred_file and os.path.exists(cred_file):
            config_status['credentials_file'] = True
            logger.info(f"[CONFIG_VALIDATOR] ✓ Gmail credentials file found: {cred_file}")
        else:
            config_status['credentials_file'] = False
            self.errors.append(f"Gmail credentials file not found: {cred_file}")
            self.suggestions.append("Download Gmail API credentials from Google Cloud Console")
        
        # 检查token文件
        token_file = GMAIL_CONFIG.get('token_path')
        if token_file and os.path.exists(token_file):
            config_status['token_file'] = True
            logger.info(f"[CONFIG_VALIDATOR] ✓ Gmail token file found: {token_file}")
            
            # 验证token内容
            try:
                with open(token_file, 'r', encoding='utf-8') as f:
                    token_data = json.load(f)
                    if 'token' in token_data and 'refresh_token' in token_data:
                        config_status['token_valid'] = True
                        logger.info("[CONFIG_VALIDATOR] ✓ Gmail token appears valid")
                    else:
                        config_status['token_valid'] = False
                        self.warnings.append("Gmail token file exists but may be invalid")
            except Exception as e:
                config_status['token_valid'] = False
                self.errors.append(f"Failed to read Gmail token: {e}")
        else:
            config_status['token_file'] = False
            self.warnings.append(f"Gmail token file not found: {token_file}")
            self.suggestions.append("Run run_gmail_auth.py to generate token")
        
        # 检查服务器模式配置
        server_mode = GMAIL_CONFIG.get('server_mode', False)
        if server_mode:
            auth_code = GMAIL_CONFIG.get('authorization_code')
            if auth_code:
                config_status['server_mode_auth'] = True
                logger.info("[CONFIG_VALIDATOR] ✓ Server mode authorization code configured")
            else:
                config_status['server_mode_auth'] = False
                self.warnings.append("Server mode enabled but no authorization code provided")
        else:
            config_status['server_mode_auth'] = True  # Not required in local mode
        
        return {
            'status': 'valid' if all(config_status.values()) else 'partial',
            'config_status': config_status,
            'errors': self.errors.copy(),
            'warnings': self.warnings.copy(),
            'suggestions': self.suggestions.copy()
        }
    
    def validate_environment_variables(self) -> Dict[str, Any]:
        """验证环境变量"""
        logger.info("[CONFIG_VALIDATOR] Validating environment variables...")
        
        env_status = {}
        required_env_vars = [
            'CLOUDFLARE_API_TOKEN',
            'CLOUDFLARE_ACCOUNT_ID',
            'KV_NAMESPACE_ID',
            'D1_DATABASE_ID'
        ]
        
        optional_env_vars = [
            'GMAIL_API_CREDENTIALS_FILE',
            'TOKEN_PATH',
            'SERVER_MODE',
            'MAX_FILE_SIZE',
            'ALLOWED_FILE_TYPES'
        ]
        
        for var in required_env_vars:
            value = os.getenv(var)
            if value:
                env_status[var] = True
                logger.info(f"[CONFIG_VALIDATOR] ✓ {var} is set")
            else:
                env_status[var] = False
                self.errors.append(f"Required environment variable {var} is not set")
        
        for var in optional_env_vars:
            value = os.getenv(var)
            env_status[var] = bool(value)
            if value:
                logger.info(f"[CONFIG_VALIDATOR] ✓ {var} is set")
            else:
                logger.info(f"[CONFIG_VALIDATOR] - {var} is not set (optional)")
        
        return {
            'status': 'valid' if all(env_status[var] for var in required_env_vars) else 'invalid',
            'env_status': env_status,
            'errors': self.errors.copy(),
            'suggestions': self.suggestions.copy()
        }
    
    def generate_config_report(self) -> DiagnosticReport:
        """生成完整的配置诊断报告"""
        logger.info("[CONFIG_VALIDATOR] Generating comprehensive configuration report...")
        
        # 重置错误和建议列表
        self.errors = []
        self.warnings = []
        self.suggestions = []
        
        # 验证各个配置组件
        cloudflare_result = self.validate_cloudflare_config()
        gmail_result = self.validate_gmail_config()
        env_result = self.validate_environment_variables()
        
        # 汇总状态
        overall_status = 'valid'
        if cloudflare_result['status'] == 'invalid' or env_result['status'] == 'invalid':
            overall_status = 'invalid'
        elif gmail_result['status'] == 'partial':
            overall_status = 'partial'
        
        # 汇总所有配置状态
        all_config_status = {}
        all_config_status.update(cloudflare_result['config_status'])
        all_config_status.update(gmail_result['config_status'])
        all_config_status.update(env_result['env_status'])
        
        # 汇总所有错误和建议
        all_errors = []
        all_errors.extend(cloudflare_result.get('errors', []))
        all_errors.extend(gmail_result.get('errors', []))
        all_errors.extend(env_result.get('errors', []))
        
        all_suggestions = []
        all_suggestions.extend(cloudflare_result.get('suggestions', []))
        all_suggestions.extend(gmail_result.get('suggestions', []))
        all_suggestions.extend(env_result.get('suggestions', []))
        
        report = DiagnosticReport(
            timestamp=datetime.now().isoformat(),
            component='Configuration',
            status=overall_status,
            errors=all_errors,
            suggestions=all_suggestions,
            config_status=all_config_status,
            details={
                'cloudflare': cloudflare_result,
                'gmail': gmail_result,
                'environment': env_result
            }
        )
        
        logger.info(f"[CONFIG_VALIDATOR] Configuration report generated: {overall_status}")
        return report

class ConnectionTester:
    """连接测试器"""
    
    def __init__(self):
        self.test_results = []
    
    async def test_d1_connection(self) -> TestResult:
        """测试D1数据库连接"""
        logger.info("[CONNECTION_TESTER] Testing D1 database connection...")
        
        start_time = datetime.now()
        try:
            d1_service = D1Service()
            
            # 测试基本查询
            result = await d1_service.execute_query("SELECT 1 as test")
            
            duration = (datetime.now() - start_time).total_seconds()
            
            if result and result.get('success') is not False:
                logger.info("[CONNECTION_TESTER] ✓ D1 connection successful")
                return TestResult(
                    test_name="D1 Connection",
                    success=True,
                    duration=duration,
                    error_message=None,
                    details={'result': result}
                )
            else:
                error_msg = result.get('error', 'Unknown error') if result else 'No response'
                logger.error(f"[CONNECTION_TESTER] ✗ D1 connection failed: {error_msg}")
                return TestResult(
                    test_name="D1 Connection",
                    success=False,
                    duration=duration,
                    error_message=error_msg,
                    details={'result': result}
                )
                
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(f"[CONNECTION_TESTER] ✗ D1 connection exception: {e}")
            return TestResult(
                test_name="D1 Connection",
                success=False,
                duration=duration,
                error_message=str(e),
                details={'exception': str(e)}
            )
    
    async def test_kv_connection(self) -> TestResult:
        """测试KV存储连接"""
        logger.info("[CONNECTION_TESTER] Testing KV storage connection...")
        
        start_time = datetime.now()
        try:
            kv_service = KVService()
            
            # 测试写入和读取
            test_key = f"connection_test_{int(datetime.now().timestamp())}"
            test_value = "connection_test_value"
            
            # 写入测试
            put_result = await kv_service.put(test_key, test_value)
            if not put_result:
                raise Exception("Failed to put test value")
            
            # 读取测试
            get_result = await kv_service.get(test_key)
            if get_result != test_value:
                raise Exception(f"Value mismatch: expected {test_value}, got {get_result}")
            
            # 清理测试数据
            await kv_service.delete(test_key)
            
            duration = (datetime.now() - start_time).total_seconds()
            logger.info("[CONNECTION_TESTER] ✓ KV connection successful")
            return TestResult(
                test_name="KV Connection",
                success=True,
                duration=duration,
                error_message=None,
                details={'test_key': test_key, 'test_value': test_value}
            )
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(f"[CONNECTION_TESTER] ✗ KV connection failed: {e}")
            return TestResult(
                test_name="KV Connection",
                success=False,
                duration=duration,
                error_message=str(e),
                details={'exception': str(e)}
            )
    
    async def test_gmail_connection(self) -> TestResult:
        """测试Gmail连接"""
        logger.info("[CONNECTION_TESTER] Testing Gmail connection...")
        
        start_time = datetime.now()
        try:
            gmail_service = GmailService()
            gmail_service._initialize_service()
            
            if not gmail_service.service:
                raise Exception("Gmail service initialization failed")
            
            # 测试获取用户信息
            health_result = gmail_service.check_service_health()
            
            duration = (datetime.now() - start_time).total_seconds()
            
            if health_result.get('success'):
                logger.info("[CONNECTION_TESTER] ✓ Gmail connection successful")
                return TestResult(
                    test_name="Gmail Connection",
                    success=True,
                    duration=duration,
                    error_message=None,
                    details=health_result
                )
            else:
                error_msg = health_result.get('status', 'Unknown error')
                logger.error(f"[CONNECTION_TESTER] ✗ Gmail connection failed: {error_msg}")
                return TestResult(
                    test_name="Gmail Connection",
                    success=False,
                    duration=duration,
                    error_message=error_msg,
                    details=health_result
                )
                
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(f"[CONNECTION_TESTER] ✗ Gmail connection exception: {e}")
            return TestResult(
                test_name="Gmail Connection",
                success=False,
                duration=duration,
                error_message=str(e),
                details={'exception': str(e)}
            )
    
    async def run_comprehensive_test(self) -> List[TestResult]:
        """运行综合连接测试"""
        logger.info("[CONNECTION_TESTER] Running comprehensive connection tests...")
        
        tests = [
            self.test_d1_connection(),
            self.test_kv_connection(),
            self.test_gmail_connection()
        ]
        
        results = await asyncio.gather(*tests, return_exceptions=True)
        
        # 处理异常结果
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append(TestResult(
                    test_name=f"Test {i+1}",
                    success=False,
                    duration=0.0,
                    error_message=str(result),
                    details={'exception': str(result)}
                ))
            else:
                processed_results.append(result)
        
        # 记录测试摘要
        successful_tests = sum(1 for r in processed_results if r.success)
        total_tests = len(processed_results)
        logger.info(f"[CONNECTION_TESTER] Connection tests completed: {successful_tests}/{total_tests} passed")
        
        return processed_results

class DebugLogger:
    """调试日志增强器"""
    
    def __init__(self):
        self.debug_logger = logging.getLogger('DEBUG_ENHANCED')
        self.debug_logger.setLevel(logging.DEBUG)
        
        # 创建调试日志文件处理器
        debug_handler = logging.FileHandler('notepad_mcp_debug.log', encoding='utf-8')
        debug_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
        )
        debug_handler.setFormatter(debug_formatter)
        self.debug_logger.addHandler(debug_handler)
    
    def log_sql_query(self, query: str, params: List[Any] = None, result: Any = None, error: str = None):
        """记录SQL查询详情"""
        self.debug_logger.debug(f"SQL Query: {query}")
        if params:
            self.debug_logger.debug(f"SQL Params: {params}")
        if result:
            self.debug_logger.debug(f"SQL Result: {result}")
        if error:
            self.debug_logger.error(f"SQL Error: {error}")
    
    def log_api_request(self, service: str, method: str, url: str = None, 
                       params: Dict = None, response: Any = None, error: str = None):
        """记录API请求详情"""
        self.debug_logger.debug(f"API Request - Service: {service}, Method: {method}")
        if url:
            self.debug_logger.debug(f"API URL: {url}")
        if params:
            self.debug_logger.debug(f"API Params: {params}")
        if response:
            self.debug_logger.debug(f"API Response: {response}")
        if error:
            self.debug_logger.error(f"API Error: {error}")
    
    def log_error_details(self, component: str, operation: str, error: Exception, 
                         context: Dict[str, Any] = None):
        """记录详细错误信息"""
        self.debug_logger.error(f"Error in {component}.{operation}: {error}")
        if context:
            self.debug_logger.error(f"Error Context: {context}")
        
        # 记录堆栈跟踪
        import traceback
        self.debug_logger.error(f"Stack Trace: {traceback.format_exc()}")
    
    def generate_debug_report(self) -> Dict[str, Any]:
        """生成调试报告"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'debug_log_file': 'notepad_mcp_debug.log',
            'log_level': 'DEBUG',
            'handlers': [handler.__class__.__name__ for handler in self.debug_logger.handlers]
        }
        
        self.debug_logger.info(f"Debug report generated: {report}")
        return report

# 便捷函数
async def run_full_diagnostic() -> Dict[str, Any]:
    """运行完整的诊断检查"""
    logger.info("Starting full diagnostic check...")
    
    # 配置验证
    config_validator = ConfigValidator()
    config_report = config_validator.generate_config_report()
    
    # 连接测试
    connection_tester = ConnectionTester()
    connection_results = await connection_tester.run_comprehensive_test()
    
    # 调试日志设置
    debug_logger = DebugLogger()
    debug_report = debug_logger.generate_debug_report()
    
    # 汇总报告
    full_report = {
        'timestamp': datetime.now().isoformat(),
        'configuration': asdict(config_report),
        'connections': [asdict(result) for result in connection_results],
        'debug_logging': debug_report,
        'summary': {
            'config_status': config_report.status,
            'connections_passed': sum(1 for r in connection_results if r.success),
            'connections_total': len(connection_results),
            'overall_health': 'healthy' if config_report.status == 'valid' and all(r.success for r in connection_results) else 'issues_detected'
        }
    }
    
    logger.info(f"Full diagnostic completed. Overall health: {full_report['summary']['overall_health']}")
    return full_report

if __name__ == "__main__":
    # 运行诊断测试
    async def main():
        report = await run_full_diagnostic()
        print(json.dumps(report, indent=2, ensure_ascii=False))
    
    asyncio.run(main())