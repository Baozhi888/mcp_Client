"""
文档内容提取服务 - 处理各种文档格式的内容提取
支持PDF、Word、Excel、文本文件、Markdown和源代码文件
"""

import logging
import os
import tempfile
from typing import Optional, Dict, Any, List
from pathlib import Path

# 文档处理相关库
try:
    import PyPDF2
    from PyPDF2 import PdfReader
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False
    logging.warning("PyPDF2 not available for PDF processing")

try:
    import docx
    from docx import Document
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False
    logging.warning("python-docx not available for DOCX processing")

try:
    import openpyxl
    from openpyxl import load_workbook
    XLSX_AVAILABLE = True
except ImportError:
    XLSX_AVAILABLE = False
    logging.warning("openpyxl not available for XLSX processing")

# Markdown处理
try:
    import markdown
    from markdown import Markdown
    MARKDOWN_AVAILABLE = True
except ImportError:
    MARKDOWN_AVAILABLE = False
    logging.warning("markdown not available for Markdown processing")

# 文件类型检测
try:
    import magic
    MAGIC_AVAILABLE = True
except ImportError:
    MAGIC_AVAILABLE = False
    logging.warning("python-magic not available for file type detection")

logger = logging.getLogger('DOCUMENT_PROCESSOR')


class DocumentProcessor:
    """文档内容提取服务类"""
    
    # 支持的文件类型映射
    SUPPORTED_EXTENSIONS = {
        # 文本文件
        'txt': 'text',
        'md': 'markdown',
        'markdown': 'markdown',
        'csv': 'text',
        'json': 'text',
        'xml': 'text',
        'html': 'text',
        'htm': 'text',
        
        # PDF文件
        'pdf': 'pdf',
        
        # Word文档
        'docx': 'word',
        'doc': 'word',  # 注意：doc格式需要其他库支持
        
        # Excel文档
        'xlsx': 'excel',
        'xls': 'excel',  # 注意：xls格式需要其他库支持
        
        # 源代码文件
        'py': 'code',
        'js': 'code',
        'java': 'code',
        'cpp': 'code',
        'c': 'code',
        'h': 'code',
        'cs': 'code',
        'php': 'code',
        'rb': 'code',
        'go': 'code',
        'rs': 'code',
        'swift': 'code',
        'kt': 'code',
        'ts': 'code',
        'sql': 'code',
        'sh': 'code',
        'pl': 'code',
        'pm': 'code',
        'r': 'code',
        'm': 'code',
        'mat': 'code',
    }
    
    def __init__(self):
        """初始化文档处理器"""
        self.temp_dir = tempfile.gettempdir()
        logger.info("DocumentProcessor initialized")
    
    def get_file_type(self, file_path: str) -> str:
        """
        获取文件类型
        
        Args:
            file_path (str): 文件路径
            
        Returns:
            str: 文件类型
        """
        try:
            # 首先通过扩展名判断
            extension = Path(file_path).suffix.lower().lstrip('.')
            if extension in self.SUPPORTED_EXTENSIONS:
                return self.SUPPORTED_EXTENSIONS[extension]
            
            # 如果扩展名不在支持列表中，尝试使用magic库检测
            if MAGIC_AVAILABLE:
                mime_type = magic.from_file(file_path, mime=True)
                if mime_type.startswith('text/'):
                    return 'text'
                elif mime_type == 'application/pdf':
                    return 'pdf'
                elif mime_type in ['application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']:
                    return 'word'
                elif mime_type in ['application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet']:
                    return 'excel'
            
            # 默认返回文本类型
            return 'text'
        except Exception as e:
            logger.error(f"Error detecting file type for {file_path}: {e}")
            return 'text'
    
    def extract_content(self, file_path: str, file_type: Optional[str] = None) -> Optional[str]:
        """
        提取文件内容
        
        Args:
            file_path (str): 文件路径
            file_type (str, optional): 文件类型
            
        Returns:
            str: 提取的文件内容
        """
        try:
            # 验证文件是否存在
            if not os.path.exists(file_path):
                logger.error(f"File not found: {file_path}")
                return None
            
            # 获取文件类型
            if not file_type:
                file_type = self.get_file_type(file_path)
            
            logger.info(f"Processing {file_path} as {file_type}")
            
            # 根据文件类型调用相应的处理方法
            if file_type == 'text':
                return self._extract_text_content(file_path)
            elif file_type == 'markdown':
                return self._extract_markdown_content(file_path)
            elif file_type == 'pdf':
                return self._extract_pdf_content(file_path)
            elif file_type == 'word':
                return self._extract_word_content(file_path)
            elif file_type == 'excel':
                return self._extract_excel_content(file_path)
            elif file_type == 'code':
                return self._extract_code_content(file_path)
            else:
                # 默认按文本处理
                return self._extract_text_content(file_path)
                
        except Exception as e:
            logger.error(f"Error extracting content from {file_path}: {e}")
            return None
    
    def _extract_text_content(self, file_path: str) -> Optional[str]:
        """
        提取文本文件内容
        
        Args:
            file_path (str): 文件路径
            
        Returns:
            str: 文件内容
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                return file.read()
        except UnicodeDecodeError:
            # 如果UTF-8解码失败，尝试其他编码
            try:
                with open(file_path, 'r', encoding='gbk') as file:
                    return file.read()
            except UnicodeDecodeError:
                try:
                    with open(file_path, 'r', encoding='latin-1') as file:
                        return file.read()
                except Exception as e:
                    logger.error(f"Error reading text file {file_path}: {e}")
                    return None
        except Exception as e:
            logger.error(f"Error reading text file {file_path}: {e}")
            return None
    
    def _extract_markdown_content(self, file_path: str) -> Optional[str]:
        """
        提取Markdown文件内容
        
        Args:
            file_path (str): 文件路径
            
        Returns:
            str: Markdown内容（纯文本）
        """
        try:
            # 读取原始Markdown内容
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()
            
            # 如果需要提取纯文本，可以简单处理
            # 这里返回原始内容，因为Markdown本身就是文本格式
            return content
        except Exception as e:
            logger.error(f"Error reading markdown file {file_path}: {e}")
            return None
    
    def _extract_pdf_content(self, file_path: str) -> Optional[str]:
        """
        提取PDF文件内容
        
        Args:
            file_path (str): 文件路径
            
        Returns:
            str: PDF文本内容
        """
        if not PDF_AVAILABLE:
            logger.error("PyPDF2 not available for PDF processing")
            return None
            
        try:
            content = ""
            with open(file_path, 'rb') as file:
                pdf_reader = PdfReader(file)
                for page in pdf_reader.pages:
                    content += page.extract_text() + "\n"
            return content
        except Exception as e:
            logger.error(f"Error extracting PDF content from {file_path}: {e}")
            return None
    
    def _extract_word_content(self, file_path: str) -> Optional[str]:
        """
        提取Word文档内容
        
        Args:
            file_path (str): 文件路径
            
        Returns:
            str: Word文档文本内容
        """
        if not DOCX_AVAILABLE:
            logger.error("python-docx not available for DOCX processing")
            return None
            
        try:
            doc = Document(file_path)
            content = ""
            for paragraph in doc.paragraphs:
                content += paragraph.text + "\n"
            return content
        except Exception as e:
            logger.error(f"Error extracting Word content from {file_path}: {e}")
            return None
    
    def _extract_excel_content(self, file_path: str) -> Optional[str]:
        """
        提取Excel文档内容
        
        Args:
            file_path (str): 文件路径
            
        Returns:
            str: Excel内容（表格数据文本表示）
        """
        if not XLSX_AVAILABLE:
            logger.error("openpyxl not available for XLSX processing")
            return None
            
        try:
            workbook = load_workbook(file_path, read_only=True)
            content = ""
            
            for sheet_name in workbook.sheetnames:
                sheet = workbook[sheet_name]
                content += f"Sheet: {sheet_name}\n"
                
                # 获取有数据的范围
                if sheet.max_row > 0 and sheet.max_column > 0:
                    for row in sheet.iter_rows(values_only=True):
                        row_content = "\t".join([str(cell) if cell is not None else "" for cell in row])
                        content += row_content + "\n"
                content += "\n"
                
            return content
        except Exception as e:
            logger.error(f"Error extracting Excel content from {file_path}: {e}")
            return None
    
    def _extract_code_content(self, file_path: str) -> Optional[str]:
        """
        提取源代码文件内容
        
        Args:
            file_path (str): 文件路径
            
        Returns:
            str: 源代码内容
        """
        try:
            # 源代码文件按文本处理，但可以添加特定的处理逻辑
            with open(file_path, 'r', encoding='utf-8') as file:
                return file.read()
        except Exception as e:
            logger.error(f"Error reading code file {file_path}: {e}")
            return None
    
    def get_supported_extensions(self) -> Dict[str, str]:
        """
        获取支持的文件扩展名列表
        
        Returns:
            Dict[str, str]: 扩展名到文件类型的映射
        """
        return self.SUPPORTED_EXTENSIONS.copy()
    
    def is_supported_extension(self, extension: str) -> bool:
        """
        检查扩展名是否支持
        
        Args:
            extension (str): 文件扩展名
            
        Returns:
            bool: 是否支持
        """
        return extension.lower() in self.SUPPORTED_EXTENSIONS


# 全局实例
document_processor = DocumentProcessor()


def extract_document_content(file_path: str, file_type: Optional[str] = None) -> Optional[str]:
    """
    提取文档内容的便捷函数
    
    Args:
        file_path (str): 文件路径
        file_type (str, optional): 文件类型
        
    Returns:
        str: 提取的文档内容
    """
    return document_processor.extract_content(file_path, file_type)


def get_file_type(file_path: str) -> str:
    """
    获取文件类型
    
    Args:
        file_path (str): 文件路径
        
    Returns:
        str: 文件类型
    """
    return document_processor.get_file_type(file_path)