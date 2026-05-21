# server.py
from mcp.server.fastmcp import FastMCP
import sys
import logging

logger = logging.getLogger('log')

# Fix UTF-8 encoding for Windows console
if sys.platform == 'win32':
    sys.stderr.reconfigure(encoding='utf-8')
    sys.stdout.reconfigure(encoding='utf-8')

import math
import random
import requests
import traceback
from bs4 import BeautifulSoup
from zhipuai import ZhipuAI
from config_manager import load_config

# Create an MCP server·12
mcp = FastMCP("mcps")

# Add an addition tool
# 修改原有的ZhipuAI初始化
def optimize_search_results(content_list, max_total_size=8000):
    """
    优化搜索结果，确保总消息大小不超过WebSocket限制
    :param content_list: 原始搜索结果列表
    :param max_total_size: 最大总字符数
    :return: 优化后的结果列表
    """
    if not content_list:
        return content_list

    # 计算当前总大小
    total_size = sum(len(content) for content in content_list)

    if total_size <= max_total_size:
        return content_list

    # 如果超过限制，按比例缩减每条结果
    reduction_ratio = max_total_size / total_size
    optimized_list = []

    for content in content_list:
        # 计算每条内容应该保留的长度
        target_length = int(len(content) * reduction_ratio)
        target_length = max(target_length, 100)  # 至少保留100字符

        if len(content) > target_length:
            optimized_content = content[:target_length] + "..."
        else:
            optimized_content = content

        optimized_list.append(optimized_content)

    return optimized_list

@mcp.tool()
def intelligent_web_search_assistant(user_query: str) -> dict:
    """
    Intelligent Web Search Assistant - Automatically determines and executes the best search strategy
    智能联网搜索助手 - 自动判断并执行最佳搜索策略

    **核心功能**：当AI遇到以下情况时自动调用此工具：
    1. 用户询问的信息超出AI训练数据时间范围（2024年4月后）
    2. 用户询问实时信息：天气、股价、汇率、交通、时间等
    3. 用户询问最新动态：新闻、政策、技术发展、公司动态等
    4. 用户询问具体的当前状态：某人近况、某公司现状等
    5. AI知识库中没有相关信息或信息可能过时
    6. 用户明确要求搜索或查询最新信息

    **智能路由逻辑**：
    - 包含"新闻"、"时事"、"头条" → 优先使用Google新闻搜索
    - 需要多方观点的争议话题 → 使用综合新闻搜索
    - 一般信息查询 → 使用通用网络搜索

    **自动触发示例**：
    - "今天天气如何？" → 自动搜索天气信息
    - "最新AI发展动态" → 自动搜索AI新闻
    - "2024年发生了什么？" → 自动搜索2024年事件
    - "某某公司股价" → 自动搜索股价信息
    - "现在几点了？" → 自动搜索当前时间

    :param user_query: 用户的原始查询
    :return: 智能搜索结果
    """
    try:
        # 智能判断搜索类型
        query_lower = user_query.lower()

        # 学术文献关键词
        academic_keywords = ['论文', '文献', '研究', '学术', '期刊', '会议论文', '博士论文', '硕士论文',
                           'paper', 'research', 'study', 'journal', 'academic', 'scholar', 'thesis', 'dissertation']

        # 技术文档关键词
        tech_keywords = ['教程', '文档', '开发', '编程', 'API', '代码', '技术', '实现', '框架', '库',
                        'tutorial', 'documentation', 'development', 'programming', 'code', 'framework', 'library']

        # 新闻类关键词
        news_keywords = ['新闻', '时事', '头条', '最新消息', '突发', '热点', '今日新闻', '时政']

        # 多源新闻关键词
        multi_source_keywords = ['各大媒体', '国际媒体', '不同观点', '全面了解', '多方报道']

        # 智能路由判断
        if any(keyword in query_lower for keyword in academic_keywords):
            # 使用学术文献搜索
            return academic_literature_search(user_query)
        elif any(keyword in query_lower for keyword in tech_keywords):
            # 使用技术文档搜索
            return professional_technical_documentation_search(user_query)
        elif any(keyword in query_lower for keyword in multi_source_keywords):
            # 使用综合新闻搜索
            return comprehensive_news_search(user_query)
        elif any(keyword in query_lower for keyword in news_keywords):
            # 使用Google新闻搜索
            return google_news_search(user_query)
        else:
            # 使用通用搜索
            return 奇点联网搜索(user_query)

    except Exception as e:
        error_msg = f"智能联网助手失败: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
        return {"success": False, "error": error_msg, "query": user_query}


def 奇点联网搜索(query_text: str) -> dict:
    """
    实时网络搜索工具 - 自动获取最新信息

    **自动触发条件**：
    - 用户询问2024年后的任何信息、事件、新闻
    - 用户询问实时数据：股价、汇率、天气、交通等
    - 用户询问最新动态：科技新闻、政策变化、公司动态等
    - 用户询问具体的人物近况、公司最新情况
    - 用户询问当前时间、今天日期相关的信息
    - 当AI知识库中没有相关信息时
    - 用户明确要求搜索或查询最新信息

    **适用场景**：
    - "今天的天气怎么样？"
    - "最新的AI技术发展如何？"
    - "某某公司最近有什么新闻？"
    - "2024年发生了什么重要事件？"
    - "现在比特币价格多少？"
    - 任何需要实时或最新信息的查询

    :param query_text: 用户的查询内容
    :return: 搜索结果
    """
    try:
        config = load_config()
        client = ZhipuAI(api_key=config["ZHIPU_API_KEY"])

        logger.info(f"开始联网搜索，查询内容: {query_text}")

        response = client.web_search.web_search(
            search_engine="search_std",
            search_query=query_text,
            count=8,  # 减少返回结果数量，避免消息过大
            # search_domain_filter="www.sohu.com",  # 移除域名限制，允许搜索所有网站
            search_recency_filter="noLimit",  # 搜索指定日期范围内的内容
            content_size="medium",  # 控制网页摘要的字数，默认medium
            timeout=20, # 设置20秒超时
        )

        content_list = []
        if hasattr(response, 'search_result') and response.search_result:
            for result in response.search_result:
                if hasattr(result, 'content') and result.content:
                    # 限制每条结果的长度，避免消息过大
                    truncated_content = result.content[:500] + "..." if len(result.content) > 500 else result.content
                    content_list.append(truncated_content)

        # 优化结果大小
        content_list = optimize_search_results(content_list)

        logger.info(f"联网查询完成，获得 {len(content_list)} 条结果")
        return {"success": True, "result": content_list, "query": query_text}

    except Exception as e:
        error_msg = f"联网搜索失败: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
        return {"success": False, "error": error_msg, "query": query_text}

@mcp.tool()
def google_news_search(search_keywords: str) -> dict:
    """
    Google News Professional Search - Get authoritative news and information
    Google新闻专业搜索 - 获取权威新闻资讯

    **自动触发条件**：
    - 用户询问"新闻"、"最新消息"、"时事"
    - 用户询问突发事件、热点话题
    - 用户询问政治、经济、社会新闻
    - 用户询问国际新闻、时政动态
    - 用户询问"今天发生了什么"
    - 需要权威新闻源验证的信息

    **适用场景**：
    - "今天有什么重要新闻？"
    - "最新的国际新闻是什么？"
    - "某某事件的最新进展"
    - "今日头条新闻"
    - "时政新闻"

    :param query_text: 新闻搜索关键词
    :return: Google新闻搜索结果
    """
    try:
        config = load_config()
        client = ZhipuAI(api_key=config["ZHIPU_API_KEY"])

        logger.info(f"开始Google新闻搜索，查询内容: {query_text}")

        response = client.web_search.web_search(
            search_engine="search_std",
            search_query=f"{query_text} site:news.google.com OR site:google.com/news",
            count=8,  # 减少返回结果数量
            search_recency_filter="1d",  # 搜索最近1天的新闻
            content_size="medium",
            timeout=20, # 设置20秒超时
        )

        content_list = []
        if hasattr(response, 'search_result') and response.search_result:
            for result in response.search_result:
                if hasattr(result, 'content') and result.content:
                    # 限制每条结果的长度
                    truncated_content = result.content[:400] + "..." if len(result.content) > 400 else result.content
                    content_list.append(truncated_content)

        # 优化结果大小
        content_list = optimize_search_results(content_list)

        logger.info(f"Google新闻搜索完成，获得 {len(content_list)} 条结果")
        return {"success": True, "result": content_list, "query": query_text, "type": "google_news"}

    except Exception as e:
        error_msg = f"Google新闻搜索失败: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
        return {"success": False, "error": error_msg, "query": query_text, "type": "google_news"}


@mcp.tool()
def comprehensive_news_search(search_keywords: str) -> dict:
    """
    Multi-source News Aggregation Search - Comprehensive news gathering from multiple sources
    多源新闻聚合搜索 - 全面获取新闻资讯

    **自动触发条件**：
    - 用户需要多角度了解某个事件
    - 用户询问争议性话题需要多方观点
    - 用户询问国际新闻需要多国媒体报道
    - 用户询问重大事件的全面报道
    - 需要对比不同媒体的报道角度

    **适用场景**：
    - "各大媒体对某事件的报道"
    - "国际媒体怎么看这个问题"
    - "这个新闻的不同观点"
    - "全面了解某个事件"
    - 需要权威性和全面性的新闻信息

    :param query_text: 新闻搜索关键词
    :return: 综合新闻搜索结果
    """
    try:
        config = load_config()
        client = ZhipuAI(api_key=config["ZHIPU_API_KEY"])

        logger.info(f"开始综合新闻搜索，查询内容: {query_text}")

        # 搜索多个新闻源
        news_sites = "site:news.google.com OR site:bbc.com OR site:cnn.com OR site:reuters.com OR site:xinhuanet.com OR site:people.com.cn"

        response = client.web_search.web_search(
            search_engine="search_std",
            search_query=f"{query_text} ({news_sites})",
            count=8,  # 减少返回结果数量
            search_recency_filter="3d",  # 搜索最近3天的新闻
            content_size="medium",
            timeout=20, # 设置20秒超时
        )

        content_list = []
        if hasattr(response, 'search_result') and response.search_result:
            for result in response.search_result:
                if hasattr(result, 'content') and result.content:
                    # 限制每条结果的长度
                    truncated_content = result.content[:400] + "..." if len(result.content) > 400 else result.content
                    content_list.append(truncated_content)

        # 优化结果大小
        content_list = optimize_search_results(content_list)

        logger.info(f"综合新闻搜索完成，获得 {len(content_list)} 条结果")
        return {"success": True, "result": content_list, "query": query_text, "type": "comprehensive_news"}

    except Exception as e:
        error_msg = f"综合新闻搜索失败: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
        return {"success": False, "error": error_msg, "query": query_text, "type": "comprehensive_news"}


@mcp.tool()
def academic_literature_search(research_keywords: str) -> dict:
    """
    Academic Literature and Paper Professional Search - Get authoritative academic resources
    学术文献与论文专业搜索 - 获取权威学术资源

    **自动触发条件**：
    - 用户询问学术论文、研究文献、期刊文章
    - 用户询问科研成果、学术观点、理论研究
    - 用户询问"有什么相关研究"、"学术界怎么看"
    - 用户询问特定领域的最新研究进展
    - 用户需要引用权威学术资源
    - 用户询问博士论文、硕士论文、学位论文
    - 用户询问会议论文、期刊论文

    **适用场景**：
    - "人工智能领域有哪些重要论文？"
    - "关于机器学习的最新研究"
    - "某某理论的相关文献"
    - "这个领域的权威研究"
    - "最新的学术进展"
    - "博士论文研究方向"
    - "期刊文章推荐"

    **搜索范围**：
    - Google Scholar (学术搜索)
    - arXiv (预印本论文)
    - IEEE Xplore (工程技术)
    - PubMed (生物医学)
    - ResearchGate (学术社交)
    - 知网、万方等中文学术数据库

    :param query_text: 学术搜索关键词
    :return: 学术文献搜索结果
    """
    try:
        config = load_config()
        client = ZhipuAI(api_key=config["ZHIPU_API_KEY"])

        logger.info(f"开始学术文献搜索，查询内容: {query_text}")

        # 构建学术搜索查询，包含主要学术数据库和网站
        academic_sites = (
            "site:scholar.google.com OR "
            "site:arxiv.org OR "
            "site:ieee.org OR "
            "site:pubmed.ncbi.nlm.nih.gov OR "
            "site:researchgate.net OR "
            "site:cnki.net OR "
            "site:wanfangdata.com.cn OR "
            "site:semanticscholar.org OR "
            "site:jstor.org OR "
            "site:springer.com OR "
            "site:sciencedirect.com"
        )

        # 添加学术相关关键词
        academic_keywords = "论文 OR paper OR research OR study OR journal OR conference OR thesis OR dissertation"

        response = client.web_search.web_search(
            search_engine="search_std",
            search_query=f"({query_text}) AND ({academic_keywords}) ({academic_sites})",
            count=8,  # 减少返回结果数量，避免消息过大
            search_recency_filter="noLimit",  # 学术文献不限制时间
            content_size="high",  # 学术内容需要更详细的摘要
            timeout=60, # 学术搜索允许更长超时
        )

        content_list = []
        if hasattr(response, 'search_result') and response.search_result:
            for result in response.search_result:
                if hasattr(result, 'content') and result.content:
                    # 学术内容保留更多信息，但仍需限制
                    truncated_content = result.content[:500] + "..." if len(result.content) > 500 else result.content
                    content_list.append(truncated_content)

        # 优化结果大小
        content_list = optimize_search_results(content_list)  # 使用默认最大8000

        logger.info(f"学术文献搜索完成，获得 {len(content_list)} 条结果")
        return {"success": True, "result": content_list, "query": query_text, "type": "academic_search"}

    except Exception as e:
        error_msg = f"学术文献搜索失败: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
        return {"success": False, "error": error_msg, "query": query_text, "type": "academic_search"}


@mcp.tool()
def professional_technical_documentation_search(technical_keywords: str) -> dict:
    """
    Professional Technical Documentation Search - Get technical materials and development documentation
    专业技术文档搜索 - 获取技术资料和开发文档

    **自动触发条件**：
    - 用户询问编程技术、开发文档、API文档
    - 用户询问技术教程、编程指南、最佳实践
    - 用户询问开源项目、代码示例、技术规范
    - 用户询问软件使用手册、技术白皮书
    - 用户询问"怎么实现"、"如何开发"、"技术方案"

    **适用场景**：
    - "Python机器学习教程"
    - "React开发文档"
    - "某某API怎么使用"
    - "最佳编程实践"
    - "开源项目推荐"
    - "技术架构设计"

    **搜索范围**：
    - GitHub (开源代码)
    - Stack Overflow (技术问答)
    - 官方文档网站
    - 技术博客和教程网站

    :param query_text: 技术搜索关键词
    :return: 技术文档搜索结果
    """
    try:
        config = load_config()
        client = ZhipuAI(api_key=config["ZHIPU_API_KEY"])

        logger.info(f"开始专业技术文档搜索，查询内容: {query_text}")

        # 构建技术搜索查询
        tech_sites = (
            "site:github.com OR "
            "site:stackoverflow.com OR "
            "site:docs.python.org OR "
            "site:developer.mozilla.org OR "
            "site:reactjs.org OR "
            "site:nodejs.org OR "
            "site:tensorflow.org OR "
            "site:pytorch.org OR "
            "site:kubernetes.io OR "
            "site:docker.com OR "
            "site:medium.com OR "
            "site:dev.to OR "
            "site:csdn.net OR "
            "site:juejin.cn"
        )

        # 添加技术相关关键词
        tech_keywords = "tutorial OR documentation OR guide OR example OR code OR API OR framework OR library"

        response = client.web_search.web_search(
            search_engine="search_std",
            search_query=f"({query_text}) AND ({tech_keywords}) ({tech_sites})",
            count=8,  # 减少返回结果数量
            search_recency_filter="1y",  # 技术文档搜索最近1年的内容
            content_size="high",
            timeout=60, # 技术搜索允许更长超时
        )

        content_list = []
        if hasattr(response, 'search_result') and response.search_result:
            for result in response.search_result:
                if hasattr(result, 'content') and result.content:
                    # 技术文档保留适中的信息量
                    truncated_content = result.content[:500] + "..." if len(result.content) > 500 else result.content
                    content_list.append(truncated_content)

        # 优化结果大小
        content_list = optimize_search_results(content_list)

        logger.info(f"专业技术文档搜索完成，获得 {len(content_list)} 条结果")
        return {"success": True, "result": content_list, "query": query_text, "type": "tech_search"}

    except Exception as e:
        error_msg = f"专业技术文档搜索失败: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
        return {"success": False, "error": error_msg, "query": query_text, "type": "tech_search"}


@mcp.tool()
def search_and_save_to_notepad_optimized(search_query: str) -> dict:
    """
    Search and Save to Notepad (Optimized) - Execute web search and format results as complete Markdown document
    搜索并保存到笔记本(优化版) - 执行网络搜索，并将结果格式化为一篇完整的Markdown文档。

    This tool implements the best practice for "search-save-share" workflow, ensuring search result integrity,
    making it convenient for direct storage in notes or email sharing, avoiding content truncation by LLM.
    此工具是实现“搜索-保存-分享”流程的最佳实践，它确保了搜索结果的完整性，
    便于后续直接存入笔记或通过邮件发送，避免内容被LLM截断。

    参数:
        user_query: 用户的原始查询内容。

    返回:
        一个包含格式化文本的字典。
        {
            "success": bool,
            "formatted_text": str,  # Markdown格式的完整搜索结果
            "raw_results": list     # 原始搜索结果列表
        }
    """
    logger.info(f"开始执行搜索并格式化，查询: {user_query}")
    try:
        # 使用现有的智能联网助手来获取搜索结果
        search_result = intelligent_web_search_assistant(user_query)

        if not search_result.get("success"):
            return search_result

        raw_results = search_result.get("result", [])
        if not raw_results:
            return {"success": True, "formatted_text": f"# 关于“{user_query}”的搜索结果\n\n未找到相关内容。", "raw_results": []}

        # 将结果格式化为Markdown
        markdown_parts = [f"# 关于“{user_query}”的搜索结果\n"]
        for i, content in enumerate(raw_results, 1):
            markdown_parts.append(f"## 搜索结果 {i}\n")
            markdown_parts.append(content)
            markdown_parts.append("\n---\n")

        formatted_text = "\n".join(markdown_parts)

        logger.info(f"成功格式化 {len(raw_results)} 条搜索结果。")
        return {
            "success": True,
            "formatted_text": formatted_text,
            "raw_results": raw_results
        }

    except Exception as e:
        error_msg = f"搜索并格式化失败: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
        return {"success": False, "error": error_msg, "query": user_query}

# Start the server
if __name__ == "__main__":
    mcp.run(transport="stdio")
