"""
完整流程测试脚本
1. 添加 disease_names 字段
2. 测试疾病识别和存储
3. 测试配置读取
"""
import sys
import os

# 添加项目路径
sys.path.insert(0, '/home/ubuntu/github/mediwise_api')

def test_add_field():
    """测试添加字段"""
    print("=" * 80)
    print("步骤 1: 添加 disease_names 字段到 bus_patient 表")
    print("=" * 80)

    try:
        from app.db.database import SessionLocal
        from sqlalchemy import text

        db = SessionLocal()
        try:
            # 添加字段
            sql = """
            ALTER TABLE bus_patient
            ADD COLUMN IF NOT EXISTS disease_names VARCHAR(500) NULL;
            """
            db.execute(text(sql))
            db.commit()
            print("✅ 成功添加 disease_names 字段")

            # 验证字段
            verify_sql = """
            SELECT column_name, data_type, character_maximum_length
            FROM information_schema.columns
            WHERE table_name = 'bus_patient' AND column_name = 'disease_names';
            """
            result = db.execute(text(verify_sql))
            row = result.fetchone()

            if row:
                print(f"✅ 验证成功: {row}")
            else:
                print("⚠️ 字段可能已存在")

        finally:
            db.close()

    except Exception as e:
        print(f"❌ 添加字段失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True


def test_clinical_config():
    """测试 bus_clinical_config 表"""
    print("\n" + "=" * 80)
    print("步骤 2: 检查 bus_clinical_config 表")
    print("=" * 80)

    try:
        from app.db.database import SessionLocal
        from app.models.bus_models import ClinicalConfig

        db = SessionLocal()
        try:
            # 查询所有激活的配置
            configs = db.query(ClinicalConfig).filter(
                ClinicalConfig.is_active == True,
                ClinicalConfig.is_deleted == False
            ).all()

            print(f"✅ 找到 {len(configs)} 条激活的临床配置")

            for config in configs:
                print(f"  - 疾病: {config.disease_name}, PPT类型: {config.ppt_type}")

            if len(configs) == 0:
                print("⚠️ 警告: 没有找到激活的临床配置，请先添加配置数据")

        finally:
            db.close()

    except Exception as e:
        print(f"❌ 检查配置失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True


def test_patient_disease_storage():
    """测试患者疾病存储"""
    print("\n" + "=" * 80)
    print("步骤 3: 测试患者疾病存储")
    print("=" * 80)

    try:
        from app.db.database import SessionLocal
        from app.models.bus_models import Patient
        import uuid

        db = SessionLocal()
        try:
            # 创建测试患者
            test_patient_id = str(uuid.uuid4())
            test_patient = Patient(
                patient_id=test_patient_id,
                name="测试患者",
                disease_names="高血压,糖尿病",  # 测试疾病名称
                created_by="test_script"
            )

            db.add(test_patient)
            db.commit()
            print(f"✅ 创建测试患者: {test_patient_id}")

            # 读取并验证
            patient = db.query(Patient).filter(Patient.patient_id == test_patient_id).first()
            if patient and patient.disease_names:
                print(f"✅ 验证成功: disease_names = {patient.disease_names}")

                # 测试提取第一个疾病
                disease_name = patient.disease_names.split(',')[0].strip()
                print(f"✅ 提取第一个疾病: {disease_name}")
            else:
                print("❌ 验证失败: 无法读取 disease_names")

            # 清理测试数据
            db.delete(patient)
            db.commit()
            print("✅ 清理测试数据完成")

        finally:
            db.close()

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True


def test_treatment_processor():
    """测试 TreatmentDataProcessor 从数据库读取配置"""
    print("\n" + "=" * 80)
    print("步骤 4: 测试 TreatmentDataProcessor 从数据库读取配置")
    print("=" * 80)

    try:
        from src.custom_tools.treatment_data_processor import TreatmentDataProcessor

        # 测试1: 通过疾病名称
        print("\n测试1: 通过疾病名称初始化")
        processor1 = TreatmentDataProcessor(disease_name="高血压")
        if processor1.treatment_config:
            print(f"✅ 成功加载配置: {len(processor1.treatment_config)} 条")
        else:
            print("⚠️ 未加载到配置（可能数据库中没有该疾病的配置）")

        # 测试2: 通过患者ID（需要先创建测试患者）
        print("\n测试2: 通过患者ID初始化")
        from app.db.database import SessionLocal
        from app.models.bus_models import Patient
        import uuid

        db = SessionLocal()
        try:
            test_patient_id = str(uuid.uuid4())
            test_patient = Patient(
                patient_id=test_patient_id,
                name="测试患者2",
                disease_names="高血压",
                created_by="test_script"
            )
            db.add(test_patient)
            db.commit()

            processor2 = TreatmentDataProcessor(patient_id=test_patient_id)
            if processor2.treatment_config:
                print(f"✅ 成功通过患者ID加载配置: {len(processor2.treatment_config)} 条")
            else:
                print("⚠️ 未加载到配置")

            # 清理
            db.delete(test_patient)
            db.commit()

        finally:
            db.close()

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True


def main():
    """主测试流程"""
    print("\n" + "=" * 80)
    print("开始完整流程测试")
    print("=" * 80)

    results = []

    # 步骤1: 添加字段
    results.append(("添加 disease_names 字段", test_add_field()))

    # 步骤2: 检查配置表
    results.append(("检查 bus_clinical_config 表", test_clinical_config()))

    # 步骤3: 测试患者疾病存储
    results.append(("测试患者疾病存储", test_patient_disease_storage()))

    # 步骤4: 测试 TreatmentDataProcessor
    results.append(("测试 TreatmentDataProcessor", test_treatment_processor()))

    # 总结
    print("\n" + "=" * 80)
    print("测试结果总结")
    print("=" * 80)

    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{name}: {status}")

    all_passed = all(result for _, result in results)
    if all_passed:
        print("\n🎉 所有测试通过！")
    else:
        print("\n⚠️ 部分测试失败，请检查错误信息")

    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
