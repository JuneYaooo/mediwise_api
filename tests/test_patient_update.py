#!/usr/bin/env python3
"""
患者数据更新测试脚本（使用chat接口）

测试场景：通过对话接口更新现有患者数据
- 需要先通过 test_flow_simple.py 创建患者，获取 patient_id
- 将 patient_id 填入下方的 PATIENT_ID 变量
- 然后运行本脚本补充新的文件和描述

使用说明：
1. 修改下方的 PATIENT_ID 为实际的患者ID
2. python test_patient_update.py

接口说明：
- 使用新的 POST /api/patients/{patient_id}/chat 接口
- 支持对话式交互更新患者信息
- 自动合并现有数据和新数据
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
PATIENT_ID = "9fe7227c-1b98-4e6b-aed3-dec22172f091"  # 👈 修改这里

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


def update_patient_with_files(patient_id, files):
    """
    测试场景1：通过chat接口新增患者数据（上传文件）
    
    这会触发 modify_type = "add_new_data"，使用 PatientDataCrew 处理
    """
    print(f"\n{'='*80}")
    print(f"🔄 测试场景1：新增患者数据（上传文件）")
    print(f"{'='*80}\n")

    payload = {
        "message": "补充最新复查报告和影像资料，用于跟踪治疗效果，调整治疗方案",
        "files": files
    }
    
    return _send_chat_request(patient_id, payload)


def modify_patient_data(patient_id):
    """
    测试场景2：修改现有患者数据（不上传文件）
    
    这会触发 modify_type = "modify_current_data"，使用 PatientInfoUpdateCrew 处理
    """
    print(f"\n{'='*80}")
    print(f"🔄 测试场景2：修改现有患者数据")
    print(f"{'='*80}\n")

    payload = {
        "message": "请把患者的过敏史更新为：青霉素过敏、头孢类过敏",
        "files": []  # 不上传文件，只修改现有数据
    }
    
    return _send_chat_request(patient_id, payload)


def _send_chat_request(patient_id, payload):
    """发送chat请求的通用方法"""
    files = payload.get('files', [])
    
    print(f"📤 发送请求到: {API_BASE_URL}/api/patients/{patient_id}/chat")
    print(f"🆔 患者ID: {patient_id}")
    print(f"📊 消息内容: {payload['message']}")
    print(f"📁 文件数量: {len(files)}")
    print(f"⏰ 时间: {get_beijing_time()}")

    try:
        response = requests.post(
            f"{API_BASE_URL}/api/patients/{patient_id}/chat",
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

        update_success = False

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

                        status = data.get('status')
                        
                        # 接收确认
                        if status == 'received':
                            print(f"📨 {data.get('message', '消息已接收')}")
                        
                        # 显示进度
                        elif status == 'processing':
                            progress = data.get('progress', 0)
                            message = data.get('message', '')
                            stage = data.get('stage', '')
                            stage_info = f' ({stage})' if stage else ''
                            
                            # 显示意图识别结果
                            if stage == 'intent_detected':
                                intent = data.get('intent', '')
                                confidence = data.get('intent_confidence', 0)
                                print(f"[{progress:3d}%] {message}")
                                print(f"       🎯 识别意图: {intent} (置信度: {confidence:.0%})")
                            else:
                                print(f"[{progress:3d}%] {message}{stage_info}")

                        # 流式返回AI回复内容
                        elif status == 'streaming':
                            content = data.get('content', '')
                            if content:
                                print(content, end='', flush=True)
                        
                        # 工具输出（结构化数据）
                        elif status == 'tool_output':
                            tool_data = data.get('data', {})
                            tool_name = tool_data.get('tool_name', '')
                            print(f"\n📊 收到工具输出: {tool_name}")
                            if DEBUG_PRINT_RAW_API:
                                print(f"    内容: {json.dumps(tool_data.get('content', {}), ensure_ascii=False)[:500]}...")

                        # 完成
                        elif status == 'completed':
                            result_data = data.get('result', {})  # 修复：使用 'result' 而不是 'data'

                            print(f"\n{'='*80}")
                            print(f"✅ 患者数据更新成功!")
                            print(f"{'='*80}")
                            print(f"  患者ID: {result_data.get('patient_id')}")
                            print(f"  会话ID: {result_data.get('conversation_id')}")
                            print(f"  识别意图: {result_data.get('intent', 'N/A')}")
                            print(f"  处理文件: {result_data.get('files_processed', 0)} 个")  # 修复：使用 'files_processed'
                            print(f"  消息: {data.get('message', '')}")
                            print(f"  耗时: {data.get('duration', 0):.2f} 秒")
                            print(f"{'='*80}\n")

                            update_success = True

                        # 错误
                        elif status == 'error':
                            print(f"\n{'='*80}")
                            print(f"❌ 处理失败")
                            print(f"{'='*80}")
                            print(f"  错误信息: {data.get('message')}")
                            print(f"  错误类型: {data.get('error_type', 'Unknown')}")
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
    
    # 选择测试场景
    print(f"\n{'='*80}")
    print(f"请选择测试场景:")
    print(f"  1. 新增患者数据（上传文件）- 使用 PatientDataCrew")
    print(f"  2. 修改现有患者数据（不上传文件）- 使用 PatientInfoUpdateCrew")
    print(f"  3. 两个场景都测试")
    print(f"{'='*80}")
    
    choice = input("请输入选项 (1/2/3，默认1): ").strip() or "1"
    
    success = True
    
    if choice in ["1", "3"]:
        # 场景1：新增患者数据（上传文件）
        files = load_last_n_files(max_files=MAX_FILES)
        success = update_patient_with_files(PATIENT_ID, files) and success
    
    if choice in ["2", "3"]:
        # 场景2：修改现有患者数据
        if choice == "3":
            print(f"\n{'='*80}")
            print(f"⏳ 等待3秒后开始场景2...")
            print(f"{'='*80}")
            import time
            time.sleep(3)
        success = modify_patient_data(PATIENT_ID) and success

    if success:
        print(f"\n🎉 患者数据更新测试完成!")
        print(f"\n💡 提示: 可以继续使用相同的 patient_id 多次更新")
    else:
        print(f"\n⚠️  患者数据更新失败")
        sys.exit(1)


if __name__ == "__main__":
    main()
