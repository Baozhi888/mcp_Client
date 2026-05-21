# Market MCP 优化版本部署文档

## 1. 环境要求

### 操作系统
- Linux (Ubuntu 18.04+ 或 CentOS 7+)
- Windows 10+ (推荐使用WSL2)
- macOS 10.15+

### Python环境
- Python 3.8+
- pip 21.0+
- virtualenv 或 conda

### 系统依赖
- git 2.20+
- gcc (编译某些Python包时需要)
- libffi-dev (某些Linux发行版需要)

### 网络要求
- 能够访问新浪股票API (hq.sinajs.cn)
- 能够访问TuShare API (可选，需要API密钥)
- 能够连接到MCP管道服务

### 第三方API密钥
- TUSHARE_TOKEN (可选，用于访问专业数据)
- MCP_ENDPOINT (必须，MCP服务端点)

## 2. 安装步骤

### 克隆代码库
```bash
git clone <repository-url>
cd market_mcp_optimized
```

### 创建Python虚拟环境
```bash
# 使用virtualenv
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# 或
.venv\Scripts\activate     # Windows

# 或使用conda
conda create -n market_mcp python=3.9
conda activate market_mcp
```

### 安装依赖
```bash
pip install -r requirements.txt
```

### 创建必要的目录结构
```bash
mkdir -p logs cache data
```

## 3. 配置说明

### 环境变量配置
创建 `.env` 文件在项目根目录：

```bash
# 基础配置
MCP_ENDPOINT=wss://your-mcp-endpoint.com
LOG_LEVEL=INFO

# TuShare配置 (可选)
TUSHARE_TOKEN=your_tushare_token_here

# 性能配置
MARKET_API_TIMEOUT=30
TUSHARE_TIMEOUT=60
CACHE_TTL=300

# Redis配置 (如果使用)
MCP_REDIS_HOST=localhost
MCP_REDIS_PORT=6380
MCP_REDIS_DB=2
```

### 重要配置项说明

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| MCP_ENDPOINT | 必须设置 | MCP服务端点URL |
| LOG_LEVEL | INFO | 日志级别 (DEBUG, INFO, WARNING, ERROR) |
| TUSHARE_TOKEN | None | TuShare API密钥 |
| MARKET_API_TIMEOUT | 30 | 市场API超时时间(秒) |
| TUSHARE_TIMEOUT | 60 | TuShare API超时时间(秒) |
| CACHE_TTL | 300 | 缓存过期时间(秒) |

## 4. 启动和停止服务

### 使用管理脚本启动/停止服务
```bash
# 启动服务
bash manage_mcp.sh start market_mcp_optimized

# 停止服务
bash manage_mcp.sh stop market_mcp_optimized

# 重启服务
bash manage_mcp.sh restart market_mcp_optimized

# 查看服务状态
bash manage_mcp.sh status market_mcp_optimized
```

### 手动启动/停止方法
```bash
# 启动服务
cd market_mcp_optimized
python market_mcp_fixed.py

# 在后台运行
nohup python market_mcp_fixed.py > logs/market_mcp.log 2>&1 &
```

### 服务状态检查命令
```bash
# 检查进程是否存在
ps aux | grep market_mcp_fixed

# 检查端口是否监听 (如果使用WebSocket)
netstat -tlnp | grep :端口号

# 查看日志
tail -f logs/market_mcp.log
```

## 5. 故障排除

### 常见问题及解决方案

#### 1. 无法连接到MCP端点
**问题**: 服务启动时报错 "Connection refused" 或 "Timeout"
**解决方案**: 
- 检查MCP_ENDPOINT配置是否正确
- 确认网络连接正常
- 检查防火墙设置

#### 2. TuShare初始化失败
**问题**: 日志显示 "TuShare not configured" 或 "Token invalid"
**解决方案**:
- 确认TUSHARE_TOKEN已正确设置
- 检查Token是否有效
- 确认TuShare账户权限

#### 3. 数据源访问失败
**问题**: 无法获取股票数据，返回空结果
**解决方案**:
- 检查网络连接
- 确认股票代码格式正确
- 查看是否触发了API频率限制

#### 4. 缓存相关问题
**问题**: 数据不更新或缓存错误
**解决方案**:
- 使用 `clear_market_data_cache` 工具清空缓存
- 调整CACHE_TTL参数
- 检查磁盘空间是否充足

### 日志分析方法
```bash
# 查看错误日志
grep -i "error" logs/market_mcp.log

# 查看警告日志
grep -i "warning" logs/market_mcp.log

# 实时监控日志
tail -f logs/market_mcp.log | grep -E "(ERROR|WARNING)"
```

### 常见错误日志模式识别

#### 网络错误
```
[ERROR] Network error in get_stock_realtime: Connection timeout
```
解决方案: 检查网络连接和API超时配置

#### 认证错误
```
[ERROR] Auth error in tushare_query: Invalid token
```
解决方案: 检查TUSHARE_TOKEN配置

#### 数据格式错误
```
[ERROR] Data error in parse_response: Invalid JSON format
```
解决方案: 检查数据源返回格式是否发生变化

## 6. 性能调优建议

### 缓存优化策略
1. **调整缓存TTL**: 根据数据更新频率调整CACHE_TTL
2. **缓存预热**: 在交易开始前预加载热门数据
3. **缓存清理**: 定期清理过期缓存释放内存

### 并发配置调整
```bash
# 调整批量查询并发数 (在代码中)
MAX_CONCURRENT_REQUESTS=10  # 默认值
```

### Redis性能优化
如果使用Redis:
1. 调整Redis内存策略
2. 使用连接池
3. 合理设置过期时间

### 数据源优先级调整
```python
# 在data_source_manager.py中调整优先级
priority_config = {
    'stock_realtime': [DataSourceType.SINA, DataSourceType.TUSHARE],  # 新浪优先
    'stock_kline': [DataSourceType.TUSHARE, DataSourceType.SINA],     # TuShare优先
}
```

## 7. 监控和日志

### 日志文件位置和级别说明
- 主日志文件: `logs/market_mcp.log`
- 错误日志: `logs/market_mcp_error.log`
- 访问日志: `logs/market_mcp_access.log`

### 监控指标定义
1. **API响应时间**: 平均响应时间应小于500ms
2. **缓存命中率**: 应保持在80%以上
3. **错误率**: 应低于1%
4. **数据源可用性**: 各数据源可用性应保持在99%以上

### 健康检查方法
```bash
# 使用MCP工具检查服务状态
mcp_call get_market_service_status

# 检查数据源健康状况
mcp_call get_data_source_health_report
```

## 8. API使用说明

### MCP工具列表

1. **query_stock_realtime_price**
   - 功能: 查询股票实时价格
   - 参数: symbol (股票代码)
   - 示例: `query_stock_realtime_price("600519")`

2. **query_multiple_symbols_batch**
   - 功能: 批量查询多个股票实时价格
   - 参数: symbols (股票代码列表)
   - 示例: `query_multiple_symbols_batch(["600519", "000001", "600036"])`

3. **query_kline_chart_data**
   - 功能: 查询K线图表数据
   - 参数: symbol, period, count
   - 示例: `query_kline_chart_data("600519", "day", 30)`

4. **query_forex_exchange_rate**
   - 功能: 查询外汇汇率
   - 参数: symbol (外汇代码)
   - 示例: `query_forex_exchange_rate("USD/CNY")`

5. **query_sector_constituent_stocks**
   - 功能: 查询板块成分股
   - 参数: sector (板块名称)
   - 示例: `query_sector_constituent_stocks("白酒")`

6. **get_market_service_status**
   - 功能: 获取市场服务状态
   - 示例: `get_market_service_status()`

7. **clear_market_data_cache**
   - 功能: 清空市场数据缓存
   - 示例: `clear_market_data_cache()`

### 数据源说明和切换机制

Market MCP优化版本支持多种数据源：
1. **新浪财经**: 免费，实时性好，适合实时行情
2. **TuShare**: 专业数据，需要API密钥，适合历史数据和专业分析

系统会根据配置的优先级自动选择数据源，并在主数据源失败时自动降级。

### 错误处理和性能建议

1. **重试机制**: 网络错误会自动重试，最多3次
2. **超时控制**: 各API调用都有合理的超时设置
3. **错误降级**: 数据源失败时自动切换到备用数据源
4. **缓存机制**: 减少重复API调用，提高响应速度