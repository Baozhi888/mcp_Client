#!/usr/bin/env python3
"""
智谱AI账户状态检查工具
检查API密钥有效性、余额、使用情况等
"""

import sys
import os
sys.path.append('.')
from config_manager import load_enhanced_config
from zhipuai import ZhipuAI

def check_zhipu_account():
    """检查智谱AI账户状态"""
    try:
        # 加载配置
        config = load_enhanced_config()
        api_key = config['ZHIPU_API_KEY']
        
        print("=" * 60)
        print("智谱AI账户状态检查")
        print("=" * 60)
        print(f"API密钥: {api_key[:20]}...")
        
        # 初始化客户端
        client = ZhipuAI(api_key=api_key)
        
        # 测试1: 检查API密钥有效性
        print("\n1. 检查API密钥有效性...")
        try:
            # 尝试调用一个简单的API来验证密钥
            response = client.chat.completions.create(
                model="glm-4-flash",  # 使用免费模型测试
                messages=[{"role": "user", "content": "你好"}],
                max_tokens=10
            )
            print("✅ API密钥有效")
        except Exception as e:
            if "余额不足" in str(e) or "1113" in str(e):
                print("⚠️  API密钥有效，但余额不足")
            elif "401" in str(e) or "Unauthorized" in str(e):
                print("❌ API密钥无效或已过期")
                return
            else:
                print(f"⚠️  API密钥状态未知: {e}")
        
        # 测试2: 检查web_search功能
        print("\n2. 检查web_search功能...")
        try:
            response = client.web_search.web_search(
                search_engine="search_std",
                search_query="测试",
                count=1,
                search_recency_filter="noLimit",
                content_size="medium",
                timeout=10
            )
            print("✅ web_search功能正常")
            print(f"搜索结果: {len(response.data) if hasattr(response, 'data') else '未知'}")
        except Exception as e:
            if "余额不足" in str(e) or "1113" in str(e):
                print("❌ web_search功能欠费 - 需要充值")
                print("错误详情:", str(e))
            elif "429" in str(e):
                print("❌ 达到使用限制或余额不足")
                print("错误详情:", str(e))
            else:
                print(f"❌ web_search功能异常: {e}")
        
        # 测试3: 检查免费模型
        print("\n3. 检查免费模型可用性...")
        free_models = ["glm-4-flash", "glm-3-turbo"]
        
        for model in free_models:
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": "测试"}],
                    max_tokens=5
                )
                print(f"✅ {model} 可用")
            except Exception as e:
                if "余额不足" in str(e):
                    print(f"❌ {model} 欠费")
                else:
                    print(f"⚠️  {model} 状态: {e}")
        
        print("\n" + "=" * 60)
        print("建议解决方案:")
        print("=" * 60)
        print("1. 登录智谱AI开放平台充值: https://open.bigmodel.cn/")
        print("2. web_search功能按次计费，约0.18-0.28元/次")
        print("3. 建议充值50-100元可使用较长时间")
        print("4. 或考虑使用其他免费搜索方案")
        
    except Exception as e:
        print(f"检查过程出错: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_zhipu_account()
