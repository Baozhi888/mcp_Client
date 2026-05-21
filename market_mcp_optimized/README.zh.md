# Market MCP Optimized

Market MCP Optimized 是一个经过重构和优化的金融市场数据服务，专为MCP (Model Context Protocol) 环境设计。

## 功能特性

- **多数据源支持**: 集成新浪财经和TuShare双数据源
- **实时行情查询**: 支持股票、外汇、期货等实时价格查询
- **K线数据服务**: 提供多种周期的K线图表数据
- **板块分析工具**: 支持板块成分股和行业龙头股分析
- **智能缓存机制**: 显著提升数据访问性能
- **错误处理和重试**: 增强服务稳定性和可靠性

## 快速开始

1. 安装依赖:
   ```bash
   pip install -r requirements.txt
   ```

2. 配置环境变量:
   ```bash
   export MCP_ENDPOINT=wss://your-mcp-endpoint.com
   ```

3. 启动服务:
   ```bash
   python market_mcp_fixed.py
   ```

## 文档

- [部署指南](DEPLOYMENT_GUIDE.md)
- [API文档](README.md)
- [更新日志](CHANGELOG.md)

## 许可证

[MIT License](LICENSE)