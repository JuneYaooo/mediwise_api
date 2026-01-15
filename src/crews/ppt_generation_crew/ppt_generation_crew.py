import os
from dotenv import load_dotenv
load_dotenv()
from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from src.llms import *
from src.utils.json_utils import JsonUtils
from src.utils.logger import BeijingLogger
from datetime import datetime
from pathlib import Path
import uuid as uuid_lib
from src.custom_tools.suvalue_ppt_template_tool import SuvaluePPTTemplateTool
from src.custom_tools.suvalue_generate_ppt_tool import SuvalueGeneratePPTTool
from src.custom_tools.medical_ppt_generation_tool import MedicalPPTGenerationTool
from src.custom_tools.medical_ppt_template import get_template_by_id, list_available_templates
from src.custom_tools.patient_journey_image_generator import generate_patient_journey_image_sync
from src.custom_tools.indicator_chart_image_generator import generate_indicator_chart_images_multiple_sync
from src.custom_tools.treatment_data_processor import TreatmentDataProcessor
from src.custom_tools.treatment_gantt_chart_generator import generate_treatment_gantt_chart_sync
from app.utils.qiniu_upload_service import QiniuUploadService

# 初始化 logger
logger = BeijingLogger().get_logger()


def process_raw_files_data(raw_files_data, filter_no_cropped_image=True):
    """
    处理原始文件数据，只保留需要的字段

    PPT生成策略：
    - 如果有裁剪后的医学影像图片(cropped_image_url)，优先使用裁剪图
    - 否则使用原始图片(cloud_storage_url)

    Args:
        raw_files_data (list): 原始文件数据列表
        filter_no_cropped_image (bool): 是否过滤掉cropped_image_available为false的文件，默认True

    Returns:
        list: 处理后的文件数据列表，每个字典只包含：
            - cloud_storage_url (PPT中使用裁剪图或原图)
            - exam_date
            - file_type
            - has_medical_image
            - extracted_text (前200个字符)
    """
    if not raw_files_data or not isinstance(raw_files_data, list):
        return []

    processed_data = []
    cropped_count = 0
    original_count = 0
    filtered_count = 0

    for file_item in raw_files_data:
        if not isinstance(file_item, dict):
            continue

        # PPT优先使用裁剪后的医学影像
        image_url = file_item.get("cloud_storage_url")
        cropped_image_available = file_item.get("cropped_image_available")
        cropped_image_url = file_item.get("cropped_image_url")
        filename = file_item.get("filename", "未知文件")

        # 🚨 DEBUG: 输出每个文件的裁剪图信息
        logger.info(f"📄 处理文件: {filename}")
        logger.info(f"  ├─ has_medical_image: {file_item.get('has_medical_image', False)}")
        logger.info(f"  ├─ cropped_image_available: {cropped_image_available}")
        logger.info(f"  ├─ cropped_image_url: {cropped_image_url[:80] if cropped_image_url else None}...")
        logger.info(f"  └─ cloud_storage_url: {image_url[:80] if image_url else None}...")

        # 如果启用过滤，则只保留cropped_image_available=True且cropped_image_url不为空的文件
        if filter_no_cropped_image:
            if not cropped_image_available or not cropped_image_url:
                filtered_count += 1
                logger.info(f"  ⚠️ 过滤掉该文件（cropped_image_available={cropped_image_available}, cropped_image_url={'有' if cropped_image_url else '无'}）: {filename}")
                continue

        if cropped_image_available and cropped_image_url:
            image_url = cropped_image_url
            cropped_count += 1
            logger.info(f"  ✅ PPT使用裁剪图: {filename} -> {image_url[:80]}...")
        else:
            original_count += 1
            logger.info(f"  ℹ️ PPT使用原图: {filename}")

        processed_item = {
            "cloud_storage_url": image_url,  # 使用裁剪图或原图
            "exam_date": file_item.get("exam_date"),
            "file_type": file_item.get("file_type"),
            "has_medical_image": file_item.get("has_medical_image", False),
            "extracted_text": file_item.get("extracted_text", "")[:2000]  # 只取前200个字符
        }
        processed_data.append(processed_item)

    logger.info("=" * 100)
    logger.info(f"📊 PPT图片使用统计: 裁剪图 {cropped_count} 个, 原图 {original_count} 个, 过滤 {filtered_count} 个")
    logger.info("=" * 100)

    return processed_data


@CrewBase
class PPTGenerationCrew():
    """PPT generation crew - 支持本地生成和Suvalue API两种模式

    **两种工作流程**:
    1. **Agent流程** (USE_AGENT_WORKFLOW=true)
       - 使用CrewAI Agent自动调用工具
       - 适合复杂的多步骤任务
       - 可能出现JSON解析问题

    2. **直接LLM调用** (USE_AGENT_WORKFLOW=false, 默认)
       - LLM生成数据 -> 直接调用工具
       - 更稳定、更可控
       - 推荐使用

    **使用方式**:
    ```python
    # 方式1: 默认从环境变量读取
    crew = PPTGenerationCrew()

    # 方式2: 手动设置模式
    PPTGenerationCrew.set_mode(
        use_suvalue_api=True,      # True=Suvalue API, False=本地python-pptx
        use_agent_workflow=False   # False=直接LLM调用(推荐), True=Agent流程
    )
    ```

    **环境变量配置**:
    - USE_SUVALUE_PPT: true/false (默认true)
    - USE_AGENT_WORKFLOW: true/false (默认false)
    """

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    # 默认使用Suvalue API（从环境变量读取）
    _use_suvalue_api = os.getenv("USE_SUVALUE_PPT", "true").lower() in ("true", "1", "yes")

    # 控制是否使用Agent流程（默认False，使用直接LLM调用）
    _use_agent_workflow = os.getenv("USE_AGENT_WORKFLOW", "false").lower() in ("true", "1", "yes")

    @classmethod
    def set_mode(cls, use_suvalue_api: bool, use_agent_workflow: bool = None):
        """设置PPT生成模式

        Args:
            use_suvalue_api: True=使用Suvalue API, False=使用本地python-pptx
            use_agent_workflow: True=使用Agent流程, False=使用直接LLM调用（更稳定），None=保持当前设置
        """
        cls._use_suvalue_api = use_suvalue_api
        if use_agent_workflow is not None:
            cls._use_agent_workflow = use_agent_workflow
        logger.info(f"PPTGenerationCrew 模式: {'Suvalue API' if use_suvalue_api else '本地python-pptx'}, "
                   f"工作流: {'Agent流程' if cls._use_agent_workflow else '直接LLM调用'}")

    @agent
    def ppt_content_generator(self) -> Agent:
        """本地模式的agent"""
        return Agent(
            config=self.agents_config['ppt_content_generator'],
            llm=document_generation_llm,
            tools=[MedicalPPTGenerationTool()],
            verbose=True
        )

    @agent
    def suvalue_ppt_data_transformer(self) -> Agent:
        """Suvalue API模式的agent"""
        return Agent(
            config=self.agents_config['suvalue_ppt_data_transformer'],
            llm=document_generation_llm,
            tools=[SuvaluePPTTemplateTool(), SuvalueGeneratePPTTool()],
            verbose=True
        )

    def _generate_ppt_data_with_llm(self, patient_timeline, raw_files_data, patient_name,
                                     patient_journey_image_url, indicator_chart_images,
                                     treatment_gantt_chart_url, treatment_gantt_data=None, template_type=2):
        """
        使用LLM直接生成PPT数据（不使用Agent流程）

        Args:
            patient_timeline: 患者时间轴数据
            raw_files_data: 原始文件数据
            patient_name: 患者姓名
            patient_journey_image_url: 患者时间旅程图片URL
            indicator_chart_images: 核心指标趋势图片列表
            treatment_gantt_chart_url: 治疗甘特图URL
            treatment_gantt_data: 治疗甘特图数据列表（source_file 已替换为文件名）
            template_type: 模板类型（默认2）

        Returns:
            dict: 格式化的PPT数据，可直接传给SuvalueGeneratePPTTool
        """
        try:
            logger.info("使用LLM直接生成PPT数据（绕过Agent流程）")

            # 1. 获取模板信息
            template_tool = SuvaluePPTTemplateTool()
            template_info = template_tool._run(template_type=template_type)

            if not template_info or not template_info.get("success"):
                error_msg = template_info.get("error", "获取模板信息失败") if template_info else "获取模板信息失败"
                logger.error(f"获取Suvalue模板信息失败: {error_msg}")
                return None

            # 模板JSON在 template_json 字段中（包含注释的原始模板）
            template_json_str = template_info.get("template_json", "{}")
            logger.info(f"成功获取模板JSON字符串，长度: {len(template_json_str)}")

            # 不需要解析JSON，直接将原始模板（包含注释）传给LLM
            # LLM能理解JSON中的注释说明

            # 2. 构建提示词
            import json

            # 构建治疗甘特图数据说明
            treatment_gantt_data_str = ""
            if treatment_gantt_data:
                treatment_gantt_data_str = f"\n\n**治疗甘特图数据** (包含每条治疗的详细信息，source_file 已替换为文件名):\n{json.dumps(treatment_gantt_data, ensure_ascii=False, indent=2)}"

            prompt = f"""你是一个医疗数据转换专家，需要将患者数据转换为Suvalue PPT模板格式。

**任务**: 根据下面的模板字段说明和患者数据，生成符合模板要求的JSON数据。

**模板字段说明**（包含注释说明每个字段的用途）:
{template_json_str}

**患者数据**:
患者姓名: {patient_name}
患者时间轴数据: {json.dumps(patient_timeline, ensure_ascii=False)}
原始文件数据: {json.dumps(raw_files_data, ensure_ascii=False)}\n\n{treatment_gantt_data_str}

**预生成的图表URL** (优先使用这些):
- 患者时间旅程图: {patient_journey_image_url or "未生成"}
- 核心指标趋势图: {json.dumps(indicator_chart_images, ensure_ascii=False) if indicator_chart_images else "未生成"}
- 治疗甘特图: {treatment_gantt_chart_url or "未生成"}

**重要要求**:
1. 严格按照模板结构输出，不要添加或删除字段
2. 只使用患者数据中真实存在的信息，不要编造
3. 对于医学原始文件的图像，从[原始文件数据]中选择has_medical_image=true的图片（优先选择裁剪图）
4. 治疗数据可从[治疗甘特图数据]中获取，其中source_file字段已是文件名（不是UUID）
5. 确保所有图片URL是完整的（包含http://或https://）
6. 直接输出JSON格式，去除模板中的所有注释
7. 不要包含任何解释文字、Markdown代码块标记（如```json）

请输出符合模板要求的JSON数据:"""

            # 3. 调用LLM
            logger.info("调用LLM生成PPT数据...")
            try:
                # CrewAI LLM 对象直接调用
                response = document_generation_llm.call(prompt)
                response_text = str(response)
            except AttributeError:
                # 如果是 LangChain LLM，使用 invoke
                try:
                    response = document_generation_llm.invoke(prompt)
                    response_text = response.content if hasattr(response, 'content') else str(response)
                except Exception as e:
                    logger.error(f"LLM调用失败: {e}")
                    return None

            # 4. 提取JSON
            logger.info(f"LLM响应长度: {len(response_text)}")
            logger.info(f"LLM响应前500字符: {response_text[:500]}")

            # 使用JsonUtils提取JSON
            ppt_data = JsonUtils.safe_parse_json(response_text, debug_prefix="LLM生成PPT数据")

            if not ppt_data:
                logger.error("无法从LLM响应中提取有效JSON")
                return None

            # 检查LLM返回的结构，提取实际的PPT数据
            # LLM可能返回包装结构：{"success": true, "template_json": "..."}
            # 或者直接返回PPT数据：{"pptTemplate2Vm": {...}}
            if "template_json" in ppt_data:
                # 如果有template_json字段，需要再解析一次
                logger.info("检测到template_json字段，进行二次解析...")
                template_json_str = ppt_data.get("template_json", "{}")
                ppt_data = JsonUtils.safe_parse_json(template_json_str, debug_prefix="二次解析PPT数据")
                if not ppt_data:
                    logger.error("二次解析失败")
                    return None

            # 验证是否包含pptTemplate2Vm字段
            if "pptTemplate2Vm" not in ppt_data:
                logger.error(f"PPT数据缺少pptTemplate2Vm字段，当前顶层字段: {list(ppt_data.keys())}")
                # 如果顶层就是pptTemplate2Vm的内容，包装一下
                if any(key in ppt_data for key in ["title", "patient", "diag"]):
                    logger.info("检测到顶层包含PPT字段，自动包装为pptTemplate2Vm结构")
                    ppt_data = {"pptTemplate2Vm": ppt_data}
                else:
                    return None

            logger.info(f"✅ 成功生成PPT数据结构")
            logger.info(f"📦 pptTemplate2Vm 包含字段: {list(ppt_data.get('pptTemplate2Vm', {}).keys())[:10]}")
            return ppt_data

        except Exception as e:
            logger.error(f"使用LLM生成PPT数据时出错: {e}", exc_info=True)
            return None

    @task
    def generate_ppt_slides_task(self) -> Task:
        """本地模式的task"""
        return Task(
            config=self.tasks_config['generate_ppt_slides_task']
        )

    @task
    def transform_and_generate_ppt_task(self) -> Task:
        """Suvalue API模式的task"""
        return Task(
            config=self.tasks_config['transform_and_generate_ppt_task']
        )

    @crew
    def crew(self) -> Crew:
        """Creates the PPT generation crew"""
        # 根据模式选择不同的 agents 和 tasks
        if self._use_suvalue_api:
            agents = [self.suvalue_ppt_data_transformer()]
            tasks = [self.transform_and_generate_ppt_task()]
        else:
            agents = [self.ppt_content_generator()]
            tasks = [self.generate_ppt_slides_task()]

        return Crew(
            agents=agents,
            tasks=tasks,
            process=Process.sequential,
            verbose=True
        )

    def generate_ppt(self, patient_timeline, patient_journey, raw_files_data, agent_session_id,
                     auth_token=None, template_id="medical", filter_no_cropped_image=True):
        """
        Generate PPT from patient data

        根据初始化时的 use_suvalue_api 参数选择生成方式：
        - True: 使用Suvalue API生成（需要auth_token）
        - False: 使用本地python-pptx生成（需要template_id）

        Args:
            patient_timeline (dict or list): Patient timeline data for PPT content generation
            patient_journey (dict or list): Patient journey data for image generation (timeline chart, indicator trends)
            raw_files_data (list): Raw files data (will be processed to keep only required fields)
            agent_session_id (str): Session ID for file organization
            auth_token (str, optional): Bearer token for Suvalue API authentication (Suvalue模式必需)
            template_id (str, optional): PPT template ID for local generation (本地模式必需, default: "medical")
            filter_no_cropped_image (bool, optional): 是否过滤掉cropped_image_available为false的文件，默认True

        Returns:
            dict: PPT info
                - Suvalue模式: {"success": bool, "ppt_url": str, "message": str}
                - 本地模式: {"success": bool, "local_path": str, "file_uuid": str, "qiniu_url": str}
        """
        try:
            if self._use_suvalue_api:
                logger.info("Starting Suvalue PPT generation task (API mode)")
            else:
                logger.info("Starting Local PPT generation task (python-pptx mode)")
            current_date = datetime.now().strftime("%Y-%m-%d")

            # 处理 raw_files_data，只保留需要的字段
            processed_raw_files_data = process_raw_files_data(raw_files_data, filter_no_cropped_image=filter_no_cropped_image)
            logger.info(f"处理了 {len(processed_raw_files_data)} 个文件的元数据（仅保留PPT所需字段）")

            # 获取患者姓名
            patient_name = '患者'
            if isinstance(patient_journey, dict):
                # 从 patient_journey 中获取患者姓名
                if 'patient_info' in patient_journey:
                    patient_info = patient_journey.get('patient_info', {})
                    if isinstance(patient_info, dict):
                        basic_info = patient_info.get('basic', {})
                        if isinstance(basic_info, dict):
                            patient_name = basic_info.get('name', '患者')
            elif isinstance(patient_journey, list) and patient_journey:
                # 如果是列表格式，尝试从第一个条目获取患者姓名
                first_entry = patient_journey[0]
                if isinstance(first_entry, dict):
                    patient_name = first_entry.get('patient_name', '患者')

            logger.info(f"Patient name: {patient_name}")

            # ========== 生成患者时间旅程图片并上传到七牛云 ==========
            patient_journey_image_url = None
            patient_journey_image_path = None

            # 提取时间线数据
            timeline_data = None
            if patient_journey:
                if isinstance(patient_journey, dict):
                    # 如果是字典，尝试提取timeline_journey字段
                    timeline_data = patient_journey.get('timeline_journey', patient_journey)
                elif isinstance(patient_journey, list):
                    # 如果是列表，直接使用
                    timeline_data = patient_journey

            if timeline_data:
                try:
                    # 支持列表格式
                    if isinstance(timeline_data, list) and timeline_data:
                        logger.info("开始生成患者时间旅程图片（用于PPT）...")

                        # 生成图片文件名和路径
                        image_uuid = str(uuid_lib.uuid4())
                        output_dir = Path("output/files_extract") / agent_session_id / "ppt_images"
                        output_dir.mkdir(parents=True, exist_ok=True)

                        image_filename = f"patient_journey_{image_uuid}.png"
                        image_path = output_dir / image_filename

                        # 生成图片
                        success = generate_patient_journey_image_sync(
                            patient_journey_data=timeline_data,
                            output_path=str(image_path),
                            patient_name=patient_name
                        )

                        if success and image_path.exists():
                            patient_journey_image_path = str(image_path)
                            logger.info(f"患者时间旅程图片生成成功: {patient_journey_image_path}")

                            # 上传到七牛云
                            try:
                                qiniu_service = QiniuUploadService()
                                qiniu_key = f"patient_journey_ppt/{image_uuid}.png"

                                upload_success, cloud_url, error = qiniu_service.upload_file(
                                    str(image_path),
                                    qiniu_key
                                )

                                if upload_success:
                                    patient_journey_image_url = cloud_url
                                    logger.info(f"患者时间旅程图片已上传到七牛云: {cloud_url}")
                                else:
                                    logger.error(f"上传患者时间旅程图片到七牛云失败: {error}")
                            except Exception as upload_error:
                                logger.error(f"上传患者时间旅程图片到七牛云时出错: {upload_error}")
                        else:
                            logger.warning("患者时间旅程图片生成失败")
                    else:
                        logger.info("患者旅程数据为空或格式不正确，跳过图片生成")

                except Exception as e:
                    logger.error(f"生成或上传患者时间旅程图片时出错: {e}")
                    import traceback
                    logger.error(traceback.format_exc())

            # ========== 生成核心指标趋势图片并上传到七牛云 ==========
            indicator_chart_images = []  # 存储多个指标图片的信息
            if patient_journey:
                try:
                    # 检查是否有indicator_series数据
                    indicator_series = None
                    if isinstance(patient_journey, dict) and 'indicator_series' in patient_journey:
                        indicator_series = patient_journey.get('indicator_series')

                    if indicator_series and isinstance(indicator_series, list) and indicator_series:
                        logger.info(f"开始生成核心指标趋势图片（用于PPT），包含 {len(indicator_series)} 个指标，每个指标单独生成图片...")

                        # 生成图片目录
                        output_dir = Path("output/files_extract") / agent_session_id / "ppt_images" / "indicators"
                        output_dir.mkdir(parents=True, exist_ok=True)

                        # 为每个指标生成独立的图片
                        results = generate_indicator_chart_images_multiple_sync(
                            indicator_series_data=indicator_series,
                            output_dir=str(output_dir),
                            patient_name=patient_name
                        )

                        # 上传每个图片到七牛云
                        qiniu_service = QiniuUploadService()
                        for result in results:
                            if result['success'] and result['file_path']:
                                try:
                                    # 生成唯一的七牛云key
                                    file_path = Path(result['file_path'])
                                    image_uuid = str(uuid_lib.uuid4())
                                    qiniu_key = f"indicator_chart_ppt/{image_uuid}_{file_path.name}"

                                    upload_success, cloud_url, error = qiniu_service.upload_file(
                                        result['file_path'],
                                        qiniu_key
                                    )

                                    if upload_success:
                                        indicator_chart_images.append({
                                            "indicator_name": result['indicator_name'],
                                            "local_path": result['file_path'],
                                            "cloud_url": cloud_url
                                        })
                                        logger.info(f"指标 '{result['indicator_name']}' 图片已上传到七牛云: {cloud_url}")
                                    else:
                                        logger.error(f"上传指标 '{result['indicator_name']}' 图片到七牛云失败: {error}")
                                        # 即使上传失败，也保留本地路径
                                        indicator_chart_images.append({
                                            "indicator_name": result['indicator_name'],
                                            "local_path": result['file_path'],
                                            "cloud_url": None
                                        })
                                except Exception as upload_error:
                                    logger.error(f"上传指标 '{result['indicator_name']}' 图片到七牛云时出错: {upload_error}")
                                    indicator_chart_images.append({
                                        "indicator_name": result['indicator_name'],
                                        "local_path": result['file_path'],
                                        "cloud_url": None
                                    })

                        logger.info(f"核心指标趋势图片生成完成，成功生成 {len(indicator_chart_images)} 个图片")
                    else:
                        logger.info("指标序列数据为空或格式不正确，跳过图片生成")

                except Exception as e:
                    logger.error(f"生成或上传核心指标趋势图片时出错: {e}")
                    import traceback
                    logger.error(traceback.format_exc())

            # ========== 处理治疗甘特图数据并生成图片上传到七牛云 ==========
            #
            # 治疗甘特图数据处理流程：
            # 1. 从 patient_timeline 或 patient_journey 中提取治疗数据
            # 2. 使用 TreatmentDataProcessor 处理数据，生成甘特图所需格式 (gantt_data)
            # 3. 构建 file_uuid -> filename 映射，将 gantt_data 中的 source_file (UUID) 替换为文件名
            # 4. 调用 generate_treatment_gantt_chart_sync 生成甘特图图片 (使用 ECharts 本地渲染)
            # 5. 上传图片到七牛云，获取 treatment_gantt_chart_url
            #
            # gantt_data 数据结构示例（处理后的原始数据，可直接传给PPT模板）：
            # [
            #   {
            #     "treatment_name": "治疗名称",           # 治疗方案名称
            #     "start_date": "2024-01-01",           # 开始日期 (YYYY-MM-DD)
            #     "end_date": "2024-01-15",             # 结束日期 (YYYY-MM-DD)
            #     "category": "化疗/放疗/手术/靶向治疗等", # 治疗类别
            #     "source_file": "来源文件名.pdf",       # 来源文件名（已从UUID转换）
            #     "details": "治疗详情描述"              # 治疗详细信息
            #   },
            #   ...
            # ]
            #
            treatment_gantt_chart_url = None
            treatment_gantt_chart_path = None
            source_file_mapping = {}  # 存储 file_uuid -> filename 的映射

            if patient_timeline or patient_journey:
                try:
                    logger.info("开始处理患者治疗数据并生成甘特图...")

                    # 初始化治疗数据处理器
                    treatment_processor = TreatmentDataProcessor()

                    # 从patient_timeline或patient_journey中提取治疗数据
                    # 优先使用patient_timeline，如果没有则使用patient_journey
                    source_data = patient_timeline if patient_timeline else patient_journey

                    # 调试：检查数据类型和内容
                    logger.info(f"治疗数据源类型: {type(source_data)}")
                    if isinstance(source_data, str):
                        logger.info(f"数据是字符串，长度: {len(source_data)}, 前200字符: {source_data[:200]}")
                    elif isinstance(source_data, dict):
                        logger.info(f"数据是字典，键: {list(source_data.keys())[:10]}")
                    elif isinstance(source_data, list):
                        logger.info(f"数据是列表，长度: {len(source_data)}")

                    # 处理治疗数据生成甘特图所需格式
                    gantt_data = treatment_processor.process_patient_treatments(source_data)

                    if gantt_data and len(gantt_data) > 0:
                        logger.info(f"成功提取 {len(gantt_data)} 条治疗记录，开始生成甘特图...")
                        logger.info(f"甘特图数据: {gantt_data}")

                        # 构建 source_file (file_uuid) -> filename 的映射
                        if raw_files_data and isinstance(raw_files_data, list):
                            for file_item in raw_files_data:
                                if isinstance(file_item, dict):
                                    file_uuid = file_item.get("file_uuid")
                                    filename = file_item.get("filename")
                                    if file_uuid and filename:
                                        source_file_mapping[file_uuid] = filename
                            logger.info(f"构建了 {len(source_file_mapping)} 个文件映射关系")

                        # 替换 gantt_data 中的 source_file (UUID) 为 source_file_name (文件名)
                        for treatment in gantt_data:
                            source_file_uuid = treatment.get("source_file", "")
                            if source_file_uuid and source_file_uuid in source_file_mapping:
                                treatment["source_file"] = source_file_mapping[source_file_uuid]
                            else:
                                treatment["source_file"] = ""

                        logger.info("已将治疗记录的 source_file 从 UUID 替换为文件名")

                        # 生成图片文件名和路径
                        gantt_uuid = str(uuid_lib.uuid4())
                        output_dir = Path("output/files_extract") / agent_session_id / "ppt_images"
                        output_dir.mkdir(parents=True, exist_ok=True)

                        gantt_filename = f"treatment_gantt_{gantt_uuid}.png"
                        gantt_path = output_dir / gantt_filename

                        # 生成甘特图图片（使用ECharts - 本地渲染，无需联网）
                        success = generate_treatment_gantt_chart_sync(
                            gantt_data=gantt_data,
                            output_path=str(gantt_path),
                            patient_name=patient_name,
                            use_google_charts=False  # 使用ECharts，每条治疗记录独立显示
                        )

                        if success and gantt_path.exists():
                            treatment_gantt_chart_path = str(gantt_path)
                            logger.info(f"治疗甘特图生成成功: {treatment_gantt_chart_path}")

                            # 上传到七牛云
                            try:
                                qiniu_service = QiniuUploadService()
                                qiniu_key = f"treatment_gantt_ppt/{gantt_uuid}.png"

                                upload_success, cloud_url, error = qiniu_service.upload_file(
                                    str(gantt_path),
                                    qiniu_key
                                )

                                if upload_success:
                                    treatment_gantt_chart_url = cloud_url
                                    logger.info(f"治疗甘特图已上传到七牛云: {cloud_url}")
                                else:
                                    logger.error(f"上传治疗甘特图到七牛云失败: {error}")
                            except Exception as upload_error:
                                logger.error(f"上传治疗甘特图到七牛云时出错: {upload_error}")
                        else:
                            logger.warning("治疗甘特图生成失败")
                    else:
                        logger.info("未提取到治疗数据，跳过甘特图生成")

                except Exception as e:
                    logger.error(f"生成或上传治疗甘特图时出错: {e}")
                    import traceback
                    logger.error(traceback.format_exc())

            # 确保所有数据都是JSON可序列化的
            import json

            # 转换数据为JSON字符串以确保可序列化
            try:
                patient_timeline_json = json.dumps(patient_timeline, ensure_ascii=False, default=str)
                processed_files_json = json.dumps(processed_raw_files_data, ensure_ascii=False, default=str)
                # 新增：序列化 treatment_gantt_data (已包含 source_file 文件名)
                treatment_gantt_data_json = json.dumps(gantt_data if 'gantt_data' in locals() else [], ensure_ascii=False, default=str)
            except Exception as e:
                logger.error(f"JSON序列化失败: {str(e)}")
                return {"success": False, "error": f"数据序列化失败: {str(e)}"}

            # 根据模式准备不同的输入参数
            if self._use_suvalue_api:
                # Suvalue API模式
                ppt_inputs = {
                    "current_date": current_date,
                    "patient_timeline": patient_timeline_json,
                    "raw_files_data": processed_files_json,
                    "patient_name": patient_name,
                    "auth_token": auth_token or "",  # 允许为空
                    "session_id": agent_session_id,
                    "patient_journey_image_url": patient_journey_image_url or "",
                    "indicator_chart_images": json.dumps(indicator_chart_images, ensure_ascii=False),
                    "treatment_gantt_chart_url": treatment_gantt_chart_url or "",
                    "treatment_gantt_data": treatment_gantt_data_json  # 新增：治疗甘特图数据（source_file 已替换为文件名）
                }
            else:
                # 本地模式
                logger.info(f"Retrieving medical template information for: {template_id}")
                template_info = get_template_by_id(template_id)

                if not template_info:
                    logger.error(f"Failed to retrieve template: {template_id}")
                    return {"success": False, "error": f"Template not found: {template_id}"}

                logger.info(f"Successfully retrieved template: {template_info.get('name')}")

                try:
                    template_info_json = json.dumps(template_info, ensure_ascii=False, default=str)
                except Exception as e:
                    logger.error(f"模板信息JSON序列化失败: {str(e)}")
                    return {"success": False, "error": f"模板信息序列化失败: {str(e)}"}

                ppt_inputs = {
                    "current_date": current_date,
                    "patient_structured_data": patient_timeline_json,
                    "patient_timeline": patient_timeline_json,
                    "raw_files_data": processed_files_json,
                    "template_info": template_info_json,
                    "session_id": agent_session_id,
                    "patient_name": patient_name,
                    "patient_journey_image_url": patient_journey_image_url or "",
                    "patient_journey_image_path": patient_journey_image_path,
                    "indicator_chart_images": json.dumps(indicator_chart_images, ensure_ascii=False),
                    "treatment_gantt_chart_url": treatment_gantt_chart_url or "",
                    "treatment_gantt_chart_path": treatment_gantt_chart_path,
                    "treatment_gantt_data": treatment_gantt_data_json  # 新增：治疗甘特图数据（source_file 已替换为文件名）
                }

            # 根据模式选择执行不同的任务
            mode_name = "Suvalue API" if self._use_suvalue_api else "Local python-pptx"
            workflow_name = "Agent流程" if self._use_agent_workflow else "直接LLM调用"
            logger.info(f"Starting PPT generation task ({mode_name} mode, {workflow_name})")

            # 🆕 判断是否使用直接LLM调用流程（仅Suvalue API模式支持）
            if self._use_suvalue_api and not self._use_agent_workflow:
                logger.info("=" * 80)
                logger.info("使用直接LLM调用流程生成PPT（绕过Agent）")
                logger.info("=" * 80)

                # 1. 使用LLM生成PPT数据
                ppt_data = self._generate_ppt_data_with_llm(
                    patient_timeline=patient_timeline,
                    raw_files_data=processed_raw_files_data,
                    patient_name=patient_name,
                    patient_journey_image_url=patient_journey_image_url,
                    indicator_chart_images=indicator_chart_images,
                    treatment_gantt_chart_url=treatment_gantt_chart_url,
                    treatment_gantt_data=gantt_data if 'gantt_data' in locals() else None,
                    template_type=2
                )

                if not ppt_data:
                    return {"success": False, "error": "LLM生成PPT数据失败"}

                # 2. 直接调用工具生成PPT
                logger.info("调用SuvalueGeneratePPTTool生成PPT...")
                ppt_tool = SuvalueGeneratePPTTool()
                ppt_info = ppt_tool._run(template_type=2, ppt_data=ppt_data)

                if ppt_info and ppt_info.get("success"):
                    logger.info(f"✅ 直接LLM调用流程成功: ppt_url={ppt_info.get('ppt_url')}")
                    # 添加 treatment_gantt_data 和 ppt_data 到返回结果
                    ppt_info["treatment_gantt_data"] = gantt_data if 'gantt_data' in locals() else []
                    ppt_info["ppt_data"] = ppt_data
                    return ppt_info
                else:
                    error_msg = ppt_info.get("error", "PPT生成失败") if ppt_info else "PPT生成失败"
                    logger.error(f"❌ 直接LLM调用流程失败: {error_msg}")
                    return {"success": False, "error": error_msg}

            # 原有的Agent流程
            if self._use_suvalue_api:
                # Suvalue API 模式：单独执行特定任务
                logger.info("Step 1: Executing Suvalue PPT transformation and generation task (Agent流程)")
                task = self.transform_and_generate_ppt_task()
                task.interpolate_inputs_and_add_conversation_history(ppt_inputs)
                result = self.suvalue_ppt_data_transformer().execute_task(task)
                logger.info("Suvalue PPT generation completed")
            else:
                # 本地模式：单独执行特定任务
                logger.info("Step 1: Executing local PPT slides generation task")
                task = self.generate_ppt_slides_task()
                task.interpolate_inputs_and_add_conversation_history(ppt_inputs)
                result = self.ppt_content_generator().execute_task(task)
                logger.info("Local PPT generation completed")

            # 记录原始返回结果用于调试
            logger.info(f"Crew执行结果类型: {type(result)}")
            logger.info(f"Crew执行结果内容: {str(result)[:500]}")

            # 从CrewOutput对象中提取结果
            ppt_info = None

            if hasattr(result, 'json_dict') and result.json_dict:
                ppt_info = result.json_dict
                logger.info("从CrewOutput.json_dict提取结果")
            elif hasattr(result, 'pydantic') and result.pydantic:
                ppt_info = result.pydantic if isinstance(result.pydantic, dict) else result.pydantic.dict()
                logger.info("从CrewOutput.pydantic提取结果")
            elif hasattr(result, 'raw'):
                if isinstance(result.raw, dict):
                    ppt_info = result.raw
                    logger.info("从CrewOutput.raw提取结果（字典）")
                elif isinstance(result.raw, str):
                    # 先尝试从文本中提取JSON（处理包含Thought等非JSON文本的情况）
                    json_str = JsonUtils.extract_json_from_text(result.raw)
                    if json_str:
                        logger.info("从CrewOutput.raw中提取到JSON字符串")
                        ppt_info = JsonUtils.safe_parse_json(json_str, debug_prefix="PPT generation")
                        if ppt_info:
                            logger.info("从CrewOutput.raw提取结果（JSON解析）")
                    else:
                        # 如果提取不到JSON，尝试ast.literal_eval
                        import ast
                        try:
                            ppt_info = ast.literal_eval(result.raw)
                            logger.info("从CrewOutput.raw提取结果（使用ast.literal_eval）")
                        except (ValueError, SyntaxError) as e:
                            logger.warning(f"ast.literal_eval失败且无法提取JSON: {e}")
                            logger.warning(f"原始内容: {result.raw[:500]}")

            if not ppt_info:
                # 最后尝试从整个result字符串中提取JSON
                result_str = str(result)
                json_str = JsonUtils.extract_json_from_text(result_str)
                if json_str:
                    logger.info("从result字符串中提取到JSON")
                    ppt_info = JsonUtils.safe_parse_json(json_str, debug_prefix="PPT generation")
                else:
                    logger.warning(f"无法从result中提取JSON，原始内容: {result_str[:500]}")

            if ppt_info and ppt_info.get("success"):
                # 根据模式添加额外信息
                if not self._use_suvalue_api:
                    # 本地模式：添加图片URL和路径
                    if patient_journey_image_url:
                        ppt_info["patient_journey_image_url"] = patient_journey_image_url
                        logger.info(f"患者时间旅程图片URL已添加到PPT结果: {patient_journey_image_url}")
                    if patient_journey_image_path:
                        ppt_info["patient_journey_image_path"] = patient_journey_image_path
                        logger.info(f"患者时间旅程图片本地路径已添加到PPT结果: {patient_journey_image_path}")
                    if indicator_chart_images:
                        ppt_info["indicator_chart_images"] = indicator_chart_images
                        logger.info(f"核心指标趋势图片信息已添加到PPT结果: {len(indicator_chart_images)} 个图片")
                    if treatment_gantt_chart_url:
                        ppt_info["treatment_gantt_chart_url"] = treatment_gantt_chart_url
                        logger.info(f"治疗甘特图URL已添加到PPT结果: {treatment_gantt_chart_url}")
                    if treatment_gantt_chart_path:
                        ppt_info["treatment_gantt_chart_path"] = treatment_gantt_chart_path
                        logger.info(f"治疗甘特图本地路径已添加到PPT结果: {treatment_gantt_chart_path}")

                    logger.info(f"Local PPT生成成功: local_path={ppt_info.get('local_path')}, "
                              f"file_uuid={ppt_info.get('file_uuid')}, qiniu_url={ppt_info.get('qiniu_url')}")
                    if not ppt_info.get('file_uuid'):
                        logger.warning("Local PPT生成成功但缺少file_uuid字段（可能未上传到七牛云）")
                else:
                    # Suvalue API模式
                    logger.info(f"Suvalue PPT生成成功: ppt_url={ppt_info.get('ppt_url')}")

                return ppt_info
            else:
                if ppt_info is None or not ppt_info:
                    error_msg = f"无法解析Crew返回结果。原始结果: {str(result)[:200]}"
                elif not isinstance(ppt_info, dict):
                    error_msg = f"Crew返回结果不是字典类型: {type(ppt_info)}, 内容: {str(ppt_info)[:200]}"
                else:
                    error_msg = ppt_info.get("error", f"PPT生成失败但未提供错误信息。返回内容: {str(ppt_info)[:200]}")

                logger.error(f"PPT生成失败 ({mode_name} mode): {error_msg}")
                return {"success": False, "error": error_msg}

        except Exception as e:
            mode_name = "Suvalue API" if self._use_suvalue_api else "Local python-pptx"
            logger.error(f"Error in PPT generation ({mode_name} mode): {e}", exc_info=True)
            return {"success": False, "error": str(e)}
