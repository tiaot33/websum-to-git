# ========================================
# 多阶段构建 - 构建阶段
# ========================================
FROM python:3.13-slim AS builder

WORKDIR /app

# 安装 UV（快速的 Python 包管理器）
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# 复制依赖配置文件
COPY pyproject.toml uv.lock ./

# 使用 UV 安装依赖到 .venv（带缓存加速）
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# 预下载 Camoufox 浏览器内核
RUN .venv/bin/python -m camoufox fetch

# ========================================
# 多阶段构建 - 运行阶段
# ========================================
FROM python:3.13-slim

WORKDIR /app

# 环境变量配置
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# 安装 Camoufox 运行时依赖 + Xvfb（虚拟显示）+ 清理缓存
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    libgtk-3-0 \
    libx11-xcb1 \
    libasound2 \
    xauth \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 创建非 root 用户（安全最佳实践）
RUN addgroup --system --gid 1001 appuser && \
    adduser --system --uid 1001 --gid 1001 appuser

# 从构建阶段复制虚拟环境（包含所有依赖）
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv

# 复制应用源码
COPY --chown=appuser:appuser src /app/src
COPY --chown=appuser:appuser entrypoint.sh /app/entrypoint.sh

# 设置执行权限
RUN chmod +x /app/entrypoint.sh

# 切换到非 root 用户运行
USER appuser

# 健康检查（每 30 秒检查一次）
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "from pathlib import Path; import sys, time; p = Path('/tmp/websum_bot_heartbeat'); t = float(p.read_text().strip()) if p.is_file() else 0.0; sys.exit(0 if time.time() - t < 120 else 1)" || exit 1

# 启动应用
ENTRYPOINT ["/app/entrypoint.sh"]
