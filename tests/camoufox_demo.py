import time
from camoufox import Camoufox

# 使用默认设置启动 CamouFox
# with Camoufox() as browser:
#     page = browser.new_page()
#     page.goto("https://www.browserscan.net/zh/bot-detection")
#     content = page.content()
#     print(f"页面标题: {page.title()}")
#     page.screenshot(path="camoufox_screenshot.png", full_page=True)

config = {
    # "geolocation:latitude": 40.7128,
    # "geolocation:longitude": -74.0060,
    # "geolocation:accuracy": 10,
    # "locale:language": "en",
    # "locale:region": "US",
    # "timezone": "America/New_York"
    "humanize": True,  # 启用类人鼠标移动
    "humanize:maxTime": 1.2,  # 鼠标移动最大时间（秒）
}

with Camoufox(
    geoip=True,
    config={
        # "geolocation:latitude": 40.7128,
        # "geolocation:longitude": -74.0060,
        # "geolocation:accuracy": 10,
        # "locale:language": "en",
        # "locale:region": "US",
        # "timezone": "America/New_York"
        "humanize": True,  # 启用类人鼠标移动
        "humanize:maxTime": 1.2,  # 鼠标移动最大时间（秒）
    },
    # webgl_config=("Apple", "Apple M1, or similar"),
    # os="macos",
    # headless="virtual"
) as browser:
    page = browser.new_page()
    # page.goto("https://bot.sannysoft.com")  # 一个指纹测试网站
    page.goto("https://www.browserscan.net/bot-detection", wait_until="domcontentloaded")  # 一个指纹测试网站
    time.sleep(5)  # 等待页面加载完成
    print(f"页面标题: {page.title()}")
    page.screenshot(path="fingerprint_test.png", full_page=True)
    page.goto("https://www.browserscan.net/canvas", wait_until="domcontentloaded")  # Canvas 指纹测试
    time.sleep(5)  # 等待页面加载完成
    print(f"页面标题: {page.title()}")
    page.screenshot(path="canvas_fingerprint_test.png", full_page=True)
    page.goto("https://www.browserscan.net/timezone", wait_until="domcontentloaded")  # Canvas 指纹测试
    time.sleep(5)  # 等待页面加载完成
    print(f"页面标题: {page.title()}")
    page.screenshot(path="timezone_fingerprint_test.png", full_page=True)
    page.goto("https://www.browserscan.net/user-agent", wait_until="domcontentloaded")
    time.sleep(5)  # 等待页面加载完成
    print(f"页面标题: {page.title()}")
    page.screenshot(path="ua_fingerprint_test.png", full_page=True)
