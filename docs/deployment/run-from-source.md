# 源码运行 | Run from Source

1) Python 虚拟环境
```bash
python -m venv .myenv
# Linux/macOS
source .myenv/bin/activate
# Windows PowerShell
# .\.myenv\Scripts\Activate.ps1
```

2) 安装根依赖
```bash
pip install -r requirements.txt
```

3) 安装各 MCP 依赖
- notepad: pip install -r notepad_mcp/requirements.txt
- calculator: pip install -r requirements-calculator.txt
- websearch（若使用）: pip install -r xiaozhi-websearch/requirements.txt
- vps（若使用）: pip install -r server_mcp_vps/requirements.txt

4) 运行统一管道
```bash
export MCP_ENDPOINT="wss://.../mcp/?token=..."
export MCP_SCRIPTS="calculator.py notepad_mcp/notepad_mcp_fixed.py xiaozhi-websearch/websearch_optimized.py server_mcp_vps/server_mcp.py"
python mcp_pipe.py $MCP_SCRIPTS
```
或: bash scripts/start_mcp_pipe.sh
