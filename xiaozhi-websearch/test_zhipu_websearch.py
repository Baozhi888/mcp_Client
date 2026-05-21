#!/usr/bin/env python3
"""
测试智谱AI web搜索接口
验证使用chat.completions.create配合web_search工具的实现
"""

import os
import sys
import json
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

def test_zhipu_websearch_direct():
    """直接测试智谱AI web搜索接口"""
    try:
        from zhipuai import ZhipuAI
        
        api_key = os.getenv("ZHIPU_API_KEY")
        if not api_key:
            print("❌ 错误: 未找到ZHIPU_API_KEY环境变量")
            return False
            
        print(f"✅ 找到API密钥: {api_key[:8]}...")
        
        # 创建客户端
        client = ZhipuAI(api_key=api_key)
        
        # 测试查询
        test_query = "最新的科技新闻"
        print(f"🔍 测试查询: {test_query}")
        
        # 使用您提供的接口示例
        response = client.chat.completions.create(
            model="glm-4",
            messages=[
                {"role": "user", "content": test_query}
            ],
            tools=[
                {
                    "type": "web_search",
                    "web_search": {
                        "search_query": test_query,
                        "search_result": True,
                    }
                }
            ]
        )
        
        print("✅ API调用成功!")
        print(f"📊 响应类型: {type(response)}")
        
        # 分析响应结构
        if hasattr(response, 'choices') and response.choices:
            choice = response.choices[0]
            print(f"📝 Choice类型: {type(choice)}")
            
            if hasattr(choice, 'message'):
                message = choice.message
                print(f"💬 Message类型: {type(message)}")
                
                # 检查工具调用
                if hasattr(message, 'tool_calls') and message.tool_calls:
                    print(f"🔧 找到 {len(message.tool_calls)} 个工具调用")
                    
                    for i, tool_call in enumerate(message.tool_calls):
                        print(f"  工具调用 {i+1}:")
                        print(f"    类型: {tool_call.type}")
                        
                        if tool_call.type == "web_search":
                            print(f"    Web搜索结果类型: {type(tool_call.web_search)}")
                            if hasattr(tool_call.web_search, 'search_result'):
                                result = tool_call.web_search.search_result
                                print(f"    搜索结果长度: {len(str(result))}")
                                print(f"    搜索结果预览: {str(result)[:200]}...")
                                
                                # 尝试解析JSON
                                try:
                                    if isinstance(result, str):
                                        parsed = json.loads(result)
                                        print(f"    ✅ JSON解析成功, 类型: {type(parsed)}")
                                        if isinstance(parsed, list):
                                            print(f"    📋 结果数量: {len(parsed)}")
                                        elif isinstance(parsed, dict):
                                            print(f"    📋 结果键: {list(parsed.keys())}")
                                    else:
                                        print(f"    📋 结果类型: {type(result)}")
                                except json.JSONDecodeError as e:
                                    print(f"    ❌ JSON解析失败: {e}")
                else:
                    print("❌ 未找到工具调用")
                
                # 检查消息内容
                if hasattr(message, 'content') and message.content:
                    print(f"💬 消息内容长度: {len(message.content)}")
                    print(f"💬 消息内容预览: {message.content[:200]}...")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_multi_search_engine():
    """测试多搜索引擎中的智谱AI实现"""
    try:
        from multi_search_engine import multi_search_engine
        
        test_query = "人工智能最新发展"
        print(f"\n🔍 测试多搜索引擎: {test_query}")
        
        result = multi_search_engine._search_zhipu(test_query, "general", 3)
        
        print(f"✅ 搜索结果: {result.get('success', False)}")
        
        if result.get('success'):
            results = result.get('results', [])
            print(f"📋 找到 {len(results)} 个结果")
            
            for i, item in enumerate(results, 1):
                print(f"  结果 {i}:")
                print(f"    标题: {item.get('title', 'N/A')}")
                print(f"    URL: {item.get('url', 'N/A')}")
                print(f"    内容: {item.get('content', 'N/A')[:100]}...")
        else:
            print(f"❌ 搜索失败: {result.get('error', 'Unknown error')}")
            
        return result.get('success', False)
        
    except Exception as e:
        print(f"❌ 多搜索引擎测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🧪 智谱AI Web搜索接口测试")
    print("=" * 50)
    
    # 测试1: 直接API调用
    print("\n📋 测试1: 直接API调用")
    success1 = test_zhipu_websearch_direct()
    
    # 测试2: 多搜索引擎集成
    print("\n📋 测试2: 多搜索引擎集成")
    success2 = test_multi_search_engine()
    
    # 总结
    print("\n" + "=" * 50)
    print("🏁 测试总结:")
    print(f"  直接API调用: {'✅ 成功' if success1 else '❌ 失败'}")
    print(f"  多搜索引擎集成: {'✅ 成功' if success2 else '❌ 失败'}")
    
    if success1 and success2:
        print("🎉 所有测试通过! 智谱AI web搜索接口工作正常")
        sys.exit(0)
    else:
        print("⚠️  部分测试失败，请检查配置和实现")
        sys.exit(1)
