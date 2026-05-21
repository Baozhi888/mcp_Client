# Docker 部署 | Deployment with Docker

前置要求:
- 安装 Docker（建议包含 docker compose 插件）
- 准备 MCP_ENDPOINT（从 MCP Gateway 获取）

步骤:
1) 配置 .env
- 关键项:
  - MCP_ENDPOINT=wss://...
  - MCP_SCRIPTS="calculator.py notepad_mcp/notepad_mcp_fixed.py xiaozhi-websearch/websearch_optimized.py server_mcp_vps/server_mcp.py"
  - 可选镜像源: PIP_INDEX_URL, PIP_TRUSTED_HOST

2) 启动
- 点名服务（推荐）:
  - docker compose up -d redis mcp-pipe
- 查看日志:
  - docker logs -f mcp-pipe

3) 验证
- 日志出现 "Successfully connected to WebSocket server"
- 网关页面显示工具列表

4) 常用操作
- 重启: docker restart mcp-pipe
- 更新重建: docker compose up -d --build
- 仅看特定脚本日志:
  - Linux/Mac: docker logs mcp-pipe --tail 500 | grep -i notepad
  - Windows: docker logs mcp-pipe --tail 500 | findstr /i notepad

5) 脚本权限与换行符（Permission denied 排错）
- 若日志出现：`/app/scripts/start_mcp_pipe.sh: Permission denied`
- 处理方法（VPS 上执行）：
  - 修复换行符：`sed -i 's/\r$//' scripts/start_mcp_pipe.sh`
  - 赋予执行权限：`chmod +x scripts/start_mcp_pipe.sh`
  - 可批量处理：
    - `find scripts -type f -name "*.sh" -exec sed -i 's/\r$//' {} \;`
    - `chmod +x scripts/*.sh`
- 然后重启：`docker compose restart mcp-pipe`

