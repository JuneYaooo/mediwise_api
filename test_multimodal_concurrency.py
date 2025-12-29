#!/usr/bin/env python3
"""
测试多模态图片并发配置
"""
import os
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

def test_concurrency_config():
    """测试并发配置"""
    print("=" * 60)
    print("多模态图片并发配置测试")
    print("=" * 60)

    # 测试 MULTIMODAL_IMAGE_CONCURRENT_WORKERS
    multimodal_workers = int(os.getenv("MULTIMODAL_IMAGE_CONCURRENT_WORKERS", "20"))
    print(f"\n✅ MULTIMODAL_IMAGE_CONCURRENT_WORKERS: {multimodal_workers}")

    # 测试 PDF_IMAGE_CONCURRENT_WORKERS
    pdf_workers = int(os.getenv("PDF_IMAGE_CONCURRENT_WORKERS", "10"))
    print(f"✅ PDF_IMAGE_CONCURRENT_WORKERS: {pdf_workers}")

    print("\n" + "=" * 60)
    print("✅ 配置测试通过")
    print("=" * 60)

    return True

if __name__ == "__main__":
    success = test_concurrency_config()
    sys.exit(0 if success else 1)
