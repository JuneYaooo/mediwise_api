"""
检查特定患者的 file_uuid 对应关系
"""
import json
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# 数据库连接
DATABASE_URL = "postgresql://mdtadmin:mdtadmin@2025@112.124.15.49:5432/db_mdt"
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

patient_id = "3ae4e400-f8b2-4c9b-b465-9637e06eabcc"

session = Session()

try:
    print("=" * 100)
    print(f"🔍 检查患者: {patient_id}")
    print("=" * 100)

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
            created_at,
            upload_timestamp
        FROM bus_patient_files
        WHERE patient_id = :patient_id
            AND is_deleted = false
        ORDER BY created_at DESC
    """), {'patient_id': patient_id})

    files_data = []
    print(f"\n共找到 {result.rowcount if hasattr(result, 'rowcount') else '?'} 个文件:")

    for idx, row in enumerate(result, 1):
        file_record = {
            'id': row[0],
            'file_uuid': row[1],
            'file_name': row[2],
            'conversation_id': row[3],
            'created_at': row[4],
            'upload_timestamp': row[5]
        }
        files_data.append(file_record)

        print(f"\n  📄 文件 {idx}:")
        print(f"    id (主键):        {row[0]}")
        print(f"    file_uuid:        {row[1]}")
        print(f"    file_name:        {row[2]}")
        print(f"    conversation_id:  {row[3]}")
        print(f"    created_at:       {row[4]}")
        print(f"    upload_timestamp: {row[5]}")

    if not files_data:
        print("  ⚠️ 没有找到文件记录")
        exit(0)

    # 收集所有 file_uuid
    all_file_uuids = {f['file_uuid'] for f in files_data}
    print(f"\n📊 统计: 共 {len(files_data)} 个文件, {len(all_file_uuids)} 个唯一 file_uuid")

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

        print(f"\n  📊 记录 {idx}:")
        print(f"    id:              {row[0]}")
        print(f"    data_type:       {row[1]}")
        print(f"    data_category:   {row[2]}")
        print(f"    conversation_id: {row[3]}")
        print(f"    created_at:      {row[5]}")
        print(f"    content length:  {len(str(row[4])) if row[4] else 0} 字符")

    if not structured_data_list:
        print("  ⚠️ 没有找到结构化数据")
        exit(0)

    # 3. 详细检查 file_uuid 对应关系
    print("\n" + "=" * 100)
    print("3️⃣ file_uuid 对应关系详细检查")
    print("=" * 100)

    for sd in structured_data_list:
        print(f"\n🔍 检查 {sd['data_type']} (category: {sd['data_category']}):")

        content = sd['structuredcontent']
        if not content:
            print("  ⚠️ structuredcontent 为空")
            continue

        # 检查 timeline 类型
        if sd['data_type'] == 'timeline' and isinstance(content, dict):
            timeline = content.get('timeline', [])
            print(f"  timeline 条目数: {len(timeline)}")

            total_items = 0
            items_with_uuid = 0
            matched_uuids = []
            unmatched_uuids_in_content = []
            all_uuids_in_content = set()

            for entry in timeline:
                entry_date = entry.get('date', '未知日期')
                data_blocks = entry.get('data_blocks', [])

                for block in data_blocks:
                    block_category = block.get('category', '未知分类')
                    items = block.get('items', [])

                    for item in items:
                        total_items += 1
                        item_file_uuid = item.get('file_uuid')

                        if item_file_uuid:
                            items_with_uuid += 1
                            all_uuids_in_content.add(item_file_uuid)

                            if item_file_uuid in all_file_uuids:
                                matched_uuids.append({
                                    'uuid': item_file_uuid,
                                    'date': entry_date,
                                    'category': block_category,
                                    'content': item.get('content', '')[:50]
                                })
                            else:
                                unmatched_uuids_in_content.append({
                                    'uuid': item_file_uuid,
                                    'date': entry_date,
                                    'category': block_category
                                })

            print(f"\n  📊 统计:")
            print(f"    总 items:              {total_items}")
            print(f"    包含 file_uuid 的:     {items_with_uuid} ({items_with_uuid/total_items*100:.1f}% if total_items > 0 else 0)")
            print(f"    唯一 file_uuid:        {len(all_uuids_in_content)}")
            print(f"    匹配的:                {len(matched_uuids)}")
            print(f"    不匹配的:              {len(unmatched_uuids_in_content)}")

            if matched_uuids:
                print(f"\n  ✅ 匹配的 file_uuid (前5个):")
                for match in matched_uuids[:5]:
                    matching_file = next((f for f in files_data if f['file_uuid'] == match['uuid']), None)
                    if matching_file:
                        print(f"    - {match['uuid']}")
                        print(f"      文件: {matching_file['file_name']}")
                        print(f"      日期: {match['date']}, 分类: {match['category']}")
                        print(f"      内容: {match['content']}...")

            if unmatched_uuids_in_content:
                print(f"\n  ❌ 不匹配的 file_uuid (在 structuredcontent 中但不在 bus_patient_files 中):")
                for unmatch in unmatched_uuids_in_content[:5]:
                    print(f"    - {unmatch['uuid']}")
                    print(f"      日期: {unmatch['date']}, 分类: {unmatch['category']}")

            # 检查反向：bus_patient_files 中有但 structuredcontent 中没有的
            missing_in_content = all_file_uuids - all_uuids_in_content
            if missing_in_content:
                print(f"\n  ⚠️ 在 bus_patient_files 中但不在 structuredcontent 中的 file_uuid:")
                for uuid in missing_in_content:
                    matching_file = next((f for f in files_data if f['file_uuid'] == uuid), None)
                    if matching_file:
                        print(f"    - {uuid}")
                        print(f"      文件: {matching_file['file_name']}")
                        print(f"      创建时间: {matching_file['created_at']}")

        elif sd['data_type'] == 'journey':
            # 检查 journey 类型
            content_str = json.dumps(content, ensure_ascii=False)

            matched_count = 0
            for uuid in all_file_uuids:
                if uuid in content_str:
                    matched_count += 1

            print(f"  匹配的 file_uuid: {matched_count}/{len(all_file_uuids)}")

    # 4. 总结
    print("\n" + "=" * 100)
    print("4️⃣ 诊断结果")
    print("=" * 100)

    if matched_uuids and len(matched_uuids) == len(all_file_uuids):
        print("\n✅ file_uuid 对应关系正常！")
        print(f"   所有 {len(all_file_uuids)} 个文件的 UUID 都在 structuredcontent 中找到了。")
    elif matched_uuids and len(matched_uuids) < len(all_file_uuids):
        print(f"\n⚠️ 部分 file_uuid 对应关系正常")
        print(f"   {len(matched_uuids)}/{len(all_file_uuids)} 个文件的 UUID 在 structuredcontent 中")
        print(f"\n   可能原因:")
        print(f"   - 某些文件还未处理完成")
        print(f"   - LLM 没有为某些数据生成 file_uuid")
    else:
        print(f"\n❌ file_uuid 对应关系异常！")
        print(f"   没有找到任何匹配的 file_uuid")
        print(f"\n   可能原因:")
        print(f"   1. LLM 完全没有输出 file_uuid 字段")
        print(f"   2. LLM 生成了完全不同的 UUID")
        print(f"   3. 数据还在处理中")

    # 检查时间差异
    if files_data and structured_data_list:
        latest_file_time = max(f['created_at'] for f in files_data)
        latest_data_time = max(sd['created_at'] for sd in structured_data_list)

        print(f"\n⏰ 时间分析:")
        print(f"   最新文件上传时间:     {latest_file_time}")
        print(f"   最新结构化数据时间:   {latest_data_time}")

        if latest_file_time > latest_data_time:
            time_diff = latest_file_time - latest_data_time
            print(f"   ⚠️ 文件比结构化数据新 {time_diff}")
            print(f"      可能还在处理中...")

finally:
    session.close()
