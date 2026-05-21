# VPS MCP Server Management

模块化的 VPS 服务器管理 MCP 服务，支持多服务器独立部署。

## 特性

- **模块化架构** - 按功能拆分，易于维护和扩展
- **多服务器支持** - 每台服务器独立配置和运行
- **安全控制** - 命令白名单、资源限制、审计日志
- **异步任务** - 支持长时间运行的后台任务
- **北京时区** - 日志和时间戳使用北京时间

## 目录结构

```
server_mcp_vps/
├── server_mcp.py       # 主入口
├── core.py             # 核心功能（日志、安全、命令执行）
├── tools/
│   ├── system.py       # 系统监控、进程、任务管理
│   ├── service.py      # 服务管理、包管理、Docker
│   ├── network.py      # 网络、端口、防火墙、DNS
│   ├── files.py        # 文件管理、磁盘、日志
│   ├── security.py     # 安全监控、用户、SSH密钥
│   └── backup.py       # 备份创建与恢复
├── requirements.txt
├── .env.example
└── README.md
```

## 快速开始

### 1. 安装依赖

```bash
cd server_mcp_vps
pip install -r requirements.txt
```

### 2. 配置环境

```bash
cp .env.example .env
# 编辑 .env 配置服务器标识和允许的服务
```

### 3. 启动服务

**方式 A: 通过 mcp_pipe.py（推荐）**

```bash
# 在主目录的 .env 中添加
MCP_SCRIPTS="server_mcp_vps/server_mcp.py"

# 启动
python mcp_pipe.py server_mcp_vps/server_mcp.py
```

**方式 B: 直接运行**

```bash
cd server_mcp_vps
python server_mcp.py
```

## 工具列表

### 系统监控 (system.py)
| 工具 | 功能 |
|------|------|
| `vps_system_info` | 获取系统信息（OS、内核、运行时间） |
| `vps_system_metrics` | 实时资源指标（CPU、内存、磁盘） |
| `vps_performance_check` | 综合性能检查 |
| `vps_process_list` | 列出进程 |
| `vps_process_manage` | 管理进程（终止/暂停/恢复） |
| `vps_task_status` | 查询异步任务状态 |
| `vps_task_cleanup` | 清理已完成任务 |

### 服务管理 (service.py)
| 工具 | 功能 |
|------|------|
| `vps_service_status` | 检查服务状态 |
| `vps_service_manage` | 管理服务（启动/停止/重启） |
| `vps_service_health` | 批量健康检查 |
| `vps_package_manage` | 软件包管理 |
| `vps_docker_manage` | Docker 容器管理 |
| `vps_async_docker_deploy` | 异步 Docker 部署 |

### 网络工具 (network.py)
| 工具 | 功能 |
|------|------|
| `vps_network_info` | 网络接口和路由信息 |
| `vps_port_check` | 端口连通性检查 |
| `vps_firewall_manage` | UFW 防火墙管理 |
| `vps_port_security` | 端口安全扫描 |
| `vps_dns_config` | DNS 配置管理 |
| `vps_network_diagnostic` | 网络诊断（ping/traceroute） |

### 文件管理 (files.py)
| 工具 | 功能 |
|------|------|
| `vps_file_manage` | 文件/目录操作 |
| `vps_disk_usage` | 磁盘使用分析 |
| `vps_log_view` | 查看日志文件 |
| `vps_log_search` | 搜索日志内容 |
| `vps_system_logs` | 查看系统日志 |

### 安全管理 (security.py)
| 工具 | 功能 |
|------|------|
| `vps_security_monitor` | 安全监控检查 |
| `vps_user_manage` | 用户账户管理 |
| `vps_ssh_key_manage` | SSH 密钥管理 |

### 备份恢复 (backup.py)
| 工具 | 功能 |
|------|------|
| `vps_backup_create` | 创建备份 |
| `vps_backup_restore` | 恢复备份 |
| `vps_backup_list` | 列出备份文件 |

## 环境变量配置

```bash
# 服务器标识（必须唯一）
SERVER_ID=vps_001
SERVER_NAME=Web Server 1
SERVER_LOCATION=US-West
SERVER_ROLE=production

# 日志级别
LOG_LEVEL=INFO

# 允许管理的服务（逗号分隔，* 表示全部）
ALLOWED_SERVICES=nginx,mysql,redis,docker

# 资源限制阈值
MAX_CPU_PERCENT=90
MAX_MEMORY_PERCENT=90
MAX_DISK_PERCENT=95
MAX_COMMAND_TIMEOUT=3600
```

## 多服务器部署示例

```bash
# 服务器 1 - Web
SERVER_ID=web_01
ALLOWED_SERVICES=nginx,docker

# 服务器 2 - Database
SERVER_ID=db_01
ALLOWED_SERVICES=mysql,postgresql

# 服务器 3 - Cache
SERVER_ID=cache_01
ALLOWED_SERVICES=redis
```

## 安全配置

### 配置 sudo 权限

```bash
sudo visudo
# 添加以下内容
your_user ALL=(ALL) NOPASSWD: /bin/systemctl
your_user ALL=(ALL) NOPASSWD: /usr/bin/docker
your_user ALL=(ALL) NOPASSWD: /usr/sbin/ufw
```

### 日志位置

- 服务日志: `~/llm_logs/vps_server_mcp.log`
- 审计日志: `~/llm_logs/vps_audit.log`

## 扩展开发

在 `tools/` 目录下创建新模块：

```python
# tools/custom.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import mcp, logger, execute_command, build_response

@mcp.tool()
def vps_custom_tool(server_name: str, param: str) -> dict:
    """自定义工具描述"""
    result = execute_command(f"your_command {param}", "custom")
    return build_response(result["success"], output=result.get("output"))
```

然后在 `server_mcp.py` 中导入：

```python
from tools import custom
```

## License

MIT License
