"""
测试Token管理和数据压缩功能

测试场景：
1. Token估算准确性
2. 数据压缩功能
3. 分块处理功能
4. 输出完整性验证
"""

import os
import sys
import json
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

from src.utils.token_manager import TokenManager
from src.utils.data_compressor import PatientDataCompressor
from src.utils.chunked_processor import ChunkedPPTProcessor
from src.utils.output_completeness_guard import OutputCompletenessGuard
from src.utils.logger import BeijingLogger

# 初始化logger
logger = BeijingLogger().get_logger()


def create_test_patient_data(size='small'):
    """创建测试患者数据

    Args:
        size: 数据大小 ('small', 'medium', 'large', 'xlarge')

    Returns:
        dict: 测试患者数据
    """
    # 基础数据
    base_data = {
        'patient_name': '张三',
        'patient_info': {
            'basic': {
                'name': '张三',
                'age': 45,
                'gender': '男',
                'id': '123456789012345678'
            },
            'contact': {
                'phone': '13800138000',
                'address': '北京市朝阳区'
            }
        },
        'diagnoses': [
            {
                'date': '2024-01-15',
                'diagnosis': '高血压',
                'icd_code': 'I10',
                'doctor': '李医生'
            },
            {
                'date': '2024-02-20',
                'diagnosis': '糖尿病',
                'icd_code': 'E11',
                'doctor': '王医生'
            }
        ],
        'current_medications': [
            {
                'name': '降压药',
                'dosage': '10mg',
                'frequency': '每日一次'
            }
        ]
    }

    # 根据size生成不同数量的时间轴记录
    timeline_counts = {
        'small': 10,
        'medium': 50,
        'large': 200,
        'xlarge': 500
    }

    count = timeline_counts.get(size, 10)

    # 生成时间轴数据
    timeline = []
    for i in range(count):
        record = {
            'date': f'2024-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}',
            'event_type': ['检查', '治疗', '复诊', '住院'][i % 4],
            'description': f'这是第{i+1}次就诊记录，患者进行了常规检查和治疗。' * 5,  # 重复5次增加长度
            'doctor': f'医生{i % 10}',
            'department': ['内科', '外科', '心内科', '神经科'][i % 4],
            'result': f'检查结果正常，继续观察治疗。患者状态良好。' * 3
        }
        timeline.append(record)

    base_data['patient_timeline'] = timeline

    # 生成原始文件数据
    raw_files = []
    file_count = count // 2  # 文件数量是时间轴的一半
    for i in range(file_count):
        file_item = {
            'file_uuid': f'uuid-{i:04d}',
            'filename': f'检查报告_{i+1}.pdf',
            'file_type': ['检验报告', '影像报告', '病历'][i % 3],
            'exam_date': f'2024-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}',
            'has_medical_image': i % 3 == 0,  # 每3个文件有1个医学影像
            'cropped_image_available': i % 3 == 0,
            'cropped_image_url': f'https://example.com/image_{i}.jpg' if i % 3 == 0 else None,
            'cloud_storage_url': f'https://example.com/file_{i}.pdf',
            'extracted_text': f'这是第{i+1}个文件的提取文本内容。' * 20  # 重复20次
        }
        raw_files.append(file_item)

    base_data['raw_files_data'] = raw_files

    return base_data


def test_token_estimation():
    """测试1: Token估算"""
    logger.info("=" * 80)
    logger.info("测试1: Token估算")
    logger.info("=" * 80)

    token_manager = TokenManager(logger=logger)

    # 测试不同大小的文本
    test_texts = {
        '短文本': '这是一个简短的测试文本。',
        '中文本': '这是一个中等长度的测试文本。' * 50,
        '长文本': '这是一个很长的测试文本。' * 500,
        '混合文本': 'This is a mixed text with 中文 and English. ' * 100
    }

    for name, text in test_texts.items():
        tokens = token_manager.estimate_tokens(text)
        logger.info(f"{name}: 字符数={len(text)}, 估算tokens={tokens}, 比例={len(text)/tokens:.2f}字符/token")

    logger.info("✅ Token估算测试完成\n")


def test_data_compression():
    """测试2: 数据压缩"""
    logger.info("=" * 80)
    logger.info("测试2: 数据压缩")
    logger.info("=" * 80)

    token_manager = TokenManager(logger=logger)
    data_compressor = PatientDataCompressor(logger=logger, token_manager=token_manager)

    # 测试不同大小的数据
    for size in ['small', 'medium', 'large']:
        logger.info(f"\n--- 测试 {size} 数据集 ---")

        # 创建测试数据
        patient_data = create_test_patient_data(size=size)

        # 估算原始token数
        original_tokens = token_manager.estimate_tokens(patient_data)
        logger.info(f"原始数据: tokens={original_tokens}")

        # 压缩到50%
        target_tokens = original_tokens // 2
        compressed_data = data_compressor.compress_data(patient_data, target_tokens)

        # 估算压缩后token数
        compressed_tokens = token_manager.estimate_tokens(compressed_data)
        compression_ratio = compressed_tokens / original_tokens if original_tokens > 0 else 1.0

        logger.info(f"压缩后数据: tokens={compressed_tokens}, 压缩比例={compression_ratio:.1%}")

        # 验证关键字段是否保留
        assert 'patient_name' in compressed_data, "关键字段patient_name丢失"
        assert 'patient_info' in compressed_data, "关键字段patient_info丢失"
        logger.info("✅ 关键字段验证通过")

    logger.info("\n✅ 数据压缩测试完成\n")


def test_input_limit_check():
    """测试3: 输入限制检查"""
    logger.info("=" * 80)
    logger.info("测试3: 输入限制检查")
    logger.info("=" * 80)

    token_manager = TokenManager(logger=logger)

    # 测试不同大小的数据
    for size in ['small', 'medium', 'large', 'xlarge']:
        logger.info(f"\n--- 测试 {size} 数据集 ---")

        patient_data = create_test_patient_data(size=size)

        # 检查输入限制
        check_result = token_manager.check_input_limit(patient_data, 'gemini-3-flash-preview')

        logger.info(f"检查结果:")
        logger.info(f"  - 总tokens: {check_result['total_tokens']}")
        logger.info(f"  - 限制: {check_result['limit']}")
        logger.info(f"  - 安全限制: {check_result['safe_limit']}")
        logger.info(f"  - 在限制内: {check_result['within_limit']}")
        logger.info(f"  - 需要压缩: {check_result['compression_needed']}")
        logger.info(f"  - 使用率: {check_result['usage_ratio']:.1%}")

    logger.info("\n✅ 输入限制检查测试完成\n")


def test_timeline_compression():
    """测试4: 时间轴压缩"""
    logger.info("=" * 80)
    logger.info("测试4: 时间轴压缩")
    logger.info("=" * 80)

    token_manager = TokenManager(logger=logger)
    data_compressor = PatientDataCompressor(logger=logger, token_manager=token_manager)

    # 创建大数据集
    patient_data = create_test_patient_data(size='large')
    timeline = patient_data['patient_timeline']

    logger.info(f"原始时间轴记录数: {len(timeline)}")

    # 压缩到50条记录
    target_tokens = 10000  # 目标token数
    compressed_timeline = data_compressor.compress_timeline(timeline, target_tokens)

    logger.info(f"压缩后时间轴记录数: {len(compressed_timeline)}")

    # 验证是否按日期排序（最新的在前）
    if len(compressed_timeline) > 1:
        first_date = compressed_timeline[0].get('date', '')
        last_date = compressed_timeline[-1].get('date', '')
        logger.info(f"日期范围: {last_date} 到 {first_date}")

    logger.info("✅ 时间轴压缩测试完成\n")


def test_raw_files_compression():
    """测试5: 原始文件压缩"""
    logger.info("=" * 80)
    logger.info("测试5: 原始文件压缩")
    logger.info("=" * 80)

    token_manager = TokenManager(logger=logger)
    data_compressor = PatientDataCompressor(logger=logger, token_manager=token_manager)

    # 创建大数据集
    patient_data = create_test_patient_data(size='large')
    raw_files = patient_data['raw_files_data']

    logger.info(f"原始文件数: {len(raw_files)}")

    # 统计医学影像文件数
    medical_image_count = sum(1 for f in raw_files if f.get('has_medical_image', False))
    logger.info(f"医学影像文件数: {medical_image_count}")

    # 压缩到30个文件
    target_tokens = 5000
    compressed_files = data_compressor.compress_raw_files(raw_files, target_tokens)

    logger.info(f"压缩后文件数: {len(compressed_files)}")

    # 统计压缩后的医学影像文件数
    compressed_medical_count = sum(1 for f in compressed_files if f.get('has_medical_image', False))
    logger.info(f"压缩后医学影像文件数: {compressed_medical_count}")

    # 验证优先保留医学影像
    if medical_image_count > 0:
        retention_ratio = compressed_medical_count / medical_image_count
        logger.info(f"医学影像保留率: {retention_ratio:.1%}")

    logger.info("✅ 原始文件压缩测试完成\n")


def test_output_completeness():
    """测试6: 输出完整性验证"""
    logger.info("=" * 80)
    logger.info("测试6: 输出完整性验证")
    logger.info("=" * 80)

    output_guard = OutputCompletenessGuard(logger=logger)

    # 测试完整的PPT数据
    complete_ppt_data = {
        'pptTemplate2Vm': {
            'title': '患者病历报告',
            'patient': {
                'name': '张三',
                'age': 45
            },
            'diag': {
                'diagnosis': '高血压',
                'date': '2024-01-15'
            },
            'treatments': [],
            'examinations': []
        }
    }

    result = output_guard.validate_ppt_data(complete_ppt_data)
    logger.info(f"完整数据验证结果: is_complete={result['is_complete']}")

    # 测试不完整的PPT数据
    incomplete_ppt_data = {
        'pptTemplate2Vm': {
            'title': '患者病历报告'
            # 缺少 patient 和 diag 字段
        }
    }

    result = output_guard.validate_ppt_data(incomplete_ppt_data)
    logger.info(f"不完整数据验证结果: is_complete={result['is_complete']}")
    logger.info(f"缺失字段: {result['missing_required_fields']}")
    logger.info(f"建议: {result['suggestions']}")

    logger.info("✅ 输出完整性验证测试完成\n")


def run_all_tests():
    """运行所有测试"""
    logger.info("🚀 开始运行Token管理和数据压缩功能测试")
    logger.info("=" * 80)

    try:
        test_token_estimation()
        test_data_compression()
        test_input_limit_check()
        test_timeline_compression()
        test_raw_files_compression()
        test_output_completeness()

        logger.info("=" * 80)
        logger.info("🎉 所有测试完成！")
        logger.info("=" * 80)

    except Exception as e:
        logger.error(f"❌ 测试失败: {e}", exc_info=True)
        raise


if __name__ == '__main__':
    run_all_tests()
