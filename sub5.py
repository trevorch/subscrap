import os
import time
import json
from playwright.sync_api import sync_playwright

SUB5_JSON_URL = os.environ.get('SUB5_JSON_URL')

def main():
    # 1. 生成带时间戳的 URL
    timestamp = int(time.time() * 1000)
    url = f"{SUB5_JSON_URL}?t={timestamp}"
    
    print(f"正在访问: {url}")
    
    with sync_playwright() as p:
        # 启动浏览器 (建议设置为 headless=True 以在后台运行)
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        try:
            # 访问 JSON 接口
            page.goto(url)
            # 获取页面内容
            content = page.text_content('body')
            data = json.loads(content)
            
            subscriptions = data.get('subscriptions', [])
            print(f"获取到 {len(subscriptions)} 个订阅链接")
            
            # 2. 遍历并抓取内容
            with open('sub5.txt', 'w', encoding='utf-8') as f:
                for index, sub in enumerate(subscriptions):
                    sub_url = sub.get('url')
                    if sub_url:
                        print(f"[{index + 1}/{len(subscriptions)}] 正在抓取: {sub_url}")
                        try:
                            # 访问订阅链接
                            sub_page = browser.new_page()
                            sub_page.goto(sub_url, timeout=10000) # 设置超时时间
                            sub_content = sub_page.text_content('body')
                            
                            # 写入文件
                            f.write(sub_content.strip() + '\n')
                            sub_page.close()
                        except Exception as e:
                            print(f"抓取失败 {sub_url}: {e}")
            
            print("所有任务完成，内容已写入 sub5.txt")
            
        except Exception as e:
            print(f"发生错误: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    main()
