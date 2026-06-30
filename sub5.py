import asyncio
import time
import os
from playwright.async_api import async_playwright

async def main():
    # 1. 生成带时间戳的 URL
    timestamp = int(time.time() * 1000)
    target_url = f"https://www.v2raya.net/free-node-store/free-subscriptions.json?t={timestamp}"
    print(f"目标 JSON 地址: {target_url}")

    async with async_playwright() as p:
        # 启动浏览器 (设置为 headless=False 可以看到浏览器操作过程，调试完成后建议改为 True)
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # 访问代理网站
        print("正在访问代理网站...")
        await page.goto("https://siteproxy.ai/zh-Hans")

        # 在输入框输入目标 URL
        print("正在输入 URL...")
        await page.fill('input#url-input', target_url)

        # 点击 "开启代理" 按钮
        print("点击开启代理...")
        # 使用 text= 选择器匹配按钮文本
        await page.click('button:has-text("开启代理")')

        # 处理弹窗：点击 "跳过并开始浏览"
        print("处理弹窗...")
        try:
            # 等待按钮出现并点击，设置超时时间防止卡死
            await page.click('button:has-text("跳过并开始浏览")', timeout=5000)
            print("已点击跳过")
        except Exception as e:
            print("未检测到跳过按钮或已自动跳过，继续执行...")

        # 等待页面加载并获取结果
        # 假设结果会以文本形式出现在页面上，或者我们需要拦截网络请求
        # 根据题目描述，结果结构是 JSON，通常这种工具会直接显示文本或提供下载
        # 这里我们尝试获取页面的文本内容，或者监听响应
        
        print("等待结果加载...")
        # 等待一段时间让内容加载，或者等待特定的元素出现
        # 由于不知道具体的结果展示元素，这里简单等待一下并获取 body 文本
        await page.wait_for_timeout(10000) 
        
        # 获取页面内容，假设 JSON 数据直接显示在页面上
        content = await page.content()
        
        # 尝试从页面中提取 JSON 数据
        # 这种方法比较取巧，实际可能需要根据页面结构调整
        # 如果页面直接显示 JSON，我们可以尝试解析
        import json
        import re
        
        # 尝试从页面文本中提取 JSON
        body_text = await page.inner_text('body')
        try:
            # 尝试直接解析整个 body 文本为 JSON (如果页面只显示 JSON)
            data = json.loads(body_text.strip())
        except json.JSONDecodeError:
            # 如果失败，尝试用正则提取 JSON
            json_match = re.search(r'\{.*\}', body_text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
            else:
                print("无法从页面提取 JSON 数据")
                await browser.close()
                return

        print(f"获取到数据: {data.get('date')}")

        # 2. 遍历 subscriptions 数组，访问每个 url，抓取内容
        subscriptions = data.get('subscriptions', [])
        all_content = []

        for i, sub in enumerate(subscriptions):
            url = sub['url']
            print(f"正在访问: {url}")
            
            # 创建新页面访问订阅链接
            sub_page = await context.new_page()
            try:
                await sub_page.goto(url, timeout=10000)
                # 获取页面内容
                sub_content = await sub_page.content()
                # 提取文本内容 (去除 HTML 标签)
                text_content = await sub_page.inner_text('body')
                all_content.append(f"--- 订阅 {i+1}: {url} ---\n{text_content}\n")
            except Exception as e:
                print(f"访问 {url} 失败: {e}")
            finally:
                await sub_page.close()

        # 3. 写入文件 sub5.txt
        with open('sub5.txt', 'w', encoding='utf-8') as f:
            f.write('\n'.join(all_content))
        
        print("所有内容已写入 sub5.txt")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
