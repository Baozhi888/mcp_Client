market_mcp_optimized/
├── __init__.py
├── market_mcp_fixed.py
├── DEPLOYMENT_GUIDE.md
├── config/
│   ├── __init__.py
│   └── config.py
├── models/
│   ├── __init__.py
│   └── market_models.py
├── services/
│   ├── __init__.py
│   ├── market_service.py
│   ├── cache_service.py
│   ├── error_handler.py
│   └── retry_manager.py
├── data/
│   ├── __init__.py
│   └── adapters/
│       ├── __init__.py
│       ├── tushare_adapter.py
│       ├── sina_adapter.py
│       └── data_source_manager.py
├── core/
│   ├── __init__.py
│   └── mcp_tools.py
├── routers/
│   ├── __init__.py
│   └── market_routes.py
├── utils/
│   ├── __init__.py
│   └── helpers.py
└── tests/
    ├── __init__.py
    └── test_market_mcp.py