FROM python:3.11-slim

LABEL maintainer="MediWise Team"
LABEL description="MediWise API Service - 医疗智能会诊PPT生成服务"

# 设置工作目录
WORKDIR /app

# 使用国内镜像源加速
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
    sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list || true

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    poppler-utils \
    libmagic1 \
    curl \
    redis-tools \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖 (使用国内镜像)
RUN pip install --no-cache-dir --upgrade pip -i https://mirrors.aliyun.com/pypi/simple/ && \
    pip install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

# 安装 Playwright 浏览器及依赖 (同时提供 Chromium 给 Kaleido/Plotly 使用)
RUN playwright install --with-deps chromium

# 设置 Chromium 路径供 Kaleido 使用
ENV CHROME_BIN=/root/.cache/ms-playwright/chromium-*/chrome-linux/chrome

# 复制应用代码
COPY . .

# 创建必要的目录
RUN mkdir -p uploads logs output

# 暴露端口
EXPOSE 9527

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:9527/health || exit 1

# 启动脚本
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9527"]
