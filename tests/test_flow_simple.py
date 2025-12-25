#!/usr/bin/env python3
"""
混合智能接口测试脚本

测试场景：客户端中途断开（后台继续执行）
- 客户端发起请求，接收几条进度消息
- 主动断开连接（模拟用户关闭浏览器）
- 后台任务继续执行
- 稍后通过task_id查询任务状态和结果

使用说明：
调用正式接口，当前版本暂无需认证
"""

import requests
import json
import sys
import base64
from pathlib import Path
from datetime import datetime
import pytz
import time

# 配置
API_BASE_URL = "http://182.254.240.153:9527" #"http://localhost:9527"
CASE_DIR = "/home/ubuntu/data/patient_case/xuguoqiang/"


def get_beijing_time():
    """获取当前北京时间"""
    beijing_tz = pytz.timezone('Asia/Shanghai')
    return datetime.now(beijing_tz).strftime('%Y-%m-%d %H:%M:%S')


def load_files_from_directory(max_files=5):
    """从服务器目录读取前N个文件并转换为base64"""
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

    # 取前N个文件
    files_to_upload = all_files[:max_files] if len(all_files) >= max_files else all_files

    print(f"📊 目录中共有 {len(all_files)} 个文件，选择前 {len(files_to_upload)} 个文件")
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


def test_scenario_1_file_upload_progress(files):
    """
    场景1：测试文件上传进度实时反馈
    验证前端能够实时看到每个文件的接收状态
    """
    print("=" * 80)
    print("📥 测试场景1：文件上传进度实时反馈")
    print("=" * 80)

    headers = {
        "Content-Type": "application/json"
    }

    payload = {
        "patient_description": "测试文件上传进度反馈功能",
        "consultation_purpose": "验证实时进度功能",
        "files": files
    }

    print(f"\n📤 发送请求... ({get_beijing_time()})")
    print(f"📊 上传文件数: {len(files)}\n")

    try:
        response = requests.post(
            f"{API_BASE_URL}/api/patient_data/process_patient_data_smart",
            headers=headers,
            json=payload,
            stream=True,
            timeout=1200
        )

        if response.status_code != 200:
            print(f"❌ 请求失败: {response.text}")
            return None

        print(f"✅ 连接成功，开始接收流式响应...\n", flush=True)
        print("-" * 80, flush=True)

        task_id = None
        event_count = 0
        file_upload_events = []
        upload_complete = False

        buffer = ""
        for chunk in response.iter_content(chunk_size=1, decode_unicode=True):
            if chunk:
                buffer += chunk

                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    line = line.strip()

                    if line and line.startswith('data: '):
                        event_count += 1

                        try:
                            data = json.loads(line[6:])

                            # 保存task_id
                            if 'task_id' in data and not task_id:
                                task_id = data['task_id']
                                print(f"📋 任务ID: {task_id}\n", flush=True)

                            stage = data.get('stage', '')
                            message = data.get('message', '')
                            progress = data.get('progress', 0)

                            # 重点关注文件上传阶段
                            if stage == 'file_upload':
                                file_info = data.get('file_info', {})
                                current = file_info.get('current', 0)
                                total = file_info.get('total', 0)
                                file_name = file_info.get('file_name', '')

                                print(f"[{progress:3d}%] {message}", flush=True)
                                file_upload_events.append(data)

                            # 上传完成标记
                            elif 'upload_complete' in stage or '所有文件接收完成' in message:
                                print(f"\n{'=' * 80}", flush=True)
                                print(f"[{progress:3d}%] ✅ {message}", flush=True)
                                print(f"{'=' * 80}\n", flush=True)
                                upload_complete = True

                                # 收到文件上传完成消息后断开连接
                                print(f"🔌 {get_beijing_time()} | 文件已全部接收，主动断开连接", flush=True)
                                print(f"   💡 后台将继续处理数据...\n", flush=True)
                                response.close()
                                break

                            # 其他重要阶段
                            elif stage in ['received']:
                                print(f"[{progress:3d}%] {message}", flush=True)

                        except json.JSONDecodeError as e:
                            print(f"⚠️  JSON 解析错误: {e}", flush=True)

                if upload_complete:
                    break

        print("-" * 80, flush=True)
        print(f"\n📊 文件上传进度统计:", flush=True)
        print(f"   - 总消息数: {event_count}", flush=True)
        print(f"   - 文件上传进度消息数: {len(file_upload_events)}", flush=True)
        print(f"   - 预期消息数: {len(files) * 2 + 1} (每个文件2条 + 完成1条)", flush=True)

        if len(file_upload_events) >= len(files):
            print(f"   ✅ 成功接收所有文件的上传进度\n", flush=True)
        else:
            print(f"   ⚠️  文件上传进度消息不足\n", flush=True)

        return task_id

    except Exception as e:
        print(f"❌ 异常: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_scenario_2_disconnect(files):
    """
    场景2：客户端接收几条消息后断开，然后查询任务状态（无需认证）
    """
    print("=" * 80)
    print("📱 测试场景2：客户端中途断开（后台继续执行）")
    print("=" * 80)

    headers = {
        "Content-Type": "application/json"
    }

    payload = {
        "patient_description": "患者李云山的完整病例资料，包含多次检查报告和影像资料",
        "consultation_purpose": "多学科会诊，制定综合治疗方案，评估预后情况",
        "files": files
    }

    print(f"\n📤 发送请求... ({get_beijing_time()})\n")

    try:
        response = requests.post(
            f"{API_BASE_URL}/api/patient_data/process_patient_data_smart",
            headers=headers,
            json=payload,
            stream=True,
            timeout=1200
        )

        if response.status_code != 200:
            print(f"❌ 请求失败: {response.text}")
            return None

        print(f"✅ 连接成功，开始接收流式响应...\n", flush=True)
        print("-" * 80, flush=True)

        task_id = None
        event_count = 0
        max_events = 5  # 只接收5条消息就断开

        buffer = ""
        for chunk in response.iter_content(chunk_size=1, decode_unicode=True):
            if chunk:
                buffer += chunk

                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    line = line.strip()

                    if line and line.startswith('data: '):
                        event_count += 1

                        # 打印原始数据
                        print(f"\n📦 [{event_count}] 原始数据:", flush=True)
                        print(line, flush=True)
                        print("-" * 40, flush=True)

                        try:
                            data = json.loads(line[6:])

                            # 保存task_id
                            if 'task_id' in data and not task_id:
                                task_id = data['task_id']

                            # 接收到指定数量的消息后主动断开
                            if event_count >= max_events:
                                print(f"\n🔌 [{event_count}] {get_beijing_time()} | 主动断开连接（模拟用户关闭浏览器）", flush=True)
                                print(f"   💡 后台任务应该继续执行...\n", flush=True)
                                response.close()
                                break

                        except json.JSONDecodeError as e:
                            print(f"⚠️  JSON 解析错误: {e}", flush=True)

                if event_count >= max_events:
                    break

        print("-" * 80)

        if not task_id:
            print("❌ 未能获取task_id")
            return None

        # 等待一段时间，然后查询任务状态
        print(f"\n⏰ 等待10秒，模拟用户稍后重新打开...\n", flush=True)
        time.sleep(10)

        # 查询任务状态
        print(f"🔍 查询任务状态... ({get_beijing_time()})\n", flush=True)

        for i in range(20):  # 最多查询20次
            status_response = requests.get(
                f"{API_BASE_URL}/api/patient_data/task_status/{task_id}"
            )

            if status_response.status_code == 200:
                status_data = status_response.json()
                current_status = status_data.get('status')
                current_progress = status_data.get('progress', 0)
                current_message = status_data.get('message', '')

                print(f"📊 [{i+1}] {get_beijing_time()} | 状态: {current_status} | 进度: {current_progress}% | {current_message}", flush=True)

                if current_status == 'completed':
                    print(f"\n✅ 任务完成！", flush=True)
                    result = status_data.get('result', {})
                    patient_id = result.get('patient_id', 'N/A')
                    conversation_id = result.get('conversation_id', 'N/A')
                    print(f"   - 患者ID: {patient_id}")
                    print(f"   - 会话ID: {conversation_id}")
                    print(f"   - 处理文件数: {result.get('uploaded_files_count', 0)}")
                    print(f"   📊 后台任务成功完成，即使客户端断开了！\n")

                    # 打印醒目的 patient_id，方便复制
                    print("=" * 80)
                    print("🆔 患者ID（用于生成PPT）:")
                    print("-" * 80)
                    print(f"   {patient_id}")
                    print("-" * 80)
                    print("💡 使用以下命令生成PPT:")
                    print(f"   python test_ppt_api.py {patient_id} generate")
                    print("=" * 80)
                    print()

                    return {'patient_id': patient_id, 'conversation_id': conversation_id}

                elif current_status == 'error':
                    print(f"\n❌ 任务失败: {status_data.get('error', 'Unknown error')}\n")
                    return None

            time.sleep(5)  # 每5秒查询一次

        print(f"\n⚠️  任务仍在处理中，已查询{20}次")
        return task_id

    except Exception as e:
        print(f"❌ 异常: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    """主测试流程"""
    print("\n" + "=" * 80)
    print("🧪 混合智能接口测试")
    print("=" * 80)
    print(f"API 地址: {API_BASE_URL}")
    print(f"病例目录: {CASE_DIR}")
    print(f"认证方式: 暂无需认证\n")

    print("💡 提示：")
    print("   场景1: 测试文件上传进度实时反馈")
    print("   场景2: 测试客户端断开后台继续执行")
    print("   PPT 生成请使用: python test_ppt_api.py <patient_id> generate")
    print()

    # 询问用户选择测试场景
    print("请选择测试场景：")
    print("  1 - 文件上传进度测试（验证实时进度反馈）")
    print("  2 - 断开重连测试（验证后台继续执行）")
    print("  3 - 运行全部测试")

    choice = input("\n请输入选项 (1/2/3，默认2): ").strip() or "2"

    # 加载文件
    files = load_files_from_directory(max_files=5)

    if choice == "1":
        # 场景1：文件上传进度测试
        print("\n" + "=" * 80)
        print("运行场景1：文件上传进度测试")
        print("=" * 80 + "\n")
        task_id = test_scenario_1_file_upload_progress(files)

        if task_id:
            # 等待并查询最终结果
            print(f"\n⏰ 等待后台处理完成...\n", flush=True)
            time.sleep(10)

            for i in range(20):
                status_response = requests.get(
                    f"{API_BASE_URL}/api/patient_data/task_status/{task_id}"
                )

                if status_response.status_code == 200:
                    status_data = status_response.json()
                    current_status = status_data.get('status')
                    current_progress = status_data.get('progress', 0)
                    current_message = status_data.get('message', '')

                    print(f"📊 [{i+1}] {get_beijing_time()} | 状态: {current_status} | 进度: {current_progress}% | {current_message}", flush=True)

                    if current_status == 'completed':
                        result = status_data.get('result', {})
                        patient_id = result.get('patient_id', 'N/A')
                        print(f"\n✅ 任务完成！患者ID: {patient_id}\n", flush=True)
                        break
                    elif current_status == 'error':
                        print(f"\n❌ 任务失败\n", flush=True)
                        break

                time.sleep(5)

    elif choice == "2":
        # 场景2：断开重连测试
        print("\n" + "=" * 80)
        print("运行场景2：断开重连测试")
        print("=" * 80 + "\n")
        result = test_scenario_2_disconnect(files)

    elif choice == "3":
        # 运行全部测试
        print("\n" + "=" * 80)
        print("运行全部测试场景")
        print("=" * 80 + "\n")

        # 场景1
        print("\n▶️  开始场景1...")
        task_id_1 = test_scenario_1_file_upload_progress(files)
        time.sleep(3)

        # 场景2
        print("\n▶️  开始场景2...")
        result_2 = test_scenario_2_disconnect(files)

    else:
        print(f"\n❌ 无效的选项: {choice}")
        return

    print("\n" + "=" * 80)
    print("✅ 测试完成")
    print("=" * 80)


if __name__ == "__main__":
    main()
