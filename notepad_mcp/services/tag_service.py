"""
标签服务 - 优化的标签管理系统
提供标签的增删改查、搜索、智能建议等功能
支持Redis缓存同步机制
"""

import logging
import re
import json
from typing import List, Dict, Optional, Set
from datetime import datetime
from collections import Counter
import asyncio
import redis

from config import SERVICE_CONFIG
from services.d1_service import D1Service
from models.note import NoteModel

logger = logging.getLogger('TAG_SERVICE')

class TagService:
    def __init__(self):
        self.d1_service = None
        self.tag_cache = {}
        self.cache_timestamp = None
        self.cache_ttl = SERVICE_CONFIG.get('tag_cache_ttl', 300)  # 默认5分钟缓存
        
        # Redis配置用于缓存同步
        self.redis_host = SERVICE_CONFIG.get('redis_host', 'localhost')
        self.redis_port = SERVICE_CONFIG.get('redis_port', 6380)
        self.redis_db = SERVICE_CONFIG.get('redis_db', 1)
        self.redis_password = SERVICE_CONFIG.get('redis_password')
        
        # Redis连接
        self._redis_client = None
        self._redis_available = False
        self._init_redis()
        
    def _init_redis(self):
        """初始化Redis连接"""
        try:
            redis_config = {
                'host': self.redis_host,
                'port': self.redis_port,
                'db': self.redis_db,
                'decode_responses': True,
                'socket_timeout': 5,
                'socket_connect_timeout': 5,
                'retry_on_timeout': True
            }
            
            if self.redis_password:
                redis_config['password'] = self.redis_password
                
            self._redis_client = redis.Redis(**redis_config)
            self._redis_client.ping()  # 测试连接
            self._redis_available = True
            logger.info("Redis连接初始化成功")
        except Exception as e:
            logger.warning(f"Redis连接初始化失败: {e}")
            self._redis_available = False
            self._redis_client = None
    
    async def _get_d1_service(self) -> D1Service:
        """获取D1服务实例"""
        if self.d1_service is None:
            self.d1_service = D1Service()
            await self.d1_service.initialize_tables()
        return self.d1_service
    
    async def _is_cache_valid(self) -> bool:
        """检查缓存是否有效"""
        if not self.cache_timestamp:
            return False
        return (datetime.now() - self.cache_timestamp).seconds < self.cache_ttl
    
    def _invalidate_cache(self):
        """清除缓存"""
        self.tag_cache.clear()
        self.cache_timestamp = None
        logger.info("标签缓存已清除")
        
        # 如果Redis可用，发布缓存失效通知
        if self._redis_available and self._redis_client:
            try:
                self._redis_client.publish("tag_cache_invalidate", "invalidate")
                logger.info("已发布标签缓存失效通知到Redis")
            except Exception as e:
                logger.warning(f"发布缓存失效通知失败: {e}")
    
    def get_cache_status(self) -> Dict:
        """获取缓存状态"""
        return {
            "cache_enabled": True,
            "cache_ttl": self.cache_ttl,
            "cache_valid": asyncio.run(self._is_cache_valid()) if self.cache_timestamp else False,
            "cache_timestamp": self.cache_timestamp.isoformat() if self.cache_timestamp else None,
            "cached_tags_count": len(self.tag_cache.get('all_tags', [])) if self.tag_cache else 0,
            "redis_available": self._redis_available
        }
    
    async def get_all_tags(self) -> List[str]:
        """获取所有标签，带缓存机制"""
        if await self._is_cache_valid() and self.tag_cache:
            return self.tag_cache.get('all_tags', [])
        
        try:
            d1 = await self._get_d1_service()
            query = "SELECT DISTINCT tags FROM notes WHERE tags IS NOT NULL AND tags != ''"
            result = await d1.execute_query(query)
            
            all_tags = set()
            if result and result.get('success') is not False:
                # 处理不同的返回格式
                rows = []
                if 'results' in result:
                    rows = result['results']
                elif 'result' in result:
                    rows = result['result']
                
                for row in rows:
                    if row.get('tags'):
                        tags_str = row['tags']
                        # 尝试解析JSON格式
                        try:
                            tags_list = json.loads(tags_str)
                            if isinstance(tags_list, list):
                                all_tags.update(tags_list)
                            else:
                                # 如果不是列表，按逗号分割
                                all_tags.update([tag.strip() for tag in tags_str.split(',') if tag.strip()])
                        except (json.JSONDecodeError, TypeError):
                            # 如果JSON解析失败，按逗号分割
                            all_tags.update([tag.strip() for tag in tags_str.split(',') if tag.strip()])
            
            # 更新缓存
            self.tag_cache['all_tags'] = list(all_tags)
            self.cache_timestamp = datetime.now()
            
            return self.tag_cache['all_tags']
        except Exception as e:
            logger.error(f"Error getting all tags: {e}")
            return []
    
    async def get_notes_by_tag(self, tag: str) -> List[Dict]:
        """根据标签获取笔记"""
        try:
            d1 = await self._get_d1_service()
            return await d1.get_notes_by_tag(tag)
        except Exception as e:
            logger.error(f"Error getting notes by tag '{tag}': {e}")
            return []
    
    async def get_notes_by_tags(self, tags: List[str], match_all: bool = False) -> List[Dict]:
        """根据多个标签获取笔记"""
        try:
            d1 = await self._get_d1_service()
            return await d1.get_notes_by_tags(tags, match_all)
        except Exception as e:
            logger.error(f"Error getting notes by tags {tags}: {e}")
            return []
    
    async def add_tag_to_note(self, note_id: str, tag: str) -> Dict:
        """为笔记添加标签"""
        try:
            # 验证标签格式
            if not tag or not tag.strip():
                return {"status": "error", "message": "标签不能为空"}
            
            tag = tag.strip()
            if len(tag) > 50:
                return {"status": "error", "message": "标签长度不能超过50个字符"}
            
            d1 = await self._get_d1_service()
            note = await d1.get_note(note_id)
            if not note:
                return {"status": "error", "message": "笔记不存在"}
            
            # 获取当前标签
            current_tags = note.get('tags', [])
            if isinstance(current_tags, str):
                try:
                    current_tags = json.loads(current_tags)
                except (json.JSONDecodeError, TypeError):
                    current_tags = [t.strip() for t in current_tags.split(',') if t.strip()]
            elif not isinstance(current_tags, list):
                current_tags = []
            
            # 添加新标签（避免重复）
            if tag not in current_tags:
                current_tags.append(tag)
                
                # 更新笔记
                update_data = {'tags': current_tags}
                success = await d1.update_note(note_id, update_data)
                
                if success:
                    # 清除缓存
                    self._invalidate_cache()
                    
                    logger.info(f"Tag '{tag}' added to note {note_id}")
                    return {"status": "success", "message": "标签添加成功", "tags": current_tags}
                else:
                    return {"status": "error", "message": "更新笔记失败"}
            else:
                return {"status": "success", "message": "标签已存在", "tags": current_tags}
                
        except Exception as e:
            logger.error(f"Error adding tag to note {note_id}: {e}")
            return {"status": "error", "message": str(e)}
    
    async def remove_tag_from_note(self, note_id: str, tag: str) -> Dict:
        """从笔记中移除标签"""
        try:
            d1 = await self._get_d1_service()
            note = await d1.get_note(note_id)
            if not note:
                return {"status": "error", "message": "笔记不存在"}
            
            # 获取当前标签
            current_tags = note.get('tags', [])
            if isinstance(current_tags, str):
                try:
                    current_tags = json.loads(current_tags)
                except (json.JSONDecodeError, TypeError):
                    current_tags = [t.strip() for t in current_tags.split(',') if t.strip()]
            elif not isinstance(current_tags, list):
                current_tags = []
            
            # 移除标签
            if tag in current_tags:
                current_tags.remove(tag)
                
                # 更新笔记
                update_data = {'tags': current_tags}
                success = await d1.update_note(note_id, update_data)
                
                if success:
                    # 清除缓存
                    self._invalidate_cache()
                    
                    logger.info(f"Tag '{tag}' removed from note {note_id}")
                    return {"status": "success", "message": "标签移除成功", "tags": current_tags}
                else:
                    return {"status": "error", "message": "更新笔记失败"}
            else:
                return {"status": "success", "message": "标签不存在", "tags": current_tags}
                
        except Exception as e:
            logger.error(f"Error removing tag from note {note_id}: {e}")
            return {"status": "error", "message": str(e)}
    
    async def rename_tag(self, old_tag: str, new_tag: str) -> Dict:
        """重命名标签（全局操作）"""
        try:
            # 验证标签格式
            if not new_tag or not new_tag.strip():
                return {"status": "error", "message": "新标签名不能为空"}
            
            new_tag = new_tag.strip()
            if len(new_tag) > 50:
                return {"status": "error", "message": "标签长度不能超过50个字符"}
            
            d1 = await self._get_d1_service()
            
            # 获取所有包含旧标签的笔记
            query = "SELECT id, tags FROM notes WHERE tags LIKE ?"
            search_pattern = f"%{old_tag}%"
            result = await d1.execute_query(query, [search_pattern])
            
            updated_notes = 0
            if result and result.get('success') is not False:
                # 处理不同的返回格式
                rows = []
                if 'results' in result:
                    rows = result['results']
                elif 'result' in result:
                    rows = result['result']
                
                for row in rows:
                    note_id = row['id']
                    tags_str = row['tags']
                    
                    # 解析标签
                    try:
                        tags_list = json.loads(tags_str)
                        if not isinstance(tags_list, list):
                            tags_list = [t.strip() for t in tags_str.split(',') if t.strip()]
                    except (json.JSONDecodeError, TypeError):
                        tags_list = [t.strip() for t in tags_str.split(',') if t.strip()]
                    
                    # 替换标签
                    if old_tag in tags_list:
                        tags_list = [new_tag if tag == old_tag else tag for tag in tags_list]
                        
                        # 更新笔记
                        update_data = {'tags': tags_list}
                        if await d1.update_note(note_id, update_data):
                            updated_notes += 1
            
            # 清除缓存
            self._invalidate_cache()
            
            logger.info(f"Tag '{old_tag}' renamed to '{new_tag}' in {updated_notes} notes")
            return {
                "status": "success", 
                "message": f"标签重命名成功，共更新{updated_notes}个笔记",
                "updated_notes": updated_notes
            }
            
        except Exception as e:
            logger.error(f"Error renaming tag '{old_tag}' to '{new_tag}': {e}")
            return {"status": "error", "message": str(e)}
    
    async def merge_tags(self, tags_to_merge: List[str], target_tag: str) -> Dict:
        """合并标签"""
        try:
            if not tags_to_merge or len(tags_to_merge) < 2:
                return {"status": "error", "message": "至少需要两个标签进行合并"}
            
            if not target_tag or not target_tag.strip():
                return {"status": "error", "message": "目标标签不能为空"}
            
            target_tag = target_tag.strip()
            if len(target_tag) > 50:
                return {"status": "error", "message": "标签长度不能超过50个字符"}
            
            d1 = await self._get_d1_service()
            
            updated_notes = 0
            processed_notes = set()
            
            # 遍历所有要合并的标签
            for tag in tags_to_merge:
                if tag == target_tag:
                    continue  # 跳过目标标签本身
                    
                # 获取包含该标签的所有笔记
                query = "SELECT id, tags FROM notes WHERE tags LIKE ?"
                search_pattern = f"%{tag}%"
                result = await d1.execute_query(query, [search_pattern])
                
                if result and result.get('success') is not False:
                    # 处理不同的返回格式
                    rows = []
                    if 'results' in result:
                        rows = result['results']
                    elif 'result' in result:
                        rows = result['result']
                    
                    for row in rows:
                        note_id = row['id']
                        # 避免重复处理同一个笔记
                        if note_id in processed_notes:
                            continue
                            
                        tags_str = row['tags']
                        
                        # 解析标签
                        try:
                            tags_list = json.loads(tags_str)
                            if not isinstance(tags_list, list):
                                tags_list = [t.strip() for t in tags_str.split(',') if t.strip()]
                        except (json.JSONDecodeError, TypeError):
                            tags_list = [t.strip() for t in tags_str.split(',') if t.strip()]
                        
                        # 移除要合并的标签并添加目标标签
                        updated_tags = [t for t in tags_list if t not in tags_to_merge]
                        if target_tag not in updated_tags:
                            updated_tags.append(target_tag)
                        
                        # 更新笔记
                        update_data = {'tags': updated_tags}
                        if await d1.update_note(note_id, update_data):
                            updated_notes += 1
                            processed_notes.add(note_id)
            
            # 清除缓存
            self._invalidate_cache()
            
            logger.info(f"Merged tags {tags_to_merge} into '{target_tag}' in {updated_notes} notes")
            return {
                "status": "success", 
                "message": f"标签合并成功，共更新{updated_notes}个笔记",
                "updated_notes": updated_notes
            }
            
        except Exception as e:
            logger.error(f"Error merging tags {tags_to_merge} into '{target_tag}': {e}")
            return {"status": "error", "message": str(e)}
    
    async def search_tags(self, query: str, limit: int = 20) -> List[str]:
        """搜索标签（支持模糊搜索）"""
        try:
            all_tags = await self.get_all_tags()
            if not query:
                return all_tags[:limit]
            
            # 不区分大小写的模糊搜索
            query_lower = query.lower()
            matched_tags = [tag for tag in all_tags if query_lower in tag.lower()]
            
            # 按匹配度排序（完全匹配优先，然后是前缀匹配，最后是包含匹配）
            def sort_key(tag):
                tag_lower = tag.lower()
                if tag_lower == query_lower:
                    return (0, tag)  # 完全匹配
                elif tag_lower.startswith(query_lower):
                    return (1, len(tag), tag)  # 前缀匹配
                else:
                    return (2, len(tag), tag)  # 包含匹配
            
            matched_tags.sort(key=sort_key)
            return matched_tags[:limit]
            
        except Exception as e:
            logger.error(f"Error searching tags with query '{query}': {e}")
            return []
    
    async def get_tag_suggestions(self, context: str = "", note_content: str = "", limit: int = 10) -> List[str]:
        """获取智能标签建议"""
        try:
            suggestions = set()
            
            # 1. 基于上下文的建议
            if context:
                context_suggestions = await self._suggest_from_context(context)
                suggestions.update(context_suggestions)
            
            # 2. 基于笔记内容的建议
            if note_content:
                content_suggestions = await self._suggest_from_content(note_content)
                suggestions.update(content_suggestions)
            
            # 3. 基于流行度的建议
            popular_tags = await self._get_popular_tags(limit * 2)
            suggestions.update(popular_tags)
            
            # 4. 获取所有标签作为候选
            all_tags = await self.get_all_tags()
            suggestions.update(all_tags)
            
            # 转换为列表并排序
            suggestion_list = list(suggestions)
            
            # 如果有上下文，按相关性排序
            if context:
                suggestion_list.sort(key=lambda x: self._calculate_relevance(x, context), reverse=True)
            else:
                # 否则按字母顺序排序
                suggestion_list.sort()
            
            return suggestion_list[:limit]
            
        except Exception as e:
            logger.error(f"Error getting tag suggestions: {e}")
            return []
    
    async def _suggest_from_context(self, context: str) -> List[str]:
        """基于上下文的标签建议"""
        suggestions = []
        context_lower = context.lower()
        
        # 预定义的上下文映射
        context_mapping = {
            'work': ['工作', '项目', '任务', '会议', '办公'],
            'study': ['学习', '课程', '教程', '知识', '笔记', '教育'],
            'personal': ['个人', '生活', '家庭', '朋友', '爱好'],
            'important': ['重要', '紧急', '优先'],
            'todo': ['待办', '任务', '计划'],
            'done': ['完成', '已完成', '结束'],
            'idea': ['想法', '创意', '灵感'],
            'meeting': ['会议', '讨论', '会谈'],
            'project': ['项目', '计划', '方案'],
            'reference': ['参考', '资料', '文档']
        }
        
        for category, tags in context_mapping.items():
            if category in context_lower:
                suggestions.extend(tags)
        
        return suggestions
    
    async def _suggest_from_content(self, content: str) -> List[str]:
        """基于内容的标签建议"""
        suggestions = []
        
        # 提取#标签
        hashtag_pattern = r'#(\w+)'
        hashtags = re.findall(hashtag_pattern, content)
        suggestions.extend(hashtags)
        
        # 基于关键词的建议
        keywords = {
            '重要': ['重要', '关键', '核心', 'urgent', 'important'],
            '待办': ['待办', 'todo', '任务', 'task'],
            '完成': ['完成', 'done', 'finished'],
            '想法': ['想法', 'idea', '思考', 'thought'],
            '笔记': ['笔记', 'note', '记录', 'record'],
            '会议': ['会议', 'meeting', '讨论', 'discussion'],
            '项目': ['项目', 'project', '计划', 'plan'],
            '学习': ['学习', 'study', '课程', 'course'],
            '工作': ['工作', 'work', 'job', '职业', 'career']
        }
        
        content_lower = content.lower()
        for tag, words in keywords.items():
            if any(word in content_lower for word in words):
                suggestions.append(tag)
        
        return suggestions
    
    async def _get_popular_tags(self, limit: int = 20) -> List[str]:
        """获取流行标签"""
        try:
            d1 = await self._get_d1_service()
            query = "SELECT tags FROM notes WHERE tags IS NOT NULL AND tags != ''"
            result = await d1.execute_query(query)
            
            tag_counter = Counter()
            if result and result.get('success') is not False:
                # 处理不同的返回格式
                rows = []
                if 'results' in result:
                    rows = result['results']
                elif 'result' in result:
                    rows = result['result']
                
                for row in rows:
                    tags_str = row['tags']
                    # 解析标签
                    try:
                        tags_list = json.loads(tags_str)
                        if not isinstance(tags_list, list):
                            tags_list = [t.strip() for t in tags_str.split(',') if t.strip()]
                    except (json.JSONDecodeError, TypeError):
                        tags_list = [t.strip() for t in tags_str.split(',') if t.strip()]
                    
                    tag_counter.update(tags_list)
            
            # 返回最常见的标签
            return [tag for tag, count in tag_counter.most_common(limit)]
            
        except Exception as e:
            logger.error(f"Error getting popular tags: {e}")
            return []
    
    def _calculate_relevance(self, tag: str, context: str) -> float:
        """计算标签与上下文的相关性"""
        tag_lower = tag.lower()
        context_lower = context.lower()
        
        # 完全匹配
        if tag_lower == context_lower:
            return 1.0
        
        # 前缀匹配
        if tag_lower.startswith(context_lower):
            return 0.8
        
        # 包含匹配
        if context_lower in tag_lower:
            return 0.6
        
        # 编辑距离（简单实现）
        if self._simple_edit_distance(tag_lower, context_lower) <= 2:
            return 0.4
        
        return 0.1
    
    def _simple_edit_distance(self, s1: str, s2: str) -> int:
        """简单的编辑距离计算"""
        if len(s1) < len(s2):
            return self._simple_edit_distance(s2, s1)
        
        if len(s2) == 0:
            return len(s1)
        
        previous_row = list(range(len(s2) + 1))
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        
        return previous_row[-1]
    
    async def get_tag_statistics(self) -> Dict:
        """获取标签统计信息"""
        try:
            d1 = await self._get_d1_service()
            
            # 获取标签使用统计
            query = "SELECT tags FROM notes WHERE tags IS NOT NULL AND tags != ''"
            result = await d1.execute_query(query)
            
            tag_counter = Counter()
            total_notes_with_tags = 0
            
            if result and result.get('success') is not False:
                # 处理不同的返回格式
                rows = []
                if 'results' in result:
                    rows = result['results']
                elif 'result' in result:
                    rows = result['result']
                
                total_notes_with_tags = len(rows)
                
                for row in rows:
                    tags_str = row['tags']
                    # 解析标签
                    try:
                        tags_list = json.loads(tags_str)
                        if not isinstance(tags_list, list):
                            tags_list = [t.strip() for t in tags_str.split(',') if t.strip()]
                    except (json.JSONDecodeError, TypeError):
                        tags_list = [t.strip() for t in tags_str.split(',') if t.strip()]
                    
                    tag_counter.update(tags_list)
            
            # 计算统计信息
            total_unique_tags = len(tag_counter)
            most_used_tags = tag_counter.most_common(10)
            
            stats = {
                "total_unique_tags": total_unique_tags,
                "total_notes_with_tags": total_notes_with_tags,
                "average_tags_per_note": total_notes_with_tags > 0 and sum(tag_counter.values()) / total_notes_with_tags or 0,
                "most_used_tags": [{"tag": tag, "count": count} for tag, count in most_used_tags],
                "tag_usage_distribution": dict(tag_counter)
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting tag statistics: {e}")
            return {}

# 全局标签服务实例
tag_service: Optional[TagService] = None

async def get_tag_service() -> TagService:
    """获取标签服务单例实例"""
    global tag_service
    if tag_service is None:
        tag_service = TagService()
    return tag_service