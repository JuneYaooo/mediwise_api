import os
from dotenv import load_dotenv
load_dotenv()
from crewai import Agent, Crew, Process, Task, LLM
from crewai.project import CrewBase, agent, crew, task
from src.llms import *
from src.utils.json_utils import JsonUtils
from src.utils.logger import BeijingLogger
from datetime import datetime
import re
import unicodedata
import concurrent.futures
from src.custom_tools.get_disease_list_tool import get_disease_list_tool
from src.custom_tools.query_disease_config_tool import query_disease_config_tool
from pathlib import Path
import time
import json
import uuid as uuid_lib
from src.custom_tools.patient_journey_image_generator import generate_patient_journey_image_sync
from src.custom_tools.indicator_chart_image_generator import generate_indicator_chart_image_sync
from app.utils.qiniu_upload_service import QiniuUploadService
from app.utils.file_metadata_builder import FileMetadataBuilder  # 新增导入

# 初始化 logger
logger = BeijingLogger().get_logger()

@CrewBase
class PatientDataCrew():
    """Patient data processing crew"""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"
    max_concurrency = 10  # 默认最大并发数
    
    def __init__(self, max_concurrency=None):
        """
        初始化PatientDataCrew

        Args:
            max_concurrency (int, optional): 最大并发处理数，默认为None，将使用类变量默认值
        """
        if max_concurrency is not None:
            self.max_concurrency = max_concurrency

    @staticmethod
    def estimate_tokens(text):
        """
        估算文本中的token数量，基于以下规则：
        - 英文字符: 约 0.3 个token/字符
        - 中文字符: 约 0.6 个token/字符
        - 其他字符: 约 0.5 个token/字符（保守估计）
        
        Args:
            text (str): 输入文本
            
        Returns:
            float: 估算的token数量
        """
        if not text:
            return 0
            
        # 计数器初始化
        english_chars = 0
        chinese_chars = 0
        other_chars = 0
        
        # 遍历文本中的每个字符
        for char in text:
            # 跳过空白字符
            if char.isspace():
                continue
                
            # 检查是否为ASCII范围内的英文字符
            if ord(char) < 128 and (char.isalpha() or char.isdigit() or char in ",.!?;:'\"()[]{}"):
                english_chars += 1
            # 检查是否为中文字符
            elif any([
                'CJK' in unicodedata.name(char, ''),
                'HIRAGANA' in unicodedata.name(char, ''),
                'KATAKANA' in unicodedata.name(char, ''),
                'IDEOGRAPHIC' in unicodedata.name(char, '')
            ]):
                chinese_chars += 1
            # 其他字符
            else:
                other_chars += 1
        
        # 根据不同字符类型计算token估算值
        estimated_tokens = (
            english_chars * 0.3 +  # 英文字符
            chinese_chars * 0.6 +  # 中文字符
            other_chars * 0.5      # 其他字符
        )
        
        # 保守起见，向上取整并添加一点额外缓冲
        return int(estimated_tokens * 1.1) + 1

    def _save_patient_data_to_output(self, session_id, patient_content, full_structure_data, patient_journey=None, mdt_simple_report=None):
        """将患者数据保存到输出目录"""
        try:
            if not session_id:
                logger.warning("No session_id provided, skipping patient data save")
                return None
            
            # 创建输出目录结构（与intent_determine_crew相同的目录结构）
            output_dir = Path("output/files_extract") / session_id
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # 确保数据中的Unicode编码被正确解码
            def decode_unicode_recursive(obj):
                """递归解码对象中的Unicode转义序列"""
                if isinstance(obj, dict):
                    return {key: decode_unicode_recursive(value) for key, value in obj.items()}
                elif isinstance(obj, list):
                    return [decode_unicode_recursive(item) for item in obj]
                elif isinstance(obj, str):
                    try:
                        # 处理Unicode转义序列
                        if '\\u' in obj:
                            return obj.encode().decode('unicode_escape')
                        return obj
                    except Exception:
                        return obj
                else:
                    return obj
            
            # 🚨 简化：直接准备要保存的数据，不需要复杂的历史记录
            patient_data = {
                "session_id": session_id,
                "timestamp": time.time(),
                "processing_date": datetime.now().isoformat(),
                "patient_content": decode_unicode_recursive(patient_content) if isinstance(patient_content, str) else patient_content,
                "full_structure_data": decode_unicode_recursive(full_structure_data),
                "patient_journey": decode_unicode_recursive(patient_journey) if patient_journey is not None else None,
                "mdt_simple_report": decode_unicode_recursive(mdt_simple_report) if mdt_simple_report is not None else None
            }
            
            # 如果已存在文件，先备份
            output_file = output_dir / "patient_data.json"
            if output_file.exists():
                # 创建备份文件
                backup_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_file = output_dir / f"patient_data_backup_{backup_timestamp}.json"
                import shutil
                shutil.copy2(output_file, backup_file)
                logger.info(f"已创建备份文件: {backup_file}")
            
            # 保存到JSON文件
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(patient_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"患者数据已保存到: {output_file}")
            
            return str(output_file)
            
        except Exception as e:
            logger.error(f"保存患者数据时出错: {str(e)}")
            return None
    
    @agent
    def file_preprocessor(self) -> Agent:
        return Agent(
            config=self.agents_config['file_preprocessor'],
            llm=general_llm,
            verbose=True
        )

    @agent
    def disease_config_agent(self) -> Agent:
        return Agent(
            config=self.agents_config['disease_config_agent'],
            tools=[get_disease_list_tool, query_disease_config_tool],
            llm=document_generation_llm,
            verbose=True
        )

    @agent
    def patient_data_processor(self) -> Agent:
        return Agent(
            config=self.agents_config['patient_data_processor'],
            llm=document_generation_llm,
            verbose=True
        )

    @agent
    def core_points_extractor(self) -> Agent:
        return Agent(
            config=self.agents_config['core_points_extractor'],
            llm=document_generation_llm,
            verbose=True
        )

    @agent
    def mdt_report_generator(self) -> Agent:
        return Agent(
            config=self.agents_config['mdt_report_generator'],
            llm=document_generation_llm,
            verbose=True
        )
    
    @task
    def preprocess_files_task(self) -> Task:
        return Task(
            config=self.tasks_config['preprocess_files_task']
        )

    @task
    def get_disease_config_task(self) -> Task:
        return Task(
            config=self.tasks_config['get_disease_config_task']
        )

    @task
    def process_patient_data_task(self) -> Task:
        return Task(
            config=self.tasks_config['process_patient_data_task'],
            context=[self.get_disease_config_task()]  # 依赖疾病配置任务的输出
        )

    @task
    def extract_core_points_task(self) -> Task:
        return Task(
            config=self.tasks_config['extract_core_points_task'],
            context=[self.get_disease_config_task()]  # 依赖疾病配置任务的输出
        )

    @task
    def generate_mdt_report_task(self) -> Task:
        return Task(
            config=self.tasks_config['generate_mdt_report_task'],
            context=[self.get_disease_config_task()]  # 依赖疾病配置任务的输出
        )

    @crew
    def crew(self) -> Crew:
        """Creates the patient data processing crew with 30-minute timeout"""
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
            max_execution_time=1800  # 30 minutes timeout (30 * 60 = 1800 seconds)
        )

    def get_structured_patient_data(self, patient_info, patient_timeline, messages, files, agent_session_id, existing_patient_data=None):
        """
        Process patient information into a structured timeline with detailed categorized information.
        支持增量更新：如果存在现有患者数据，将新信息与现有信息合并更新。

        Args:
            patient_info (str): Raw patient information text
            patient_timeline (str): Current patient timeline (may be empty for new patients)
            messages (list): Conversation messages history
            files (list): List of file objects with their content
            agent_session_id (str): The session ID for the agent
            existing_patient_data (dict): 现有患者数据，包含timeline、journey、mdt_report等
        Returns:
            dict: Structured patient data with timeline and categorized details
        """
        # 将生成器版本的结果收集起来返回
        result = None
        for progress_data in self.get_structured_patient_data_stream(
            patient_info=patient_info,
            patient_timeline=patient_timeline,
            messages=messages,
            files=files,
            agent_session_id=agent_session_id,
            existing_patient_data=existing_patient_data
        ):
            if progress_data.get("type") == "result":
                result = progress_data.get("data")
        return result if result else {"error": "No result returned"}

    def get_structured_patient_data_stream(self, patient_info, patient_timeline, messages, files, agent_session_id, existing_patient_data=None):
        """
        Process patient information into a structured timeline (generator version).
        实时返回处理进度和最终结果。

        Args:
            patient_info (str): Raw patient information text
            patient_timeline (str): Current patient timeline (may be empty for new patients)
            messages (list): Conversation messages history
            files (list): List of file objects with their content
            agent_session_id (str): The session ID for the agent
            existing_patient_data (dict): 现有患者数据，包含timeline、journey、mdt_report等

        Yields:
            dict: Progress updates or final result
                - type: "progress" or "result"
                - For progress: stage, message, progress (0-100)
                - For result: data (final result dict)
        """
        try:
            # ========== 总体开始时间 ==========
            overall_start_time = time.time()
            logger.info("=" * 80)
            logger.info("开始患者数据处理流程")
            logger.info("=" * 80)
            
            # 设置当前日期
            current_date = datetime.now().strftime("%Y-%m-%d")
            
            # 🚨 修改：使用传入的existing_patient_data参数而不是从本地文件加载
            existing_timeline = None
            existing_patient_journey = None
            existing_mdt_report = None
            
            if existing_patient_data:
                logger.info("Found existing patient data from database, will perform incremental update")
                
                # 安全地获取现有数据，处理可能为None的情况
                patient_timeline_data = existing_patient_data.get("patient_timeline")
                existing_timeline = patient_timeline_data.get("timeline", []) if patient_timeline_data else []
                
                existing_patient_journey = existing_patient_data.get("patient_journey")
                if existing_patient_journey is None:
                    existing_patient_journey = {}
                
                existing_mdt_report = existing_patient_data.get("mdt_simple_report")
                if existing_mdt_report is None:
                    existing_mdt_report = {}
                
                logger.info(f"Existing data contains {len(existing_timeline)} timeline entries")
                
                # 记录现有数据的详细信息
                if existing_patient_journey and "timeline_journey" in existing_patient_journey:
                    logger.info(f"Existing patient journey contains {len(existing_patient_journey['timeline_journey'])} journey events")
                if existing_patient_journey and "indicator_series" in existing_patient_journey:
                    logger.info(f"Existing patient journey contains {len(existing_patient_journey['indicator_series'])} indicator series")
                if existing_mdt_report:
                    logger.info(f"Existing MDT report contains data")
            else:
                logger.info("No existing patient data found, will create new patient record")
            
            # ========== 阶段1: 文件预处理 ==========
            file_preprocessing_start_time = time.time()
            logger.info("-" * 80)
            logger.info("【阶段1】开始文件预处理")
            logger.info("-" * 80)

            # 发送进度更新
            yield {"type": "progress", "stage": "file_preprocessing", "message": "正在预处理上传的文件", "progress": 10}

            # 确定是否需要文件预处理
            if not files or len(files) == 0:
                logger.info("No files to process, skipping file preprocessing step")
                # 将messages转换为字符串格式
                if isinstance(messages, list):
                    messages_text = "\n".join([str(msg) for msg in messages if msg])
                    preprocessed_info = f"{patient_info}\n\n对话历史:\n{messages_text}" if messages_text else patient_info
                else:
                    preprocessed_info = str(messages) if messages else patient_info
            else:
                # 过滤文件：跳过从PDF提取的图片，避免重复
                # 因为PDF的extracted_text已经包含了图片描述
                filtered_files = FileMetadataBuilder.filter_for_llm_input(files)
                logger.info(f"过滤后用于LLM的文件数: {len(filtered_files)} (原始: {len(files)})")

                # 首先计算所有文件的总token数
                total_file_tokens = 0
                valid_file_count = 0
                for file in filtered_files:
                    # 优先使用file_content，兼容extracted_text
                    file_content = file.get('file_content') or file.get('extracted_text', '')
                    # 只计算有内容文件的token数
                    if file_content and file_content.strip():
                        file_tokens = self.estimate_tokens(file_content)
                        total_file_tokens += file_tokens
                        valid_file_count += 1
                    else:
                        logger.warning(f"Skipping empty file in token calculation: {file.get('file_name', '未命名文件')}")

                logger.info(f"Total tokens for {valid_file_count} valid files: {total_file_tokens} (out of {len(filtered_files)} total files)")

                # 如果总token数不超过50000，跳过文件预处理步骤
                if total_file_tokens <= 50000:
                    logger.info("Files token count doesn't exceed 50000, skipping file preprocessing step")
                    # 直接合并所有文件内容
                    files_content = []
                    for file in filtered_files:
                        file_name = file.get('file_name', '未命名文件')
                        # 优先使用file_content，兼容extracted_text
                        file_content = file.get('file_content') or file.get('extracted_text', '')
                        file_uuid = file.get('file_uuid', '')

                        # 只处理有内容的文件，跳过空内容文件
                        if file_content and file_content.strip():
                            files_content.append(f"文件UUID: {file_uuid}\n内容:\n{file_content}")
                            logger.info(f"Added file content: {file_name} (UUID: {file_uuid}) ({len(file_content)} chars)")
                        else:
                            logger.warning(f"Skipping file with empty content: {file_name} (UUID: {file_uuid})")

                    if files_content:
                        preprocessed_info = f"{patient_info}\n\n文件提取的患者信息:\n" + "\n\n".join(files_content)
                    else:
                        logger.info("No valid file content found, using only patient_info and messages")
                        preprocessed_info = patient_info
                else:
                    logger.info(f"Preprocessing {len(filtered_files)} files (total tokens: {total_file_tokens})")
                    
                    # 文件预处理步骤
                    preprocessed_info = patient_info
                    
                    # 准备文件预处理任务的输入
                    max_tokens_per_batch = 88000 # 每批次处理的最大token数 ，现在用qwen 128k 的模型，所以设置为75000
                    max_tokens_per_chunk = 88000  # 单个文件块的最大token数，现在用qwen 128k 的模型，所以设置为75000

                    # 遍历处理所有文件，收集所有批次
                    all_batches = []
                    current_batch = []
                    current_batch_tokens = 0

                    # 使用过滤后的文件列表
                    for file in filtered_files:
                        file_name = file.get('file_name', '未命名文件')
                        # 优先使用file_content，兼容extracted_text
                        file_content = file.get('file_content') or file.get('extracted_text', '')
                        file_uuid = file.get('file_uuid', '')

                        # 跳过空内容文件
                        if not file_content or not file_content.strip():
                            logger.warning(f"Skipping file with empty content during preprocessing: {file_name} (UUID: {file_uuid})")
                            continue
                            
                        file_tokens = self.estimate_tokens(file_content)
                        
                        logger.info(f"File '{file_name}' (UUID: {file_uuid}): {len(file_content)} chars, estimated {file_tokens} tokens")
                        
                        # 处理大文件 - 切分为多个块
                        if file_tokens > max_tokens_per_chunk:
                            logger.info(f"Splitting large file '{file_name}' ({file_tokens} tokens) into chunks")
                            
                            # 估计每个字符的平均token数
                            avg_tokens_per_char = file_tokens / len(file_content) if len(file_content) > 0 else 0.5
                            # 估算每个块的最大字符数
                            chars_per_chunk = int(max_tokens_per_chunk / avg_tokens_per_char) if avg_tokens_per_char > 0 else 20000
                            
                            # 计算需要的块数
                            num_chunks = (len(file_content) + chars_per_chunk - 1) // chars_per_chunk
                            
                            for chunk_idx in range(num_chunks):
                                start_pos = chunk_idx * chars_per_chunk
                                end_pos = min((chunk_idx + 1) * chars_per_chunk, len(file_content))
                                chunk_content = file_content[start_pos:end_pos]
                                chunk_tokens = self.estimate_tokens(chunk_content)
                                
                                logger.info(f"  Chunk {chunk_idx+1}/{num_chunks}: {len(chunk_content)} chars, estimated {chunk_tokens} tokens")
                                
                                # 检查当前批次是否会超出token限制
                                if current_batch_tokens + chunk_tokens > max_tokens_per_batch:
                                    # 添加当前批次到所有批次列表
                                    if current_batch:
                                        all_batches.append(list(current_batch))
                                    
                                    # 重置批次
                                    current_batch = []
                                    current_batch_tokens = 0
                                
                                # 添加文件块到当前批次
                                current_batch.append({
                                    "file_name": f"{file_name} (Part {chunk_idx+1}/{num_chunks})",
                                    "file_content": chunk_content,
                                    "file_uuid": file_uuid
                                })
                                current_batch_tokens += chunk_tokens
                        else:
                            # 处理标准大小文件
                            # 检查当前批次是否会超出token限制
                            if current_batch_tokens + file_tokens > max_tokens_per_batch:
                                # 添加当前批次到所有批次列表
                                if current_batch:
                                    all_batches.append(list(current_batch))
                                
                                # 重置批次
                                current_batch = []
                                current_batch_tokens = 0
                            
                            # 添加到当前批次
                            current_batch.append({
                                "file_name": file_name,
                                "file_content": file_content,
                                "file_uuid": file_uuid
                            })
                            current_batch_tokens += file_tokens
                    
                    # 添加最后一个批次
                    if current_batch:
                        all_batches.append(list(current_batch))
                    
                    logger.info(f"Prepared {len(all_batches)} batches for processing")
                    
                    # 使用并发处理批次
                    all_preprocessed_content = []
                    all_batch_inputs = []
                    
                    # 定义批次处理函数
                    def process_batch(batch):
                        batch_input = {
                            "files_batch": batch,
                            "patient_info": patient_info,
                            "current_date": current_date
                        }
                        all_batch_inputs.append(batch_input)  # 保存batch_input
                        self.preprocess_files_task().interpolate_inputs_and_add_conversation_history(batch_input)
                        return self.file_preprocessor().execute_task(self.preprocess_files_task())
                    
                    # 获取最大并发数
                    max_concurrent = min(self.max_concurrency, len(all_batches))
                    logger.info(f"Processing {len(all_batches)} batches with maximum {max_concurrent} concurrent workers")
                    
                    # 使用线程池执行并发处理
                    completed_batches = 0
                    with concurrent.futures.ThreadPoolExecutor(max_workers=max_concurrent) as executor:
                        # 提交所有批次处理任务
                        future_to_batch = {executor.submit(process_batch, batch): i for i, batch in enumerate(all_batches)}

                        # 收集所有结果
                        for future in concurrent.futures.as_completed(future_to_batch):
                            batch_idx = future_to_batch[future]
                            try:
                                result = future.result()
                                all_preprocessed_content.append(result)
                                completed_batches += 1
                                logger.info(f"Completed processing batch {batch_idx+1}/{len(all_batches)}")

                                # 发送文件批次处理进度（10-30%之间）
                                batch_progress = 10 + int(20 * completed_batches / len(all_batches))
                                yield {"type": "progress", "stage": "file_preprocessing", "message": f"正在处理文件批次 {completed_batches}/{len(all_batches)}", "progress": batch_progress}
                            except Exception as e:
                                logger.error(f"Error processing batch {batch_idx+1}: {str(e)}")
                    
                    # 合并所有预处理结果
                    if all_preprocessed_content:
                        # 保存预处理结果到本地文件
                        try:
                            # 确保目录存在
                            log_dir = "logs/patient_data_preprocessed"
                            os.makedirs(log_dir, exist_ok=True)
                            
                            # 创建带有时间戳的文件名
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            
                            # 保存预处理输出结果
                            output_filename = f"{log_dir}/patient_data_preprocessed_{timestamp}.json"
                            # 准备JSON数据
                            output_json_data = {
                                "timestamp": datetime.now().isoformat(),
                                "content_count": len(all_preprocessed_content),
                                "preprocessed_content": all_preprocessed_content
                            }
                            # 写入JSON文件
                            JsonUtils.safe_json_dump(output_json_data, output_filename)
                            
                            # 保存预处理输入数据
                            input_filename = f"{log_dir}/patient_data_input_{timestamp}.json"
                            # 准备JSON数据
                            input_json_data = {
                                "timestamp": datetime.now().isoformat(),
                                "batch_count": len(all_batch_inputs),
                                "batch_inputs": all_batch_inputs
                            }
                            # 写入JSON文件
                            JsonUtils.safe_json_dump(input_json_data, input_filename)
                            
                            logger.info(f"Preprocessed content saved to {output_filename}")
                            logger.info(f"Batch input data saved to {input_filename}")
                        except Exception as e:
                            logger.error(f"Failed to save preprocessed content: {e}")
                        
                        preprocessed_info = f"{patient_info}\n\n文件提取的患者信息:\n" + "\n\n".join(all_preprocessed_content)
                        preprocessed_tokens = self.estimate_tokens(preprocessed_info)
                        logger.info(f"Files preprocessing completed, combined result: {len(preprocessed_info)} chars, estimated {preprocessed_tokens} tokens")

            # 记录文件预处理耗时
            file_preprocessing_duration = time.time() - file_preprocessing_start_time
            logger.info("-" * 80)
            logger.info(f"【阶段1】文件预处理完成，耗时: {file_preprocessing_duration:.2f} 秒 ({file_preprocessing_duration/60:.2f} 分钟)")
            logger.info("-" * 80)

            # 发送文件预处理完成进度
            yield {"type": "progress", "stage": "file_preprocessing_completed", "message": "文件预处理完成", "progress": 30}

            # 使用预处理后的患者信息执行原始任务
            # ========== 阶段2: 疾病配置识别 ==========
            disease_config_start_time = time.time()
            logger.info("-" * 80)
            logger.info("【阶段2】开始疾病配置识别")
            logger.info("-" * 80)

            # 发送进度更新
            yield {"type": "progress", "stage": "disease_config", "message": "正在识别疾病配置", "progress": 35}

            disease_config_inputs = {
                "patient_info": preprocessed_info
            }
            self.get_disease_config_task().interpolate_inputs_and_add_conversation_history(disease_config_inputs)
            disease_config_result = self.disease_config_agent().execute_task(self.get_disease_config_task())

            # 记录疾病配置识别耗时
            disease_config_duration = time.time() - disease_config_start_time
            logger.info("-" * 80)
            logger.info(f"【阶段2】疾病配置识别完成，耗时: {disease_config_duration:.2f} 秒 ({disease_config_duration/60:.2f} 分钟)")
            logger.info("-" * 80)

            # 解析疾病配置结果
            disease_config_data = JsonUtils.safe_parse_json(disease_config_result, debug_prefix="Disease config identification")
            if disease_config_data:
                logger.info(f"Identified diseases config: {disease_config_data.get('status', 'unknown')}")
                if disease_config_data.get('configs'):
                    logger.info(f"Found {len(disease_config_data['configs'])} disease configurations")
            else:
                logger.warning("Failed to parse disease config result, will proceed without specific disease config")
                disease_config_data = {"status": "error", "configs": []}

            # 发送疾病配置识别完成进度
            yield {"type": "progress", "stage": "disease_config_completed", "message": "疾病配置识别完成", "progress": 45}

            # ========== 阶段3: 患者数据处理（时间轴生成） ==========
            patient_data_processing_start_time = time.time()
            logger.info("-" * 80)
            logger.info("【阶段3】开始患者数据处理（时间轴生成）")
            logger.info("-" * 80)

            # 发送进度更新
            yield {"type": "progress", "stage": "timeline_generation", "message": "正在生成患者时间轴", "progress": 50}

            # 步骤2: 执行患者数据处理任务，将疾病配置作为上下文传递
            inputs = {
                "patient_info": preprocessed_info,
                "patient_timeline": patient_timeline,
                "current_date": current_date,
                "existing_timeline": existing_timeline if existing_timeline else [],
                "disease_config": disease_config_data  # 传递疾病配置
            }
            self.process_patient_data_task().interpolate_inputs_and_add_conversation_history(inputs)

            # 执行任务
            patient_data_result = self.patient_data_processor().execute_task(self.process_patient_data_task())

            # 记录患者数据处理耗时
            patient_data_processing_duration = time.time() - patient_data_processing_start_time
            logger.info("-" * 80)
            logger.info(f"【阶段3】患者数据处理完成，耗时: {patient_data_processing_duration:.2f} 秒 ({patient_data_processing_duration/60:.2f} 分钟)")
            logger.info("-" * 80)

            # 解析结果，确保其为有效的JSON
            parsed_result = JsonUtils.safe_parse_json(patient_data_result, debug_prefix="Patient data processing")

            # 额外的Unicode清理步骤，确保没有遗漏的Unicode编码
            if parsed_result:
                parsed_result = JsonUtils._decode_unicode_in_dict(parsed_result)

            # 发送时间轴生成完成进度
            yield {"type": "progress", "stage": "timeline_generation_completed", "message": "患者时间轴生成完成", "progress": 65}

            # ========== 阶段4: 患者旅程提取 ==========
            patient_journey_start_time = time.time()
            logger.info("-" * 80)
            logger.info("【阶段4】开始患者旅程提取")
            logger.info("-" * 80)

            # 发送进度更新
            yield {"type": "progress", "stage": "patient_journey", "message": "正在提取患者旅程数据", "progress": 70}

            # 执行"患者时间旅程"任务
            special_parsed_result = None
            try:
                core_inputs = {
                    "current_date": current_date,
                    "patient_content": preprocessed_info,
                    "full_structure_data": parsed_result if parsed_result else {},
                    "existing_patient_journey": existing_patient_journey if existing_patient_journey else {},
                    "disease_config": disease_config_data  # 传递疾病配置
                }
                self.extract_core_points_task().interpolate_inputs_and_add_conversation_history(core_inputs)
                special_result = self.core_points_extractor().execute_task(self.extract_core_points_task())
                special_parsed_result = JsonUtils.safe_parse_json(special_result, debug_prefix="Patient journey extraction")
                
                # 额外的Unicode清理步骤和结构验证
                if special_parsed_result:
                    special_parsed_result = JsonUtils._decode_unicode_in_dict(special_parsed_result)
                    # 验证是否包含预期的字段
                    if isinstance(special_parsed_result, dict):
                        expected_fields = ["timeline_journey", "indicator_series"]
                        missing_fields = [field for field in expected_fields if field not in special_parsed_result]
                        if missing_fields:
                            logger.warning(f"患者时间旅程JSON缺少字段: {missing_fields}")
                        else:
                            logger.info(f"成功提取患者时间旅程，包含{len(special_parsed_result.get('timeline_journey', []))}个时间节点和{len(special_parsed_result.get('indicator_series', []))}个指标序列")
                    else:
                        logger.warning("患者时间旅程解析结果不是字典格式")
                else:
                    logger.warning("患者时间旅程解析结果为空")
            except Exception as e:
                logger.error(f"Error in patient journey extraction: {e}")

            # 记录患者旅程提取耗时
            patient_journey_duration = time.time() - patient_journey_start_time
            logger.info("-" * 80)
            logger.info(f"【阶段4】患者旅程提取完成，耗时: {patient_journey_duration:.2f} 秒 ({patient_journey_duration/60:.2f} 分钟)")
            logger.info("-" * 80)

            # 发送患者旅程提取完成进度
            yield {"type": "progress", "stage": "patient_journey_completed", "message": "患者旅程数据提取完成", "progress": 80}

            # ========== 阶段5: MDT报告生成 ==========
            mdt_report_start_time = time.time()
            logger.info("-" * 80)
            logger.info("【阶段5】开始MDT报告生成")
            logger.info("-" * 80)

            # 发送进度更新
            yield {"type": "progress", "stage": "mdt_report", "message": "正在生成MDT报告", "progress": 85}

            # 执行MDT报告生成任务
            mdt_report_result = None
            try:
                mdt_inputs = {
                    "current_date": current_date,
                    "patient_content": preprocessed_info,
                    "patient_structured_data": parsed_result if parsed_result else {},
                    "existing_mdt_report": existing_mdt_report if existing_mdt_report else {},
                    "disease_config": disease_config_data  # 传递疾病配置
                }
                self.generate_mdt_report_task().interpolate_inputs_and_add_conversation_history(mdt_inputs)
                mdt_result = self.mdt_report_generator().execute_task(self.generate_mdt_report_task())
                mdt_parsed_result = JsonUtils.safe_parse_json(mdt_result, debug_prefix="MDT report generation")
                
                # 🚨 修复：正确提取mdt_simple_report字段
                if mdt_parsed_result:
                    mdt_parsed_result = JsonUtils._decode_unicode_in_dict(mdt_parsed_result)
                    # 检查是否包含mdt_simple_report字段
                    if isinstance(mdt_parsed_result, dict) and "mdt_simple_report" in mdt_parsed_result:
                        mdt_report_result = mdt_parsed_result["mdt_simple_report"]
                        logger.info(f"成功提取MDT报告，包含{len(mdt_report_result)}个条目")
                    else:
                        # 如果没有mdt_simple_report字段，使用整个解析结果
                        logger.warning("MDT报告JSON中未找到mdt_simple_report字段，使用整个解析结果")
                        mdt_report_result = mdt_parsed_result
                else:
                    logger.warning("MDT报告解析结果为空")
            except Exception as e:
                logger.error(f"Error in MDT report generation: {e}")

            # 记录MDT报告生成耗时
            mdt_report_duration = time.time() - mdt_report_start_time
            logger.info("-" * 80)
            logger.info(f"【阶段5】MDT报告生成完成，耗时: {mdt_report_duration:.2f} 秒 ({mdt_report_duration/60:.2f} 分钟)")
            logger.info("-" * 80)

            # 发送MDT报告生成完成进度
            yield {"type": "progress", "stage": "mdt_report_completed", "message": "MDT报告生成完成", "progress": 90}

            if parsed_result:
                timeline_count = len(parsed_result.get('timeline', []))
                logger.info(f"Successfully processed patient data with {timeline_count} timeline entries")
            else:
                logger.warning("Failed to parse patient data processing result")
            
            # 准备返回的结果
            result_data = {
                "patient_content": preprocessed_info,
                "full_structure_data": parsed_result if parsed_result else {"error": "Failed to parse patient data", "raw": patient_data_result},
                "patient_journey": special_parsed_result if special_parsed_result else {},
                "mdt_simple_report": mdt_report_result if mdt_report_result else {}
            }

            # 🚨 简化：移除复杂的验证逻辑，直接保存处理结果

            # ========== 生成患者时间旅程图片并上传到七牛云 ==========
            # 🚨 临时禁用：因为Playwright加载超时问题
            if False and special_parsed_result and agent_session_id:
                try:
                    logger.info("开始生成患者时间旅程图片...")

                    # 从patient_journey中提取数据
                    journey_list = special_parsed_result if isinstance(special_parsed_result, list) else []

                    if journey_list:
                        # 生成图片文件名和路径
                        image_uuid = str(uuid_lib.uuid4())
                        output_dir = Path("output/files_extract") / agent_session_id / "patient_journey_images"
                        output_dir.mkdir(parents=True, exist_ok=True)

                        image_filename = f"patient_journey_{image_uuid}.png"
                        image_path = output_dir / image_filename

                        # 提取患者姓名（如果有的话）
                        patient_name = "患者"
                        if parsed_result and isinstance(parsed_result, dict):
                            patient_name = parsed_result.get("patient_name", "患者")

                        # 生成图片
                        success = generate_patient_journey_image_sync(
                            patient_journey_data=journey_list,
                            output_path=str(image_path),
                            patient_name=patient_name
                        )

                        if success and image_path.exists():
                            logger.info(f"患者时间旅程图片生成成功: {image_path}")

                            # 上传到七牛云
                            try:
                                qiniu_service = QiniuUploadService()
                                qiniu_key = f"patient_journey/{image_uuid}.png"

                                upload_success, cloud_url, error = qiniu_service.upload_file(
                                    str(image_path),
                                    qiniu_key
                                )

                                if upload_success:
                                    logger.info(f"患者时间旅程图片已上传到七牛云: {cloud_url}")

                                    # 将图片URL添加到patient_journey JSON中
                                    if isinstance(result_data["patient_journey"], dict):
                                        result_data["patient_journey"]["image_url"] = cloud_url
                                    elif isinstance(result_data["patient_journey"], list):
                                        # 如果是列表，转换为字典结构
                                        result_data["patient_journey"] = {
                                            "timeline_journey": result_data["patient_journey"],
                                            "image_url": cloud_url
                                        }
                                else:
                                    logger.error(f"上传患者时间旅程图片到七牛云失败: {error}")
                            except Exception as upload_error:
                                logger.error(f"上传患者时间旅程图片到七牛云时出错: {upload_error}")
                        else:
                            logger.warning("患者时间旅程图片生成失败")
                    else:
                        logger.info("患者旅程数据为空，跳过图片生成")

                except Exception as e:
                    logger.error(f"生成或上传患者时间旅程图片时出错: {e}")
                    import traceback
                    logger.error(traceback.format_exc())

            # ========== 生成核心指标趋势图片并上传到七牛云 ==========
            # 🚨 临时禁用：因为Playwright加载超时问题
            indicator_chart_image_url = None
            if False and special_parsed_result and agent_session_id:
                try:
                    # 从patient_journey中提取indicator_series数据
                    indicator_series = None
                    if isinstance(special_parsed_result, dict) and 'indicator_series' in special_parsed_result:
                        indicator_series = special_parsed_result.get('indicator_series')

                    if indicator_series and isinstance(indicator_series, list) and indicator_series:
                        logger.info(f"开始生成核心指标趋势图片，包含 {len(indicator_series)} 个指标...")

                        # 生成图片文件名和路径
                        image_uuid = str(uuid_lib.uuid4())
                        output_dir = Path("output/files_extract") / agent_session_id / "indicator_chart_images"
                        output_dir.mkdir(parents=True, exist_ok=True)

                        image_filename = f"indicator_chart_{image_uuid}.png"
                        image_path = output_dir / image_filename

                        # 提取患者姓名
                        patient_name = "患者"
                        if parsed_result and isinstance(parsed_result, dict):
                            patient_name = parsed_result.get("patient_name", "患者")

                        # 生成图片
                        success = generate_indicator_chart_image_sync(
                            indicator_series_data=indicator_series,
                            output_path=str(image_path),
                            patient_name=patient_name
                        )

                        if success and image_path.exists():
                            logger.info(f"核心指标趋势图片生成成功: {image_path}")

                            # 上传到七牛云
                            try:
                                qiniu_service = QiniuUploadService()
                                qiniu_key = f"indicator_chart/{image_uuid}.png"

                                upload_success, cloud_url, error = qiniu_service.upload_file(
                                    str(image_path),
                                    qiniu_key
                                )

                                if upload_success:
                                    indicator_chart_image_url = cloud_url
                                    # 将URL添加到patient_journey JSON中
                                    if isinstance(special_parsed_result, dict):
                                        special_parsed_result["indicator_chart_image_url"] = cloud_url
                                        result_data["patient_journey"] = special_parsed_result
                                    logger.info(f"核心指标趋势图片已上传到七牛云: {cloud_url}")
                                else:
                                    logger.error(f"上传核心指标趋势图片到七牛云失败: {error}")
                            except Exception as upload_error:
                                logger.error(f"上传核心指标趋势图片到七牛云时出错: {upload_error}")
                        else:
                            logger.warning("核心指标趋势图片生成失败")
                    else:
                        logger.info("指标序列数据为空或格式不正确，跳过图片生成")

                except Exception as e:
                    logger.error(f"生成或上传核心指标趋势图片时出错: {e}")
                    import traceback
                    logger.error(traceback.format_exc())

            # 保存患者数据到输出目录（与intent_determine_crew相同的session目录）
            if agent_session_id:
                output_file_path = self._save_patient_data_to_output(
                    agent_session_id,
                    preprocessed_info,
                    result_data["full_structure_data"],
                    result_data.get("patient_journey"),
                    result_data.get("mdt_simple_report")
                )
                if output_file_path:
                    logger.info(f"患者数据已保存到输出目录: {output_file_path}")
                else:
                    logger.warning("保存患者数据到输出目录失败")
            else:
                logger.warning("No agent_session_id provided, skipping patient data save")

            # ========== 总体耗时统计 ==========
            overall_duration = time.time() - overall_start_time
            logger.info("=" * 80)
            logger.info("患者数据处理流程完成 - 耗时统计")
            logger.info("=" * 80)
            logger.info(f"【阶段1】文件预处理:        {file_preprocessing_duration:.2f} 秒 ({file_preprocessing_duration/60:.2f} 分钟) - {(file_preprocessing_duration/overall_duration*100):.1f}%")
            logger.info(f"【阶段2】疾病配置识别:      {disease_config_duration:.2f} 秒 ({disease_config_duration/60:.2f} 分钟) - {(disease_config_duration/overall_duration*100):.1f}%")
            logger.info(f"【阶段3】患者数据处理:      {patient_data_processing_duration:.2f} 秒 ({patient_data_processing_duration/60:.2f} 分钟) - {(patient_data_processing_duration/overall_duration*100):.1f}%")
            logger.info(f"【阶段4】患者旅程提取:      {patient_journey_duration:.2f} 秒 ({patient_journey_duration/60:.2f} 分钟) - {(patient_journey_duration/overall_duration*100):.1f}%")
            logger.info(f"【阶段5】MDT报告生成:       {mdt_report_duration:.2f} 秒 ({mdt_report_duration/60:.2f} 分钟) - {(mdt_report_duration/overall_duration*100):.1f}%")
            logger.info("-" * 80)
            logger.info(f"【总计】整体处理时间:       {overall_duration:.2f} 秒 ({overall_duration/60:.2f} 分钟)")
            logger.info("=" * 80)

            # 发送最终处理完成进度
            yield {"type": "progress", "stage": "finalizing", "message": "处理完成，正在整理结果", "progress": 95}

            # yield 最终结果
            yield {"type": "result", "data": result_data}

        except Exception as e:
            logger.error(f"Error in patient data processing: {e}")
            yield {"type": "result", "data": {"error": str(e)}} 

