# CLAUDE.md

你的任务流程必须使用agent完成：
1.requirements-analyzer 分析任务
2.aicp7-project-builder 分析技术栈
3.task-breakdown-manager划分子任务
4.tech-roadmap-architect实现任务


This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a multi-functional MCP (Model Context Protocol) control platform that integrates Gmail automation, PDF/Markdown generation, server/container/log management, and market data services. The platform is designed for AI-driven smart office, remote operations, and automated email processing.

## Commands

### Development Environment Setup
```bash
# Create and activate virtual environment
python -m venv .myenv
source .myenv/bin/activate  # Linux/Mac
# OR
.myenv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt
```

### Service Management
```bash
# Start all services (including Redis)
bash manage_mcp.sh start

# Stop services
bash manage_mcp.sh stop

# Restart services
bash manage_mcp.sh restart

# Check service status
bash manage_mcp.sh status
bash manage_mcp.sh fullstatus  # includes Redis status
```

### Individual Service Commands
```bash
# Run Notepad MCP service
python notepad_mcp/notepad_mcp_fixed.py

# Run server management MCP service
python server_mcp_vps/server_mcp.py

# Run MCP pipe service (communication hub)
python mcp_pipe.py <mcp_script1.py> [<mcp_script2.py> ...]
```

### Redis Management
```bash
# Redis container operations
bash manage_mcp.sh redis-start
bash manage_mcp.sh redis-stop
bash manage_mcp.sh redis-restart
bash manage_mcp.sh redis-status
bash manage_mcp.sh redis-logs
```

### Logging and Monitoring
```bash
# View latest service logs
bash manage_mcp.sh logs

# View market service logs
bash manage_mcp.sh marketlogs

# View specific log file
bash manage_mcp.sh log <filename>

# Clean up old logs
bash manage_mcp.sh cleanup
```

### Testing
```bash
# Run tests (check specific test directories)
pytest test/
pytest tests/
pytest notepad_mcp/tests/
```

## Architecture

### Core Components

1. **MCP Pipe Service (`mcp_pipe.py`)**: Central communication hub that manages WebSocket connections between multiple MCP services and provides automatic reconnection with exponential backoff.

2. **Service Management (`main.py`)**: Main service orchestrator that handles health checks, resource monitoring, and connection cleanup.

3. **Connection Manager (`connection_manager.py`)**: Manages persistent connections and handles connection lifecycle.

4. **Configuration System (`configs/`)**: Centralized configuration management with logging and service configuration.

### Service Modules

- **Notepad MCP (`notepad_mcp/notepad_mcp_fixed.py`)**: Notes, Gmail, file management, image recognition, and email reminders
- **Server MCP (`server_mcp_vps/server_mcp.py`)**: Server and container management including Docker operations, log monitoring, and system administration
- **Market MCP (`market_mcp.py`)**: Stock market data analysis and trading information
- **Calculator (`calculator.py`)**: Basic calculation MCP service
- **Web Search (`xiaozhi-websearch/`)**: Enhanced web search capabilities
- **Zhipu AI Service (`notepad_mcp/services/zhipu_service.py`)**: Image recognition and AI capabilities powered by Zhipu AI

### Data Layer

- **Redis Integration**: Used for caching and cross-service communication (port 6380)
- **Models (`models/`)**: Data models for files, notes, and LLM interactions
- **Services (`services/`)**: Business logic layer including LLM, Redis, and external API services


### Key Dependencies

- **MCP Protocol**: `mcp`, `websockets` for service communication
- **Google APIs**: `google-api-python-client`, `google-auth` for Gmail integration
- **Database**: SQLite for local data, Redis for caching
- **Document Generation**: `reportlab`, `PyPDF2`, `markdown` for PDF/Markdown creation
- **System Management**: `psutil`, `paramiko`, `docker` for server operations

## Environment Variables

Set these in `.env` file or system environment:
- `MCP_ENDPOINT`: WebSocket server endpoint for MCP communication
- `LOG_LEVEL`: Logging level (INFO, DEBUG, ERROR)
- `GMAIL_API_CREDENTIALS_FILE`: Path to Gmail API credentials
- `TOKEN_PATH`: Path to OAuth token file
- `MCP_REDIS_HOST`: Redis host (default: localhost)
- `MCP_REDIS_PORT`: Redis port (default: 6380)
- `MCP_REDIS_DB`: Redis database number (default: 1)
- `ZHIPU_API_KEY`: API key for Zhipu AI services (required for image recognition features)

## Security Considerations

- Gmail credentials (`token.json`, `gmail_credentials.json`) are in `.gitignore`
- Server management supports configurable command/path restrictions
- Redis container runs with data persistence and optional password protection
- All services support secure communication protocols

## Development Notes

- The system uses a virtual environment (`.myenv/`) for Python dependencies
- Services communicate through WebSocket connections managed by `mcp_pipe.py`
- Each service module is designed to be independently runnable
- Comprehensive logging is implemented across all components
- Docker is used for Redis deployment with automatic container management
