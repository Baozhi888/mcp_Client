#!/usr/bin/env bash
set -euo pipefail

# 容器内自检脚本：
# 1) 检查 Redis 连通
# 2) 通过 Redis 触发一次 notepad ping

: "${MCP_REDIS_HOST:=redis}"
: "${MCP_REDIS_PORT:=6379}"
: "${MCP_REDIS_DB:=1}"
: "${MCP_REDIS_PASSWORD:=changeme}"

python - <<PY
import os, sys, time, uuid, json
import redis

host=os.getenv('MCP_REDIS_HOST','redis')
port=int(os.getenv('MCP_REDIS_PORT','6379'))
db=int(os.getenv('MCP_REDIS_DB','1'))
password=os.getenv('MCP_REDIS_PASSWORD','')

r = redis.Redis(host=host, port=port, db=db, password=password, decode_responses=True)
try:
    assert r.ping() is True, 'Redis ping failed'
    print('[SELFCHK] redis ping ok')
except Exception as e:
    print('[SELFCHK] redis ping error:', e)
    sys.exit(1)

# 触发一次 notepad_ping
request_id = str(uuid.uuid4())
request_key = 'notepad_requests'
response_key = f'response_{request_id}'
req = {
    'request_id': request_id,
    'command': 'notepad_ping',
    'timestamp': time.time()
}
r.lpush(request_key, json.dumps(req))

# 等待响应
msg = r.brpop(response_key, timeout=10)
if not msg:
    print('[SELFCHK] ping timeout (no response)')
    sys.exit(2)

_, data = msg
try:
    payload = json.loads(data)
except Exception:
    payload = {'raw': data}
print('[SELFCHK] ping response:', payload)
PY

