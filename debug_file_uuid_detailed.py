"""
详细排查 file_uuid 对应关系
"""
import sys
import json
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# 数据库连接
DATABASE_URL = "postgresql://mdtadmin:mdtadmin@2025@112.124.15.49:5432/db_mdt"
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

def check_file_uuid_mapping(patient_id=None):
    """检查file_uuid的映射关系"""
    session = Session()

    try:
        print("=" * 100)
        print("🔍 file_uuid 对应关系详细排查")
        print("=" * 100)

        # 如果没有指定patient_id，获取最新的一个
        if not patient_id:
            result = session.execute(text("""
                SELECT DISTINCT patient_id
                FROM bus_patient_files
                WHERE is_deleted = false
                ORDER BY created_at DESC
                LIMIT 1
            """))
            row = result.fetchone()
            if row:
                patient_id = row[0]
            else:
                print("❌ 没有找到任何患者文件记录")
                return

        print(f"\n📋 检查患者: {patient_id}")

        # 1. 查看 bus_patient_files 表
        print("\n" + "=" * 100)
        print("1️⃣ bus_patient_files 表中的文件记录")
        print("=" * 100)

        result = session.execute(text("""
            SELECT
                id,
                file_uuid,
                file_name,
                conversation_id,
                created_at
            FROM bus_patient_files
            WHERE patient_id = :patient_id
                AND is_deleted = false
            ORDER BY created_at DESC
            LIMIT 10
        """), {'patient_id': patient_id})

        files_data = []
        for idx, row in enumerate(result, 1):
            file_record = {
                'id': row[0],
                'file_uuid': row[1],
                'file_name': row[2],
                'conversation_id': row[3],
                'created_at': row[4]
            }
            files_data.append(file_record)

            print(f"\n  文件 {idx}:")
            print(f"    id (主键): {row[0]}")
            print(f"    file_uuid: {row[1]}")
            print(f"    file_name: {row[2]}")
            print(f"    conversation_id: {row[3]}")
            print(f"    created_at: {row[4]}")

        if not files_data:
            print("  ⚠️ 没有找到文件记录")
            return

        # 2. 查看 bus_patient_structured_data 表
        print("\n" + "=" * 100)
        print("2️⃣ bus_patient_structured_data 表中的结构化数据")
        print("=" * 100)

        result = session.execute(text("""
            SELECT
                id,
                data_type,
                data_category,
                conversation_id,
                structuredcontent,
                created_at
            FROM bus_patient_structured_data
            WHERE patient_id = :patient_id
                AND is_deleted = false
            ORDER BY created_at DESC
        """), {'patient_id': patient_id})

        structured_data_list = []
        for idx, row in enumerate(result, 1):
            structured_record = {
                'id': row[0],
                'data_type': row[1],
                'data_category': row[2],
                'conversation_id': row[3],
                'structuredcontent': row[4],
                'created_at': row[5]
            }
            structured_data_list.append(structured_record)

            print(f"\n  记录 {idx}:")
            print(f"    id: {row[0]}")
            print(f"    data_type: {row[1]}")
            print(f"    data_category: {row[2]}")
            print(f"    conversation_id: {row[3]}")
            print(f"    created_at: {row[5]}")

        if not structured_data_list:
            print("  ⚠️ 没有找到结构化数据")
            return

        # 3. 检查 file_uuid 对应关系
        print("\n" + "=" * 100)
        print("3️⃣ file_uuid 对应关系检查")
        print("=" * 100)

        # 收集所有 file_uuid
        all_file_uuids = set(f['file_uuid'] for f in files_data)
        print(f"\n📁 bus_patient_files 表中的 file_uuid 总数: {len(all_file_uuids)}")
        print(f"   示例 file_uuid (前3个):")
        for uuid in list(all_file_uuids)[:3]:
            print(f"     - {uuid}")

        # 检查每个结构化数据中的 file_uuid
        for sd in structured_data_list:
            print(f"\n🔍 检查 {sd['data_type']} (data_category: {sd['data_category']}):")

            content = sd['structuredcontent']
            if not content:
                print("  ⚠️ structuredcontent 为空")
                continue

            # 转换为字符串搜索
            content_str = json.dumps(content, ensure_ascii=False)

            # 统计匹配的 file_uuid
            matched_uuids = []
            unmatched_uuids_in_content = []

            for file_uuid in all_file_uuids:
                if file_uuid in content_str:
                    matched_uuids.append(file_uuid)

            # 检查 structuredcontent 中是否有 file_uuid 字段
            if sd['data_type'] == 'timeline' and isinstance(content, dict):
                timeline = content.get('timeline', [])
                total_items = 0
                items_with_uuid = 0

                for entry in timeline:
                    data_blocks = entry.get('data_blocks', [])
                    for block in data_blocks:
                        items = block.get('items', [])
                        for item in items:
                            total_items += 1
                            item_file_uuid = item.get('file_uuid')
                            if item_file_uuid:
                                items_with_uuid += 1
                                if item_file_uuid not in all_file_uuids:
                                    unmatched_uuids_in_content.append(item_file_uuid)

                print(f"  timeline 统计:")
                print(f"    - 总 items: {total_items}")
                print(f"    - 包含 file_uuid 的 items: {items_with_uuid}")
                print(f"    - 匹配的 file_uuid: {len(matched_uuids)}")
                print(f"    - 不匹配的 file_uuid: {len(unmatched_uuids_in_content)}")

                if matched_uuids:
                    print(f"\n  ✅ 匹配的 file_uuid (前3个):")
                    for uuid in matched_uuids[:3]:
                        matching_file = next((f for f in files_data if f['file_uuid'] == uuid), None)
                        if matching_file:
                            print(f"    - {uuid} → {matching_file['file_name']}")

                if unmatched_uuids_in_content:
                    print(f"\n  ❌ structuredcontent 中有但 bus_patient_files 中没有的 file_uuid (前3个):")
                    for uuid in unmatched_uuids_in_content[:3]:
                        print(f"    - {uuid}")

            elif sd['data_type'] == 'journey' and isinstance(content, dict):
                # 检查 journey 类型
                timeline_journey = content.get('timeline_journey', [])
                print(f"  timeline_journey 条目数: {len(timeline_journey)}")

                # 搜索是否包含 file_uuid
                journey_str = json.dumps(timeline_journey, ensure_ascii=False)
                if 'file_uuid' in journey_str:
                    print(f"  ✅ 包含 file_uuid 字段")
                    print(f"  匹配的 file_uuid: {len(matched_uuids)}")
                else:
                    print(f"  ⚠️ 不包含 file_uuid 字段")

        # 4. 总结
        print("\n" + "=" * 100)
        print("4️⃣ 问题总结")
        print("=" * 100)

        # 查找不匹配的原因
        print("\n可能的原因:")
        print("  1. LLM 没有在生成的 JSON 中包含 file_uuid 字段")
        print("  2. LLM 生成了错误的 file_uuid 值")
        print("  3. file_uuid 在处理过程中被修改了")
        print("  4. structuredcontent 是在文件上传前生成的")

        # 建议
        print("\n💡 排查建议:")
        print("  1. 查看日志，检查传给 LLM 的文件信息中是否包含 file_uuid")
        print("  2. 查看 LLM 的原始输出，确认是否包含 file_uuid")
        print("  3. 检查 conversation_id 是否匹配")
        print("  4. 上传一个新文件，观察完整流程")

    finally:
        session.close()

if __name__ == "__main__":
    patient_id = sys.argv[1] if len(sys.argv) > 1 else None
    check_file_uuid_mapping(patient_id)
