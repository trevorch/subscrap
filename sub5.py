#!/usr/bin/env python3
import os
import requests
import time
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
SUB5_JSON_URL = os.environ.get('SUB5_JSON_URL')
def get_proxy():
    """
    从代理 API 获取一个 HTTP 代理
    返回格式为 "ip:port" 的字符串，如果失败则返回 None
    """
    proxy_api = "https://proxy.scdn.io/api/get_proxy.php?protocol=http&count=1"
    try:
        response = requests.get(proxy_api, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get("code") == 200 and data.get("data", {}).get("proxies"):
            proxy = data["data"]["proxies"][0]
            print(f"成功获取代理: {proxy}")
            return proxy
    except Exception as e:
        print(f"获取代理失败: {e}")
    return None

def fetch_subscription(url, proxy=None):
    """
    请求单个订阅链接并返回其内容
    """
    try:
        # 伪装请求头
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
        }
        
        # 设置代理
        proxies = None
        if proxy:
            proxies = {
                "http": f"http://{proxy}",
                "https": f"http://{proxy}"
            }
        
        response = requests.get(url, headers=headers, proxies=proxies, timeout=15)
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
    # 1. 获取代理
    proxy = get_proxy()
    if not proxy:
        print("警告：未能获取到代理，将尝试直接连接。")

    # 2. 获取当前时间戳（毫秒级）
    timestamp = int(time.time() * 1000)
    json_url = f"{SUB5_JSON_URL}?t={timestamp}"

    try:
        # 3. 获取 JSON 列表（使用代理）
        proxies = None
        if proxy:
            proxies = {"http": f"http://{proxy}", "https": f"http://{proxy}"}
            
        response = requests.get(json_url, proxies=proxies, timeout=10)
        response.raise_for_status()
        data = response.json()
        subscriptions = data.get("subscriptions", [])
        urls = [item["url"] for item in subscriptions if "url" in item]

        if not urls:
            print("未获取到任何订阅链接。")
            return

        print(f"开始获取 {len(urls)} 个订阅链接的内容...")

        # 4. 并发获取每个 URL 的内容（使用代理）
        all_contents = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_url = {executor.submit(fetch_subscription, url, proxy): url for url in urls}
            for future in as_completed(future_to_url):
                content = future.result()
                if content:
                    all_contents.append(content)

        if not all_contents:
            print("未获取到任何有效的订阅内容。")
            return

        # 5. 将获取到的所有明文内容合并，并重新编码为 Base64
        combined_content = "\n".join(all_contents)
        encoded_content = base64.b64encode(combined_content.encode('utf-8')).decode('utf-8')

        # 6. 将 Base64 字符串写入 sub5.txt
        with open("sub5.txt", "w", encoding="utf-8") as f:
            f.write(encoded_content)

        print(f"成功获取 {len(all_contents)} 个有效订阅内容，并已重新编码为 Base64 写入 sub5.txt")

    except requests.exceptions.RequestException as e:
        print(f"获取 JSON 列表失败: {e}")
    except Exception as e:
        print(f"发生未知错误: {e}")

if __name__ == "__main__":
    main()
