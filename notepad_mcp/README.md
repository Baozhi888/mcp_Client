# MCP 多功能控制平台（邮件与服务器管理）
#### MCP Multi-functional Control Platform (Mail & Server Management)

简洁入口：本 README 提供概览与快速开始；完整部署与运维指南请见 docs/。

- 文档索引: docs/README.md
- 部署
  - Docker 部署: docs/deployment/docker.md
  - VPS 最简部署: docs/deployment/vps-minimal.md
  - 源码运行: docs/deployment/run-from-source.md
- 运维
  - 常见问题与排障: docs/operations/troubleshooting.md
  - 生产优化: docs/operations/production.md
- 开发
  - 新增/移除 MCP 服务: docs/development/manage-mcp-services.md


- 工具总览 | Tools Overview
  - HTML 单页（推荐）：notepad_mcp/docs/tools_overview.html
  - 记事本服务最佳实践：notepad_mcp/BEST_PRACTICES.md

---

#### 项目简介 | Project Overview

本项目是一个基于小智AI的 MCP 协议的多功能控制平台，集成 **邮件自动化**、**MCP 多服务托管** 与 **服务器/容器管理** 能力，可通过统一管道（mcp-pipe）对接远端 MCP Gateway 并动态加载多个 MCP 子服务。

---

#### 主要功能 | Main Features

- 📧 邮件自动化：收发、内容分析、PDF/Markdown/JSON 附件生成
- 🧮 MCP 子服务示例：calculator、notepad、websearch（可扩展 market 等）
- 🐳 容器/服务器运维：Docker/Compose 管理、日志、inspect 等
- 🔒 安全与可控：可配置的命令白名单、环境变量与运行策略
- 🧩 结构化接口：LLM 友好，便于自动调用

---

#### 目录结构 | Project Structure

```
.
├── docker-compose.yml
├── mcp_pipe.py                       # 统一管道（托管多个 MCP 脚本，stdio）
├── scripts/
│   └── start_mcp_pipe.sh             # 启动脚本（动态安装依赖 + 重试）
├── mcp-pipe/
│   └── Dockerfile                    # mcp-pipe 服务镜像定义
├── calculator.py                     # 示例 MCP 脚本
├── requirements-calculator.txt       # calculator 独立依赖
├── notepad_mcp/
│   ├── notepad_mcp_fixed.py
│   └── requirements.txt
├── xiaozhi-websearch/
│   ├── websearch_optimized.py
│   └── requirements.txt
├── market_mcp_optimized/             # 可选：完善后再加入 MCP_SCRIPTS
│   └── requirements.txt
├── .env                              # 运行配置（MCP_ENDPOINT、MCP_SCRIPTS 等）
└── README.md
```

---

#### 快速开始 | Quick Start

**首先创建虚拟环境**
```bash
python -m venv .myenv
source .myenv/bin/activate
```


1. **安装依赖 | Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **环境变量配置 | Set up environment variables**
   - 可通过`.env`文件或系统环境变量配置Gmail凭据、日志等级等
   - 例如：
     ```
     LOG_LEVEL=INFO
     GMAIL_API_CREDENTIALS_FILE=gmail_credentials.json
     TOKEN_PATH=token.json
     ```

3. **一键启动所有服务 | One-click Start All Services**
   ```bash
   bash manage_mcp.sh
   ```

4. **单独运行记事本 MCP 服务 | Run Notepad MCP Service**
   ```bash
   python notepad_mcp_fixed.py
   ```

5. **单独运行服务器管理MCP服务 | Run Server MCP Service**
   ```bash
   python ../server_mcp_vps/server_mcp.py
   ```

6. **测试 | Run Tests**
   ```bash
   pytest test/
   ```

7. **Windows 11 用户启动记事本MCP服务**
   ```cmd
   start_notepad_mcp.bat
   ```
   或直接运行PowerShell脚本：
   ```powershell
   .\start_notepad_mcp.ps1
   ```

---

#### 典型用法 | Typical Usage

- **发送带PDF/Markdown/JSON附件的邮件**
- **自动分析邮件内容，生成回复建议**
- **一键获取服务器状态、服务/进程/日志/网络信息**
- **远程执行命令、管理容器、备份与恢复**
- **日志tail/grep/统计/实时监控**

---

#### 依赖环境 | Requirements

- Python 3.7+
- Docker Desktop (Windows 11用户需要安装Docker Desktop)
- 详见 `requirements.txt`，主要依赖：
  - google-api-python-client, google-auth, google-auth-oauthlib
  - websockets, python-dotenv, mcp, pydantic, psutil, paramiko, cryptography
  - reportlab, PyPDF2, markdown, markdown-it-py, python-markdown-math 等
  - fastmcp, cloudflare (记事本MCP服务需要)

---

#### 安全与隐私 | Security & Privacy

- 谷歌邮箱**token.json** 和 **gmail_credentials.json** 已加入 `.gitignore`，请勿上传敏感凭据到远程仓库。
- 支持自定义命令/路径/服务名的安全限制，生产环境建议开启严格模式。

---

#### 开发人员 | Developers

- 主开发：KingJohn
- 邮箱：kj331704@email.com
- 贡献者：欢迎在PR中署名

---

#### 贡献与反馈 | Contributing

欢迎提交PR、Issue，或提出改进建议！

Contributions and suggestions are welcome!

---

#### 致谢与引用 | Acknowledgments & References

- 本项目部分设计和实现参考自 [mcp-calculator](https://github.com/78/mcp-calculator)
- 服务端与AI物联网生态 [xiaozhi-esp32](https://github.com/78/xiaozhi-esp32)
- 感谢虾哥提供的优秀项目，本项目将不断完善，欢迎PR

---

#### License

MIT License


---

## 架构与近期优化 | Architecture & Recent Optimizations

本项目现已采用“统一管道 + 多个 MCP 子服务”的架构：
- 统一管道：mcp_pipe.py（容器服务名：mcp-pipe）负责与远端 MCP Gateway 建立 stdio 连接，并托管多个子脚本（MCP 服务）
- 子服务：如 calculator.py、notepad_mcp/notepad_mcp_fixed.py、xiaozhi-websearch/websearch_optimized.py 等
- 动态依赖安装：启动脚本 scripts/start_mcp_pipe.sh 可根据 MCP_SCRIPTS 中的脚本列表安装依赖；生产环境默认关闭，需设置 MCP_INSTALL_DEPS_ON_START=true 才会启用
  - 依赖查找优先级（匹配即安装）：
    1) <script_dir>/requirements.txt（脚本位于子目录时，常用）
    2) <script_dir>/requirements-<script_basename>.txt
    3) <script_dir>/requirements.<script_basename>.txt
    4) ./requirements-<script_basename>.txt（根目录脚本）
    5) ./requirements.<script_basename>.txt（根目录脚本）
  - 若未命中上述文件，已预装最小公共依赖：mcp、fastmcp
  - 为了减少重启时 CPU 和内存抖动，生产环境建议预装依赖并保持 MCP_INSTALL_DEPS_ON_START=false
- 统一配置：使用 .env 配置 MCP_ENDPOINT、MCP_SCRIPTS、Redis 等环境变量
- Redis：notepad 依赖 Redis 监听器，可通过 ENABLE_REDIS_LISTENER 进行开关

优势：
- 新增 MCP 服务只需：提供脚本与对应 requirements 文件，追加到 MCP_SCRIPTS，重启即可
- 安装逻辑更健壮：内置 pip 重试/超时、预装常用基座依赖

---

## 部署指南（Docker） | Deployment with Docker

前置要求：
- 已安装 Docker（建议含 docker compose）
- 准备好远端 MCP Gateway 的 MCP_ENDPOINT（带 token）

1) 配置 .env
- 关键项：
  - MCP_ENDPOINT=wss://...（从你的网关获取）
  - MCP_SCRIPTS="calculator.py notepad_mcp/notepad_mcp_fixed.py xiaozhi-websearch/websearch_optimized.py server_mcp_vps/server_mcp.py"
  - ENABLE_REDIS_LISTENER=true（notepad 需要 Redis 监听）
  - 可选：PIP_INDEX_URL、PIP_TRUSTED_HOST（加速依赖安装）

2) 启动
- 方式 A：使用 profiles（推荐）
  - Windows PowerShell: `$env:COMPOSE_PROFILES="mcp-pipe"; docker compose up -d --build`
  - Linux/macOS: `export COMPOSE_PROFILES="mcp-pipe" && docker compose up -d --build`
- 方式 B：直接点名服务（兼容部分环境）
  - `docker compose up -d redis mcp-pipe`

3) 查看日志与验证
- `docker logs -f mcp-pipe`
- 看到类似如下即表示接入成功：
  - `[... notepad_mcp_fixed ...] Successfully connected to WebSocket server`
  - `[... calculator.py ...] Successfully connected to WebSocket server`
- 首次启动需安装依赖，时间取决于网络环境

4) 常用操作
- 重启：`docker restart mcp-pipe`
- 仅跟踪 notepad 日志（示例）：`docker logs mcp-pipe --tail 500 | grep -i notepad`
- 更新代码后重建：`docker compose up -d --build`

---

---

## VPS 最简部署 | Minimal Deployment on VPS

以下流程适用于常见的云服务器（Ubuntu/Debian/CentOS 等），仅依赖 Docker 与 compose 插件。

1) 安装 Docker 与 compose 插件
- Ubuntu/Debian
  - `sudo apt-get update`
  - `sudo apt-get install -y docker.io docker-compose-plugin`
- CentOS/RHEL
  - `sudo yum install -y docker docker-compose-plugin`
- 启动 Docker 服务
  - `sudo systemctl enable --now docker`

2) 克隆仓库并配置 .env
- `git clone <your-repo> && cd <project>`
- 编辑 .env，至少设置以下键：
  - `MCP_ENDPOINT=wss://...`（从 MCP Gateway 获取）
  - `MCP_SCRIPTS="calculator.py notepad_mcp/notepad_mcp_fixed.py xiaozhi-websearch/websearch_optimized.py server_mcp_vps/server_mcp.py"`
  - 可选（强烈建议加速）：
    - `PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple`
    - `PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn`

3) 一条命令启动
- `docker compose up -d redis mcp-pipe`
- 查看日志：`docker logs -f mcp-pipe`
- 看到 `Successfully connected to WebSocket server` 即表示接入成功

4) 加入/移除 MCP 服务（无需改 compose）
- 仅修改 .env 的 `MCP_SCRIPTS`，空格追加或删除脚本路径：
  - 例如加入 websearch：
    - `MCP_SCRIPTS="calculator.py notepad_mcp/notepad_mcp_fixed.py xiaozhi-websearch/websearch_optimized.py server_mcp_vps/server_mcp.py"`
    - `docker restart mcp-pipe`
- 依赖会由 `scripts/start_mcp_pipe.sh` 自动解析并安装（含重试）

5) 常用运维命令
- 重启：`docker restart mcp-pipe`
- 仅跟踪某脚本日志（Linux/Mac）：`docker logs mcp-pipe --tail 500 | grep -i websearch`
- 仅跟踪某脚本日志（Windows）：`docker logs mcp-pipe --tail 500 | findstr /i websearch`

提示：首次启动会安装各 MCP 的依赖（如 PyQt/OpenCV/MySQL Connector 等大包），耗时取决于网络；设置 PyPI 镜像可显著加速。


## 源码运行 | Run from Source

1) 准备 Python 虚拟环境
```bash
python -m venv .myenv
# Linux/macOS
source .myenv/bin/activate
# Windows PowerShell
# .\.myenv\Scripts\Activate.ps1
```

2) 安装根依赖（用于统一管道与通用组件）
```bash
pip install -r requirements.txt
```

3) 为各 MCP 服务安装依赖
- notepad（示例）：`pip install -r notepad_mcp/requirements.txt`
- calculator：`pip install -r requirements-calculator.txt`
- 其它服务请参考其目录下的 requirements 文件

4) 运行统一管道（与 docker 中的行为一致）
```bash
# 通过环境变量传入端点和脚本列表
export MCP_ENDPOINT="wss://.../mcp/?token=..."
export MCP_SCRIPTS="calculator.py notepad_mcp/notepad_mcp_fixed.py xiaozhi-websearch/websearch_optimized.py server_mcp_vps/server_mcp.py"
python mcp_pipe.py $MCP_SCRIPTS
```
- 或在 bash 下使用脚本：`bash scripts/start_mcp_pipe.sh`

---

## 新增/移除 MCP 服务 | Add/Remove MCP Services

1) 新增脚本与依赖
- 放置脚本：例如 `my_mcp/my_tool.py`
- 准备依赖（任选其一命中即可）：
  - `my_mcp/requirements.txt`
  - `my_mcp/requirements-my_tool.txt`
  - `my_mcp/requirements.my_tool.txt`
  - 根目录脚本可用：`requirements-my_tool.txt` 或 `requirements.my_tool.txt`

2) 加入统一管道
- 在 .env 的 `MCP_SCRIPTS` 追加脚本路径（以空格分隔）
- 重启容器：`docker restart mcp-pipe`
- 观察日志至“Successfully connected to WebSocket server”

3) 临时移除
- 从 `MCP_SCRIPTS` 删除对应脚本路径，重启即可

---

## 常见问题与排障 | Troubleshooting

- ModuleNotFoundError（mcp/fastmcp/redis）：
  - 启动脚本会先装 mcp/fastmcp/redis；若仍失败，检查网络与镜像源
- 4004 Internal server error：
  - 多由子进程启动后立刻异常退出引起；查看之前日志行找具体异常（如 ImportError、SyntaxError）
- 依赖下载超时/速度慢：
  - 在 `.env` 中设置：
    - `PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple`
    - `PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn`
- profiles 不可用：
  - 使用 `docker compose up -d redis mcp-pipe` 启动

---

## 生产优化 | Production Optimization

目标：缩短冷启动时间、提升稳定性与可观测性、减少对外网依赖。

1) 预装依赖镜像（推荐）
- 将常用依赖 bake 进 mcp-pipe 镜像，运行时无需 pip：
  - 在 `mcp-pipe/Dockerfile` 中新增：
    - `RUN python -m pip install --no-cache-dir mcp fastmcp redis \
       && python -m pip install --no-cache-dir -r notepad_mcp/requirements.txt \
       && python -m pip install --no-cache-dir -r requirements-calculator.txt`
  - 如需包含 websearch：再追加 `-r xiaozhi-websearch/requirements.txt`
  - 构建：`docker compose build mcp-pipe`
- 优点：冷启动秒级；缺点：镜像体积增大、更新需重建

2) 本地 PyPI 代理/缓存（可选）
- 在无预装镜像方案时，使用私有缓存（如 devpi、pypiserver、sonatype）
- 在 `.env` 中指向你的代理：`PIP_INDEX_URL` 与 `PIP_TRUSTED_HOST`

3) 健康检查与重启策略
- 在 docker-compose.yml 中为 mcp-pipe 增加 healthcheck（若未设置）：
  - `CMD-SHELL: python -c 'import socket; print(1)'`
  - 或定制：探测 mcp_pipe 的主循环/网关握手日志
- 配置 `restart: unless-stopped`

4) 资源与并发
- 为 mcp-pipe 限制 CPU/内存（避免与其它服务抢占）：
  - `deploy.resources.limits.cpus: "1.0"`
  - `deploy.resources.limits.memory: 1g`
- 按需拆分重型 MCP 到独立容器运行（仍可沿用 stdio 模式，经 mcp-pipe 管理）

5) 日志与监控
- 将容器日志接入 Loki/ELK：保留安装日志与运行时调用记录
- 为关键事件打点：首次依赖安装完成、与网关成功握手、子进程异常重启

6) 配置管理
- 仅通过 `.env` 维护运行时配置（MCP_SCRIPTS、MCP_ENDPOINT、镜像源等）
- 各 MCP 的依赖与代码同库管理，遵循本文“依赖命名规则”以确保自动安装命中

7) 回滚策略
- 镜像带版本标签；合并前在 staging 环境按本文“验证”步骤回归
- 遇到失败可快速回滚到上一个镜像或上一个 commit

8) 冷热切换与更新
- 更新 `.env` 或代码后：`docker compose up -d --no-build mcp-pipe`
- 大版本依赖变更：重建镜像并标注版本，分批上线

- Redis 监听器：
  - `ENABLE_REDIS_LISTENER=true|false` 控制 notepad 的跨服务通信监听

---

## 验证 | Verification

- 网关页面显示“在线”，并出现相应工具名称（如 calculator、notepad_manager 等）
- 容器日志出现：`Successfully connected to WebSocket server`

---

## 变更摘要 | What We Changed

- 引入统一管道 mcp-pipe，支持多 MCP 子服务托管（stdio）
- 动态依赖安装机制，支持多种 requirements 命名规则
- 预装并重试安装关键依赖（mcp、fastmcp、redis），提升首次成功率
- 文档清晰化：Docker/源码双路径、问题排查
