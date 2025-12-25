#!/usr/bin/env python3
"""
患者数据更新测试脚本

测试场景：更新现有患者数据
- 需要先通过 test_flow_simple.py 创建患者，获取 patient_id
- 将 patient_id 填入下方的 PATIENT_ID 变量
- 然后运行本脚本补充新的文件和描述

使用说明：
1. 修改下方的 PATIENT_ID 为实际的患者ID
2. python test_patient_update.py
"""

import requests
import json
import sys
import base64
from pathlib import Path
from datetime import datetime
import pytz

# ========== 配置区域 ==========
API_BASE_URL = "http://182.254.240.153:9527"
CASE_DIR = "/home/ubuntu/data/patient_case/xuguoqiang/"

# ⚠️ 请在此填入要更新的患者ID（从 test_flow_simple.py 运行结果中获取）
PATIENT_ID = "685f1678-8260-41fa-8b7c-660c299bf44b"  # 👈 修改这里

# 文件配置
MAX_FILES = 3  # 读取后3个文件

# 调试配置
DEBUG_PRINT_RAW_API = False  # 设置为 True 时打印原始API返回
# ================================


def get_beijing_time():
    """获取当前北京时间"""
    beijing_tz = pytz.timezone('Asia/Shanghai')
    return datetime.now(beijing_tz).strftime('%Y-%m-%d %H:%M:%S')


def load_last_n_files(max_files=3):
    """
    从服务器目录读取后N个文件并转换为base64

    Args:
        max_files: 读取最后N个文件
    """
    print(f"\n📂 正在从目录读取文件: {CASE_DIR}")

    case_path = Path(CASE_DIR)

    if not case_path.exists():
        print(f"❌ 目录不存在: {CASE_DIR}")
        sys.exit(1)

    # 收集所有文件
    all_files = []
    supported_extensions = ['.pdf', '.jpg', '.jpeg', '.png']

    for file_path in case_path.rglob('*'):
        if file_path.is_file() and file_path.suffix.lower() in supported_extensions:
            all_files.append(file_path)

    if not all_files:
        print(f"❌ 目录中未找到任何支持的文件")
        sys.exit(1)

    # 按文件名排序（确保顺序一致）
    all_files.sort(key=lambda x: x.name)

    # 取最后N个文件
    files_to_upload = all_files[-max_files:] if len(all_files) >= max_files else all_files

    print(f"📊 目录中共有 {len(all_files)} 个文件，选择最后 {len(files_to_upload)} 个文件")
    print(f"正在读取文件并转换为 base64...\n")

    files = []
    for file_path in files_to_upload:
        try:
            with open(file_path, 'rb') as f:
                file_content = f.read()

            files.append({
                'file_name': file_path.name,
                'file_content': base64.b64encode(file_content).decode('utf-8')
            })

            file_size_mb = len(file_content) / (1024 * 1024)
            print(f"  ✓ {file_path.name} ({file_size_mb:.2f} MB)")

        except Exception as e:
            print(f"  ✗ 无法读取 {file_path.name}: {e}")

    if not files:
        print(f"\n❌ 未成功读取任何文件")
        sys.exit(1)

    print(f"\n✅ 已准备 {len(files)} 个文件用于上传\n")
    return files


def update_patient(patient_id, files):
    """更新现有患者数据"""
    print(f"\n{'='*80}")
    print(f"🔄 更新患者数据")
    print(f"{'='*80}\n")

    payload = {
        "patient_id": patient_id,
        "patient_description": "补充最新复查报告和影像资料",
        "consultation_purpose": "跟踪治疗效果，调整治疗方案",
        "files": files
    }

    print(f"📤 发送请求到: {API_BASE_URL}/api/patient_data/process_patient_data_smart")
    print(f"🆔 患者ID: {patient_id}")
    print(f"📊 补充描述: {payload['patient_description']}")
    print(f"📁 文件数量: {len(files)}")
    print(f"⏰ 时间: {get_beijing_time()}")

    try:
        response = requests.post(
            f"{API_BASE_URL}/api/patient_data/process_patient_data_smart",
            json=payload,
            stream=True,
            timeout=600
        )

        if response.status_code != 200:
            print(f"\n❌ 请求失败: HTTP {response.status_code}")
            print(f"响应: {response.text}")
            return False

        print(f"\n✅ 连接成功，开始接收流式数据...\n")
        print(f"{'='*80}")

        task_id = None
        update_success = False
        ai_response_started = False  # 标记是否已开始AI回复

        for line in response.iter_lines():
            if line:
                line_str = line.decode('utf-8')

                # 调试：打印原始API返回
                if DEBUG_PRINT_RAW_API:
                    print(f"📥 原始API返回: {line_str}")

                if line_str.startswith('data: '):
                    data_str = line_str[6:]
                    try:
                        data = json.loads(data_str)

                        # 保存task_id
                        if 'task_id' in data and not task_id:
                            task_id = data['task_id']
                            print(f"📌 任务ID: {task_id}\n")

                        # 显示进度
                        if data.get('status') in ['started', 'processing']:
                            progress = data.get('progress', 0)
                            message = data.get('message', '')
                            stage = data.get('stage', '')
                            stage_info = f' ({stage})' if stage else ''
                            print(f"[{progress:3d}%] {message}{stage_info}")

                        # 显示流式AI回复
                        elif data.get('status') == 'streaming_response':
                            chunk_content = data.get('message', '')
                            is_chunk = data.get('is_chunk', False)
                            stage = data.get('stage', '')

                            if stage == 'confirmation' and chunk_content:
                                # 第一次输出时显示标题
                                if not ai_response_started:
                                    print(f"\n{'='*80}")
                                    print(f"🤖 AI确认消息：")
                                    print(f"{'='*80}")
                                    ai_response_started = True

                                # 实时打印AI回复（不换行）
                                print(chunk_content, end='', flush=True)
                            elif stage == 'confirmation_complete':
                                # 回复结束，换行
                                if ai_response_started:
                                    print()  # 换行
                                    print(f"{'='*80}\n")

                        # 完成
                        elif data.get('status') == 'completed':
                            is_update = data.get('is_update', False)
                            result = data.get('result', {})

                            print(f"\n{'='*80}")
                            print(f"✅ 患者数据更新成功!")
                            print(f"{'='*80}")
                            print(f"  患者ID: {result.get('patient_id')}")
                            print(f"  会话ID: {result.get('conversation_id')}")
                            print(f"  新增文件: {result.get('uploaded_files_count')} 个")
                            print(f"  文件IDs: {', '.join(result.get('uploaded_file_ids', []))}")
                            print(f"  更新模式: {'是' if is_update else '否'}")
                            print(f"  耗时: {data.get('duration', 0):.2f} 秒")
                            print(f"{'='*80}\n")

                            update_success = True

                        # 错误
                        elif data.get('status') == 'error':
                            print(f"\n{'='*80}")
                            print(f"❌ 处理失败")
                            print(f"{'='*80}")
                            print(f"  错误信息: {data.get('message')}")
                            print(f"  错误详情: {data.get('error')}")
                            print(f"{'='*80}\n")
                            return False

                    except json.JSONDecodeError as e:
                        print(f"⚠️  JSON解析失败: {e}")

        return update_success

    except requests.exceptions.Timeout:
        print(f"\n❌ 请求超时（超过10分钟）")
        return False
    except Exception as e:
        print(f"\n❌ 请求异常: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主函数"""
    print(f"\n{'='*80}")
    print(f"🧪 患者数据更新测试")
    print(f"{'='*80}\n")

    # 检查是否配置了 patient_id
    if PATIENT_ID == "patient_xxx_xxx_xxx":
        print(f"❌ 请先配置 PATIENT_ID")
        print(f"\n配置步骤:")
        print(f"  1. 运行 test_flow_simple.py 创建患者")
        print(f"  2. 从输出中复制 patient_id")
        print(f"  3. 编辑本文件，将 PATIENT_ID 修改为实际的患者ID")
        print(f"  4. 重新运行本脚本")
        print(f"\n示例:")
        print(f"  PATIENT_ID = \"patient_abc123xyz\"  # 修改这一行\n")
        sys.exit(1)

    print(f"🆔 患者ID: {PATIENT_ID}")
    print(f"🌐 API地址: {API_BASE_URL}")
    print(f"📂 数据目录: {CASE_DIR}")
    print(f"⏰ 当前时间: {get_beijing_time()}")

    # 加载后3个文件
    files = load_last_n_files(max_files=MAX_FILES)

    # 更新患者数据
    success = update_patient(PATIENT_ID, files)

    if success:
        print(f"\n🎉 患者数据更新测试完成!")
        print(f"\n💡 提示: 可以继续使用相同的 patient_id 多次更新")
    else:
        print(f"\n⚠️  患者数据更新失败")
        sys.exit(1)


if __name__ == "__main__":
    main()
