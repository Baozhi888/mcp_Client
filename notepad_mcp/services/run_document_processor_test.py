#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文档处理器测试脚本
"""

import os
import sys
import tempfile
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from notepad_mcp.services.document_processor import DocumentProcessor, extract_document_content


def test_document_processor():
    """测试文档处理器功能"""
    print("开始测试文档处理器...")
    
    # 创建处理器实例
    processor = DocumentProcessor()
    print("✓ DocumentProcessor实例创建成功")
    
    # 测试文本文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write("这是一个测试文本文件。\n第二行内容。")
        txt_file = f.name
    
    try:
        # 测试文件类型检测
        file_type = processor.get_file_type(txt_file)
        print(f"✓ 文件类型检测: {txt_file} -> {file_type}")
        
        # 测试内容提取
        content = extract_document_content(txt_file)
        print(f"✓ 文本文件内容提取: {content}")
        
        # 测试支持的扩展名
        extensions = processor.get_supported_extensions()
        print(f"✓ 支持的文件扩展名数量: {len(extensions)}")
        
        # 测试扩展名检查
        is_supported = processor.is_supported_extension('pdf')
        print(f"✓ PDF扩展名支持检查: {is_supported}")
        
        # 测试Markdown文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write("# 测试Markdown文件\n\n这是一个**加粗**的文本。")
            md_file = f.name
        
        md_content = extract_document_content(md_file)
        print(f"✓ Markdown文件内容提取: {md_content[:50]}...")
        
        # 清理测试文件
        os.unlink(txt_file)
        os.unlink(md_file)
        
        print("\n所有测试通过!")
        
    except Exception as e:
        print(f"测试过程中发生错误: {e}")
        # 确保清理测试文件
        if 'txt_file' in locals():
            os.unlink(txt_file)
        if 'md_file' in locals():
            os.unlink(md_file)
        return False
    
    return True


if __name__ == "__main__":
    success = test_document_processor()
    sys.exit(0 if success else 1)