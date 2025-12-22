# -*- coding: utf-8 -*-
"""
七牛云文件管理工具类
提供文件上传、下载、删除等功能
"""
import os
import time
import requests
from typing import Optional, Tuple, Dict, Any
from qiniu import Auth, put_file, BucketManager, etag
from qiniu.services.storage.uploaders import FormUploader, ResumeUploaderV2
import qiniu.config
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


class QiniuClient:
    """七牛云文件管理客户端"""
    
    def __init__(self, 
                 access_key: Optional[str] = None, 
                 secret_key: Optional[str] = None,
                 bucket_name: Optional[str] = None,
                 bucket_domain: Optional[str] = None):
        """
        初始化七牛云客户端
        
        Args:
            access_key: 七牛云Access Key，如果不提供则从环境变量读取
            secret_key: 七牛云Secret Key，如果不提供则从环境变量读取
            bucket_name: 存储空间名称，如果不提供则从环境变量读取
            bucket_domain: 存储空间绑定的域名，如果不提供则从环境变量读取
        """
        self.access_key = access_key or os.getenv('QINIU_ACCESS_KEY')
        self.secret_key = secret_key or os.getenv('QINIU_SECRET_KEY')
        self.bucket_name = bucket_name or os.getenv('QINIU_BUCKET_NAME')
        self.bucket_domain = bucket_domain or os.getenv('QINIU_BUCKET_DOMAIN')
        
        if not all([self.access_key, self.secret_key, self.bucket_name]):
            raise ValueError("请在环境变量中设置 QINIU_ACCESS_KEY, QINIU_SECRET_KEY, QINIU_BUCKET_NAME")
            
        # 构建鉴权对象
        self.auth = Auth(self.access_key, self.secret_key)
        # 初始化BucketManager
        self.bucket_manager = BucketManager(self.auth)
    
    def upload_file(self, 
                   local_file_path: str, 
                   key: Optional[str] = None,
                   expires: int = 3600,
                   policy: Optional[Dict] = None,
                   use_acceleration: bool = False) -> Tuple[Dict, Dict]:
        """
        上传文件到七牛云
        
        Args:
            local_file_path: 本地文件路径
            key: 上传后保存的文件名，如果不指定则使用文件名
            expires: token过期时间（秒），默认1小时
            policy: 上传策略，可以指定回调等
            use_acceleration: 是否使用上传加速
            
        Returns:
            Tuple[Dict, Dict]: (返回信息, 响应信息)
        """
        if not os.path.exists(local_file_path):
            raise FileNotFoundError(f"文件不存在: {local_file_path}")
            
        # 如果没有指定key，使用文件名
        if key is None:
            key = os.path.basename(local_file_path)
        
        # 清理和标准化文件key
        key = self._normalize_key(key)
        
        # 尝试多种token生成策略来解决带路径文件上传问题
        
        # 方法1: 使用不指定key的token（推荐用于带路径的文件）
        try:
            token = self.auth.upload_token(self.bucket_name, None, expires, policy)
            ret, info = put_file(token, key, local_file_path)

            if info.status_code == 200:
                return ret, info
        except Exception:
            pass

        # 方法2: 使用指定key的token
        try:
            token = self.auth.upload_token(self.bucket_name, key, expires, policy)

            if use_acceleration:
                # 使用上传加速（需要配置加速域名）
                form_uploader = FormUploader(self.bucket_name)
                ret, info = form_uploader.upload(key, local_file_path, up_token=token)
            else:
                # 普通上传
                ret, info = put_file(token, key, local_file_path)

            return ret, info
            
        except Exception as e:
            raise Exception(f"上传文件失败: {str(e)}")
    
    def _normalize_key(self, key: str) -> str:
        """
        标准化文件key，确保符合七牛云的要求
        
        Args:
            key: 原始文件key
            
        Returns:
            str: 标准化后的文件key
        """
        # 移除开头的斜杠
        if key.startswith('/'):
            key = key[1:]
        
        # 替换反斜杠为正斜杠
        key = key.replace('\\', '/')
        
        # 移除连续的斜杠
        import re
        key = re.sub(r'/+', '/', key)
        
        # 确保key不为空
        if not key:
            key = 'unnamed_file'
            
        return key
    
    # 🚨 已移除：upload_data_as_file方法，临时文件处理统一在conversations.py中进行
    
    def download_file(self, 
                     key: str, 
                     local_file_path: Optional[str] = None,
                     expires: int = 3600,
                     is_private: bool = False) -> str:
        """
        下载文件
        
        Args:
            key: 文件在七牛云中的key
            local_file_path: 本地保存路径，如果不指定则返回下载URL
            expires: 私有空间下载链接过期时间（秒）
            is_private: 是否为私有空间
            
        Returns:
            str: 如果指定了本地路径则返回本地文件路径，否则返回下载URL
        """
        if not self.bucket_domain:
            raise ValueError("请在环境变量中设置 QINIU_BUCKET_DOMAIN")
            
        # 构造下载URL
        base_url = f'http://{self.bucket_domain}/{key}'
        
        if is_private:
            # 私有空间需要生成带签名的下载链接
            download_url = self.auth.private_download_url(base_url, expires=expires)
        else:
            # 公开空间直接使用base_url
            download_url = base_url
            
        if local_file_path is None:
            # 如果没有指定本地路径，直接返回下载URL
            return download_url
            
        try:
            # 下载文件到本地
            response = requests.get(download_url)
            response.raise_for_status()
            
            # 确保目录存在
            os.makedirs(os.path.dirname(local_file_path), exist_ok=True)
            
            # 写入文件
            with open(local_file_path, 'wb') as f:
                f.write(response.content)
                
            return local_file_path
            
        except Exception as e:
            raise Exception(f"下载文件失败: {str(e)}")
    
    def delete_file(self, key: str) -> Tuple[Dict, Dict]:
        """
        删除文件
        
        Args:
            key: 要删除的文件key
            
        Returns:
            Tuple[Dict, Dict]: (返回信息, 响应信息)
        """
        try:
            ret, info = self.bucket_manager.delete(self.bucket_name, key)
            return ret, info
        except Exception as e:
            raise Exception(f"删除文件失败: {str(e)}")
    
    def get_file_info(self, key: str) -> Tuple[Dict, Dict]:
        """
        获取文件信息
        
        Args:
            key: 文件key
            
        Returns:
            Tuple[Dict, Dict]: (文件信息, 响应信息)
        """
        try:
            ret, info = self.bucket_manager.stat(self.bucket_name, key)
            return ret, info
        except Exception as e:
            raise Exception(f"获取文件信息失败: {str(e)}")
    
    def list_files(self, 
                  prefix: Optional[str] = None,
                  limit: int = 100,
                  marker: Optional[str] = None) -> Tuple[Dict, bool, Dict]:
        """
        列举文件
        
        Args:
            prefix: 文件前缀过滤
            limit: 返回数量限制
            marker: 分页标记
            
        Returns:
            Tuple[Dict, bool, Dict]: (文件列表, 是否结束, 响应信息)
        """
        try:
            ret, eof, info = self.bucket_manager.list(
                self.bucket_name, prefix, marker, limit, None
            )
            return ret, eof, info
        except Exception as e:
            raise Exception(f"列举文件失败: {str(e)}")
    
    def copy_file(self, 
                 src_key: str, 
                 dest_key: str,
                 dest_bucket: Optional[str] = None) -> Tuple[Dict, Dict]:
        """
        复制文件
        
        Args:
            src_key: 源文件key
            dest_key: 目标文件key
            dest_bucket: 目标bucket，如果不指定则复制到同一bucket
            
        Returns:
            Tuple[Dict, Dict]: (返回信息, 响应信息)
        """
        if dest_bucket is None:
            dest_bucket = self.bucket_name
            
        try:
            ret, info = self.bucket_manager.copy(
                self.bucket_name, src_key, dest_bucket, dest_key
            )
            return ret, info
        except Exception as e:
            raise Exception(f"复制文件失败: {str(e)}")
    
    def move_file(self, 
                 src_key: str, 
                 dest_key: str,
                 dest_bucket: Optional[str] = None) -> Tuple[Dict, Dict]:
        """
        移动文件（重命名）
        
        Args:
            src_key: 源文件key
            dest_key: 目标文件key
            dest_bucket: 目标bucket，如果不指定则移动到同一bucket
            
        Returns:
            Tuple[Dict, Dict]: (返回信息, 响应信息)
        """
        if dest_bucket is None:
            dest_bucket = self.bucket_name
            
        try:
            ret, info = self.bucket_manager.move(
                self.bucket_name, src_key, dest_bucket, dest_key
            )
            return ret, info
        except Exception as e:
            raise Exception(f"移动文件失败: {str(e)}")
    
    def batch_delete(self, keys: list) -> Tuple[Dict, Dict]:
        """
        批量删除文件
        
        Args:
            keys: 要删除的文件key列表
            
        Returns:
            Tuple[Dict, Dict]: (返回信息, 响应信息)
        """
        from qiniu import build_batch_delete
        
        try:
            ops = build_batch_delete(self.bucket_name, keys)
            ret, info = self.bucket_manager.batch(ops)
            return ret, info
        except Exception as e:
            raise Exception(f"批量删除文件失败: {str(e)}")
    
    def generate_upload_token(self, 
                            key: Optional[str] = None,
                            expires: int = 3600,
                            policy: Optional[Dict] = None) -> str:
        """
        生成上传token（用于前端直传）
        
        Args:
            key: 文件key，如果不指定则允许上传任意文件名
            expires: token过期时间（秒）
            policy: 上传策略
            
        Returns:
            str: 上传token
        """
        return self.auth.upload_token(self.bucket_name, key, expires, policy)
    
    def get_private_download_url(self, 
                               key: str, 
                               expires: int = 3600) -> str:
        """
        获取私有空间文件的下载链接
        
        Args:
            key: 文件key
            expires: 链接过期时间（秒）
            
        Returns:
            str: 带签名的下载链接
        """
        if not self.bucket_domain:
            raise ValueError("请在环境变量中设置 QINIU_BUCKET_DOMAIN")
            
        base_url = f'http://{self.bucket_domain}/{key}'
        return self.auth.private_download_url(base_url, expires=expires)


# 便捷函数
def create_qiniu_client() -> QiniuClient:
    """
    创建七牛云客户端实例
    
    Returns:
        QiniuClient: 七牛云客户端实例
    """
    return QiniuClient()


# # 使用示例
# if __name__ == "__main__":
#     # 创建客户端
#     client = create_qiniu_client()
    
#     # 上传文件示例
#     try:
#         ret, info = client.upload_file("./uploads/session_1756879788371_rc8um31/local_1756879809176______20250901154305_10_png_微信图片_20250901154305_10.png", "test.jpg")
#         print(f"上传成功: {ret, info}")
#     except Exception as e:
#         print(f"上传失败: {e}")
    
#     # 下载文件示例
#     try:
#         download_url = client.download_file("uploaded/test.jpg")
#         print(f"下载链接: {download_url}")
#     except Exception as e:
#         print(f"获取下载链接失败: {e}")
    
#     # 删除文件示例
#     try:
#         ret, info = client.delete_file("uploaded/test.jpg")
#         print(f"删除成功: {ret}")
#     except Exception as e:
#         print(f"删除失败: {e}") 