"""
简单的患者 file_uuid 检查（使用 psycopg2）
"""
import psycopg2
import json

patient_id = "3ae4e400-f8b2-4c9b-b465-9637e06eabcc"

conn = psycopg2.connect(
    host='112.124.15.49',
    port=5432,
    user='mdtadmin',
    password='mdtadmin@2025',
    database='db_mdt'
)
cur = conn.cursor()

print("=" * 100)
print(f"🔍 检查患者: {patient_id}")
print("=" * 100)

# 1. 查看文件记录
print("\n" + "=" * 100)
print("1️⃣ bus_patient_files 表中的文件")
print("=" * 100)

cur.execute("""
    SELECT
        file_uuid,
        file_name,
        created_at
    FROM bus_patient_files
    WHERE patient_id = %s
        AND is_deleted = false
    ORDER BY created_at DESC
""", (patient_id,))

files = cur.fetchall()
print(f"\n共 {len(files)} 个文件:")

file_uuids = set()
for idx, (uuid, name, created) in enumerate(files, 1):
    print(f"\n  文件 {idx}:")
    print(f"    file_uuid: {uuid}")
    print(f"    file_name: {name}")
    print(f"    created:   {created}")
    file_uuids.add(uuid)

if not files:
    print("  ⚠️ 没有找到文件")
    conn.close()
    exit(0)

# 2. 查看结构化数据
print("\n" + "=" * 100)
print("2️⃣ bus_patient_structured_data 表")
print("=" * 100)

cur.execute("""
    SELECT
        data_type,
        data_category,
        structuredcontent,
        created_at
    FROM bus_patient_structured_data
    WHERE patient_id = %s
        AND is_deleted = false
    ORDER BY created_at DESC
""", (patient_id,))

structured_data = cur.fetchall()
print(f"\n共 {len(structured_data)} 条结构化数据:")

for idx, (dtype, category, content, created) in enumerate(structured_data, 1):
    print(f"\n  记录 {idx}:")
    print(f"    data_type:     {dtype}")
    print(f"    data_category: {category}")
    print(f"    created:       {created}")

    if not content:
        print(f"    ⚠️ content 为空")
        continue

    # 检查是否包含 file_uuid
    if dtype == 'timeline':
        timeline = content.get('timeline', [])
        print(f"    timeline 条目: {len(timeline)}")

        total_items = 0
        items_with_uuid = 0
        matched = 0

        for entry in timeline:
            for block in entry.get('data_blocks', []):
                for item in block.get('items', []):
                    total_items += 1
                    item_uuid = item.get('file_uuid')
                    if item_uuid:
                        items_with_uuid += 1
                        if item_uuid in file_uuids:
                            matched += 1

        print(f"    总 items:      {total_items}")
        print(f"    有 file_uuid:  {items_with_uuid}")
        print(f"    匹配的:        {matched}")

        if matched == 0 and items_with_uuid > 0:
            print(f"    ❌ 有 file_uuid 但都不匹配！")
        elif matched < items_with_uuid:
            print(f"    ⚠️ 部分匹配 ({matched}/{items_with_uuid})")
        elif matched > 0:
            print(f"    ✅ 全部匹配")

# 3. 详细对比
print("\n" + "=" * 100)
print("3️⃣ 详细 file_uuid 检查")
print("=" * 100)

# 获取第一个 file_uuid 作为示例
if file_uuids:
    first_uuid = list(file_uuids)[0]
    print(f"\n检查示例 file_uuid: {first_uuid}")

    for dtype, category, content, created in structured_data:
        if content:
            content_str = json.dumps(content)
            if first_uuid in content_str:
                print(f"  ✅ 在 {dtype} ({category}) 中找到")
            else:
                print(f"  ❌ 在 {dtype} ({category}) 中未找到")

# 4. 提取 structuredcontent 中的所有 file_uuid
print("\n" + "=" * 100)
print("4️⃣ structuredcontent 中的 file_uuid")
print("=" * 100)

all_uuids_in_content = set()
for dtype, category, content, created in structured_data:
    if content and dtype == 'timeline':
        timeline = content.get('timeline', [])
        for entry in timeline:
            for block in entry.get('data_blocks', []):
                for item in block.get('items', []):
                    item_uuid = item.get('file_uuid')
                    if item_uuid:
                        all_uuids_in_content.add(item_uuid)

print(f"\nbus_patient_files 中的 file_uuid: {len(file_uuids)} 个")
print(f"structuredcontent 中的 file_uuid: {len(all_uuids_in_content)} 个")

if all_uuids_in_content:
    print(f"\nstructuredcontent 中的 UUID 示例 (前3个):")
    for uuid in list(all_uuids_in_content)[:3]:
        if uuid in file_uuids:
            print(f"  ✅ {uuid} (匹配)")
        else:
            print(f"  ❌ {uuid} (不匹配)")

# 总结
print("\n" + "=" * 100)
print("5️⃣ 诊断结果")
print("=" * 100)

matched_uuids = file_uuids & all_uuids_in_content
missing_in_content = file_uuids - all_uuids_in_content
extra_in_content = all_uuids_in_content - file_uuids

print(f"\n匹配的 UUID:     {len(matched_uuids)}")
print(f"缺失的 UUID:     {len(missing_in_content)} (在 files 表中但不在 content 中)")
print(f"多余的 UUID:     {len(extra_in_content)} (在 content 中但不在 files 表中)")

if len(matched_uuids) == len(file_uuids) == len(all_uuids_in_content):
    print(f"\n✅ 完美匹配！所有 file_uuid 都对应上了。")
elif len(matched_uuids) > 0:
    print(f"\n⚠️ 部分匹配")
    if missing_in_content:
        print(f"\n缺失的 UUID (前3个):")
        for uuid in list(missing_in_content)[:3]:
            print(f"  - {uuid}")
    if extra_in_content:
        print(f"\n多余的 UUID (前3个):")
        for uuid in list(extra_in_content)[:3]:
            print(f"  - {uuid}")
else:
    print(f"\n❌ 完全不匹配！")
    print(f"\n可能原因:")
    print(f"  1. LLM 没有输出 file_uuid")
    print(f"  2. LLM 生成了不同的 UUID")
    print(f"  3. 这是修复前的旧数据")

conn.close()
