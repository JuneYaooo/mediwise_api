"""
调试脚本：检查 file_uuid 在两个表中的对应关系
"""
from app.db.database import SessionLocal
from app.models.bus_models import PatientFile, PatientStructuredData
from sqlalchemy import func
import json

db = SessionLocal()

try:
    print("=" * 80)
    print("检查 bus_patient_files 中的 file_uuid")
    print("=" * 80)

    # 获取最近的一个患者
    latest_file = db.query(PatientFile).filter(
        PatientFile.is_deleted == False
    ).order_by(PatientFile.created_at.desc()).first()

    if not latest_file:
        print("❌ 没有找到任何文件记录")
        exit(1)

    patient_id = latest_file.patient_id
    print(f"\n📊 患者ID: {patient_id}")
    print(f"最新文件:")
    print(f"  - id (主键): {latest_file.id}")
    print(f"  - file_uuid: {latest_file.file_uuid}")
    print(f"  - file_name: {latest_file.file_name}")
    print(f"  - conversation_id: {latest_file.conversation_id}")

    # 获取该患者的所有文件
    files = db.query(PatientFile).filter(
        PatientFile.patient_id == patient_id,
        PatientFile.is_deleted == False
    ).all()

    print(f"\n该患者共有 {len(files)} 个文件:")
    file_uuid_map = {}
    for f in files[:5]:  # 只显示前5个
        print(f"  - file_uuid: {f.file_uuid}, file_name: {f.file_name}")
        file_uuid_map[f.file_uuid] = f.file_name

    # 获取该患者的结构化数据
    print("\n" + "=" * 80)
    print("检查 bus_patient_structured_data 中的 structuredcontent")
    print("=" * 80)

    structured_data = db.query(PatientStructuredData).filter(
        PatientStructuredData.patient_id == patient_id,
        PatientStructuredData.is_deleted == False
    ).all()

    print(f"\n该患者共有 {len(structured_data)} 条结构化数据:")

    for sd in structured_data:
        print(f"\n📄 data_type: {sd.data_type}, data_category: {sd.data_category}")

        content = sd.structuredcontent
        if not content or not isinstance(content, dict):
            print("  ⚠️ structuredcontent 为空或不是字典")
            continue

        # 检查 timeline 类型
        if sd.data_type == 'timeline':
            timeline = content.get('timeline', [])
            print(f"  包含 {len(timeline)} 个时间轴条目")

            # 统计包含 file_uuid 的 items
            total_items = 0
            items_with_uuid = 0
            matched_uuids = []
            unmatched_uuids = []

            for entry in timeline:
                data_blocks = entry.get('data_blocks', [])
                for block in data_blocks:
                    items = block.get('items', [])
                    for item in items:
                        total_items += 1
                        item_file_uuid = item.get('file_uuid')
                        if item_file_uuid:
                            items_with_uuid += 1
                            # 检查是否在 bus_patient_files 中存在
                            if item_file_uuid in file_uuid_map:
                                matched_uuids.append(item_file_uuid)
                            else:
                                unmatched_uuids.append(item_file_uuid)

            print(f"  统计:")
            print(f"    - 总 items: {total_items}")
            print(f"    - 包含 file_uuid 的 items: {items_with_uuid} ({items_with_uuid/total_items*100:.1f}%)")
            print(f"    - 匹配的 file_uuid: {len(matched_uuids)}")
            print(f"    - 不匹配的 file_uuid: {len(unmatched_uuids)}")

            if matched_uuids:
                print(f"\n  ✅ 匹配的 file_uuid 示例 (前3个):")
                for uuid in matched_uuids[:3]:
                    print(f"    - {uuid} → {file_uuid_map[uuid]}")

            if unmatched_uuids:
                print(f"\n  ❌ 不匹配的 file_uuid 示例 (前3个):")
                for uuid in unmatched_uuids[:3]:
                    print(f"    - {uuid} (在 bus_patient_files 中未找到)")

        # 检查 journey 类型
        elif sd.data_type == 'journey':
            timeline_journey = content.get('timeline_journey', [])
            print(f"  包含 {len(timeline_journey)} 个旅程事件")

            # 检查是否有文件引用
            has_file_ref = any('file' in str(event).lower() for event in timeline_journey)
            print(f"  是否包含文件引用: {'是' if has_file_ref else '否'}")

    print("\n" + "=" * 80)
    print("结论")
    print("=" * 80)

    if items_with_uuid == 0 and total_items > 0:
        print("\n❌ 问题确认：structuredcontent 中的 items 完全没有 file_uuid 字段")
        print("   原因：LLM 在生成结构化数据时忽略了 file_uuid 字段")
        print("   解决方案：")
        print("   1. 检查提示词是否明确要求 LLM 输出 file_uuid")
        print("   2. 检查 LLM 的输出是否被正确解析")
        print("   3. 可能需要在后处理阶段补充 file_uuid")
    elif items_with_uuid < total_items:
        print(f"\n⚠️ 部分 items 缺少 file_uuid ({items_with_uuid}/{total_items})")
        print("   原因：某些数据项没有明确的文件来源（如从患者描述中提取的信息）")
    else:
        print("\n✅ 所有 items 都包含 file_uuid")

    if unmatched_uuids:
        print(f"\n❌ 发现 {len(unmatched_uuids)} 个不匹配的 file_uuid")
        print("   原因可能：")
        print("   1. file_uuid 的值在不同阶段不一致")
        print("   2. bus_patient_files 中的 file_uuid 字段存储的是其他值")
        print("   3. LLM 生成了错误的 file_uuid")

finally:
    db.close()
