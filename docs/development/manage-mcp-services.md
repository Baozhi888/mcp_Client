# 新增/移除 MCP 服务 | Manage MCP Services

依赖命名规则（命中任一即可被自动安装）:
1) <script_dir>/requirements.txt（脚本在子目录）
2) <script_dir>/requirements-<script_basename>.txt
3) <script_dir>/requirements.<script_basename>.txt
4) ./requirements-<script_basename>.txt（脚本在根目录）
5) ./requirements.<script_basename>.txt（脚本在根目录）

流程:
1) 放置脚本与依赖文件
2) 在 .env 的 MCP_SCRIPTS 追加脚本路径（空格分隔）
3) docker restart mcp-pipe
4) 观察日志直到出现 "Successfully connected to WebSocket server"

临时移除:
- 从 MCP_SCRIPTS 删除对应脚本路径，重启即可

