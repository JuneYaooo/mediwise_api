"""
Token管理和数据压缩使用示例

演示如何使用Token管理和数据压缩功能
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 设置环境变量
os.environ['MODEL_MAX_INPUT_TOKENS'] = '1000000'
os.environ['MODEL_MAX_OUTPUT_TOKENS'] = '65535'
os.environ['TOKEN_SAFE_INPUT_RATIO'] = '0.7'
os.environ['ENABLE_AUTO_COMPRESSION'] = 'true'
os.environ['COMPRESSION_STRATEGY'] = 'smart'

from src.utils.token_manager import TokenManager
from src.utils.data_compressor import PatientDataCompressor


class SimpleLogger:
    def info(self, msg): print(f"[INFO] {msg}")
    def warning(self, msg): print(f"[WARNING] {msg}")
    def error(self, msg, exc_info=False): print(f"[ERROR] {msg}")


def example_1_basic_token_check():
    """示例1: 基础Token检查"""
    print("\n" + "="*80)
    print("示例1: 基础Token检查")
    print("="*80)

    logger = SimpleLogger()
    token_manager = TokenManager(logger=logger)

    # 模拟患者数据
    patient_data = {
        'patient_name': '张三',
        'patient_timeline': [
            {'date': '2024-01-01', 'event': '首次就诊', 'description': '患者主诉头痛...' * 100}
            for _ in range(50)
        ]
    }

    # 检查token限制
    check_result = token_manager.check_input_limit(patient_data, 'gemini-3-flash-preview')

    print(f"\n检查结果:")
    print(f"  总tokens: {check_result['total_tokens']}")
    print(f"  安全限制: {check_result['safe_limit']}")
    print(f"  需要压缩: {check_result['compression_needed']}")
    print(f"  使用率: {check_result['usage_ratio']:.1%}")


def example_2_auto_compression():
    """示例2: 自动数据压缩"""
    print("\n" + "="*80)
    print("示例2: 自动数据压缩")
    print("="*80)

    logger = SimpleLogger()
    token_manager = TokenManager(logger=logger)
    data_compressor = PatientDataCompressor(logger=logger, token_manager=token_manager)

    # 创建大量数据
    large_patient_data = {
        'patient_name': '李四',
        'patient_info': {'age': 45, 'gender': '男'},
        'patient_timeline': [
            {
                'date': f'2024-{i%12+1:02d}-{i%28+1:02d}',
                'event': f'就诊记录{i}',
                'description': '详细的就诊记录内容...' * 50
            }
            for i in range(200)  # 200条记录
        ],
        'raw_files_data': [
            {
                'filename': f'报告{i}.pdf',
                'extracted_text': '报告内容...' * 100
            }
            for i in range(100)  # 100个文件
        ]
    }

    # 检查原始数据
    original_tokens = token_manager.estimate_tokens(large_patient_data)
    print(f"\n原始数据: {original_tokens} tokens")

    # 自动压缩
    check_result = token_manager.check_input_limit(large_patient_data, 'gemini-3-flash-preview')

    if check_result['compression_needed']:
        print(f"⚠️ 数据超过安全限制，开始压缩...")

        # 压缩到安全限制
        compressed_data = data_compressor.compress_data(
            large_patient_data,
            target_tokens=check_result['safe_limit']
        )

        # 检查压缩后的数据
        compressed_tokens = token_manager.estimate_tokens(compressed_data)
        print(f"压缩后数据: {compressed_tokens} tokens")
        print(f"压缩比例: {compressed_tokens/original_tokens:.1%}")

        # 验证关键字段
        print(f"\n关键字段验证:")
        print(f"  patient_name: {'✅' if 'patient_name' in compressed_data else '❌'}")
        print(f"  patient_info: {'✅' if 'patient_info' in compressed_data else '❌'}")
        print(f"  patient_timeline: {len(compressed_data.get('patient_timeline', []))} 条记录")
        print(f"  raw_files_data: {len(compressed_data.get('raw_files_data', []))} 个文件")


def example_3_timeline_compression():
    """示例3: 时间轴压缩"""
    print("\n" + "="*80)
    print("示例3: 时间轴压缩")
    print("="*80)

    logger = SimpleLogger()
    token_manager = TokenManager(logger=logger)
    data_compressor = PatientDataCompressor(logger=logger, token_manager=token_manager)

    # 创建时间轴数据
    timeline = [
        {
            'date': f'2024-{i%12+1:02d}-{i%28+1:02d}',
            'event_type': ['检查', '治疗', '复诊'][i % 3],
            'description': f'第{i+1}次就诊，进行了常规检查和治疗。' * 10,
            'doctor': f'医生{i%5}'
        }
        for i in range(150)
    ]

    print(f"\n原始时间轴: {len(timeline)} 条记录")

    # 压缩到50条
    target_tokens = 10000
    compressed_timeline = data_compressor.compress_timeline(timeline, target_tokens)

    print(f"压缩后时间轴: {len(compressed_timeline)} 条记录")

    # 显示日期范围
    if compressed_timeline:
        dates = [r['date'] for r in compressed_timeline if 'date' in r]
        if dates:
            print(f"日期范围: {min(dates)} 到 {max(dates)}")


def example_4_file_compression():
    """示例4: 文件数据压缩（优先保留医学影像）"""
    print("\n" + "="*80)
    print("示例4: 文件数据压缩")
    print("="*80)

    logger = SimpleLogger()
    token_manager = TokenManager(logger=logger)
    data_compressor = PatientDataCompressor(logger=logger, token_manager=token_manager)

    # 创建文件数据（包含医学影像和普通文件）
    raw_files = []
    for i in range(80):
        file_item = {
            'filename': f'文件{i+1}.pdf',
            'file_type': ['检验报告', '影像报告', '病历'][i % 3],
            'exam_date': f'2024-{i%12+1:02d}-{i%28+1:02d}',
            'has_medical_image': i % 4 == 0,  # 每4个文件有1个医学影像
            'extracted_text': f'文件内容...' * 50
        }
        raw_files.append(file_item)

    medical_count = sum(1 for f in raw_files if f.get('has_medical_image'))
    print(f"\n原始文件: {len(raw_files)} 个 (医学影像: {medical_count} 个)")

    # 压缩到30个文件
    target_tokens = 5000
    compressed_files = data_compressor.compress_raw_files(raw_files, target_tokens)

    compressed_medical = sum(1 for f in compressed_files if f.get('has_medical_image'))
    print(f"压缩后文件: {len(compressed_files)} 个 (医学影像: {compressed_medical} 个)")
    print(f"医学影像保留率: {compressed_medical/medical_count:.1%}")


def example_5_integrated_workflow():
    """示例5: 完整工作流程（模拟PPT生成）"""
    print("\n" + "="*80)
    print("示例5: 完整工作流程")
    print("="*80)

    logger = SimpleLogger()
    token_manager = TokenManager(logger=logger)
    data_compressor = PatientDataCompressor(logger=logger, token_manager=token_manager)

    # 模拟完整的患者数据
    patient_data = {
        'patient_name': '王五',
        'patient_info': {
            'basic': {'name': '王五', 'age': 50, 'gender': '女'},
            'contact': {'phone': '13800138000'}
        },
        'diagnoses': [
            {'date': '2024-01-15', 'diagnosis': '高血压'},
            {'date': '2024-02-20', 'diagnosis': '糖尿病'}
        ],
        'patient_timeline': [
            {
                'date': f'2024-{i%12+1:02d}-{i%28+1:02d}',
                'event': f'就诊{i+1}',
                'description': '详细记录...' * 30
            }
            for i in range(100)
        ],
        'raw_files_data': [
            {
                'filename': f'报告{i}.pdf',
                'has_medical_image': i % 3 == 0,
                'extracted_text': '报告内容...' * 50
            }
            for i in range(60)
        ]
    }

    print("\n步骤1: 检查Token限制")
    check_result = token_manager.check_input_limit(patient_data, 'gemini-3-flash-preview')
    print(f"  总tokens: {check_result['total_tokens']}")
    print(f"  需要压缩: {check_result['compression_needed']}")

    if check_result['compression_needed']:
        print("\n步骤2: 执行数据压缩")
        target_tokens = check_result['safe_limit']

        # 分别压缩不同部分
        compressed_timeline = data_compressor.compress_timeline(
            patient_data['patient_timeline'],
            target_tokens=int(target_tokens * 0.5)
        )

        compressed_files = data_compressor.compress_raw_files(
            patient_data['raw_files_data'],
            target_tokens=int(target_tokens * 0.3)
        )

        # 构建压缩后的数据
        compressed_patient_data = {
            'patient_name': patient_data['patient_name'],
            'patient_info': patient_data['patient_info'],
            'diagnoses': patient_data['diagnoses'],
            'patient_timeline': compressed_timeline,
            'raw_files_data': compressed_files
        }

        print("\n步骤3: 验证压缩结果")
        compressed_tokens = token_manager.estimate_tokens(compressed_patient_data)
        print(f"  压缩后tokens: {compressed_tokens}")
        print(f"  压缩比例: {compressed_tokens/check_result['total_tokens']:.1%}")
        print(f"  时间轴记录: {len(compressed_timeline)} 条")
        print(f"  文件数量: {len(compressed_files)} 个")

        print("\n步骤4: 最终检查")
        final_check = token_manager.check_input_limit(compressed_patient_data, 'gemini-3-flash-preview')
        if final_check['within_limit']:
            print("  ✅ 数据在限制内，可以继续生成PPT")
        else:
            print("  ❌ 数据仍超限，需要更激进的压缩或分块处理")


def main():
    """运行所有示例"""
    print("\n🚀 Token管理和数据压缩使用示例")
    print("="*80)

    try:
        example_1_basic_token_check()
        example_2_auto_compression()
        example_3_timeline_compression()
        example_4_file_compression()
        example_5_integrated_workflow()

        print("\n" + "="*80)
        print("✅ 所有示例运行完成！")
        print("="*80)

    except Exception as e:
        print(f"\n❌ 示例运行失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
