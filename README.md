# MCP Client

这是一个通过 `mcp-pipe` 统一托管多个 MCP 服务的项目，当前主要面向语音助手调用：记事本、邮件、联网搜索、VPS 运维和计算器。

## 当前生产入口

当前建议只运行下面四个脚本：

```bash
MCP_SCRIPTS="calculator.py notepad_mcp/notepad_mcp_fixed.py xiaozhi-websearch/websearch_optimized.py"
```

| 服务 | 入口 | 说明 |
| --- | --- | --- |
| Calculator | `calculator.py` | 安全数学表达式计算 |
| Notepad MCP | `notepad_mcp/notepad_mcp_fixed.py` | 笔记、邮件、文件、图片识别、邮件提醒 |
| Websearch MCP | `xiaozhi-websearch/websearch_optimized.py` | 联网搜索、搜索结果保存到记事本 |

旧的单体/实验入口已经清理，不再使用根目录 `server_mcp_vps.py`、`mcp_pipe_improved.py`、`notepad_mcp/gmail_mcp.py`、`notepad_mcp/notepad_mcp.py` 等旧文件。

## 快速启动

1. 准备 `.env`

```bash
cp .env.compose.example .env
```

至少需要配置：

```bash
MCP_ENDPOINT=wss://...
MCP_REDIS_PASSWORD=change_this
CLOUDFLARE_API_TOKEN=
CLOUDFLARE_ACCOUNT_ID=
KV_NAMESPACE_ID=
D1_DATABASE_ID=
GMAIL_API_CREDENTIALS_FILE=notepad_mcp/.google_key/gmail_credentials.json
TOKEN_PATH=notepad_mcp/.google_key/token.json
MCP_SCRIPTS="calculator.py notepad_mcp/notepad_mcp_fixed.py xiaozhi-websearch/websearch_optimized.py"
```

2. 启动

```bash
docker compose up -d redis mcp-pipe
```

3. 查看状态

```bash
docker compose ps
docker logs -f mcp-pipe
```

更新代码或环境变量后：

```bash
docker compose restart mcp-pipe
```

## Notepad MCP 说明

Notepad MCP 的主要工具统一使用 `notepad_` 前缀，便于语音助手识别：

- `notepad_note_*`: 创建、读取、更新、删除、追加、搜索笔记
- `notepad_email_*`: 发送、列出、读取、回复、标记、删除邮件
- `notepad_file_*`: 文件列表、文件附件发送、图片文件识别
- `notepad_reminder_*`: 创建、查询、更新、删除邮件提醒
- `notepad_health_check`: 检查 D1、KV、Gmail 和服务状态

邮件提醒的当前规则：

- 创建邮件提醒必须在当前对话中确认收件邮箱。
- 语音助手可以使用提示词里的默认邮箱作为候选，但不能静默代填。
- 用户在当前对话明确说出邮箱后，工具调用应传 `email_to`，并设置 `email_confirmed=true`。
- 调度器默认每 60 秒扫描一次到期提醒，可通过 `REMINDER_CHECK_INTERVAL` 调整。
- 可用 `notepad_reminder_scheduler_status` 查看自动调度器运行状态。

邮件发送相关配置：

```bash
GMAIL_SENDER_NAME=小可爱
GMAIL_DUPLICATE_WINDOW_SECONDS=120
```

`GMAIL_DUPLICATE_WINDOW_SECONDS` 用于抑制短时间内完全相同的普通邮件重复发送。

## 性能与资源

`docker-compose.yml` 已给 `mcp-pipe` 和 Redis 设置资源限制，适合 2G 内存 VPS：

- `mcp-pipe`: `mem_limit=512m`，`cpus=1.25`
- `redis`: `mem_limit=64m`
- `MALLOC_ARENA_MAX=2` 降低 Python 多线程场景下的内存碎片
- `MCP_INSTALL_DEPS_ON_START=false` 默认不在每次启动时安装依赖，避免重启时 CPU 和内存抖动

如需首次补装依赖，可临时设置：

```bash
MCP_INSTALL_DEPS_ON_START=true
```

## 常用运维命令

```bash
docker compose ps
docker stats --no-stream mcp-pipe mcp-redis
docker logs mcp-pipe --tail 300
docker logs mcp-pipe --tail 500 | grep -i notepad
docker compose restart mcp-pipe
```

## 文档

- 文档索引：`docs/README.md`
- Docker 部署：`docs/deployment/docker.md`
- VPS 最简部署：`docs/deployment/vps-minimal.md`
- 源码运行：`docs/deployment/run-from-source.md`
- Notepad 工具总览：`notepad_mcp/docs/tools_overview.html`
