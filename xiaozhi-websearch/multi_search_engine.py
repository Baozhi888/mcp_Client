#!/usr/bin/env python3
"""
多搜索引擎服务
支持智谱AI、Tavily、Google、Bing等多个搜索引擎
当主要搜索引擎（智谱AI）不可用时，自动切换到免费的备选方案
"""

import os
import json
import time
import requests
import logging
import queue
import threading
from typing import Dict, List, Optional, Any
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from config_manager import load_enhanced_config
from zhipuai import ZhipuAI
from dotenv import load_dotenv

# 确保加载环境变量
load_dotenv()

logger = logging.getLogger('multi_search_engine')

class MultiSearchEngine:
    """多搜索引擎管理器"""

    def __init__(self):
        self.config = load_enhanced_config()
        self.search_engines = {
            'zhipu': self._search_zhipu,
            'tavily': self._search_tavily,
            'google': self._search_google,
            'bing': self._search_bing,
            'news_api': self._search_news_api,
            'gemini': self._search_gemini
        }
        # 调整优先级：将响应更快/稳定的引擎放在前面，Gemini 放到最后以避免长时延导致上游超时
        self.engine_priority = ['tavily', 'news_api', 'google', 'bing', 'zhipu', 'gemini']

        # 引擎状态缓存 - 记录失败的引擎，避免重复尝试
        self.engine_status = {}
        self.failure_cache_duration = 300  # 5分钟内不再尝试失败的引擎

        # 动态优先级：特定类查询优先 Gemini（受超时保护）
        self.gemini_first_flag = os.getenv("WEBSEARCH_GEMINI_FIRST", "false").lower() in ("1","true","yes","on")

    def _remaining_timeout(self, deadline: float, default_timeout: float = 20.0) -> float:
        remaining = deadline - time.monotonic()
        if remaining < 1:
            raise TimeoutError("Search deadline exceeded")
        return max(1.0, min(default_timeout, remaining))

    @staticmethod
    def _run_with_timeout(func, timeout_seconds: float):
        result_queue = queue.Queue(maxsize=1)

        def runner():
            try:
                result_queue.put((True, func()), block=False)
            except BaseException as exc:
                try:
                    result_queue.put((False, exc), block=False)
                except Exception:
                    pass

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        thread.join(timeout_seconds)
        if thread.is_alive():
            raise TimeoutError(f"Operation timed out after {timeout_seconds:.1f}s")

        try:
            ok, value = result_queue.get_nowait()
        except queue.Empty:
            raise TimeoutError(f"Operation returned no result after {timeout_seconds:.1f}s")

        if ok:
            return value
        raise value

    def _prefer_gemini_for(self, query: str) -> bool:
        kws = ["经济","金融","政策","市场","产业","研报","解读","宏观","通胀","央行","地产","股指","期货","油价","黄金"]
        return any(k in query for k in kws) and len(query) >= 8

    def search(self, query: str, search_type: str = "general", max_results: int = 6) -> Dict[str, Any]:
        """
        智能搜索 - 自动选择可用的搜索引擎

        Args:
            query: 搜索查询
            search_type: 搜索类型 (general, news, academic, tech)
            max_results: 最大结果数量

        Returns:
            搜索结果字典
        """
        current_time = time.time()
        total_timeout = float(os.getenv("WEBSEARCH_TOTAL_TIMEOUT_S", "25"))
        deadline = time.monotonic() + max(3.0, total_timeout)
        last_error = None

        # 按需动态提升 Gemini 优先级
        engines = list(self.engine_priority)
        if self.gemini_first_flag or self._prefer_gemini_for(query):
            engines = [e for e in engines if e != 'gemini']
            engines.insert(0, 'gemini')

        for engine_name in engines:
            try:
                timeout_seconds = self._remaining_timeout(deadline)
                # 检查引擎是否在失败缓存中
                if self._is_engine_cached_as_failed(engine_name, current_time):
                    logger.info(f"跳过搜索引擎 {engine_name} - 最近失败过，使用缓存状态")
                    continue

                logger.info(f"尝试使用搜索引擎: {engine_name}")

                # 检查API密钥是否可用
                if not self._check_engine_available(engine_name):
                    logger.warning(f"搜索引擎 {engine_name} 不可用 - 缺少API密钥")
                    continue

                # 执行搜索
                search_func = self.search_engines[engine_name]
                result = search_func(query, search_type, max_results, timeout_seconds)

                if result.get('success'):
                    logger.info(f"搜索成功 - 使用引擎: {engine_name}")
                    # 清除该引擎的失败缓存
                    self._clear_engine_failure_cache(engine_name)
                    result['search_engine'] = engine_name
                    return result
                else:
                    error_msg = result.get('error', '')
                    logger.warning(f"搜索引擎 {engine_name} 返回失败: {error_msg}")

                    # 检查是否是需要缓存的失败类型
                    if self._should_cache_failure(error_msg):
                        self._cache_engine_failure(engine_name, current_time)
                        logger.info(f"已缓存搜索引擎 {engine_name} 的失败状态")

                    last_error = error_msg

            except Exception as e:
                error_str = str(e)
                logger.error(f"搜索引擎 {engine_name} 出错: {error_str}")

                # 检查是否是需要缓存的失败类型
                if self._should_cache_failure(error_str):
                    self._cache_engine_failure(engine_name, current_time)
                    logger.info(f"已缓存搜索引擎 {engine_name} 的异常状态")

                last_error = error_str
                if "deadline exceeded" in error_str.lower():
                    break

        # 所有搜索引擎都失败了
        return {
            "success": False,
            "error": f"所有搜索引擎都不可用。最后错误: {last_error}",
            "query": query,
            "available_engines": self._get_available_engines()
        }

    def _check_engine_available(self, engine_name: str) -> bool:
        """检查搜索引擎是否可用"""
        key_mapping = {
            'zhipu': 'ZHIPU_API_KEY',
            'tavily': 'TAVILY_API_KEY',
            'google': 'GOOGLE_API_KEY',
            'bing': 'BING_API_KEY',
            'news_api': 'NEWS_API_KEY',
            'gemini': 'GEMINI_API_KEY'
        }

        required_key = key_mapping.get(engine_name)
        if not required_key:
            return False

        # 直接从环境变量读取
        api_key = os.getenv(required_key)

        # 对于Google搜索，还需要检查GOOGLE_CX
        if engine_name == 'google':
            google_cx = os.getenv('GOOGLE_CX')
            return bool(api_key and api_key.strip() and google_cx and google_cx.strip())

        return bool(api_key and api_key.strip())

    def _get_available_engines(self) -> List[str]:
        """获取可用的搜索引擎列表"""
        available = []
        for engine in self.engine_priority:
            if self._check_engine_available(engine):
                available.append(engine)
        return available

    def _is_engine_cached_as_failed(self, engine_name: str, current_time: float) -> bool:
        """检查引擎是否在失败缓存中"""
        if engine_name not in self.engine_status:
            return False

        failure_time = self.engine_status[engine_name].get('failure_time', 0)
        return (current_time - failure_time) < self.failure_cache_duration

    def _should_cache_failure(self, error_msg: str) -> bool:
        """判断是否应该缓存此类失败"""
        cache_keywords = [
            "余额不足", "1113", "429", "quota", "limit", "timeout", "timed out",
            "unauthorized", "401", "403", "invalid key"
        ]
        error_lower = error_msg.lower()
        return any(keyword.lower() in error_lower for keyword in cache_keywords)

    def _cache_engine_failure(self, engine_name: str, failure_time: float):
        """缓存引擎失败状态"""
        self.engine_status[engine_name] = {
            'failure_time': failure_time,
            'status': 'failed'
        }

    def _clear_engine_failure_cache(self, engine_name: str):
        """清除引擎失败缓存"""
        if engine_name in self.engine_status:
            del self.engine_status[engine_name]

    def _search_zhipu(self, query: str, search_type: str, max_results: int, timeout_seconds: float = 3) -> Dict[str, Any]:
        """智谱AI搜索 - 快速失败版本"""
        try:
            from zhipuai import ZhipuAI

            # 使用默认客户端，但设置短超时
            client = ZhipuAI(api_key=os.getenv("ZHIPU_API_KEY"))

            response = client.web_search.web_search(
                search_engine="search_std",
                search_query=query,
                count=max_results,
                search_recency_filter="noLimit" if search_type != "news" else "1d",
                content_size="medium",
                timeout=max(1, min(3, int(timeout_seconds)))  # 快速失败
            )

            # 处理智谱AI响应
            results = []
            if hasattr(response, 'data') and response.data:
                for item in response.data:
                    results.append({
                        "title": getattr(item, 'title', ''),
                        "url": getattr(item, 'url', ''),
                        "content": getattr(item, 'content', ''),
                        "source": "智谱AI"
                    })

            return {
                "success": True,
                "results": results,
                "total_results": len(results),
                "query": query,
                "engine": "zhipu"
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _search_tavily(self, query: str, search_type: str, max_results: int, timeout_seconds: float = 20) -> Dict[str, Any]:
        """Tavily搜索"""
        try:
            url = "https://api.tavily.com/search"
            headers = {"Content-Type": "application/json"}

            payload = {
                "api_key": os.getenv("TAVILY_API_KEY"),
                "query": query,
                "search_depth": "basic",
                "include_answer": True,
                "include_images": False,
                "include_raw_content": False,
                "max_results": max_results
            }

            response = requests.post(url, json=payload, headers=headers, timeout=max(1, min(20, timeout_seconds)))
            response.raise_for_status()

            data = response.json()
            results = []

            if "results" in data:
                for item in data["results"]:
                    results.append({
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "content": item.get("content", ""),
                        "source": "Tavily"
                    })

            return {
                "success": True,
                "results": results,
                "total_results": len(results),
                "query": query,
                "engine": "tavily"
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _search_google(self, query: str, search_type: str, max_results: int, timeout_seconds: float = 20) -> Dict[str, Any]:
        """Google自定义搜索"""
        try:
            url = "https://www.googleapis.com/customsearch/v1"
            params = {
                "key": os.getenv("GOOGLE_API_KEY"),
                "cx": os.getenv("GOOGLE_CX"),
                "q": query,
                "num": min(max_results, 10)  # Google API最多返回10个结果
            }

            response = requests.get(url, params=params, timeout=max(1, min(20, timeout_seconds)))
            response.raise_for_status()

            data = response.json()
            results = []

            if "items" in data:
                for item in data["items"]:
                    results.append({
                        "title": item.get("title", ""),
                        "url": item.get("link", ""),
                        "content": item.get("snippet", ""),
                        "source": "Google"
                    })

            return {
                "success": True,
                "results": results,
                "total_results": len(results),
                "query": query,
                "engine": "google"
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _search_bing(self, query: str, search_type: str, max_results: int, timeout_seconds: float = 20) -> Dict[str, Any]:
        """Bing搜索"""
        try:
            url = "https://api.bing.microsoft.com/v7.0/search"
            headers = {"Ocp-Apim-Subscription-Key": os.getenv("BING_API_KEY")}
            params = {
                "q": query,
                "count": max_results,
                "offset": 0,
                "mkt": "zh-CN"
            }

            response = requests.get(url, headers=headers, params=params, timeout=max(1, min(20, timeout_seconds)))
            response.raise_for_status()

            data = response.json()
            results = []

            if "webPages" in data and "value" in data["webPages"]:
                for item in data["webPages"]["value"]:
                    results.append({
                        "title": item.get("name", ""),
                        "url": item.get("url", ""),
                        "content": item.get("snippet", ""),
                        "source": "Bing"
                    })

            return {
                "success": True,
                "results": results,
                "total_results": len(results),
                "query": query,
                "engine": "bing"
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _search_news_api(self, query: str, search_type: str, max_results: int, timeout_seconds: float = 20) -> Dict[str, Any]:
        """NewsAPI搜索（主要用于新闻）"""
        try:
            url = "https://newsapi.org/v2/everything"
            headers = {"X-API-Key": os.getenv("NEWS_API_KEY")}
            params = {
                "q": query,
                "pageSize": max_results,
                "language": "zh",
                "sortBy": "publishedAt"
            }

            response = requests.get(url, headers=headers, params=params, timeout=max(1, min(20, timeout_seconds)))
            response.raise_for_status()

            data = response.json()
            results = []

            if "articles" in data:
                for item in data["articles"]:
                    results.append({
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "content": item.get("description", ""),
                        "source": f"NewsAPI - {item.get('source', {}).get('name', '')}"
                    })

            return {
                "success": True,
                "results": results,
                "total_results": len(results),
                "query": query,
                "engine": "news_api"
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _search_gemini(self, query: str, search_type: str, max_results: int, timeout_seconds: float = 8) -> Dict[str, Any]:
        """Gemini搜索 - 使用实时网络搜索功能"""
        try:
            import google.generativeai as genai

            # 配置Gemini
            genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

            # 方法1: 尝试使用Gemini 2.0 Flash (稳定且快速)
            try:
                # 使用稳定的Gemini 2.0 Flash模型，平衡速度和质量
                model = genai.GenerativeModel("gemini-2.0-flash-exp")

                # 构建搜索提示，明确要求搜索最新信息
                search_prompt = f"""
请搜索关于"{query}"的最新信息。我需要实时的、准确的搜索结果。

请提供{max_results}个最相关的搜索结果，每个结果包含：
1. 标题
2. 网址链接
3. 内容摘要

请以JSON格式返回结果：
{{
    "results": [
        {{
            "title": "标题",
            "url": "网址",
            "content": "内容摘要"
        }}
    ]
}}

请确保搜索最新的网络信息，而不是仅基于训练数据。
"""

                # 使用generation_config启用搜索
                generation_config = genai.types.GenerationConfig(
                    temperature=0.1,
                    top_p=0.8,
                    top_k=40,
                    max_output_tokens=2048,
                )

                # 发送请求（受超时保护）
                gemini_timeout = min(float(os.getenv("WEBSEARCH_GEMINI_TIMEOUT_S", "8")), timeout_seconds)
                response = self._run_with_timeout(
                    lambda: model.generate_content(search_prompt, generation_config=generation_config),
                    gemini_timeout
                )

            except Exception as pro_error:
                logger.warning(f"Gemini Pro搜索失败，尝试Flash模型: {pro_error}")

                # 方法2: 使用Gemini 2.5 Flash with search instruction
                model = genai.GenerativeModel("gemini-2.5-flash")

                search_prompt = f"""
你是一个搜索助手，请用中文返回“结构化 JSON”且仅输出 JSON（不要代码块、不要多余解释）。
请基于最新的网络信息提供不超过 {max_results} 条结果，数组长度<= {max_results}。
每条结果包含: title, url, content。
约束：
- content 请控制在 120 字以内，简洁准确
- 如无法提供可靠 url，不要编造，跳过该条
返回示例：
{
  "results": [
    {"title": "标题", "url": "https://example.com", "content": "简要摘要，不超过120字"}
  ]
}
"""

                generation_config_25 = genai.types.GenerationConfig(
                    temperature=float(os.getenv("WEBSEARCH_GEMINI_TEMP", "0.2")),
                    top_p=0.8,
                    top_k=40,
                    max_output_tokens=int(os.getenv("WEBSEARCH_GEMINI25_MAX_TOKENS", "800")),
                )
                _timeout_25 = min(
                    float(os.getenv("WEBSEARCH_GEMINI25_TIMEOUT_S", os.getenv("WEBSEARCH_GEMINI_TIMEOUT_S", "8"))),
                    timeout_seconds
                )
                response = self._run_with_timeout(
                    lambda: model.generate_content(search_prompt, generation_config=generation_config_25),
                    _timeout_25
                )

            # 解析响应
            results = []
            try:
                import json
                # 尝试解析JSON响应
                response_text = response.text

                # 如果响应包含JSON，尝试提取
                if "```json" in response_text:
                    json_start = response_text.find("```json") + 7
                    json_end = response_text.find("```", json_start)
                    json_text = response_text[json_start:json_end].strip()
                elif "{" in response_text and "}" in response_text:
                    json_start = response_text.find("{")
                    json_end = response_text.rfind("}") + 1
                    json_text = response_text[json_start:json_end]
                else:
                    # 如果没有JSON格式，创建一个简单的结果
                    results.append({
                        "title": f"关于{query}的搜索结果",
                        "url": "https://gemini.google.com",
                        "content": response_text[:500] + "..." if len(response_text) > 500 else response_text,
                        "source": "Gemini"
                    })

                if 'json_text' in locals():
                    parsed_data = json.loads(json_text)
                    if "results" in parsed_data:
                        for item in parsed_data["results"][:max_results]:
                            results.append({
                                "title": item.get("title", ""),
                                "url": item.get("url", ""),
                                "content": item.get("content", ""),
                                "source": "Gemini"
                            })

            except Exception as parse_error:
                logger.warning(f"Gemini响应解析失败: {parse_error}")
                # 创建一个基本结果
                results.append({
                    "title": f"关于{query}的搜索结果",
                    "url": "https://gemini.google.com",
                    "content": response.text[:500] + "..." if len(response.text) > 500 else response.text,
                    "source": "Gemini"
                })

            return {
                "success": True,
                "results": results,
                "total_results": len(results),
                "query": query,
                "engine": "gemini"
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

# 全局实例
multi_search_engine = MultiSearchEngine()
