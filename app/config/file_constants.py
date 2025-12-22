"""
文件处理相关常量配置
"""

# 文件扩展名分类
IMAGE_EXTENSIONS = ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'tiff', 'webp', 'heic', 'heif']
BINARY_EXTENSIONS = IMAGE_EXTENSIONS + ['pdf']
DOCUMENT_EXTENSIONS = ['docx', 'doc', 'xlsx', 'xls', 'pptx', 'ppt']
TEXT_EXTENSIONS = ['txt', 'md', 'csv', 'json', 'xml', 'html', 'htm']

# 文件类型映射
MIME_TYPE_TO_EXTENSION = {
    'image/jpeg': '.jpg',
    'image/png': '.png',
    'image/gif': '.gif',
    'image/bmp': '.bmp',
    'image/tiff': '.tiff',
    'image/webp': '.webp',
    'text/plain': '.txt',
    'text/markdown': '.md',
    'application/pdf': '.pdf',
    'application/json': '.json',
    'application/xml': '.xml',
    'text/html': '.html',
    'text/csv': '.csv',
}

# 临时文件路径模板
TEMP_FILE_PATH_TEMPLATE = "./uploads/temp/{conversation_id}"

# 反馈等待机制常量
FEEDBACK_KEY_PREFIX = "feedback_response:"
FEEDBACK_TTL = 300  # 5分钟

# 文件处理常量
MAX_CONCURRENT_FILE_WORKERS = 10  # 提高并发数从3到10，加速文件处理
