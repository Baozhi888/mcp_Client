# 🔧 Redis跨MCP服务通信配置指南

## 📋 概述

基于您的问题，我推荐使用 **Redis消息队列方案** 作为跨MCP服务通信的最优解决方案。

## 🎯 为什么选择Redis方案？

### ✅ **Redis方案优势**
1. **性能优秀** - 内存存储，毫秒级响应
2. **可靠性高** - 支持持久化，数据不丢失
3. **功能丰富** - 支持阻塞队列、发布订阅、过期时间
4. **易于扩展** - 支持集群，可水平扩展
5. **生态成熟** - Python客户端稳定，文档完善
6. **调试友好** - 可视化工具多，便于监控

### ❌ **其他方案局限**
- **共享数据库**: SQLite在高并发下有锁竞争，性能较差
- **文件系统**: 依赖文件I/O，Windows权限问题，无法处理并发

## 🛠️ Redis安装配置

### Windows安装
```bash
# 1. 下载Redis for Windows
# https://github.com/microsoftarchive/redis/releases

# 2. 解压并启动
redis-server.exe

# 3. 测试连接
redis-cli.exe
ping
# 应该返回 PONG
```

### Python依赖安装
```bash
pip install redis
```

## 🔄 通信架构

```
WebSearch Service          Redis Queue          Notepad Service
     ↓                         ↓                       ↓
1. 生成请求ID              2. 存储请求           3. 监听队列
2. 发送到队列              3. 阻塞等待           4. 处理请求
3. 等待响应                4. 返回结果           5. 发送响应
```

## 📝 实现示例

### WebSearch服务端（发送请求）
```python
import redis
import json
import uuid

def call_notepad_service_sync(action: str, **kwargs) -> dict:
    """通过Redis调用notepad服务"""
    try:
        # 连接Redis
        r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        
        # 生成请求ID
        request_id = str(uuid.uuid4())
        
        # 构建请求
        request = {
            "id": request_id,
            "service": "notepad",
            "action": action,
            "params": kwargs,
            "timestamp": datetime.now().isoformat(),
            "from_service": "websearch"
        }
        
        # 发送请求到队列
        r.lpush("notepad_requests", json.dumps(request, ensure_ascii=False))
        
        # 等待响应（阻塞30秒）
        response = r.brpop(f"response_{request_id}", timeout=30)
        
        if response:
            return json.loads(response[1])
        else:
            return {"success": False, "error": "请求超时"}
            
    except Exception as e:
        return {"success": False, "error": str(e)}
```

### Notepad服务端（处理请求）
```python
import redis
import json
import threading

class NotepadServiceHandler:
    def __init__(self):
        self.redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        self.running = True
    
    def start_listener(self):
        """启动请求监听器"""
        thread = threading.Thread(target=self._listen_requests)
        thread.daemon = True
        thread.start()
    
    def _listen_requests(self):
        """监听并处理请求"""
        while self.running:
            try:
                # 阻塞等待请求
                result = self.redis_client.brpop("notepad_requests", timeout=1)
                if result:
                    request_data = json.loads(result[1])
                    self._process_request(request_data)
            except Exception as e:
                logger.error(f"处理请求失败: {e}")
    
    def _process_request(self, request_data):
        """处理具体请求"""
        try:
            request_id = request_data["id"]
            action = request_data["action"]
            params = request_data["params"]
            
            # 根据action执行相应操作
            if action == "create":
                result = self._create_note(**params)
            elif action == "get_file":
                result = self._get_file(**params)
            # ... 其他操作
            else:
                result = {"success": False, "error": f"未知操作: {action}"}
            
            # 发送响应
            self.redis_client.lpush(f"response_{request_id}", json.dumps(result, ensure_ascii=False))
            
        except Exception as e:
            # 发送错误响应
            error_response = {"success": False, "error": str(e)}
            self.redis_client.lpush(f"response_{request_id}", json.dumps(error_response, ensure_ascii=False))

# 在notepad服务启动时初始化
handler = NotepadServiceHandler()
handler.start_listener()
```

## 🚀 部署步骤

### 1. 启动Redis服务
```bash
# Windows
redis-server.exe

# Linux/Mac
redis-server
```

### 2. 修改notepad服务
在 `notepad_mcp_fixed.py` 中添加Redis监听器：
```python
# 在文件末尾添加
if __name__ == "__main__":
    # 启动Redis监听器
    handler = NotepadServiceHandler()
    handler.start_listener()
    
    # 启动MCP服务
    mcp.run(transport="stdio")
```

### 3. 使用生产版本websearch
```bash
cd xiaozhi-websearch
cp websearch_production.py websearch_enhanced.py
```

### 4. 重启MCP服务
```bash
./manage_mcp.sh stop
./manage_mcp.sh start
```

## 🔍 测试验证

### 测试Redis连接
```python
import redis

try:
    r = redis.Redis(host='localhost', port=6379, db=0)
    r.ping()
    print("✅ Redis连接成功")
except Exception as e:
    print(f"❌ Redis连接失败: {e}")
```

### 测试跨服务通信
```python
# 在websearch服务中测试
result = call_notepad_service_sync("test_connection")
print(f"测试结果: {result}")
```

## 📊 监控和调试

### Redis命令行监控
```bash
# 查看队列长度
redis-cli llen notepad_requests

# 查看所有键
redis-cli keys "*"

# 监控实时命令
redis-cli monitor
```

### Python监控脚本
```python
import redis
import time

r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

while True:
    queue_length = r.llen("notepad_requests")
    response_keys = r.keys("response_*")
    
    print(f"队列长度: {queue_length}, 待处理响应: {len(response_keys)}")
    time.sleep(5)
```

## ⚠️ 注意事项

1. **Redis服务必须先启动** - 确保Redis在MCP服务启动前运行
2. **超时设置合理** - 建议设置30秒超时，避免长时间阻塞
3. **错误处理完善** - 确保所有异常都有适当的错误响应
4. **资源清理** - 定期清理过期的响应键，避免内存泄漏
5. **安全考虑** - 生产环境建议设置Redis密码和访问控制

## 🎉 总结

Redis方案是跨MCP服务通信的最优选择，具有：
- ✅ 高性能和可靠性
- ✅ 简单易实现
- ✅ 便于调试和监控
- ✅ 良好的扩展性

按照本指南配置后，您的websearch服务将能够真正与notepad服务进行通信，实现完整的跨服务集成功能。
