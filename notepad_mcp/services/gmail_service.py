"""
Gmail服务模块 - 为笔记本MCP提供邮件功能
优化版本，专注于核心邮件收发功能
"""

import os
import json
import time
import logging
import base64
import email.utils
import hashlib
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.utils import formatdate
import email.encoders
from typing import Dict, List, Optional, Union

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from googleapiclient.discovery import build

from config import GMAIL_CONFIG

logger = logging.getLogger(__name__)

_RECENT_SEND_CACHE: Dict[str, Dict] = {}
_RECENT_SEND_LOCK = threading.Lock()


def _duplicate_window_seconds() -> int:
    try:
        return max(0, int(os.getenv("GMAIL_DUPLICATE_WINDOW_SECONDS", "120")))
    except (TypeError, ValueError):
        return 120


def _mask_email(addr: Optional[str]) -> str:
    if not addr or "@" not in addr:
        return "<missing>"
    local, domain = addr.split("@", 1)
    if len(local) <= 2:
        masked_local = f"{local[:1]}*"
    else:
        masked_local = f"{local[:2]}***{local[-1:]}"
    return f"{masked_local}@{domain}"

class GmailService:
    """Gmail服务类，提供邮件收发功能"""

    def __init__(self):
        self.scopes = [
            'https://www.googleapis.com/auth/gmail.modify'
        ]
        self.service = None
        self.api_timeout = GMAIL_CONFIG.get('api_timeout', 60) # 从配置中获取API超时
        self._initialization_attempted = False
        self._initialization_error = None
        self._sender_email = GMAIL_CONFIG.get('sender_email') or None
        # 主动初始化服务
        try:
            self._initialize_service()
        except Exception as e:
            logger.warning(f"[GMAIL] Initial service initialization failed: {e}")
            self._initialization_error = str(e)

    def _initialize_service(self):
        """初始化Gmail服务"""
        try:
            self.service = self._get_gmail_service()
            logger.info("[GMAIL] Service initialized successfully")
        except Exception as e:
            logger.error(f"[GMAIL] Failed to initialize service: {e}")
            self.service = None

    def _get_gmail_service(self):
        """获取Gmail服务实例"""
        creds = None
        token_path = GMAIL_CONFIG['token_path']
        credentials_path = GMAIL_CONFIG['api_credentials_file']

        # 读取现有token
        if os.path.exists(token_path):
            try:
                with open(token_path, 'r', encoding='utf-8') as f:
                    creds_info = json.load(f)
                creds = Credentials.from_authorized_user_info(creds_info, self.scopes)
            except Exception as e:
                logger.warning(f"[GMAIL] Failed to load token: {e}")
                creds = None

        # 刷新或重新认证
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    logger.info("[GMAIL] Token refreshed successfully")
                except RefreshError as e:
                    logger.warning(f"[GMAIL] Token refresh failed: {e}")
                    self._backup_token(token_path)
                    creds = None

            if not creds:
                # 在服务器模式下，如果token和refresh都失败，则不再尝试交互式认证
                if GMAIL_CONFIG.get('server_mode', False):
                    logger.error("[GMAIL] [SERVER MODE] No valid token, and refresh failed. Manual intervention required.")
                    logger.error(f"[GMAIL] Please run 'run_gmail_auth.py' on a local machine to regenerate 'token.json' and deploy it.")
                    return None  # 优雅地禁用Gmail功能

                # 在本地模式下，才允许启动交互式认证流程
                if not os.path.exists(credentials_path):
                    raise FileNotFoundError(f"Gmail credentials not found: {credentials_path}")

                flow = InstalledAppFlow.from_client_secrets_file(
                    credentials_path, self.scopes
                )
                flow.redirect_uri = 'http://localhost'
                creds = self._handle_authentication(flow)

                if creds is None:
                    return None # 认证失败，返回None

            # 保存新获取或刷新后的token
            with open(token_path, 'w', encoding='utf-8') as f:
                f.write(creds.to_json())
            logger.info("[GMAIL] Token saved successfully")

        return build('gmail', 'v1', credentials=creds)

    def _backup_token(self, token_path: str):
        """备份token文件"""
        if os.path.exists(token_path):
            backup_path = f"{token_path}.backup.{int(time.time())}"
            try:
                import shutil
                shutil.copy2(token_path, backup_path)
                logger.info(f"[GMAIL] Token backed up to: {backup_path}")
            except Exception as e:
                logger.warning(f"[GMAIL] Backup failed: {e}")

    def _handle_authentication(self, flow):
        """处理OAuth认证，优先使用本地服务器流程"""
        # 在本地模式下，我们总是希望启动一个新的认证流程，而不是使用可能已失效的旧授权码
        # 因此，我们直接调用 run_local_server
        if not GMAIL_CONFIG.get('server_mode', False):
            try:
                logger.info("[GMAIL] Starting local server for authentication...")
                return flow.run_local_server(port=0, open_browser=True)
            except Exception as e:
                logger.error(f"[GMAIL] Local server authentication failed: {e}")
                # 提供手动URL作为最终的备用方案
                auth_url, _ = flow.authorization_url(
                    access_type='offline',
                    include_granted_scopes='true'
                )
                logger.info(f"[GMAIL] FALLBACK: Please visit this URL to authorize: {auth_url}")
                logger.info("[GMAIL] After authorization, you will get a code. Set it as AUTHORIZATION_CODE in your config and restart.")
                return None
        else: # 服务器模式
            auth_code = GMAIL_CONFIG.get('authorization_code')
            if auth_code:
                try:
                    flow.fetch_token(code=auth_code)
                    return flow.credentials
                except Exception as e:
                    logger.error(f"[GMAIL] Server mode auth code failed: {e}")

            # 如果服务器模式下没有有效的auth_code，则必须手动获取
            auth_url, _ = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true'
            )
            logger.warning(f"[GMAIL] SERVER MODE: Manual authentication required. Visit this URL: {auth_url}")
            return None

    def _send_raw_email(self, to: str, subject: str, body: str,
                   html_body: str = None, attachments: List[Dict] = None,
                   cc: str = None, bcc: str = None) -> Dict:
        """内部方法：发送邮件的原始逻辑，不进行额外的MCP工具封装"""
        if not self.service:
            return {"success": False, "error": "Gmail service not available"}

        try:
            # 验证收件人
            to_list = self._validate_emails(to)
            cc_list = self._validate_emails(cc) if cc else []
            bcc_list = self._validate_emails(bcc) if bcc else []

            if not to_list:
                return {"success": False, "error": "No valid recipients"}

            # 创建邮件
            message = MIMEMultipart('mixed')
            sender_header = self._build_from_header()
            if sender_header:
                message['From'] = sender_header
            message['To'] = ', '.join(to_list)
            if cc_list:
                message['Cc'] = ', '.join(cc_list)
            if bcc_list:
                message['Bcc'] = ', '.join(bcc_list)
            message['Subject'] = subject
            message['Date'] = formatdate(localtime=True)
            message['Message-ID'] = email.utils.make_msgid()

            # 添加正文
            msg_alternative = MIMEMultipart('alternative')
            message.attach(msg_alternative)
            msg_alternative.attach(MIMEText(body, 'plain', 'utf-8'))

            if html_body:
                msg_alternative.attach(MIMEText(html_body, 'html', 'utf-8'))

            # 处理附件
            attached_count = 0
            if attachments:
                for attachment in attachments:
                    if self._attach_file(message, attachment):
                        attached_count += 1

            # 发送邮件
            raw_message = base64.urlsafe_b64encode(
                message.as_string().encode('utf-8')
            ).decode('utf-8')

            # 添加超时处理
            import socket
            original_timeout = socket.getdefaulttimeout()
            try:
                socket.setdefaulttimeout(self.api_timeout)
                sent_msg = self.service.users().messages().send(
                    userId='me',
                    body={'raw': raw_message}
                ).execute(num_retries=3) # 增加num_retries
            finally:
                socket.setdefaulttimeout(original_timeout)

            logger.info(f"[GMAIL] Email sent successfully: {sent_msg.get('id')}")
            return {
                "success": True,
                "message_id": sent_msg.get('id'),
                "attachments_sent": attached_count,
                "recipients": {
                    "to": to_list,
                    "cc": cc_list,
                    "bcc": bcc_list
                }
            }

        except Exception as e:
            logger.error(f"[GMAIL] Send email failed: {e}")
            return {"success": False, "error": str(e)}

    def _build_from_header(self) -> Optional[str]:
        sender_name = GMAIL_CONFIG.get('sender_name') or ''
        if not sender_name:
            return None

        sender_email = self._get_sender_email()
        if not sender_email:
            logger.warning("[GMAIL] Sender name configured but sender email is unavailable; From header skipped")
            return None

        return email.utils.formataddr((sender_name, sender_email))

    def _get_sender_email(self) -> Optional[str]:
        cached = getattr(self, '_sender_email', None)
        if cached:
            return cached

        if not self.service:
            return None

        try:
            profile = self.service.users().getProfile(userId='me').execute(num_retries=3)
            self._sender_email = profile.get('emailAddress')
            return self._sender_email
        except Exception as e:
            logger.warning(f"[GMAIL] Failed to get sender profile: {e}")
            return None

    def _validate_emails(self, email_str: str) -> List[str]:
        """验证邮箱地址"""
        if not email_str:
            return []

        import re
        emails = [e.strip() for e in email_str.split(',')]
        valid_emails = []

        for email_addr in emails:
            if re.match(r"[^@]+@[^@]+\.[^@]+", email_addr):
                valid_emails.append(email_addr)
            else:
                logger.warning(f"[GMAIL] Invalid email: {email_addr}")

        return valid_emails

    def _attach_file(self, message: MIMEMultipart, attachment: Dict) -> bool:
        """添加附件到邮件"""
        try:
            filename = attachment.get('filename', attachment.get('name', 'attachment'))
            content = attachment.get('content')
            content_type = attachment.get('content_type', 'application/octet-stream')

            if not content:
                logger.warning(f"[GMAIL] Attachment {filename} has no content")
                return False

            # 处理文件内容 - 支持多种格式
            if isinstance(content, str):
                try:
                    # 尝试作为base64解码
                    file_content = base64.b64decode(content)
                except Exception:
                    # 如果不是base64，直接使用UTF-8编码
                    file_content = content.encode('utf-8')
            elif isinstance(content, bytes):
                file_content = content
            else:
                # 其他类型转换为字符串后编码
                file_content = str(content).encode('utf-8')

            # 检查大小限制
            if len(file_content) > GMAIL_CONFIG['max_attachment_size']:
                logger.warning(f"[GMAIL] File too large: {filename} ({len(file_content)} bytes)")
                return False

            # 处理content_type
            if '/' not in content_type:
                content_type = 'application/octet-stream'

            # 创建附件
            main_type, sub_type = content_type.split('/', 1)
            part = MIMEBase(main_type, sub_type)
            part.set_payload(file_content)
            email.encoders.encode_base64(part)

            # 安全地处理文件名，避免特殊字符问题
            safe_filename = filename.replace('"', '').replace("'", "")
            part.add_header(
                'Content-Disposition',
                'attachment',
                filename=('utf-8', '', safe_filename)
            )

            message.attach(part)
            logger.info(f"[GMAIL] Successfully attached file: {filename} ({len(file_content)} bytes)")
            return True

        except Exception as e:
            logger.error(f"[GMAIL] Attach file failed for {filename}: {e}")
            return False

    def list_emails(self, mailbox: str = "inbox", max_results: int = 10, query: str = None) -> Dict:
        """列出邮件 - 支持不同邮箱类型"""
        if not self.service:
            return {"success": False, "error": "Gmail service not available"}

        try:
            # 映射邮箱类型到Gmail标签
            mailbox_labels = {
                "inbox": "INBOX",
                "sent": "SENT",
                "spam": "SPAM",
                "trash": "TRASH",
                "draft": "DRAFT",
                "all": None  # 不指定标签，获取所有邮件
            }

            label = mailbox_labels.get(mailbox.lower(), "INBOX")

            # 构建查询
            query_parts = []
            if label:
                query_parts.append(f'in:{label.lower()}')
            if query:
                query_parts.append(query)

            search_query = ' '.join(query_parts) if query_parts else None

            # 获取邮件列表
            response = self.service.users().messages().list(
                userId='me',
                maxResults=min(max_results, 100),
                q=search_query
            ).execute(num_retries=3)

            messages = response.get('messages', [])
            emails = []

            for msg in messages:
                email_data = self.service.users().messages().get(
                    userId='me',
                    id=msg['id'],
                    format='metadata'
                ).execute()

                headers = email_data.get('payload', {}).get('headers', [])
                subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '(No Subject)')
                sender = next((h['value'] for h in headers if h['name'] == 'From'), '(Unknown)')
                date = next((h['value'] for h in headers if h['name'] == 'Date'), '')

                emails.append({
                    'id': msg['id'],
                    'subject': subject,
                    'sender': sender,
                    'date': date,
                    'snippet': email_data.get('snippet', ''),
                    'labels': email_data.get('labelIds', [])
                })

            logger.info(f"[GMAIL] Listed {len(emails)} emails from {mailbox}")
            return {
                "success": True,
                "emails": emails,
                "total": len(emails),
                "mailbox": mailbox
            }

        except Exception as e:
            logger.error(f"[GMAIL] List emails failed: {e}")
            return {"success": False, "error": str(e)}

    def get_recent_emails(self, max_results: int = 10,
                         label: str = None, query: str = None) -> Dict:
        """获取最近邮件"""
        if not self.service:
            return {"success": False, "error": "Gmail service not available"}

        try:
            # 构建查询
            query_parts = []
            if label:
                query_parts.append(f'in:{label}')
            if query:
                query_parts.append(query)

            search_query = ' '.join(query_parts) if query_parts else None

            # 获取邮件列表
            response = self.service.users().messages().list(
                userId='me',
                maxResults=min(max_results, 100),
                q=search_query
            ).execute(num_retries=3)

            messages = response.get('messages', [])
            emails = []

            for msg in messages:
                email_data = self.service.users().messages().get(
                    userId='me',
                    id=msg['id'],
                    format='metadata'
                ).execute()

                headers = email_data.get('payload', {}).get('headers', [])
                subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '(No Subject)')
                sender = next((h['value'] for h in headers if h['name'] == 'From'), '(Unknown)')
                date = next((h['value'] for h in headers if h['name'] == 'Date'), '')

                emails.append({
                    'id': msg['id'],
                    'subject': subject,
                    'sender': sender,
                    'date': date,
                    'snippet': email_data.get('snippet', '')
                })

            return {
                "success": True,
                "emails": emails,
                "total": len(emails)
            }

        except Exception as e:
            logger.error(f"[GMAIL] Get emails failed: {e}")
            return {"success": False, "error": str(e)}

    def check_service_health(self) -> Dict:
        """检查服务健康状态"""
        try:
            if not self.service:
                return {
                    "success": False,
                    "status": "Service not initialized"
                }

            profile = self.service.users().getProfile(userId='me').execute(num_retries=3)
            return {
                "success": True,
                "status": "Healthy",
                "email_address": profile.get('emailAddress'),
                "server_mode": GMAIL_CONFIG['server_mode']
            }

        except Exception as e:
            logger.error(f"[GMAIL] Health check failed: {e}")
            return {
                "success": False,
                "status": f"Unhealthy: {str(e)}"
            }

    def get_user_info(self) -> Dict:
        """获取用户信息"""
        if not self.service:
            return {"success": False, "error": "Gmail service not available"}

        try:
            profile = self.service.users().getProfile(userId='me').execute(num_retries=3)
            return {
                "success": True,
                "data": {
                    "email": profile.get('emailAddress'),
                    "messages_total": profile.get('messagesTotal', 0),
                    "threads_total": profile.get('threadsTotal', 0),
                    "history_id": profile.get('historyId')
                }
            }
        except Exception as e:
            logger.error(f"[GMAIL] Get user info failed: {e}")
            return {"success": False, "error": str(e)}

    def _safe_decode_email_content(self, data: str) -> str:
        """安全解码邮件内容，尝试多种编码"""
        try:
            import base64
            raw_data = base64.urlsafe_b64decode(data)

            # 尝试多种编码
            encodings = ['utf-8', 'gbk', 'gb2312', 'latin1', 'big5']
            for encoding in encodings:
                try:
                    return raw_data.decode(encoding)
                except UnicodeDecodeError:
                    continue

            # 如果所有编码都失败，使用替换模式
            return raw_data.decode('utf-8', errors='replace')
        except Exception as e:
            logger.warning(f"[GMAIL] Email content decode failed: {e}")
            return "[邮件内容解码失败]"

    def get_email_content(self, email_id: str) -> Dict:
        """获取邮件内容"""
        if not self.service:
            # 尝试重新初始化服务
            try:
                self._initialize_service()
            except Exception as e:
                logger.warning(f"[GMAIL] Service reinitialization failed: {e}")
                return {"success": False, "error": "Gmail service not available and reinitialization failed"}

        if not self.service:
            return {"success": False, "error": "Gmail service not available"}

        try:
            logger.info(f"[GMAIL] Getting email content for ID: {email_id}")
            message = self.service.users().messages().get(
                userId='me',
                id=email_id,
                format='full'
            ).execute(num_retries=3)

            # 解析邮件头部信息
            headers = {}
            for header in message['payload'].get('headers', []):
                headers[header['name']] = header['value']

            # 提取邮件正文。multipart 邮件可能包含多个 plain/html part，不能覆盖前一个 part。
            plain_parts = []
            html_parts = []

            def extract_body_from_payload(payload):
                mime_type = payload.get('mimeType', '')
                body_data = payload.get('body', {})
                if 'data' in body_data:
                    content = self._safe_decode_email_content(body_data['data'])
                    if mime_type == 'text/plain':
                        plain_parts.append(content)
                    elif mime_type == 'text/html':
                        html_parts.append(content)

                for part in payload.get('parts', []) or []:
                    extract_body_from_payload(part)

            extract_body_from_payload(message.get('payload', {}))

            body = "\n\n".join(part.strip() for part in plain_parts if part and part.strip())
            html_body = "\n\n".join(part.strip() for part in html_parts if part and part.strip())

            # 如果没有找到纯文本，但有HTML，尝试从HTML中提取纯文本
            if not body and html_body:
                try:
                    import re
                    # 简单的HTML标签清理
                    body = re.sub(r'<[^>]+>', '', html_body)
                    body = re.sub(r'\s+', ' ', body).strip()
                except Exception as e:
                    logger.warning(f"[GMAIL] HTML to plain text conversion failed: {e}")
                    body = html_body  # 回退到HTML内容

            if not body:
                body = message.get('snippet', '')

            return {
                "success": True,
                "data": {
                    "id": message['id'],
                    "thread_id": message['threadId'],
                    "subject": headers.get('Subject', ''),
                    "from": headers.get('From', ''),
                    "to": headers.get('To', ''),
                    "date": headers.get('Date', ''),
                    "body": body,
                    "body_length": len(body or ""),
                    "html_body": html_body,
                    "snippet": message.get('snippet', ''),
                    "labels": message.get('labelIds', [])
                }
            }
        except Exception as e:
            logger.error(f"[GMAIL] Get email content failed: {e}")
            return {"success": False, "error": str(e)}

    def _send_raw_email_with_attachments(self, to: str, subject: str, body: str,
                                  attachments: List[Dict] = None, **kwargs) -> Dict:
        """内部方法：发送带附件的邮件的原始逻辑"""
        return self._send_raw_email(to=to, subject=subject, body=body, attachments=attachments, **kwargs)

    def modify_email(self, email_id: str, labels_to_add: List[str] = None, labels_to_remove: List[str] = None) -> Dict:
        """修改邮件的标签"""
        if not self.service:
            return {"success": False, "error": "Gmail service not available"}

        try:
            body = {}
            if labels_to_add:
                body['addLabelIds'] = labels_to_add
            if labels_to_remove:
                body['removeLabelIds'] = labels_to_remove

            if not body:
                return {"success": False, "error": "No labels specified for modification"}

            modified_msg = self.service.users().messages().modify(
                userId='me',
                id=email_id,
                body=body
            ).execute(num_retries=3)

            logger.info(f"[GMAIL] Email {email_id} modified successfully.")
            return {"success": True, "data": modified_msg}

        except Exception as e:
            logger.error(f"[GMAIL] Modify email {email_id} failed: {e}")
            return {"success": False, "error": str(e)}

    def trash_email(self, email_id: str) -> Dict:
        """将邮件移入垃圾箱"""
        return self.modify_email(email_id, labels_to_add=['TRASH'])

    def untrash_email(self, email_id: str) -> Dict:
        """将邮件从垃圾箱移出"""
        return self.modify_email(email_id, labels_to_remove=['TRASH'])

    def archive_email(self, email_id: str) -> Dict:
        """归档邮件"""
        return self.modify_email(email_id, labels_to_remove=['INBOX'])

    def mark_as_read(self, email_id: str) -> Dict:
        """将邮件标记为已读"""
        return self.modify_email(email_id, labels_to_remove=['UNREAD'])

    def mark_as_unread(self, email_id: str) -> Dict:
        """将邮件标记为未读"""
        return self.modify_email(email_id, labels_to_add=['UNREAD'])

    def batch_modify_emails(self, email_ids: List[str], labels_to_add: List[str] = None, labels_to_remove: List[str] = None) -> Dict:
        """批量修改邮件的标签"""
        if not self.service:
            return {"success": False, "error": "Gmail service not available"}
        if not email_ids:
            return {"success": False, "error": "No email IDs provided for batch modification"}

        try:
            body = {
                'ids': email_ids,
                'addLabelIds': labels_to_add if labels_to_add else [],
                'removeLabelIds': labels_to_remove if labels_to_remove else []
            }

            self.service.users().messages().batchModify(
                userId='me',
                body=body
            ).execute(num_retries=3)

            logger.info(f"[GMAIL] Batch modified {len(email_ids)} emails successfully.")
            return {"success": True, "count": len(email_ids), "message": f"Successfully modified {len(email_ids)} emails."}

        except Exception as e:
            logger.error(f"[GMAIL] Batch modify emails failed: {e}")
            return {"success": False, "error": str(e)}

    def batch_trash_emails(self, email_ids: List[str]) -> Dict:
        """批量将邮件移入垃圾箱"""
        return self.batch_modify_emails(email_ids, labels_to_add=['TRASH'])

    def get_email_attachments(self, email_id: str) -> Dict:
        """获取邮件的所有附件"""
        if not self.service:
            return {"success": False, "error": "Gmail service not available"}

        try:
            # 获取邮件详情
            message = self.service.users().messages().get(
                userId='me',
                id=email_id,
                format='full'
            ).execute()

            attachments = []

            def extract_attachments(parts):
                """递归提取附件"""
                for part in parts:
                    if part.get('parts'):
                        # 如果有子部分，递归处理
                        extract_attachments(part['parts'])
                    elif part.get('filename') and part['filename']:
                        # 有文件名的部分是附件
                        attachment_id = part['body'].get('attachmentId')
                        if attachment_id:
                            # 获取附件内容
                            attachment = self.service.users().messages().attachments().get(
                                userId='me',
                                messageId=email_id,
                                id=attachment_id
                            ).execute()

                            # 解码附件内容
                            import base64
                            file_data = base64.urlsafe_b64decode(attachment['data'])

                            attachments.append({
                                'filename': part['filename'],
                                'content': base64.b64encode(file_data).decode('utf-8'),
                                'content_type': part.get('mimeType', 'application/octet-stream'),
                                'size': attachment.get('size', len(file_data))
                            })

            # 提取附件
            if 'parts' in message['payload']:
                extract_attachments(message['payload']['parts'])

            logger.info(f"[GMAIL] Found {len(attachments)} attachments in email {email_id}")
            return {
                "success": True,
                "attachments": attachments,
                "count": len(attachments)
            }

        except Exception as e:
            logger.error(f"[GMAIL] Failed to get email attachments: {str(e)}")
            return {"success": False, "error": str(e)}

    def send_email(self, to: str, subject: str, body: str, cc: str = None, bcc: str = None) -> Dict:
        """发送简单邮件"""
        if not self.service:
            # 尝试重新初始化服务
            try:
                self._initialize_service()
            except Exception as e:
                logger.error(f"[GMAIL] Failed to reinitialize service: {e}")

            if not self.service:
                return {"success": False, "error": "Gmail service not available"}

        try:
            dedupe_key = self._build_send_dedupe_key(to, subject, body, cc, bcc)
            duplicate = self._get_recent_send(dedupe_key)
            if duplicate:
                window = _duplicate_window_seconds()
                logger.warning(
                    "[GMAIL] Duplicate email suppressed within %ss: to=%s, subject=%s",
                    window,
                    _mask_email(to),
                    subject,
                )
                return {
                    "success": True,
                    "duplicate_suppressed": True,
                    "message": "Duplicate email suppressed",
                    "message_id": duplicate.get("message_id"),
                    "original_message_id": duplicate.get("message_id"),
                    "recipients": duplicate.get("recipients"),
                }

            # 导入调试日志器
            from diagnostic_tools import DebugLogger
            debug_logger = DebugLogger()

            debug_logger.log_api_request('Gmail', 'send_email', params={
                'to': to, 'subject': subject, 'body_length': len(body), 'cc': cc, 'bcc': bcc
            })

            logger.info(f"[GMAIL] Sending email to {to}, subject: {subject}")
            result = self._send_raw_email(
                to=to,
                subject=subject,
                body=body,
                cc=cc,
                bcc=bcc
            )

            debug_logger.log_api_request('Gmail', 'send_email', response=result)
            if result.get("success"):
                self._remember_recent_send(dedupe_key, result)
            return result

        except Exception as e:
            logger.error(f"[GMAIL] Failed to send email: {str(e)}")
            from diagnostic_tools import DebugLogger
            debug_logger = DebugLogger()
            debug_logger.log_error_details('GmailService', 'send_email', e, {
                'to': to, 'subject': subject, 'cc': cc, 'bcc': bcc
            })
            return {"success": False, "error": str(e)}

    def _build_send_dedupe_key(self, to: str, subject: str, body: str, cc: str = None, bcc: str = None) -> str:
        payload = {
            "to": sorted(email.lower() for email in self._validate_emails(to)),
            "cc": sorted(email.lower() for email in self._validate_emails(cc)) if cc else [],
            "bcc": sorted(email.lower() for email in self._validate_emails(bcc)) if bcc else [],
            "subject": subject or "",
            "body_sha256": hashlib.sha256((body or "").encode("utf-8")).hexdigest(),
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _get_recent_send(self, key: str) -> Optional[Dict]:
        window = _duplicate_window_seconds()
        if window <= 0:
            return None
        now = time.time()
        with _RECENT_SEND_LOCK:
            stale_keys = [
                cache_key
                for cache_key, entry in _RECENT_SEND_CACHE.items()
                if now - float(entry.get("sent_at", 0)) > window
            ]
            for cache_key in stale_keys:
                _RECENT_SEND_CACHE.pop(cache_key, None)
            entry = _RECENT_SEND_CACHE.get(key)
            if not entry:
                return None
            return dict(entry.get("result") or {})

    def _remember_recent_send(self, key: str, result: Dict) -> None:
        window = _duplicate_window_seconds()
        if window <= 0:
            return
        safe_result = {
            "message_id": result.get("message_id"),
            "recipients": result.get("recipients"),
        }
        with _RECENT_SEND_LOCK:
            _RECENT_SEND_CACHE[key] = {
                "sent_at": time.time(),
                "result": safe_result,
            }


    def send_email_html(self, to: str, subject: str, text_body: str, html_body: str,
                        cc: str = None, bcc: str = None) -> Dict:
        """发送包含 HTML 正文的邮件（带纯文本备份）"""
        if not self.service:
            # 尝试重新初始化服务
            try:
                self._initialize_service()
            except Exception as e:
                logger.error(f"[GMAIL] Failed to reinitialize service: {e}")
            if not self.service:
                return {"success": False, "error": "Gmail service not available"}
        try:
            from diagnostic_tools import DebugLogger
            debug_logger = DebugLogger()
            debug_logger.log_api_request('Gmail', 'send_email_html', params={
                'to': to, 'subject': subject, 'text_len': len(text_body or ''), 'has_html': bool(html_body), 'cc': cc, 'bcc': bcc
            })
            logger.info(f"[GMAIL] Sending HTML email to {to}, subject: {subject}")
            result = self._send_raw_email(
                to=to,
                subject=subject,
                body=text_body or '',
                html_body=html_body,
                cc=cc,
                bcc=bcc
            )
            debug_logger.log_api_request('Gmail', 'send_email_html', response=result)
            return result
        except Exception as e:
            logger.error(f"[GMAIL] Failed to send HTML email: {str(e)}")
            return {"success": False, "error": str(e)}

    def send_email_with_attachment(self, to: str, subject: str, body: str,
                                 attachment_data: str, attachment_filename: str,
                                 attachment_content_type: str, cc: str = None) -> Dict:
        """发送带单个附件的邮件"""
        if not self.service:
            return {"success": False, "error": "Gmail service not available"}

        try:
            attachment = {
                'name': attachment_filename,
                'content': attachment_data,
                'content_type': attachment_content_type
            }

            logger.info(f"[GMAIL] Sending email with attachment '{attachment_filename}' to {to}")
            return self._send_raw_email(
                to=to,
                subject=subject,
                body=body,
                cc=cc,
                attachments=[attachment]
            )

        except Exception as e:
            logger.error(f"[GMAIL] Failed to send email with attachment: {str(e)}")
            return {"success": False, "error": str(e)}
