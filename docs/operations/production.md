# 生产优化 | Production Optimization

目标: 缩短冷启动、提升稳定性/可观测性、减少对外网依赖。

1) 预装依赖镜像（推荐）
- 将常用依赖 bake 入 mcp-pipe 镜像，避免运行时 pip:
```
# mcp-pipe/Dockerfile 片段示例
RUN python -m pip install --no-cache-dir mcp fastmcp redis \
 && python -m pip install --no-cache-dir -r notepad_mcp/requirements.txt \
 && python -m pip install --no-cache-dir -r requirements-calculator.txt
# 如需包含 websearch:
# && python -m pip install --no-cache-dir -r xiaozhi-websearch/requirements.txt
```
- 构建: docker compose build mcp-pipe
- 优点: 冷启动快；权衡: 镜像更大，依赖变更需重建

2) 私有 PyPI 代理/缓存
- 使用 devpi/pypiserver/sonatype 等
- 在 .env 指向代理: PIP_INDEX_URL, PIP_TRUSTED_HOST

3) 健康检查与重启策略
- 为 mcp-pipe 增加 healthcheck 与 restart 策略（docker-compose.yml）
- 可选: 自定义探针脚本，检测与网关握手/子进程状态

4) 资源限制与拆分
- deploy.resources.limits.cpus / memory
- 重型 MCP 可拆分为独立容器运行（仍由 mcp-pipe 托管 stdio）

5) 日志与监控
- 接入 Loki/ELK；关键节点打点：首次依赖安装完成、握手成功、子进程异常重启

6) 配置管理
- 仅通过 .env 维护 MCP_SCRIPTS、MCP_ENDPOINT、镜像源等
- 依赖命名遵循规则，确保自动安装命中

7) 回滚与更新
- 镜像版本化，staging 回归后上线
- 代码/配置变更: docker compose up -d --no-build mcp-pipe
- 依赖大版本调整: 重建镜像并分批发布

