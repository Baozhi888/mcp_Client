# VPS 最简部署 | Minimal Deployment on VPS

1) 安装 Docker 与 compose 插件
- Ubuntu/Debian
  - sudo apt-get update
  - sudo apt-get install -y docker.io docker-compose-plugin
- CentOS/RHEL
  - sudo yum install -y docker docker-compose-plugin
- 启动 Docker
  - sudo systemctl enable --now docker

2) 克隆仓库并配置 .env
- git clone <your-repo> && cd <project>
- 编辑 .env:
  - MCP_ENDPOINT=wss://...
  - MCP_SCRIPTS="calculator.py notepad_mcp/notepad_mcp_fixed.py xiaozhi-websearch/websearch_optimized.py server_mcp_vps/server_mcp.py"
  - 可选加速:
    - PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
    - PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn

3) 一条命令启动
- docker compose up -d redis mcp-pipe
- docker logs -f mcp-pipe

4) 加入/移除 MCP（无需改 compose）
- 调整 .env 的 MCP_SCRIPTS，空格追加或删除脚本路径
- docker restart mcp-pipe

5) 说明
- 首次会安装依赖，时间取决于网络；配置镜像源可显著加速

6) 如果出现 Permission denied
- 执行：
  - `sed -i 's/\r$//' scripts/start_mcp_pipe.sh`
  - `chmod +x scripts/start_mcp_pipe.sh`
- 重启：`docker compose restart mcp-pipe`

