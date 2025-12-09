"""Headless 策略包。"""

# 自动导入子模块以触发注册
from .registry import get_route, route

__all__ = ["get_route", "route"]
