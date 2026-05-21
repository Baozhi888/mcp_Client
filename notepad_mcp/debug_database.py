"""
调试数据库数据，检查标签和过滤问题
"""

import asyncio
import json
import logging
from datetime import datetime
import sys
import os

# 添加路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.d1_service import D1Service

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('DEBUG_DB')

async def debug_database_content():
    """调试数据库内容"""
    logger.info("=== 调试数据库内容 ===")
    
    try:
        d1_service = D1Service()
        
        # 1. 查看所有笔记
        logger.info("1. 查看所有笔记...")
        all_notes_sql = "SELECT * FROM notes ORDER BY created_at DESC LIMIT 10"
        all_result = await d1_service.execute_query(all_notes_sql, [])
        
        if all_result and all_result.get('results'):
            logger.info(f"找到 {len(all_result['results'])} 条笔记:")
            for i, note in enumerate(all_result['results']):
                logger.info(f"  笔记 {i+1}:")
                logger.info(f"    ID: {note.get('id')}")
                logger.info(f"    标题: {note.get('title')}")
                logger.info(f"    分类: {note.get('category')}")
                logger.info(f"    优先级: {note.get('priority')}")
                logger.info(f"    标签: '{note.get('tags')}'")
                logger.info(f"    创建时间: {note.get('created_at')}")
                logger.info(f"    内容: {note.get('content')[:50]}...")
                logger.info("")
        else:
            logger.error("没有找到任何笔记")
            return False
        
        # 2. 测试标签查询
        logger.info("2. 测试标签查询...")
        
        # 查找包含"Python"的标签
        python_sql = "SELECT * FROM notes WHERE tags LIKE ?"
        python_result = await d1_service.execute_query(python_sql, ['%Python%'])
        logger.info(f"包含'Python'的笔记: {len(python_result.get('results', []))} 条")
        
        # 查找包含"测试"的标签
        test_sql = "SELECT * FROM notes WHERE tags LIKE ?"
        test_result = await d1_service.execute_query(test_sql, ['%测试%'])
        logger.info(f"包含'测试'的笔记: {len(test_result.get('results', []))} 条")
        
        # 3. 测试分类查询
        logger.info("3. 测试分类查询...")
        
        # 查找test分类
        test_category_sql = "SELECT * FROM notes WHERE category = ?"
        test_category_result = await d1_service.execute_query(test_category_sql, ['test'])
        logger.info(f"test分类的笔记: {len(test_category_result.get('results', []))} 条")
        
        # 查找work分类
        work_category_sql = "SELECT * FROM notes WHERE category = ?"
        work_category_result = await d1_service.execute_query(work_category_sql, ['work'])
        logger.info(f"work分类的笔记: {len(work_category_result.get('results', []))} 条")
        
        # 4. 测试优先级查询
        logger.info("4. 测试优先级查询...")
        
        # 查找high优先级
        high_priority_sql = "SELECT * FROM notes WHERE priority = ?"
        high_priority_result = await d1_service.execute_query(high_priority_sql, ['high'])
        logger.info(f"high优先级的笔记: {len(high_priority_result.get('results', []))} 条")
        
        # 5. 测试日期查询
        logger.info("5. 测试日期查询...")
        
        # 查找2025年的笔记
        date_2025_sql = "SELECT * FROM notes WHERE created_at >= ?"
        date_2025_result = await d1_service.execute_query(date_2025_sql, ['2025-01-01'])
        logger.info(f"2025年后的笔记: {len(date_2025_result.get('results', []))} 条")
        
        # 查找今天的笔记
        today = datetime.now().strftime('%Y-%m-%d')
        today_sql = "SELECT * FROM notes WHERE created_at >= ?"
        today_result = await d1_service.execute_query(today_sql, [today])
        logger.info(f"今天的笔记: {len(today_result.get('results', []))} 条")
        
        # 6. 测试组合查询
        logger.info("6. 测试组合查询...")
        
        # 查找test分类且high优先级的笔记
        combo_sql = "SELECT * FROM notes WHERE category = ? AND priority = ?"
        combo_result = await d1_service.execute_query(combo_sql, ['test', 'high'])
        logger.info(f"test分类且high优先级的笔记: {len(combo_result.get('results', []))} 条")
        
        if combo_result.get('results'):
            for note in combo_result['results']:
                logger.info(f"  - {note['title']} (分类: {note['category']}, 优先级: {note['priority']})")
        
        # 7. 检查数据库表结构
        logger.info("7. 检查数据库表结构...")
        schema_sql = "PRAGMA table_info(notes)"
        schema_result = await d1_service.execute_query(schema_sql, [])
        
        if schema_result and schema_result.get('results'):
            logger.info("notes表结构:")
            for column in schema_result['results']:
                logger.info(f"  - {column.get('name')}: {column.get('type')}")
        
        return True
        
    except Exception as e:
        logger.error(f"调试失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

async def test_manual_queries():
    """手动测试查询"""
    logger.info("=== 手动测试查询 ===")
    
    try:
        d1_service = D1Service()
        
        # 创建一个简单的测试笔记
        test_note = {
            'id': f'debug_test_{int(datetime.now().timestamp())}',
            'title': '调试测试笔记',
            'content': '这是调试用的测试笔记',
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'category': 'debug',
            'priority': 'high',
            'tags': 'debug,test,查询',
            'reminder_id': None,
            'file_ids': ''
        }
        
        logger.info("创建调试测试笔记...")
        note_id = await d1_service.insert_note(test_note)
        if note_id:
            logger.info(f"✓ 调试笔记创建成功: {note_id}")
            
            # 立即查询这个笔记
            logger.info("立即查询刚创建的笔记...")
            get_result = await d1_service.get_note(note_id)
            if get_result:
                logger.info(f"✓ 查询成功:")
                logger.info(f"  标题: {get_result['title']}")
                logger.info(f"  分类: {get_result['category']}")
                logger.info(f"  优先级: {get_result['priority']}")
                logger.info(f"  标签: '{get_result['tags']}'")
                
                # 测试标签查询
                logger.info("测试标签查询...")
                tag_sql = "SELECT * FROM notes WHERE id = ? AND tags LIKE ?"
                tag_result = await d1_service.execute_query(tag_sql, [note_id, '%debug%'])
                logger.info(f"标签查询结果: {tag_result}")

                # 检查结果格式
                if tag_result:
                    if 'result' in tag_result and tag_result['result']:
                        result_data = tag_result['result']
                        if isinstance(result_data, list) and len(result_data) > 0:
                            if isinstance(result_data[0], dict) and 'results' in result_data[0]:
                                # Cloudflare D1嵌套格式
                                actual_results = result_data[0]['results']
                                logger.info(f"嵌套格式结果: {len(actual_results)} 条")
                                if actual_results:
                                    logger.info("✓ 标签查询成功")
                                else:
                                    logger.error("✗ 标签查询失败 - 无结果")
                            else:
                                logger.info(f"标准格式结果: {len(result_data)} 条")
                                if result_data:
                                    logger.info("✓ 标签查询成功")
                                else:
                                    logger.error("✗ 标签查询失败 - 无结果")
                        else:
                            logger.error("✗ 标签查询失败 - 结果为空列表")
                    else:
                        logger.error("✗ 标签查询失败 - 无result字段")
                else:
                    logger.error("✗ 标签查询失败 - 查询返回None")

                # 测试分类查询
                logger.info("测试分类查询...")
                category_sql = "SELECT * FROM notes WHERE id = ? AND category = ?"
                category_result = await d1_service.execute_query(category_sql, [note_id, 'debug'])
                logger.info(f"分类查询结果: {category_result}")

                # 检查分类查询结果
                if category_result and 'result' in category_result:
                    result_data = category_result['result']
                    if isinstance(result_data, list) and len(result_data) > 0:
                        if isinstance(result_data[0], dict) and 'results' in result_data[0]:
                            actual_results = result_data[0]['results']
                            if actual_results:
                                logger.info("✓ 分类查询成功")
                            else:
                                logger.error("✗ 分类查询失败 - 无结果")
                        else:
                            if result_data:
                                logger.info("✓ 分类查询成功")
                            else:
                                logger.error("✗ 分类查询失败 - 无结果")
                    else:
                        logger.error("✗ 分类查询失败 - 结果为空")
                else:
                    logger.error("✗ 分类查询失败")
                
            else:
                logger.error("✗ 无法查询刚创建的笔记")
        else:
            logger.error("✗ 调试笔记创建失败")
        
        return True
        
    except Exception as e:
        logger.error(f"手动测试失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

async def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("数据库调试工具")
    logger.info("=" * 60)
    
    # 1. 调试数据库内容
    await debug_database_content()
    
    logger.info("\n" + "=" * 40)
    
    # 2. 手动测试查询
    await test_manual_queries()

if __name__ == "__main__":
    asyncio.run(main())
