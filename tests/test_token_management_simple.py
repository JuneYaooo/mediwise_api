"""
简化版测试脚本 - 测试Token管理和数据压缩功能（不依赖外部库）

测试场景：
1. Token估算准确性
2. 数据压缩功能
3. 输入限制检查
"""

import os
import sys
import json
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 设置环境变量（模拟.env文件）
os.environ['MODEL_MAX_INPUT_TOKENS'] = '1000000'
os.environ['MODEL_MAX_OUTPUT_TOKENS'] = '65535'
os.environ['TOKEN_SAFE_INPUT_RATIO'] = '0.7'
os.environ['TOKEN_SAFE_OUTPUT_RATIO'] = '0.9'
os.environ['ENABLE_AUTO_COMPRESSION'] = 'true'
os.environ['COMPRESSION_STRATEGY'] = 'smart'
os.environ['MAX_RAW_FILES_COUNT'] = '50'
os.environ['MAX_TIMELINE_RECORDS'] = '100'
os.environ['EXTRACTED_TEXT_MAX_LENGTH'] = '200'


class SimpleLogger:
    """简单的日志记录器"""
    def info(self, msg):
        print(f"[INFO] {msg}")

    def warning(self, msg):
        print(f"[WARNING] {msg}")

    def error(self, msg, exc_info=False):
        print(f"[ERROR] {msg}")


# 创建简单的logger
logger = SimpleLogger()


def create_test_patient_data(size='small'):
    """创建测试患者数据"""
    timeline_counts = {
        'small': 10,
        'medium': 50,
        'large': 200,
    }

    count = timeline_counts.get(size, 10)

    # 生成时间轴数据
    timeline = []
    for i in range(count):
        record = {
            'date': f'2024-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}',
            'event_type': ['检查', '治疗', '复诊', '住院'][i % 4],
            'description': f'这是第{i+1}次就诊记录，患者进行了常规检查和治疗。' * 5,
            'doctor': f'医生{i % 10}',
            'result': f'检查结果正常，继续观察治疗。' * 3
        }
        timeline.append(record)

    # 生成原始文件数据
    raw_files = []
    file_count = count // 2
    for i in range(file_count):
        file_item = {
            'file_uuid': f'uuid-{i:04d}',
            'filename': f'检查报告_{i+1}.pdf',
            'file_type': ['检验报告', '影像报告', '病历'][i % 3],
            'exam_date': f'2024-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}',
            'has_medical_image': i % 3 == 0,
            'extracted_text': f'这是第{i+1}个文件的提取文本内容。' * 20
        }
        raw_files.append(file_item)

    return {
        'patient_name': '张三',
        'patient_info': {
            'basic': {'name': '张三', 'age': 45, 'gender': '男'}
        },
        'patient_timeline': timeline,
        'raw_files_data': raw_files
    }


def test_token_estimation():
    """测试1: Token估算"""
    print("\n" + "=" * 80)
    print("测试1: Token估算")
    print("=" * 80)

    # 导入TokenManager（延迟导入，避免dotenv问题）
    from src.utils.token_manager import TokenManager
    token_manager = TokenManager(logger=logger)

    test_texts = {
        '短文本': '这是一个简短的测试文本。',
        '中文本': '这是一个中等长度的测试文本。' * 50,
        '长文本': '这是一个很长的测试文本。' * 500,
    }

    for name, text in test_texts.items():
        tokens = token_manager.estimate_tokens(text)
        logger.info(f"{name}: 字符数={len(text)}, 估算tokens={tokens}, 比例={len(text)/tokens:.2f}字符/token")

    print("✅ Token估算测试完成\n")


def test_data_compression():
    """测试2: 数据压缩"""
    print("\n" + "=" * 80)
    print("测试2: 数据压缩")
    print("=" * 80)

    from src.utils.token_manager import TokenManager
    from src.utils.data_compressor import PatientDataCompressor

    token_manager = TokenManager(logger=logger)
    data_compressor = PatientDataCompressor(logger=logger, token_manager=token_manager)

    for size in ['small', 'medium', 'large']:
        print(f"\n--- 测试 {size} 数据集 ---")

        patient_data = create_test_patient_data(size=size)
        original_tokens = token_manager.estimate_tokens(patient_data)
        logger.info(f"原始数据: tokens={original_tokens}")

        # 压缩到50%
        target_tokens = original_tokens // 2
        compressed_data = data_compressor.compress_data(patient_data, target_tokens)

        compressed_tokens = token_manager.estimate_tokens(compressed_data)
        compression_ratio = compressed_tokens / original_tokens if original_tokens > 0 else 1.0

        logger.info(f"压缩后数据: tokens={compressed_tokens}, 压缩比例={compression_ratio:.1%}")

        # 验证关键字段
        assert 'patient_name' in compressed_data, "关键字段patient_name丢失"
        assert 'patient_info' in compressed_data, "关键字段patient_info丢失"
        logger.info("✅ 关键字段验证通过")

    print("\n✅ 数据压缩测试完成\n")


def test_input_limit_check():
    """测试3: 输入限制检查"""
    print("\n" + "=" * 80)
    print("测试3: 输入限制检查")
    print("=" * 80)

    from src.utils.token_manager import TokenManager
    token_manager = TokenManager(logger=logger)

    for size in ['small', 'medium', 'large']:
        print(f"\n--- 测试 {size} 数据集 ---")

        patient_data = create_test_patient_data(size=size)
        check_result = token_manager.check_input_limit(patient_data, 'gemini-3-flash-preview')

        logger.info(f"检查结果:")
        logger.info(f"  - 总tokens: {check_result['total_tokens']}")
        logger.info(f"  - 限制: {check_result['limit']}")
        logger.info(f"  - 安全限制: {check_result['safe_limit']}")
        logger.info(f"  - 在限制内: {check_result['within_limit']}")
        logger.info(f"  - 需要压缩: {check_result['compression_needed']}")
        logger.info(f"  - 使用率: {check_result['usage_ratio']:.1%}")

    print("\n✅ 输入限制检查测试完成\n")


def test_timeline_compression():
    """测试4: 时间轴压缩"""
    print("\n" + "=" * 80)
    print("测试4: 时间轴压缩")
    print("=" * 80)

    from src.utils.token_manager import TokenManager
    from src.utils.data_compressor import PatientDataCompressor

    token_manager = TokenManager(logger=logger)
    data_compressor = PatientDataCompressor(logger=logger, token_manager=token_manager)

    patient_data = create_test_patient_data(size='large')
    timeline = patient_data['patient_timeline']

    logger.info(f"原始时间轴记录数: {len(timeline)}")

    target_tokens = 10000
    compressed_timeline = data_compressor.compress_timeline(timeline, target_tokens)

    logger.info(f"压缩后时间轴记录数: {len(compressed_timeline)}")

    if len(compressed_timeline) > 1:
        first_date = compressed_timeline[0].get('date', '')
        last_date = compressed_timeline[-1].get('date', '')
        logger.info(f"日期范围: {last_date} 到 {first_date}")

    print("✅ 时间轴压缩测试完成\n")


def test_raw_files_compression():
    """测试5: 原始文件压缩"""
    print("\n" + "=" * 80)
    print("测试5: 原始文件压缩")
    print("=" * 80)

    from src.utils.token_manager import TokenManager
    from src.utils.data_compressor import PatientDataCompressor

    token_manager = TokenManager(logger=logger)
    data_compressor = PatientDataCompressor(logger=logger, token_manager=token_manager)

    patient_data = create_test_patient_data(size='large')
    raw_files = patient_data['raw_files_data']

    logger.info(f"原始文件数: {len(raw_files)}")

    medical_image_count = sum(1 for f in raw_files if f.get('has_medical_image', False))
    logger.info(f"医学影像文件数: {medical_image_count}")

    target_tokens = 5000
    compressed_files = data_compressor.compress_raw_files(raw_files, target_tokens)

    logger.info(f"压缩后文件数: {len(compressed_files)}")

    compressed_medical_count = sum(1 for f in compressed_files if f.get('has_medical_image', False))
    logger.info(f"压缩后医学影像文件数: {compressed_medical_count}")

    if medical_image_count > 0:
        retention_ratio = compressed_medical_count / medical_image_count
        logger.info(f"医学影像保留率: {retention_ratio:.1%}")

    print("✅ 原始文件压缩测试完成\n")


def run_all_tests():
    """运行所有测试"""
    print("\n🚀 开始运行Token管理和数据压缩功能测试")
    print("=" * 80)

    try:
        test_token_estimation()
        test_data_compression()
        test_input_limit_check()
        test_timeline_compression()
        test_raw_files_compression()

        print("=" * 80)
        print("🎉 所有测试完成！")
        print("=" * 80)

    except Exception as e:
        logger.error(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == '__main__':
    run_all_tests()
