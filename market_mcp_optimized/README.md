# Market MCP Optimized - README

## 简介

Market MCP Optimized 是一个经过重构和优化的金融市场数据服务，专为MCP (Model Context Protocol) 环境设计。该服务提供了实时股票行情、K线数据、板块分析、外汇汇率、期货和宏观经济数据的查询功能。

## 主要特性

### 1. 多数据源支持
- **新浪财经**: 免费实时行情数据
- **TuShare**: 专业金融数据（需要API密钥）
- **智能切换**: 自动在数据源间切换以保证数据可用性

### 2. 核心功能模块

#### 实时行情管理
- 股票实时价格查询
- 外汇汇率查询
- 批量数据查询
- 市场概览和热门股票

#### K线数据管理
- 日K、周K、月K线数据
- 5分钟、15分钟、30分钟、60分钟K线
- 支持多种技术指标

#### 板块分析管理
- 板块成分股查询
- 行业龙头股分析
- 板块对比分析
- 概念股查询

#### 宏观数据管理
- GDP、CPI、PMI等宏观经济指标
- 资金流向分析
- 市场情绪指标

### 3. 性能优化
- **智能缓存**: 减少重复API调用，提高响应速度
- **并发处理**: 支持批量数据查询
- **连接池**: 优化网络连接管理
- **数据压缩**: 减少网络传输大小

### 4. 错误处理和可靠性
- **重试机制**: 网络错误自动重试
- **降级策略**: 数据源不可用时自动切换
- **健康检查**: 实时监控数据源状态
- **详细日志**: 便于问题诊断和性能分析

## 安装和部署

请参考 [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) 获取详细的安装和部署说明。

## 配置

### 环境变量
```bash
MCP_ENDPOINT=wss://your-mcp-endpoint.com
LOG_LEVEL=INFO
TUSHARE_TOKEN=your_tushare_token_here  # 可选
```

### 重要配置项
- `MCP_ENDPOINT`: MCP服务端点（必需）
- `LOG_LEVEL`: 日志级别（默认INFO）
- `TUSHARE_TOKEN`: TuShare API密钥（可选）

## 使用方法

### 启动服务
```bash
bash manage_mcp.sh start market_mcp_optimized
```

### MCP工具调用示例
```python
# 查询股票实时价格
query_stock_realtime_price("600519")

# 批量查询多只股票
query_multiple_symbols_batch(["600519", "000001", "600036"])

# 查询K线数据
query_kline_chart_data("600519", "day", 30)

# 查询板块成分股
query_sector_constituent_stocks("白酒")

# 查询外汇汇率
query_forex_exchange_rate("USD/CNY")
```

## API文档

### 核心工具

1. **query_stock_realtime_price(symbol: str)**
   - 查询单只股票实时价格
   - 参数: 股票代码（如 "600519"）
   - 返回: 实时行情数据

2. **query_multiple_symbols_batch(symbols: List[str])**
   - 批量查询多只股票
   - 参数: 股票代码列表
   - 返回: 批量查询结果

3. **query_kline_chart_data(symbol: str, period: str = 'day', count: int = 30)**
   - 查询K线图表数据
   - 参数: 股票代码，周期，数量
   - 返回: K线数据

4. **query_sector_constituent_stocks(sector: str)**
   - 查询板块成分股
   - 参数: 板块名称
   - 返回: 成分股列表

5. **query_forex_exchange_rate(symbol: str)**
   - 查询外汇汇率
   - 参数: 外汇代码（如 "USD/CNY"）
   - 返回: 汇率数据

6. **get_market_service_status()**
   - 获取服务状态
   - 返回: 服务健康状况报告

7. **clear_market_data_cache()**
   - 清空数据缓存
   - 返回: 清空结果

## 监控和维护

### 日志文件
- 主日志: `logs/market_mcp.log`
- 错误日志: `logs/market_mcp_error.log`

### 健康检查
```bash
# 检查服务状态
get_market_service_status()

# 检查数据源健康
get_data_source_health_report()
```

## 故障排除

请参考 [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) 中的故障排除部分获取常见问题的解决方案。

## 版本历史

请查看 [CHANGELOG.md](CHANGELOG.md) 获取详细的版本更新历史。

## 许可证

请查看项目根目录下的LICENSE文件。