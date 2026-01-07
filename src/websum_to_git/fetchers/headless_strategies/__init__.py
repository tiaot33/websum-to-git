"""Headless 策略包。"""

# 导入注册表 API
from . import custom as _custom  # noqa: F401

# 导入具体策略模块以触发 @route 注册
# 仅通过导入产生副作用，不直接在此处使用
from . import telegram as _telegram  # noqa: F401
from . import twitter as _twitter  # noqa: F401
from .registry import get_route, route

__all__ = ["get_route", "route"]
