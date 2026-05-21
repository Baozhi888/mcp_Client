#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebSearch Enhanced 生产版本测试脚本
测试所有集成工具的功能
"""

import sys
import json
import logging
from datetime import datetime

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('test_production')

def test_service_status():
    """测试服务状态检查"""
    print("🔍 测试服务状态检查...")
    try:
        from websearch_production import 检查服务连接状态
        result = 检查服务连接状态()
        print(f"✅ 服务状态检查: {result}")
        return result.get("success", False)
    except Exception as e:
        print(f"❌ 服务状态检查失败: {e}")
        return False

def test_service_config():
    """测试服务配置获取"""
    print("⚙️ 测试服务配置获取...")
    try:
        from websearch_production import 获取服务配置
        result = 获取服务配置()
        print(f"✅ 服务配置: {result}")
        return result.get("success", False)
    except Exception as e:
        print(f"❌ 服务配置获取失败: {e}")
        return False

def test_search_and_save():
    """测试搜索并保存到笔记本"""
    print("📝 测试搜索并保存到笔记本...")
    try:
        from websearch_production import 搜索并保存到笔记本
        result = 搜索并保存到笔记本(
            user_query="人工智能最新发展",
            note_title="AI发展测试笔记",
            category="测试分类"
        )
        print(f"✅ 搜索并保存: {result}")
        return result.get("success", False)
    except Exception as e:
        print(f"❌ 搜索并保存失败: {e}")
        return False

def test_search_and_email():
    """测试搜索并发送邮件"""
    print("📧 测试搜索并发送邮件...")
    try:
        from websearch_production import 搜索并发送邮件
        result = 搜索并发送邮件(
            user_query="区块链技术应用",
            to_email="test@example.com",
            subject="区块链技术测试邮件"
        )
        print(f"✅ 搜索并发送邮件: {result}")
        return result.get("success", False)
    except Exception as e:
        print(f"❌ 搜索并发送邮件失败: {e}")
        return False

def test_search_save_and_send():
    """测试搜索保存并发送"""
    print("🔄 测试搜索保存并发送...")
    try:
        from websearch_production import 搜索保存并发送
        result = 搜索保存并发送(
            user_query="量子计算发展趋势",
            to_email="test@example.com",
            note_title="量子计算测试笔记"
        )
        print(f"✅ 搜索保存并发送: {result}")
        return result.get("success", False)
    except Exception as e:
        print(f"❌ 搜索保存并发送失败: {e}")
        return False

def test_file_operations():
    """测试文件操作"""
    print("📁 测试文件操作...")
    try:
        from websearch_production import 发送笔记本文件邮件
        result = 发送笔记本文件邮件(
            file_id="test_file_123",
            to_email="test@example.com",
            subject="测试文件邮件"
        )
        print(f"✅ 文件操作: {result}")
        return result.get("success", False)
    except Exception as e:
        print(f"❌ 文件操作失败: {e}")
        return False

def test_multi_file_operations():
    """测试多文件操作"""
    print("📁📁 测试多文件操作...")
    try:
        from websearch_production import 发送多个笔记本文件邮件
        result = 发送多个笔记本文件邮件(
            file_ids=["file1", "file2", "file3"],
            to_email="test@example.com",
            subject="测试多文件邮件"
        )
        print(f"✅ 多文件操作: {result}")
        return result.get("success", False)
    except Exception as e:
        print(f"❌ 多文件操作失败: {e}")
        return False

def test_download_operations():
    """测试下载操作"""
    print("⬇️ 测试下载操作...")
    try:
        from websearch_production import download_file_from_url
        result = download_file_from_url(
            url="https://httpbin.org/json",
            filename="test.json"
        )
        print(f"✅ 下载操作: {result}")
        return result.get("success", False)
    except Exception as e:
        print(f"❌ 下载操作失败: {e}")
        return False

def test_intelligent_search():
    """测试智能搜索"""
    print("🧠 测试智能搜索...")
    try:
        from websearch_production import 智能联网助手
        result = 智能联网助手("Python编程最佳实践")
        print(f"✅ 智能搜索: {result}")
        return result.get("success", False)
    except Exception as e:
        print(f"❌ 智能搜索失败: {e}")
        return False

def run_all_tests():
    """运行所有测试"""
    print("🚀 开始WebSearch Enhanced生产版本测试")
    print("=" * 60)
    
    tests = [
        ("服务状态检查", test_service_status),
        ("服务配置获取", test_service_config),
        ("搜索并保存", test_search_and_save),
        ("搜索并发送邮件", test_search_and_email),
        ("搜索保存并发送", test_search_save_and_send),
        ("文件操作", test_file_operations),
        ("多文件操作", test_multi_file_operations),
        ("下载操作", test_download_operations),
        ("智能搜索", test_intelligent_search)
    ]
    
    results = []
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n📋 测试: {test_name}")
        print("-" * 40)
        
        try:
            success = test_func()
            results.append((test_name, success))
            if success:
                passed += 1
                print(f"✅ {test_name} - 通过")
            else:
                print(f"❌ {test_name} - 失败")
        except Exception as e:
            results.append((test_name, False))
            print(f"💥 {test_name} - 异常: {e}")
    
    # 测试结果汇总
    print("\n" + "=" * 60)
    print("📊 测试结果汇总")
    print("=" * 60)
    
    for test_name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"{test_name:<20} {status}")
    
    print("-" * 60)
    print(f"总计: {passed}/{total} 测试通过")
    print(f"成功率: {(passed/total)*100:.1f}%")
    
    if passed == total:
        print("🎉 所有测试通过！生产版本可以部署。")
        return True
    else:
        print("⚠️ 部分测试失败，请检查相关功能。")
        return False

def main():
    """主函数"""
    if len(sys.argv) > 1 and sys.argv[1] == "--help":
        print("WebSearch Enhanced 生产版本测试脚本")
        print("用法:")
        print("  python test_production.py        # 运行所有测试")
        print("  python test_production.py --help # 显示帮助")
        return
    
    try:
        success = run_all_tests()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⏹️ 测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 测试执行异常: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
