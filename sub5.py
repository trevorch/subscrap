import asyncio
import time
import json
import re
import os
import base64
from playwright.async_api import async_playwright
SUB5_JSON_URL = os.environ.get('SUB5_JSON_URL')
async def fetch_via_proxy(page, target_url):
    """
    通过 siteproxy 代理访问目标 URL 并获取页面文本内容
    """
    print("正在访问代理网站...")
    await page.goto("https://siteproxy.ai/zh-Hans")

    print(f"正在输入 URL: {target_url}")
    await page.fill('input#url-input', target_url)

    print("点击开启代理...")
    await page.click('button:has-text("开启代理")')

    print("处理弹窗...")
    try:
        await page.click('button:has-text("跳过并开始浏览")', timeout=5000)
        print("已点击跳过")
    except Exception as e:
        print("未检测到跳过按钮或已自动跳过，继续执行...")

    print("等待结果加载...")
    await page.wait_for_timeout(10000) 
    
    body_text = await page.inner_text('body')
    return body_text.strip()

async def main():
    timestamp = int(time.time() * 1000)
    target_url = f"{SUB5_JSON_URL}?t={timestamp}"
    print(f"目标 JSON 地址: {target_url}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            # 1. 获取 JSON 数据
            body_text = await fetch_via_proxy(page, target_url)
            
            try:
                data = json.loads(body_text)
            except json.JSONDecodeError:
                json_match = re.search(r'\{.*\}', body_text, re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group())
                else:
                    print("无法从页面提取 JSON 数据")
                    return

            print(f"获取到数据，日期: {data.get('date')}")

            # 2. 遍历 subscriptions 数组，抓取并解码内容
            subscriptions = data.get('subscriptions', [])
            all_content = []

            for i, sub in enumerate(subscriptions):
                url = sub['url']
                print(f"\n[{i+1}/{len(subscriptions)}] 正在访问订阅: {url}")
                
                sub_text = await fetch_via_proxy(page, url)
                
                # 尝试进行 Base64 解码
                try:
                    # 去除可能存在的换行符和空格
                    clean_text = sub_text.replace("\n", "").replace("\r", "").strip()
                    decoded_content = base64.b64decode(clean_text).decode('utf-8')
                    all_content.append(f"--- 订阅 {i+1}: {url} ---\n{decoded_content}\n")
                    print(f"成功解码并获取内容 (长度: {len(decoded_content)})")
                except Exception as e:
                    # 如果解码失败，保留原始文本以防数据丢失
                    print(f"Base64 解码失败: {e}, 丢弃")
                    #all_content.append(f"--- 订阅 {i+1}: {url} (未解码) ---\n{sub_text}\n")

            # 3. 写入文件 sub5.txt
            with open('sub5.txt', 'w', encoding='utf-8') as f:
                f.write('\n'.join(all_content))
            
            print("\n✅ 所有内容已解码并写入 sub5.txt")

        except Exception as e:
            print(f"执行过程中发生错误: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
