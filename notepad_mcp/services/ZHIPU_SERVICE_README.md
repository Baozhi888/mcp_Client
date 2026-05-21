# 智谱AI服务使用说明

## 简介

智谱AI服务为记事本MCP提供了图像识别功能，基于智谱AI的GLM-4V视觉模型，可以分析和描述图像内容。

## 功能特性

1. **图像识别**: 分析图像内容并生成描述
2. **服务健康检查**: 检查智谱AI服务连接状态
3. **错误处理**: 完善的错误处理和日志记录

## 环境配置

### API密钥设置

在项目根目录的 `.env` 文件中添加智谱AI API密钥：

```env
ZHIPU_API_KEY=your_api_key_here
```

## 使用方法

### 1. 图像识别

```python
# 使用工具调用方式
result = await zhipu_recognize_image(
    image_path="/path/to/your/image.jpg",
    prompt="请描述这张图片"
)
```

### 2. 服务健康检查

```python
# 检查服务状态
result = await zhipu_check_service_health()
```

## 工具函数说明

### zhipu_recognize_image

**参数**:
- `image_path` (str): 图像文件的路径
- `prompt` (str, 可选): 提示词，默认为"请描述这张图片"

**返回值**:
```json
{
  "success": true,
  "data": {
    "description": "图像内容描述",
    "model": "glm-4v",
    "usage": {
      "prompt_tokens": 123,
      "completion_tokens": 456,
      "total_tokens": 579
    }
  }
}
```

### zhipu_check_service_health

**返回值**:
```json
{
  "success": true,
  "status": "Healthy"
}
```

## 错误处理

服务包含完善的错误处理机制：
- API密钥缺失检查
- 文件存在性验证
- 网络请求超时处理
- 异常捕获和日志记录

## 测试

运行测试脚本验证服务功能：

```bash
python test_zhipu_service.py
```

## 依赖

- `requests`: HTTP请求库
- `base64`: 图像编码
- `logging`: 日志记录

## 注意事项

1. 确保图像文件路径正确且文件存在
2. API密钥需要在智谱AI平台申请
3. 图像文件大小应符合API限制
4. 网络连接正常以访问智谱AI API