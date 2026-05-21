#!/usr/bin/env bash
set -euo pipefail

# 启动前提示
echo "[mcp-pipe] starting with scripts: ${MCP_SCRIPTS:-<not set>}"

# 容器内一般没有本机代理，避免 pip 误走 127.0.0.1 代理导致失败
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY || true

# 检查必要环境变量
if [ -z "${MCP_ENDPOINT:-}" ]; then
  echo "[mcp-pipe] ERROR: MCP_ENDPOINT is not set"
  exit 1
fi

# pip 安装重试函数，防超时与网络抖动
pip_retry() {
  local attempt=1
  local max_attempts=3
  local delay=3
  while true; do
    if python -m pip install --no-cache-dir --default-timeout 180 "$@"; then
      return 0
    fi
    if [ $attempt -ge $max_attempts ]; then
      echo "[deps] pip install failed after $attempt attempts: $*"
      return 1
    fi
    echo "[deps] pip install failed (attempt $attempt), retrying in ${delay}s: $*"
    sleep $delay
    attempt=$((attempt+1))
    delay=$((delay*2))
  done
}

# 默认脚本列表（可通过 MCP_SCRIPTS 覆盖），以空格分隔
DEFAULT_SCRIPTS="calculator.py notepad_mcp/notepad_mcp_fixed.py xiaozhi-websearch/websearch_optimized.py server_mcp_vps/server_mcp.py"
SCRIPTS=${MCP_SCRIPTS:-$DEFAULT_SCRIPTS}

# 动态为每个 MCP 脚本安装其依赖：
# 规则优先级（找到即用，避免重复安装同一文件）：
# 1) <script_dir>/requirements.txt（若脚本在子目录）
# 2) <script_dir>/requirements-<script_basename>.txt
# 3) <script_dir>/requirements.<script_basename>.txt
# 4) ./requirements-<script_basename>.txt（根目录旁）
# 5) ./requirements.<script_basename>.txt（根目录旁）
# 若均不存在，则已具备基础依赖（mcp/fastmcp/redis）

installed_list=""
install_reqs() {
  local req_path="$1"
  if echo " $installed_list " | grep -q " $req_path "; then
    echo "[deps] skip already installed: $req_path"
    return 0
  fi
  if [ -f "$req_path" ]; then
    echo "[deps] installing: $req_path"
    pip_retry -r "$req_path"
    installed_list="$installed_list $req_path"
    return 0
  fi
  return 1
}

if [ "${MCP_INSTALL_DEPS_ON_START:-false}" = "true" ]; then
  # 先安装基础依赖，避免 mcp/fastmcp/redis 缺失导致子进程 ImportError
  pip_retry mcp fastmcp redis || true

  for s in $SCRIPTS; do
    dir="$(dirname "$s")"
    basefile="$(basename "$s")"
    base="${basefile%.py}"

    echo "[deps] resolving for script: $s (dir=$dir, base=$base)"
    found=0

    if [ "$dir" != "." ]; then
      install_reqs "$dir/requirements.txt" && found=1 || true
      if [ $found -eq 0 ]; then install_reqs "$dir/requirements-$base.txt" && found=1 || true; fi
      if [ $found -eq 0 ]; then install_reqs "$dir/requirements.$base.txt" && found=1 || true; fi
    else
      # 根目录脚本（如 calculator.py）
      if [ $found -eq 0 ]; then install_reqs "requirements-$base.txt" && found=1 || true; fi
      if [ $found -eq 0 ]; then install_reqs "requirements.$base.txt" && found=1 || true; fi
    fi

  done
else
  echo "[deps] skip runtime pip install (set MCP_INSTALL_DEPS_ON_START=true to enable)"
fi

# 输出最终脚本列表
echo "[mcp-pipe] Using scripts: $SCRIPTS"

# 启动 mcp_pipe.py 托管多个 MCP 脚本（stdio 传输，对接远端 MCP Gateway）
exec python mcp_pipe.py $SCRIPTS
