#!/usr/bin/env python3
"""
查询数据库中可用的测试患者
"""

import sys
import os

# 添加项目路径
sys.path.insert(0, '/home/ubuntu/github/mediwise_api')

from app.db.database import SessionLocal
from app.models.bus_models import Patient
from app.models.patient_detail_helpers import PatientDetailHelper

def check_test_patients():
    """查询可用的测试患者"""
    db = SessionLocal()
    try:
        print("=" * 80)
        print("查询数据库中的可用患者")
        print("=" * 80)
        print()

        # 查询所有未删除的患者
        patients = db.query(Patient).filter(
            Patient.is_deleted == False
        ).limit(10).all()

        if not patients:
            print("⚠️  数据库中没有找到任何患者记录")
            return

        print(f"找到 {len(patients)} 个患者记录:\n")

        for i, patient in enumerate(patients, 1):
            print(f"{i}. Patient ID: {patient.patient_id}")
            print(f"   姓名: {patient.name or '未设置'}")
            print(f"   性别: {patient.gender or '未设置'}")
            print(f"   出生日期: {patient.birth_date or '未设置'}")

            # 检查是否有结构化数据
            patient_detail = PatientDetailHelper.get_latest_patient_detail_by_patient_id(
                db, patient.patient_id
            )

            if patient_detail:
                print(f"   ✅ 有结构化数据（可用于测试修改接口）")

                # 获取时间轴信息
                timeline = PatientDetailHelper.get_patient_timeline(patient_detail)
                if timeline:
                    # 尝试提取一些基本信息
                    basic_info = timeline.get("基本信息", {}) or timeline.get("patient_info", {}).get("basic", {})
                    if basic_info:
                        print(f"   基本信息:")
                        if basic_info.get("name"):
                            print(f"     - 姓名: {basic_info.get('name')}")
                        if basic_info.get("age"):
                            print(f"     - 年龄: {basic_info.get('age')}")
                        if basic_info.get("gender"):
                            print(f"     - 性别: {basic_info.get('gender')}")
            else:
                print(f"   ❌ 无结构化数据（需要先调用 /process_patient_data_smart 创建数据）")

            print()

        print("-" * 80)
        print("\n💡 测试提示:")
        print("   使用有结构化数据(✅)的 patient_id 来测试修改接口")
        print()
        print("   测试命令示例:")
        if patients:
            first_patient_with_data = None
            for patient in patients:
                patient_detail = PatientDetailHelper.get_latest_patient_detail_by_patient_id(
                    db, patient.patient_id
                )
                if patient_detail:
                    first_patient_with_data = patient
                    break

            if first_patient_with_data:
                print(f"   python test_modify_patient_stream.py {first_patient_with_data.patient_id} '将患者年龄修改为45岁'")
            else:
                print(f"   python test_modify_patient_stream.py <patient_id> '将患者年龄修改为45岁'")
        print()

    except Exception as e:
        print(f"❌ 查询失败: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    check_test_patients()
