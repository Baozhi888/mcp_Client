# Enhanced websearch with notepad and email integration - 简化版
from mcp.server.fastmcp import FastMCP
import sys
import logging
import json
import requests
from datetime import datetime
import traceback
from bs4 import BeautifulSoup

logger = logging.getLogger('websearch_enhanced')

# Fix UTF-8 encoding for Windows console
if sys.platform == 'win32':
    sys.stderr.reconfigure(encoding='utf-8')
    sys.stdout.reconfigure(encoding='utf-8')

# Create an MCP server
mcp = FastMCP("websearch_enhanced")

def call_notepad_service_sync(action: str, **kwargs) -> dict:
    """同步调用笔记本服务 - 简化版本"""
    try:
        # 在实际部署时，这里会通过mcp_pipe.py与notepad服务通信
        # 现在返回模拟的成功结果
        logger.info(f"模拟调用笔记本服务: {action}, 参数: {kwargs}")
        return {
            "success": True,
            "note_id": f"note_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "message": "笔记保存成功（模拟）"
        }
    except Exception as e:
        logger.error(f"调用笔记本服务失败: {e}")
        return {"success": False, "error": str(e)}

def call_email_service_sync(action: str, **kwargs) -> dict:
    """同步调用邮件服务 - 简化版本"""
    try:
        # 在实际部署时，这里会通过mcp_pipe.py与邮件服务通信
        # 现在返回模拟的成功结果
        logger.info(f"模拟调用邮件服务: {action}, 参数: {kwargs}")
        return {
            "success": True,
            "message": "邮件发送成功（模拟）"
        }
    except Exception as e:
        logger.error(f"调用邮件服务失败: {e}")
        return {"success": False, "error": str(e)}

def download_file_from_url(url: str, filename: str = None) -> dict:
    """从URL下载文件"""
    try:
        logger.info(f"开始下载文件: {url}")
        response = requests.get(url, timeout=30, stream=True)
        response.raise_for_status()

        # 获取文件名
        if not filename:
            from urllib.parse import urlparse
            parsed_url = urlparse(url)
            filename = parsed_url.path.split('/')[-1] or f"download_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # 获取内容类型
        content_type = response.headers.get('content-type', 'application/octet-stream')

        # 读取文件内容
        file_content = response.content
        file_size = len(file_content)

        # 编码为base64用于存储
        import base64
        encoded_content = base64.b64encode(file_content).decode('utf-8')

        logger.info(f"文件下载成功: {filename}, 大小: {file_size} bytes")

        return {
            "success": True,
            "filename": filename,
            "content": encoded_content,
            "content_type": content_type,
            "size": file_size
        }

    except Exception as e:
        logger.error(f"下载文件失败: {e}")
        return {"success": False, "error": str(e)}

def optimize_search_results(content_list, max_total_size=8000):
    """优化搜索结果，确保总消息大小不超过WebSocket限制"""
    if not content_list:
        return content_list

    total_size = sum(len(content) for content in content_list)
    if total_size <= max_total_size:
        return content_list

    reduction_ratio = max_total_size / total_size
    optimized_list = []

    for content in content_list:
        target_length = int(len(content) * reduction_ratio)
        target_length = max(target_length, 100)
        
        if len(content) <= target_length:
            optimized_list.append(content)
        else:
            optimized_content = content[:target_length-3] + "..."
            optimized_list.append(optimized_content)

    return optimized_list

@mcp.tool()
def 搜索并保存到笔记本(user_query: str, note_title: str = None, category: str = "搜索结果", tags: str = "搜索,网络") -> dict:
    """
    执行网络搜索并将结果直接保存到笔记本
    
    **功能说明**：
    - 执行智能网络搜索
    - 将搜索结果格式化为Markdown
    - 自动保存到笔记本系统
    - 返回笔记ID和搜索结果
    
    **参数**：
    - user_query: 搜索查询内容
    - note_title: 笔记标题（可选，默认基于查询生成）
    - category: 笔记分类（默认：搜索结果）
    - tags: 笔记标签（默认：搜索,网络）
    
    **返回**：包含搜索结果和笔记保存状态的字典
    """
    try:
        # 1. 执行搜索
        search_result = 智能联网助手(user_query)
        
        if not search_result.get("success", False):
            return {
                "success": False,
                "error": "搜索失败",
                "search_error": search_result.get("error", "未知错误")
            }
        
        # 2. 格式化搜索结果为笔记内容
        search_content = search_result.get("content", "")
        sources = search_result.get("sources", [])
        
        # 生成笔记标题
        if not note_title:
            note_title = f"搜索结果：{user_query[:50]}"
        
        # 构建笔记内容
        note_content = f"""# {note_title}

**搜索查询**: {user_query}
**搜索时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 搜索结果

{search_content}

## 信息来源

"""
        
        # 添加来源链接
        for i, source in enumerate(sources, 1):
            note_content += f"{i}. [{source.get('title', '未知标题')}]({source.get('url', '#')})\n"
        
        note_content += f"\n---\n*此笔记由网络搜索自动生成*"
        
        # 3. 保存到笔记本
        save_result = call_notepad_service_sync(
            action="create",
            title=note_title,
            content=note_content,
            category=category,
            tags=tags,
            priority="medium"
        )
        
        if save_result.get("success", False):
            return {
                "success": True,
                "message": "搜索结果已成功保存到笔记本",
                "note_id": save_result.get("note_id"),
                "note_title": note_title,
                "search_content": search_content[:500] + "..." if len(search_content) > 500 else search_content,
                "sources_count": len(sources)
            }
        else:
            return {
                "success": False,
                "error": "笔记保存失败",
                "save_error": save_result.get("error", "未知错误"),
                "search_content": search_content  # 仍然返回搜索内容
            }
            
    except Exception as e:
        error_msg = f"搜索并保存失败: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
        return {"success": False, "error": error_msg, "query": user_query}

@mcp.tool()
def 搜索并发送邮件(user_query: str, to_email: str, subject: str = None, cc_email: str = None) -> dict:
    """
    执行网络搜索并将结果通过邮件发送
    
    **功能说明**：
    - 执行智能网络搜索
    - 将搜索结果格式化为邮件内容
    - 自动发送邮件
    - 支持抄送功能
    
    **参数**：
    - user_query: 搜索查询内容
    - to_email: 收件人邮箱地址
    - subject: 邮件主题（可选，默认基于查询生成）
    - cc_email: 抄送邮箱地址（可选）
    
    **返回**：包含搜索结果和邮件发送状态的字典
    """
    try:
        # 1. 执行搜索
        search_result = 智能联网助手(user_query)
        
        if not search_result.get("success", False):
            return {
                "success": False,
                "error": "搜索失败",
                "search_error": search_result.get("error", "未知错误")
            }
        
        # 2. 格式化搜索结果为邮件内容
        search_content = search_result.get("content", "")
        sources = search_result.get("sources", [])
        
        # 生成邮件主题
        if not subject:
            subject = f"搜索结果：{user_query[:30]}"
        
        # 构建邮件正文
        email_body = f"""您好！

以下是关于"{user_query}"的搜索结果：

{search_content}

信息来源：
"""
        
        # 添加来源链接
        for i, source in enumerate(sources, 1):
            email_body += f"{i}. {source.get('title', '未知标题')}: {source.get('url', '#')}\n"
        
        email_body += f"""

搜索时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---
此邮件由智能搜索系统自动发送
"""
        
        # 3. 发送邮件
        send_result = call_email_service_sync(
            action="send_email",
            to=to_email,
            subject=subject,
            body=email_body,
            cc=cc_email if cc_email else None
        )
        
        if send_result.get("success", False):
            return {
                "success": True,
                "message": "搜索结果已成功发送邮件",
                "to_email": to_email,
                "subject": subject,
                "search_content": search_content[:500] + "..." if len(search_content) > 500 else search_content,
                "sources_count": len(sources)
            }
        else:
            return {
                "success": False,
                "error": "邮件发送失败",
                "send_error": send_result.get("error", "未知错误"),
                "search_content": search_content  # 仍然返回搜索内容
            }
            
    except Exception as e:
        error_msg = f"搜索并发送邮件失败: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
        return {"success": False, "error": error_msg, "query": user_query}

@mcp.tool()
def 搜索保存并发送(user_query: str, to_email: str, note_title: str = None, subject: str = None, 
                   category: str = "搜索结果", tags: str = "搜索,网络,邮件", cc_email: str = None) -> dict:
    """
    执行网络搜索，同时保存到笔记本并发送邮件
    
    **功能说明**：
    - 执行智能网络搜索
    - 将结果保存到笔记本
    - 同时通过邮件发送
    - 一次操作完成双重任务
    
    **参数**：
    - user_query: 搜索查询内容
    - to_email: 收件人邮箱地址
    - note_title: 笔记标题（可选）
    - subject: 邮件主题（可选）
    - category: 笔记分类（默认：搜索结果）
    - tags: 笔记标签（默认：搜索,网络,邮件）
    - cc_email: 抄送邮箱地址（可选）
    
    **返回**：包含搜索、保存和发送状态的综合结果
    """
    try:
        # 1. 执行搜索
        search_result = 智能联网助手(user_query)
        
        if not search_result.get("success", False):
            return {
                "success": False,
                "error": "搜索失败",
                "search_error": search_result.get("error", "未知错误")
            }
        
        # 2. 执行保存和发送
        save_result = 搜索并保存到笔记本(user_query, note_title, category, tags)
        email_result = 搜索并发送邮件(user_query, to_email, subject, cc_email)
        
        # 3. 汇总结果
        return {
            "success": True,
            "message": "搜索、保存和发送操作完成",
            "search_success": True,
            "save_success": save_result.get("success", False),
            "email_success": email_result.get("success", False),
            "note_id": save_result.get("note_id"),
            "to_email": to_email,
            "search_content": search_result.get("content", "")[:300] + "...",
            "sources_count": len(search_result.get("sources", [])),
            "details": {
                "save_result": save_result,
                "email_result": email_result
            }
        }
        
    except Exception as e:
        error_msg = f"搜索保存并发送失败: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
        return {"success": False, "error": error_msg, "query": user_query}

# 文件处理工具

@mcp.tool()
def 搜索并下载文件到笔记本(user_query: str, file_url: str, filename: str = None, note_title: str = None, category: str = "文件资源") -> dict:
    """
    搜索相关信息并下载指定文件到笔记本

    参数:
    - user_query: 搜索查询内容
    - file_url: 要下载的文件URL
    - filename: 文件名（可选，自动从URL获取）
    - note_title: 笔记标题（可选，自动生成）
    - category: 笔记分类（默认：文件资源）
    """
    try:
        logger.info(f"开始搜索并下载文件: {user_query}, URL: {file_url}")

        # 1. 执行搜索获取相关信息
        search_result = 智能联网助手(user_query)

        # 2. 下载文件
        download_result = download_file_from_url(file_url, filename)
        if not download_result["success"]:
            return {
                "success": False,
                "error": f"文件下载失败: {download_result['error']}"
            }

        # 3. 上传文件到笔记本
        file_upload_result = call_notepad_service_sync(
            action="upload_file",
            name=download_result["filename"],
            content=download_result["content"],
            file_type="document",
            size=download_result["size"],
            content_type=download_result["content_type"]
        )

        # 4. 创建包含搜索信息和文件链接的笔记
        final_title = note_title or f"{user_query} - 文件资源"
        note_content = f"""# {final_title}

**搜索查询**: {user_query}
**文件来源**: {file_url}
**下载时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 相关搜索信息

{search_result.get('content', '搜索信息获取中...')}

## 下载文件信息

- **文件名**: {download_result["filename"]}
- **文件大小**: {download_result["size"]} bytes
- **文件类型**: {download_result["content_type"]}
- **文件ID**: {file_upload_result.get('file_id', 'N/A')}

---
*此笔记和文件由网络搜索自动生成和下载*"""

        # 5. 保存笔记
        save_result = call_notepad_service_sync(
            action="create",
            title=final_title,
            content=note_content,
            category=category,
            tags="搜索,文件,下载",
            priority="medium"
        )

        return {
            "success": True,
            "search_success": search_result.get("success", False),
            "download_success": download_result["success"],
            "upload_success": file_upload_result.get("success", False),
            "note_success": save_result.get("success", False),
            "note_id": save_result.get("note_id"),
            "file_id": file_upload_result.get("file_id"),
            "filename": download_result["filename"],
            "file_size": download_result["size"],
            "message": f"成功搜索、下载并保存文件: {download_result['filename']}"
        }

    except Exception as e:
        logger.error(f"搜索并下载文件失败: {e}")
        return {"success": False, "error": str(e)}

@mcp.tool()
def 搜索并发送文件邮件(user_query: str, file_url: str, to_email: str, subject: str = None, filename: str = None, cc_email: str = None) -> dict:
    """
    搜索相关信息，下载文件并作为邮件附件发送

    参数:
    - user_query: 搜索查询内容
    - file_url: 要下载的文件URL
    - to_email: 收件人邮箱
    - subject: 邮件主题（可选，自动生成）
    - filename: 文件名（可选，自动从URL获取）
    - cc_email: 抄送邮箱（可选）
    """
    try:
        logger.info(f"开始搜索并发送文件邮件: {user_query}, URL: {file_url}")

        # 1. 执行搜索
        search_result = 智能联网助手(user_query)

        # 2. 下载文件
        download_result = download_file_from_url(file_url, filename)
        if not download_result["success"]:
            return {
                "success": False,
                "error": f"文件下载失败: {download_result['error']}"
            }

        # 3. 准备邮件内容
        final_subject = subject or f"搜索结果和文件: {user_query}"
        email_body = f"""您好！

以下是关于"{user_query}"的搜索结果和相关文件：

{search_result.get('content', '搜索信息获取中...')}

附件中包含相关文件: {download_result["filename"]}

搜索时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---
此邮件由智能搜索系统自动发送
"""

        # 4. 发送邮件（模拟）
        send_result = call_email_service_sync(
            action="send_email_with_attachment",
            to=to_email,
            subject=final_subject,
            body=email_body,
            cc=cc_email if cc_email else None,
            attachment_data=download_result["content"],
            attachment_filename=download_result["filename"],
            attachment_content_type=download_result["content_type"]
        )

        return {
            "success": True,
            "search_success": search_result.get("success", False),
            "download_success": download_result["success"],
            "email_success": send_result.get("success", False),
            "filename": download_result["filename"],
            "file_size": download_result["size"],
            "message": f"成功搜索、下载并发送文件邮件: {download_result['filename']}"
        }

    except Exception as e:
        logger.error(f"搜索并发送文件邮件失败: {e}")
        return {"success": False, "error": str(e)}

@mcp.tool()
def 发送笔记本文件邮件(file_id: str, to_email: str, subject: str = None, body: str = None, cc_email: str = None, search_context: str = None) -> dict:
    """
    发送笔记本中已存储的文件作为邮件附件

    参数:
    - file_id: 笔记本中的文件ID
    - to_email: 收件人邮箱
    - subject: 邮件主题（可选，自动生成）
    - body: 邮件正文（可选，自动生成）
    - cc_email: 抄送邮箱（可选）
    - search_context: 搜索上下文信息（可选，用于邮件正文）
    """
    try:
        logger.info(f"开始发送笔记本文件邮件: file_id={file_id}, to={to_email}")

        # 1. 获取文件信息
        file_result = call_notepad_service_sync(
            action="get_file",
            file_id=file_id
        )

        if not file_result.get("success", False):
            return {
                "success": False,
                "error": f"获取文件失败: {file_result.get('error', '文件不存在')}"
            }

        file_data = file_result.get("data", {})
        filename = file_data.get("name", f"file_{file_id}")
        content_type = file_data.get("content_type", "application/octet-stream")
        file_size = file_data.get("size", 0)

        # 2. 准备邮件内容
        final_subject = subject or f"文件分享: {filename}"

        if body:
            final_body = body
        else:
            final_body = f"""您好！

请查收附件中的文件: {filename}

文件信息:
- 文件名: {filename}
- 文件大小: {file_size} bytes
- 文件类型: {content_type}"""

            if search_context:
                final_body += f"\n- 相关搜索: {search_context}"

            final_body += f"""

发送时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---
此邮件由智能文件管理系统自动发送
"""

        # 3. 发送邮件
        send_result = call_email_service_sync(
            action="send_file_email",
            file_id=file_id,
            to=to_email,
            subject=final_subject,
            body=final_body,
            cc=cc_email if cc_email else None
        )

        return {
            "success": True,
            "email_success": send_result.get("success", False),
            "filename": filename,
            "file_size": file_size,
            "content_type": content_type,
            "message": f"成功发送文件邮件: {filename}"
        }

    except Exception as e:
        logger.error(f"发送笔记本文件邮件失败: {e}")
        return {"success": False, "error": str(e)}

@mcp.tool()
def 搜索并发送笔记本文件(user_query: str, file_id: str, to_email: str, subject: str = None, cc_email: str = None) -> dict:
    """
    搜索相关信息并发送笔记本中已存储的文件

    参数:
    - user_query: 搜索查询内容（用于提供上下文）
    - file_id: 笔记本中的文件ID
    - to_email: 收件人邮箱
    - subject: 邮件主题（可选，自动生成）
    - cc_email: 抄送邮箱（可选）
    """
    try:
        logger.info(f"开始搜索并发送笔记本文件: {user_query}, file_id={file_id}")

        # 1. 执行搜索获取相关信息
        search_result = 智能联网助手(user_query)

        # 2. 获取文件信息
        file_result = call_notepad_service_sync(
            action="get_file",
            file_id=file_id
        )

        if not file_result.get("success", False):
            return {
                "success": False,
                "error": f"获取文件失败: {file_result.get('error', '文件不存在')}"
            }

        file_data = file_result.get("data", {})
        filename = file_data.get("name", f"file_{file_id}")

        # 3. 准备邮件内容（包含搜索结果）
        final_subject = subject or f"搜索结果和文件: {user_query}"

        email_body = f"""您好！

以下是关于"{user_query}"的搜索结果和相关文件：

## 搜索结果

{search_result.get('content', '搜索信息获取中...')}

## 附件文件

附件中包含相关文件: {filename}

搜索时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---
此邮件由智能搜索和文件管理系统自动发送
"""

        # 4. 发送文件邮件
        send_result = 发送笔记本文件邮件(
            file_id=file_id,
            to_email=to_email,
            subject=final_subject,
            body=email_body,
            cc_email=cc_email,
            search_context=user_query
        )

        return {
            "success": True,
            "search_success": search_result.get("success", False),
            "email_success": send_result.get("email_success", False),
            "filename": send_result.get("filename"),
            "file_size": send_result.get("file_size"),
            "content_type": send_result.get("content_type"),
            "message": f"成功搜索并发送笔记本文件: {send_result.get('filename')}"
        }

    except Exception as e:
        logger.error(f"搜索并发送笔记本文件失败: {e}")
        return {"success": False, "error": str(e)}

@mcp.tool()
def 发送多个笔记本文件邮件(file_ids: list, to_email: str, subject: str = None, body: str = None, cc_email: str = None, search_context: str = None) -> dict:
    """
    发送笔记本中的多个文件作为邮件附件

    参数:
    - file_ids: 笔记本中的文件ID列表，如["file1", "file2", "file3"]
    - to_email: 收件人邮箱
    - subject: 邮件主题（可选，自动生成）
    - body: 邮件正文（可选，自动生成）
    - cc_email: 抄送邮箱（可选）
    - search_context: 搜索上下文信息（可选，用于邮件正文）
    """
    try:
        logger.info(f"开始发送多个笔记本文件邮件: file_ids={file_ids}, to={to_email}")

        if not file_ids or len(file_ids) == 0:
            return {"success": False, "error": "file_ids列表不能为空"}

        # 1. 获取所有文件信息
        attachments = []
        file_info_list = []
        total_size = 0

        for file_id in file_ids:
            file_result = call_notepad_service_sync(
                action="get_file",
                file_id=file_id
            )

            if not file_result.get("success", False):
                logger.warning(f"获取文件失败: {file_id}, 错误: {file_result.get('error', '文件不存在')}")
                continue

            file_data = file_result.get("data", {})
            filename = file_data.get("name", f"file_{file_id}")
            file_content = file_data.get("content", "")
            content_type = file_data.get("content_type", "application/octet-stream")
            file_size = file_data.get("size", 0)

            # 准备附件数据
            attachments.append({
                'name': filename,
                'content': file_content,
                'content_type': content_type
            })

            file_info_list.append({
                'filename': filename,
                'size': file_size,
                'content_type': content_type
            })

            total_size += file_size

        if len(attachments) == 0:
            return {"success": False, "error": "没有成功获取到任何文件"}

        # 2. 准备邮件内容
        final_subject = subject or f"多文件分享 ({len(attachments)}个文件)"

        if body:
            final_body = body
        else:
            final_body = f"""您好！

请查收附件中的{len(attachments)}个文件：

"""
            for i, file_info in enumerate(file_info_list, 1):
                final_body += f"{i}. {file_info['filename']} ({file_info['size']} bytes, {file_info['content_type']})\n"

            final_body += f"""
总文件大小: {total_size} bytes"""

            if search_context:
                final_body += f"\n相关搜索: {search_context}"

            final_body += f"""

发送时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---
此邮件由智能文件管理系统自动发送
"""

        # 3. 发送多附件邮件
        send_result = call_email_service_sync(
            action="send_email_with_attachments",
            to=to_email,
            subject=final_subject,
            body=final_body,
            attachments=attachments,
            cc=cc_email if cc_email else None
        )

        return {
            "success": True,
            "email_success": send_result.get("success", False),
            "attachments_count": len(attachments),
            "total_size": total_size,
            "files": file_info_list,
            "message": f"成功发送{len(attachments)}个文件的邮件"
        }

    except Exception as e:
        logger.error(f"发送多个笔记本文件邮件失败: {e}")
        return {"success": False, "error": str(e)}

@mcp.tool()
def 搜索并发送多个笔记本文件(user_query: str, file_ids: list, to_email: str, subject: str = None, cc_email: str = None) -> dict:
    """
    搜索相关信息并发送笔记本中的多个文件

    参数:
    - user_query: 搜索查询内容（用于提供上下文）
    - file_ids: 笔记本中的文件ID列表，如["file1", "file2", "file3"]
    - to_email: 收件人邮箱
    - subject: 邮件主题（可选，自动生成）
    - cc_email: 抄送邮箱（可选）
    """
    try:
        logger.info(f"开始搜索并发送多个笔记本文件: {user_query}, file_ids={file_ids}")

        # 1. 执行搜索获取相关信息
        search_result = 智能联网助手(user_query)

        # 2. 获取文件信息（用于邮件主题）
        file_names = []
        for file_id in file_ids:
            file_result = call_notepad_service_sync(
                action="get_file",
                file_id=file_id
            )
            if file_result.get("success", False):
                file_data = file_result.get("data", {})
                filename = file_data.get("name", f"file_{file_id}")
                file_names.append(filename)

        # 3. 准备邮件内容（包含搜索结果）
        final_subject = subject or f"搜索结果和多个文件: {user_query}"

        email_body = f"""您好！

以下是关于"{user_query}"的搜索结果和相关文件：

## 搜索结果

{search_result.get('content', '搜索信息获取中...')}

## 附件文件

附件中包含{len(file_names)}个相关文件：
"""

        for i, filename in enumerate(file_names, 1):
            email_body += f"{i}. {filename}\n"

        email_body += f"""
搜索时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---
此邮件由智能搜索和文件管理系统自动发送
"""

        # 4. 发送多文件邮件
        send_result = 发送多个笔记本文件邮件(
            file_ids=file_ids,
            to_email=to_email,
            subject=final_subject,
            body=email_body,
            cc_email=cc_email,
            search_context=user_query
        )

        return {
            "success": True,
            "search_success": search_result.get("success", False),
            "email_success": send_result.get("email_success", False),
            "attachments_count": send_result.get("attachments_count", 0),
            "total_size": send_result.get("total_size", 0),
            "files": send_result.get("files", []),
            "message": f"成功搜索并发送{len(file_names)}个文件的邮件"
        }

    except Exception as e:
        logger.error(f"搜索并发送多个笔记本文件失败: {e}")
        return {"success": False, "error": str(e)}

# 搜索功能实现

@mcp.tool()
def 智能联网助手(user_query: str) -> dict:
    """
    智能联网搜索助手 - 自动判断并执行最佳搜索策略

    **核心功能**：当AI遇到以下情况时自动调用此工具：
    1. 用户询问的信息超出AI训练数据时间范围（2024年4月后）
    2. 用户询问实时信息：天气、股价、汇率、交通、时间等
    3. 用户询问最新动态：新闻、政策、技术发展、公司动态等
    4. 用户询问具体的当前状态：某人近况、某公司现状等
    5. AI知识库中没有相关信息或信息可能过时
    6. 用户明确要求搜索或查询最新信息

    :param user_query: 用户的原始查询
    :return: 智能搜索结果
    """
    try:
        # 简化版本：直接使用通用搜索
        # 在实际部署时，可以连接到原始websearch.py的具体搜索功能
        return _perform_general_search(user_query)

    except Exception as e:
        error_msg = f"联网搜索失败: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
        return {"success": False, "error": error_msg, "query": user_query}

def _perform_general_search(query_text: str) -> dict:
    """执行通用网络搜索"""
    try:
        # 构建搜索URL
        search_url = f"https://www.google.com/search?q={requests.utils.quote(query_text)}&num=10"

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

        # 执行搜索
        response = requests.get(search_url, headers=headers, timeout=10)
        response.raise_for_status()

        # 解析搜索结果
        soup = BeautifulSoup(response.content, 'html.parser')
        search_results = []
        sources = []

        # 提取搜索结果
        for result in soup.find_all('div', class_='g')[:5]:  # 取前5个结果
            title_elem = result.find('h3')
            link_elem = result.find('a')
            snippet_elem = result.find('span', class_='aCOpRe')

            if title_elem and link_elem:
                title = title_elem.get_text()
                url = link_elem.get('href', '')
                snippet = snippet_elem.get_text() if snippet_elem else ""

                if url.startswith('/url?q='):
                    url = url.split('/url?q=')[1].split('&')[0]

                search_results.append(f"**{title}**\n{snippet}\n")
                sources.append({"title": title, "url": url})

        # 组合搜索内容
        content = f"关于'{query_text}'的搜索结果：\n\n" + "\n".join(search_results)

        # 优化结果长度
        if len(content) > 8000:
            content = content[:8000] + "...\n\n*结果已截断，更多信息请查看来源链接*"

        return {
            "success": True,
            "content": content,
            "sources": sources,
            "query": query_text,
            "type": "general_search"
        }

    except Exception as e:
        error_msg = f"通用搜索失败: {str(e)}"
        logger.error(error_msg)
        return {"success": False, "error": error_msg, "query": query_text}

if __name__ == "__main__":
    mcp.run()
