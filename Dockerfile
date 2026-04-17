# ========================================
# 多阶段构建 - 构建阶段
# ========================================
FROM python:3.13-slim AS builder

WORKDIR /app

# 安装构建依赖（git 用于从 Git 仓库安装 camoufox）
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get update && \
    apt-get install -y --no-install-recommends git curl && \
    rm -rf /var/lib/apt/lists/*

# 安装 UV（快速的 Python 包管理器）
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# 复制依赖配置文件
COPY pyproject.toml uv.lock ./

# 使用 UV 安装依赖到 .venv（带缓存加速）
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# ========================================
# 多阶段构建 - 运行阶段
# ========================================
FROM python:3.13-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    HOME="/app"

ARG CAMOUFOX_VERSION=official/prerelease/146.0.1-alpha.25

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        libgtk-3-0 \
        libx11-xcb1 \
        libasound2 \
        libgl1-mesa-dri libglu1-mesa mesa-utils \
        libegl1 \
        libgbm1 \
        ca-certificates \
        curl \
        jq \
        xvfb \
        git && rm -rf /var/lib/apt/lists/*

ENV MOZ_WEBGL_FORCE_EGL=1 \
    MOZ_X11_EGL=1 \
    LIBGL_ALWAYS_SOFTWARE=1 \
    GALLIUM_DRIVER=llvmpipe=value

# 预创建 X11 套接字目录（需要 root 权限）
RUN mkdir -p /tmp/.X11-unix && chmod 1777 /tmp/.X11-unix

# 从构建阶段复制虚拟环境（包含所有依赖）
COPY --from=builder /app/.venv /app/.venv
# 预下载固定版本的 Camoufox 浏览器内核。
# 不能先执行 `camoufox set ...` 再 `camoufox fetch`：
# 第一次 fetch 会清理兼容目录，导致 set 刚写入的 config.json 被删除，随后回退到默认 stable。
# prerelease 安装会触发交互确认，这里显式输入 y，保证 Docker build 非交互可执行。
RUN printf 'y\n' | /app/.venv/bin/python -m camoufox fetch "${CAMOUFOX_VERSION}" && \
    /app/.venv/bin/python -m camoufox set "${CAMOUFOX_VERSION}"

# 复制应用源码
COPY src /app/src
COPY entrypoint.sh /app/entrypoint.sh

# 设置执行权限
RUN chmod +x /app/entrypoint.sh

# 健康检查（每 30 秒检查一次）
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "from pathlib import Path; import sys, time; p = Path('/tmp/websum_bot_heartbeat'); t = float(p.read_text().strip()) if p.is_file() else 0.0; sys.exit(0 if time.time() - t < 120 else 1)" || exit 1

# 启动应用
ENTRYPOINT ["/app/entrypoint.sh"]
