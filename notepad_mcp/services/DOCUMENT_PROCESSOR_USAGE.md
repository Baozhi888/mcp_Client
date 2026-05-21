# 文档内容提取服务使用说明

## 简介

文档内容提取服务 (`document_processor.py`) 是一个用于从各种文档格式中提取文本内容的服务模块。它支持多种文件格式，包括PDF、Word、Excel、文本文件、Markdown文件和源代码文件。

## 支持的文件格式

- **文本文件**: .txt, .csv, .json, .xml, .html等
- **Markdown文件**: .md, .markdown
- **PDF文件**: .pdf
- **Word文档**: .docx
- **Excel文档**: .xlsx
- **源代码文件**: .py, .js, .java, .cpp, .c, .cs, .php, .rb, .go等

## 安装依赖

在使用文档处理器之前，请确保安装了必要的依赖：

```bash
pip install PyPDF2 python-docx openpyxl
```

## 使用方法

### 1. 基本用法

```python
from notepad_mcp.services.document_processor import extract_document_content

# 提取文档内容
content = extract_document_content("path/to/document.pdf")
if content:
    print(content)
else:
    print("无法提取文档内容")
```

### 2. 使用DocumentProcessor类

```python
from notepad_mcp.services.document_processor import DocumentProcessor

# 创建处理器实例
processor = DocumentProcessor()

# 提取文档内容
content = processor.extract_content("path/to/document.docx")

# 获取文件类型
file_type = processor.get_file_type("path/to/document.xlsx")
print(f"文件类型: {file_type}")

# 检查扩展名是否支持
is_supported = processor.is_supported_extension("pdf")
print(f"PDF支持: {is_supported}")
```

### 3. 错误处理

```python
from notepad_mcp.services.document_processor import extract_document_content
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)

try:
    content = extract_document_content("path/to/document.pdf")
    if content:
        print("文档内容提取成功")
        print(content[:100])  # 打印前100个字符
    else:
        print("文档内容提取失败")
except Exception as e:
    print(f"提取文档时发生错误: {e}")
```

## 注意事项

1. **依赖库**: 不同的文件格式需要不同的依赖库。确保安装了相应的库：
   - PDF处理需要 PyPDF2
   - Word文档处理需要 python-docx
   - Excel文档处理需要 openpyxl

2. **编码问题**: 文本文件会尝试多种编码格式（UTF-8, GBK, Latin-1）进行读取。

3. **大文件处理**: 对于大文件，处理可能需要一些时间，请适当处理超时和性能问题。

4. **权限问题**: 确保程序有读取目标文件的权限。

## 服务集成

文档处理器可以轻松集成到现有的MCP服务中：

```python
from fastmcp import FastMCP
from notepad_mcp.services.document_processor import extract_document_content

mcp = FastMCP()

@mcp.tool()
def process_document(file_path: str) -> str:
    """处理文档并提取内容"""
    content = extract_document_content(file_path)
    if content:
        return content
    else:
        return "无法处理文档"
```