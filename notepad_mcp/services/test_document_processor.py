"""
文档处理器测试
"""

import os
import tempfile
from notepad_mcp.services.document_processor import DocumentProcessor, extract_document_content


def test_document_processor():
    """测试文档处理器功能"""
    processor = DocumentProcessor()
    
    # 创建测试文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("这是一个测试文本文件。\n第二行内容。")
        txt_file = f.name
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("# 测试Markdown文件\n\n这是一个**加粗**的文本。")
        md_file = f.name
    
    try:
        # 测试文本文件处理
        txt_content = extract_document_content(txt_file)
        print("文本文件内容:")
        print(txt_content)
        print()
        
        # 测试Markdown文件处理
        md_content = extract_document_content(md_file)
        print("Markdown文件内容:")
        print(md_content)
        print()
        
        # 测试支持的扩展名
        extensions = processor.get_supported_extensions()
        print("支持的文件扩展名:")
        for ext, type_name in list(extensions.items())[:10]:  # 只显示前10个
            print(f"  .{ext} -> {type_name}")
        print()
        
        # 测试文件类型检测
        txt_type = processor.get_file_type(txt_file)
        md_type = processor.get_file_type(md_file)
        print(f"文本文件类型: {txt_type}")
        print(f"Markdown文件类型: {md_type}")
        
    finally:
        # 清理测试文件
        os.unlink(txt_file)
        os.unlink(md_file)


if __name__ == "__main__":
    test_document_processor()