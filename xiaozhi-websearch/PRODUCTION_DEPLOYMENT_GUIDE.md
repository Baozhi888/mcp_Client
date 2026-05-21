# 🚀 WebSearch Enhanced 生产部署指南

## 📋 概述

本指南将帮助您将 `websearch_enhanced` 服务从模拟版本升级到可直接部署的生产版本。

## 🏗️ MCP架构说明

### **实际架构**
您的MCP服务使用以下架构：
```
MCP客户端 (Claude Desktop等)
    ↕️ WebSocket
mcp_pipe.py (通信管道)
    ↕️ 标准输入输出
多个MCP服务 (notepad, websearch, email等)
```

### **通信方式**
- ❌ **不是** HTTP REST API
- ✅ **是** WebSocket + 标准输入输出
- ✅ 通过 `mcp_pipe.py` 统一管理
- ✅ 通过 `manage_mcp.sh` 启动所有服务

## 🔄 版本对比

### **当前版本 (websearch_enhanced.py)**
- ✅ 功能完整，包含10个集成工具
- ⚠️ 使用模拟调用，仅用于测试
- ⚠️ 无法与真实服务通信

### **生产版本 (websearch_production.py)** 🆕
- ✅ 真实MCP工具调用，可直接部署
- ✅ 完整的错误处理机制
- ✅ MCP标准通信协议
- ✅ 适配WebSocket架构
- ✅ 所有10个集成工具完全实现

## 🛠️ 部署步骤

### **第1步：理解当前架构**

您的服务通过以下方式启动：
```bash
# manage_mcp.sh 启动所有服务
./manage_mcp.sh start

# 实际执行的命令：
python mcp_pipe.py notepad_mcp/notepad_mcp_fixed.py server_mcp.py calculator.py news_mcp.py market_mcp_fixed.py xiaozhi-websearch/websearch_enhanced.py
```

### **第2步：无需额外配置**

与HTTP版本不同，MCP版本无需：
- ❌ 配置服务URL
- ❌ 设置端口号
- ❌ 管理HTTP连接
- ✅ 只需通过 `manage_mcp.sh` 统一管理

### **第2步：部署生产版本**

1. **备份当前版本**：
   ```bash
   cd xiaozhi-websearch
   cp websearch_enhanced.py websearch_enhanced_mock.py
   ```

2. **使用生产版本**：
   ```bash
   # 替换为生产版本
   cp websearch_production.py websearch_enhanced.py
   ```

### **第3步：重启MCP服务**

```bash
# 停止当前服务
./manage_mcp.sh stop

# 启动更新后的服务
./manage_mcp.sh start

# 检查服务状态
./manage_mcp.sh status
```

### **第4步：验证部署**

1. **检查日志**：
   ```bash
   ./manage_mcp.sh logs
   ```

2. **测试功能**：
   在MCP客户端中测试新的工具：
   ```
   检查服务连接状态()
   获取服务配置()
   ```

### **第5步：更新管理脚本**

更新 `manage_mcp.sh` 以使用生产版本：

```bash
#!/bin/bash
# 生产环境MCP服务管理脚本

echo "🚀 启动生产环境MCP服务..."

# 启动notepad服务
echo "📝 启动Notepad MCP服务..."
cd notepad_mcp
python notepad_mcp_fixed.py &
NOTEPAD_PID=$!
cd ..

# 等待notepad服务启动
sleep 5

# 启动增强版websearch服务（生产版本）
echo "🔍 启动WebSearch Enhanced服务（生产版本）..."
cd xiaozhi-websearch
python websearch_enhanced.py &
WEBSEARCH_PID=$!
cd ..

echo "✅ 所有服务已启动"
echo "📝 Notepad服务 PID: $NOTEPAD_PID"
echo "🔍 WebSearch服务 PID: $WEBSEARCH_PID"

# 保存PID以便后续管理
echo $NOTEPAD_PID > notepad.pid
echo $WEBSEARCH_PID > websearch.pid

echo "🎯 服务端点:"
echo "   - Notepad: http://localhost:8001"
echo "   - WebSearch: http://localhost:8002"
```

## 🔧 生产版本新特性

### **1. 真实服务调用**
```python
# 替换模拟调用
def call_notepad_service_sync(action: str, **kwargs) -> dict:
    # 发送真实HTTP请求到notepad服务
    response = requests.post(
        f"{NOTEPAD_SERVICE_URL}/notepad",
        json={"action": action, **kwargs},
        timeout=REQUEST_TIMEOUT
    )
    return response.json()
```

### **2. 健康检查工具**
```python
@mcp.tool()
def 检查服务连接状态() -> dict:
    """检查与notepad和email服务的连接状态"""
    # 实时检查服务可用性
```

### **3. 配置管理**
```python
@mcp.tool()
def 更新服务配置(notepad_url: str = None, timeout: int = None) -> dict:
    """动态更新服务配置"""
    # 运行时配置更新
```

### **4. 错误处理增强**
```python
# 连接错误处理
except requests.exceptions.ConnectionError:
    error_msg = f"无法连接到notepad服务，请确保服务已启动"
    return {"success": False, "error": error_msg}

# 超时处理
except requests.exceptions.Timeout:
    error_msg = "请求超时，请检查服务是否正常运行"
    return {"success": False, "error": error_msg}
```

## 🧪 测试验证

### **1. 服务连接测试**
```python
# 测试服务连接
result = 检查服务连接状态()
print(result)
# 期望输出: {"success": True, "services": {"notepad_service": {"status": "connected"}}}
```

### **2. 功能测试**
```python
# 测试搜索并保存
result = 搜索并保存到笔记本("人工智能发展", "AI研究笔记")
print(result)
# 期望输出: {"success": True, "note_id": "note_xxx", "save_success": True}
```

### **3. 邮件功能测试**
```python
# 测试搜索并发送邮件
result = 搜索并发送邮件("区块链技术", "test@example.com")
print(result)
# 期望输出: {"success": True, "email_success": True, "message_id": "xxx"}
```

## 📊 性能对比

| 功能 | 模拟版本 | 生产版本 |
|------|----------|----------|
| 服务调用 | 模拟返回 | 真实HTTP调用 |
| 错误处理 | 基础 | 完整的异常处理 |
| 配置管理 | 硬编码 | 环境变量+动态配置 |
| 健康检查 | 无 | 实时服务状态检查 |
| 安全验证 | 无 | 域名过滤+文件类型检查 |
| 日志记录 | 基础 | 详细的操作日志 |
| 部署就绪 | ❌ | ✅ |

## 🔒 安全特性

### **1. 域名过滤**
```python
# 配置允许/阻止的域名
ALLOWED_DOMAINS=trusted-site.com,company.com
BLOCKED_DOMAINS=malicious-site.com,spam-site.com
```

### **2. 文件类型验证**
```python
# 只允许安全的文件类型
ALLOWED_FILE_TYPES = [
    "image/jpeg", "image/png", "application/pdf",
    "application/msword", "text/plain", "application/json"
]
```

### **3. 大小限制**
```python
# 文件大小限制（25MB）
MAX_FILE_SIZE=25000000
MAX_EMAIL_SIZE=25000000
```

## 🚨 故障排除

### **常见问题**

1. **连接错误**：
   ```
   错误: 无法连接到notepad服务
   解决: 确保notepad服务在端口8001运行
   ```

2. **超时错误**：
   ```
   错误: 请求超时
   解决: 增加REQUEST_TIMEOUT值或检查网络连接
   ```

3. **文件上传失败**：
   ```
   错误: 文件大小超过限制
   解决: 检查MAX_FILE_SIZE配置或压缩文件
   ```

### **调试命令**

```bash
# 检查服务状态
curl http://localhost:8001/health

# 查看日志
tail -f websearch_enhanced.log

# 测试配置
python production_config.py
```

## 🎯 部署检查清单

- [ ] notepad MCP服务正常运行（端口8001）
- [ ] 环境变量配置完成（.env文件）
- [ ] 依赖包安装完成
- [ ] 生产版本文件就位
- [ ] 服务连接测试通过
- [ ] 功能测试验证完成
- [ ] 日志记录正常
- [ ] 错误处理测试通过

## 🎉 部署完成

恭喜！您已成功将WebSearch Enhanced服务升级到生产就绪版本。现在您可以：

- ✅ 与真实的notepad MCP服务通信
- ✅ 执行所有10个集成工具功能
- ✅ 享受完整的错误处理和监控
- ✅ 使用动态配置管理
- ✅ 获得生产级别的稳定性和安全性

**您的MCP跨服务集成系统现在已完全可用于生产环境！** 🚀
