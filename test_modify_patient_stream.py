#!/usr/bin/env python3
"""
测试患者数据修改接口的流式回答功能
测试 /api/patient_data/modify_patient_data 接口
"""

import requests
import json
import sys
import time

# 配置
BASE_URL = "http://localhost:9527"
API_ENDPOINT = f"{BASE_URL}/api/patient_data/modify_patient_data"

# 测试用的 patient_id（需要替换为实际存在的 patient_id）
TEST_PATIENT_ID = "test_patient_001"

# 测试用的修改需求
TEST_MODIFICATION_REQUEST = "将患者年龄修改为45岁，性别修改为女性"

# 测试用的认证token（如果需要的话）
AUTH_TOKEN = None  # 如果需要认证，在这里填写token


def test_modify_patient_stream():
    """测试患者数据修改的流式接口"""

    print("=" * 80)
    print(f"测试患者数据修改流式接口")
    print("=" * 80)
    print()

    # 准备请求数据
    request_data = {
        "patient_id": TEST_PATIENT_ID,
        "modification_request": TEST_MODIFICATION_REQUEST,
        "files": []  # 可选：添加文件
    }

    # 准备请求头
    headers = {
        "Content-Type": "application/json",
    }

    if AUTH_TOKEN:
        headers["Authorization"] = f"Bearer {AUTH_TOKEN}"

    print(f"📤 发送请求到: {API_ENDPOINT}")
    print(f"📋 请求数据:")
    print(f"   - patient_id: {TEST_PATIENT_ID}")
    print(f"   - modification_request: {TEST_MODIFICATION_REQUEST}")
    print()
    print("⏳ 等待流式响应...")
    print("-" * 80)
    print()

    try:
        # 发送流式请求
        response = requests.post(
            API_ENDPOINT,
            json=request_data,
            headers=headers,
            stream=True,  # 关键：启用流式传输
            timeout=600   # 10分钟超时
        )

        if response.status_code != 200:
            print(f"❌ 请求失败: HTTP {response.status_code}")
            print(f"错误信息: {response.text}")
            return False

        # 解析流式响应
        task_id = None
        message_count = 0
        streaming_response_count = 0
        current_stage = None

        for line in response.iter_lines():
            if not line:
                continue

            # 解码行
            line_str = line.decode('utf-8')

            # 跳过非数据行
            if not line_str.startswith('data: '):
                continue

            # 提取JSON数据
            json_str = line_str[6:]  # 去掉 "data: " 前缀

            try:
                data = json.loads(json_str)
                message_count += 1

                # 保存 task_id（从第一条消息中获取）
                if task_id is None and 'task_id' in data:
                    task_id = data['task_id']
                    print(f"🆔 Task ID: {task_id}")
                    print()

                # 显示状态变化
                if 'stage' in data and data['stage'] != current_stage:
                    current_stage = data['stage']
                    print(f"\n📍 阶段: {current_stage}")

                # 显示进度
                if 'progress' in data:
                    progress = data['progress']
                    print(f"   进度: {progress}%", end='')

                # 显示消息
                if 'message' in data and data['message']:
                    msg = data['message']
                    print(f" | 消息: {msg[:50]}{'...' if len(msg) > 50 else ''}")

                # 显示流式确认消息（关键部分）
                if data.get('status') == 'streaming_response':
                    streaming_response_count += 1
                    is_chunk = data.get('is_chunk', False)

                    if is_chunk:
                        # 流式文本片段
                        chunk_text = data.get('message', '')
                        if chunk_text:
                            print(f"💬 {chunk_text}", end='', flush=True)
                    else:
                        # 流式结束
                        if data.get('stage') == 'confirmation_complete':
                            print()  # 换行
                            print("\n✅ 流式确认消息完成")

                # 显示最终结果
                if data.get('status') == 'completed':
                    print()
                    print("-" * 80)
                    print("✅ 患者数据修改完成!")
                    print()

                    if 'duration' in data:
                        duration = data['duration']
                        print(f"⏱️  总耗时: {duration:.2f} 秒")

                    if 'result' in data:
                        result = data['result']
                        print()
                        print("📊 修改结果:")
                        print(f"   - patient_id: {result.get('patient_id')}")
                        print(f"   - conversation_id: {result.get('conversation_id')}")
                        print(f"   - 上传文件数: {result.get('uploaded_files_count', 0)}")

                    print()
                    print(f"📈 统计:")
                    print(f"   - 总消息数: {message_count}")
                    print(f"   - 流式确认消息数: {streaming_response_count}")

                # 显示错误
                if data.get('status') == 'error':
                    print()
                    print("-" * 80)
                    print(f"❌ 修改失败: {data.get('message')}")
                    if 'error' in data:
                        print(f"   错误详情: {data['error']}")
                    return False

            except json.JSONDecodeError as e:
                print(f"⚠️  JSON解析错误: {e}")
                print(f"   原始数据: {json_str[:100]}")

        print()
        print("=" * 80)
        print("✅ 测试完成")
        print("=" * 80)

        # 判断是否有流式确认消息
        if streaming_response_count > 0:
            print(f"\n✅ 流式确认消息功能正常！(共{streaming_response_count}条流式消息)")
            return True
        else:
            print(f"\n⚠️  警告：没有检测到流式确认消息")
            return False

    except requests.exceptions.Timeout:
        print("❌ 请求超时")
        return False
    except requests.exceptions.RequestException as e:
        print(f"❌ 请求异常: {e}")
        return False
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断测试")
        return False


def print_usage():
    """打印使用说明"""
    print("使用方法:")
    print(f"  python {sys.argv[0]} [patient_id] [modification_request]")
    print()
    print("示例:")
    print(f"  python {sys.argv[0]} test_patient_001 '将患者年龄修改为45岁'")
    print()
    print("注意:")
    print("  - patient_id 必须是已存在的患者ID")
    print("  - 该患者必须已经有结构化数据")
    print("  - 如果需要认证，请在脚本中设置 AUTH_TOKEN")


if __name__ == "__main__":
    # 解析命令行参数
    if len(sys.argv) > 1:
        if sys.argv[1] in ['-h', '--help']:
            print_usage()
            sys.exit(0)
        TEST_PATIENT_ID = sys.argv[1]

    if len(sys.argv) > 2:
        TEST_MODIFICATION_REQUEST = sys.argv[2]

    # 运行测试
    success = test_modify_patient_stream()

    sys.exit(0 if success else 1)
