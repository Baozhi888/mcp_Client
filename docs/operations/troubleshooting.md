# 常见问题与排障 | Troubleshooting

- ModuleNotFoundError（mcp/fastmcp/redis）
  - 启动脚本会先安装 mcp/fastmcp/redis；仍失败请检查网络及镜像源
- 4004 Internal server error
  - 多由子进程启动后立刻异常退出引起；先找更早的 ImportError、SyntaxError 等具体异常
- 依赖慢/超时
  - .env 配置 PIP_INDEX_URL 与 PIP_TRUSTED_HOST
- profiles 不可用
  - 使用: docker compose up -d redis mcp-pipe
- Redis 监听器开关
  - ENABLE_REDIS_LISTENER=true|false

