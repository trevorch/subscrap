#!/usr/bin/env python3
"""
用 Playwright 无头浏览器
提取订阅链接并保存内容到：
  - sub0.txt
  - sub0/yyyymmdd.txt  （北京时间）
"""

import sys
import os
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

SUB0_HOME = os.environ.get('SUB0_HOME')
SUB0_HOST = os.environ.get('SUB0_HOME')
BEIJING_TZ = timezone(timedelta(hours=8))

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
}


# ── 1. 用 Playwright 获取 copy 属性 URL ─────────────────────────────────────

def get_copy_url() -> str:
    print(f"[*] 启动无头浏览器")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        context = browser.new_context(
            user_agent=BROWSER_HEADERS["User-Agent"],
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            # 伪装成真实浏览器，避免 bot 检测
            extra_http_headers={
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Referer": SUB0_HOST,
            },
        )
        page = context.new_page()

        # 隐藏 webdriver 标记
        page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        try:
            page.goto(SUB0_HOME, wait_until="networkidle", timeout=30_000)
        except PWTimeout:
            print("[!] networkidle 超时，尝试 domcontentloaded …")
            page.goto(SUB0_HOME, wait_until="domcontentloaded", timeout=30_000)

        # 等待目标按钮出现（最多 15 秒）
        selector = "button.itemCopy[copy]"
        try:
            page.wait_for_selector(selector, timeout=15_000)
        except PWTimeout:
            # 把当前 HTML 输出方便调试
            print("[!] 未找到 button.itemCopy，当前页面 HTML 片段：")
            print(page.content()[:3000])
            browser.close()
            raise RuntimeError(f"页面中找不到选择器 `{selector}`，结构可能已变更。")

        # 读取 copy 属性
        buttons = page.query_selector_all(selector)
        if not buttons:
            browser.close()
            raise RuntimeError("query_selector_all 返回空列表。")

        copy_url = buttons[0].get_attribute("copy")
        browser.close()

    if not copy_url or not copy_url.startswith("http"):
        raise RuntimeError(f"copy 属性值无效")

    print(f"[+] 获取到订阅链接")
    return copy_url


# ── 2. 下载订阅内容 ──────────────────────────────────────────────────────────

def fetch_subscription(sub_url: str) -> str:
    print(f"[*] 下载订阅内容")
    resp = requests.get(sub_url, headers=BROWSER_HEADERS, timeout=30)
    resp.raise_for_status()
    content = resp.text
    print(f"[+] 获取成功，长度: {len(content)} 字符")
    return content


# ── 3. 保存文件 ──────────────────────────────────────────────────────────────

def save_files(content: str) -> None:
    now_cst = datetime.now(BEIJING_TZ)
    date_str = now_cst.strftime("%Y%m%d")

    # sub0.txt（始终覆盖为最新）
    flat = Path("sub0.txt")
    flat.write_text(content, encoding="utf-8")
    print(f"[+] 已写入: {flat}")

    # sub0/yyyymmdd.txt
    dir_ = Path("sub0")
    dir_.mkdir(exist_ok=True)
    dated = dir_ / f"{date_str}.txt"
    dated.write_text(content, encoding="utf-8")
    print(f"[+] 已写入: {dated}")


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    try:
        sub_url = get_copy_url()
        content  = fetch_subscription(sub_url)
        save_files(content)
        print("[✓] 完成！")
    except Exception as exc:
        print(f"[✗] 失败: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
