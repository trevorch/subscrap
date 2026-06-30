#!/usr/bin/env python3

import os
import requests
import time
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 从环境变量获取JSON URL，方便在GitHub Actions中配置
SUB5_JSON_URL = os.environ.get('SUB5_JSON_URL')
SUB5_HOST = os.environ.get('SUB5_HOST')
# 完善浏览器请求头，包含 User-Agent, Referer, Accept 等
headers = {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
      "Referer": SUB5_HOST,
      "Accept": "text/html,application/xhtml+xml,application/json,application/xml;q=0.9,image/webp,*/*;q=0.8",
      "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"
}
def create_session_with_retries():
    """
    创建一个带有自动重试机制的 requests.Session 对象
    """
    session = requests.Session()
    # 定义重试策略
    retries = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS", "POST"]
    )
    session.mount('http://', HTTPAdapter(max_retries=retries))
    session.mount('https://', HTTPAdapter(max_retries=retries))
    return session

def fetch_subscription(url, session):
    """
    请求单个订阅链接并返回其内容
    """
    try:
        
        response = session.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        content = response.text.strip()
        
        # 尝试自动解码 Base64
        try:
            decoded_content = base64.b64decode(content).decode('utf-8', 'ignore')
            # 简单判断：如果解码后包含常见的协议头，说明解码成功
            if any(protocol in decoded_content for protocol in ['vmess://', 'trojan://', 'ss://', 'vless://']):
                return decoded_content
        except Exception:
            pass  # 解码失败则返回原始文本
            
        return content
    except requests.exceptions.RequestException as e:
        print(f"获取内容失败 [{url}]: {e}")
        return None

def main():
    # 1. 获取当前时间戳（毫秒级）
    timestamp = int(time.time() * 1000)
    json_url = f"{SUB5_JSON_URL}?t={timestamp}"

    # 使用带有重试机制的 session
    session = create_session_with_retries()

    try:
        # 2. 获取 JSON 列表
        response = session.get(json_url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        subscriptions = data.get("subscriptions", [])
        urls = [item["url"] for item in subscriptions if "url" in item]

        if not urls:
            print("未获取到任何订阅链接。")
            return

        print(f"开始获取 {len(urls)} 个订阅链接的内容...")

        # 3. 并发获取每个 URL 的内容
        all_contents = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_url = {executor.submit(fetch_subscription, url, session): url for url in urls}
            for future in as_completed(future_to_url):
                content = future.result()
                if content:
                    all_contents.append(content)

        if not all_contents:
            print("未获取到任何有效的订阅内容。")
            return

        # 4. 将获取到的所有明文内容合并，并重新编码为 Base64
        combined_content = "\n".join(all_contents)
        encoded_content = base64.b64encode(combined_content.encode('utf-8')).decode('utf-8')

        # 5. 将 Base64 字符串写入 sub5.txt
        with open("sub5.txt", "w", encoding="utf-8") as f:
            f.write(encoded_content)

        print(f"成功获取 {len(all_contents)} 个有效订阅内容，并已重新编码为 Base64 写入 sub5.txt")

    except requests.exceptions.RequestException as e:
        print(f"获取 JSON 列表失败: {e}")
    except Exception as e:
        print(f"发生未知错误: {e}")

if __name__ == "__main__":
    main()
