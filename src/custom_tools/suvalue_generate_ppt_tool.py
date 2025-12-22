"""
苏州医学PPT生成执行工具 - 基于 ppt.suvalue.com API
用于调用API生成PPT文件
"""

from typing import Any, Type, Optional, Dict
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
import os
import logging
import requests
import re
from urllib.parse import urlparse, parse_qs
from qiniu import Auth
from boto3 import client
from botocore.client import Config
from botocore.exceptions import NoCredentialsError

logger = logging.getLogger(__name__)


def _is_qiniu_url(url: str) -> bool:
    """
    判断URL是否为七牛云URL

    Args:
        url: 待检测的URL

    Returns:
        是否为七牛云URL
    """
    if not url or not isinstance(url, str):
        return False

    # 匹配七牛云域名模式（包括s3协议和直接域名）
    # 支持格式：
    # - http://mediwise.s3.cn-east-1.qiniucs.com/xxx.jpg
    # - http://bucket.qiniucdn.com/xxx.jpg
    # - http://bucket.clouddn.com/xxx.jpg
    qiniu_patterns = [
        r'\.qiniucs\.com',      # S3协议域名
        r'\.qiniucdn\.com',     # CDN加速域名
        r'\.clouddn\.com',      # 旧版CDN域名
    ]

    return any(re.search(pattern, url) for pattern in qiniu_patterns)


def _is_authenticated_url(url: str) -> bool:
    """
    判断URL是否已经过鉴权

    Args:
        url: 待检测的URL

    Returns:
        是否已鉴权
    """
    if not url or not isinstance(url, str):
        return False

    # 检查是否包含鉴权参数
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)

    # AWS S3签名关键参数
    aws_params = ['X-Amz-Algorithm', 'X-Amz-Signature', 'X-Amz-Credential']

    # 七牛云鉴权参数 (e=过期时间, token=签名token)
    qiniu_params = ['e', 'token']

    # 如果包含任意一组鉴权参数，则认为已鉴权
    has_aws_auth = any(param in query_params for param in aws_params)
    has_qiniu_auth = all(param in query_params for param in qiniu_params)

    return has_aws_auth or has_qiniu_auth


def _generate_authenticated_url(url: str, expires: int = 3600) -> str:
    """
    为七牛云URL生成AWS S3格式的鉴权链接

    Args:
        url: 原始七牛云URL
        expires: 过期时间（秒），默认1小时

    Returns:
        鉴权后的URL，如果失败返回原URL
    """
    try:
        # 如果不是七牛云URL，直接返回
        if not _is_qiniu_url(url):
            return url

        # 如果已经鉴权，直接返回
        if _is_authenticated_url(url):
            logger.info(f"URL already authenticated: {url[:100]}...")
            return url

        # 获取七牛云配置
        access_key = os.getenv('QINIU_ACCESS_KEY')
        secret_key = os.getenv('QINIU_SECRET_KEY')
        bucket_name = os.getenv('QINIU_BUCKET_NAME')
        region = os.getenv('QINIU_REGION', 'cn-east-1')
        endpoint = os.getenv('QINIU_ENDPOINT', 'https://s3.cn-east-1.qiniucs.com')

        if not access_key or not secret_key or not bucket_name:
            logger.warning("Qiniu credentials not found, returning original URL")
            return url

        # 从URL中提取对象key
        parsed_url = urlparse(url)
        # 移除开头的斜杠
        object_key = parsed_url.path.lstrip('/')

        if not object_key:
            logger.warning(f"Cannot extract object key from URL: {url}")
            return url

        # 创建S3客户端（使用七牛云的S3兼容接口）
        s3_client = client(
            's3',
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            endpoint_url=endpoint,
            region_name=region,
            config=Config(signature_version='s3v4')
        )

        # 生成预签名URL
        authenticated_url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': bucket_name,
                'Key': object_key
            },
            ExpiresIn=expires
        )

        logger.info(f"Generated AWS S3 authenticated URL for: {url[:100]}...")
        return authenticated_url

    except NoCredentialsError:
        logger.error("AWS credentials not available")
        return url
    except Exception as e:
        logger.error(f"Failed to generate authenticated URL for {url}: {str(e)}")
        return url


def _process_urls_in_data(data: Any, expires: int = 3600) -> Any:
    """
    递归处理数据结构中的所有七牛云URL，为其添加鉴权

    Args:
        data: 待处理的数据（可以是dict、list或其他类型）
        expires: URL过期时间（秒）

    Returns:
        处理后的数据
    """
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            # 如果key名称包含url或image相关字段，且值为字符串，尝试鉴权
            if isinstance(value, str) and any(keyword in key.lower() for keyword in ['url', 'img', 'image']):
                original_url = value
                authenticated_url = _generate_authenticated_url(value, expires)
                if original_url != authenticated_url:
                    logger.info(f"🔐 Field '{key}' URL authenticated: {original_url[:80]}... -> {authenticated_url[:80]}...")
                result[key] = authenticated_url
            else:
                result[key] = _process_urls_in_data(value, expires)
        return result
    elif isinstance(data, list):
        # 对于列表，检查是否所有元素都是字符串且看起来像URL
        # 如果是URL列表（如imageList），则对每个URL进行鉴权
        if all(isinstance(item, str) and (_is_qiniu_url(item) or item.startswith('http')) for item in data):
            result = []
            for url in data:
                original_url = url
                authenticated_url = _generate_authenticated_url(url, expires)
                if original_url != authenticated_url:
                    logger.info(f"🔐 List item URL authenticated: {original_url[:80]}... -> {authenticated_url[:80]}...")
                result.append(authenticated_url)
            return result
        else:
            # 否则递归处理列表中的每个元素
            return [_process_urls_in_data(item, expires) for item in data]
    else:
        return data


class SuvalueGeneratePPTToolSchema(BaseModel):
    """苏州医学PPT生成工具输入Schema"""
    template_type: int = Field(
        ..., description="PPT模板类型（必须先通过SuvaluePPTTemplateTool获取）"
    )
    ppt_data: Dict[str, Any] = Field(
        ..., description="根据模板要求格式化的PPT数据，必须包含模板所需的所有字段"
    )


class SuvalueGeneratePPTTool(BaseTool):
    name: str = "Generate PPT Using Suvalue API"
    description: str = (
        "使用苏州医学PPT生成API生成医疗病例PPT的工具。"
        "需要提供template_type和根据模板格式准备好的ppt_data。"
        "在调用此工具前，应先使用SuvaluePPTTemplateTool获取模板信息。"
    )
    args_schema: Type[BaseModel] = SuvalueGeneratePPTToolSchema
    result_as_answer: bool = True  # 工具返回结果直接作为最终答案

    def _run(self, **kwargs: Any) -> Any:
        """执行PPT生成"""
        ppt_data = kwargs.get("ppt_data")
        template_type = kwargs.get("template_type")

        # 从环境变量读取API基础URL和认证Token
        api_base_url = os.getenv("SUVALUE_PPT_API_BASE_URL", "https://ppt.suvalue.com/api")
        auth_token = os.getenv("SUVALUE_PPT_AUTH_TOKEN", "").strip()

        # 验证必需参数
        if not ppt_data:
            return {"success": False, "error": "ppt_data参数不能为空"}

        if not isinstance(ppt_data, dict):
            return {"success": False, "error": "ppt_data必须是字典类型"}

        if template_type is None:
            return {"success": False, "error": "template_type参数不能为空"}

        print(f"开始使用Suvalue API生成医疗病例PPT")
        print(f"API基础URL: {api_base_url}")
        print(f"模板类型: {template_type}")
        print(f"认证Token: {'已设置' if auth_token else '未设置（允许为空）'}")

        try:
            # 生成PPT
            print("调用API生成PPT...")
            result = self._generate_ppt(
                api_base_url=api_base_url,
                auth_token=auth_token,
                ppt_data=ppt_data,
                template_type=template_type
            )

            if result and result.get("success"):
                ppt_url = result.get("ppt_url")
                print(f"PPT生成成功")
                print(f"PPT下载地址: {ppt_url}")
                return {
                    "success": True,
                    "ppt_url": ppt_url,
                    "message": "PPT生成成功"
                }
            else:
                error_msg = result.get("error", "PPT生成失败") if result else "PPT生成失败"
                return {"success": False, "error": error_msg}

        except Exception as e:
            logger.error(f"PPT生成过程中出错: {str(e)}", exc_info=True)
            print(f"PPT生成过程中出错: {str(e)}")
            return {"success": False, "error": str(e)}

    def _generate_ppt(
        self,
        api_base_url: str,
        auth_token: str,
        ppt_data: Dict[str, Any],
        template_type: int
    ) -> Optional[Dict[str, Any]]:
        """
        生成PPT

        Args:
            api_base_url: API基础URL
            auth_token: Bearer Token
            ppt_data: PPT数据
            template_type: 模板类型

        Returns:
            包含PPT URL的字典，失败返回错误信息
        """
        try:
            # 在发送数据前，对所有七牛云URL进行鉴权处理
            print("🔐 开始对PPT数据中的七牛云URL进行鉴权处理...")
            authenticated_ppt_data = _process_urls_in_data(ppt_data, expires=7200)  # 2小时过期
            print("✅ URL鉴权处理完成")

            url = f"{api_base_url}/ModifyAndSavePPT"
            headers = {
                "Accept": "*/*",
                "Content-Type": "application/json"
            }
            # 只有当auth_token不为空时才添加Authorization头
            if auth_token:
                headers["Authorization"] = f"Bearer {auth_token}"

            params = {
                "type": template_type
            }

            print(f"请求URL: {url}")
            print(f"请求参数: {params}")
            print(f"请求Headers: {headers}")

            # 打印完整的请求Body（使用JSON格式化以便阅读）
            import json
            try:
                print(f"请求Body (完整):")
                print(json.dumps(authenticated_ppt_data, ensure_ascii=False, indent=2))
            except Exception as e:
                print(f"请求Body (原始): {authenticated_ppt_data}")
                print(f"JSON格式化失败: {e}")

            # 发送POST请求，data以JSON格式传递，使用鉴权后的数据
            response = requests.post(
                url,
                headers=headers,
                params=params,
                json=authenticated_ppt_data,
                timeout=60  # 生成PPT可能需要较长时间
            )

            # 打印完整响应信息
            print(f"\n{'='*60}")
            print(f"响应状态码: {response.status_code}")
            print(f"响应Headers: {dict(response.headers)}")
            print(f"响应内容: {response.text}")
            print(f"{'='*60}\n")

            # 检查响应状态码
            if response.status_code != 200:
                # 尝试获取详细错误信息
                try:
                    error_detail = response.json()
                    error_msg = f"API请求失败，状态码: {response.status_code}"
                    logger.error(f"{error_msg}\n完整响应: {error_detail}")
                    print(f"完整错误响应: {error_detail}")
                    return {"success": False, "error": error_msg, "status_code": response.status_code, "response_data": error_detail}
                except:
                    error_msg = f"API请求失败，状态码: {response.status_code}"
                    logger.error(f"{error_msg}\n响应内容: {response.text}")
                    print(f"响应内容: {response.text}")
                    return {"success": False, "error": error_msg, "status_code": response.status_code, "response_text": response.text}

            # 解析响应JSON
            response_data = response.json()

            # 检查API返回的code
            if response_data.get("code") != "200":
                error_msg = f"API返回错误: {response_data.get('msg', '未知错误')}"
                logger.error(error_msg)
                return {"success": False, "error": error_msg}

            # 提取PPT URL
            ppt_url = response_data.get("data", {}).get("url", "")

            if not ppt_url:
                error_msg = "API未返回PPT URL"
                logger.error(error_msg)
                return {"success": False, "error": error_msg}

            # 确保URL包含协议
            if not ppt_url.startswith("http://") and not ppt_url.startswith("https://"):
                ppt_url = f"https://{ppt_url}"

            return {
                "success": True,
                "ppt_url": ppt_url,
                "message": response_data.get("msg", "操作成功")
            }

        except requests.exceptions.Timeout:
            error_msg = "请求超时，PPT生成时间过长"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}
        except requests.exceptions.RequestException as e:
            error_msg = f"网络请求失败: {str(e)}"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}
        except Exception as e:
            error_msg = f"生成PPT时出错: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {"success": False, "error": error_msg}
