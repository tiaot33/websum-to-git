#!/bin/bash
set -euo pipefail

# 1. 在后台启动 Xvfb，创建一个虚拟显示器，编号为 99
# 分辨率为 1920x1080，色深为 24
Xvfb :99 -screen 0 1920x1080x24 &

# 2. 将 DISPLAY 环境变量设置为指向我们创建的虚拟显示器
export DISPLAY=:99

# 3. 等待 Xvfb 完全启动 (可选，但建议)
sleep 2

# 4. 使用虚拟环境中的 Python 执行应用
echo "Starting application in headed mode..."
exec /app/.venv/bin/python src/main.py --config /app/config.yaml
