#!/usr/bin/env python3
"""
PPT API 测试脚本
"""
import requests
import json

BASE_URL = "http://182.254.240.153:9527"#"http://182.254.240.153:9527" #"http://localhost:9527"

def test_get_ppt_data(patient_id):
    """测试获取 PPT 数据"""
    print(f"\n{'='*60}")
    print(f"📊 测试 1: 获取患者 PPT 数据")
    print(f"{'='*60}")

    url = f"{BASE_URL}/api/patients/{patient_id}/ppt_data"
    print(f"请求 URL: {url}")

    try:
        response = requests.get(url)
        print(f"状态码: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                patient_data = data['data']
                print(f"\n✅ 查询成功！")
                print(f"  患者姓名: {patient_data['patient_info']['name']}")
                print(f"  患者ID: {patient_data['patient_info']['patient_id']}")
                print(f"  文件总数: {len(patient_data['raw_files_data'])} 个")
                print(f"  Timeline: {'✅ 有' if patient_data['patient_timeline'] else '❌ 无'}")
                print(f"  Journey: {'✅ 有' if patient_data['patient_journey'] else '❌ 无'}")
                print(f"  MDT报告: {len(patient_data['mdt_reports'])} 个")

                # 显示前3个文件
                if patient_data['raw_files_data']:
                    print(f"\n  前3个文件:")
                    for i, f in enumerate(patient_data['raw_files_data'][:3], 1):
                        print(f"    {i}. {f['file_name']} ({f.get('source_type', 'unknown')})")

                return True
            else:
                print(f"❌ 查询失败: {data}")
                return False
        else:
            print(f"❌ 请求失败: {response.text}")
            return False

    except Exception as e:
        print(f"❌ 异常: {str(e)}")
        return False


def test_generate_ppt(patient_id):
    """测试生成 PPT"""
    print(f"\n{'='*60}")
    print(f"📄 测试 2: 生成患者 PPT")
    print(f"{'='*60}")

    url = f"{BASE_URL}/api/patients/{patient_id}/generate_ppt"
    print(f"请求 URL: {url}")
    print("⚠️  注意：PPT 生成可能需要较长时间...")

    try:
        response = requests.post(url, timeout=300)  # 5分钟超时
        print(f"状态码: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                print(f"\n✅ PPT 生成成功！")
                print(f"  PPT URL: {result.get('ppt_url') or result.get('qiniu_url')}")
                print(f"  本地路径: {result.get('local_path', 'N/A')}")
                return True
            else:
                print(f"❌ PPT 生成失败: {result.get('error', result)}")
                return False
        else:
            print(f"❌ 请求失败: {response.text}")
            return False

    except requests.exceptions.Timeout:
        print(f"❌ 请求超时（超过5分钟）")
        return False
    except Exception as e:
        print(f"❌ 异常: {str(e)}")
        return False


def verify_patient_exists(patient_id):
    """验证患者是否存在"""
    try:
        url = f"{BASE_URL}/api/patients/{patient_id}/ppt_data"
        response = requests.get(url, timeout=5)

        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                patient_info = data['data']['patient_info']
                return True, patient_info
            else:
                return False, None
        else:
            return False, None

    except Exception as e:
        return False, None


if __name__ == "__main__":
    import sys

    # ========================================
    # 配置区域 - 直接在这里修改配置
    # ========================================

    # 配置1: 指定要测试的 patient_id（必填）
    PATIENT_ID = "685f1678-8260-41fa-8b7c-660c299bf44b"  # 👈 修改为实际的患者ID

    # 配置2: 是否要生成 PPT
    GENERATE_PPT = True  # True: 测试获取数据 + 生成PPT, False: 只测试获取数据

    # ========================================

    print("=" * 60)
    print("🏥 MediWise PPT API 测试工具")
    print("=" * 60)

    # 1. 检查配置
    if not PATIENT_ID:
        print("\n❌ 错误：请在脚本中配置 PATIENT_ID")
        print("💡 提示：将 PATIENT_ID 变量设置为实际的患者ID")
        sys.exit(1)

    print(f"\n📋 测试配置:")
    print(f"   患者ID: {PATIENT_ID}")
    print(f"   生成PPT: {'是' if GENERATE_PPT else '否'}")

    # 2. 验证患者是否存在
    print(f"\n🔍 验证患者是否存在...")
    exists, patient_info = verify_patient_exists(PATIENT_ID)

    if exists:
        print(f"✅ 患者存在")
        print(f"   姓名: {patient_info.get('name', 'N/A')}")
    else:
        print(f"❌ 患者不存在或无法访问: {PATIENT_ID}")
        print(f"💡 提示：请检查 PATIENT_ID 是否正确")
        sys.exit(1)

    # 3. 测试获取 PPT 数据
    success1 = test_get_ppt_data(PATIENT_ID)

    # 4. 根据配置决定是否生成 PPT
    if GENERATE_PPT and success1:
        test_generate_ppt(PATIENT_ID)
    elif success1 and not GENERATE_PPT:
        print("\n💡 提示：如需测试生成 PPT，请将脚本中的 GENERATE_PPT 设置为 True")

    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)
