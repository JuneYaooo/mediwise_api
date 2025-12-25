"""
检查 bus_patient_files 和 bus_patient_structured_data 之间的 file_uuid 关联
"""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

# 数据库连接
DATABASE_URL = "postgresql://mdtadmin:mdtadmin@2025@112.124.15.49:5432/db_mdt"
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

def check_file_uuid_mapping():
    """检查file_uuid的映射关系"""
    session = Session()

    try:
        print("=" * 80)
        print("检查 bus_patient_files 表中的 file_uuid")
        print("=" * 80)

        # 查询 bus_patient_files 中的 file_uuid 样例
        result = session.execute(text("""
            SELECT
                id,
                patient_id,
                file_uuid,
                file_name,
                conversation_id
            FROM bus_patient_files
            WHERE is_deleted = false
            ORDER BY created_at DESC
            LIMIT 10
        """))

        files_data = []
        print("\n📁 bus_patient_files 表数据:")
        for row in result:
            print(f"\nid: {row[0]}")
            print(f"patient_id: {row[1]}")
            print(f"file_uuid: {row[2]}")
            print(f"file_name: {row[3]}")
            print(f"conversation_id: {row[4]}")
            files_data.append({
                'id': row[0],
                'patient_id': row[1],
                'file_uuid': row[2],
                'conversation_id': row[4]
            })

        print("\n" + "=" * 80)
        print("检查 bus_patient_structured_data 表")
        print("=" * 80)

        # 获取一些患者ID
        if files_data:
            patient_ids = [f['patient_id'] for f in files_data[:3]]

            for patient_id in patient_ids:
                print(f"\n🔍 检查患者 {patient_id} 的结构化数据:")

                result = session.execute(text("""
                    SELECT
                        id,
                        patient_id,
                        data_type,
                        conversation_id,
                        structuredcontent::text
                    FROM bus_patient_structured_data
                    WHERE patient_id = :patient_id
                    AND is_deleted = false
                    AND data_type = 'timeline'
                    LIMIT 1
                """), {'patient_id': patient_id})

                row = result.fetchone()
                if row:
                    print(f"  id: {row[0]}")
                    print(f"  data_type: {row[2]}")
                    print(f"  conversation_id: {row[3]}")

                    # 检查 structuredcontent 中是否包含 file_uuid
                    content_str = row[4]
                    if content_str:
                        # 搜索是否包含文件相关的UUID
                        if 'file_uuid' in content_str.lower():
                            print("  ✅ structuredcontent 中包含 'file_uuid' 字段")
                        else:
                            print("  ⚠️ structuredcontent 中不包含 'file_uuid' 字段")

                        # 显示前500个字符
                        print(f"  structuredcontent 预览: {content_str[:500]}...")
                else:
                    print("  ⚠️ 没有找到该患者的 timeline 数据")

        print("\n" + "=" * 80)
        print("分析结论")
        print("=" * 80)
        print("""
🔍 关键发现:

1. bus_patient_files.file_uuid
   - 这是文件的唯一标识符
   - 在文件上传/处理时生成
   - 用于标识具体的文件

2. bus_patient_structured_data.structuredcontent
   - 这是 LLM 处理后的结构化数据（JSON格式）
   - 可能不直接包含 file_uuid
   - 通过 patient_id 和 conversation_id 间接关联

3. 正确的关联方式:
   ✅ 通过 patient_id 关联:
      bus_patient_files.patient_id = bus_patient_structured_data.patient_id

   ✅ 通过 conversation_id 关联:
      bus_patient_files.conversation_id = bus_patient_structured_data.conversation_id

4. 如果需要在 structuredcontent 中存储 file_uuid:
   - 需要在生成结构化数据时显式添加文件引用
   - 或者在 raw_files_data 中包含文件信息
        """)

    finally:
        session.close()

if __name__ == "__main__":
    check_file_uuid_mapping()
