"""
文件处理工具类
处理文件内容提取、AI类型判断、哈希计算、重复检测等
"""

import os
import hashlib
import time
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.custom_tools.extract_content_from_path import ExtractContentFromPathTool
from src.utils.logger import BeijingLogger

# 初始化 logger
logger = BeijingLogger().get_logger()


class FileContentExtractor:
    """文件内容提取器"""

    def __init__(self):
        self.content_extractor = ExtractContentFromPathTool()

    def _extract_single_file_content(self, file: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """提取单个文件的内容"""
        file_url = file.get('file_url', '')
        file_name = file.get('file_name', '未命名文件')
        file_uuid = file.get('file_uuid') or file.get('file_id', str(uuid.uuid4()))

        logger.info(f"📄 ========== 开始处理文件 ==========")
        logger.info(f"  文件名: {file_name}")
        logger.info(f"  文件UUID: {file_uuid}")
        logger.info(f"  文件URL: {file_url}")

        file_path_from_file = file.get('file_path', '')
        logger.info(f"  文件路径: {file_path_from_file}")

        if not file_url and not file_path_from_file:
            logger.warning(f"❌ [文件: {file_name}] 既没有file_url也没有file_path，跳过内容提取")
            return None

        start_time = time.time()
        file_preview = ""
        file_content = None

        try:
            # 确定文件路径
            logger.info(f"  ├─ 步骤1: 确定文件路径")
            file_path = None
            if "file_path" in file and file["file_path"] and Path(file["file_path"]).exists():
                file_path = file["file_path"]
                logger.info(f"  │  └─ 使用file['file_path']: {file_path}")
            elif file_path_from_file and Path(file_path_from_file).exists():
                file_path = file_path_from_file
                logger.info(f"  │  └─ 使用file_path_from_file: {file_path}")
            else:
                logger.warning(f"❌ [文件: {file_name}] 未找到有效的文件路径")

            # 如果有文件路径，使用提取工具获取内容
            if file_path:
                logger.info(f"  ├─ 步骤2: 使用提取工具处理文件")
                extraction_result = self.content_extractor._run(path=file_path)
                logger.info(f"  ├─ 步骤3: 提取完成，结果类型: {type(extraction_result).__name__}")

                if extraction_result:
                    if isinstance(extraction_result, list):
                        logger.info(f"  ├─ 步骤4: 处理列表结果（ZIP/PDF提取），包含 {len(extraction_result)} 个项")
                        return self._process_zip_extraction(extraction_result, file, file_name, file_uuid, start_time)
                    elif isinstance(extraction_result, dict) and 'file_content' in extraction_result:
                        logger.info(f"  ├─ 步骤4: 处理单个文件内容")
                        content = extraction_result['file_content'] if isinstance(extraction_result['file_content'], str) else str(extraction_result['file_content'])
                        if content and content.strip():
                            logger.info(f"  │  └─ 内容提取成功，长度: {len(content)} 字符")
                            file_preview = content[:500] + ("...[当前文件内容过长，只显示前500字符]" if len(content) >= 500 else "")
                            file_content = content
                        else:
                            logger.warning(f"❌ [文件: {file_name}] 单个文件内容为空")
                            file_preview = "[文件内容为空]"
                            file_content = "[文件内容为空]"
                    else:
                        logger.warning(f"❌ [文件: {file_name}] 提取结果格式异常")
                        logger.warning(f"  └─ 结果类型: {type(extraction_result)}")
                        file_preview = "[文件内容提取失败]"
                else:
                    logger.warning(f"❌ [文件: {file_name}] 提取工具返回空结果")
                    file_preview = "[文件内容提取失败]"
            elif "file_content" in file:
                logger.info(f"  ├─ 步骤2: 从base64内容提取: {file_name}")
                try:
                    import base64
                    decoded = base64.b64decode(file["file_content"]).decode('utf-8', errors='ignore')
                    logger.info(f"  │  └─ base64解码成功，长度: {len(decoded)} 字符")
                    file_preview = decoded[:500] + ("...[当前文件内容过长，只显示前500字符]" if len(decoded) >= 500 else "")
                    file_content = decoded
                except Exception as decode_e:
                    logger.error(f"❌ [文件: {file_name}] base64解码失败: {str(decode_e)}")
                    file_preview = "[无法解析文件内容]"
            else:
                logger.warning(f"❌ [文件: {file_name}] 文件路径不可访问且无file_content")
                file_preview = "[文件路径不可访问]"
        except Exception as e:
            logger.error(f"❌ ========== 文件处理异常 ==========")
            logger.error(f"  文件名: {file_name}")
            logger.error(f"  异常类型: {type(e).__name__}")
            logger.error(f"  异常信息: {str(e)}")
            import traceback
            logger.error(f"  错误堆栈:\n{traceback.format_exc()}")
            file_preview = f"[文件内容提取出错: {str(e)}]"

        extraction_time = time.time() - start_time
        logger.info(f"  ├─ 步骤5: 内容提取完成，耗时: {extraction_time:.3f}秒")

        # 🚨 优化：移除单独的AI判断，改为批量处理（在process_files_concurrently中统一调用）
        # 只提取文件扩展名和基本信息
        file_extension = ""
        if file_name and "." in file_name:
            file_extension = os.path.splitext(file_name)[1].lstrip('.').lower()

        # 判断是否包含医学影像（图片文件从提取结果获取，其他文件默认False）
        has_medical_image = False
        # 🚨 优先使用原始的file_uuid（保持一致性）
        extracted_file_uuid = None
        if isinstance(extraction_result, dict):
            has_medical_image = extraction_result.get('has_medical_image', False)
            extracted_file_uuid = extraction_result.get('file_uuid')  # 获取提取结果中的UUID（仅作为备用）

        # 🔧 修复：优先使用原始UUID而不是提取器生成的UUID，确保与数据库一致
        final_file_uuid = file_uuid if file_uuid else extracted_file_uuid

        final_result = {
            "file_uuid": final_file_uuid,
            "file_name": file_name,
            "file_url": "",
            "file_path": file.get("file_path", ""),
            "file_extension": file_extension,
            "file_type": None,  # 延迟到批量AI判断时填充
            "exam_date": None,  # 延迟到批量AI判断时填充
            "has_medical_image": has_medical_image,
            "file_preview": file_preview,
            "file_content": file_content,
            "extracted_text": file_content,
            "extraction_time": extraction_time,

            # 🔧 修复：传递医学影像相关字段（从extraction_result获取）
            "image_bbox": extraction_result.get('image_bbox') if isinstance(extraction_result, dict) else None,
            "cropped_image_uuid": extraction_result.get('cropped_image_uuid') if isinstance(extraction_result, dict) else None,
            "cropped_image_path": extraction_result.get('cropped_image_path') if isinstance(extraction_result, dict) else None,
            "cropped_image_filename": extraction_result.get('cropped_image_filename') if isinstance(extraction_result, dict) else None,
            "cropped_image_available": extraction_result.get('cropped_image_available', False) if isinstance(extraction_result, dict) else False,
            "cropped_temp_dir": extraction_result.get('cropped_temp_dir') if isinstance(extraction_result, dict) else None,

            # 🔧 修复：传递提取状态字段
            "extraction_success": extraction_result.get('extraction_success') if isinstance(extraction_result, dict) else None,
            "extraction_error": extraction_result.get('extraction_error') if isinstance(extraction_result, dict) else None,
            "extraction_failed": extraction_result.get('extraction_failed', False) if isinstance(extraction_result, dict) else False
        }

        logger.info(f"✅ ========== 文件内容提取完成 ==========")
        logger.info(f"  文件名: {file_name}")
        logger.info(f"  内容长度: {len(file_content) if file_content else 0} 字符")
        logger.info(f"  提取耗时: {extraction_time:.3f}秒")
        logger.info(f"  (文件类型将在批量AI判断阶段确定)")

        return final_result

    def _process_zip_extraction(self, extraction_result: List, file: Dict, file_name: str,
                                file_uuid: str, start_time: float) -> Optional[List[Dict]]:
        """处理ZIP文件提取结果"""
        results = []
        total_content_length = 0
        valid_files_count = 0

        for i, item in enumerate(extraction_result):
            logger.info(f"处理子文件 {i+1}/{len(extraction_result)}: {item.get('file_name', f'子文件_{i}')}")
            if isinstance(item, dict) and 'file_content' in item:
                item_content = item['file_content'] if isinstance(item['file_content'], str) else str(item['file_content'])

                # 🚨 优先使用item中的file_uuid，如果没有再生成新的
                sub_file_uuid = item.get('file_uuid', str(uuid.uuid4()))
                sub_file_name = item.get('file_name', f'子文件_{i}')
                sub_file_extension = ""
                if sub_file_name and "." in sub_file_name:
                    sub_file_extension = os.path.splitext(sub_file_name)[1].lstrip('.').lower()

                if item_content and item_content.strip():
                    total_content_length += len(item_content)
                    valid_files_count += 1
                    logger.info(f"子文件 {sub_file_name} 内容提取成功，长度: {len(item_content)} 字符")

                    # 🚨 优化：移除单独的AI判断，改为批量处理
                    # 从提取结果获取has_medical_image
                    has_medical_image = item.get('has_medical_image', False)

                    sub_result = {
                        "file_uuid": sub_file_uuid,
                        "file_name": sub_file_name,
                        "file_url": "",
                        "file_path": file.get("file_path", ""),
                        "file_extension": sub_file_extension,
                        "file_type": None,  # 延迟到批量AI判断
                        "exam_date": None,  # 延迟到批量AI判断
                        "has_medical_image": has_medical_image,
                        "file_preview": item_content[:500] + ("...[当前文件内容过长，只显示前500字符]" if len(item_content) >= 500 else ""),
                        "file_content": item_content,
                        "extracted_text": item_content,
                        "extraction_time": time.time() - start_time,
                        "parent_zip_file": file_name,
                        "parent_zip_uuid": file_uuid,
                        "is_from_zip": True,
                        "original_file_path": item.get('original_file_path'),
                        "temp_file_available": item.get('temp_file_available', True),

                        # 🚨 传递item中的所有PDF/图片相关字段
                        "source_type": item.get('source_type', 'uploaded'),
                        "parent_pdf_uuid": item.get('parent_pdf_uuid'),
                        "parent_pdf_filename": item.get('parent_pdf_filename'),
                        "page_number": item.get('page_number'),
                        "image_index_in_page": item.get('image_index_in_page'),
                        "position_in_parent": item.get('position_in_parent'),
                        "temp_file_path": item.get('temp_file_path'),
                        "persistent_temp_file": item.get('persistent_temp_file'),
                        "cleanup_temp_dir": item.get('cleanup_temp_dir'),

                        # 裁剪图片信息
                        "image_bbox": item.get('image_bbox'),
                        "cropped_image_uuid": item.get('cropped_image_uuid'),
                        "cropped_image_path": item.get('cropped_image_path'),
                        "cropped_image_filename": item.get('cropped_image_filename'),
                        "cropped_image_available": item.get('cropped_image_available', False),
                        "cropped_temp_dir": item.get('cropped_temp_dir')
                    }
                    results.append(sub_result)
                else:
                    logger.warning(f"子文件 {sub_file_name} 内容为空，但仍记录文件信息")
                    inferred_type = self._infer_file_type_by_extension(sub_file_extension)

                    sub_result = {
                        "file_uuid": sub_file_uuid,
                        "file_name": sub_file_name,
                        "file_url": "",
                        "file_path": file.get("file_path", ""),
                        "file_extension": sub_file_extension,
                        "file_type": inferred_type,
                        "exam_date": None,
                        "has_medical_image": False,
                        "file_preview": f"[文件 {sub_file_name} - {inferred_type}，内容提取失败或为空]",
                        "file_content": f"文件名: {sub_file_name}\n文件类型: {inferred_type}\n状态: 内容提取失败或为空",
                        "extracted_text": f"文件名: {sub_file_name}\n文件类型: {inferred_type}\n状态: 内容提取失败或为空",
                        "extraction_time": time.time() - start_time,
                        "parent_zip_file": file_name,
                        "parent_zip_uuid": file_uuid,
                        "is_from_zip": True,
                        "extraction_failed": True
                    }
                    results.append(sub_result)

        # 生成zip文件的综合预览信息（延迟到AI判断后）
        if results:
            zip_summary = f"ZIP文件包含 {len(results)} 个子文件，其中 {valid_files_count} 个成功提取内容"
            if total_content_length > 0:
                zip_summary += f"，总内容长度: {total_content_length} 字符"

            file_list = []
            for i, result in enumerate(results[:5]):
                # 🚨 修改：暂时不显示file_type（因为AI判断还未执行）
                file_info = f"{result['file_name']}"
                if result.get('file_extension'):
                    file_info += f" (.{result['file_extension']})"
                file_list.append(file_info)

            if len(results) > 5:
                file_list.append(f"... 还有 {len(results) - 5} 个文件")

            zip_summary += "\n文件列表:\n- " + "\n- ".join(file_list)

            for result in results:
                if not result.get('extraction_failed'):
                    result['zip_summary'] = zip_summary

            logger.info(f"ZIP文件处理完成: {file_name}, 子文件数: {len(results)}, 有效文件数: {valid_files_count}")
            return results
        else:
            logger.warning(f"ZIP文件 {file_name} 处理后未找到任何有效子文件")
            return None

    def _infer_file_type_by_extension(self, file_extension: str) -> str:
        """根据文件扩展名推测可能的文件类型"""
        if file_extension in ['pdf', 'docx', 'doc']:
            return "文档文件"
        elif file_extension in ['jpg', 'jpeg', 'png', 'gif', 'bmp']:
            return "图片文件"
        elif file_extension in ['txt', 'md']:
            return "文本文件"
        elif file_extension in ['xlsx', 'xls', 'csv']:
            return "表格文件"
        elif file_extension in ['pptx', 'ppt']:
            return "演示文稿"
        return "其他"

    def _determine_file_type(self, file_name: str, file_content: str) -> Dict[str, Any]:
        """使用大模型智能判断文件类型和时间，支持重试机制"""
        logger.info(f"开始AI文件类型判断: {file_name}")
        logger.info(f"文件内容长度: {len(file_content) if file_content else 0} 字符")

        if not file_content or not file_content.strip():
            logger.warning(f"文件内容为空，跳过AI判断: {file_name}")
            return {"file_type": "其他", "exam_date": None}

        # 检查文件内容是否包含错误信息
        error_indicators = [
            "处理失败", "无法处理", "不可用", "失败", "错误", "error", "failed",
            "图片URL无效", "文件不存在", "权限不足", "多模态API返回内容为空"
        ]

        content_lower = file_content.lower()
        detected_errors = [indicator for indicator in error_indicators if indicator.lower() in content_lower]

        if detected_errors:
            logger.warning(f"检测到错误信息在文件内容中: {file_name}")
            logger.warning(f"检测到的错误指示词: {detected_errors}")
            return {"file_type": "其他", "exam_date": None, "note": f"文件处理失败: {', '.join(detected_errors)}"}

        # 截取前2000字符用于分析
        content_sample = file_content[:2000] if len(file_content) > 2000 else file_content
        logger.info(f"用于AI分析的内容长度: {len(content_sample)} 字符")

        # 🚨 修复：将json导入移到try块外，避免在except中使用未定义的变量
        import json as json_lib

        # 重试机制：最多重试3次
        max_retries = 3
        for attempt in range(max_retries):
            try:
                logger.info(f"AI文件类型判断尝试 {attempt + 1}/{max_retries}: {file_name}")

                from openai import OpenAI

                api_key = os.getenv('FILE_TYPE_LLM_API_KEY')
                base_url = os.getenv('FILE_TYPE_LLM_BASE_URL')
                model_name = os.getenv('FILE_TYPE_LLM_MODEL', 'gemini-2.5-pro')

                if not api_key or not base_url:
                    logger.error(f"文件类型判断 API配置缺失")
                    return {"file_type": "其他", "exam_date": None, "note": "AI API配置缺失"}

                client = OpenAI(api_key=api_key, base_url=base_url)

                prompt = f"""请分析以下文档内容，判断其是否为医疗文档，如果是医疗文档则进一步分类，并识别相关时间。

【文档内容】（前2000字符）:
{content_sample}

【分类规则】：
如果是医疗相关文档，请从以下8个类型中选择：
1. 检验单 - 血液、尿液、生化等实验室检查结果
2. 影像报告 - CT、MRI、X光、超声等影像学检查报告
3. 病理报告 - 组织病理学检查、活检、细胞学检查报告
4. 诊断报告 - 临床诊断书、病历、门诊记录、住院记录
5. 处方单 - 药物处方、用药指导
6. 手术记录 - 手术操作记录、手术报告
7. 护理记录 - 护理观察记录、护理计划
8. 体检报告 - 健康体检、入职体检等综合检查报告

如果不是医疗文档或不属于以上类型，统一归类为"其他"。

【时间识别规则】：
- 对于检查报告（检验单、影像报告、病理报告、体检报告），优先识别检查时间、采样时间、检查日期
- 对于诊疗记录（诊断报告、手术记录、护理记录），识别就诊时间、手术时间、记录时间
- 对于处方单，识别开具时间
- 如果找到多个时间，选择最早的检查/治疗相关时间

请以JSON格式返回：
{{
  "file_type": "类型名称",
  "exam_date": "检查/治疗时间（YYYY-MM-DD格式，如未找到则为null）",
  "note": "如果是其他类型，请简要说明文档内容性质；如果是医疗文档但未找到时间，说明时间情况"
}}

注意：file_type只能是上述8个医疗类型之一，或者"其他"。exam_date必须是YYYY-MM-DD格式或null。"""

                response = client.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    temperature=0.1,
                    max_tokens=6000,
                    timeout=300.0  # 增加超时时间到30秒，确保完整接收响应
                )

                logger.info(f"文件类型判断 API调用成功: {file_name}")

                response_content = response.choices[0].message.content

                # 🚨 调试：打印原始响应内容
                if response_content:
                    logger.info(f"[文件: {file_name}] API原始响应内容长度: {len(response_content)}")
                    logger.info(f"[文件: {file_name}] API原始响应内容: {repr(response_content)}")
                else:
                    logger.warning(f"[文件: {file_name}] AI返回内容为None")

                if not response_content or not response_content.strip():
                    if attempt < max_retries - 1:
                        logger.warning(f"[文件: {file_name}] AI返回内容为空 (尝试 {attempt + 1}/{max_retries})，准备重试")
                        continue
                    else:
                        logger.error(f"[文件: {file_name}] AI返回内容为空，已达到最大重试次数")
                        return {"file_type": "其他", "exam_date": None}

                # 清理响应内容：移除可能的特殊标记
                response_content = response_content.strip()

                # 处理GLM模型返回的特殊标记
                if response_content.startswith("<|begin_of_box|>"):
                    response_content = response_content[len("<|begin_of_box|>"):].strip()
                if response_content.endswith("<|end_of_box|>"):
                    response_content = response_content[:-len("<|end_of_box|>")].strip()

                # 处理 markdown 代码块包裹（如 ```json ... ```）
                if response_content.startswith("```"):
                    # 移除开头的 ```json 或 ```
                    lines = response_content.split('\n')
                    if lines[0].startswith("```"):
                        lines = lines[1:]  # 移除第一行 ```json
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]  # 移除最后一行 ```
                    response_content = '\n'.join(lines).strip()
                    logger.info(f"[文件: {file_name}] 已移除 markdown 代码块包裹")

                logger.info(f"[文件: {file_name}] 清理后的响应内容（前200字符）: {response_content[:200]}")

                # 检查 JSON 完整性（简单检查：是否以 } 结尾）
                if not response_content.rstrip().endswith('}'):
                    logger.warning(f"⚠️ [文件: {file_name}] JSON 可能不完整，响应未以 '}}' 结尾")
                    logger.warning(f"  └─ 最后50字符: {response_content[-50:]}")
                    if attempt < max_retries - 1:
                        logger.warning(f"  └─ 准备重试...")
                        continue
                    else:
                        logger.error(f"❌ [文件: {file_name}] JSON 不完整，已达到最大重试次数")
                        return {"file_type": "其他", "exam_date": None}

                result = json_lib.loads(response_content)
                file_type = result.get("file_type", "其他")
                if file_type is None:
                    file_type = "其他"
                else:
                    file_type = str(file_type).strip()

                exam_date = result.get("exam_date")
                note = result.get("note", "")

                logger.info(f"AI解析结果: {file_name} -> 类型: {file_type}, 时间: {exam_date}, 备注: {note}")

                processed_exam_date = exam_date if exam_date and exam_date != "null" else None

                valid_medical_types = [
                    "检验单", "影像报告", "病理报告", "诊断报告", "处方单",
                    "手术记录", "护理记录", "体检报告"
                ]

                if file_type in valid_medical_types:
                    return {"file_type": file_type, "exam_date": processed_exam_date}
                elif file_type == "其他":
                    return {"file_type": "其他", "exam_date": None}
                else:
                    logger.warning(f"AI返回了未知的文件类型: '{file_type}'，归类为其他")
                    return {"file_type": "其他", "exam_date": None}

            except json_lib.JSONDecodeError as e:
                logger.error(f"❌ [文件: {file_name}] JSON解析失败")
                logger.error(f"  ├─ 错误类型: JSONDecodeError")
                logger.error(f"  ├─ 错误信息: {str(e)}")
                logger.error(f"  ├─ 响应内容长度: {len(response_content) if 'response_content' in locals() else 'N/A'}")
                logger.error(f"  ├─ 完整响应内容: {repr(response_content) if 'response_content' in locals() else 'N/A'}")
                logger.error(f"  └─ 尝试次数: {attempt + 1}/{max_retries}")

                if attempt < max_retries - 1:
                    logger.warning(f"  └─ 准备重试...")
                    continue
                else:
                    logger.error(f"❌ [文件: {file_name}] 已达到最大重试次数")
                    return {"file_type": "其他", "exam_date": None}

            except Exception as e:
                logger.error(f"❌ [文件: {file_name}] AI判断失败")
                logger.error(f"  ├─ 错误类型: {type(e).__name__}")
                logger.error(f"  ├─ 错误信息: {str(e)}")
                logger.error(f"  └─ 尝试次数: {attempt + 1}/{max_retries}")

                if attempt < max_retries - 1:
                    logger.warning(f"  └─ 准备重试...")
                    continue
                else:
                    logger.error(f"❌ [文件: {file_name}] 已达到最大重试次数")
                    return {"file_type": "其他", "exam_date": None}

        return {"file_type": "其他", "exam_date": None}

    def _calculate_file_hash(self, file_path: str) -> Optional[str]:
        """计算文件的MD5哈希值"""
        if not file_path or not os.path.exists(file_path):
            return None

        try:
            hash_md5 = hashlib.md5()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except Exception as e:
            logger.error(f"计算文件哈希值失败 {file_path}: {str(e)}")
            return None

    def _calculate_content_hash(self, content: Any) -> Optional[str]:
        """计算文件内容的MD5哈希值"""
        if not content:
            return None

        try:
            if isinstance(content, str):
                content_bytes = content.encode('utf-8')
            elif isinstance(content, bytes):
                content_bytes = content
            else:
                content_bytes = str(content).encode('utf-8')

            return hashlib.md5(content_bytes).hexdigest()
        except Exception as e:
            logger.error(f"计算内容哈希值失败: {str(e)}")
            return None

    def _detect_duplicate_files(self, files: List[Dict]) -> tuple[List[Dict], List[Dict]]:
        """
        检测并剔除重复文件
        返回去重后的文件列表和重复文件信息
        """
        unique_files = []
        duplicate_files = []
        seen_hashes = set()
        seen_names = set()

        logger.info(f"开始检测重复文件，总计 {len(files)} 个文件")

        for i, file in enumerate(files):
            file_name = file.get('file_name', f'未知文件_{i}')
            file_content = file.get('file_content')
            file_path = file.get('file_path')

            # 计算文件哈希值
            file_hash = None
            content_hash = None

            if file_path and os.path.exists(file_path):
                file_hash = self._calculate_file_hash(file_path)

            if not file_hash and file_content:
                content_hash = self._calculate_content_hash(file_content)
                file_hash = content_hash

            # 检查是否重复
            is_duplicate = False
            duplicate_reason = ""

            if file_hash and file_hash in seen_hashes:
                is_duplicate = True
                duplicate_reason = "文件内容相同"
            elif file_name in seen_names:
                is_duplicate = True
                duplicate_reason = "文件名相同"

            if is_duplicate:
                duplicate_info = {
                    "file_name": file_name,
                    "file_uuid": file.get('file_uuid', file.get('file_id')),
                    "duplicate_reason": duplicate_reason,
                    "file_hash": file_hash,
                    "original_index": i
                }
                duplicate_files.append(duplicate_info)
                logger.info(f"发现重复文件: {file_name} - {duplicate_reason}")
            else:
                unique_files.append(file)
                if file_hash:
                    seen_hashes.add(file_hash)
                seen_names.add(file_name)
                file['file_hash'] = file_hash
                file['content_hash'] = content_hash

        logger.info(f"重复文件检测完成: 唯一文件 {len(unique_files)} 个, 重复文件 {len(duplicate_files)} 个")

        if duplicate_files:
            logger.info("重复文件详情:")
            for dup in duplicate_files:
                logger.info(f"  - {dup['file_name']} ({dup['duplicate_reason']})")

        return unique_files, duplicate_files

    def process_files_concurrently(self, files: List[Dict], max_workers: int = 5) -> List[Dict]:
        """并发处理文件列表，包括AI文件类型判断，现在包含重复文件检测"""
        if not files:
            return []

        logger.info("=" * 80)
        logger.info(f"开始并发处理 {len(files)} 个文件（并发数: {max_workers}）")
        logger.info("=" * 80)

        # ========== 阶段1: 重复文件检测 ==========
        duplicate_detection_start = time.time()
        logger.info("-" * 80)
        logger.info("【阶段1】开始重复文件检测")
        logger.info("-" * 80)

        # 首先进行重复文件检测
        unique_files, duplicate_files = self._detect_duplicate_files(files)

        duplicate_detection_duration = time.time() - duplicate_detection_start
        logger.info("-" * 80)
        logger.info(f"【阶段1】重复文件检测完成，耗时: {duplicate_detection_duration:.2f} 秒")
        logger.info(f"  原始文件: {len(files)} 个，唯一文件: {len(unique_files)} 个，重复文件: {len(duplicate_files)} 个")
        logger.info("-" * 80)

        if duplicate_files:
            logger.info(f"已剔除 {len(duplicate_files)} 个重复文件")

        if not unique_files:
            logger.warning("所有文件都是重复文件，没有需要处理的文件")
            return []

        # ========== 阶段2: 文件内容提取（并发） ==========
        extraction_start_time = time.time()
        logger.info("-" * 80)
        logger.info(f"【阶段2】开始文件内容提取（并发数: {max_workers}）")
        logger.info("-" * 80)

        file_results = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有文件提取任务
            future_to_file = {
                executor.submit(self._extract_single_file_content, file): file
                for file in unique_files
            }

            # 收集文件提取结果
            extraction_results = []
            completed_count = 0
            for future in as_completed(future_to_file):
                try:
                    result = future.result()
                    completed_count += 1
                    logger.info(f"  进度: {completed_count}/{len(unique_files)} 文件已完成提取")
                    if result:
                        if isinstance(result, list):
                            extraction_results.extend(result)
                        else:
                            extraction_results.append(result)
                except Exception as e:
                    file_info = future_to_file[future]
                    logger.error(f"Error processing file {file_info.get('file_name', 'unknown')}: {str(e)}")

            extraction_duration = time.time() - extraction_start_time
            logger.info("-" * 80)
            logger.info(f"【阶段2】文件内容提取完成，耗时: {extraction_duration:.2f} 秒")
            logger.info(f"  提取成功: {len(extraction_results)} 个文件/子文件")
            if extraction_results:
                extraction_times = [r.get('extraction_time', 0) for r in extraction_results if r.get('extraction_time')]
                if extraction_times:
                    avg_time = sum(extraction_times) / len(extraction_times)
                    logger.info(f"  单个文件平均提取时间: {avg_time:.2f} 秒")
            logger.info("-" * 80)

            # ========== 阶段3: AI文件类型判断（批量并发，20并发） ==========
            ai_start_time = time.time()
            if extraction_results:
                logger.info("-" * 80)
                logger.info(f"【阶段3】开始AI文件类型批量判断（并发数: {int(os.getenv('MULTIMODAL_IMAGE_CONCURRENT_WORKERS', '20'))}）")
                logger.info("-" * 80)

                # 🚨 优化：所有文件（包括zip子文件）都统一批量AI判断
                files_need_ai = [result for result in extraction_results if result.get('file_content')]

                logger.info(f"  需要AI判断的文件总数: {len(files_need_ai)} 个")

                if files_need_ai:
                    # 使用环境变量配置的并发数处理AI判断
                    ai_max_workers = int(os.getenv("MULTIMODAL_IMAGE_CONCURRENT_WORKERS", "20"))
                    with ThreadPoolExecutor(max_workers=ai_max_workers) as ai_executor:
                        ai_futures = {
                            ai_executor.submit(self._determine_file_type, result['file_name'], result['file_content']): result
                            for result in files_need_ai
                        }

                        ai_completed_count = 0
                        for ai_future in as_completed(ai_futures):
                            try:
                                result = ai_futures[ai_future]
                                type_result = ai_future.result()
                                ai_completed_count += 1
                                logger.info(f"  进度: {ai_completed_count}/{len(files_need_ai)} AI判断已完成 - {result['file_name']}")
                                if isinstance(type_result, dict):
                                    result['file_type'] = type_result["file_type"]
                                    result['exam_date'] = type_result.get("exam_date")
                                else:
                                    result['file_type'] = type_result
                                    result['exam_date'] = None
                                file_results.append(result)
                            except Exception as e:
                                result = ai_futures[ai_future]
                                logger.error(f"AI文件类型判断失败 {result['file_name']}: {str(e)}")
                                result['file_type'] = "其他"
                                result['exam_date'] = None
                                file_results.append(result)
                else:
                    # 如果没有需要AI判断的文件，直接使用提取结果
                    file_results = extraction_results

                ai_duration = time.time() - ai_start_time
                logger.info("-" * 80)
                logger.info(f"【阶段3】AI文件类型判断完成，耗时: {ai_duration:.2f} 秒")
                if files_need_ai:
                    avg_ai_time = ai_duration / len(files_need_ai)
                    logger.info(f"  单个文件平均AI判断时间: {avg_ai_time:.2f} 秒")
                    concurrent_workers = int(os.getenv("MULTIMODAL_IMAGE_CONCURRENT_WORKERS", "20"))
                    logger.info(f"  并发效率提升: 约 {max_workers / concurrent_workers * 100:.0f}% -> 100% (使用{concurrent_workers}并发)")
                logger.info("-" * 80)

        # ========== 总体统计 ==========
        total_duration = time.time() - extraction_start_time + duplicate_detection_duration
        logger.info("=" * 80)
        logger.info("文件并发处理完成 - 耗时统计")
        logger.info("=" * 80)
        logger.info(f"【阶段1】重复文件检测:        {duplicate_detection_duration:.2f} 秒 - {(duplicate_detection_duration/total_duration*100):.1f}%")
        logger.info(f"【阶段2】文件内容提取:        {extraction_duration:.2f} 秒 - {(extraction_duration/total_duration*100):.1f}%")
        if 'ai_duration' in locals():
            logger.info(f"【阶段3】AI文件类型判断:      {ai_duration:.2f} 秒 - {(ai_duration/total_duration*100):.1f}%")
        logger.info("-" * 80)
        logger.info(f"【总计】文件处理总时间:      {total_duration:.2f} 秒")
        logger.info(f"处理统计: 原始 {len(files)} 个 -> 去重后 {len(unique_files)} 个 -> 成功 {len(file_results)} 个 (重复 {len(duplicate_files)} 个)")
        logger.info("=" * 80)

        # 为结果添加重复文件信息
        if file_results and duplicate_files:
            for result in file_results[:1]:
                result['duplicate_files_detected'] = len(duplicate_files)
                result['duplicate_files_info'] = duplicate_files

        return file_results
