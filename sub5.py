import asyncio
import re
from playwright.async_api import async_playwright

async def main():
    # 目标网址
    url = "https://www.v2raya.net/free-nodes/free-v2ray-node-subscriptions.html"
    # CSS 选择器
    selector = "#free_subscription_list > ul > li"

    async with async_playwright() as p:
        # 启动浏览器 (headless=False 可以看到浏览器界面，方便调试)
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        print(f"正在访问 {url}...")
        await page.goto(url)

        # 等待元素出现，确保页面内容已加载
        try:
            await page.wait_for_selector(selector, timeout=10000)
        except Exception:
            print("未能找到指定的元素，请检查选择器或页面加载情况。")
            await browser.close()
            return

        # 获取所有匹配的 li 元素
        li_elements = await page.query_selector_all(selector)
        print(f"找到 {len(li_elements)} 个列表项。")

        urls = []
        for li in li_elements:
            # 获取 li 元素内的所有文本
            text_content = await li.text_content()
            # 使用正则表达式从文本中提取所有网址
            found_urls = re.findall(r'https?://[^\s]+', text_content)
            urls.extend(found_urls)

        await browser.close()

        # 打印结果
        if urls:
            print("\n提取到的网址如下：")
            for u in urls:
                print(u)
        else:
            print("未在列表项中提取到任何网址。")

# 运行主函数
if __name__ == "__main__":
    asyncio.run(main())
