# 记事本与邮件集成最佳实践

## 目标
- 保证“创建/更新笔记 + 邮件发送”的一致性、可观测与幂等
- 降低 LLM 编排多步骤失败的概率

## 关键改动
1. 使用 UUID 作为所有资源（笔记/文件/提醒）ID，避免时间戳小数导致的口述或复制精度问题
2. 所有邮件发送入口统一：
   - 先 ensure_gmail_service；失败返回明确可操作错误
   - 正文统一 _format_text_body（CRLF 换行）；附件文件名统一 _safe_filename
3. 引入容错笔记检索 _get_note_by_id_with_fallback：
   - 若传入 ID 被截断/丢小数，按前缀/去尾 0 做 LIKE 匹配
4. 推荐用原子化工具调用以降低失败率（见下）


## 工具文档统一入口
- HTML 总览（推荐）：notepad_mcp/docs/tools_overview.html
- 代码内 Docstring（便于 LLM 解析）：见各 @mcp.tool 函数顶部注释

## 推荐的调用序列（原子化）

- 更新并发送（一次调用完成）
  - 工具：update_note_and_email
  - 参数：note_id、update_fields（title/content/tags/category/priority）、send_type=attachment|body、to、subject
  - 行为：
    1) 标准化输入，执行更新
    2) 使用容错检索获取最新笔记
    3) 按 send_type 作为正文或附件发送

- 创建并发送（一次调用完成）
  - 工具：create_note_and_email（已存在）

## LLM 提示建议
- 当用户说“把这段内容更新到刚才那条笔记并发我邮件附件”时，优先调用：
  - update_note_and_email(note_id, content=..., to=..., send_type="attachment")
- 当用户仅要求“发给我邮件正文”时：
  - email_manager(action="send_note_body", note_id=..., to=...)

## 失败可观测
- 任何发送前先 ensure_gmail_service；若缺 token/凭据，返回明确错误
- 发送成功返回 success=true 且可带 message_id

## 兼容与迁移
- 旧的时间戳 ID 仍可通过 _get_note_by_id_with_fallback 找回
- 建议新生成全部使用 UUID

## 工具一览表（LLM/Agent 友好）
- notepad_manager — route; actions: create/get/update/delete/search/filter/quick_note/add_tag/remove_tag/get_tags/statistics/create_from_text
- content_manager — route; actions: upload_file/get_file/delete_file; create_reminder/get_reminder/delete_reminder; backup_data/get_system_status
- email_manager — route; actions: send_email/list_emails/get_email/trash_email/mark_read/mark_unread/batch_trash; send_note_email/send_note_body/send_reminder_email/send_notes_summary/create_note_and_email; download_email_attachments/send_email_with_file_attachment/send_file_email
- create_note / get_note / update_note / update_note_and_email / delete_note / search_notes
- send_note_as_email_attachment / send_note_as_html_email / send_email_simple / get_recent_emails
- gmail_health_check / get_system_status / save_search_results_to_notepad / batch_note_operations
- tag_manager / smart_tag_suggestions
- zhipu_recognize_image / zhipu_check_service_health / process_email_image_attachments
- send_file_as_email_attachment / notepad_initialize_components
