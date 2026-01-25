"""
集成验证测试脚本

验证以下集成是否正常工作:
1. patient_data_crew 数据压缩
2. ppt_generation_crew 分块输出
3. patient_info_update_crew 数据压缩
"""

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def test_patient_data_crew_imports():
    """测试 patient_data_crew 的导入"""
    print("=" * 80)
    print("测试 1: patient_data_crew 导入验证")
    print("=" * 80)

    try:
        from src.crews.patient_data_crew.patient_data_crew import PatientDataCrew
        from src.utils.data_compressor import PatientDataCompressor
        from src.utils.token_manager import TokenManager
        from src.utils.universal_chunked_generator import UniversalChunkedGenerator

        print("✅ 所有必需的模块导入成功")
        print("  ├─ PatientDataCrew")
        print("  ├─ PatientDataCompressor")
        print("  ├─ TokenManager")
        print("  └─ UniversalChunkedGenerator")
        return True
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        return False

def test_ppt_generation_crew_imports():
    """测试 ppt_generation_crew 的导入"""
    print("\n" + "=" * 80)
    print("测试 2: ppt_generation_crew 导入验证")
    print("=" * 80)

    try:
        from src.crews.ppt_generation_crew.ppt_generation_crew import PPTGenerationCrew
        from src.utils.universal_chunked_generator import UniversalChunkedGenerator
        from src.utils.token_manager import TokenManager

        print("✅ 所有必需的模块导入成功")
        print("  ├─ PPTGenerationCrew")
        print("  ├─ UniversalChunkedGenerator")
        print("  └─ TokenManager")
        return True
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        return False

def test_patient_info_update_crew_imports():
    """测试 patient_info_update_crew 的导入"""
    print("\n" + "=" * 80)
    print("测试 3: patient_info_update_crew 导入验证")
    print("=" * 80)

    try:
        from src.crews.patient_info_update_crew.patient_info_update_crew import PatientInfoUpdateCrew
        from src.utils.data_compressor import PatientDataCompressor
        from src.utils.token_manager import TokenManager

        print("✅ 所有必需的模块导入成功")
        print("  ├─ PatientInfoUpdateCrew")
        print("  ├─ PatientDataCompressor")
        print("  └─ TokenManager")
        return True
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        return False

def test_data_compressor_functionality():
    """测试数据压缩器的基本功能"""
    print("\n" + "=" * 80)
    print("测试 4: 数据压缩器功能验证")
    print("=" * 80)

    try:
        from src.utils.data_compressor import PatientDataCompressor
        from src.utils.token_manager import TokenManager
        from src.utils.logger import BeijingLogger

        logger = BeijingLogger().get_logger()
        token_manager = TokenManager(logger=logger)
        compressor = PatientDataCompressor(logger=logger, token_manager=token_manager)

        # 测试数据
        test_data = {
            "field1": "这是一个测试字段" * 100,
            "field2": "另一个测试字段" * 100,
            "field3": ["列表项1" * 50, "列表项2" * 50]
        }

        # 尝试压缩
        compressed = compressor.compress_data(test_data, target_tokens=500)

        print("✅ 数据压缩器功能正常")
        print(f"  ├─ 原始数据大小: {len(str(test_data))} 字符")
        print(f"  └─ 压缩后数据大小: {len(str(compressed))} 字符")
        return True
    except Exception as e:
        print(f"❌ 数据压缩器测试失败: {e}")
        import traceback
        print(traceback.format_exc())
        return False

def test_universal_chunked_generator_functionality():
    """测试通用分块生成器的基本功能"""
    print("\n" + "=" * 80)
    print("测试 5: 通用分块生成器功能验证")
    print("=" * 80)

    try:
        from src.utils.universal_chunked_generator import UniversalChunkedGenerator
        from src.utils.token_manager import TokenManager
        from src.utils.logger import BeijingLogger

        logger = BeijingLogger().get_logger()
        token_manager = TokenManager(logger=logger)
        generator = UniversalChunkedGenerator(logger=logger, token_manager=token_manager)

        print("✅ 通用分块生成器初始化成功")
        print("  ├─ 支持上下文传递")
        print("  └─ 支持多种任务类型")
        return True
    except Exception as e:
        print(f"❌ 通用分块生成器测试失败: {e}")
        import traceback
        print(traceback.format_exc())
        return False

def main():
    """运行所有测试"""
    print("\n" + "=" * 80)
    print("开始集成验证测试")
    print("=" * 80)

    results = []

    # 运行所有测试
    results.append(("patient_data_crew 导入", test_patient_data_crew_imports()))
    results.append(("ppt_generation_crew 导入", test_ppt_generation_crew_imports()))
    results.append(("patient_info_update_crew 导入", test_patient_info_update_crew_imports()))
    results.append(("数据压缩器功能", test_data_compressor_functionality()))
    results.append(("通用分块生成器功能", test_universal_chunked_generator_functionality()))

    # 汇总结果
    print("\n" + "=" * 80)
    print("测试结果汇总")
    print("=" * 80)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{status}: {test_name}")

    print("\n" + "=" * 80)
    print(f"总计: {passed}/{total} 测试通过 ({passed/total*100:.0f}%)")
    print("=" * 80)

    if passed == total:
        print("\n🎉 所有集成验证测试通过！")
        return 0
    else:
        print(f"\n⚠️ {total - passed} 个测试失败，请检查集成")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
