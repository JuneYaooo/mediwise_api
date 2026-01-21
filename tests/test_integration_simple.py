"""
简化的集成验证测试脚本

验证代码集成是否完成:
1. patient_data_crew 数据压缩代码
2. ppt_generation_crew 分块输出代码
3. patient_info_update_crew 数据压缩代码
"""

import os
import re

def check_file_contains(file_path, patterns):
    """检查文件是否包含指定的模式"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        results = {}
        for name, pattern in patterns.items():
            if isinstance(pattern, str):
                results[name] = pattern in content
            else:  # regex pattern
                results[name] = bool(re.search(pattern, content))

        return results
    except Exception as e:
        print(f"❌ 读取文件失败: {e}")
        return None

def test_patient_data_crew():
    """测试 patient_data_crew 集成"""
    print("=" * 80)
    print("测试 1: patient_data_crew 数据压缩集成验证")
    print("=" * 80)

    file_path = "src/crews/patient_data_crew/patient_data_crew.py"
    patterns = {
        "导入PatientDataCompressor": "from src.utils.data_compressor import PatientDataCompressor",
        "导入TokenManager": "from src.utils.token_manager import TokenManager",
        "导入UniversalChunkedGenerator": "from src.utils.universal_chunked_generator import UniversalChunkedGenerator",
        "初始化token_manager": r"token_manager\s*=\s*TokenManager",
        "初始化data_compressor": r"data_compressor\s*=\s*PatientDataCompressor",
        "压缩preprocessed_info": r"compressed_patient_info\s*=\s*data_compressor\.compress_data",
        "压缩existing_timeline": r"compressed_timeline\s*=\s*data_compressor\.compress_timeline",
        "压缩existing_patient_journey": r"compressed_journey\s*=\s*data_compressor\.compress_data",
        "压缩existing_mdt_report": r"compressed_mdt_report\s*=\s*data_compressor\.compress_data"
    }

    results = check_file_contains(file_path, patterns)
    if results is None:
        return False

    all_passed = all(results.values())
    for name, passed in results.items():
        status = "✅" if passed else "❌"
        print(f"{status} {name}")

    return all_passed

def test_ppt_generation_crew():
    """测试 ppt_generation_crew 集成"""
    print("\n" + "=" * 80)
    print("测试 2: ppt_generation_crew 分块输出集成验证")
    print("=" * 80)

    file_path = "src/crews/ppt_generation_crew/ppt_generation_crew.py"
    patterns = {
        "导入UniversalChunkedGenerator": "from src.utils.universal_chunked_generator import UniversalChunkedGenerator",
        "使用UniversalChunkedGenerator": r"UniversalChunkedGenerator\(logger=logger",
        "调用generate_in_chunks": r"\.generate_in_chunks\(",
        "传递task_type参数": r"task_type\s*=\s*['\"]ppt_generation['\"]",
        "传递template_or_schema参数": r"template_or_schema\s*=\s*template_json_str"
    }

    results = check_file_contains(file_path, patterns)
    if results is None:
        return False

    all_passed = all(results.values())
    for name, passed in results.items():
        status = "✅" if passed else "❌"
        print(f"{status} {name}")

    return all_passed

def test_patient_info_update_crew():
    """测试 patient_info_update_crew 集成"""
    print("\n" + "=" * 80)
    print("测试 3: patient_info_update_crew 数据压缩集成验证")
    print("=" * 80)

    file_path = "src/crews/patient_info_update_crew/patient_info_update_crew.py"
    patterns = {
        "导入PatientDataCompressor": "from src.utils.data_compressor import PatientDataCompressor",
        "导入TokenManager": "from src.utils.token_manager import TokenManager",
        "初始化token_manager": r"token_manager\s*=\s*TokenManager",
        "初始化data_compressor": r"data_compressor\s*=\s*PatientDataCompressor",
        "检查输入限制": r"check_input_limit\(current_patient_data",
        "压缩patient_timeline": r"compress_timeline\(",
        "压缩patient_journey": r"compressed_patient_data\[\"patient_journey\"\]",
        "压缩mdt_simple_report": r"compressed_patient_data\[\"mdt_simple_report\"\]",
        "使用压缩后的数据": r"compressed_patient_data\s*#.*使用压缩后的数据"
    }

    results = check_file_contains(file_path, patterns)
    if results is None:
        return False

    all_passed = all(results.values())
    for name, passed in results.items():
        status = "✅" if passed else "❌"
        print(f"{status} {name}")

    return all_passed

def main():
    """运行所有测试"""
    print("\n" + "=" * 80)
    print("开始集成验证测试（代码检查）")
    print("=" * 80)

    results = []

    # 运行所有测试
    results.append(("patient_data_crew 数据压缩集成", test_patient_data_crew()))
    results.append(("ppt_generation_crew 分块输出集成", test_ppt_generation_crew()))
    results.append(("patient_info_update_crew 数据压缩集成", test_patient_info_update_crew()))

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
        print("\n✅ 集成完成:")
        print("  1. patient_data_crew: 数据压缩功能已集成")
        print("  2. ppt_generation_crew: 分块输出功能已集成（带上下文传递）")
        print("  3. patient_info_update_crew: 数据压缩功能已集成")
        return 0
    else:
        print(f"\n⚠️ {total - passed} 个测试失败，请检查集成")
        return 1

if __name__ == "__main__":
    import sys
    exit_code = main()
    sys.exit(exit_code)
