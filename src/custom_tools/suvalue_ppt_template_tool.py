"""
苏州医学PPT模板检索工具 - 基于 ppt.suvalue.com API
用于获取PPT模板信息
"""

from typing import Any, Type, Optional, Dict
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
import os
import logging
import requests

logger = logging.getLogger(__name__)


class SuvaluePPTTemplateToolSchema(BaseModel):
    """苏州医学PPT模板检索工具输入Schema"""
    template_type: int = Field(
        default=1, description="PPT模板类型，默认为1"
    )


class SuvaluePPTTemplateTool(BaseTool):
    name: str = "Get Suvalue PPT Template Info"
    description: str = (
        "获取苏州医学PPT模板信息的工具。"
        "根据template_type参数获取对应的模板结构信息，返回模板的JSON schema。"
        "这个工具应该在生成PPT之前调用，以了解模板需要哪些字段。"
    )
    args_schema: Type[BaseModel] = SuvaluePPTTemplateToolSchema
    result_as_answer: bool = False  # 不直接作为最终答案

    def _run(self, **kwargs: Any) -> Any:
        """获取PPT模板信息"""
        template_type = kwargs.get("template_type", 1)

        # 从环境变量读取API基础URL和认证Token
        api_base_url = os.getenv("SUVALUE_PPT_API_BASE_URL", "https://ppt.suvalue.com/api")
        auth_token = os.getenv("SUVALUE_PPT_AUTH_TOKEN", "").strip()

        print(f"获取Suvalue PPT模板信息")
        print(f"API基础URL: {api_base_url}")
        print(f"模板类型: {template_type}")
        print(f"认证Token: {'已设置' if auth_token else '未设置（允许为空）'}")

        try:
            result = self._get_ppt_template(
                api_base_url=api_base_url,
                auth_token=auth_token,
                template_type=template_type
            )

            if result and result.get("success"):
                print(f"成功获取PPT模板信息")
                return {
                    "success": True,
                    "template_type": template_type,
                    "template_json": result.get("template_json"),
                    "message": result.get("message", "获取模板信息成功")
                }
            else:
                error_msg = result.get("error", "获取PPT模板失败") if result else "获取PPT模板失败"
                print(f"获取模板信息失败: {error_msg}")
                return {"success": False, "error": error_msg}

        except Exception as e:
            logger.error(f"获取PPT模板时出错: {str(e)}", exc_info=True)
            print(f"获取PPT模板时出错: {str(e)}")
            return {"success": False, "error": str(e)}

    def _get_ppt_template(
        self,
        api_base_url: str,
        auth_token: str,
        template_type: int
    ) -> Optional[Dict[str, Any]]:
        """
        获取PPT模板信息

        Args:
            api_base_url: API基础URL
            auth_token: Bearer Token
            template_type: 模板类型

        Returns:
            包含模板信息的字典，失败返回错误信息
        """
        try:
            url = f"{api_base_url}/ppt-template"
            headers = {
                "Accept": "*/*"
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

            response = requests.post(url, headers=headers, params=params, timeout=30)

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

            # 提取模板信息
            template_json = response_data.get("data", {}).get("json", "")

            return {
                "success": True,
                "template_json": template_json,
                "message": response_data.get("msg", "操作成功")
            }

        except requests.exceptions.Timeout:
            error_msg = "请求超时，请检查网络连接"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}
        except requests.exceptions.RequestException as e:
            error_msg = f"网络请求失败: {str(e)}"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}
        except Exception as e:
            error_msg = f"获取PPT模板时出错: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {"success": False, "error": error_msg}
