#!/usr/bin/env python3
"""
PPT API 测试脚本
"""
import requests
import json

BASE_URL = "http://localhost:9527"

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


def list_patients():
    """列出最近的患者"""
    print(f"\n{'='*60}")
    print(f"👥 查询最近的患者列表")
    print(f"{'='*60}")

    from sqlalchemy import create_engine, text
    from app.db.database import DATABASE_URL

    engine = create_engine(DATABASE_URL)

    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT
                patient_id,
                name,
                created_at
            FROM bus_patient
            WHERE is_deleted = false
            ORDER BY created_at DESC
            LIMIT 5;
        """))

        patients = list(result)

        if patients:
            print(f"\n找到 {len(patients)} 个患者:\n")
            for i, p in enumerate(patients, 1):
                print(f"{i}. ID: {p[0]}")
                print(f"   姓名: {p[1]}")
                print(f"   创建时间: {p[2]}")
                print()
            return [p[0] for p in patients]
        else:
            print("❌ 没有找到患者")
            return []


if __name__ == "__main__":
    import sys

    print("=" * 60)
    print("🏥 MediWise PPT API 测试工具")
    print("=" * 60)

    # 1. 列出患者
    patient_ids = list_patients()

    if not patient_ids:
        print("\n❌ 没有可测试的患者，请先上传患者数据")
        sys.exit(1)

    # 2. 选择患者
    if len(sys.argv) > 1:
        patient_id = sys.argv[1]
        print(f"\n使用命令行参数指定的患者: {patient_id}")

        # 检查是否要生成 PPT
        if len(sys.argv) > 2 and sys.argv[2] == 'generate':
            test_get_ppt_data(patient_id)
            test_generate_ppt(patient_id)
            print("\n" + "=" * 60)
            print("测试完成！")
            print("=" * 60)
            sys.exit(0)
    else:
        patient_id = patient_ids[0]
        print(f"\n使用最近的患者: {patient_id}")

    # 3. 测试获取 PPT 数据
    success1 = test_get_ppt_data(patient_id)

    # 4. 提示如何生成 PPT
    if success1:
        print("\n提示：如需测试生成 PPT，请运行:")
        print(f"  python test_ppt_api.py {patient_id} generate")

    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)
